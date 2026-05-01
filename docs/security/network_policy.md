# Network Policy

The default deployment is local-only. Approved endpoint hosts are configured by
`SWITCH_ALLOWED_LOCAL_HOSTS` and `SWITCH_ALLOWED_NETWORK_CIDRS`.

Public model/vector endpoints are rejected while `SWITCH_LOCAL_ONLY=true`.
Sandbox containers run with `--network none` by default. Network-enabled
validation is not part of the default workflow and requires explicit review.

The backend API, database, Redis, and Qdrant remain bound to loopback by default.
Only the limited web surface should bind to the LAN by default, using
`SWITCH_WEB_BIND=0.0.0.0` and `SWITCH_WEB_PORT=55602`. Host-only routes for
diagnostics, approvals, audit logs, task details, sandbox console use, and
metrics are not exposed by that surface.
