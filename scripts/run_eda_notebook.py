"""Exécuter les cellules Python du notebook EDA avec l'environnement du projet."""

import json
import os
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    notebook = root / "notebooks" / "eda_paysim.ipynb"
    os.chdir(root)
    cells = json.loads(notebook.read_text(encoding="utf-8"))["cells"]
    namespace: dict[str, object] = {"__name__": "__main__"}
    for cell in cells:
        if cell["cell_type"] == "code":
            source = "".join(cell["source"])
            exec(compile(source, str(notebook), "exec"), namespace)


if __name__ == "__main__":
    main()
