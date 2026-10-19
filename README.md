# cs-multi-agent-project

해외 고객상담 AI 에이전트 (C/S 멀티 에이전트 시스템).

FastAPI + LangGraph 백엔드, React 화면, PostgreSQL · Redis · ChromaDB, Langfuse, Docker Compose.

- 구조: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Jira 작업별 코드 위치: [docs/JIRA_MAP.md](docs/JIRA_MAP.md)

## 개발

[uv](https://docs.astral.sh/uv/getting-started/installation/) 설치 후:

```bash
uv sync
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

`src/cs_agent/` 의 .py 파일은 아직 주석만 있다. 파일마다 맨 위 주석의 할 일을 보고 시작한다.
누가 어느 파일을 맡는지는 [docs/JIRA_MAP.md](docs/JIRA_MAP.md).

구현 후 실행:

```bash
uv run uvicorn cs_agent.main:app --reload     # 백엔드 http://localhost:8000/docs
cd frontend && npm install && npm run dev     # 화면 http://localhost:5173
cp .env.example .env && docker compose up --build   # 전체 구성 http://localhost
```

원천 데이터(`CS_AI_Agent_Training_Data_v1`)는 git에 올리지 않는다. `data/raw/` 에 풀어 두면
`data/raw/docs` 를 검색 근거로 쓴다.

- CI: GitHub Actions (`.github/workflows/ci.yml`)
- Jira 연동 및 브랜치/커밋 규칙: [docs/JIRA_INTEGRATION.md](docs/JIRA_INTEGRATION.md)
