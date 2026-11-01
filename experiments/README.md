# experiments/ — IncHUSM stream experiments (Python)

The Python side drives the Java miner (`inchusm-miner/`) over snapshot streams
and checks correctness against a static re-run. Build the jar first:

```bash
mvn -f ../inchusm-miner/pom.xml package     # 15 tests, produces the jar
python -m venv ~/.venvs/inchusm && pip install -r ../requirements.txt
```

`experiments/src` is a source root; scripts add it to `sys.path` automatically.
Java and Python communicate through `.lg` / `.jsonl` files (no JNI), via
`src/inchusm/miner_bridge.py`.

## Scripts (result CSVs go to `results/`)

```bash
# E2 — IncHUSM vs static re-run on Elliptic-49 (49/49 exact match, 83 patterns):
python scripts/e2_inchusm_stream.py
python scripts/e2_inchusm_stream.py --bound eu  --no-compare    # upper-bound ablation
python scripts/e2_inchusm_stream.py --bound ivu --no-compare
python scripts/e2_inchusm_stream.py --measure support --min-value 200 --no-compare

# E2b — Citeseer trend check (static baseline is a faithful HUSM re-implementation):
python scripts/e2b_citeseer_trend.py

# E2c — controlled synthetic streams:
python scripts/e2c_synthetic_stream.py --tag S
python scripts/e2c_synthetic_stream.py --tag L --n 3000 --min-value 1600

# E2d — real AML stream (AMLworld HI-Small, one snapshot per day; takes hours):
python scripts/e2d_amlworld_stream.py

# Verify the deterministic values of every experiment above (machine-independent):
python scripts/check_results.py

# Repeated-run timing (mean +/- std; run on the declared measurement machine):
python scripts/e2_repeat_std.py --runs 5
python scripts/e2_ablation_repeat_std.py --runs 5
python scripts/e2d_repeat_std.py --runs 3

# Figures:
python scripts/make_figures_paper2.py
```

`run_paper2.bat` / `run_extra_std.bat` at the repository root wrap these for
Windows. Timing must be measured on one idle machine; cloud sync off.

## Outputs

Each stream step writes one CSV to `results/`, one row per snapshot:

| Column | Meaning |
|---|---|
| `snapshot` | snapshot index (1-based) |
| `vertices`, `edges` | vertex / edge count of this snapshot |
| `tracked` | pattern-states held in the store |
| `high_total` | high-utility patterns through this snapshot (cumulative) |
| `newly_high` | patterns promoted to high at this snapshot |
| `seg_last` | segment evaluations for the arriving snapshot alone |
| `inc_ms` | incremental update time for this snapshot (ms) |
| `static_ms` | static re-mine time on the accumulated union (ms; `-1` without `--compare-static`) |
| `static_high` | high count from the static re-run (`-1` without `--compare-static`) |
| `match` | `OK` / `MISMATCH` vs the static re-run (blank without `--compare-static`) |

Approximate wall-clock per run: E2 ~10 min, each ablation round ~55 s, E2d several hours.

## Alternative strategies, scalability and discretization

Three scripts, each writing one folder per invocation (`results/<scenario>/<UTC time>_<commit>/`)
with a CSV and a log per cell and a `manifest.json` (commit, working-tree state, Java runtime and
vendor, JVM flags, machine, time limit, jar and input checksums, exact command of every cell).
They refuse to start from a working tree with uncommitted or untracked files (unless
`--allow-dirty`, which the manifest records) or with a jar older than the sources.
Re-running with `--out-dir <folder>` continues an interrupted run and skips completed cells.

```bash
python scripts/stream_inputs.py        # build all 10 input streams once and verify them
python scripts/alt_strategies.py       # 4 cells, ~4 min on an i7-10750H
python scripts/scalability.py          # 6 cells, ~23 min  (--n 1500 for a smoke test)
python scripts/discretization.py       # 3 cells, ~66 min
```

Common options: `--java PATH`, `--xmx 16g` (default), `--timeout-min M` (default: none).

### Input streams (`stream_inputs.py`)

Built into `results/streams/<name>/` and checked file by file against `streams_sha256.txt`
(269 files); the script exits non-zero on any difference.

| Stream | Source | Snapshots | Labels | Construction |
|---|---|---|---|---|
| `elliptic` | `datasets/elliptic1` | 49 | 4 | as E2: f0 quantile buckets fit on steps <= 34 |
| `aml_k2`, `aml_k4`, `aml_k8` | `datasets/amlworld/HI-Small_Trans.csv` | 10 | k | as E2d: days 0..9, amount >= 5000, in-day degree <= 30, account-day amount buckets fit on day 0 |
| `synth_N<n>`, n = 1500 .. 48000 | generator of E2c | 30 | 6 | edge factor 1.5, 30 planted chains, seed 42 |

For AMLworld the qualifying transactions are first copied in file order to
`results/streams/HI-Small_Trans_d10_a5000.csv`. Account ids are assigned at first
appearance, so building straight from the full file yields the same graphs with a different
vertex numbering; the filtered copy reproduces the checksums exactly.

### Parameters

| Script | Cell | Stream | theta | Method |
|---|---|---|---|---|
| `alt_strategies.py` | `alt_elliptic` | `elliptic` | 500 | `cli.Baselines` (INC, B1, B2) |
| | `alt_amlworld` | `aml_k4` | 2000 | |
| | `alt_S` | `synth_N1500` | 800 | |
| | `alt_L` | `synth_N3000` | 1600 | |
| `scalability.py` | `scale_N<n>` | `synth_N<n>` | 800 * n / 1500 | `cli.Baselines --skip b1,b2` |
| `discretization.py` | `aml_k4`, `aml_k2`, `aml_k8` | `aml_k<k>` | round(2000 * (k+1) / 5): 2000, 1200, 3600 | `stream --compare-static` |

Fixed in every cell: utility u(label i) = i + 1, MER = 1, CEU bound, at most 5 edges per pattern.
B2 uses sigma = ceil(theta / u_max).

### `cli.Baselines` columns (alt_*.csv, scale_*.csv)

| Column | Meaning |
|---|---|
| `snapshot` | snapshot index (1-based) |
| `inc_ms`, `inc_high`, `inc_tracked`, `inc_seg` | IncHUSM: update time, high patterns so far, patterns tracked, segment evaluations for this snapshot |
| `b1_ms` | snapshot-local mining: static HUSM time on this snapshot alone |
| `b1_found` | patterns in the union of the per-snapshot results so far |
| `b1_recall` | `b1_found` / `inc_high` (1 when `inc_high` = 0) |
| `b2_ms` | support-filter incremental: update time plus the u >= theta filter |
| `b2_tracked`, `b2_seg` | patterns tracked and segment evaluations of the support-mode store |
| `b2_high` | patterns left after the filter |
| `b2_match` | `OK` when the B2 set equals the IncHUSM set at this snapshot |

Skipped methods (`--skip b1,b2`) report -1 and a blank `b2_match`. The log ends with
`MEM retainedHeapAfterGC=<MB>` (plus the peak resident size where `/proc` exists) and
`TOTAL inc=.. b1=.. b2=..` cumulative times. `aml_k*.csv` uses the `stream` columns above.

### Measured results

`measured/` holds result sets copied from the measurement machine, one folder per run,
named `<local start time>_<machine>_<commit>`, each with a `MANIFEST.md` linking the numbers
to the code commit, the jar, the Java runtime and the input checksums. Folders are never
overwritten; a new run goes into a new folder.

## Package (`src/inchusm/`)

| Module | Role |
|---|---|
| `miner_bridge.py` | export `.lg` snapshot streams + utilities, invoke the jar, parse per-snapshot telemetry |
| `data/amlworld.py` | AMLworld transaction loader (chunked, memory-efficient) |
