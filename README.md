# Fraud Investigation

Prototype local d'enquête sur les transactions synthétiques PaySim. Les fondations et les règles de données sont dans [docs/PROJECT.md](docs/PROJECT.md). Les mesures du CSV téléchargé sont dans [docs/DATA_AUDIT.md](docs/DATA_AUDIT.md).

## Environnement vérifié

Sur ce Mac, Python 3.11 était disponible et `uv` a été installé gratuitement dans `.tools/`, sans `sudo`. Depuis la racine du projet :

```sh
python3.11 -m pip install --target .tools uv
UV_CACHE_DIR=.cache/uv UV_PYTHON_DOWNLOADS=never .tools/bin/uv sync --locked --python /opt/homebrew/bin/python3.11
UV_CACHE_DIR=.cache/uv .tools/bin/uv run --locked python -c 'import fraud_investigation, polars as pl; print(fraud_investigation.__name__, pl.__version__)'
```

`uv.lock` fixe les versions résolues. Les dossiers `.tools/`, `.cache/uv/` et `.venv/` sont locaux et exclus de Git. Le chemin de Python ci-dessus est celui vérifié sur ce Mac ; sur une autre machine, le remplacer par son interpréteur Python 3.11.

## Récupérer et auditer PaySim

Ces commandes ont été exécutées avec succès le 16 octobre 2026. Le téléchargement provient de l'API du [jeu PaySim publié sur Kaggle](https://www.kaggle.com/datasets/ealaxi/paysim1). Aucun compte ni jeton Kaggle n'a été nécessaire lors de cette exécution.

```sh
mkdir -p data/raw
curl -fL --retry 2 --max-time 900 -o data/raw/paysim1.zip https://www.kaggle.com/api/v1/datasets/download/ealaxi/paysim1
unzip -t data/raw/paysim1.zip
unzip -n data/raw/paysim1.zip -d data/raw/
shasum -a 256 data/raw/PS_20174392719_1491204439457_log.csv
UV_CACHE_DIR=.cache/uv .tools/bin/uv run --locked python scripts/audit_paysim.py data/raw/PS_20174392719_1491204439457_log.csv --output data/audit.json
```

Le script ne modifie pas le CSV. Il relève les colonnes et leurs types, les valeurs manquantes, les effectifs par `step` et par type, les labels et les valeurs numériques suspectes. Le rapport JSON détaillé reste local dans `data/`, exclu de Git. Les labels sont lus uniquement pour cet audit hors ligne. Aucun outil d'enquête, schéma SQLite, import en base ou modèle ML n'est encore implémenté.
