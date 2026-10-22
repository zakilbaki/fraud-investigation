# Fraud Investigation

An AI engineering portfolio prototype combining **fraud detection, a Python investigation backend, and a Microsoft Copilot Studio agent** on synthetic PaySim transactions.

The project covers the full path from reproducible data ingestion and temporal model evaluation to authenticated API access, recorded tool executions, and evidence-linked investigation reports.

## Results at a glance

| Item | Result |
| --- | --- |
| Dataset | 6,362,620 synthetic transactions; 8,213 labeled frauds |
| Model selection | 13 candidates evaluated on five temporal validation windows |
| Selected pipeline | CatBoost, 200 iterations, learning rate 0.05, depth 6 |
| Temporal test | 298,584 transactions, including 2,592 frauds |
| Test precision / recall / F1 | **98.69% / 84.49% / 0.9104** |
| Test confusion matrix | TP 2,190; FP 29; FN 402; TN 295,963 |

These are results on **synthetic data**, not validated banking production performance. The analyst inspected the future test labels during EDA; test scores were excluded from subsequent model tuning and threshold selection. Balance-related features can exploit simulator-specific patterns. See the [model card](docs/ML_MODEL_CARD.md) and [final report](docs/ML_FINAL_REPORT.md).

## Architecture and current capabilities

```text
Copilot Studio agent
    -> authenticated REST tool -> HTTPS tunnel for demonstrations
        -> restricted transaction-lookup gateway -> application SQLite database

Local investigation API
    -> frozen CatBoost scoring pipeline
    -> bounded, strictly historical account queries
    -> investigation cases and recorded tool executions
    -> versioned JSON / Markdown reports with evidence references

Offline evaluation labels -> separate SQLite file, unavailable to agent tools
```

**Implemented:** application/label separation, source provenance, idempotent import, temporal ML validation, a frozen model and threshold, local scoring and investigation APIs, persisted evidence, and deterministic reports.

**Manually tested in Copilot Studio:** authenticated lookup of a known transaction through the HTTPS gateway, and a custom user-facing response for an unknown transaction. The other backend tools are implemented but are not yet connected to the agent. Multi-agent delegation is a planned next step.

The project targets a zero-additional-cost learning setup. Copilot Studio requires an eligible organizational account and appropriate permissions or trial access; a personal Microsoft account is insufficient. The Python backend can be used independently of Copilot Studio.

## Documentation

- [Project scope and implementation history](docs/PROJECT.md)
- [Data audit](docs/DATA_AUDIT.md), [database design](docs/DATABASE.md), [EDA](docs/EDA.md)
- [ML protocol](docs/ML_PROTOCOL.md), [initial benchmark](docs/ML_BENCHMARK.md), [feature experiments](docs/ML_FEATURE_RATIO_RECIPIENT_HISTORY.md)
- [Model selection](docs/ML_TUNE_H_SELECTION.md), [model card](docs/ML_MODEL_CARD.md), [final test](docs/ML_FINAL_REPORT.md)
- [API contracts and investigation workflow](docs/API.md), [Copilot Studio REST setup](docs/COPILOT_REST.md)

## Prerequisites

- Git, Python 3.11, and [uv](https://docs.astral.sh/uv/getting-started/installation/). The package accepts Python 3.11–3.13; the verified environment uses Python 3.11 on macOS Apple Silicon. Linux and Windows remain untested.
- A shell with `curl` for the download commands, Internet access, and several GB of free space for the CSV, databases, model artifacts, and temporary files.
- No developer-specific account is needed for the local backend. Kaggle's public download availability can change; if necessary, download PaySim manually from the [dataset page](https://www.kaggle.com/datasets/ealaxi/paysim1).

Run the commands below from the repository root. Raw data, databases, labels, model artifacts, environments, credentials, and individual predictions are excluded from Git.

## Installation

The committed `uv.lock` pins resolved dependencies. The local `.venv/` environment is ignored by Git. Install uv using its [official instructions](https://docs.astral.sh/uv/getting-started/installation/) if needed.

```sh
git clone https://github.com/zakilbaki/fraud-investigation.git
cd fraud-investigation
uv sync --locked --python 3.11
uv run --locked python -c 'import fraud_investigation, polars as pl; print(fraud_investigation.__name__, pl.__version__)'
```

## Download PaySim

The audited CSV is **493,534,783 bytes** with SHA-256 `16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b`. Verify both before importing. If the distributed source changes, audit and document that version rather than attributing the old fingerprint to it. Keep the original CSV unchanged under `data/raw/`.

```sh
mkdir -p data/raw
curl -fL --retry 2 --max-time 900 -o data/raw/paysim1.zip https://www.kaggle.com/api/v1/datasets/download/ealaxi/paysim1
uv run --locked python -m zipfile -t data/raw/paysim1.zip
uv run --locked python -m zipfile -e data/raw/paysim1.zip data/raw/
uv run --locked python -c 'import hashlib, pathlib; p = pathlib.Path("data/raw/PS_20174392719_1491204439457_log.csv"); h = hashlib.file_digest(p.open("rb"), "sha256"); print(p.stat().st_size, h.hexdigest())'
```

## Validate and import the data

The offline audit may read labels. The importer writes transactions to `data/app/fraud.sqlite` and labels to the separate `data/evaluation/labels.sqlite`. Reimporting the same audited source returns `already_imported` without duplicates or deleting investigations. Agent tools must open only the application database.

```sh
uv run --locked python scripts/audit_paysim.py data/raw/PS_20174392719_1491204439457_log.csv --output data/audit.json
uv run --locked python -m unittest discover -s tests -v
uv run --locked python scripts/import_paysim.py data/raw/PS_20174392719_1491204439457_log.csv --database data/app/fraud.sqlite --labels data/evaluation/labels.sqlite --expected-sha256 16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b
```

## Query from Python

`get_transaction` returns `None` for an unknown ID. Account history includes only steps strictly below `before_step`. Its deterministic output order is not evidence of chronology within a step. The scripts accept explicit paths and can run from outside the repository.

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

## Reproduce exploratory analysis

The runner executes notebook code cells in a fresh namespace, checks the source fingerprint and assertions, and regenerates SVGs under `docs/figures/`. The [EDA report](docs/EDA.md) embeds PNG exports for GitHub; the runner does not regenerate those PNGs. This is offline analysis with labels, not model training.

```sh
uv run --locked python scripts/run_eda_notebook.py
```

## Reproduce the initial ML benchmark

Training and model selection use only steps 1–504. Each window has separate fitting, threshold-selection, and outer-validation portions. Intermediate results and logs are local under `data/ml_benchmark/`; completed windows are resumed. Runs are bounded by the documented time and memory budgets. Additional feasible candidates can be requested with `--models mlp knn`. The kernel SVM was stopped during feasibility assessment without a comparable score. See the [benchmark](docs/ML_BENCHMARK.md).

```sh
uv run --locked python -m unittest tests.test_ml_benchmark -v
uv run --locked python scripts/run_ml_benchmark_all.py
uv run --locked python scripts/report_ml_benchmark.py
```

## Inspect the initial ML diagnostics

This audits the published aggregates and regenerates the figure in [ML_DIAGNOSTICS.md](docs/ML_DIAGNOSTICS.md), without training or a new test evaluation. Individual benchmark predictions were not retained; later diagnostics may replay only frozen configurations and must keep individual predictions outside Git.

```sh
uv run --locked python scripts/diagnose_ml_results.py
```

## Experiment A: simulated hour

Adds sine/cosine hour encoding to the original `type + amount` reference. The five shortlisted models each use five windows. Thresholds are selected internally; the final test is excluded. The [report](docs/ML_FEATURE_HOUR.md) and aggregates compare against the existing reference, without retraining it.

```sh
uv run --locked python -m unittest tests.test_ml_feature_hour tests.test_ml_benchmark -v
uv run --locked python scripts/run_ml_feature_hour_all.py
uv run --locked python scripts/report_ml_feature_hour.py
```

## Experiment B: sender starting balance

Adds only `oldbalanceOrg` to `type + amount`. XGBoost, CatBoost, Extra Trees, and Random Forest complete five windows. Three historical KNN windows remain separately documented without a five-window average. KNN was retired for prediction/storage cost. See the [report](docs/ML_FEATURE_BALANCE_ORG.md). Balance availability in this simulator does not establish real-time availability in an actual application.

```sh
uv run --locked python -m unittest tests.test_ml_feature_balance_org tests.test_ml_benchmark -v
uv run --locked python scripts/run_ml_feature_balance_org_all.py
uv run --locked python scripts/report_ml_feature_balance_org.py
```

## Experiment C: recipient starting balance

Adds only `oldbalanceDest` to `type + amount` for the same four models. Results resume under `data/ml_feature_balance_dest/` and are compared to the verified reference. See the [report](docs/ML_FEATURE_BALANCE_DEST.md). Recorded zero balances can represent unavailable merchant information; they are not automatically empty accounts.

```sh
uv run --locked python -m unittest tests.test_ml_feature_balance_dest tests.test_ml_benchmark -v
uv run --locked python scripts/run_ml_feature_balance_dest_all.py
uv run --locked python scripts/report_ml_feature_balance_dest.py
```

## Experiment D: sender balance and simulated hour

Combines B with the cyclic hour from A. The [report](docs/ML_FEATURE_BALANCE_ORG_HOUR.md) compares four models against B without retraining B. Intermediate results remain local and the final test is excluded.

```sh
uv run --locked python -m unittest tests.test_ml_feature_balance_org_hour tests.test_ml_feature_hour tests.test_ml_feature_balance_org tests.test_ml_benchmark -v
uv run --locked python scripts/run_ml_feature_balance_org_hour_all.py
uv run --locked python scripts/report_ml_feature_balance_org_hour.py
```

## Experiment E: balance share

Adds only `part_solde` to D for XGBoost and CatBoost: `amount / oldbalanceOrg` for a positive starting balance, otherwise missing. Ratios above one are not clipped. See the [report](docs/ML_FEATURE_BALANCE_SHARE.md). The ratio makes an existing relationship explicit and can exploit simulator artifacts.

```sh
uv run --locked python -m unittest tests.test_ml_feature_balance_share -v
uv run --locked python scripts/run_ml_feature_balance_share_all.py
uv run --locked python scripts/report_ml_feature_balance_share.py
```

## Sender history coverage F

Reads only `step` and `nameOrig` through step 504, without labels. The [coverage report](docs/ML_SENDER_HISTORY_COVERAGE.md) explains why F was set aside without training: only 0.1391% of transactions have a previous sender occurrence at an earlier step.

```sh
uv run --locked python -m unittest tests.test_ml_sender_history -v
uv run --locked python scripts/inspect_ml_sender_history.py
```

## Recipient history coverage G

Reads only `step` and `nameDest` through step 504, without labels or model scores. It produces the [coverage report](docs/ML_RECIPIENT_HISTORY_COVERAGE.md), figure, and aggregates. Coverage is 56.5140%, which supports feasibility but does not establish predictive usefulness.

```sh
uv run --locked python -m unittest tests.test_ml_recipient_history -v
uv run --locked python scripts/inspect_ml_recipient_history.py
```

## Experiment G: recipient history

Adds only the count of earlier receptions by the same `nameDest` to D. The counter excludes the current step and future steps. The [report](docs/ML_FEATURE_RECIPIENT_HISTORY.md) reuses D as reference. E’s ratio is not included.

```sh
uv run --locked python -m unittest tests.test_ml_recipient_history tests.test_ml_feature_recipient_history -v
uv run --locked python scripts/run_ml_feature_recipient_history_all.py
uv run --locked python scripts/report_ml_feature_recipient_history.py
```

## Experiment H: balance share and recipient history

Combines E with G’s strictly historical recipient counter for XGBoost and CatBoost. The [report](docs/ML_FEATURE_RATIO_RECIPIENT_HISTORY.md) compares H with E and G, reusing their published results. Intermediate files are under `data/ml_feature_ratio_recipient_history/`, outside Git.

```sh
uv run --locked python -m unittest tests.test_ml_feature_ratio_recipient_history tests.test_ml_feature_balance_share tests.test_ml_recipient_history -v
uv run --locked python scripts/run_ml_feature_ratio_recipient_history_all.py
uv run --locked python scripts/report_ml_feature_ratio_recipient_history.py
```

## Limited hyperparameter tuning of H

Three predefined XGBoost variants were evaluated first, followed by three CatBoost variants. See the [XGBoost report](docs/ML_TUNE_H_XGBOOST.md), [CatBoost report](docs/ML_TUNE_H_CATBOOST.md), and [selection record](docs/ML_TUNE_H_SELECTION.md). The selected configuration is `cat_slow200`. These commands reproduce development experiments; they must not be used to adapt the frozen pipeline to the final test.

```sh
uv run --locked python -m unittest discover -s tests
uv run --locked python scripts/run_ml_tune_h_xgboost_all.py
uv run --locked python scripts/report_ml_tune_h_xgboost.py
uv run --locked python scripts/run_ml_tune_h_catboost_all.py
uv run --locked python scripts/report_ml_tune_h_catboost.py
uv run --locked python scripts/report_ml_tune_h_selection.py
```

## Frozen model and final evaluation

The [freeze decision](docs/ML_FINAL_FREEZE.md) and [manifest](docs/results/ml_final_manifest.json) were published before final scoring. The binary model and individual predictions stay in `data/ml_final_catboost/`. Freezing/evaluation refuse to overwrite artifacts; reproduce independently in a clean workspace. The CASH_OUT threshold follow-up is explicitly exploratory and does not replace the final policy. Its commands are `python scripts/run_ml_cashout_threshold.py reserve`, `python scripts/run_ml_cashout_threshold.py test`, and `python scripts/report_ml_cashout_threshold.py`.

```sh
python -m unittest discover -s tests
python scripts/freeze_ml_final.py
# Publish and verify the manifest before any evaluation.
python scripts/evaluate_ml_final.py
python scripts/report_ml_final.py
```

## Local scoring and investigation API

The common entry point exposes lookup, bounded histories, scoring, cases, recorded checks, and versioned reports. The standalone lookup server remains available without ML. A missing model keeps fact lookup available and makes scoring unavailable. For the protected Copilot gateway and Swagger export, follow [COPILOT_REST.md](docs/COPILOT_REST.md). The common API listens on `127.0.0.1:8000`; `POST /score` expects a 32-character hexadecimal `transaction_id`. The model is neither downloaded nor retrained automatically. The explicit reconstruction procedure is `uv run --locked python scripts/freeze_ml_final.py`; it checks the published manifest and refuses to overwrite local artifacts. Raw data and model artifacts are not distributed with this repository.

```sh
uv run --locked python scripts/serve_api.py \
  --database data/app/fraud.sqlite \
  --model data/ml_final_catboost/pipeline.joblib \
  --manifest docs/results/ml_final_manifest.json
```

## Verification status

The project has been exercised on macOS Apple Silicon with Python 3.11. Local `uv sync --locked` and `uv run --locked` checks succeeded for the API setup using an accessible temporary cache. Historical ML reports retain their original verification limits: those individual runs used the local Python environment, and the generic uv commands were not rechecked in every experiment. Linux and Windows have not been verified. Model reconstruction is documented but was not rerun for the API delivery.

Copilot Studio connectivity was manually demonstrated using a temporary HTTPS tunnel and an API-key-protected, read-only lookup gateway. This is a development demonstration, not a production deployment or a guarantee of real-time performance. Stop the tunnel after testing, keep the key outside Git, and regenerate the Swagger export when the tunnel hostname changes.
