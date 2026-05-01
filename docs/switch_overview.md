# SWITCH Overview

SWITCH is a Python-based internal operations intelligence platform for support, engineering, site, circuit, vendor, ticket, and escalation workflows. It is designed to help authorized City Tele Coin staff assemble accurate operational context, draft safe communications, and prepare action plans without bypassing human judgment or approval gates.

SWITCH is employer-scoped. It must only ingest, index, retrieve, summarize, or reason over approved City Tele Coin operational data and approved internal knowledge sources.

## Intended Users

- Support operators who need fast, cited context around tickets, outages, sites, and vendors.
- Network and telecom engineers who need facility, circuit, equipment, and provider history.
- Escalation coordinators preparing vendor-facing summaries and follow-up drafts.
- Approved administrators responsible for policy, access, audit, deployment, and retention.

## Supported Workflows

- Site, facility, circuit, and vendor context assembly.
- Ticket and outage history review.
- Troubleshooting procedure lookup and preparation.
- Vendor escalation packet drafting.
- Billing, order, and MARC/order tracking context gathering where applicable.
- Knowledge-base retrieval with provenance.
- Controlled AI-assisted drafting, analysis, and risk explanation.

## Non-Goals

- SWITCH does not autonomously contact vendors, customers, providers, or external systems.
- SWITCH does not make network, telecom, billing, or production system changes without explicit approval.
- SWITCH does not silently use credentials or secrets.
- SWITCH does not ingest unrelated personal, private, or non-company project data.
- SWITCH does not provide uncontrolled automation or unsupervised operational agents.

## Operating Principles

- Draft, do not send.
- Propose, do not apply.
- Prepare, do not mutate.
- Explain risk before action.
- Keep an audit trail for important actions.
- Separate raw evidence from accepted operational truth.
- Require approval gates for external-facing or system-changing work.
- Prefer least-privilege access and scoped context over broad data exposure.

## Human Approval Philosophy

SWITCH may retrieve evidence, summarize records, draft messages, assemble escalation packets, and propose next steps. Human operators remain responsible for reviewing, approving, sending, applying, or rejecting any external-facing or system-changing action.

Approval is not a UI formality. It must bind an authenticated actor, the requested action, the evidence used, the risk explanation, and the final decision into an auditable record.
