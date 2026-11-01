"""Alternative strategies: IncHUSM against snapshot-local mining (B1) and a support-filter
incremental miner (B2), all three in one JVM per stream (cli.Baselines).

  B1  static HUSM on each arriving snapshot alone, results unioned; reports b1_recall
      against the exact IncHUSM set.
  B2  IncHUSM in support mode with sigma = ceil(theta / u_max), then keep u >= theta;
      b2_match = OK when its set equals the IncHUSM set at that snapshot.

Cells (stream, theta):
  alt_elliptic  elliptic       500
  alt_amlworld  aml_k4        2000
  alt_S         synth_N1500    800
  alt_L         synth_N3000   1600

Run (Elliptic and AMLworld need the datasets, see docs/reproduce/paper2.md):
  python experiments/scripts/alt_strategies.py
  python experiments/scripts/alt_strategies.py --only alt_S alt_L
Output: results/alt_strategies/<UTC time>_<commit>/alt_*.csv|log + manifest.json
"""

from __future__ import annotations

import argparse
import csv
import sys

import run_record

CELLS = {
    "alt_elliptic": ("elliptic", 500),
    "alt_amlworld": ("aml_k4", 2000),
    "alt_S": ("synth_N1500", 800),
    "alt_L": ("synth_N3000", 1600),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", choices=list(CELLS), default=list(CELLS))
    run_record.common_args(ap)
    a = ap.parse_args()
    run = run_record.Run("alt_strategies", a)
    for cell in a.only:
        name, theta = CELLS[cell]
        out = run.run_cell(cell, run_record.baselines_args(run.stream(name), theta))
        if out is None:
            continue
        rows = list(csv.DictReader(out.open(encoding="utf-8")))
        last = rows[-1]
        ok = sum(r["b2_match"] == "OK" for r in rows)
        seg = lambda c: sum(int(r[c]) for r in rows)
        ms = lambda c: sum(int(r[c]) for r in rows)
        print(f"  {cell}: INC high={last['inc_high']} | B1 found={last['b1_found']} "
              f"recall={float(last['b1_recall']):.3f} | B2 match {ok}/{len(rows)}, "
              f"segments B2/INC={seg('b2_seg') / max(1, seg('inc_seg')):.3f}, "
              f"time B2/INC={ms('b2_ms') / max(1, ms('inc_ms')):.3f}", flush=True)
        if ok != len(rows):
            print(f"  {cell}: B2 MISMATCH at {len(rows) - ok} snapshots", file=sys.stderr)
    run.finish()


if __name__ == "__main__":
    main()
