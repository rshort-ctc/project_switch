# Service Topology

SWITCH uses separated local services:

```text
switch-dashboard -> switch-api -> switch-db
                              -> switch-redis
                              -> switch-qdrant
                              -> local vLLM endpoint
switch-web -> switch-api
switch-api -> Docker/Podman sandbox -> mounted workspace
```

The host dashboard is the `switch-dashboard` Docker service, bound to
`127.0.0.1:3000` by default. It never connects directly to the database, vector
store, sandbox, or model server. It uses backend APIs for every read and mutation.

The network web surface is the `switch-web` Docker service, bound to
`0.0.0.0:3001` by default and limited to chat and repository views. Diagnostics,
approval decisions, audit logs, task timelines, sandbox console access, and
metrics stay on the host dashboard.

Sandbox validation containers mount only the selected workspace. Network is
disabled by default and must not be enabled for normal tests, linting,
typechecking, or builds.
