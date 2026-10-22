"""Démarrer la surface REST protégée sur 127.0.0.1 pour un futur tunnel HTTPS."""

import argparse
from pathlib import Path

import uvicorn

from fraud_investigation.copilot_api import create_copilot_app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/app/fraud.sqlite"))
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    try:
        app = create_copilot_app(args.database)
    except RuntimeError as exc:
        parser.error(str(exc))
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
