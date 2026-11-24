# Investigation Policy Agent: English demonstration corpus

Version 1.0.0, prepared 24 November 2026. Status: authored and statically reviewed;
Copilot ingestion, retrieval quality and multi-agent delegation are not yet tested.

## Architecture decision

This knowledge-only specialist replaces the proposed Evidence Reviewer. The
Reviewer and its planned read-only dispatcher are not prerequisites for this lot.
Fraud Investigator retains operational tools. A future coordinator asks Policy
Agent what procedure applies, delegates authorized execution to Investigator,
and combines procedural requirements with returned evidence. Procedures do not
constitute execution authorization. No API, live flow, database or model changed.

This split demonstrates document-grounded guidance versus tool-grounded facts.
It adds orchestration latency and testing work; quality improvements are not
assumed. Unlike a live evidence reviewer, Policy Agent cannot certify a case's
completeness from an ID alone.

## Upload only the four files under knowledge/

| File prefix | Knowledge-source description |
| --- | --- |
| 01 | Internal demo procedure: request scope, four-check baseline, case reuse and history bounds. |
| 02 | Frozen scoring policy, limitations, required scoring evidence and non-alert interpretation. |
| 03 | Empty versus missing evidence, truncation, recorded statuses, safe retries and report versions. |
| 04 | Internal human-handoff criteria, packet contents, unavailable capabilities and external-source limits. |

These are UTF-8 .txt files, supported for direct knowledge upload by Copilot
Studio. Go to the agent's Knowledge page, Add knowledge, upload the four files,
and supply distinct descriptions. Wait for processing to complete; test retrieval
before publishing. Local upload requires Dataverse search and is subject to the
environment's policies. Do not upload the ZIP itself.

Microsoft reference (consulted 24 November 2026):
https://learn.microsoft.com/en-us/microsoft-copilot-studio/knowledge-add-file-upload

## Configure the agent separately

Name: Investigation Policy Agent.
Paste setup/agent_description.txt into the description and
setup/agent_instructions.txt into Instructions. These files are configuration,
not knowledge documents. Do not upload setup/ or evaluation/ as knowledge.
Do not attach the investigation write dispatcher or any operational tool.
For the baseline, keep knowledge restricted to this versioned corpus and avoid
open-web grounding. If the UI permits disabling general-knowledge answers, use
that setting and still test unsupported questions. Instructions alone do not
prove that grounding restrictions are enforced.

If an Evidence Reviewer shell already exists, it can be renamed and reconfigured;
remove obsolete reviewer instructions and tools. Existing Investigator flows
must remain unchanged. Do not claim this configuration has been deployed here.

## Provenance and limits

Each rule identifies its authority. Internal policies were written for this
prototype; they are not bank procedures or legal mandates. Technical limits
were checked against backend revision a41390d. The only external-derived text
is the short, attributed AUSTRAC paragraph HND-05. The full external site/PDF is
not bundled or uploaded, preventing irrelevant legal content from being treated
as the internal procedure. The URL remains available for human verification.

All documents share one version/date and contain no case-specific fixture answers.
Replacing a version requires maintainer review and removal of superseded knowledge
sources. A change to text does not automatically change the existing agent or
backend behavior. Verify any desired workflow changes separately.

## Manual evaluation

Run evaluation/acceptance_tests.jsonl in fresh test sessions. It contains prompts,
expected behaviors, suggested rule references and critical failures. Do not use
it as retrieval knowledge. Equivalent valid citations may be accepted after
checking their actual content. No cloud tests have been run for this release.

For each prompt record: response, knowledge sources actually retrieved, exact
citations, applicable-rule accuracy, unsupported claims, unnecessary questions,
operational calls, latency and token use if visible. A plausible answer without
a supporting retrieved source is not a citation pass. Proposed gate: all critical
failures absent and each applicable requirement correctly supported; revise and
repeat failed cases before reporting acceptance. Do not infer accuracy from a
single successful example.

First smoke prompt: Can a low suspicion score establish legitimacy or waive the
other checks in a full recorded investigation? Cite the applicable procedure.

After standalone acceptance, test coordinator routing on a policy-only question,
a facts-only lookup and an explicitly authorized full investigation. Verify real
agent calls and preserved citations, not just a narrative claiming delegation.
