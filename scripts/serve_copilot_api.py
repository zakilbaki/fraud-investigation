"""Serve authenticated lookup and frozen scoring on loopback for an HTTPS tunnel."""

import argparse
from pathlib import Path

import uvicorn

from fraud_investigation.copilot_api import create_copilot_app
from fraud_investigation.scoring_service import ScoringPaths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/app/fraud.sqlite"))
    parser.add_argument("--model", type=Path, default=ScoringPaths().model)
    parser.add_argument("--manifest", type=Path, default=ScoringPaths().manifest)
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    try:
        app = create_copilot_app(args.database, model_path=args.model, manifest_path=args.manifest)
    except RuntimeError as exc:
        parser.error(str(exc))
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
