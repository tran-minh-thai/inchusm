"""Shared runner for the alternative-strategy, scalability and discretization scripts.

Each invocation writes into its own folder results/<scenario>/<UTC time>_<commit>/ :
  <cell>.csv, <cell>.log   one pair per run cell (stream x threshold x method)
  manifest.json            commit, tree state, Java runtime and flags, machine, timeout,
                           jar checksum, input checksums, and the exact command of each cell
Running the same command with --out-dir <existing folder> continues it: cells whose log
already ends with the TOTAL line are skipped.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

import stream_inputs

EXP = stream_inputs.EXP
ROOT = stream_inputs.ROOT
JAR = ROOT / "inchusm-miner" / "target" / "inchusm-miner-0.1.0-SNAPSHOT.jar"


def common_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--java", default="java", help="java executable (default: java on PATH)")
    ap.add_argument("--xmx", default="16g", help="JVM max heap (default 16g)")
    ap.add_argument("--timeout-min", type=float, default=None, help="per-cell limit (default none)")
    ap.add_argument("--out-dir", default=None, help="continue an existing run folder")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="run from a working tree with uncommitted changes (recorded in the manifest)")


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True).stdout.strip()


def tree_state() -> tuple[str, str]:
    commit = _git("rev-parse", "HEAD") or "unknown"
    # untracked files count too: an uncommitted source file still ends up in the jar
    changed = [l for l in _git("status", "--porcelain").splitlines() if l]
    return commit, "clean" if not changed else f"MODIFIED ({len(changed)} files)"


def jar_is_current() -> bool:
    """The jar must be newer than every miner source file, or it may not match the commit."""
    srcs = (ROOT / "inchusm-miner").rglob("*.java")
    newest = max((s.stat().st_mtime for s in srcs), default=0.0)
    return JAR.stat().st_mtime >= newest


def java_runtime(java: str) -> dict:
    proc = subprocess.run([java, "-XshowSettings:properties", "-version"],
                          capture_output=True, text=True)
    props = {}
    for line in proc.stderr.splitlines():
        if "=" in line:
            k, v = line.strip().split("=", 1)
            props[k.strip()] = v.strip()
    return {
        "executable": java,
        "java.runtime.version": props.get("java.runtime.version", "?"),
        "java.vendor": props.get("java.vendor", "?"),
        "java.vm.name": props.get("java.vm.name", "?"),
        "version_banner": [l for l in proc.stderr.splitlines() if "version" in l and "=" not in l],
    }


def machine() -> dict:
    info = {"hostname": platform.node(), "os": platform.platform(), "arch": platform.machine(),
            "python": platform.python_version(), "logical_cpus": os.cpu_count()}
    try:
        if sys.platform == "win32":
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_Processor).Name; "
                 "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"],
                capture_output=True, text=True, timeout=60).stdout.split("\n")
            info["cpu"], info["ram_bytes"] = out[0].strip(), int(out[1].strip())
        elif sys.platform == "darwin":
            sysctl = lambda k: subprocess.run(["sysctl", "-n", k], capture_output=True, text=True).stdout.strip()
            info["cpu"], info["ram_bytes"] = sysctl("machdep.cpu.brand_string"), int(sysctl("hw.memsize"))
        else:
            cpu = [l for l in Path("/proc/cpuinfo").read_text().splitlines() if l.startswith("model name")]
            mem = [l for l in Path("/proc/meminfo").read_text().splitlines() if l.startswith("MemTotal")]
            info["cpu"] = cpu[0].split(":", 1)[1].strip() if cpu else "?"
            info["ram_bytes"] = int(mem[0].split()[1]) * 1024 if mem else None
    except Exception as e:  # recorded, never fatal
        info["probe_error"] = repr(e)
    return info


def rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


class Run:
    """One run folder plus its manifest; cells are executed with run_cell()."""

    def __init__(self, scenario: str, args: argparse.Namespace):
        if not JAR.exists():
            sys.exit(f"missing {JAR}; build it with: mvn -f inchusm-miner/pom.xml package")
        if not jar_is_current():
            sys.exit(f"{JAR.name} is older than the miner sources; rebuild: mvn -f inchusm-miner/pom.xml package")
        commit, tree = tree_state()
        if tree != "clean" and not args.allow_dirty:
            sys.exit(f"working tree is {tree}; commit first, or pass --allow-dirty "
                     f"(the manifest then records the tree as modified)")
        self.args = args
        if args.out_dir:
            self.dir = Path(args.out_dir).resolve()
        else:
            stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            self.dir = EXP / "results" / scenario / f"{stamp}_{commit[:7]}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.dir / "manifest.json"
        if self.manifest_path.exists():
            self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            if self.manifest.get("commit") != commit:
                sys.exit(f"{self.dir} was started at commit {self.manifest.get('commit')}, "
                         f"current commit is {commit}; start a new folder instead")
        else:
            self.manifest = {
                "scenario": scenario,
                "commit": commit,
                "tree": tree,
                "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "java": java_runtime(args.java),
                "jvm_flags": [f"-Xmx{args.xmx}"],
                "timeout_min_per_cell": args.timeout_min,
                "machine": machine(),
                "jar": {"path": rel(JAR), "sha256": stream_inputs.sha256(JAR)},
                "inputs": {},
                "cells": {},
            }
        self.manifest.setdefault("sessions", []).append(
            {"argv": sys.argv, "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
             "tree": tree, "java.runtime.version": java_runtime(args.java)["java.runtime.version"]})
        self._save()
        print(f"[run] {scenario} -> {rel(self.dir)}  (commit {commit[:7]}, tree {tree})", flush=True)

    def _save(self) -> None:
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.manifest, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.manifest_path)

    def stream(self, name: str) -> Path:
        d = stream_inputs.ensure(name)
        if name not in self.manifest["inputs"]:
            self.manifest["inputs"][name] = {
                p.name: stream_inputs.sha256(p) for p in sorted(d.iterdir()) if p.is_file()}
            self._save()
        return d

    def run_cell(self, cell: str, java_args: list[str]) -> Path | None:
        """Run one Java command; stdout+stderr go to <cell>.log, the CSV to <cell>.csv."""
        csv_path, log_path = self.dir / f"{cell}.csv", self.dir / f"{cell}.log"
        if log_path.exists() and "TOTAL" in log_path.read_text(encoding="utf-8", errors="replace"):
            print(f"[run] {cell}: already complete, skipped", flush=True)
            return csv_path
        cmd = [self.args.java, f"-Xmx{self.args.xmx}", *java_args, "--out", str(csv_path)]
        shown = [c if not Path(c).is_absolute() else rel(Path(c)) for c in cmd]
        print(f"[run] {cell}: {' '.join(shown)}", flush=True)
        t0 = dt.datetime.now(dt.timezone.utc)
        status = "ok"
        try:
            with log_path.open("w", encoding="utf-8") as log:
                timeout = None if self.args.timeout_min is None else self.args.timeout_min * 60
                rc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=timeout).returncode
            if rc != 0:
                status = f"exit {rc}"
        except subprocess.TimeoutExpired:
            status = "timeout"
        self.manifest["cells"][cell] = {
            "command": shown, "status": status,
            "started_utc": t0.isoformat(timespec="seconds"),
            "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        self._save()
        tail = log_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-2:]
        print("\n".join(f"    {l}" for l in tail), flush=True)
        if status != "ok":
            print(f"[run] {cell}: {status} (see {rel(log_path)})", flush=True)
            return None
        return csv_path

    def finish(self) -> None:
        self.manifest["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        self._save()
        failed = [c for c, v in self.manifest["cells"].items() if v["status"] != "ok"]
        print(f"[run] done: {len(self.manifest['cells']) - len(failed)} cells ok, {len(failed)} failed "
              f"{failed if failed else ''} -> {rel(self.dir)}", flush=True)
        if failed:
            sys.exit(1)


def baselines_args(stream_dir: Path, theta: float, skip: str | None = None) -> list[str]:
    args = ["-cp", str(JAR), "edu.huflit.inchusm.cli.Baselines",
            "--snapshot-dir", str(stream_dir), "--util", str(stream_dir / "utilities.tsv"),
            "--minvalue", f"{theta:g}", "--max-edges", "5"]
    return args + (["--skip", skip] if skip else [])
