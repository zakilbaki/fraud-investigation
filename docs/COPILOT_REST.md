# Copilot Studio REST tools

## Gateway and tools

`scripts/serve_copilot_api.py` exposes exactly two authenticated operations on loopback:

| Operation | Purpose | Copilot tool |
| --- | --- | --- |
| `GET /transactions/{transaction_id}` | Read ten allowed pre-transaction/provenance fields | `getTransactionById` |
| `POST /score` | Score an existing transaction using frozen CatBoost | `scoreTransactionById` |

The gateway does not expose cases, histories, reports, arbitrary SQL, `/docs`, `/openapi.json` or a public health route. Scoring calculates its own exact prior-recipient count internally; this does not expose an account-history search tool.

Lookup has been manually demonstrated in Copilot Studio. The scoring operation and its English specification are prepared and verified locally; adding it to Copilot Studio remains a manual integration step. The full backend investigation tools are documented in [API.md](API.md).

## Authentication and startup

Both operations require `X-API-Key`. The server compares it with `FRAUD_INVESTIGATION_API_KEY` using a constant-time comparison. A missing, empty or shorter-than-32-character secret prevents startup; an absent/wrong request key returns 401. The secret is not stored in Git or OpenAPI. This shared key does not establish individual user identity.

From the repository root, with the application database and frozen model available:

```sh
read -s "FRAUD_INVESTIGATION_API_KEY?API key: "
export FRAUD_INVESTIGATION_API_KEY
.venv/bin/python scripts/serve_copilot_api.py \
  --database data/app/fraud.sqlite \
  --model data/ml_final_catboost/pipeline.joblib \
  --manifest docs/results/ml_final_manifest.json \
  --port 8768
```

Enter the same secret already configured in the lookup connection. Do not regenerate it just to add scoring. If the variable is already exported in this terminal, omit `read` and `export`. The defaults match these paths. The server always binds to `127.0.0.1`.

When upgrading an already running gateway, stop **only that API process** with Ctrl+C and rerun its command in the same terminal. Keep an existing tunnel running. Model and manifest are loaded and checked once at startup; a missing/incompatible artifact leaves lookup working and scoring returns 503. No model is trained or downloaded automatically.

## Frozen scoring contract

The request contains only `transaction_id`, exactly 32 hexadecimal characters. Features, history and threshold are calculated by Python. Extra request fields, including a caller-supplied threshold, are rejected.

Response fields are `transaction_id`, `suspicion_score`, `threshold`, `alert`, `model_version` and `policy_version`. The global threshold stays **0.3123179923852385** and `alert` is true when `suspicion_score >= threshold`. The CASH_OUT exploratory policy is not applied. Scores are not calibrated fraud probabilities or proof of fraud.

The same saved transformer constructs H's seven features. Prior-recipient counts exclude the current and future steps and have no response-row cap. Only the application database is opened, read-only. Evaluation labels, post-transaction balances and arbitrary file paths are not tool inputs.

Scoring errors are 400 for a malformed ID, 401 for authentication failure, 404 for an absent transaction, 422 for an invalid request or incompatible transaction data, 503 for unavailable/incompatible model/database and 500 for unexpected prediction failure. No substitute score or internal traceback is returned. A failed request must not be described as a low-risk transaction.

This direct scoring route does not create a case or persist a tool-evidence record. Recorded investigation scoring remains a separate operation on the full backend: `POST /cases/{id}/runs` with `operation=score`.

## Local and tunnel checks

In a second terminal with the same key exported:

```sh
curl -i http://127.0.0.1:8768/transactions/d83a6871a919fd644c774f3e65fbe41b
curl -i -H "X-API-Key: $FRAUD_INVESTIGATION_API_KEY" \
  http://127.0.0.1:8768/transactions/d83a6871a919fd644c774f3e65fbe41b
curl -i -X POST http://127.0.0.1:8768/score \
  -H "X-API-Key: $FRAUD_INVESTIGATION_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"transaction_id":"d83a6871a919fd644c774f3e65fbe41b"}'
```

The unauthenticated call returns 401. Authenticated lookup returns 200 for this ID in the audited PaySim import. Scoring returns 200 if the frozen artifacts are valid. These commands do not contain a published individual prediction. Visiting `/` in a browser returns 404 because no root route is provided; browser navigation does not automatically supply the key.

An HTTPS tunnel forwards a public URL to the gateway. The manually demonstrated setup uses:

```sh
cloudflared tunnel --url http://127.0.0.1:8768
```

Keep the computer, API and tunnel active during testing. Target this port only. Check 401 without a key and 200 with the key through the tunnel, using the real public hostname instead of `127.0.0.1:8768`. A cloud service's `localhost` does not refer to this computer. Temporary hostnames and secrets are deliberately not committed. If the tunnel hostname changes, regenerate the export and update affected connections.

## Generate the English import files

The [lookup template](copilot/transaction_lookup.swagger.template.json) is unchanged. The new [scoring template](copilot/transaction_scoring.swagger.template.json) describes only `POST /score`. Each uses Swagger/OpenAPI v2 JSON, a unique operation ID and `apiKey` authentication in the header. Their `.invalid` hosts are deliberate placeholders. **Import generated files, not these templates.**

```sh
.venv/bin/python scripts/export_copilot_openapi.py \
  --tool lookup --base-url "https://ACTUAL-TUNNEL-HOST"
.venv/bin/python scripts/export_copilot_openapi.py \
  --tool scoring --base-url "https://ACTUAL-TUNNEL-HOST"
```

Replace the example hostname with the existing root HTTPS URL. The exporter rejects HTTP, extra paths, URL credentials/query/fragment and `.invalid` hosts. Generated files are ignored by Git:

- `data/copilot/transaction_lookup.swagger.json`
- `data/copilot/transaction_scoring.swagger.json`

Omitting `--tool` keeps the original lookup behavior. `--output` allows an explicit destination. A scoring export does not replace the lookup export or its connector.

## Add the scoring tool manually

Following [Microsoft's REST tool workflow](https://learn.microsoft.com/en-us/microsoft-copilot-studio/agent-extend-action-rest-api):

1. Open the existing **Fraud Investigator** agent, then **Tools → Add a tool → New tool → REST API**.
2. Upload `data/copilot/transaction_scoring.swagger.json`.
3. Use **Transaction Scoring** as the name. Keep the English descriptions explaining that the backend uses a frozen model and threshold.
4. Select **API key**, parameter location **Header**, parameter name **X-API-Key**. Supply the existing secret only in the connection form.
5. Select **Score an existing transaction by ID**. Review its single request field and six response fields, publish the tool, create/select its connection and add it to the agent.
6. Keep the existing Transaction Lookup tool. This step does not replace it.

Copilot Studio tenant permissions and UI availability must be verified in the actual environment. No automated account configuration or new subscription is performed by this repository.

### Agent instruction addition

```text
When asked to assess an existing transaction, retrieve its facts with the
transaction lookup tool and use the transaction scoring tool for its ML score.
Submit only the transaction ID. Never calculate, invent or modify the model
score, threshold, model version or policy version yourself.
Present the returned score, threshold and alert decision separately from facts.
A score is not a calibrated probability, and an alert does not confirm fraud.
A score below threshold does not prove legitimacy.
If scoring fails, explain that the assessment is unavailable; do not substitute
zero or infer an alert decision. Cite the returned model and policy versions.
Do not claim to have checked account histories or saved a report unless the
corresponding connected tools actually completed those actions.
```

### Manual acceptance checks

Start a fresh test conversation and ask:

```text
Retrieve transaction d83a6871a919fd644c774f3e65fbe41b and use the
transaction scoring tool to return its suspicion score, threshold and alert.
```

Inspect the actual tool trace: lookup and scoring must both run and the answer must match the returned fields. Then check an unknown ID, malformed ID and scoring unavailability. A connector failure may invoke the **On Error** system topic before a generated answer; keep lookup-specific not-found handling scoped to the lookup tool. Model failures or 401 errors must not become a not-found or no-fraud answer.

## Verification record

The updated repository passes **74 tests** using Python 3.11 on macOS Apple Silicon. New synthetic tests cover both-operation authentication, threshold equality, feature order, missing ratio, strictly prior history, malformed/missing/extra inputs, unavailable/incompatible artifacts, continued lookup, narrow route exposure and the separate fully described Swagger export. The fixed-score test model is explicitly synthetic and is not evidence of CatBoost quality.

A separate HTTP check started the actual gateway command on a temporary loopback port and compared its six output fields with the existing frozen service on four development transactions, through step 212. All four matched exactly. Authentication, malformed/unknown IDs and successful lookup were checked. No label file was opened, no model was trained, no final-test evaluation was performed and the model/manifest hashes remained unchanged. The temporary verification server was stopped without touching the running demonstration server or tunnel.

The Copilot Studio import and scoring conversation have not yet been validated for this addition. No new Linux/Windows or `uv run --locked` check is claimed for this stage. Existing dependencies are unchanged.

## Interview notes

1. **Why reuse the scoring service?** It keeps feature construction, artifact checks and the decision threshold identical to the evaluated pipeline.
2. **Why a separate Swagger file?** It adds one focused tool while preserving the existing lookup definition and connection.
3. **Why keep lookup available when the model is missing?** Recorded facts remain useful, while an explicit 503 prevents fabricated scores.
