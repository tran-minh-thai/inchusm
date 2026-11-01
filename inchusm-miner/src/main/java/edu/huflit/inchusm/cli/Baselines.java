package edu.huflit.inchusm.cli;

import edu.huflit.inchusm.graph.Graph;
import edu.huflit.inchusm.graph.GraphLoader;
import edu.huflit.inchusm.mining.HUSM;
import edu.huflit.inchusm.mining.IncHUSM;
import edu.huflit.inchusm.mining.Measure;
import edu.huflit.inchusm.mining.PatternState;
import edu.huflit.inchusm.mining.UtilityTable;

import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Stream;

/**
 * Alternative-strategy comparison over one snapshot stream, all methods in the same JVM run.
 *
 * INC  IncHUSM, measure=utility, bound=CEU (the exact reference).
 * B1   snapshot-local: static HUSM on G_t alone, high set = union over s<=t of HUS(G_s).
 *      Always sound (monotonicity), may miss patterns that cross theta only by
 *      accumulation; reported as recall against INC.
 * B2   support-filter incremental: IncHUSM in support mode (a support-based fringe over
 *      CMNI) with sigma = ceil(theta / u_max), then keep patterns with u >= theta.
 *      Exact because u(P) = CMNI(P) * mean(P) <= CMNI(P) * u_max.
 *
 * usage: java -cp inchusm-miner.jar edu.huflit.inchusm.cli.Baselines
 *            --snapshot-dir DIR --util u.tsv --minvalue X [--mer 1]
 *            [--max-edges 5] [--skip b1,b2] --out per_snapshot.csv
 *
 * Snapshots are read in filename order. One CSV row per snapshot; times in ms.
 * b2_ms includes the u >= theta filter. A skipped method reports -1 and a blank match.
 */
public final class Baselines {

    public static void main(String[] args) throws Exception {
        Map<String, String> opt = new HashMap<>();
        for (int i = 0; i < args.length; i++) {
            if (args[i].startsWith("--")) {
                if (i + 1 < args.length && !args[i + 1].startsWith("--")) opt.put(args[i], args[++i]);
                else opt.put(args[i], "true");
            }
        }
        Path dir = Path.of(opt.get("--snapshot-dir"));
        double theta = Double.parseDouble(opt.get("--minvalue"));
        int mer = Integer.parseInt(opt.getOrDefault("--mer", "1"));
        int maxEdges = Integer.parseInt(opt.getOrDefault("--max-edges", "5"));
        String skip = opt.getOrDefault("--skip", "");
        boolean runB1 = !skip.contains("b1");
        boolean runB2 = !skip.contains("b2");

        List<Path> paths;
        try (Stream<Path> s = Files.list(dir)) {
            paths = s.filter(p -> p.toString().endsWith(".lg"))
                    .sorted(Comparator.comparing(p -> p.getFileName().toString())).toList();
        }
        List<Graph> snaps = new ArrayList<>();
        for (Path p : paths) snaps.add(GraphLoader.loadLG(p));
        Map<Integer, Double> table = GraphLoader.loadUtilityTable(Path.of(opt.get("--util")));
        UtilityTable ext = new UtilityTable(table);
        double uMax = table.values().stream().mapToDouble(Double::doubleValue).max().orElse(1.0);
        double sigma = Math.ceil(theta / uMax);

        IncHUSM inc = new IncHUSM(new IncHUSM.Config(theta, mer, HUSM.Bound.CEU, Measure.UTILITY, maxEdges), ext);
        IncHUSM sup = new IncHUSM(new IncHUSM.Config(sigma, mer, HUSM.Bound.CEU, Measure.SUPPORT, maxEdges), ext);
        Set<String> b1Union = new HashSet<>();

        System.out.printf(Locale.ROOT, "stream: %d snapshots | theta=%s u_max=%s sigma=%s maxEdges=%d%n",
                snaps.size(), theta, uMax, sigma, maxEdges);
        Path out = Path.of(opt.get("--out"));
        if (out.getParent() != null) Files.createDirectories(out.getParent());
        long incCum = 0, b1Cum = 0, b2Cum = 0;
        try (PrintWriter w = new PrintWriter(Files.newBufferedWriter(out, StandardCharsets.UTF_8))) {
            w.println("snapshot,inc_ms,inc_high,inc_tracked,inc_seg,"
                    + "b1_ms,b1_found,b1_recall,b2_ms,b2_tracked,b2_seg,b2_high,b2_match");
            for (int i = 0; i < snaps.size(); i++) {
                Graph gt = snaps.get(i);

                inc.update(gt);
                IncHUSM.Stats st = inc.stats();
                Set<String> exact = new HashSet<>();
                for (PatternState ps : inc.highPatterns()) exact.add(ps.code().key());
                incCum += st.lastUpdateMs;

                long b1Ms = -1;
                int b1Found = -1;
                double recall = Double.NaN;
                if (runB1) {
                    long t0 = System.nanoTime();
                    HUSM.Result r = HUSM.mine(gt, ext, new HUSM.Config(theta, mer, HUSM.Bound.CEU, maxEdges));
                    b1Union.addAll(r.hus.keySet());
                    b1Ms = (System.nanoTime() - t0) / 1_000_000;
                    b1Cum += b1Ms;
                    int hit = 0;
                    for (String k : b1Union) if (exact.contains(k)) hit++;
                    b1Found = b1Union.size();
                    recall = exact.isEmpty() ? 1.0 : hit / (double) exact.size();
                    if (hit != b1Union.size()) System.out.println("WARN: B1 reported a non-high pattern");
                }

                long b2Ms = -1, b2Tracked = -1, b2Seg = -1;
                int b2High = -1;
                String match = "";
                if (runB2) {
                    sup.update(gt);
                    IncHUSM.Stats s2 = sup.stats();
                    long t0 = System.nanoTime();
                    Set<String> filt = new HashSet<>();
                    for (PatternState ps : sup.highPatterns()) {
                        if (ps.evaluation().utility() >= theta) filt.add(ps.code().key());
                    }
                    long filterMs = (System.nanoTime() - t0) / 1_000_000;
                    b2Ms = s2.lastUpdateMs + filterMs;
                    b2Cum += b2Ms;
                    b2Tracked = s2.patternsTracked;
                    b2Seg = s2.segmentsComputedLast;
                    b2High = filt.size();
                    match = filt.equals(exact) ? "OK" : "MISMATCH";
                }

                w.printf(Locale.ROOT, "%d,%d,%d,%d,%d,%d,%d,%.4f,%d,%d,%d,%d,%s%n",
                        i + 1, st.lastUpdateMs, exact.size(), st.patternsTracked, st.segmentsComputedLast,
                        b1Ms, b1Found, recall, b2Ms, b2Tracked, b2Seg, b2High, match);
                w.flush();
                System.out.printf(Locale.ROOT,
                        "t=%2d INC high=%d tracked=%d %dms | B1 found=%d recall=%.3f %dms | B2 tracked=%d %dms [%s]%n",
                        i + 1, exact.size(), st.patternsTracked, st.lastUpdateMs,
                        b1Found, recall, b1Ms, b2Tracked, b2Ms, match);
            }
        }
        Runtime rt = Runtime.getRuntime();
        System.gc(); System.gc();
        long retainedMb = (rt.totalMemory() - rt.freeMemory()) >> 20;
        String hwm = "";
        try { for (String l : Files.readAllLines(Path.of("/proc/self/status"))) if (l.startsWith("VmHWM")) hwm = l.replaceAll("\\s+", " "); } catch (Exception e) { }
        System.out.printf(Locale.ROOT, "MEM retainedHeapAfterGC=%dMB %s%n", retainedMb, hwm);
        System.out.printf(Locale.ROOT, "TOTAL inc=%dms b1=%dms b2=%dms segTotal inc=%d b2=%d%n",
                incCum, b1Cum, b2Cum, inc.stats().segmentsComputedTotal, sup.stats().segmentsComputedTotal);
    }
}
