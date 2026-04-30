# Admin Configuration

Administrative settings are environment-driven and should be reviewed before
deployment:

- `SWITCH_ADMIN_CONTACT`: local owner for incidents and deployment questions
- `SWITCH_AUDIT_RETENTION_DAYS`: minimum audit retention window
- `SWITCH_DEFAULT_PERMISSION_LEVEL`: conservative default permission level
- `SWITCH_PROTECTED_BRANCHES`: branches agents must not modify directly
- `SWITCH_ALLOWED_LOCAL_HOSTS`: approved local service hostnames
- `SWITCH_ALLOWED_NETWORK_CIDRS`: approved local network ranges

Changing these settings should be treated as an administrative action. Record
the operator, reason, timestamp, old value, and new value in your local change
management system.
