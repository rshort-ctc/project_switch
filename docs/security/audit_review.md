# Audit Review

Audit events should exist for:

- repository registration
- task creation and status changes
- agent run creation and status changes
- approval requests and decisions
- policy evaluations
- tool executions
- patch generation/application
- validation runs

Missing audit records for mutating actions should be treated as a deployment or
policy defect.
