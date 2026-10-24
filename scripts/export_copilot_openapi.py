"""Export an English Swagger v2 tool definition for an actual HTTPS endpoint."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit


TEMPLATE = Path(__file__).resolve().parents[1] / "docs/copilot/transaction_lookup.swagger.template.json"
DEFAULT_OUTPUT = Path("data/copilot/transaction_lookup.swagger.json")
SCORING_TEMPLATE = TEMPLATE.with_name("transaction_scoring.swagger.template.json")
SCORING_OUTPUT = Path("data/copilot/transaction_scoring.swagger.json")
HISTORY_TEMPLATE = TEMPLATE.with_name("account_history.swagger.template.json")
HISTORY_OUTPUT = Path("data/copilot/account_history.swagger.json")
CASES_TEMPLATE = TEMPLATE.with_name("investigation_cases.swagger.template.json")
CASES_OUTPUT = Path("data/copilot/investigation_cases.swagger.json")
TOOL_FILES = {
    "lookup": (TEMPLATE, DEFAULT_OUTPUT),
    "scoring": (SCORING_TEMPLATE, SCORING_OUTPUT),
    "history": (HISTORY_TEMPLATE, HISTORY_OUTPUT),
    "cases": (CASES_TEMPLATE, CASES_OUTPUT),
}


def export(base_url: str, output: Path, *, tool: str = "lookup") -> Path:
    if tool not in TOOL_FILES:
        raise ValueError("Tool must be lookup, scoring, history or cases")
    parsed = urlsplit(base_url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid HTTPS port") from exc
    if (parsed.scheme != "https" or not parsed.hostname or "." not in parsed.hostname
            or parsed.hostname.endswith(".invalid") or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment
            or any(character.isspace() for character in base_url)):
        raise ValueError("Provide an actual root HTTPS URL without a path or query parameters")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Invalid HTTPS port")
    template = TOOL_FILES[tool][0]
    specification = json.loads(template.read_text(encoding="utf-8"))
    specification["host"] = parsed.netloc
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(specification, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Actual public HTTPS tunnel URL")
    parser.add_argument("--tool", choices=tuple(TOOL_FILES), default="lookup")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    try:
        output = arguments.output or TOOL_FILES[arguments.tool][1]
        print(export(arguments.base_url, output, tool=arguments.tool))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
