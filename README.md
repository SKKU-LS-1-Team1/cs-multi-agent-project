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
# 백엔드는 GCP에 두고 화면만 로컬에서: frontend/.env.example 을 .env.local 로 복사해 VITE_API_TARGET=http://<VM IP>
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

## 사례 학습 지식 그래프 (Neo4j, CSA-69~73)

해결 사례를 제품 · 고장 · 에러코드 · 부품 · 펌웨어 · 문서 절 노드에 이어 Neo4j 에 둔다.
`GRAPH_ENABLED=true` 면 답변 근거의 사례를 그래프에서 찾고(제품 → 에러코드 → 고장 경로로 좁힌 뒤
증상 임베딩 비교), 해결 확정한 사례를 그래프에 학습한다. 꺼져 있거나 Neo4j 에 붙지 못하면 지금의
패턴 DB(`case_patterns`)로 찾는다. 설계: `agents/knowledge_graph.py` 머리말.

적재 순서 (`embed_docs` 다음에 한 번, 다시 돌려도 같은 결과):

```bash
docker compose up -d postgres neo4j
uv run --extra data python -m cs_agent.pipeline.prepare_data
uv run --extra rag --extra llm --extra data python -m cs_agent.pipeline.embed_docs --target all
uv run --extra graph python -m cs_agent.pipeline.build_graph      # --dry-run: 수만 센다
# .env 에 GRAPH_ENABLED=true 를 넣고 서버를 다시 띄운다
```

기준 노드 수: Product 23 · Fault 97 · ErrorCode 45 · Part 19 · Firmware 39 · Case 568 (train).
DB 가 비어 있으면 `data/raw` 의 train 사례로 적재한다 (`--embed-missing` 으로 고장 설명만 임베딩).

비교 평가:

```bash
uv run --all-extras python -m cs_agent.evaluation.case_retrieval --split valid --graph
uv run --all-extras python -m cs_agent.evaluation.run_eval --split valid --no-graph
uv run --all-extras python -m cs_agent.evaluation.run_eval --split valid --graph
```

시연 — Neo4j Browser(http://localhost:7474, `.env` 의 NEO4J 계정)에서 문의 하나의 경로를 본다.
관리자 화면 근거에도 같은 경로가 한 줄로 나온다 (`경로: 제품 → 에러코드 → 고장 → 사례 → 문서 절`).

```cypher
// S100 인버터가 E.OC 로 멈춘 문의: 후보 고장 → 대표 사례 → 인용 문서 절
MATCH (p:Product {id: 'INV-LSLV0075-S100'})<-[:APPLIES_TO]-(f:Fault)-[:SHOWS_CODE]->(e:ErrorCode {id: 'E.OC'})
OPTIONAL MATCH (c:Case {active: true})-[:INSTANCE_OF]->(f)
WHERE (c)-[:ON_PRODUCT]->(p)
OPTIONAL MATCH (c)-[:CITED]->(d:DocSection)
RETURN p, e, f, c, d LIMIT 30
```

해결 후 학습 시연: 비슷한 문의를 해결 확정한 뒤 같은 쿼리를 다시 돌리면 그 사례(`split: 'live'`)가
고장에 붙어 있고, 다음 비슷한 문의의 대표 사례로 올라온다 (CSA-15 피드백 루프).

- CI: GitHub Actions (`.github/workflows/ci.yml`)
- Jira 연동 및 브랜치/커밋 규칙: [docs/JIRA_INTEGRATION.md](docs/JIRA_INTEGRATION.md)
