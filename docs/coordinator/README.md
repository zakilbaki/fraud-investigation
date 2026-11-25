# Fraud Investigation Coordinator

Configuration reference, 25 November 2026. The owner configured a Standard Copilot Studio coordinator connected to two existing specialists. These files are a maintainable configuration reference, not an exported live solution.

## Responsibilities

| Agent | Responsibility | Resources |
| --- | --- | --- |
| Fraud Investigation Coordinator | Select specialists, carry context and synthesize their responses | Two connected agents |
| Fraud Investigator | Retrieve facts, score transactions and perform requested saved investigations | Authenticated backend agent flows |
| Investigation Policy Agent | Retrieve and explain prototype procedures with rule citations | Four English v1.0.0 knowledge documents |

Separating procedure from execution lets the same coordinator answer a general policy question without accessing transaction records, or combine live evidence with the relevant procedure. The Policy Agent does not create cases or execute checks.

## Configuration

Use [instructions.txt](instructions.txt) as the coordinator instruction reference. Connect both specialists and pass conversation history. Explicitly include identifiers, scope and relevant returned evidence in each handoff.

Suggested connected-agent descriptions:

- **Fraud Investigator:** Retrieves PaySim transaction facts, suspicion scores, bounded account histories and saved case evidence using authorized backend tools. Performs saved investigation writes only when requested. Select for operational evidence, not general policy interpretation.
- **Investigation Policy Agent:** Retrieves the configured INV, SCO, EVD and HND v1.0.0 prototype procedures and explains applicable rules with citations. Select for procedure, scoring limitations, evidence completeness and human-handoff boundaries. Does not retrieve live cases or execute operations.

Keep test questions separate from knowledge. The policy corpus is maintained in [policy_agent](../policy_agent/README.md). Deployment still requires the owner's flows, connections and environment configuration; this repository does not provision them.

## Observed behavior

Owner-supplied interactive results show a mixed scoring/procedure response containing the backend suspicion score, threshold, non-alert interpretation and policy guidance. Policy examples distinguish a successful empty history from a technical timeout and preserve the difference between a recommendation and a mandatory requirement. Coordinator responses also request missing identifiers or cutoffs instead of reconstructing them.

Error responses disclose unavailable evidence rather than substituting invented transaction facts or scores. These are desirable evidence-handling behaviors. They describe observed examples, not a guarantee across all inputs. Response text alone cannot establish the actual delegation sequence or absence of writes.

## Evaluation assets

[The 20-case suite](evaluation/copilot-test-set-import.csv) covers five policy questions, five operational requests, five mixed requests and five clarification/capability-boundary requests. Each is an independent English single-response scenario. No scenario authorizes writes.

Import the two-column CSV in Copilot Studio Evaluation. Configure Custom with [these instructions](evaluation/custom-instructions.txt) and [Pass/Fail criteria](evaluation/custom-labels.txt). Answer quality can provide a second signal. The [JSON cases](evaluation/test_cases.json) and [routing reference](evaluation/routing-reference.csv) retain required, optional and forbidden agents for trace review.

In the observed coordinator interface, Tool use offered system topics rather than the connected specialists. Do not select an unrelated topic as a proxy for delegation. Inspect activity traces for agent selection, handoff inputs, operation order and nested writes. A plausible final answer is not evidence of the correct tool path.

Report answer correctness, task completion and routing compliance separately. An honest error response can demonstrate appropriate failure handling without satisfying an operational request. Custom judgments require human review; a generated Pass is not itself evidence of completion. These assets are a development evaluation suite, not a production certification or a measurement of retrieval precision/recall.

For reproduction, use an authenticated evaluation profile, available specialists and a running gateway with current connector host configuration. Fixture identifiers refer to the owner's synthetic demonstration dataset; adapt them and reference answers to independently verified fixtures when reproducing elsewhere. Never upload raw evaluation exports containing environment or conversation identifiers to the public repository.
