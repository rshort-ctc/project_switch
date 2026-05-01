# City Tele Coin Operational Scope

This document defines the intended City Tele Coin operations domain for future SWITCH phases. It is a scope and design baseline only; Phase 0 does not implement these entities.

## Sites and Facilities

Sites and facilities represent physical operating locations, service points, or managed locations relevant to support and engineering work.

Likely fields include site identifier, name, address, facility type, status, contacts, region, timezone, supported services, related tickets, active outages, installed equipment, circuits, and notes.

Relationships:

- A site can have many circuits.
- A site can have many equipment records.
- A site can have many tickets and outages.
- A site can be linked to procedures, escalation contacts, and supporting documentation.

## Circuits

Circuits represent access, transport, SIP, DIA, ASE/ADI, or other connectivity services used by a site or operational system.

Likely fields include circuit ID, provider circuit ID, service type, bandwidth, handoff, status, install date, disconnect date, billing account, demarc notes, provider, site, orders, and outage history.

Relationships:

- A circuit belongs to a site or operational service.
- A circuit belongs to a provider or vendor.
- A circuit may map to orders, billing records, outage records, tickets, and escalation packets.

## Vendors

Vendors include LECs, ISPs, carriers, service providers, equipment vendors, and support partners. Examples include AT&T ASE/ADI, Lumen, Sparklight, Fusion, and other approved providers.

Likely fields include vendor name, account numbers, escalation contacts, support portals, NOC contacts, contract notes, service types, order references, and communication history.

Relationships:

- A vendor provides circuits, equipment support, orders, billing documents, and escalation channels.
- A vendor may be referenced by tickets, outages, and escalation packets.

## Equipment

Equipment includes Adtran gateways, Ciena equipment, EdgeRouters, SIP trunk handoff equipment, and other managed telecom/network devices.

Likely fields include equipment type, vendor, model, serial number, management address, site, circuit association, support status, firmware notes, configuration references, and maintenance history.

Relationships:

- Equipment is installed at a site.
- Equipment may terminate or support one or more circuits.
- Equipment may be referenced by tickets, outages, troubleshooting procedures, and approved change records.

## Tickets

Tickets represent support or engineering cases, whether internal or provider-facing.

Likely fields include ticket ID, source system, requester, status, priority, site, circuit, vendor, equipment, outage linkage, timeline, summary, evidence, owner, next action, and closure notes.

Relationships:

- A ticket can reference a site, circuit, vendor, equipment item, outage, order, or billing record.
- A ticket can contribute evidence to escalation packets and accepted operational truth.

## Outages

Outages represent service-impacting incidents or suspected incidents.

Likely fields include outage ID, affected sites, affected circuits, provider, start time, restore time, symptoms, suspected cause, confirmed cause, impact, evidence, related tickets, and post-incident notes.

Relationships:

- An outage can affect multiple sites and circuits.
- An outage can contain many tickets and escalation records.
- An outage can produce accepted operational learnings and knowledge-base updates.

## Escalations

Escalations represent controlled preparation for vendor, carrier, internal engineering, or management follow-up.

An escalation packet should compile evidence, relevant tickets, outage history, circuit details, provider details, contacts, troubleshooting already performed, current ask, risk notes, and a proposed draft communication.

Escalations must remain draft-only until an authorized human reviews and approves any external-facing message or action.

## Orders

Orders include new service orders, disconnects, changes, upgrades, MACD activity, and MARC/order tracking where applicable.

Likely fields include order ID, vendor order number, site, circuit, service type, requested date, due date, status, dependencies, billing linkage, contacts, milestones, and related tickets.

Relationships:

- An order may create, change, or disconnect a circuit.
- An order may be linked to vendor records, billing documents, and support tickets.

## Billing and Supporting Documentation

Billing and supporting documents include invoices, account references, service records, order confirmations, provider emails, PDFs, knowledge-base articles, and internal notes.

These records require classification before indexing. Sensitive billing, customer, payment-adjacent, facility, or account data must not be exported or exposed without policy controls.

## Knowledge Base

The knowledge base should contain approved internal procedures, troubleshooting guides, known issues, vendor escalation instructions, equipment notes, and operational runbooks.

Knowledge-base content can support context assembly, but retrieval alone is not operational truth. Accepted operational truth must come from approved records, validated evidence, or courthouse verdicts.

## Approval-Gated Actions

Approval-gated actions include sending vendor communications, changing network or telecom configuration, updating operational records, exporting sensitive data, deleting records, using credentials, or invoking external systems.

SWITCH may prepare drafts, explain risks, and assemble evidence. Human operators must approve external-facing or system-changing actions before execution.
