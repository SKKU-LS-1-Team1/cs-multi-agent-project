# cs-multi-agent-project

C/S 멀티 에이전트 시스템.

## 개발

[uv](https://docs.astral.sh/uv/getting-started/installation/) 설치 후:

```bash
uv sync
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

- CI: GitHub Actions (`.github/workflows/ci.yml`)
- Jira 연동 및 브랜치/커밋 규칙: [docs/JIRA_INTEGRATION.md](docs/JIRA_INTEGRATION.md)
