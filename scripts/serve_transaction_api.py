"""Démarrer l'API locale de consultation sur 127.0.0.1."""

import argparse
from pathlib import Path

import uvicorn

from fraud_investigation.transaction_api import create_transaction_app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/app/fraud.sqlite"))
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_transaction_app(args.database), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
