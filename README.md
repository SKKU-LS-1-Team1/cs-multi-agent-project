<div align="center">

# 🤖 C/S Multi-Agent

**해외 고객상담 AI 에이전트** · 15개 언어 문의를 분류하고 근거를 찾아 답변 초안까지 만든 뒤 상담원 검토로 넘긴다.

[![CI](https://github.com/SKKU-LS-1-Team1/cs-multi-agent-project/actions/workflows/ci.yml/badge.svg)](https://github.com/SKKU-LS-1-Team1/cs-multi-agent-project/actions/workflows/ci.yml)
[![Deploy](https://github.com/SKKU-LS-1-Team1/cs-multi-agent-project/actions/workflows/deploy.yml/badge.svg)](https://github.com/SKKU-LS-1-Team1/cs-multi-agent-project/actions/workflows/deploy.yml)
![Python](https://img.shields.io/badge/python-3.11-3776AB?logo=python&logoColor=white)

[구조](docs/ARCHITECTURE.md) · [Jira 작업별 코드 위치](docs/JIRA_MAP.md) · [브랜치/커밋 규칙](docs/JIRA_INTEGRATION.md) · [시험 결과](docs/results/results.md)

</div>

---

## 🧰 기술 스택

| 영역 | 사용 기술 |
|:--|:--|
| **AI · 에이전트** | ![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?style=for-the-badge&logo=langgraph&logoColor=white) ![LangChain](https://img.shields.io/badge/LangChain-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white) ![Google Gemini](https://img.shields.io/badge/Google%20Gemini-8E75B2?style=for-the-badge&logo=googlegemini&logoColor=white) ![Langfuse](https://img.shields.io/badge/Langfuse-0A0A0A?style=for-the-badge&logoColor=white) |
| **백엔드** | ![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white) ![Pydantic](https://img.shields.io/badge/Pydantic-E92063?style=for-the-badge&logo=pydantic&logoColor=white) ![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white) |
| **데이터 · 검색** | ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white) ![pgvector](https://img.shields.io/badge/pgvector-336791?style=for-the-badge&logo=postgresql&logoColor=white) ![Redis](https://img.shields.io/badge/Redis-FF4438?style=for-the-badge&logo=redis&logoColor=white) |
| **프론트엔드** | ![React](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB) ![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white) ![Vite](https://img.shields.io/badge/Vite-9135FF?style=for-the-badge&logo=vite&logoColor=white) ![Tailwind CSS](https://img.shields.io/badge/Tailwind%20CSS-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white) ![shadcn/ui](https://img.shields.io/badge/shadcn%2Fui-000000?style=for-the-badge&logo=shadcnui&logoColor=white) |
| **인프라 · 배포** | ![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white) ![Nginx](https://img.shields.io/badge/Nginx-009639?style=for-the-badge&logo=nginx&logoColor=white) ![Google Cloud](https://img.shields.io/badge/Google%20Cloud-4285F4?style=for-the-badge&logo=googlecloud&logoColor=white) ![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white) |
| **개발 도구 · 협업** | ![uv](https://img.shields.io/badge/uv-DE5FE9?style=for-the-badge&logo=uv&logoColor=white) ![Ruff](https://img.shields.io/badge/Ruff-D7FF64?style=for-the-badge&logo=ruff&logoColor=black) ![Pytest](https://img.shields.io/badge/Pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white) ![Jira](https://img.shields.io/badge/Jira-0052CC?style=for-the-badge&logo=jira&logoColor=white) |

---

## 🔀 처리 흐름

LangGraph 그래프가 순서를 정하고, LLM은 분류·추출, 요청문·답변 작성, 근거 검증에만 쓴다.
자세한 내용은 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

```
① 접수 ─┬ ② 분류 ─┐
        ├ ③ 추출 ─┼→ ⑤ 규칙 처리 → ⑥ 분기 ─┬ 안전 → 사람 큐
        └ ④ 검색 ─┘                      ├ 차단성 누락 → ⑦ 추가정보 요청문 → 상담원 검토
                                         └ 정상 → ⑧ 근거 확정 → ⑨ 답변 작성 → ⑩ 자동 점검
```

| 구성 | 역할 |
|:--|:--|
| **PostgreSQL + pgvector** | 문의·답변·처리 기록 저장과 벡터 검색(문서 조각 `doc_chunks`, 해결 사례 `resolution_cases`) |
| **Redis** | LLM 응답 캐시 · 호출 제한 · 챗봇 세션 |
| **Gemini** | 답변·요청문 작성, 다국어 임베딩(`gemini-embedding-2`, 1536차원) |
| **Langfuse** | LLM 호출 추적 |

---

## 🚀 시작하기

[uv](https://docs.astral.sh/uv/getting-started/installation/) 설치 후:

```bash
uv sync
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

`src/cs_agent/` 의 .py 파일마다 맨 위 주석에 담당·Jira 키·할 일이 적혀 있다.
누가 어느 파일을 맡는지는 [docs/JIRA_MAP.md](docs/JIRA_MAP.md).

### 실행

```bash
uv run uvicorn cs_agent.main:app --reload     # 백엔드 http://localhost:8000/docs
cd frontend && npm install && npm run dev     # 화면 http://localhost:5173
cp .env.example .env && docker compose up --build   # 전체 구성 http://localhost
```

> [!TIP]
> 백엔드는 GCP에 두고 화면만 로컬에서 띄우려면 `frontend/.env.example` 을 `.env.local` 로 복사해
> `VITE_API_TARGET=http://<VM IP>` 로 바꾼다.

---

## 🗂️ 데이터

원천 데이터(`CS_AI_Agent_Training_Data_v1`, 교육용 가상 데이터)는 `data/raw/` 에 있다.

| 경로 | 내용 | 적재 위치 |
|:--|:--|:--|
| `cs_tickets_resolution_v1.xlsx`<br><sub>(같은 내용 `tickets.csv`·`tickets.jsonl`·`resolution_cases.csv`)</sub> | 상담 이력 4,000건, 해결 사례 800건 | 정제·분리(CSA-17) 후 임베딩 → `resolution_cases` (CSA-18) |
| `docs/` | 제품 23개의 데이터시트·설치·트러블슈팅·유지보수 문서와 FAQ | 절 단위로 잘라 임베딩 → `doc_chunks` (CSA-18) |
| `data/ref/` | 원본 기준표 (`ref/` 에서 옮김) | 코드에서 직접 조회 |

가공 결과(`data/processed/`)는 git에 올리지 않고 각자 만든다. 벡터는 PostgreSQL 안에 있다.

상담 데이터 정제와 분리는 다음 명령으로 실행한다. `data/processed/` 에
`tickets_train.parquet`, `tickets_valid.parquet`, `tickets_test.parquet`,
`cases_seed.parquet`, `classifier_train.parquet` (`text` / `category_code`)가 생성된다.

```bash
uv run --extra data python -m cs_agent.pipeline.prepare_data
```

---

## 🕸️ 사례 학습 지식 그래프 (Neo4j)

CSA-69~73.

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

---

## ⚙️ CI · 배포

| 워크플로 | 하는 일 |
|:--|:--|
| [`ci.yml`](.github/workflows/ci.yml) | ruff 린트 · 포맷 검사 · pytest |
| [`deploy.yml`](.github/workflows/deploy.yml) | `main` 푸시 시 GCP VM에 SSH로 접속해 `docker compose` 로 다시 띄움 |
| [`jira-key-check.yml`](.github/workflows/jira-key-check.yml) | PR 제목·브랜치 이름의 Jira 키(`CSA-n`) 확인 ([규칙](docs/JIRA_INTEGRATION.md)) |
