// 고객 화면에 보이는 코드 → 쉬운 말. 챗봇(더 물어본 항목) · 문의하기(입력 칸) · 내 문의 내역(상태)이 같이 쓴다.
import type { CustomerStatus } from "../../api/client";

// 기준표 info_field_codebook 의 항목
export const FIELD_KO: Record<string, string> = {
  product_model: "제품 모델명", serial_no: "시리얼 번호", error_code: "에러 코드·증상", operating_condition: "고장 당시 운전 조건",
  photos: "제품·명판 사진", site_condition: "설치 환경", wiring_diagram: "배선도", application: "사용 용도", purchase_doc: "PO·송장 번호",
  install_date: "설치·시운전 날짜", failure_description: "고장 내용", po_number: "PO 번호", quantity: "수량", required_date: "희망 납기일",
  incoterms: "인도 조건", document_type: "필요한 문서", target_standard: "필요한 규격·인증", target_country: "사용 국가", current_fw: "현재 펌웨어",
  tool_version: "툴 버전", return_reason: "반품 사유", packaging_condition: "포장 상태", logs: "이벤트·트립 기록",
};

// 칸 아래 작은 안내 (예시가 있어야 덜 헤매는 항목만)
export const FIELD_HINT: Record<string, string> = {
  product_model: "명판에 적힌 모델명 (예: LSLV0075S100-4)",
  serial_no: "명판의 S/N 또는 Serial No.",
  error_code: "화면에 뜬 코드나 램프 상태 (예: E.OC, ALM 깜빡임)",
  po_number: "주문서(Purchase Order) 번호",
  purchase_doc: "PO 번호 또는 송장(Invoice) 번호",
  install_date: "예: 2026-03-15",
  required_date: "예: 2026-12-01",
  incoterms: "예: FOB, CIF, DAP",
  photos: "사진 링크를 붙여 넣거나, 보낼 수 있다고 적어 주세요",
  logs: "기록 파일 링크 또는 내용",
};

export const fieldLabel = (k: string) => FIELD_KO[k] ?? k;

// 문의 유형 10개 (domain.Category)
export const CATEGORY_KO: Record<string, string> = {
  TECH_SPEC: "사양 문의", MANUAL: "문서·자료 요청", COMPLIANCE: "인증·규격", QUOTE: "견적", ORDER_LEAD: "주문·납기",
  DEFECT: "고장·오류", INSTALL: "설치·설정", FW_UPDATE: "펌웨어", WARRANTY: "보증", RETURN: "반품·교환",
};

export const STATUS_LABEL: Record<CustomerStatus, string> = {
  RECEIVED: "접수됨",
  IN_PROGRESS: "검토 중",
  WAITING_CUSTOMER: "답장 필요",
  ANSWERED: "답변 완료",
  CLOSED: "종료",
};
