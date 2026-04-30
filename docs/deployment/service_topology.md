# Service Topology

SWITCH uses separated local services:

```text
dashboard -> backend -> postgres
                    -> redis
                    -> qdrant
                    -> local vLLM endpoint
backend -> Docker/Podman sandbox -> mounted workspace
```

The dashboard never connects directly to the database, vector store, sandbox, or
model server. It uses backend APIs for every read and mutation.

Sandbox validation containers mount only the selected workspace. Network is
disabled by default and must not be enabled for normal tests, linting,
typechecking, or builds.
