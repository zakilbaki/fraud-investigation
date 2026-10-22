# Fraud Investigation

An AI-assisted fraud-investigation prototype built on **6.3 million synthetic financial transactions**, combining Microsoft Copilot Studio, machine learning and a Python backend.

## What it does

The investigation workflow starts with a transaction ID:

1. Retrieve the transaction and its source provenance.
2. Calculate a suspicion score using the trained CatBoost model.
3. Examine the sender and recipient histories.
4. Save an investigation report linked to recorded tool results, with missing information and errors kept visible.

Copilot Studio provides a conversational entry point through authenticated transaction lookup. The backend supplies scoring, bounded history searches, case management and evidence-linked reports. A suspicion score supports investigation; it does not confirm fraud.

## Results

**13 models compared** using five temporal walk-forward validation windows, followed by feature engineering and CatBoost tuning.

Final temporal test: **298,584 transactions**, including **2,592 frauds**.

| Precision | Recall | F1 | Frauds detected | False alerts |
| --- | --- | --- | --- | --- |
| **98.69%** | **84.49%** | **0.9104** | **2,190** | **29** |

Results describe synthetic PaySim data. [Evaluation and limitations](docs/ML_FINAL_REPORT.md).

## Stack

Python · Polars · CatBoost · FastAPI · Pydantic · SQLite · Microsoft Copilot Studio

[Data analysis](docs/EDA.md) · [Backend tools](docs/API.md) · [Reproduce the project](docs/REPRODUCING.md)
