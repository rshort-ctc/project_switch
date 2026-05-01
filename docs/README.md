# SWITCH Documentation

SWITCH is operated as a local-first internal operations intelligence platform.
Start with the guide for your role:

- Operators: [local production deployment](deployment/local_production.md) and
  [operator guide](operations/operator_guide.md)
- Administrators: [environment variables](deployment/environment_variables.md),
  [admin configuration](deployment/admin_config.md),
  [backup and restore](operations/backup_restore.md), and
  [security checklist](security/production_checklist.md)
- Model operators: [local model configuration](models/local_model_configuration.md)
- Developers: [onboarding](development/onboarding.md), [local setup](development/local_setup.md),
  [evaluation harness](development/evaluation.md), and
  [VS Code/Cursor extension](extensions/vscode_cursor.md)
- Security reviewers: [security model](architecture/security_model.md),
  [approval policy](security/approval_policy.md),
  [network policy](security/network_policy.md), and [audit review](security/audit_review.md)
- Retention owners: [logging and retention](operations/logging_retention.md)

The core deployment must remain local-only unless an administrator explicitly
documents and approves an exception.
