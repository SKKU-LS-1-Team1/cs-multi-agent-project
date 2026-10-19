# 구조

기획서 v10 9장·9.1·9.2와 `analysis/agent-architecture/에이전트_구조_제안.md` 를 파일 구조로 옮긴 골격이다.

## 처리 흐름 (LangGraph, `src/cs_agent/graph/builder.py`)

슈퍼바이저 = 코드가 순서를 정한 그래프. LLM은 분류·추출(Jev), 요청문·답변 작성(Gemini), 근거 검증에만 쓴다.

```
① 접수 ─┬ ② 분류 ─┐
        ├ ③ 추출 ─┼→ ⑤ 규칙 처리 → ⑥ 분기 ─┬ 안전 → 사람 큐
        └ ④ 검색 ─┘                      ├ 차단성 누락 → ⑦ 추가정보 요청문 → 상담원 검토
                                         └ 정상 → ⑧ 근거 확정 → ⑨ 답변 작성 → ⑩ 자동 점검
⑩ 통과 → 상담원 검토 (interrupt) / 실패 → ⑨ 재작성 (최대 2회) / 초과 → 보류 → 상담원 검토
상담원 검토 → 승인 · 수정 후 승인 · AI 재작성 · 추가정보 요청 · 전문부서 이관 · 반려
해결 확정 → 사례 DB 저장 (기획서 7.1)
```

상담원 검토 지점에서 그래프가 멈추고(체크포인트), `POST /api/tickets/{id}/action` 이 `Command(resume=...)` 로 같은 그래프를 이어서 돌린다.

## 저장소와 RAG

| 저장소 | 담는 것 |
|---|---|
| PostgreSQL | 문의·답변·상담원 처리 기록·챗봇 대화 (CSA-24) **+ 벡터 검색** (pgvector) |
| Redis | LLM 응답 캐시 · 호출 제한 · 챗봇 세션 (CSA-45) |
| `data/ref/*.csv` | 기준표. 사양값·보증기간·에러코드처럼 정확히 맞아야 하는 값은 벡터가 아니라 여기서 조회 |

- **벡터 DB = PostgreSQL + pgvector** (ChromaDB 대신). 저장소가 하나라 운영·백업이 단순하고, 사례 원본과
  벡터가 같은 행에 있어 SQL 필터(제품·유형·data_split)와 벡터 검색을 한 쿼리로 한다.
  - `doc_chunks`: 공식 문서·FAQ·정책을 절 단위로 (약 900조각). 답변 근거.
  - `resolution_cases.embedding`: 해결 사례 (train 연결 568건 + 운영 중 해결 건). 참고·문장 본보기.
- **임베딩 = `gemini-embedding-2`, 1536차원** (`EMBEDDING_MODEL`·`EMBEDDING_DIM`). 15개 언어 문의로
  영어 문서를 찾는 다국어 모델. task_type(검색용/문서용 구분)은 이 모델이 무시하므로 적재·검색에
  같은 호출을 쓴다. 글 여러 개를 한 번에 보내면 벡터 1개로 합쳐지므로 글마다 따로 부른다.
  모델·차원을 바꾸면 전부 다시 적재한다.

## 폴더

| 폴더 | 내용 |
|---|---|
| `src/cs_agent/graph/` | 상태(`TicketState`)와 그래프 조립 |
| `src/cs_agent/agents/` | 문의 분석 · 추가정보 요청 · 지식 검색 · 답변 작성 · 자동 점검 · 사례 저장 |
| `src/cs_agent/chatbot/` | 챗봇 대화 · 화면 이동 · 문의서 작성 · 문의 전환 |
| `src/cs_agent/rules/` | 기준표 로더 · 우선순위/부서/필수정보 · SLA |
| `src/cs_agent/llm/` | 모델 분기 (Jev 판단 / Gemini 작성) · Langfuse |
| `src/cs_agent/api/` | FastAPI 라우터 (`/api/tickets`, `/api/chat`, `/api/products`, `/api/dashboard`) |
| `src/cs_agent/db/` | PostgreSQL 모델(벡터 테이블 포함) · SQL 쿼리 |
| `src/cs_agent/cache/` | Redis (캐시 · 호출 제한 · 챗봇 세션) |
| `src/cs_agent/pipeline/` | 데이터 정제 · 문서 청킹/임베딩 · mock 데이터 |
| `src/cs_agent/evaluation/` | KPI 계산 · 시험 문의 평가 |
| `data/ref/` | 기준표 CSV (아래 참고) |
| `frontend/` | React (고객 화면 · 관리자 화면) |
| `infra/` | Nginx · GCP 안내 |

## 지금 상태

처리 흐름은 처음부터 끝까지 돈다: `POST /api/tickets` → 그래프 → 상담원 검토 대기 →
`POST /api/tickets/{id}/action` → 승인·재작성·추가정보 요청·이관·반려 → `/resolve` → 사례 저장.
아직 구현되지 않은 에이전트(분류·추출·검색·답변·점검·요청문)는 `graph/defaults.py` 의 임시 구현이
자리를 채운다. 담당자가 `agents/*.py` 를 만들면 `graph/builder.py` 의 `GraphDeps` 기본값만 바꾼다.
저장은 아직 메모리(서버를 다시 켜면 사라짐)이고, DB(CSA-24)가 오면 PostgreSQL 로 바꾼다.

주석만 있는 파일은 맨 위 주석에 담당·Jira 키·할 일·완료 기준·참고 문서가, 아래 "만들 것" 주석에
다른 파일이 부를 함수·클래스 모양이 적혀 있다. 이름과 모양은 그대로 맞춰서 구현한다.
`domain.py`·`schemas.py`·`graph/state.py` 는 팀이 같이 쓰는 값이라 바꿀 때는 팀에 알린다.

## 기준표 (`data/ref/`)

받은 원본 기준표(`CS_AI_Agent_Training_Data_v1/ref/`)를 그대로 둔다. 파일별 내용과 읽는 방법은
`src/cs_agent/rules/tables.py` 맨 위 주석에 있다.
`navigation_rules.csv`(기획서 5.4, CSA-33)와 `family_divisions.csv`(제품군 → 대분류, CSA-19)는
원본에 없어서 직접 만든 표다. 기준표와 tickets 대조 검수는
`uv run python -m cs_agent.rules.tables` 로 한다.
