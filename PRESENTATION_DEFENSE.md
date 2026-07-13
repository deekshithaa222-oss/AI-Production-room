# SentinelAI Presentation Defense Notes

Use this as the concise answer bank for the Amazon SA communication presentation Q&A.

## Core Positioning

SentinelAI is a demo of the Agentic RAG pattern for production incident investigation. It does not automatically prove the final root cause. It identifies evidence-backed investigation leads, explains why a lead is plausible, and keeps the final root-cause decision human-reviewed.

Best one-line framing:

> We should not trust AI because it sounds confident; we should trust it when it can show the evidence behind its answer.

## Safer Claims

- Say: SentinelAI helps engineers avoid stopping at the first visible symptom.
- Say: It is more likely to identify the real root cause because it checks whether evidence explains downstream symptoms.
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

### Why not retrieve everything every time?

That increases cost, latency, and noise. In a real production environment, logs and metrics can be huge. Routing lets simple incidents take a lightweight path while complex or high-impact incidents trigger deeper investigation.

### How does it know when it has enough evidence?

It checks whether the proposed cause explains the full chain of symptoms. For example, payment timeouts can explain database queuing and app latency. If evidence is missing or contradictory, it should report uncertainty instead of claiming a confirmed root cause.

### How do you prevent hallucination?

I would not say hallucination is impossible. The system reduces hallucination risk by grounding answers in real evidence sources and explicitly reporting missing evidence when sources are unavailable.

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

## Strong Closing

My takeaway is simple: in real systems, confidence is not enough. AI should show its evidence, check whether the first answer is only a symptom, and be honest when the evidence is incomplete.
