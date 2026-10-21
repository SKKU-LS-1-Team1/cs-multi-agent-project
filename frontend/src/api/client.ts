// 백엔드 API 타입과 호출 함수. 스키마는 src/cs_agent/schemas.py 와 맞춘다.

export type Evidence = { source: string; doc_id: string; section: string | null; text: string; score: number };
export type CheckResult = { name: string; passed: boolean; reason: string };
export type Draft = { text: string; template: string; slots: Record<string, string>; cited: string[] };
export type Ticket = {
  ticket_id: string;
  status: string;
  route: string | null;
  category: string | null;
  product_code: string | null;
  priority: string | null;
  assigned_dept: string | null;
  sla_due_at: string | null;
  draft: Draft | null;
  info_request: string | null;
  checks: CheckResult[];
  evidence: Evidence[];
};
export type WorkItem = Pick<Ticket, "ticket_id" | "status" | "category" | "priority" | "assigned_dept" | "sla_due_at"> & {
  sla_ratio: number;
  at_risk: boolean;
};
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
  submitInquiry: (body: Record<string, unknown>) =>
    request<Ticket>("/tickets", { method: "POST", body: JSON.stringify(body) }),
  workList: (dept?: string) => request<WorkItem[]>(`/tickets${dept ? `?dept=${dept}` : ""}`),
  ticket: (id: string) => request<Ticket>(`/tickets/${id}`),
  act: (id: string, body: { action: ReviewAction } & Record<string, unknown>) =>
    request<Ticket>(`/tickets/${id}/action`, { method: "POST", body: JSON.stringify(body) }),
  departments: () => request<{ dept: string; open: number; at_risk: number }[]>("/dashboard/departments"),
};
