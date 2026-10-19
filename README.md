# cs-multi-agent-project

해외 고객상담 AI 에이전트 (C/S 멀티 에이전트 시스템).

FastAPI + LangGraph 백엔드, React 화면, PostgreSQL(+pgvector) · Redis, Langfuse, Docker Compose.

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

원천 데이터(`CS_AI_Agent_Training_Data_v1`, 교육용 가상 데이터)는 `data/raw/` 에 있다.

- `cs_tickets_resolution_v1.xlsx` (같은 내용 `tickets.csv`·`tickets.jsonl`·`resolution_cases.csv`):
  상담 이력 4,000건과 해결 사례 800건. 정제·분리(CSA-17) 후 임베딩해서 PostgreSQL `resolution_cases` 에 넣는다(CSA-18).
- `docs/`: 제품 23개의 데이터시트·설치·트러블슈팅·유지보수 문서와 FAQ. 절 단위로 잘라 임베딩해서 PostgreSQL `doc_chunks` 에 넣는다(CSA-18).
- 원본 기준표(`ref/`)는 `data/ref/` 로 옮겼다.
- 가공 결과(`data/processed/`)는 git에 올리지 않고 각자 만든다. 벡터는 PostgreSQL 안에 있다.

상담 데이터 정제와 분리는 다음 명령으로 실행한다. `data/processed/`에
`tickets_train.parquet`, `tickets_valid.parquet`, `tickets_test.parquet`,
`cases_seed.parquet`, `classifier_train.parquet` (`text` / `category_code`)가 생성된다.

```bash
uv run --extra data python -m cs_agent.pipeline.prepare_data
```

- CI: GitHub Actions (`.github/workflows/ci.yml`)
- Jira 연동 및 브랜치/커밋 규칙: [docs/JIRA_INTEGRATION.md](docs/JIRA_INTEGRATION.md)
