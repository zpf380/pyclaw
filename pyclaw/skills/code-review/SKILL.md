---
name: code-review
description: 系统化代码审查技能，从正确性、安全性、性能、可维护性四个维度审查代码并给出可执行建议
metadata: {"always": false}
---

# Code Review Skill

## Description
This skill enables systematic code review. Given a file or code snippet, analyze it
across four dimensions and return prioritized, actionable findings.

## Review Dimensions

1. **Correctness** — logic errors, off-by-one, race conditions, error handling gaps
2. **Security** — injection, path traversal, secrets in logs, unsafe deserialization
3. **Performance** — avoidable allocations, N+1 queries, blocking calls in async paths
4. **Maintainability** — naming, dead code, duplicated logic, missing types/comments

## Procedure

1. Identify the code language and read the full file via `read_file`.
2. Review each dimension in order, collecting concrete findings with line references.
3. For each finding, state: severity (high/medium/low), the affected lines, and a concrete fix.
4. Summarize with a prioritized list — fix high-severity issues first.

## Output Format

```
## Findings
- [高] <file>:<line> <问题描述>
  修复建议: <具体改法>

## Summary
<总体评价与优先级建议>
```

## Best Practices
1. Never rewrite code without explaining *why* the change is needed.
2. Prefer suggesting small, testable changes over large refactors.
3. When unsure about intent, ask instead of assuming.
