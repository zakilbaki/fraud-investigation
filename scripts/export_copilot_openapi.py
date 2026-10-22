"""Créer le fichier Swagger v2 à importer après obtention d'une URL HTTPS réelle."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit


TEMPLATE = Path(__file__).resolve().parents[1] / "docs/copilot/transaction_lookup.swagger.template.json"
DEFAULT_OUTPUT = Path("data/copilot/transaction_lookup.swagger.json")


def export(base_url: str, output: Path) -> Path:
    parsed = urlsplit(base_url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Port HTTPS invalide") from exc
    if (parsed.scheme != "https" or not parsed.hostname or "." not in parsed.hostname
            or parsed.hostname.endswith(".invalid") or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment
            or any(character.isspace() for character in base_url)):
        raise ValueError("Fournir une URL HTTPS réelle à la racine, sans chemin ni paramètres")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Port HTTPS invalide")
    specification = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    specification["host"] = parsed.netloc
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(specification, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="URL HTTPS publique réelle du tunnel")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    try:
        print(export(arguments.base_url, arguments.output))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
