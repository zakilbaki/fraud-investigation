"""Démarrer l'API locale sur 127.0.0.1."""

import argparse
from pathlib import Path

import uvicorn

from fraud_investigation.api import create_app
from fraud_investigation.scoring_service import ScoringPaths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ScoringPaths.database)
    parser.add_argument("--model", type=Path, default=ScoringPaths.model)
    parser.add_argument("--manifest", type=Path, default=ScoringPaths.manifest)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    app = create_app(ScoringPaths(args.database, args.model, args.manifest))
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
