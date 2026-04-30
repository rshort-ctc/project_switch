# Approval Policy

Agents do not self-approve. Risky or mutating operations must create an
approval request and pause until a human decision is recorded.

Approval-gated actions include:

- applying patches to a workspace
- running validation commands
- touching high-risk files
- exporting patches
- creating branch artifacts
- any future push or PR operation

Denied approvals stop the current action path. Operators should use denial notes
that explain the risk or missing context.

Current limitation: approval APIs identify approvers by local user id supplied to
the backend. Production deployments should place SWITCH behind internal access
controls until role-based authentication is added.
