# Fraud Investigation

Prototype local d'enquête sur les transactions synthétiques PaySim. Le [cadrage](docs/PROJECT.md), l'[audit du CSV](docs/DATA_AUDIT.md) et le [schéma SQLite](docs/DATABASE.md) décrivent les choix et les limites.

## Prérequis

- Git, Python 3.11 et [`uv`](https://docs.astral.sh/uv/getting-started/installation/) disponibles dans le terminal. Le projet accepte Python 3.11 à 3.13 selon `pyproject.toml` ; seule la version 3.11 a été vérifiée.
- Pour les commandes de téléchargement ci-dessous : un terminal compatible avec `sh` et `curl`. Une connexion à Internet et plusieurs Go d'espace libre sont nécessaires pour le CSV, les deux bases et les fichiers temporaires d'import.
- Aucun compte du développeur ni service payant n'est requis. L'accès public au téléchargement Kaggle peut évoluer ; si la commande échoue, récupérer le jeu depuis sa [page officielle](https://www.kaggle.com/datasets/ealaxi/paysim1), puis placer son archive dans `data/raw/paysim1.zip`. Ne jamais enregistrer d'identifiants ou de jetons dans le dépôt.

Les commandes suivantes partent de la racine du dépôt et utilisent des chemins relatifs à celle-ci.

## Installation

```sh
git clone https://github.com/zakilbaki/fraud-investigation.git
cd fraud-investigation
uv sync --locked --python 3.11
uv run --locked python -c 'import fraud_investigation, polars as pl; print(fraud_investigation.__name__, pl.__version__)'
```

`uv.lock` est versionné pour figer la résolution des dépendances. L'environnement `.venv/` reste local et exclu de Git. Si `uv` manque, utiliser la [procédure officielle adaptée à sa plateforme](https://docs.astral.sh/uv/getting-started/installation/) avant `uv sync`.

## Récupération de PaySim

```sh
mkdir -p data/raw
curl -fL --retry 2 --max-time 900 -o data/raw/paysim1.zip https://www.kaggle.com/api/v1/datasets/download/ealaxi/paysim1
uv run --locked python -m zipfile -t data/raw/paysim1.zip
uv run --locked python -m zipfile -e data/raw/paysim1.zip data/raw/
uv run --locked python -c 'import hashlib, pathlib; p = pathlib.Path("data/raw/PS_20174392719_1491204439457_log.csv"); h = hashlib.file_digest(p.open("rb"), "sha256"); print(p.stat().st_size, h.hexdigest())'
```

Pour le fichier audité le 16 octobre 2026, la taille attendue est `493534783` octets et le SHA-256 est `16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b`. Comparer ces valeurs avant l'import. Si Kaggle distribue une autre version, ne pas lui attribuer cette empreinte : effectuer un nouvel audit et documenter sa provenance. Le CSV brut est conservé sans modification dans `data/raw/`, exclu de Git.

## Vérifications et génération des bases

```sh
uv run --locked python scripts/audit_paysim.py data/raw/PS_20174392719_1491204439457_log.csv --output data/audit.json
uv run --locked python -m unittest discover -s tests -v
uv run --locked python scripts/import_paysim.py data/raw/PS_20174392719_1491204439457_log.csv --database data/app/fraud.sqlite --labels data/evaluation/labels.sqlite --expected-sha256 16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b
```

L'audit lit les labels hors ligne. L'import crée la base applicative `data/app/fraud.sqlite` sans labels et une base distincte `data/evaluation/labels.sqlite`, réservée à l'évaluation. Réexécuter l'import du même CSV doit retourner `already_imported` sans créer de doublons. Les futurs outils d'enquête devront aussi limiter explicitement l'accès à la seule base applicative. Les fichiers générés dans `data/` ne sont pas publiés.

## Consultation depuis Python

Depuis la racine du dépôt, après génération des bases :

```sh
uv run --locked python - <<'PY'
from fraud_investigation.database import get_account_transactions, get_transaction, open_readonly

with open_readonly("data/app/fraud.sqlite") as database:
    transaction = get_transaction(database, "d83a6871a919fd644c774f3e65fbe41b")
    print(transaction)
    if transaction is not None:
        history = get_account_transactions(
            database, transaction["name_dest"], before_step=transaction["step"], limit=3
        )
        print(history)
PY
```

La transaction d'exemple correspond au CSV et à l'empreinte ci-dessus. `get_transaction` renvoie `None` pour un identifiant inconnu. L'historique ne contient que des `step` strictement antérieurs à la borne et son ordre de restitution est déterministe ; l'ordre des lignes au sein d'un même `step` n'est pas une chronologie réelle. Les scripts acceptent des chemins de fichiers en arguments et peuvent être invoqués depuis un autre dossier avec des chemins explicites.

## Reproduire l'analyse exploratoire

Après l'installation et le téléchargement du CSV ci-dessus, lancer depuis la racine du dépôt :

```sh
uv run --locked python scripts/run_eda_notebook.py
```

Cette commande réexécute les cellules Python de [notebooks/eda_paysim.ipynb](notebooks/eda_paysim.ipynb) dans un espace de variables neuf. Elle vérifie l'empreinte du CSV et les contrôles du notebook, puis régénère les figures SVG dans [docs/figures/](docs/figures/). Le [rapport EDA](docs/EDA.md) présente les tableaux, les interprétations et les figures PNG publiées pour la lecture ; les PNG sont des exports des SVG et ne sont pas régénérés par cette commande. Aucun modèle n'est entraîné. Le [protocole ML proposé](docs/ML_PROTOCOL.md) décrit les étapes à implémenter après le choix du critère de seuil. Les labels sont lus uniquement pour cette analyse hors ligne.

## Portabilité et historique de vérification

La procédure vise une installation reproductible sur toute machine où les prérequis sont disponibles. Les exécutions effectivement vérifiées ont eu lieu sur macOS Apple Silicon avec Python 3.11.15, `uv` 0.13.1 et Polars 1.44.2. Linux et Windows n'ont pas été testés ; leur compatibilité reste à vérifier. Le téléchargement public, l'audit et l'import complet ont réussi le 16 octobre 2026 sur cette machine. Les effectifs mesurés et les contrôles de cohérence sont conservés dans les documents liés en tête de page. Le notebook EDA a été réexécuté intégralement lors de la clôture du lot 4.0.
