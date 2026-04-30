# Network Policy

The default deployment is local-only. Approved endpoint hosts are configured by
`SWITCH_ALLOWED_LOCAL_HOSTS` and `SWITCH_ALLOWED_NETWORK_CIDRS`.

Public model/vector endpoints are rejected while `SWITCH_LOCAL_ONLY=true`.
Sandbox containers run with `--network none` by default. Network-enabled
validation is not part of the default workflow and requires explicit review.
