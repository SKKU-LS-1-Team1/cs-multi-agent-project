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
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
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
  submitInquiry: (body: Record<string, unknown>) =>
    request<Ticket>("/tickets", { method: "POST", body: JSON.stringify(body) }),
  workList: (dept?: string) => request<WorkItem[]>(`/tickets${dept ? `?dept=${dept}` : ""}`),
  ticket: (id: string) => request<Ticket>(`/tickets/${id}`),
  act: (id: string, body: { action: ReviewAction } & Record<string, unknown>) =>
    request<Ticket>(`/tickets/${id}/action`, { method: "POST", body: JSON.stringify(body) }),
  departments: () => request<{ dept: string; open: number; at_risk: number }[]>("/dashboard/departments"),
};
