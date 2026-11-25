# Fraud Investigation system guide

Fraud Investigation connects a frozen temporal fraud model with transaction lookup, account history, evidence persistence, and Microsoft Copilot Studio orchestration.

## System boundaries

| Component | Responsibility |
| --- | --- |
| Coordinator | Route an analyst request to the appropriate specialist and combine returned evidence |
| Fraud Investigator | Call configured flows for facts, scores, histories, and authorized case operations |
| Investigation Policy Agent | Retrieve cited investigation procedures |
| Authenticated gateway | Expose bounded operations under shared-key authentication |
| Python services | Validate requests, construct deterministic features, score transactions, and maintain case records |
| SQLite | Store application transactions and investigation records; evaluation labels remain separate |

The [architecture](assets/architecture.svg) shows these boundaries. Policy guidance does not substitute for transaction evidence. Scores support investigation; they do not authorize payment blocking.

## Transaction and model evidence

The application retrieves transactions by stable identifiers and reconstructs earlier account activity. The final model uses seven predictors and counts recipient transactions at strictly earlier steps. Transactions in the same step never contribute to one another's recipient history.

The frozen CatBoost configuration and threshold are recorded in the [manifest](results/ml_final_manifest.json). Its final synthetic PaySim test contains 298,584 transactions and 2,592 frauds. At threshold 0.312318, it produces 2,190 true positives, 29 false positives, 402 false negatives, and 295,963 true negatives.

[Model card](ML_MODEL_CARD.md) · [Final report](ML_FINAL_REPORT.md) · [Freeze specification](ML_FINAL_FREEZE.md)

## Investigation records

Direct lookups and scores do not automatically create stored evidence. Explicit case operations create cases, execute and record checks, and create versioned reports. Each write requires a stable retry key. A retry returns the existing result rather than duplicating it.

Saved reports reference recorded checks and preserve their evidence snapshots. New report versions do not overwrite old ones. Case search returns bounded matches and their latest-report references; it does not select or create a case implicitly.

[API contracts](API.md) · [Case operations](COPILOT_CASES.md) · [Storage](DATABASE.md)

## Copilot integration

The Coordinator configuration connects the Investigator and Policy Agent. The repository documents role boundaries, context transfer, English instructions, and a 20-case evaluation suite. Published configuration and evaluation scenarios are reproducible documentation assets, not a universal reliability or pass-rate claim.

Owner-supplied demonstrations cover transaction and account lookup, scoring, saved investigations, retry behavior, and procedural citations. Configured cloud flows and local service contracts must be distinguished: a local passing test does not independently validate a tenant's live configuration.

[Coordinator](coordinator/README.md) · [Policy corpus](policy_agent/README.md) · [Gateway](COPILOT_REST.md) · [Flow configuration](COPILOT_FLOWS.md)

## Experimental record

The model-development record separates chronological training, threshold selection, candidate selection, and final evaluation. Feature studies test balance, cyclic time, amount/balance ratio, and recipient history. The final test was scored after the model and threshold were frozen; its labels had already been examined during exploratory analysis.

The later CASH_OUT threshold comparison is exploratory and does not replace the frozen global policy.

[Data audit](DATA_AUDIT.md) · [Exploratory analysis](EDA.md) · [Protocol](ML_PROTOCOL.md) · [Benchmark](ML_BENCHMARK.md) · [Candidate selection](ML_TUNE_H_SELECTION.md) · [Exploratory CASH_OUT comparison](ML_CASHOUT_THRESHOLD_EXPLORATORY.md)

## Reproduction

Use [REPRODUCING.md](REPRODUCING.md) for dependency setup, data preparation, model reconstruction, and service commands. Raw PaySim data, SQLite databases, individual predictions, and serialized model files are not included in Git.

Model loading validates artifact identity, feature order, threshold policy, and provenance. Transaction services can remain available when scoring cannot load a compatible model.
