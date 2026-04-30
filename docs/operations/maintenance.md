# Maintenance

- Review `/audit` and dashboard audit logs weekly.
- Verify backups and restore at least monthly.
- Rotate container logs with Compose `json-file` limits or host logrotate.
- Rebuild indexes after large repository moves or embedding model changes.
- Keep local sandbox images patched and pinned.
- Prune stale `.switch/artifacts` only after confirming audit and patch retention
  requirements.
- Keep `SWITCH_LOCAL_ONLY=true` and review any exception as an incident.
