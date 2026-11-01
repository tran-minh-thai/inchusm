"""Build the named snapshot streams used by the alternative-strategy, scalability and
discretization runs, and check them against the recorded input checksums.

Streams (written to results/streams/<name>/snap_XX.lg + utilities.tsv):
  elliptic        Elliptic, 49 time steps, f0 quantile labels, k=4 (as in E2)
  aml_k2/4/8      AMLworld HI-Small, 10 daily snapshots, account-day amount buckets, k=2/4/8
  synth_N<n>      synthetic stream, T=30, n vertices per snapshot, seed 42 (as in E2c)

AMLworld: the transactions of days 0..9 with amount >= 5000 are first copied, in file order,
to results/streams/HI-Small_Trans_d10_a5000.csv, and the daily snapshots are built from that
file. Account ids are assigned in order of first appearance, so building from the full file
gives the same graphs with different vertex numbering; the filtered copy reproduces the
measured .lg files byte for byte.

Every built file is compared with experiments/streams_sha256.txt; the script exits non-zero
on any mismatch (pass --no-verify to skip).

Run (from the repository root or anywhere):
  python experiments/scripts/stream_inputs.py                     # all streams
  python experiments/scripts/stream_inputs.py --only synth_N1500  # one stream
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPTS = Path(__file__).resolve().parent
EXP = SCRIPTS.parent
ROOT = EXP.parent
sys.path.insert(0, str(EXP / "src"))
sys.path.insert(0, str(SCRIPTS))

STREAMS_DIR = EXP / "results" / "streams"
CHECKSUMS = EXP / "streams_sha256.txt"
AML_RAW = ROOT / "datasets" / "amlworld" / "HI-Small_Trans.csv"
AML_DAYS, AML_MIN_AMOUNT, AML_DEG_CAP = 10, 5000.0, 30
SYNTH_T, SYNTH_EDGE_FACTOR, SYNTH_K, SYNTH_PLANT, SYNTH_SEED = 30, 1.5, 6, 30, 42
SYNTH_SIZES = (1500, 3000, 6000, 12000, 24000, 48000)

ALL_STREAMS = ["elliptic", "aml_k2", "aml_k4", "aml_k8", *[f"synth_N{n}" for n in SYNTH_SIZES]]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def expected_checksums() -> dict[str, str]:
    """streams_sha256.txt rows: '<sha256>  ./<stream>/<file>' -> {'<stream>/<file>': sha}."""
    out = {}
    for line in CHECKSUMS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            out[name.strip().removeprefix("./")] = digest
    return out


def aml_filtered_copy() -> Path:
    """Copy the HI-Small rows of days 0..9 with amount >= 5000 (file order kept)."""
    out = STREAMS_DIR / f"HI-Small_Trans_d{AML_DAYS}_a{int(AML_MIN_AMOUNT)}.csv"
    if out.exists():
        return out
    if not AML_RAW.exists():
        sys.exit(f"missing {AML_RAW}; see docs/reproduce/paper2.md section 1c")
    print(f"[streams] filtering {AML_RAW.name} -> {out.name}", flush=True)
    with AML_RAW.open(newline="", encoding="utf-8") as f:
        lines = f.readlines()
    fmt = "%Y/%m/%d %H:%M"
    t0 = min(dt.datetime.strptime(line[:16], fmt) for line in lines[1:])
    kept = [lines[0]]
    for line in lines[1:]:
        row = next(csv.reader([line]))
        day = (dt.datetime.strptime(row[0], fmt) - t0).total_seconds() // 86400
        if day < AML_DAYS and float(row[7]) >= AML_MIN_AMOUNT:  # column 7 = Amount Paid
            kept.append(line)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        f.writelines(kept)
    tmp.replace(out)
    print(f"[streams] kept {len(kept) - 1} of {len(lines) - 1} transactions", flush=True)
    return out


def build(name: str):
    """Return (snapshots, n_labels) for a named stream."""
    if name == "elliptic":
        import e2_inchusm_stream as e2
        return e2.build_snapshots(4, 49)
    if name.startswith("aml_k"):
        import e2d_amlworld_stream as e2d
        from inchusm.data import amlworld
        filtered = aml_filtered_copy()
        e2d.load_transactions = lambda _path, *a, **kw: amlworld.load_transactions(filtered, *a, **kw)
        return e2d.build_daily_snapshots(AML_DAYS, AML_MIN_AMOUNT, AML_DEG_CAP, int(name[5:]))
    if name.startswith("synth_N"):
        from e2c_synthetic_stream import gen_stream
        snaps = gen_stream(SYNTH_T, int(name[7:]), SYNTH_EDGE_FACTOR, SYNTH_K, SYNTH_PLANT, SYNTH_SEED)
        return snaps, SYNTH_K
    raise ValueError(f"unknown stream {name!r}; choose from {ALL_STREAMS}")


def ensure(name: str, verify: bool = True, rebuild: bool = False) -> Path:
    """Build stream `name` unless already present; return its directory.

    With verify=True, every file is checked against streams_sha256.txt (exit on mismatch).
    """
    from inchusm.miner_bridge import export_snapshot_stream, export_utilities

    out = STREAMS_DIR / name
    if rebuild or not (out / "utilities.tsv").exists():
        snaps, n_labels = build(name)
        for old in out.glob("snap_*.lg"):
            old.unlink()
        export_snapshot_stream(snaps, out)
        export_utilities({i: float(i + 1) for i in range(n_labels)}, out / "utilities.tsv")
        print(f"[streams] {name}: {len(snaps)} snapshots, {n_labels} labels", flush=True)
    if verify:
        want = {k: v for k, v in expected_checksums().items() if k.split("/")[0] == name}
        have = {f"{name}/{p.name}": sha256(p) for p in sorted(out.iterdir()) if p.is_file()}
        bad = sorted(k for k in want if have.get(k) != want[k])
        extra = sorted(set(have) - set(want))
        if not want:
            sys.exit(f"[streams] {name}: no recorded checksums in {CHECKSUMS.name}")
        if bad or extra:
            sys.exit(f"[streams] {name}: {len(bad)} of {len(want)} files differ from the recorded "
                     f"inputs {bad[:3]}; {len(extra)} unexpected files {extra[:3]}")
        print(f"[streams] {name}: {len(want)}/{len(want)} files match {CHECKSUMS.name}", flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", choices=ALL_STREAMS, default=ALL_STREAMS)
    ap.add_argument("--rebuild", action="store_true", help="rebuild even if the stream exists")
    ap.add_argument("--no-verify", action="store_true")
    a = ap.parse_args()
    for name in a.only:
        ensure(name, verify=not a.no_verify, rebuild=a.rebuild)


if __name__ == "__main__":
    main()
