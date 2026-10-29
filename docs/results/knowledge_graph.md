# 사례 검색: 패턴 DB vs 지식 그래프 (CSA-73)

같은 정답·같은 코드로 잰다 (`evaluation/case_retrieval.py --graph`). 정답 = 문의에 연결된 실제 해결 사례와
같은 고장(fault_id). 사례 DB = train 568건. 초안에 들어가는 사례는 위 2개.
메타데이터: gold = 티켓 라벨, rule = LLM 없는 규칙 추출 (두 경우 같은 수가 나왔다).

| 방식 | valid 128건 1등 | valid 위 2개 안 | test 104건 1등 | test 위 2개 안 |
|---|---|---|---|---|
| 지난 문의 글 임베딩 (처음) | 86 | 94 | 77 | 85 |
| 패턴, 해결 건수 많은 순 (임베딩 없음) | 37 | 56 | 42 | 57 |
| 패턴 설명 임베딩 + 거름 (지금) | 90 | 109 | 83 | 93 |
| **지식 그래프 (이번)** | **90** | **109** | **84** | **95** |

- 2026-10-29 측정, gemini-embedding-2 (1536차원), Neo4j 5.26.2. 원본: `case_retrieval_graph_{valid,test}.json`.
- valid 는 같고 test 는 1등 +1, 위 2개 +2. 설계안에서 예상한 대로 차이는 작다 — 지금 방식도 이미
  제품군·적용 제품·에러코드로 거르고 있어서 후보가 거의 같다. 그래프 쪽 차이는 후보를 먼저 좁힌 뒤
  그 안에서 위 2개를 고르는 것(지금은 전체 상위 8개를 가져온 뒤 거른다)에서 나온다.
- 그래프의 분명한 이득은 점수보다 설명 가능성이다: 근거마다 따라간 경로
  (`제품 → 에러코드 → 고장 → 사례 → 문서 절`)가 남아 관리자 화면에 한 줄로 나오고, 해결 확정 사례가
  바로 그래프에 붙어 다음 문의의 대표 사례가 된다 (운영 사례 → 같은 제품 사례 → 최근 순).
- 전체 K3(`run_eval --graph` / `--no-graph`)는 아직 재지 않았다. 그래프는 사례 근거만 바꾸고 K3 는
  문서 근거로 재므로 K3 차이는 없을 것으로 본다 (답변 초안 차이는 K2 로 본다).

재현:

```bash
docker compose up -d postgres neo4j
uv run --extra data python -m cs_agent.pipeline.prepare_data
uv run --extra rag --extra llm --extra data python -m cs_agent.pipeline.embed_docs --target patterns
uv run --extra rag --extra llm --extra data python -m cs_agent.pipeline.embed_docs --target cases
uv run --extra graph python -m cs_agent.pipeline.build_graph
uv run --all-extras python -m cs_agent.evaluation.case_retrieval --split valid --graph
```
