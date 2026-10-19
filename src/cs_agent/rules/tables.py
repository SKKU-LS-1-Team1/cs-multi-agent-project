# 기준표 로더 (CSA-19 기준표 정리 · 담당 박종석 · Sprint 1)
#
# 규칙 처리(⑤)·근거 확정(⑧)·자동 점검(⑩)·화면 이동이 모두 여기 표를 읽는다.
# 규칙은 코드가 아니라 파일에 둔다 (N-02). 파일은 data/ref/ 에 있다.
#
# data/ref/ (원본 기준표. 파일 맨 앞에 BOM 이 있으니 encoding="utf-8-sig" 로 읽는다)
# - product_master.csv    제품 23개: 제품군·보증기간·리드타임·MOQ·정가·인증·문서 ID·기술지원 부서
# - routing_rules.csv     (family, category) → primary_dept, escalation_dept, escalation_condition.
#                         rule_source 로 우선순위: SUBTYPE_OVERRIDE(예: RT-ALL-RETURN-NON_DEFECT
#                         → SCM) > FAMILY_OVERRIDE > CATEGORY_DEFAULT. ESCALATION 행은 이관 규칙
# - required_info.csv     (family, category) → required_fields, blocking_fields (';' 로 구분)
# - info_field_codebook.csv 항목 이름 → 고객에게 보일 라벨 (추가정보 요청 문구에 쓴다)
# - priority_rules.csv    PR-01~07. order 순서대로 condition 을 보고 처음 맞는 규칙
# - urgency_codebook.csv  긴급도 코드 설명
# - sla_policy.csv        (category, customer_tier, priority) → 첫 응답·해결 목표 시간
# - departments.csv       부서 코드·이름·레벨·담당 범위
# - customers.csv         고객 600곳의 tier·segment (SLA 등급 조회)
# - product_spec_facts.csv 제품별 사양값 + 근거 문서·절 (답변 슬롯, 근거 확정 ⑧)
# - fault_catalog.csv     에러코드 97건: 증상·원인·진단·조치·현장 출동·RMA 여부
# - firmware_history.csv  제품별 펌웨어 버전·출시일·최신 여부·변경 내용
# - reference_master.xlsx 위 표들을 한 파일로 묶은 엑셀 (같은 내용)
# - navigation_rules.csv  기획서 5.4 표 (CSA-33). 원본에 없어 직접 만든 표
#
# 할 일
# 1. load_tables(): 위 CSV를 읽어 RefTables 로 돌려준다. 한 번만 읽도록 캐시(lru_cache).
# 2. routing 은 rule_source 우선순위대로 찾게 만든다. RETURN 이 불량이 아니면 SUBTYPE_OVERRIDE.
# 3. tickets 와 대조해 검수: routing_rule_id·priority_rule_id·required_info 열 일치율을 낸다.
#    priority 가 규칙과 다른 건은 상담원 조정(priority_adjusted_by_agent)인지 확인.
# 4. 제품 트리(api/products.py)의 대분류는 원본에 없다. family 를 묶는 대분류 표를 정해서 둔다.
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
#       division: str  # 원본에 없음, 할 일 4
#
#   @dataclass(frozen=True)
#   class RefTables:
#       products: dict[str, Product]
#       routing: dict[tuple[str, str], dict[str, str]]  # (family, category) -> 행 (rule_id·dept)
#       required: dict[tuple[str, str], tuple[list[str], list[str]]]  # -> (required, blocking)
#       priority: list[dict[str, str]]
#       sla: dict[tuple[str, str, str], dict[str, str]]  # (category, tier, priority) -> row
#       navigation: dict[str, dict[str, str]]  # intent -> row (CSA-33)
#
#   def load_tables(ref_dir: Path | None = None) -> RefTables:
#       """data/ref/*.csv → RefTables. 경로 기본값은 config.Settings.ref_dir."""
