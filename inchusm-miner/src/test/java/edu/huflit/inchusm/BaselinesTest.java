package edu.huflit.inchusm;

import edu.huflit.inchusm.cli.Baselines;
import edu.huflit.inchusm.graph.Graph;
import edu.huflit.inchusm.mining.UtilityTable;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * End-to-end check of the {@link Baselines} CLI on small streams written to disk.
 * After each snapshot: INC equals a definition-level count on the accumulated union,
 * B2 (support filter) returns exactly the INC set, and B1 (snapshot-local) reports a
 * subset of it.
 */
class BaselinesTest {

    private static final Map<Integer, Double> EXT = Map.of(1, 1.0, 2, 2.5, 3, 4.5);
    private static final int MAX_EDGES = 4;
    private static final int MER = 1;

    @TempDir
    Path tmp;

    @Test
    void supportFilterMatchesIncHusmAfterEachSnapshot() throws Exception {
        UtilityTable ext = new UtilityTable(EXT);
        int rowsWithPatterns = 0;
        for (long base : new long[] {10, 20, 30, 40, 50}) {
            List<Graph> stream = new ArrayList<>();
            for (int i = 0; i < 5; i++) stream.add(TestGraphs.random(base + i, 6 + (i % 3), 3, 3, 2));
            double theta = midThreshold(stream, ext);

            List<String[]> rows = runCli(stream, theta, "s" + base);
            assertEquals(stream.size(), rows.size(), "base=" + base);
            List<Graph> seen = new ArrayList<>();
            Set<String> localUnion = new HashSet<>();
            for (int t = 0; t < rows.size(); t++) {
                seen.add(stream.get(t));
                int expected = BruteForce.hus(TestGraphs.disjointUnion(seen), ext, MER, MAX_EDGES, theta).size();
                localUnion.addAll(BruteForce.hus(stream.get(t), ext, MER, MAX_EDGES, theta).keySet());
                String[] r = rows.get(t);
                String ctx = "base=" + base + " t=" + (t + 1) + " theta=" + theta;
                int incHigh = Integer.parseInt(r[2]);
                assertEquals(expected, incHigh, ctx + " INC");
                assertEquals("OK", r[12], ctx + " B2 match");
                assertEquals(incHigh, Integer.parseInt(r[11]), ctx + " B2 high");
                int b1Found = Integer.parseInt(r[6]);
                assertEquals(localUnion.size(), b1Found, ctx + " B1 = union of per-snapshot HUS");
                assertTrue(b1Found <= incHigh, ctx + " B1 reported more than INC");
                double recall = Double.parseDouble(r[7]);
                double want = incHigh == 0 ? 1.0 : b1Found / (double) incHigh;
                assertEquals(want, recall, 1e-4, ctx + " B1 recall");
                if (incHigh > 0) rowsWithPatterns++;
            }
        }
        // guard against a vacuous pass: the comparison must cover non-empty high sets
        assertTrue(rowsWithPatterns >= 10, "only " + rowsWithPatterns + " rows had high patterns");
    }

    @Test
    void snapshotLocalMissesPatternsThatOnlyAccumulate() throws Exception {
        // each snapshot is one 3-3 edge: u = 4.5 per snapshot, below theta = 10,
        // but the accumulated union reaches 13.5 at t = 3
        List<Graph> stream = new ArrayList<>();
        for (int i = 0; i < 3; i++) stream.add(new Graph(new int[] {3, 3}, List.<int[]>of(new int[] {0, 1, 0})));
        List<String[]> rows = runCli(stream, 10.0, "acc");
        String[] last = rows.get(rows.size() - 1);
        assertTrue(Integer.parseInt(last[2]) >= 1, "INC found no pattern at t=3");
        assertEquals(0, Integer.parseInt(last[6]), "B1 found a pattern no single snapshot supports");
        assertTrue(Double.parseDouble(last[7]) < 1.0, "B1 recall should drop below 1");
        assertEquals("OK", last[12]);
    }

    @Test
    void skipLeavesOnlyIncHusmColumns() throws Exception {
        List<Graph> stream = new ArrayList<>();
        for (int i = 0; i < 3; i++) stream.add(TestGraphs.random(70 + i, 7, 3, 3, 2));
        List<String[]> rows = runCli(stream, midThreshold(stream, new UtilityTable(EXT)), "skip",
                "--skip", "b1,b2");
        for (String[] r : rows) {
            assertEquals("-1", r[5], "b1_ms");
            assertEquals("-1", r[8], "b2_ms");
            assertEquals(12, r.length, "match column should be blank");
        }
    }

    private List<String[]> runCli(List<Graph> stream, double theta, String tag, String... extra)
            throws Exception {
        Path dir = Files.createDirectories(tmp.resolve(tag));
        for (int i = 0; i < stream.size(); i++) {
            writeLg(stream.get(i), dir.resolve(String.format(Locale.ROOT, "snap_%02d.lg", i + 1)));
        }
        Path util = dir.resolve("utilities.tsv");
        StringBuilder sb = new StringBuilder();
        for (var e : new TreeSet<>(EXT.keySet())) sb.append(e).append(' ').append(EXT.get(e)).append('\n');
        Files.writeString(util, sb.toString(), StandardCharsets.UTF_8);
        Path out = tmp.resolve(tag + ".csv");

        List<String> args = new ArrayList<>(List.of(
                "--snapshot-dir", dir.toString(), "--util", util.toString(),
                "--minvalue", Double.toString(theta), "--mer", Integer.toString(MER),
                "--max-edges", Integer.toString(MAX_EDGES), "--out", out.toString()));
        args.addAll(List.of(extra));
        Baselines.main(args.toArray(new String[0]));

        List<String> lines = Files.readAllLines(out, StandardCharsets.UTF_8);
        assertEquals("snapshot,inc_ms,inc_high,inc_tracked,inc_seg,"
                + "b1_ms,b1_found,b1_recall,b2_ms,b2_tracked,b2_seg,b2_high,b2_match", lines.get(0));
        List<String[]> rows = new ArrayList<>();
        for (String l : lines.subList(1, lines.size())) rows.add(l.split(","));
        return rows;
    }

    private static void writeLg(Graph g, Path path) throws IOException {
        StringBuilder sb = new StringBuilder();
        for (int v = 0; v < g.n(); v++) sb.append("v ").append(v).append(' ').append(g.vlabel(v)).append('\n');
        for (int u = 0; u < g.n(); u++) {
            int[] nbrs = g.neighbors(u);
            int[] labs = g.neighborEdgeLabels(u);
            for (int k = 0; k < nbrs.length; k++) {
                if (u < nbrs[k]) sb.append("e ").append(u).append(' ').append(nbrs[k]).append(' ').append(labs[k]).append('\n');
            }
        }
        Files.writeString(path, sb.toString(), StandardCharsets.UTF_8);
    }

    /** A threshold strictly between two distinct union utility values. */
    private static double midThreshold(List<Graph> stream, UtilityTable ext) {
        TreeSet<Double> utilities = new TreeSet<>();
        for (var s : BruteForce.allPatternStats(TestGraphs.disjointUnion(stream), ext, MER, MAX_EDGES).values()) {
            if (s.utility() > 0) utilities.add(s.utility());
        }
        List<Double> sorted = new ArrayList<>(utilities);
        int mid = Math.max(1, sorted.size() / 2);
        return (sorted.get(mid - 1) + sorted.get(mid)) / 2.0;
    }
}
