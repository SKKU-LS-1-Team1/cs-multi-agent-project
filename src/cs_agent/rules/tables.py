# 기준표 로더 (CSA-19 기준표 정리 · 담당 박종석 · Sprint 1)
#
# 규칙 처리(⑤)·근거 확정(⑧)·자동 점검(⑩)·화면 이동이 모두 여기 표를 읽는다.
# 규칙은 코드가 아니라 파일에 둔다 (N-02). 파일은 data/ref/ 에 있다.
#
# data/ref/ 현재 상태
# - sla_policy.csv      복원본 (tickets 의 SLA 목표값과 100% 일치)
# - routing_rules.csv   tickets 에서 역산한 임시본 (제품군 × 유형 → 담당 부서)
# - required_info.csv   역산 임시본 (유형 × 제품군 → 필수 항목, blocking_info = 처리 차단 항목 추정)
# - priority_rules.csv  역산 임시본 (PR-01~07)
# - product_master.csv  doc_index 의 데이터시트 23개. 대분류(POWER/AUTOMATION/ENERGY)는 가정
# - navigation_rules.csv 기획서 5.4 표 (CSA-33)
#
# 할 일
# 1. 원본 ref/ 파일을 받으면 같은 열 이름으로 교체한다. 못 받으면 임시본을 tickets 와 대조해 검수
#    (routing_rule_id·priority_rule_id·required_info 열과 일치율 확인).
# 2. 추가할 표: product_spec_facts(사양값), fault_catalog(에러코드 97건), firmware_history,
#    warranty(제품별 보증기간), price_list(정가·최소 주문·표준 납기). 답변 슬롯을 여기서 채운다.
# 3. load_tables(): 위 CSV를 읽어 RefTables 로 돌려준다. 한 번만 읽도록 캐시(lru_cache).
# 4. 이관 규칙(예: RETURN 비불량 → SCM, RT-ALL-RETURN-NON_DEFECT)도 표로 정리한다.
#
# 완료 기준: 김동규 님 규칙 처리(CSA-22)가 이 표만으로 valid 부서·우선순위 일치율을 낼 수 있음
#
# 만들 것 (이름·모양은 다른 파일이 이대로 부른다)
#
#   @dataclass(frozen=True)
#   class Product:
#       code: str
#       name: str
#       family: str
#       division: str
#
#   @dataclass(frozen=True)
#   class RefTables:
#       products: dict[str, Product]
#       routing: dict[tuple[str, str], tuple[str, str]]  # (family, category) -> (rule_id, dept)
#       required: dict[tuple[str, str], tuple[list[str], list[str]]]  # -> (required, blocking)
#       priority: list[dict[str, str]]
#       sla: dict[tuple[str, str, str], dict[str, str]]  # (category, tier, priority) -> row
#       navigation: dict[str, dict[str, str]]  # intent -> row (CSA-33)
#
#   def load_tables(ref_dir: Path | None = None) -> RefTables:
#       """data/ref/*.csv → RefTables. 경로 기본값은 config.Settings.ref_dir."""
