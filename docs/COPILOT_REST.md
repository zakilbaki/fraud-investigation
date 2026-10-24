# Copilot Studio REST tools

## Gateway and tools

`scripts/serve_copilot_api.py` exposes five direct operations plus nine case/evidence/report operations on loopback.
See [Saved investigations](COPILOT_CASES.md) for the new contracts and import steps.

Direct operations:

| Operation | Purpose | Copilot tool |
| --- | --- | --- |
| `GET /transactions/{transaction_id}` | Read ten allowed pre-transaction/provenance fields | `getTransactionById` |
| `POST /score` | Score an existing transaction using frozen CatBoost | `scoreTransactionById` |
| `GET /transactions/{transaction_id}/sender-history` | Derive the sender and cutoff from a transaction | `getSenderHistoryByTransactionId` |
| `GET /transactions/{transaction_id}/recipient-history` | Derive the recipient and cutoff from a transaction | `getRecipientHistoryByTransactionId` |
| `GET /accounts/{account_id}/transactions` | Query an explicit account with a required cutoff | `getAccountHistory` |

The gateway now exposes the closed case/evidence/report interface, but not caller event submission, arbitrary SQL, `/docs`, `/openapi.json` or a public health route. Scoring's exact prior-recipient receipt count is separate from these bounded account histories and is unchanged.

Lookup and scoring have been manually demonstrated together in Copilot Studio. The three history operations have also been manually exercised by the owner. The new case tools still require manual Copilot import. The full backend investigation tools are documented in [API.md](API.md).

## Authentication and startup

All operations require `X-API-Key`. The server compares it with `FRAUD_INVESTIGATION_API_KEY` using a constant-time comparison. A missing, empty or shorter-than-32-character secret prevents startup; an absent/wrong request key returns 401. The secret is not stored in Git or OpenAPI. This shared key does not establish individual user identity.

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

Use the same configured gateway secret for all tools. If a secret has been exposed, rotate it and update the affected connections together. If the variable is already exported in this terminal, omit `read` and `export`. The defaults match these paths. The server always binds to `127.0.0.1`.

When upgrading an already running gateway, stop **only that API process** with Ctrl+C and rerun its command in the same terminal. Keep an existing tunnel running. Model and manifest are loaded and checked once at startup; a missing/incompatible artifact leaves lookup working and scoring returns 503. No model is trained or downloaded automatically.

## Frozen scoring contract

The request contains only `transaction_id`, exactly 32 hexadecimal characters. Features, history and threshold are calculated by Python. Extra request fields, including a caller-supplied threshold, are rejected.

Response fields are `transaction_id`, `suspicion_score`, `threshold`, `alert`, `model_version` and `policy_version`. The global threshold stays **0.3123179923852385** and `alert` is true when `suspicion_score >= threshold`. The CASH_OUT exploratory policy is not applied. Scores are not calibrated fraud probabilities or proof of fraud.

The same saved transformer constructs H's seven features. Prior-recipient counts exclude the current and future steps and have no response-row cap. Only the application database is opened, read-only. Evaluation labels, post-transaction balances and arbitrary file paths are not tool inputs.

Scoring errors are 400 for a malformed ID, 401 for authentication failure, 404 for an absent transaction, 422 for an invalid request or incompatible transaction data, 503 for unavailable/incompatible model/database and 500 for unexpected prediction failure. No substitute score or internal traceback is returned. A failed request must not be described as a low-risk transaction.

This direct scoring route does not create a case or persist a tool-evidence record. Recorded investigation scoring is available on the protected gateway: `POST /cases/{id}/runs` with `operation=score`.

## History by transaction or by account

The two anchored tools accept a transaction ID, optional `lookback_steps` (default 168, range 1–168) and optional `limit` (default 50, range 1–100). Python retrieves the original sender or recipient and sets `before_step` to that transaction's step. The caller cannot change the derived account or cutoff. An additional caller query such as `before_step=999` does not override this rule.

The direct account tool accepts an exact observed account ID and requires `before_step` (1–1,000,000). The same lookback and row limits apply. An account ID is a PaySim identifier, not a person's name. For example, to inspect steps 10 through 20 inclusive, use `before_step=21` and `lookback_steps=11`. Ask for missing temporal information rather than assuming a civil date or an unlimited search.

Every response searches **both account roles**: transactions sent or received by the selected account. “Sender history” and “recipient history” refer to the account selected from the anchor, not a restriction to outgoing or incoming operations. The ML feature counts receipts only, so it is not equal to this history's `returned_count`.

The effective window is `max(1, before_step - lookback_steps) <= step < before_step`. All current-step and future transactions are excluded. A self-transfer is returned once. Rows sort by descending step, then ascending stable identifier; within-step identifier order is not chronology. The existing two account/step indexes support these searches; no new index or schema migration is introduced.

Responses contain `account_id`, `before_step`, `min_step`, `lookback_steps`, `limit`, `returned_count`, `truncated` and `transactions`. Anchored responses also contain `anchor_transaction_id` and `account_role`. Each transaction has the same ten public fact/provenance fields as lookup. Decimal amounts remain strings. Labels and post-transaction balances are excluded.

`returned_count` is the number of returned rows, not the full matching count. `truncated=true` means at least one additional match exists **within the requested window**. It says nothing about earlier activity outside that window. This version does not provide continuation pagination; a truncated response must not be described as a complete history.

A known account with no matching activity returns 200 with an empty list. An unknown account or anchor transaction returns 404. A malformed ID returns 400; a missing/invalid cutoff or out-of-range limit returns 422; an unavailable database returns 503. Histories remain available when the model cannot load. The application database is opened read-only and SQL values are bound as parameters. No SQL supplied by the agent is executed.

These three direct tools do not create a case, tool `run_id` or saved report. Their transaction IDs and source provenance remain available in the response; persisted evidence requires the separate case-linked backend operations.

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

The [lookup template](copilot/transaction_lookup.swagger.template.json) is unchanged. The new [scoring template](copilot/transaction_scoring.swagger.template.json) describes only `POST /score`. The new [history template](copilot/account_history.swagger.template.json) describes only the three history GET operations. Each uses Swagger/OpenAPI v2 JSON, a unique operation ID and `apiKey` authentication in the header. Their `.invalid` hosts are deliberate placeholders. **Import generated files, not these templates.**

```sh
.venv/bin/python scripts/export_copilot_openapi.py \
  --tool lookup --base-url "https://ACTUAL-TUNNEL-HOST"
.venv/bin/python scripts/export_copilot_openapi.py \
  --tool scoring --base-url "https://ACTUAL-TUNNEL-HOST"
.venv/bin/python scripts/export_copilot_openapi.py \
  --tool history --base-url "https://ACTUAL-TUNNEL-HOST"
```

Replace the example hostname with the existing root HTTPS URL. The exporter rejects HTTP, extra paths, URL credentials/query/fragment and `.invalid` hosts. Generated files are ignored by Git:

- `data/copilot/transaction_lookup.swagger.json`
- `data/copilot/transaction_scoring.swagger.json`
- `data/copilot/account_history.swagger.json`

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

## Add the three history tools manually

Create a new REST API tool using `data/copilot/account_history.swagger.json`, with the same `API key` / `Header` / `X-API-Key` configuration. Use **Account History** as its name. Select all three operations and add them to the agent. Keep lookup and scoring configured separately, preserving their existing connectors.

If the tunnel hostname changes later, regenerate the import files. In Power Apps, the existing custom connector can be edited with **Update OpenAPI file** and saved with **Update connector**; it is not necessary to keep creating numbered duplicates. Use the same environment and the exact connector bound to the agent. A successful Power Apps **Test operation** checks that connection; Copilot still needs to use the correct connection reference. Actual tenant UI and permissions determine the available editing options.

Instruction addition:

```text
For an investigation tied to a transaction, use the sender-history and
recipient-history tools with that transaction ID. The backend derives the
accounts and exclusive step cutoff; do not substitute another account or time.
For a direct account request, use the account-history tool with the exact
observed account ID and a specified before_step. Ask for a missing cutoff.
All histories include both incoming and outgoing transactions. They are not
the model's receipt-count feature. Report the searched window, returned_count
and truncated flag. Do not describe a partial history as complete.
An empty list means no matching records in the searched window, not that the
account has never been active. Do not infer event order within one step,
fraudulent intent or a money-flow chain from shared amounts alone.
Do not claim a case, recorded tool run or saved report unless those separate
tools actually complete. These history tools return facts, not fraud labels.
```

Manual checks after connecting:

```text
For transaction d83a6871a919fd644c774f3e65fbe41b, retrieve sender and
recipient histories. Report both account IDs, the step bounds, returned counts
and whether either list is truncated. Do not score or save a report.
```

```text
Retrieve the history of account C553264065 before step 6, looking back
5 steps, with at most 10 transactions. State the searched bounds and truncation.
```

Compare the direct-account result with the anchored recipient history using identical limits/window. Check a transaction at step 1, an unknown account and an out-of-range limit. Confirm the tool trace actually includes the requested operations. The expected first-step history is empty, not an error or evidence of legitimacy.

## Verification record

The scoring stage passed **74 tests** using Python 3.11 on macOS Apple Silicon. New synthetic tests cover both-operation authentication, threshold equality, feature order, missing ratio, strictly prior history, malformed/missing/extra inputs, unavailable/incompatible artifacts, continued lookup, narrow route exposure and the separate fully described Swagger export. The fixed-score test model is explicitly synthetic and is not evidence of CatBoost quality.

A separate HTTP check started the actual gateway command on a temporary loopback port and compared its six output fields with the existing frozen service on four development transactions, through step 212. All four matched exactly. Authentication, malformed/unknown IDs and successful lookup were checked. No label file was opened, no model was trained, no final-test evaluation was performed and the model/manifest hashes remained unchanged. The temporary verification server was stopped without touching the running demonstration server or tunnel.

Lookup and scoring were subsequently confirmed manually in Copilot Studio. The history addition passes **82 tests**, including authenticated access, server-derived accounts/cutoffs, inclusive lower and exclusive upper bounds, limits, truncation, both roles, self-transfers, missing databases, unknown accounts and absence of label/post-balance fields. An actual temporary HTTP server compared 16 history responses (anchored and direct, both roles) against independent SQL on four development anchors through step 212. No label file, ML prediction or training was used; model and manifest hashes stayed unchanged. Copilot history import and agent use remain unverified until the manual checks above. No new Linux/Windows or `uv run --locked` check is claimed for this stage. Existing dependencies are unchanged.

## History interview notes

1. **Why accept a transaction ID as well as an account ID?** A transaction anchor lets Python derive the account and time bound reliably; direct IDs support an explicit account-level inquiry.
2. **Why can an empty list differ from an unknown account?** A known account may have no observed activity in the requested window. It does not imply no lifetime activity.
3. **Why exclude the same step?** The dataset does not establish event order within one simulated hour.

## Scoring interview notes

1. **Why reuse the scoring service?** It keeps feature construction, artifact checks and the decision threshold identical to the evaluated pipeline.
2. **Why a separate Swagger file?** It adds one focused tool while preserving the existing lookup definition and connection.
3. **Why keep lookup available when the model is missing?** Recorded facts remain useful, while an explicit 503 prevents fabricated scores.

## Case tools and connection troubleshooting

See [COPILOT_CASES.md](COPILOT_CASES.md) for the fourth export (`--tool cases`),
protected writes, retry keys, English versioned reports and the demonstrated
maker-versus-end-user credential issue.
