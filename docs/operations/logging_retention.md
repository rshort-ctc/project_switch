# Logging And Retention

Container logs use Compose `json-file` limits:

```bash
SWITCH_LOG_MAX_SIZE=10m
SWITCH_LOG_MAX_FILES=5
```

For host-managed logs, use `deploy/logrotate/switch` as a starting point and
adjust the path to your local log directory.

Audit retention is configured with:

```bash
SWITCH_AUDIT_RETENTION_DAYS=365
```

Audit events are operational records. Do not delete them casually. If local law
or company policy requires pruning, export a backup first and document the
administrator, reason, timestamp, and retention window.
