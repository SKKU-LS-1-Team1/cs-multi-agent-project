# LLM 호출 기록 (local · 2026-09-29 ~ 2026-10-29)

- 실제 LLM 호출 4116건 (전체 기록 4191건, fake·합성 제외)
- 지연·토큰은 캐시가 아닌 호출만. 지연 단위 초, 비용 USD (Langfuse 모델 단가)

## 단계별 지연 (느린 순)

| task | model | calls | cache_hits | latency_p50_s | latency_p95_s | over_60s | input_tokens_avg | output_tokens_avg | cost_usd |
|---|---|---|---|---|---|---|---|---|---|
| info_request | Gemini | 57 | 0 | 5.552 | 9052.058 | 5 | 148.789 | 486.228 | 0.110 |
| classify_secondary | Gemini | 36 | 0 | 5.061 | 599.074 | 2 | 1297.639 | 468.278 | 0.098 |
| translate_reply | Gemini | 17 | 0 | 18.975 | 46.976 | 1 | 693.118 | 2731.294 | 0.183 |
| extract_fields | Gemini | 422 | 0 | 7.221 | 41.486 | 14 | 3362.607 | 961.017 | 2.585 |
| draft | Gemini | 845 | 12 | 10.366 | 19.446 | 8 | 1773.882 | 1245.843 | 5.072 |
| chat_answer | Gemini | 52 | 11 | 6.367 | 17.489 | 0 | 834.577 | 853.173 | 0.199 |
| inquiry_summary | Gemini | 37 | 4 | 8.968 | 15.683 | 0 | 337.838 | 1091.838 | 0.161 |
| extract_urgency | Gemini | 89 | 3 | 5.707 | 14.094 | 0 | 349.270 | 571.416 | 0.214 |
| escalation_request | Gemini | 177 | 1 | 8.147 | 13.036 | 0 | 1332.492 | 738.847 | 0.667 |
| translate_ko | Gemini | 62 | 7 | 6.191 | 12.994 | 0 | 465.823 | 716.694 | 0.188 |
| translate_info_request | Gemini | 3 | 0 | 9.623 | 12.337 | 0 | 141.000 | 1094.333 | 0.013 |
| verify_grounding | Gemini | 121 | 9 | 5.380 | 12.291 | 0 | 1465.264 | 643.198 | 0.425 |
| classify | Gemini | 28 | 0 | 7.047 | 12.142 | 0 | 1983.250 | 597.893 | 0.104 |
| progress_notice | Gemini | 1 | 0 | 9.798 | 9.798 | 0 | 543.000 | 1110.000 | 0.005 |
| draft_eval_judge_calibration | Gemini | 4 | 0 | 5.614 | 8.298 | 0 | 1497.250 | 527.500 | 0.012 |
| specialist_followup | Gemini | 1 | 0 | 7.773 | 7.773 | 0 | 1353.000 | 763.000 | 0.004 |
| chat_handoff | Gemini | 19 | 24 | 6.096 | 7.318 | 0 | 38.526 | 430.421 | 0.031 |
| draft_eval_judge | Gemini | 591 | 0 | 4.839 | 7.312 | 0 | 2744.193 | 390.535 | 2.082 |
| review_translation_smoke | Gemini | 3 | 0 | 4.797 | 6.161 | 0 | 755.667 | 518.667 | 0.008 |
| chat_intent | Gemini | 10 | 3 | 3.811 | 5.267 | 0 | 252.700 | 225.800 | 0.010 |
| verify_specialist_followup | Gemini | 1 | 0 | 4.299 | 4.299 | 0 | 1181.000 | 314.000 | 0.002 |
| customer_send_qc | Gemini | 8 | 0 | 2.776 | 4.097 | 0 | 732.125 | 66.625 | 0.006 |
| ping | Gemini | 3 | 0 | 3.509 | 3.645 | 0 | 4.000 | 66.333 | 0.001 |
| verify_specialist_followup | Jev | 1 | 0 | 0.397 | 0.397 | 0 | 1494.000 | 31.000 | 0.000 |
| classify | Jev | 355 | 19 | 0.211 | 0.346 | 0 | 2703.146 | 99.065 | 0.040 |
| classify_secondary | Jev | 266 | 7 | 0.190 | 0.291 | 1 | 1583.688 | 98.079 | 0.018 |
| extract_urgency | Jev | 358 | 20 | 0.182 | 0.272 | 3 | 643.483 | 71.313 | 0.010 |
| verify_grounding | Jev | 289 | 0 | 0.202 | 0.270 | 0 | 1408.623 | 31.000 | 0.017 |
| chat_intent | Jev | 92 | 25 | 0.182 | 0.260 | 0 | 494.489 | 44.641 | 0.002 |
| verify_progress_notice | Jev | 2 | 0 | 0.220 | 0.250 | 0 | 1033.000 | 31.000 | 0.000 |
| extract_return_defect | Jev | 16 | 0 | 0.191 | 0.221 | 0 | 919.312 | 42.688 | 0.001 |
| chat_decision | Jev | 2 | 3 | 0.161 | 0.162 | 0 | 429.000 | 33.000 | 0.000 |

## Jev vs Gemini (둘 다 불린 판단 단계)

Gemini 줄의 fallback_* = Jev 확신도가 낮거나 실패해서 Gemini 로 넘어간 호출 수, Jev 줄의 handed_over_rate = 그 합 / Jev 호출 수.

| task | model | calls | fallback_low_confidence | fallback_error | handed_over_rate | latency_p50_s | latency_p95_s | cost_per_call_usd |
|---|---|---|---|---|---|---|---|---|
| chat_intent | Gemini | 10 | 10 | 0 | - | 3.811 | 5.267 | 0.001 |
| chat_intent | Jev | 92 | 0 | 0 | 0.109 | 0.182 | 0.260 | 0.000 |
| classify | Gemini | 28 | 24 | 3 | - | 7.047 | 12.142 | 0.004 |
| classify | Jev | 355 | 0 | 0 | 0.076 | 0.211 | 0.346 | 0.000 |
| classify_secondary | Gemini | 36 | 36 | 0 | - | 5.061 | 599.074 | 0.003 |
| classify_secondary | Jev | 266 | 0 | 0 | 0.135 | 0.190 | 0.291 | 0.000 |
| extract_urgency | Gemini | 89 | 89 | 0 | - | 5.707 | 14.094 | 0.002 |
| extract_urgency | Jev | 358 | 0 | 0 | 0.249 | 0.182 | 0.272 | 0.000 |
| verify_grounding | Gemini | 121 | 93 | 0 | - | 5.380 | 12.291 | 0.004 |
| verify_grounding | Jev | 289 | 0 | 0 | 0.322 | 0.202 | 0.270 | 0.000 |
| verify_specialist_followup | Gemini | 1 | 1 | 0 | - | 4.299 | 4.299 | 0.002 |
| verify_specialist_followup | Jev | 1 | 0 | 0 | 1.000 | 0.397 | 0.397 | 0.000 |

## 문의 1건당 첫 처리 (LLM 구간)

접수 직후 호출 묶음(호출 사이 120초 넘게 쉬면 끊음)의 시작 ~ 끝. 검색·규칙·저장까지 넣은 K1 은 run_eval 로 잰다.

| tickets | llm_calls_avg | first_pass_p50_s | first_pass_p95_s | over_60s | cost_avg_usd | cost_total_usd |
|---|---|---|---|---|---|---|
| 1115 | 2.978 | 15.474 | 42.909 | 28 | 0.010 | 10.943 |
