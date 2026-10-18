"""Orchestrer les cinq fenêtres, avec reprise et limites de ressources."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import psutil

from fraud_investigation.ml_benchmark import MODELS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=Path("data/raw/PS_20174392719_1491204439457_log.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/ml_benchmark"))
    parser.add_argument("--models", nargs="+", choices=MODELS, default=MODELS[:-1])
    parser.add_argument("--folds", nargs="+", type=int, choices=range(1, 6), default=range(1, 6))
    parser.add_argument("--max-seconds", type=int, default=1800)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    status_path = args.output / "status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    memory_limit = int(psutil.virtual_memory().total * 0.75)
    print(f"Limite RSS processus: {memory_limit / 2**30:.1f} Gio", flush=True)
    for name in args.models:
        if any(status.get(f"{name}_fold_{fold}", {}).get("state") == "failed" for fold in range(1, 6)):
            print(f"{name}: arrêt antérieur, cinq fenêtres non comparables", flush=True)
            continue
        for fold in args.folds:
            key = f"{name}_fold_{fold}"
            if (args.output / f"{key}.json").exists():
                continue
            command = [sys.executable, "scripts/run_ml_benchmark.py", "--model", name,
                       "--fold", str(fold), "--csv", str(args.csv), "--output", str(args.output)]
            print(f"Début {key}", flush=True)
            start = time.monotonic()
            with (args.output / f"{key}.log").open("w") as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                child = psutil.Process(process.pid)
                peak = 0
                reason = None
                while process.poll() is None:
                    try:
                        rss = child.memory_info().rss
                        peak = max(peak, rss)
                        if rss > memory_limit:
                            reason = "memory_limit"
                        elif time.monotonic() - start > args.max_seconds:
                            reason = "time_limit"
                    except psutil.NoSuchProcess:
                        break
                    if reason:
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        break
                    time.sleep(1)
                code = process.wait()
            status[key] = {
                "state": "ok" if code == 0 and reason is None else "failed",
                "exit_code": code, "reason": reason,
                "elapsed_seconds": round(time.monotonic() - start, 2),
                "peak_rss_bytes": peak,
            }
            status_path.write_text(json.dumps(status, indent=2) + "\n")
            print(f"Fin {key}: {status[key]}; journal {args.output / f'{key}.log'}", flush=True)
            if status[key]["state"] == "failed":
                break


if __name__ == "__main__":
    main()
