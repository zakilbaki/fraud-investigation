# Frozen model and final evaluation specification

This specification records the decision made before final scoring. The selected candidate is `cat_slow200`, following the [candidate comparison](ML_TUNE_H_SELECTION.md).

## Fixed configuration

```python
iterations = 200
learning_rate = 0.05
depth = 6
loss_function = "Logloss"
thread_count = 4
random_seed = 42
verbose = False
allow_writing_files = False
task_type = "CPU"
cat_features = ["type"]
```

No additional weighting, calibration, early stopping, feature, or candidate is introduced at this stage. The fitted artifact's versions and hash are recorded in the [manifest](results/ml_final_manifest.json).

## Fixed representation

| Ordered input | Construction |
| --- | --- |
| `type` | CatBoost categorical feature |
| `amount` | Raw float32 amount |
| `oldbalanceOrg` | Raw float32 sender initial balance |
| `hour_sin` | Sine encoding of `(step - 1) % 24` |
| `hour_cos` | Cosine encoding of the same simulated hour |
| `part_solde` | Amount / initial balance; NaN for zero balance; not clipped |
| `nb_entrees_anterieures` | Float32 recipient count from strictly earlier steps |

`step` and `nameDest` support feature construction but are not raw predictors. Labels, post-transaction balances, and other raw identifiers are excluded. Learned preprocessing is fitted on training data only.

## Chronology

| Steps | Role |
| --- | --- |
| 1–360 | Fit the final pipeline |
| 361–432 | Choose one global F1-maximizing threshold |
| 433–504 | Previously used for selection; no final refitting |
| 505–743 | Evaluate once after freezing model and threshold |

Threshold selection considers distinct scores, keeps tied scores together, and chooses the highest numerical threshold if maxima tie. The model and threshold are saved, reloaded, and verified before test scoring.

## History at prediction time

Recipient counters are initialized with steps 1–504 without labels. At step `t`, all transactions use counters derived only from steps `< t`. Predict the whole step, then update counters with all its transactions. An unseen recipient receives zero.

Test labels are loaded separately for metrics. They never construct history, features, or model predictions.

## Predeclared diagnostics

Report counts, prevalence, and metrics by transaction type; zero amount and the intervals `(0, 100000)`, `[100000, 10^5.5)`, `[10^5.5, 1000000)`, `[1000000, 10^6.5)`, and `[10^6.5, +inf)`; and periods 505–672, 673–720, and 721–743.

Precision is undefined when no alerts exist. The final period contains only frauds, so it cannot independently support ROC-AUC, false-positive rate, or two-class separation claims. Diagnostics do not select another model or threshold.

## Prior exposure

The amount/balance ratio carries a strong PaySim signature. Walk-forward training periods overlap, and validation periods supported multiple choices. Future test labels were examined during exploratory analysis. This prior exposure is part of the interpretation of the final experiment.
