# Saved investigations in Copilot Studio

## Implemented and verified scope

The protected loopback gateway adds nine case, evidence and report operations.
They reuse the local services; no second agent, model training or automatic
Copilot configuration is included. Existing lookup/scoring/history operations
remain available. The frozen model, feature definitions and threshold are unchanged.

The owner has manually verified the five original tools, interactive transaction
selection and an error-explanation prompt. These new case tools have been verified
locally, but still require manual import and acceptance testing in Copilot Studio.

## Tools

| Operation ID | Route | Purpose |
| --- | --- | --- |
| `findInvestigationCasesByTransactionId` | `GET /cases?transaction_id=...` | Rediscover cases without knowing a case ID |
| `createInvestigationCase` | `POST /cases` | Save a case for one known transaction |
| `getInvestigationCase` | `GET /cases/{case_id}` | Retrieve the returned case ID |
| `executeRecordedCheck` | `POST /cases/{case_id}/runs` | Execute and retain one permitted check |
| `listRecordedChecks` | `GET /cases/{case_id}/runs` | Inspect successes, errors and incomplete runs |
| `getRecordedCheck` | `GET /cases/{case_id}/runs/{run_id}` | Retrieve one evidence record |
| `generateInvestigationReport` | `POST /cases/{case_id}/reports` | Save a deterministic evidence-linked snapshot |
| `listInvestigationReports` | `GET /cases/{case_id}/reports` | List report versions |
| `getInvestigationReport` | `GET /cases/{case_id}/reports/{version}` | Retrieve an immutable saved version |

All require `X-API-Key`. Every POST also requires a caller-supplied
`Idempotency-Key` of 1–128 characters. IDs in paths are lowercase 32-character
hexadecimal backend IDs. A version is a positive integer. Lists default to 50,
are capped at 100, and explicitly report truncation. No list continuation is
implemented; do not describe a truncated response as complete.

Case creation accepts only `transaction_id`. A check request accepts only:

```json
{"operation": "recipient_history", "limit": 50, "lookback_steps": 168}
```

Allowed operations are `transaction`, `score`, `sender_history`,
`recipient_history`. History bounds are optional, with maximums of 100 rows and
168 prior simulated steps. Bounds are rejected for transaction and scoring
checks. The backend derives the account, cutoff and transaction from the case;
callers cannot supply scores, evidence, labels, SQL, model parameters or file paths.
History includes both roles for the selected account and excludes its anchor step.

Case and evidence services write investigation tables in the application SQLite
file. They do not edit imported transactions, accounts or evaluation labels.
Caller-submitted event routes, arbitrary SQL, report deletion and case deletion
are not exposed by this gateway. The shared key is prototype access control,
not user-specific ownership or tenant isolation. Anyone authorized by that key
can access the exposed cases if they possess their IDs.

## Rediscovering cases by transaction ID

`GET /cases?transaction_id=<32-hex-ID>&limit=10` requires the API key but no
idempotency key. IDs are normalized to lowercase. `limit` defaults to 10 and
must be 1–100. The response contains `transaction_id`, `limit`, `returned_count`,
`truncated` and `cases`. Each case contains its ordinary metadata plus
`latest_report`: null, or the saved report ID, highest version and generation time.
The report body remains available through the existing report-reading tool.

Known transaction with no case: HTTP 200 and `cases: []`. Unknown transaction:
404. Missing/malformed input: 422. Failed database query: 503, never an empty
success. Search is a consistent read-only snapshot and does not create cases,
execute checks, initialize report tables, update status or regenerate a report.

Cases are ordered by **creation timestamp descending**, with case ID descending
as a stable tie breaker, not by the case's `updated_at` field or latest evidence.
Multiple cases are allowed; none is automatically selected. Inspect runs/report
before reusing a case. Report presence does not establish that checks succeeded
or that its snapshot includes later runs or the current model. The current case
status remains independent of report generation. There is no continuation page
for a truncated list yet; raise the limit up to 100 or obtain a case ID explicitly.

An index on `(transaction_id, created_at DESC, case_id DESC)` is installed during
case-creation writes, including retry calls. It adds storage and index maintenance
on case creation. Read-only search works on legacy databases before the index
exists; it does not perform a hidden schema migration. A synthetic EXPLAIN QUERY
PLAN check confirms index use without a temporary sort once installed. No speed
improvement on the real dataset is claimed.

The **search → create/resume** orchestration remains to be configured in Copilot.
These are separate requests: two callers can both observe an empty search and
create different cases with different keys. This change does not add a unique
active-case rule or atomic find-or-create. Old results and report versions are
preserved; the agent must distinguish retrieval, completion and deliberate reanalysis.

## Case-search verification, 24 October 2026

95 tests pass on macOS Apple Silicon with Python 3.11, including six new search
tests: known/unknown transactions, multiple cases and stable ordering, report
metadata and legacy schemas, authentication/validation, database errors and
read-only behavior, reopening persistence, truncation and index query-plan use.
An actual temporary HTTP server additionally verified the search/create/report/
rediscovery path on synthetic data, including 401/404/422 and truncation. No
real database writes, label access, model predictions or running-server changes
were performed. Linux, Windows and Copilot import are not verified for this change.

Interview questions:

1. **Why search by transaction rather than asking for a case ID?** The transaction
   is the user's known reference; the backend returns persistent case references
   across conversations.
2. **Why distinguish zero results from a failed search?** Only a successful empty
   search establishes absence. Creating a case after a query failure risks duplicates.
3. **Does a saved report prove completeness?** No. It is a versioned snapshot;
   failed or missing checks and subsequent runs must be inspected separately.

## Requests, retries and recorded failures

Generate one key per logical request and keep it stable for network retries.
Use separate keys for each check. A deliberately new investigation needs a new
case-creation key, even when the transaction is the same. Do not derive every
case key solely from transaction ID, which would merge independent investigations.
The key is an input; the API does not automatically detect semantic duplicates.
An LLM choosing a new key for a retry can still create duplicates, so test and
preserve keys in the caller's workflow. No automatic retry orchestration is
introduced in this lot.

Cases and finished check retries return the original result after restart. Using
a key with different content yields 409. A check left running after interruption
is visible as incomplete; repeating its key yields 409 rather than claiming
success. Inspect runs first. A deliberate new attempt uses a new key.

HTTP 201 means the evidence record was saved, not that its tool succeeded.
Always inspect `status`, `result`, `error`, `verification` and `incomplete`.
For example, scoring without a loaded model produces a persisted `unavailable`
run with no score. Reports preserve that absence. A failure to persist the
investigation itself returns HTTP 503.

Report generation requires a key in this gateway. Same case and same key returns
the exact original snapshot even after more checks are added. A new report key
creates a new version reflecting the currently stored checks. Report and retry
cache are written atomically; an error does not leave a half-saved version.
The existing full local API retains its previous unkeyed report interface.

No model or tool is rerun while generating a report. Facts, score, histories and
limitations cite the stored run IDs. The report also includes failed, missing
and interrupted checks. Its content is deterministic; the agent can summarize
it but must not claim that generated prose is itself a backend fact. Reports
newly generated by this version are English. Previously saved versions are not
rewritten, including older French reports. Case status stays `open` unless a
separate future lifecycle operation changes it; a saved report is not case closure.

## Export and manual connection

Restart only the Python API in its existing terminal after upgrading; preserve
its key and leave the tunnel running. Use the same startup command in
[COPILOT_REST.md](COPILOT_REST.md). Do not restart a working tunnel just to add routes.

Generate the fourth Swagger file from the current HTTPS tunnel URL:

```sh
.venv/bin/python scripts/export_copilot_openapi.py \
  --tool cases --base-url https://YOUR-CURRENT-TUNNEL.trycloudflare.com
```

Import `data/copilot/investigation_cases.swagger.json`, not the versioned
`.invalid` template. The file contains no secret and remains outside Git.
Existing lookup, scoring and history files do not need reimporting for this addition.

1. In **Fraud Investigator → Tools → Add a tool → REST API**, import this file.
2. Name the connector **Investigation Cases** and select its nine operations.
3. Configure API-key authentication: **Header**, `X-API-Key`, with the existing
   server key stored only in the connection form.
4. For this local shared-access prototype, select **Additional details →
   Credentials to use → Maker-provided credentials**, where allowed by the
   environment. Bind the valid connection and save each tool.
5. The prototype previously entered a connection-prompt loop with **End user
   credentials** while Power Apps tests passed. Switching the scoring tool to
   **Maker-provided credentials** resolved the observed runtime failure.
   This is a different access model: users of the tool use the maker's backend
   access. Do not disable organization policy if that option is unavailable.

UI and permissions must be checked in the actual environment. Import, nine-tool
binding and real Copilot writes have not been performed automatically.

## Agent instruction addition after tools are connected

```text
Before a saved investigation, search cases by the exact transaction ID using
findInvestigationCasesByTransactionId. Only a successful empty search permits
creating a new case. A search error is not absence. If cases exist, inspect their
recorded checks and latest report to decide whether to retrieve or resume.
Multiple cases may exist; explain which case is chosen and ask for clarification
when the choice is ambiguous. Do not infer completeness from report presence
or case status alone. Reuse the selected case_id for all checks and the report.
Never invent case or run IDs. An explicitly requested new investigation may
create a separate case; do not silently overwrite prior investigations.
Choose one idempotency key per logical request; preserve it unchanged on retries.
Run transaction, score and the relevant histories through executeRecordedCheck,
not the unrecorded lookup/score/history tools when evidence must be retained.
Inspect each run status: HTTP success does not imply a successful check.
Cite run_id for facts and findings. Distinguish observations, hypotheses and ML
score interpretation. An alert is not proof of fraud; no alert is not legitimacy.
After the checks, call generateInvestigationReport and present its returned
case_id, report_id and version. Say it was saved only after a successful response.
For a deliberate updated snapshot use a new report key; retries reuse the old key.
Keep missing checks and errors explicit. Do not claim case closure or user-specific
access control. These transactions are simulated PaySim data.
```

## Acceptance checks

First verify the single-transaction path in Power Apps, then in Copilot:
create a case, execute all four check types, generate a report and retrieve
version 1. Verify real returned IDs and references rather than the wording alone.
Retry the same requests with the same keys and check unchanged IDs and version.
Verify unknown transaction, out-of-range history, a partial report and connection
failure separately. The error prompt needs the new case/report mappings; a
recorded unavailable run is a tool response to inspect, not an HTTP exception
that necessarily invokes On Error.

## Local verification, 24 October 2026

89 tests pass on macOS Apple Silicon with Python 3.11, including seven new tests:
authentication of all eight operations, persistence and retries after reopening,
exact simulated scorer capture, input validation and forged-evidence rejection,
interrupted runs and cross-case evidence lookup, report/cache atomic rollback,
and Swagger route/reference consistency. Existing route-surface assertions were
updated for the newly authorized paths. Existing report tests retain their
provenance/immutability checks with English presentation assertions.

An actual temporary loopback HTTP server additionally exercised a complete
four-check workflow on a synthetic database with an explicitly synthetic scorer,
report retrieval/retry, authentication rejection, unknown transaction, conflicts
and invalid bounds/operations. It did not touch the running demo server or its
key, read labels, write the PaySim database, train a model or re-evaluate the test.
Linux, Windows, Copilot import and cloud-mediated calls for this lot are unverified.
No new dependency or paid subscription was added. Copilot usage remains subject
to the environment's existing license/credits.

## Interview questions

1. **Why record a check in Python?** The backend stores the actual execution,
   parameters and outcome; a declaration written by an LLM is not evidence of execution.
2. **Why can HTTP 201 contain an unavailable score?** The evidence record was
   successfully saved, but the underlying model was unavailable. Both facts matter.
3. **Why reuse a report key?** A network retry should return the original snapshot.
   A deliberate update gets a new key and a new version; old reports stay intact.
