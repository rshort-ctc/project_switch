# Production Security Checklist

- [ ] `SWITCH_LOCAL_ONLY=true`
- [ ] No cloud LLM API keys in `.env`
- [ ] Model endpoint is localhost or approved local service hostname
- [ ] Database password changed from example value
- [ ] Protected branches configured
- [ ] Sandbox network disabled by default
- [ ] Sandbox CPU, memory, timeout, and disk limits configured
- [ ] Dangerous commands denied by tests
- [ ] Approval queue tested with approve and deny decisions
- [ ] Audit log visible in API/dashboard
- [ ] Backup and restore tested
- [ ] Secret files excluded from indexing
- [ ] Generated reports and backups ignored by git
- [ ] Push/merge automation disabled
