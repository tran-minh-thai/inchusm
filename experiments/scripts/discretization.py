"""Discretization: AMLworld HI-Small daily stream with k = 4, 2, 8 amount buckets, IncHUSM
against a static re-run on the accumulated union after every snapshot (cli.Main stream
--compare-static). theta scales with the mean label utility (k+1)/2 relative to k=4:
theta = round(2000 * (k+1) / 5).

Cells: aml_k4 (theta 2000), aml_k2 (1200), aml_k8 (3600); about 66 minutes in total
on an i7-10750H. Columns are those of the stream command (experiments/README.md).

Run (needs datasets/amlworld/HI-Small_Trans.csv):
  python experiments/scripts/discretization.py
  python experiments/scripts/discretization.py --k 2
Output: results/discretization/<UTC time>_<commit>/aml_k*.csv|log + manifest.json
"""

from __future__ import annotations

import argparse
import csv

import run_record

THETA = {k: round(2000 * (k + 1) / 5) for k in (2, 4, 8)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", nargs="+", type=int, choices=[4, 2, 8], default=[4, 2, 8])
    run_record.common_args(ap)
    a = ap.parse_args()
    run = run_record.Run("discretization", a)
    for k in a.k:
        d = run.stream(f"aml_k{k}")
        out = run.run_cell(f"aml_k{k}", [
            "-jar", str(run_record.JAR), "stream", "--snapshot-dir", str(d),
            "--util", str(d / "utilities.tsv"), "--minvalue", str(THETA[k]),
            "--measure", "utility", "--bound", "ceu", "--mer", "1", "--max-edges", "5",
            "--compare-static"])
        if out is None:
            continue
        rows = list(csv.DictReader(out.open(encoding="utf-8")))
        ok = sum(r["match"] == "OK" for r in rows)
        inc = sum(int(r["inc_ms"]) for r in rows)
        st = sum(int(r["static_ms"]) for r in rows)
        print(f"  k={k} theta={THETA[k]}: match {ok}/{len(rows)}, high={rows[-1]['high_total']}, "
              f"tracked={rows[-1]['tracked']}, speedup={st / max(1, inc):.1f}x", flush=True)
    run.finish()


if __name__ == "__main__":
    main()
