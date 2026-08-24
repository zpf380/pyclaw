---
name: web-security
description: Web 安全防护技能，用于识别常见 Web 漏洞、检查敏感信息泄漏与加固配置
metadata: {"always": false}
---

# Web Security Skill

## Description
This skill helps assess and harden web-facing code and configuration: spotting
common OWASP Top 10 issues, accidental secret leakage, and weak access control.

## Scope

- **Injection** — SQL/NoSQL injection, command injection, template injection
- **Auth & Session** — hardcoded credentials, weak password hashing, missing token expiry
- **Secret Leakage** — API keys/tokens in source, config files, or commit messages
- **Access Control** — admin-only operations reachable by member role, IDOR
- **Input Validation** — missing validation on paths, uploads, URLs

## Procedure

1. Locate the entry points: channels, HTTP handlers, CLI commands, scheduled jobs.
2. Trace data flow from untrusted input to sinks (queries, `exec`, filesystem).
3. For each risk, report: severity, affected file/line, exploit sketch, and fix.

## Checklist

- [ ] No secrets or API keys in code or config that ships
- [ ] Privileged operations (exec/spawn/cron) gated by role
- [ ] User-controlled paths validated against traversal (`..`, absolute paths)
- [ ] Auth tokens hashed at rest and expired properly

## Best Practices
1. Report risks with a concrete reproduction, not vague advice.
2. Default to "deny by default" for new privileged surfaces.
3. Do not attempt exploitation beyond safe verification in this workspace.
