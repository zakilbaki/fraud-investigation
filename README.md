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

Cette commande réexécute les cellules Python de [notebooks/eda_paysim.ipynb](notebooks/eda_paysim.ipynb) dans un espace de variables neuf. Elle vérifie l'empreinte du CSV et les contrôles du notebook, puis régénère les figures SVG dans [docs/figures/](docs/figures/). Le [rapport EDA](docs/EDA.md) présente les tableaux, les interprétations et les figures PNG publiées pour la lecture ; les PNG sont des exports des SVG et ne sont pas régénérés par cette commande. Cette commande EDA n'entraîne aucun modèle. Les labels sont lus uniquement pour cette analyse hors ligne.

## Reproduire la première comparaison ML

Après `uv sync --locked` et l'installation du CSV audité, exécuter depuis la racine du dépôt :

```sh
uv run --locked python -m unittest tests.test_ml_benchmark -v
uv run --locked python scripts/run_ml_benchmark_all.py
uv run --locked python scripts/report_ml_benchmark.py
```

Chaque processus lit seulement les steps 1 à 504. Pour chaque modèle et fenêtre, il apprend sur la première portion du train, choisit le seuil sur sa réserve interne et évalue ensuite la validation extérieure. Le test 505 à 743 reste réservé. Les résultats intermédiaires et journaux sont dans `data/ml_benchmark/`, hors de Git ; une interruption se reprend en relançant la même commande. L'orchestrateur arrête une fenêtre dépassant 30 minutes ou dont la mémoire résidente dépasse 75 % de la RAM physique, puis conserve l'incident dans son état local. Le [rapport de comparaison](docs/ML_BENCHMARK.md), le [protocole](docs/ML_PROTOCOL.md) et les figures dans `docs/figures/` décrivent les résultats publiés. Les onze candidats obligatoires du protocole sont exécutés par défaut ; les candidats supplémentaires faisables peuvent être demandés avec `--models mlp knn`. Le SVM à noyau a été interrompu lors du contrôle de coût sans score comparable.

## Relire les premiers diagnostics ML

Après la comparaison, cette commande audite les agrégats publiés et régénère la figure des cinq modèles commentés dans [docs/ML_DIAGNOSTICS.md](docs/ML_DIAGNOSTICS.md), sans réentraîner ni lire le test final :

```sh
uv run --locked python scripts/diagnose_ml_results.py
```

Les prédictions transaction par transaction n'ont pas été conservées pendant le lot 4.2. Les étapes suivantes de diagnostic devront rejouer uniquement les configurations figées nécessaires et garder ces prédictions hors de Git.

## Reproduire l'expérience A du lot 4.3

Après le benchmark de référence et avec le même CSV audité, exécuter depuis la racine du dépôt :

```sh
uv run --locked python -m unittest tests.test_ml_feature_hour tests.test_ml_benchmark -v
uv run --locked python scripts/run_ml_feature_hour_all.py
uv run --locked python scripts/report_ml_feature_hour.py
```

L'expérience ajoute seulement l'heure simulée codée en sinus et cosinus aux cinq modèles présélectionnés. Les 25 ajustements sont enregistrés dans `data/ml_feature_hour/`, exclu de Git, et une interruption reprend les fenêtres déjà terminées. Le script de rapport compare ces résultats aux 25 lignes correspondantes de `docs/results/ml_benchmark.json` et produit [le rapport détaillé](docs/ML_FEATURE_HOUR.md), [les résultats agrégés](docs/results/ml_feature_hour.json) et deux figures. Chaque seuil est choisi dans la réserve interne de sa fenêtre. Le test 505 à 743 n'est pas lu. Les expériences B et C ne font pas partie de cette commande.

## Reproduire l'expérience B du lot 4.3

Après le benchmark de référence et avec le même CSV audité, exécuter depuis la racine du dépôt :

```sh
uv run --locked python -m unittest tests.test_ml_feature_balance_org tests.test_ml_benchmark -v
uv run --locked python scripts/run_ml_feature_balance_org_all.py
uv run --locked python scripts/report_ml_feature_balance_org.py
```

B ajoute uniquement `oldbalanceOrg` à la référence `type + amount`. La commande exécute les **quatre modèles encore retenus** sur les cinq fenêtres : XGBoost, CatBoost, Extra Trees et Random Forest. Trois fenêtres KNN achevées avant son retrait restent conservées dans le [rapport B](docs/ML_FEATURE_BALANCE_ORG.md), sans moyenne sur cinq fenêtres. Les résultats intermédiaires et journaux restent dans `data/ml_feature_balance_org/`, hors de Git ; la commande reprend les fenêtres terminées. Les [agrégats structurés](docs/results/ml_feature_balance_org.json) et trois figures comparent les quatre modèles complets à la référence, sans réexécuter celle-ci. Le test final et l'expérience C ne sont pas lancés par ces commandes. La présence du solde dans PaySim ne prouve pas qu'il serait effectivement disponible avant une transaction réelle.

## Reproduire l'expérience C du lot 4.3

Après le benchmark de référence et avec le même CSV audité, exécuter depuis la racine du dépôt :

```sh
uv run --locked python -m unittest tests.test_ml_feature_balance_dest tests.test_ml_benchmark -v
uv run --locked python scripts/run_ml_feature_balance_dest_all.py
uv run --locked python scripts/report_ml_feature_balance_dest.py
```

C ajoute uniquement `oldbalanceDest` à `type + amount` pour XGBoost, CatBoost, Extra Trees et Random Forest, sur les cinq fenêtres. Les résultats intermédiaires et journaux restent dans `data/ml_feature_balance_dest/`, hors de Git. La commande reprend les fenêtres déjà terminées. Le [rapport C](docs/ML_FEATURE_BALANCE_DEST.md), les [agrégats](docs/results/ml_feature_balance_dest.json) et trois figures comparent C à la référence vérifiée, sans relancer les autres expériences ni le test final. Les quatre ajouts référence, A, B et C restent séparés.

## Reproduire l'expérience D du lot 4.3

Après l'installation et le téléchargement du même CSV audité, exécuter depuis la racine du dépôt. Les résultats agrégés déjà publiés de la référence, de A, B et C servent à la comparaison ; il n'est pas nécessaire de les réentraîner :

```sh
uv run --locked python -m unittest tests.test_ml_feature_balance_org_hour tests.test_ml_feature_hour tests.test_ml_feature_balance_org tests.test_ml_benchmark -v
uv run --locked python scripts/run_ml_feature_balance_org_hour_all.py
uv run --locked python scripts/report_ml_feature_balance_org_hour.py
```

D conserve les colonnes de B, `type + amount + oldbalanceOrg`, et ajoute seulement l'heure cyclique de A pour XGBoost, CatBoost, Extra Trees et Random Forest. Chaque seuil est choisi dans la réserve interne de sa fenêtre. Les résultats intermédiaires et journaux restent dans `data/ml_feature_balance_org_hour/`, hors de Git ; la commande reprend les fenêtres terminées. Le [rapport D](docs/ML_FEATURE_BALANCE_ORG_HOUR.md), les [agrégats](docs/results/ml_feature_balance_org_hour.json) et trois figures comparent D aux vingt résultats B publiés, sans réentraîner B ni consulter le test final.

## Reproduire l'expérience E du lot 4.4

Avec le CSV audité et les agrégats D déjà publiés, lancer depuis la racine du dépôt :

```sh
uv run --locked python -m unittest tests.test_ml_feature_balance_share -v
uv run --locked python scripts/run_ml_feature_balance_share_all.py
uv run --locked python scripts/report_ml_feature_balance_share.py
```

E ajoute seulement `part_solde` à D pour XGBoost et CatBoost. Le ratio vaut `amount / oldbalanceOrg` quand le solde est positif et reste manquant sinon. Les fichiers intermédiaires sont dans `data/ml_feature_balance_share/`, hors de Git ; la commande reprend les fenêtres terminées. Les [résultats E](docs/ML_FEATURE_BALANCE_SHARE.md) comparent les cinq validations de chaque modèle aux agrégats D, sans consulter le test final. F et G ne sont pas lancées par ces commandes.

## Mesurer la couverture de l'historique F avant entraînement

Avec le même CSV audité, depuis la racine du dépôt :

```sh
uv run --locked python -m unittest tests.test_ml_sender_history -v
uv run --locked python scripts/inspect_ml_sender_history.py
```

Le script lit seulement `step` et `nameOrig` jusqu'au step 504. Il produit des [agrégats de couverture](docs/results/ml_sender_history_coverage.json) sans identifiants ni labels ; le [rapport F préalable](docs/ML_SENDER_HISTORY_COVERAGE.md) explique leur lecture. Ces commandes n'entraînent aucun modèle F et ne lancent pas G.

## Mesurer la couverture de l'historique G avant entraînement

Avec le même CSV audité, depuis la racine du dépôt :

```sh
uv run --locked python -m unittest tests.test_ml_recipient_history -v
uv run --locked python scripts/inspect_ml_recipient_history.py
```

Le script lit seulement `step` et `nameDest` jusqu'au step 504 pour produire les [agrégats G](docs/results/ml_recipient_history_coverage.json), la [figure](docs/figures/ml_recipient_history_distribution.png) et le [rapport de couverture](docs/ML_RECIPIENT_HISTORY_COVERAGE.md). Il ne lit aucun label, ne calcule aucun score et n'entraîne aucun modèle. F est mis de côté, avec son diagnostic conservé.

## Portabilité et historique de vérification

La procédure vise une installation reproductible sur toute machine où les prérequis sont disponibles. Les exécutions effectivement vérifiées ont eu lieu sur macOS Apple Silicon avec Python 3.11.15, `uv` 0.13.1 et Polars 1.44.2. Linux et Windows n'ont pas été testés ; leur compatibilité reste à vérifier. Le téléchargement public, l'audit et l'import complet ont réussi le 16 octobre 2026 sur cette machine. Les effectifs mesurés et les contrôles de cohérence sont conservés dans les documents liés en tête de page. Le notebook EDA a été réexécuté intégralement lors de la clôture du lot 4.0. Pour le lot 4.2, `uv run --locked` a réussi avec un cache temporaire explicitement accessible dans l'environnement restreint ; la commande avec le cache par défaut n'a pas été revérifiée.
