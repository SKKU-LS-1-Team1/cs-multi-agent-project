# cs-multi-agent-project

C/S 멀티 에이전트 시스템.

## 개발

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && pytest
```

- CI: GitHub Actions (`.github/workflows/ci.yml`)
- Jira 연동 및 브랜치/커밋 규칙: [docs/JIRA_INTEGRATION.md](docs/JIRA_INTEGRATION.md)
