// 문의 남기기: 제품군·문의 유형에 맞는 입력 항목을 required_info 기준표에서 가져온다.
// 규칙(저장소 form_filler / InquiryForm 과 같게):
//  - required_fields 는 모두 채워야 제출할 수 있다 (빈 칸은 빨간 칸).
//  - blocking_fields 는 그중 "없으면 처리가 시작되지 않는" 항목이라 따로 표시한다. (blocking ⊂ required)
//  - [잘 모르겠어요]는 도움말을 열 뿐, 값이 확인되기 전에는 입력 완료로 치지 않는다.
import biz from '../data/biz.json'
import { LEGACY_FIELDS, LEGACY_NAME, LEGACY_TOPIC, LEGACY_TYPE, legacyRoute } from './legacy.js'
import { fieldLabel } from './inquiry.js'

export const UNKNOWN_PRODUCT = '__unknown'

// 고객에게는 4개 카테고리, 세부 목적을 고르면 내부 10개 유형으로 연결
export const CATEGORIES = [
  { id: 'defect', icon: 'alert', label: '제품 고장', sub: '제품이 멈췄거나 이상해요', types: [{ id: 'DEFECT', label: '제품이 고장 났어요' }] },
  { id: 'howto', icon: 'gear', label: '설치 · 사용 방법', sub: '설치나 사용이 궁금해요', types: [
    { id: 'INSTALL', label: '설치', sub: '설치 · 시운전' },
    { id: 'USAGE', label: '사용 방법', sub: '내용을 보고 담당 부서가 유형을 정해요' }] },
  // 펌웨어 업데이트는 문의 유형으로 받지 않는다. AI 상담이 알아보고 기술팀 연락처로 잇는다 (lib/firmware.js).
  { id: 'info', icon: 'doc', label: '제품 정보 · 자료', sub: '사양, 문서, 인증', types: [
    { id: 'TECH_SPEC', label: '사양', sub: '제품 사양이 궁금해요' }, { id: 'MANUAL', label: '문서 요청', sub: '설명서나 데이터시트가 필요해요' },
    { id: 'COMPLIANCE', label: '인증 · 규격', sub: '인증서나 규격이 필요해요' },
    { id: LEGACY_TYPE, label: LEGACY_NAME, sub: '오래된 제품이라 부품이 없거나 대체 모델이 궁금해요' }] },
  { id: 'biz', icon: 'shield', label: '보증 · 주문 · 견적', sub: '보증, 반품, 주문, 견적', types: [
    { id: 'WARRANTY', label: '보증', sub: '보증 적용을 확인하고 싶어요' }, { id: 'RETURN', label: '반품', sub: '교환이나 반품을 하고 싶어요' },
    { id: 'ORDER_LEAD', label: '주문 · 납기', sub: '주문이나 납기를 확인하고 싶어요' }, { id: 'QUOTE', label: '견적', sub: '견적을 받고 싶어요' }] },
]
export const typeInfo = (id) => CATEGORIES.flatMap((c) => c.types.map((t) => ({ ...t, cat: c.id }))).find((t) => t.id === id)
export const TYPE_NAME = { DEFECT: '제품 고장', INSTALL: '설치', USAGE: '사용 방법(유형 미정)', TECH_SPEC: '사양', MANUAL: '문서 요청', COMPLIANCE: '인증·규격', FW_UPDATE: '펌웨어', WARRANTY: '보증', RETURN: '반품', ORDER_LEAD: '주문·납기', QUOTE: '견적', [LEGACY_TYPE]: LEGACY_TOPIC }

// 항목 입력 방식, 쉬운 도움말
const FILE = { type: 'file' }
export const FIELD_CONF = {
  product_model: { type: 'text', help: '제품 이름이나 주문 코드를 적어 주세요.', placeholder: '예: INV-LSLV0750-iS7' },
  serial_no: { type: 'text', placeholder: '예: SN-2024-001234' },
  purchase_doc: { type: 'text', help: '구매할 때 받은 PO(주문서) 번호나 송장 번호예요.', placeholder: '예: PO-12345' },
  po_number: { type: 'text', help: '구매 주문서(PO)에 적힌 번호예요.', placeholder: '예: PO-12345' },
  error_code: { type: 'text', help: '화면에 뜬 글자(예: E.OC)를 적어 주세요. 에러 코드가 없는 제품은 보이는 증상을 설명해 주세요.', placeholder: '예: E.OC, 또는 "가속할 때 멈춰요"' },
  operating_condition: { type: 'textarea', help: '고장 났을 때 부하, 속도, 주변 온도가 어땠는지 알려 주세요.', placeholder: '예: 80% 부하, 주변 온도 40°C' },
  failure_description: { type: 'textarea', help: '무엇이 언제부터 어떻게 고장 났는지 적어 주세요.', placeholder: '예: 어제 오후부터 전원이 켜지지 않아요' },
  site_condition: { type: 'text', help: '설치한 곳의 주변 온도, 높이(고도), 습도예요.', placeholder: '예: 35°C, 800m, 습도 60%' },
  application: { type: 'text', help: '어떤 설비에 어떤 전압·부하로 쓰는지 알려 주세요.', placeholder: '예: 수처리 설비, 380V' },
  install_date: { type: 'date', help: '설치하고 처음 켠 날(시운전일)이에요.' },
  required_date: { type: 'date', help: '언제까지 필요한지 알려 주세요.' },
  quantity: { type: 'number', help: '필요한 개수예요.' },
  incoterms: { type: 'text', list: ['FOB Busan', 'EXW Factory', 'CIF', 'CFR', 'DAP'], help: '인코텀즈는 운송비·위험을 누가 어디까지 맡을지 정하는 인도 조건이에요. 표준은 FOB Busan 또는 EXW Factory예요. 납품 목적지도 함께 적어 주세요.', placeholder: '예: FOB Busan, 도착지 하노이', needsHelp: true },
  document_type: { type: 'text', list: ['데이터시트', '설치 가이드', '문제 해결 가이드', '유지보수 가이드', '펌웨어 릴리스 노트'], help: '어떤 문서가 필요한지 골라 주세요.', placeholder: '예: 데이터시트', needsHelp: true },
  target_standard: { type: 'text', help: '필요한 규격이나 인증서 이름이에요.', placeholder: '예: IEC 62443-4-2', needsHelp: true },
  target_country: { type: 'text', help: '제품을 쓸 국가나 시장이에요.', placeholder: '예: 미국' },
  current_fw: { type: 'text', help: '지금 제품에 설치된 펌웨어 버전이에요.', placeholder: '예: 3.10', needsHelp: true },
  tool_version: { type: 'text', help: '펌웨어를 올릴 때 쓰는 엔지니어링 도구(로더)의 버전이에요.', placeholder: '예: v4.6', needsHelp: true },
  return_reason: { type: 'text', list: ['처음부터 불량', '오배송', '배송 중 파손', '주문 실수 · 잉여 재고'], help: '반품하려는 이유를 알려 주세요.', placeholder: '예: 오배송' },
  packaging_condition: { type: 'text', list: ['원래 포장 그대로', '포장 훼손', '포장을 뜯음'], help: '제품이 도착했을 때 포장 상태예요.', placeholder: '예: 원래 포장 그대로' },
  motor_nameplate: { type: 'text', help: '모터 명판에 적힌 정격(전력, 전류, 전압 등)이에요.', placeholder: '예: 75kW, 135A, 380V' },
  load_profile: { type: 'textarea', help: '부하 전류나 온도 기록이 있으면 적어 주세요.', placeholder: '예: 평균 60%, 최대 85%' },
  battery_age: { type: 'text', help: '배터리를 설치한 날이나 사용한 기간이에요.', placeholder: '예: 2024-03 설치' },
  battery_status: { type: 'text', help: '이벤트 당시 배터리 충전량(SOC)과 셀 온도예요.' },
  string_config: { type: 'text', help: '스트링 하나에 모듈이 몇 장 연결됐는지 알려 주세요.' },
  manufacture_year: { type: 'text', help: '제품 명판에 적힌 제조 연도(또는 연월)예요. 안 보이면 설치한 해를 적고, 모르면 "모름"이라고 적어 주세요.', placeholder: '예: 2003', needsHelp: true },
  legacy_goal: { type: 'text', list: ['대체 모델 안내', '기존 자리에 호환 설치', '수리 · 부품 구하기', '교체 견적'], help: '무엇이 필요한지 골라 주세요. 여러 개면 직접 적어도 돼요.', placeholder: '예: 대체 모델 안내', needsHelp: true },
  photos: { ...FILE, help: '제품 전체와 명판이 보이는 사진이에요.' },
  logs: { ...FILE, help: '제품에서 내려받은 이벤트·트립 기록 파일이에요.' },
  parameter_backup: { ...FILE, help: '제품 설정(파라미터)을 저장한 백업 파일이에요.' },
  program_backup: { ...FILE, help: 'PLC·HMI 프로젝트 백업 파일이에요.' },
  wiring_diagram: { ...FILE, help: '배선도나 단선도 파일이에요.' },
  oil_test: { ...FILE, help: '절연유 시험(DGA) 보고서예요.' },
}
export const confOf = (key) => FIELD_CONF[key] ?? { type: 'text' }

// 유형·제품군에 맞는 항목 (기준표 그대로). 유형이 미정이면 제품 모델만.
export function fieldsFor(type, family) {
  if (type === LEGACY_TYPE) return LEGACY_FIELDS.map((f) => ({ key: f.key, blocking: f.blocking, label: fieldLabel(f.key) }))
  if (!type || type === 'USAGE') return [{ key: 'product_model', blocking: true, label: fieldLabel('product_model') }]
  return (biz.required[family]?.[type] ?? [{ key: 'product_model', blocking: true }]).map((f) => ({ key: f.key, blocking: f.blocking, label: fieldLabel(f.key) }))
}

export const isDate = (v) => /^\d{4}-\d{2}-\d{2}$/.test(v ?? '')
export const filled = (f, vals, files) => (confOf(f.key).type === 'file' ? (files[f.key]?.length ?? 0) > 0 : !!String(vals[f.key] ?? '').trim())
export const missingOf = (fields, vals, files) => fields.filter((f) => !filled(f, vals, files))
export const errorText = (f) => `${f.label}: ${confOf(f.key).type === 'file' ? '파일을 첨부해 주세요' : '입력해 주세요'}${f.blocking ? ' (꼭 필요해요)' : ''}`

export const EXAMPLES = {
  DEFECT: '예) 가속할 때마다 E.OC가 떠요. 가속 시간을 늘려 봤지만 같은 증상이에요. 원인과 해결 방법을 알고 싶어요.',
  INSTALL: '예) 시운전 중인데 자동 튜닝이 끝나지 않아요. 설치 환경은 이렇고, 어디를 확인해야 하는지 알고 싶어요.',
  USAGE: '예) 이 기능을 이렇게 쓰고 싶은데 어떻게 설정하는지 알고 싶어요.',
  TECH_SPEC: '예) 이 제품의 정격 전류와 통신 방식을 확인하고 싶어요. 사용 환경은 이래요.',
  MANUAL: '예) 설치 가이드 최신판이 필요해요. 어디에 쓰려는지 함께 알려 주세요.',
  COMPLIANCE: '예) 미국 프로젝트에 필요한 인증서를 받을 수 있는지 알고 싶어요.',
  WARRANTY: '예) 설치한 지 1년 된 제품이 고장 났어요. 보증으로 수리나 교체가 가능한지 알고 싶어요.',
  RETURN: '예) 주문한 모델과 다른 제품이 도착했어요. 교환하고 싶어요.',
  ORDER_LEAD: '예) 주문한 제품의 출하 시기를 확인하고 싶어요. 납기를 앞당길 수 있는지도 궁금해요.',
  QUOTE: '예) 이 제품 10개 견적이 필요해요. 납품 지역과 희망 납기는 이래요.',
  [LEGACY_TYPE]: '예) 20년 넘게 쓴 차단기라 부품을 구할 수 없어요. 같은 자리에 들어가는 대체 모델이 있는지 알고 싶어요.',
}
export const LANGUAGES = [['en', 'English'], ['ko', '한국어'], ['ja', '日本語'], ['zh', '中文'], ['es', 'Español'], ['fr', 'Français'], ['de', 'Deutsch'], ['it', 'Italiano'], ['pt', 'Português'], ['ru', 'Русский'], ['tr', 'Türkçe'], ['vi', 'Tiếng Việt'], ['id', 'Bahasa Indonesia'], ['th', 'ไทย'], ['ar', 'العربية']]

export const routeOf = (family, type) => (type === LEGACY_TYPE ? legacyRoute(family) : biz.routing[family]?.[type])
export const humanSize = (n) => (n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`)
