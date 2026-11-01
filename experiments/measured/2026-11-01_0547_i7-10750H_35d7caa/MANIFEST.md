# Measured run: i7-10750H, 2026-11-01

Results of `alt_strategies`, `scalability` and `discretization` as produced on the
measurement machine. Files are byte-for-byte copies (Windows line endings kept).
`SHA256SUMS` lists every file of this folder except this manifest.

## Code

| Item | Value |
|---|---|
| Commit holding the code | `35d7caa` (this repository) |
| Sources the jar was built from | commit `278f77588bfa91e3bad33ff6637de8fe02cfed79` plus `inchusm-miner/src/main/java/edu/huflit/inchusm/cli/Baselines.java`, sha256 `da50eb950e57298fedf30383171dbfa015b1538ab1f63758b560a741827f2135`; all other 19 source files identical to `278f775` |
| Difference between those sources and `35d7caa` | the class comment of `Baselines.java` only. Compiled with `javac -g:none --release 17`, all 32 classes are byte-identical; a control edit (sigma + 1 in `Baselines`) changes exactly 1 class |
| Jar | `inchusm-revision.jar`, built outside the repository with `javac --release 17` (manifest: `Created-By: 21.0.12.1`), sha256 `b650fb3cabcd00707be807349cd4d8ccfdfc1ab79422a9913e16852b54d16636`, 32 classes |
| Jar against its sources | recompiling the listed sources gives 31 of 32 classes byte-identical; `cli.Main` differs only in constant-pool layout, with identical bytecode instructions (`javap -c`) |
| Working tree | not a git checkout; the jar and its sources were copied to the machine together |

## Runtime and machine

| Item | Value |
|---|---|
| Java | Microsoft OpenJDK 21.0.12.1 (build 21.0.12.1+1-LTS), from `machine.txt` |
| JVM flags | `-Xmx16g` |
| Time limit | none |
| CPU | Intel Core i7-10750H @ 2.60 GHz, from `machine.txt` |
| RAM | 63.75 GiB reported, from `machine.txt` |
| OS | Windows 11, stated by the operator (not recorded by `run_i7.bat`) |
| Run window | 2026-11-01 05:47:08 to 07:20:01 local time, from `machine.txt` |
| Commands | `run_i7.bat`, executed with no argument (all three parts, in order alt, scale, k) |

## Inputs

269 snapshot and utility files (`.lg`, `.tsv`) in 10 streams; their sha256 values are
`experiments/streams_sha256.txt`. Rebuilding them from the original datasets with
`python experiments/scripts/stream_inputs.py` reproduces all 269 checksums.

| Cell | Stream | theta | Command |
|---|---|---|---|
| `alt_elliptic` | `elliptic` | 500 | `cli.Baselines --max-edges 5` |
| `alt_amlworld` | `aml_k4` | 2000 | same |
| `alt_S` | `synth_N1500` | 800 | same |
| `alt_L` | `synth_N3000` | 1600 | same |
| `scale_N<n>` | `synth_N<n>`, n = 1500 .. 48000 | 800 * n / 1500 | `cli.Baselines --max-edges 5 --skip b1,b2` |
| `aml_k4`, `aml_k2`, `aml_k8` | `aml_k<k>` | 2000, 1200, 3600 | `stream --measure utility --bound ceu --mer 1 --max-edges 5 --compare-static` |

The scripts `alt_strategies.py`, `scalability.py` and `discretization.py` issue the same
commands; their own output goes to `experiments/results/`, never into this folder.
