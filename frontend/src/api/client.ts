import type { Customer } from "../admin/lib/customer-types";
export type CustomerQc = {
  decision: "PASS" | "BLOCK" | "REVIEW" | "ERROR";
  issues: { paragraph_id: string; category: "ABUSE" | "CREDENTIAL" | "CONFIDENTIAL"; source_id: string | null; reason: string; suggestion: string }[];
  message: string; text_hash: string;
};
// 백엔드 API 타입과 호출 함수. 스키마는 src/cs_agent/schemas.py 와 맞춘다.

export type Evidence = { source: string; doc_id: string; section: string | null; text: string; score: number; metadata?: Record<string, string> };
export type CheckResult = { name: string; passed: boolean; reason: string };
export type Draft = { text: string; template: string; slots: Record<string, string>; cited: string[] };
export type InquiryIn = {
  channel: string;
  customer_id?: string | null;
  country?: string | null;
  language?: string | null;
  subject: string;
  body: string;
  product_code?: string | null;
  category?: string | null;
  provided_fields?: Record<string, string>;
  thread_ref?: string | null;
  received_at?: string;
};
export type EscalationRequest = { to_dept: string; reason: string; summary: string; fields: Record<string, string>; cited: string[]; text: string; model: string };
export type SpecialistRequest = {
  request_id: string; to_dept: string; text: string; requested_by: string; created_at: string;
  channel?: string; attachment_names?: string[];
  reply: { reply_id: string; text: string; author: string; created_at: string } | null;
};
export type ResolutionIn = {
  outcome: "resolved" | "provided" | "unconfirmed";
  cause: string; action: string; result: string; verification: string; confirmed_by: string;
  references: { id: string; label: string; kind: string }[];
};
export type Resolution = ResolutionIn & { confirmed_at: string; superseded: boolean };
export type Classification = { category: string; secondary_category?: string | null; confidence: number; model: string };
export type Extraction = {
  product_code: string | null; product_family?: string | null; error_code: string | null;
  fw_version: string | null; serial_no: string | null; urgency: string; language: string | null;
  field_values: Record<string, string>; provided_info: string[];
  field_evidence?: Record<string, string>; field_sources?: Record<string, string>;
  unconfirmed_fields?: Record<string, string>; unconfirmed_evidence?: Record<string, string>;
  issues?: string[]; assessed_urgency?: string | null; safety_review_required?: boolean;
};
export type RuleResult = { required_info: string[]; missing_info: string[]; missing_blocking: string[]; priority: string; priority_rule_id: string; routing_rule_id: string; assigned_dept: string };
export type CustomerMessage = { message_id: string; kind: "initial" | "reply"; body: string; subject: string;
  received_at: string; language: string | null; provided_fields: Record<string, string> };
export type InformationFieldReview = { status: "missing" | "unusable" | "confirmed"; value?: string; evidence: string };
export type InformationReviewIn = { reply_id: string; customer_revision: number; expected_reviewed_at?: string | null; reviewer: string; fields: Record<string, InformationFieldReview> };
export type InformationReview = InformationReviewIn & { checked_at: string };
export type ProgressFact = { ticket_id: string; status: string; category: string | null; product_code: string | null;
  pending_specialist_count: number; received_specialist_count: number; waiting_for_customer: boolean; resolution_outcome: string | null; investigation?: { status: "in_progress" | "confirmed"; steps: { stage: string; status: "in_progress" | "completed" }[] } };
export type ProgressNotice = {
  notice_id: string; anchor_ticket_id: string; ticket_ids: string[]; customer_id: string;
  target_language: string; status: "draft" | "prepared"; draft_text: string | null;
  approved_text: string | null; final_text: string | null; reviewer: string | null;
  created_at: string; approved_at: string | null; error: string | null;
  source_facts: ProgressFact[];
  customer_qc?: CustomerQc | null;
};
export type SpecialistFollowup = {
  source_version: string; status: "in_progress" | "confirmed"; pending_replies: boolean;
  needs_review: boolean; error: string | null; missing_fields: string[];
  reading: { steps: { stage: string; status: "in_progress" | "completed"; reply_id: string; evidence: string }[];
    requested_fields: { field: string; reply_id: string; evidence: string }[];
    conclusion: { reply_id: string; evidence: string } | null; needs_review: boolean } | null;
  confirmation: { reviewer: string; confirmed_at: string; finding: { reply_id: string; evidence: string } } | null;
};
export type Ticket = {
  ticket_id: string;
  inquiry: InquiryIn | null; // 문의 원문 (회신이 오면 이어 붙인 본문)
  body_ko: string | null; // 상담원용 한국어 번역 (CSA-57)
  status: string;
  manual_reply?: boolean;
  processing_history?: { id: string; kind: string; created_at: string; actor: string; text?: string; master_text?: string; reply_language?: string; purpose?: string; edited?: boolean; resolution?: Resolution | null }[];
  assignment_history?: { from_assignee: string | null; to_assignee: string | null; reason: string; assigned_by: string; created_at: string }[];
  route: string | null;
  category: string | null;
  product_code: string | null;
  priority: string | null;
  assigned_dept: string | null;
  sla_due_at: string | null;
  assignee: string | null; // agent_id (data/ref/agents.csv)
  draft: Draft | null;
  info_request: string | null;
  approved_reply: string | null;
  approval_text?: string | null;
  approval_cited?: string[] | null;
  approval_error?: string | null;
  customer_qc?: CustomerQc | null;
  resolution?: Resolution | null;
  final_reply: string | null; // 고객에게 보낸 글 (고객 언어)
  escalation_request: EscalationRequest | null; // 전문부서 이관 요청서 초안 (CSA-55)
  final_reply_language: string | null;
  translation_error: string | null;
  classification?: Classification | null;
  extraction?: Extraction | null;
  rules?: RuleResult | null;
  field_labels?: Record<string, string>;
  customer_messages?: CustomerMessage[];
  customer_revision?: number;
  draft_customer_revision?: number;
  draft_information_reviewed_at?: string | null;
  information_review?: InformationReview | null;
  information_reviews?: InformationReview[];
  investigation_info?: { recommended_fields: string[]; provided_fields: string[]; missing_fields: string[]; note: string } | null;
  specialist_followup?: SpecialistFollowup | null;
  specialist_requests?: SpecialistRequest[];
  specialist_revision?: number;
  draft_specialist_revision?: number;
  checks: CheckResult[];
  evidence: Evidence[];
};
export type WorkItem = Pick<Ticket, "ticket_id" | "status" | "category" | "priority" | "assigned_dept" | "assignee" | "sla_due_at"> & {
  sla_ratio: number;
  at_risk: boolean;
};
// 고객용 문의 조회 (GET /api/inquiries/{id}, CSA-61). 내부 초안·근거·담당자는 오지 않는다.
export type CustomerStatus = "RECEIVED" | "IN_PROGRESS" | "WAITING_CUSTOMER" | "ANSWERED" | "CLOSED";
export type CustomerInquiry = {
  ticket_id: string;
  subject: string;
  body: string;
  received_at: string | null;
  status: CustomerStatus;
  message: string | null; // 상담원이 보낸 회신 · 추가정보 요청
  message_language: string | null;
};
export type Agent = { agent_id: string; name: string; dept: string; active: boolean; max_open: number; open_count: number };
export type Navigation = { product_code: string | null; tab: string | null; anchor: string | null; candidates: string[] };
export type InquiryForm = {
  category: string | null;
  product_code: string | null;
  fields: Record<string, string>;
  missing_required: string[];
  subject: string;
  body: string;
};
export type ChatReply = {
  answer: string;
  navigation: Navigation;
  evidence: Evidence[];
  ask_fields: string[];
  handoff: boolean;
  handoff_reason: string;
  form: InquiryForm | null;
};
export type ProductTree = {
  division: string;
  label: string;
  families: { family: string; label: string; products: { code: string; name: string }[] }[];
}[];
// 제품 상세 (GET /api/products/{code}, CSA-60). 탭은 내용이 있는 것만 tabs 에 온다.
// 챗봇 이동 지시의 anchor 로 강조: faults[].error_code · info.specs[].attribute ·
// install.sections[].section · docs[].doc_id · firmware.latest (lead_time → info.ordering, policy → faq.policies)
export type DocSection = { section: string; title: string; text: string };
export type DocMeta = { doc_id: string; title: string; doc_type: string; revision: string };
export type ProductDocument = DocMeta & { sections: DocSection[] };
export type ProductDetail = {
  code: string;
  name: string;
  family: string;
  family_label: string;
  division: string;
  division_label: string;
  description: string;
  lifecycle_status: string;
  tabs: ("info" | "install" | "faults" | "firmware" | "faq" | "docs")[];
  info: {
    specs: { attribute: string; value: string; doc_id: string; section: string }[];
    standards: string[];
    certifications: string[];
    ordering: { std_lead_time_weeks: string; moq: string; warranty_months: string };
    physical: { weight_kg: string; dimensions_mm: string; ip_rating: string; operating_temp: string };
  };
  install: ProductDocument | null;
  faults: {
    fault_id: string;
    error_code: string;
    symptom: string;
    root_cause: string;
    diagnosis: string;
    action: string;
    needs_onsite: boolean;
    needs_rma: boolean;
    fw_fix_version: string;
    doc_id: string | null;
    section: string | null;
  }[];
  firmware: {
    latest: string;
    releases: { version: string; release_date: string; latest: boolean; changes: string[]; doc_id: string }[];
  } | null;
  faq: {
    doc_id: string | null;
    items: { section: string; question: string; answer: string }[];
    policies: ProductDocument[];
  } | null;
  docs: DocMeta[];
};
export type ReviewAction = "approve" | "edit_approve" | "rewrite" | "info_request" | "escalate" | "reject";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw Object.assign(new Error(`${res.status} ${await res.text()}`), { status: res.status });
  return res.json() as Promise<T>;
}

export type CompletedItem = {
  ticket_id: string; subject: string; product_code: string | null; status: string;
  received_at: string; resolved_at: string | null; resolution: Record<string, any>;
  verified: boolean; superseded: boolean;
};
export type CompletedPage = { items: CompletedItem[]; total: number };

export const api = {
  customers: () => request<Customer[]>("/customers"),
  productTree: () => request<ProductTree>("/products/tree"),
  product: (code: string) => request<ProductDetail>(`/products/${code}`),
  productDocument: (code: string, docId: string) => request<ProductDocument>(`/products/${code}/docs/${docId}`),
  chat: (body: {
    session_id: string;
    message: string;
    language?: string;
    viewing_product?: string | null;
    unresolved?: boolean; // "해결 안 됐어요" 버튼 → 바로 문의 전환
  }) =>
    request<ChatReply>("/chat", { method: "POST", body: JSON.stringify(body) }),
  submitInquiry: (body: InquiryIn) => request<Ticket>("/tickets", { method: "POST", body: JSON.stringify(body) }),
  // 고객 화면은 이것으로 문의·회신을 보낸다 (고객 도메인은 /api/tickets 를 막는다, CSA-46)
  createInquiry: (body: InquiryIn) => request<CustomerInquiry>("/inquiries", { method: "POST", body: JSON.stringify(body) }),
  customerInquiry: (id: string) => request<CustomerInquiry>(`/inquiries/${id}`),
  resolve: (id: string, body?: ResolutionIn) => request<Ticket>(`/tickets/${id}/resolve`, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  agents: (dept?: string) => request<Agent[]>(`/agents${dept ? `?dept=${dept}` : ""}`),
  workList: (dept?: string) => request<WorkItem[]>(`/tickets${dept ? `?dept=${dept}` : ""}`),
  answered: () => request<string[]>("/tickets/answered"),
  completedPage: (q = "", verified = false, offset = 0, limit = 50) => request<CompletedPage>(`/tickets/completed?${new URLSearchParams({ q, verified: String(verified), offset: String(offset), limit: String(limit) })}`),
  closed: () => request<string[]>("/tickets/closed"),
  manualReply: (id: string, body: { text: string; reviewer: string; expected_customer_revision: number; expected_specialist_revision: number; expected_information_reviewed_at: string | null }) =>
    request<Ticket>(`/tickets/${id}/manual-reply`, { method: "POST", body: JSON.stringify(body) }),
  assign: (id: string, body: { assignee: string; reason?: string; by?: string }) =>
    request<Ticket>(`/tickets/${id}/assign`, { method: "POST", body: JSON.stringify(body) }),
  // 전문부서 이관 요청서 초안 만들기 (CSA-55). 실제 이관은 act(escalate)
  escalationRequest: (id: string, toDept?: string) =>
    request<Ticket>(`/tickets/${id}/escalation-request`, { method: "POST", body: JSON.stringify(toDept ? { to_dept: toDept } : {}) }), // 발송했고 해결 확정 전 (작업 목록에는 없다)
  informationReview: (id: string, body: InformationReviewIn) =>
    request<Ticket>(`/tickets/${id}/information-review`, { method: "POST", body: JSON.stringify(body) }),
  progressNotices: (id: string) => request<ProgressNotice[]>(`/tickets/${id}/progress-notices`),
  progressNotice: (id: string, body: { notice_id: string; ticket_ids: string[] }) =>
    request<ProgressNotice>(`/tickets/${id}/progress-notices`, { method: "POST", body: JSON.stringify(body) }),
  prepareProgressNotice: (id: string, noticeId: string, body: { reviewer: string; edited_text: string }) =>
    request<ProgressNotice>(`/tickets/${id}/progress-notices/${noticeId}/approve`, { method: "POST", body: JSON.stringify(body) }),
  specialistRequest: (id: string, body: { request_id: string; to_dept: string; text: string; requested_by: string; channel?: string; attachment_names?: string[] }) =>
    request<Ticket>(`/tickets/${id}/specialist-requests`, { method: "POST", body: JSON.stringify(body) }),
  analyzeSpecialistFollowup: (id: string) => request<Ticket>(`/tickets/${id}/specialist-followup/analyze`, { method: "POST" }),
  confirmSpecialistFinding: (id: string, body: { source_version: string; reviewer: string; finding: { reply_id: string; evidence: string } }) => request<Ticket>(`/tickets/${id}/specialist-followup/confirm`, { method: "POST", body: JSON.stringify(body) }),
  specialistReply: (id: string, requestId: string, body: { reply_id: string; text: string; author: string }) =>
    request<Ticket>(`/tickets/${id}/specialist-requests/${requestId}/reply`, { method: "POST", body: JSON.stringify(body) }),
  replyPreview: (id: string, text: string) => request<{ preview_id: string; source_text: string; target_language: string; final_text: string }>(`/tickets/${id}/reply-preview`, { method: "POST", body: JSON.stringify({ text }) }),
  ticket: (id: string) => request<Ticket>(`/tickets/${id}`),
  act: (id: string, body: { action: ReviewAction } & Record<string, unknown>) =>
    request<Ticket>(`/tickets/${id}/action`, { method: "POST", body: JSON.stringify(body) }),
  departments: () => request<{ dept: string; open: number; at_risk: number }[]>("/dashboard/departments"),
};
