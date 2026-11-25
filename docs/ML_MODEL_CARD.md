# PaySim CatBoost model card

## Task

Rank synthetic PaySim transactions for investigation and produce an alert decision at a frozen threshold. The score is not presented as a calibrated real-world probability.

## Feature contract

The seven ordered model inputs are `type`, `amount`, `oldbalanceOrg`, `hour_sin`, `hour_cos`, `part_solde`, and `nb_entrees_anterieures`.

Simulated hour is `(step - 1) % 24`. The amount/balance ratio is missing when the initial balance is zero and is not capped at one. Recipient history counts transactions at strictly earlier steps. An unseen recipient has a zero count. Every transaction in a step is predicted before that step updates the history.

Raw identifiers, labels, and post-transaction balances are excluded from model inputs. The [manifest](results/ml_final_manifest.json) records input order, model identity, and dependency versions.

## Fitting and threshold

CatBoost CPU: 200 iterations, learning rate 0.05, depth 6, and random seed 42. Training uses steps 1–360. One F1-maximizing threshold, **0.312317992385**, is selected on steps 361–432. Equal scores are grouped; ties between optimal thresholds select the highest threshold. Steps 433–504 are not used to refit the final model or threshold.

The pipeline is serialized, reloaded, and checked before final evaluation.

## Recorded final test

| Quantity | Value |
| --- | ---: |
| Steps | 505–743 |
| Transactions | 298,584 |
| Frauds | 2,592 |
| Alerts | 2,219 |
| True positives / false positives | 2,190 / 29 |
| False negatives / true negatives | 402 / 295,963 |
| Precision | 0.9869 |
| Recall | 0.8449 |
| F1 | 0.9104 |

See the [final report](ML_FINAL_REPORT.md) for denominators and subgroup diagnostics.

## Interpretation

PaySim is synthetic. Amount/balance relationships and late-period composition can reflect simulator-specific signatures. Simulated hours do not identify a known civil calendar. Development folds were reused for model selection, and the future test labels had been examined during exploratory analysis.

The final segment contains only frauds. Real-time availability and quality of balances and account histories were not established by this experiment. These results therefore describe the recorded simulator test and do not establish real-world fraud-detection performance.
