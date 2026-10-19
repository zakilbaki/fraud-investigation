"""Orchestrer les 10 ajustements de D sous les mêmes plafonds que B."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

from fraud_investigation.ml_feature_balance_share import MODELS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=Path("data/raw/PS_20174392719_1491204439457_log.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/ml_feature_balance_share"))
    parser.add_argument("--max-seconds", type=int, default=1800)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    status_path = args.output / "status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    memory_limit = int(psutil.virtual_memory().total * 0.75)
    print(f"Limite RSS processus : {memory_limit / 2**30:.1f} Gio", flush=True)
    for name in MODELS:
        for fold in range(1, 6):
            key = f"{name}_fold_{fold}"
            if (args.output / f"{key}.json").exists():
                continue
            command = [sys.executable, "scripts/run_ml_feature_balance_share.py", "--model", name,
                       "--fold", str(fold), "--csv", str(args.csv), "--output", str(args.output)]
            print(f"Début {key}", flush=True)
            environment = os.environ.copy()
            environment.update({key: "4" for key in (
                "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS")})
            start = time.monotonic()
            peak = 0
            reason = None
            with (args.output / f"{key}.log").open("w") as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=environment)
                child = psutil.Process(process.pid)
                while process.poll() is None:
                    try:
                        peak = max(peak, child.memory_info().rss)
                        if peak > memory_limit:
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
                raise SystemExit(f"Échec de {key} : {reason or 'voir journal local'}")


if __name__ == "__main__":
    main()
