# Backup And Restore

## Durable State

- PostgreSQL: authoritative task, run, approval, audit, policy, validation state
- Qdrant: vector index data, rebuildable from repos but expensive to recreate
- Workspaces and `.switch` artifacts: local patch, validation, and report artifacts
- Redis: cache/queue state, generally disposable unless configured otherwise

## Backup

```bash
scripts/backup
```

The script writes a timestamped directory under `backups/` with a PostgreSQL
custom dump and workspace archive when present.

## Restore

```bash
BACKUP_DIR=backups/<timestamp> make restore
```

After restore:

```bash
docker compose restart backend dashboard
curl http://127.0.0.1:55600/health/details
switch repo list
scripts/eval
```

Test restores periodically. A backup that has never been restored is not a
verified backup.
