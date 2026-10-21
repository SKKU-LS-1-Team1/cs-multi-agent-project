// 백엔드 API 타입과 호출 함수. 스키마는 src/cs_agent/schemas.py 와 맞춘다.

export type Evidence = { source: string; doc_id: string; section: string | null; text: string; score: number };
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
export type Ticket = {
  ticket_id: string;
  inquiry: InquiryIn | null; // 문의 원문 (회신이 오면 이어 붙인 본문)
  body_ko: string | null; // 상담원용 한국어 번역 (CSA-57)
  status: string;
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
  final_reply: string | null; // 고객에게 보낸 글 (고객 언어)
  final_reply_language: string | null;
  translation_error: string | null;
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
  families: { family: string; products: { code: string; name: string }[] }[];
}[];
export type ReviewAction = "approve" | "edit_approve" | "rewrite" | "info_request" | "escalate" | "reject";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  productTree: () => request<ProductTree>("/products/tree"),
  product: (code: string) => request<{ code: string; name: string; family: string; tabs: string[] }>(`/products/${code}`),
  chat: (body: {
    session_id: string;
    message: string;
    language?: string;
    viewing_product?: string | null;
    unresolved?: boolean; // "해결 안 됐어요" 버튼 → 바로 문의 전환
  }) =>
    request<ChatReply>("/chat", { method: "POST", body: JSON.stringify(body) }),
  submitInquiry: (body: InquiryIn) => request<Ticket>("/tickets", { method: "POST", body: JSON.stringify(body) }),
  customerInquiry: (id: string) => request<CustomerInquiry>(`/inquiries/${id}`),
  resolve: (id: string) => request<Ticket>(`/tickets/${id}/resolve`, { method: "POST" }),
  agents: (dept?: string) => request<Agent[]>(`/agents${dept ? `?dept=${dept}` : ""}`),
  workList: (dept?: string) => request<WorkItem[]>(`/tickets${dept ? `?dept=${dept}` : ""}`),
  ticket: (id: string) => request<Ticket>(`/tickets/${id}`),
  act: (id: string, body: { action: ReviewAction } & Record<string, unknown>) =>
    request<Ticket>(`/tickets/${id}/action`, { method: "POST", body: JSON.stringify(body) }),
  departments: () => request<{ dept: string; open: number; at_risk: number }[]>("/dashboard/departments"),
};
