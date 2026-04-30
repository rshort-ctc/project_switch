# Operator Guide

## Start

```bash
docker compose up --build -d
curl http://127.0.0.1:8000/health/details
```

## Register And Index A Repo

```bash
switch repo add /workspaces/example --name example
switch repo list
switch repo index <repository_id>
switch repo status <repository_id>
```

## Ask A Repo Question

```bash
switch ask <repository_id> "Where is authentication handled?"
```

## Create And Inspect A Task

```bash
switch task create <repository_id> "Fix failing auth test" --created-by <user_id>
switch task status <task_id>
switch task logs <task_id>
switch task diff <task_id>
switch validation results <task_id>
```

## Approve Or Deny

```bash
switch approve <approval_id> --user <user_id> --note "reviewed diff"
switch deny <approval_id> --user <user_id> --note "unsafe request"
```

Review the dashboard approval queue before deciding. Risk badges and diff
summaries are operator inputs, not replacements for code review.

## Run Evaluations

```bash
scripts/eval
scripts/eval --json
```
