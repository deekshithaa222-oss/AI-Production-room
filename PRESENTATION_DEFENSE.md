# SentinelAI Presentation Defense Notes

Use this as the concise answer bank for the Amazon SA communication presentation Q&A.

## Core Positioning

SentinelAI is a demo Agentic RAG investigation assistant that dynamically gathers operational evidence, ranks plausible causes, explains its reasoning through traceable sources, and helps engineers investigate incidents. It does not independently prove root cause or execute remediation.

Best one-line framing:

> We should not trust AI because it sounds confident; we should trust it when it can show the evidence behind its answer.

## Safer Claims

- Say: SentinelAI helps engineers avoid stopping at the first visible symptom.
- Say: It is more likely to identify the most likely cause because it checks whether evidence explains downstream symptoms.
- Say: The demo implements the core pattern: planner, specialist agents, evidence collection, lead scoring, and human approval.
- Avoid: SentinelAI always finds the true root cause.
- Avoid: It fully prevents hallucination.
- Avoid: It is production-ready as-is.

## What The Demo Supports

- A planner selects relevant specialists from the incident description and configured evidence sources.
- Specialist agents collect source-backed evidence from logs, metrics, databases, payment health/logs, networking, Kubernetes, cloud, and deployment metadata.
- Missing sources are reported as missing evidence instead of being guessed.
- The report stays unconfirmed until a human reviews the evidence.
- Payment timeout evidence can be scored as the likely upstream issue when it explains checkout queuing, database wait, and app latency symptoms.

## Current Demo vs Production Evolution

Current demo:

- Planner-based specialist selection.
- One evidence-collection round.
- Lead scoring.
- Human approval.
- In-memory investigation state.

Production evolution:

- Multi-round planning.
- Contradiction checking.
- Dependency tracing.
- Persistent state.
- RBAC and auditing.
- Historical evaluation.
- Automated post-remediation validation.

## Evaluation Metrics

If asked how to prove SentinelAI is better, do not only explain the architecture. Explain how you would evaluate it.

- Investigation-lead accuracy compared with historical incident reports.
- Mean Time to Detect (MTTD) and Mean Time to Resolution (MTTR).
- False positive investigation leads.
- Percentage of investigations requiring human correction.
- Investigation latency from request to report.
- Cost per investigation, including LLM tokens and infrastructure API calls.
- Evidence coverage: how many required sources were available for the investigation.
- Engineer approval rate for suggested leads and recommended actions.
- Abstention quality: whether the system correctly refuses to overstate uncertain conclusions.

Strong answer:

> I would replay a labeled set of historical incidents and compare SentinelAI with a fixed runbook, one-shot RAG, and human investigation. I would measure whether the correct lead appears in the top one or top three, whether every claim is evidence-supported, whether critical sources were missed, how many unnecessary tools were called, how quickly the useful lead surfaced, how often humans rejected the lead, and whether the system abstained appropriately when evidence was insufficient.

## Planner Stop Criteria

A production planner should not investigate forever. It should stop when one of these conditions is met:

- An evidence-sufficiency threshold is reached.
- New tool calls are no longer producing new evidence.
- The investigation budget is exceeded.
- Maximum reasoning depth is reached.
- Evidence is missing or contradictory and human intervention is required.

Strong answer:

> The planner stops when additional investigation is unlikely to reduce uncertainty enough to justify the cost and latency. If evidence is insufficient, it says so instead of forcing a conclusion.

## Confidence Model

Do not describe confidence as the LLM feeling confident. Confidence should come from evidence.

- Quantity of supporting evidence.
- Consistency across sources.
- Quality and freshness of data.
- Whether the hypothesis explains downstream symptoms.
- Whether contradictory evidence exists.

Strong answer:

> Every lead should have confidence derived from the quantity, consistency, and quality of supporting evidence, not simply from the LLM's confidence.

## Validation Loop

Validation should follow the full causal loop:

> Hypothesis -> supporting evidence -> contradiction search -> causal check -> remediation -> observed recovery -> human confirmation

For the payment-service example, stronger validation means checking that after the payment issue is corrected:

- Payment latency returns to normal.
- Checkout failures decrease.
- Database queues drain.
- Application errors fall.
- Customer-facing performance recovers.

That is much closer to confirming causality than simply finding payment timeout logs.

## Failure Modes

SentinelAI can fail or become uncertain when:

- Logs are missing or incomplete.
- Timestamps are inconsistent across systems.
- Metrics are delayed, sampled, or misconfigured.
- Monitoring is missing for a dependency.
- Dependencies are unknown or undocumented.
- Evidence is contradictory.
- Multiple partial failures happen at the same time.
- A tool lacks permission to access the right source.

Strong answer:

> When evidence is insufficient or conflicting, the system should explicitly report uncertainty instead of inventing an answer.

## Evidence Provenance

Every material claim in the report should be traceable to its source evidence. Each evidence item should retain:

- Source system.
- Timestamp.
- Query or tool used.
- Relevant excerpt or metric.
- Freshness.
- Collection status.
- Investigation ID.

Strong answer:

> Every material claim in the report should be traceable to its source evidence.

## Observability For SentinelAI

In production, SentinelAI itself needs monitoring:

- Planner decisions and routing history.
- Tool-call success and failure rates.
- Retrieval latency.
- Token and infrastructure cost.
- Evidence-source freshness.
- Unsupported-claim rate.
- Human overrides.
- Investigation outcomes.
- Prompt and model version.
- End-to-end traces for each investigation.

## Prompt Injection And Untrusted Data

Logs, tickets, documents, and tool output must be treated as untrusted input.

- Separate system instructions from retrieved evidence.
- Never execute commands found inside logs or documents.
- Allowlist tools and parameters.
- Sanitize sensitive output.
- Require approval for write actions.
- Defend against prompt injection in retrieved content.
- Restrict each specialist to read-only access where possible.

## Data Governance

Production deployments should account for:

- Redaction of secrets and personal data.
- Encryption in transit and at rest.
- Retention policies.
- Tenant isolation.
- Regional data residency.
- Model-provider data-handling controls.
- Access logging.

## Multiple Contributing Causes

Not every incident has one root cause. SentinelAI should support multiple contributing causes rather than forcing every incident into a single-root-cause explanation. For example, a deployment change and a payment-provider slowdown might combine to create the outage.

## Human Review Model

- Read-only investigation can run automatically.
- Low-risk suggestions can be reviewed by the on-call engineer.
- High-impact actions such as rollback, failover, scaling, or configuration changes require explicit authorization.
- All actions should be auditable and reversible where possible.

## Security Boundary Clarification

Separate agents are not automatically a security boundary. Least privilege must be enforced through separate IAM roles, scoped credentials, tool-level authorization, network policies, and backend access controls. The LLM prompt alone is not a security boundary.

## AWS Mapping

A production AWS version could use:

- Amazon Bedrock for the model layer.
- Bedrock Agents or a LangGraph-style service for orchestration.
- Amazon CloudWatch for logs and metrics.
- AWS X-Ray for traces across app, database, and payment calls.
- Amazon OpenSearch Service for searchable operational evidence.
- AWS Lambda or Amazon ECS for specialist collectors.
- Amazon S3 or DynamoDB for evidence snapshots and investigation state.
- AWS IAM for least-privilege agent permissions.
- AWS CloudTrail for auditing investigation activity.

Simple SA-style explanation:

> On AWS, I would separate the reasoning layer from the tool-access layer. Bedrock handles model reasoning, specialist collectors run with narrow IAM roles, CloudWatch and X-Ray provide evidence, and the final report remains human-approved before any remediation.

## Likely Follow-Up Answers

### What is the difference between RAG and Agentic RAG?

Regular RAG usually retrieves relevant context once and answers. Agentic RAG adds a planner loop. It can decide which evidence to collect, evaluate whether the evidence is enough, check whether symptoms are only downstream effects, and continue investigating when needed.

### How does the planner decide the next specialist?

The planner selects the specialist most likely to reduce the current uncertainty, based on the incident description, collected evidence, known dependencies, and remaining unanswered questions. It does not need to be complex machine learning. Even a rules-plus-evidence planner can be effective if it routes based on symptoms, dependencies, and missing evidence.

### Why Agentic RAG instead of MCP?

MCP standardizes tool access. Agentic RAG decides which tools to use, when to use them, and whether additional evidence is needed. MCP can be part of the tool layer, but it is not the reasoning and planning strategy by itself.

### How is this different from giving GPT access to all logs?

Giving GPT access to every log does not automatically make the system agentic. It still has to process a massive amount of information in one step. SentinelAI breaks the investigation into smaller decisions. It gathers evidence incrementally, decides what to investigate next, validates hypotheses, and only then produces an evidence-backed conclusion. That reduces unnecessary retrieval, improves explainability, and scales better for complex production environments.

### Why not retrieve everything every time?

That increases cost, latency, and noise. In a real production environment, logs and metrics can be huge. Routing lets simple incidents take a lightweight path while complex or high-impact incidents trigger deeper investigation.

Planner-based routing also reduces both LLM token usage and infrastructure API calls because only relevant agents execute.

### How does it know when it has enough evidence?

It checks whether the proposed cause explains the full chain of symptoms. For example, payment timeouts can explain database queuing and app latency. If evidence is missing or contradictory, it should report uncertainty instead of claiming a confirmed root cause.

### How do you prevent hallucination?

I would not say hallucination is impossible. The system reduces hallucination risk by grounding answers in real evidence sources and explicitly reporting missing evidence when sources are unavailable.

The LLM is not treated as the source of truth. It proposes hypotheses, but evidence determines whether those hypotheses survive.

### What happens if agents disagree?

The planner should treat disagreement as uncertainty. It can gather more evidence if available, lower confidence in the lead, or report that the evidence is mixed.

### What are the main tradeoffs?

The tradeoffs are cost, latency, and complexity. Agentic RAG can improve investigation quality, but it may call more tools and take longer. That is why routing and human approval are important.

### Is this production-ready?

No. It is a demo of the core pattern. A production version would add deeper iterative reasoning, contradiction scoring, stronger observability integrations, persistent audit trails, and stricter security controls.

## Red Flags To Avoid

- Do not overclaim that the system automatically knows the root cause.
- Do not make the presentation too implementation-heavy.
- Do not ignore security; mention read-only access, least privilege, audit logs, and human approval.
- Do not say it eliminates hallucination; say it reduces hallucination risk through grounding.
- Do not forget cost and latency; explain selective routing.

## Optional Final Slide: Production Challenges

- Hallucinations: ground answers in evidence.
- Missing data: report insufficient evidence.
- Cost: use planner-based selective routing.
- Latency: stop when confidence is sufficient or budget is reached.
- Security: enforce least privilege, audit logs, and approval workflows.
- Trust: require human approval before remediation.

## Strong Closing

My takeaway is simple: in real systems, confidence is not enough. AI should show its evidence, check whether the first answer is only a symptom, and be honest when the evidence is incomplete.
