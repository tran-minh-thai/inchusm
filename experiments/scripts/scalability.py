"""Scalability: IncHUSM alone (cli.Baselines --skip b1,b2) on the synthetic stream
(T=30, seed 42) with n vertices per snapshot and theta = 800 * n / 1500, so the threshold
grows with the stream as in the S configuration (n=1500, theta=800).

Cells: scale_N1500, scale_N3000, scale_N6000, scale_N12000, scale_N24000, scale_N48000.
The log ends with a MEM line (retained heap after GC; peak RSS where /proc is available)
and a TOTAL line (cumulative IncHUSM time).

Run (no external dataset needed):
  python experiments/scripts/scalability.py
  python experiments/scripts/scalability.py --n 1500            # smoke test, under a minute
Output: results/scalability/<UTC time>_<commit>/scale_N*.csv|log + manifest.json
"""

from __future__ import annotations

import argparse
import re

import run_record
import stream_inputs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", nargs="+", type=int, choices=stream_inputs.SYNTH_SIZES,
                    default=list(stream_inputs.SYNTH_SIZES))
    run_record.common_args(ap)
    a = ap.parse_args()
    run = run_record.Run("scalability", a)
    for n in a.n:
        theta = 800 * n // 1500
        cell = f"scale_N{n}"
        out = run.run_cell(cell, run_record.baselines_args(run.stream(f"synth_N{n}"), theta, skip="b1,b2"))
        if out is None:
            continue
        log = out.with_suffix(".log").read_text(encoding="utf-8")
        total = re.search(r"TOTAL inc=(\d+)ms", log)
        mem = re.search(r"retainedHeapAfterGC=(\d+)MB", log)
        print(f"  n={n} theta={theta}: inc total={int(total.group(1)) / 1000:.1f}s, "
              f"retained heap={mem.group(1)} MB", flush=True)
    run.finish()


if __name__ == "__main__":
    main()
