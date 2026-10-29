// 관리자 화면 ↔ 백엔드 API 연결 (CSA-61 · 담당 김동규). 페이지·디자인(CSA-59 · 김도연)은 그대로 두고
// 데이터만 잇는다.
//
// - startApiSync(): 열린 작업과 선택한 문의의 상세만 10초마다 읽어
//   서버 문의를 화면 스토어에 반영한다. 연결 실패 시 마지막 서버 데이터를 유지하고 오류를 표시한다.
// - 백엔드 티켓(source "api")에서 API 로 보내는 동작 (actions.ts 가 여기로 넘긴다)
//   · 승인 및 발송 → POST /action  approve (AI 초안 그대로) / edit_approve (고친 글)
//     추가정보 요청문 초안이면 승인 후 고객 회신 대기(WAITING_CUSTOMER)가 된다.
//     명시적인 변환 버튼으로 미리 본 고객 언어 문구를 최종 점검 후 그대로 사용한다.
//   · 처리 결과 기록 및 완료 → POST /resolve (해결 사례로 남는다)
//   · 답변 초안 작성 → 저장된 AI 초안을 사용하고, 새 전문부서 회신이 있으면 rewrite
// - 화면 표시: 원문 언어(language)·접수 시각(receivedLabel)·한국어 번역(bodyKo, "한국어 번역" 토글)·
//   근거 문서(apiEvidence → logic.answerContext 의 관련 기술문서)
//   · 초안 수정 요청 → POST /action rewrite (feedback). 같은 근거로 백엔드가 다시 쓴다
//   · 추가정보 요청문 → POST /action info_request. 요청문 초안이 나오고, 승인하면 고객 회신 대기
//   · 담당자 변경(배정·리소스 보드·일괄) → POST /assign (앞단 상담원끼리, CSA-53)
//   · 전문부서 요청서 AI 생성 및 요청·회신 기록 → specialist-requests (CSA-62). 외부 전달은 담당자가 수행.
//   · 고객 회신 자료 확인 → POST /information-review. 실제 값·근거와 회신 버전을 저장한다.
// - 고객 관리·로그인은 별도 화면 기록을 사용한다.
import { toast } from "sonner";
import { api, type Agent, type Ticket as ApiTicket, type WorkItem, type ResolutionIn, type InformationFieldReview } from "../../api/client";
import { people, answerContext, contextKey, record, signedIn, waitingReviews } from "./logic";
import { commit, openModal, setUi, tickets } from "./store";
import type { Ticket } from "./types";

const REFRESH_MS = 10_000;

const CATEGORY_LABEL: Record<string, string> = {
  TECH_SPEC: "사양", MANUAL: "문서 요청", COMPLIANCE: "인증", QUOTE: "견적", ORDER_LEAD: "납기",
  DEFECT: "불량", INSTALL: "설치", FW_UPDATE: "펌웨어", WARRANTY: "보증", RETURN: "반품",
};
const STATUS_LABEL: Record<string, string> = {
  NEW: "접수", ANALYSIS_PENDING: "분석 대기", HUMAN_QUEUE: "사람 검토", WAITING_CUSTOMER: "고객 회신 대기",
  READY_FOR_REVIEW: "답변 검토", ON_HOLD: "보류", ESCALATED: "이관", APPROVED: "발송 완료",
  REJECTED: "반려", RESOLVED: "완료",
};
// 화면의 고객 언어 표기 (logic.replyLanguages). 없는 언어는 코드 그대로
const LANGUAGE_LABEL: Record<string, string> = {
  en: "English", ko: "한국어", ja: "日本語", de: "Deutsch", fr: "Français", es: "Español", vi: "Tiếng Việt", zh: "中文",
};
const CLOSED = new Set(["RESOLVED", "REJECTED"]);
// 부서 코드 → 이름 (data/ref/departments.csv dept_name_ko)
export const DEPT_LABEL: Record<string, string> = {
  GCS_L1: "글로벌 C/S 센터", TS_LV: "저압기기 기술지원", TS_MV: "고압·배전반 기술지원", TS_TRF: "변압기 기술지원",
  TS_AUTO: "자동화 기술지원", TS_ENERGY: "에너지솔루션 기술지원", RND_FW: "펌웨어 개발", QA_CLAIM: "품질보증/클레임",
  FIELD_SVC: "현장 서비스", CERT: "인증·규격", SALES_OPS: "해외영업 운영", SCM: "주문·물류", WARRANTY_DESK: "보증·RMA 데스크",
};
export const deptCode = (label: string) => Object.keys(DEPT_LABEL).find((k) => DEPT_LABEL[k] === label) ?? label;

let agents = new Map<string, Agent>();
let online = false;
const workItems = new Map<string, WorkItem>();
const specialistWrites = new WeakSet<Ticket>();
const rewrites = new WeakSet<Ticket>();
const sends = new WeakSet<Ticket>();
const replyTranslations = new WeakSet<Ticket>();
const informationWrites = new WeakSet<Ticket>();

export const isApiTicket = (t: Ticket) => t.source === "api";

function receivedLabel(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getMonth() + 1)}.${pad(d.getDate())} · ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function slaText(due: string | null): string {
  if (!due) return "—";
  const minutes = Math.round((new Date(due).getTime() - Date.now()) / 60_000);
  const abs = Math.abs(minutes), text = abs >= 60 ? `${Math.floor(abs / 60)}h ${abs % 60}m` : `${abs}m`;
  return minutes < 0 ? `초과 ${text}` : text;
}

/** 백엔드 티켓 → 프로토타입 Ticket. 상담원이 고치던 글은 지우지 않는다. */
export function apply(t: Ticket | undefined, api: ApiTicket): Ticket {
  // An older poll must not undo a request/reply mutation that finished meanwhile.
  if (t && (api.specialist_revision ?? 0) < (t.specialistRevision ?? 0)) return t;
  if (t && (api.customer_revision ?? 0) < (t.customerRevision ?? 0)) return t;
  if (t && (api.customer_revision ?? 0) === (t.customerRevision ?? 0) &&
    (api.information_review?.checked_at || "") < (t.informationReviewedAt || "")) return t;
  const inquiry = api.inquiry;
  const initialMessage = api.customer_messages?.find((m) => m.kind === "initial");
  const replies = (api.customer_messages || []).filter((m) => m.kind === "reply");
  const latestReply = replies.at(-1);
  const currentReview = api.information_review?.customer_revision === (api.customer_revision ?? 0) ? api.information_review : null;
  const labels = api.field_labels || {}, extraction = api.extraction;
  const values: Record<string, string> = { ...(extraction?.field_values || {}) };
  for (const [code, value] of Object.entries({ product_model: extraction?.product_code, current_fw: extraction?.fw_version,
    error_code: extraction?.error_code, serial_no: extraction?.serial_no })) if (value && !values[code]) values[code] = value;
  const required = (api.rules?.required_info || []).map((id) => ({ id, label: labels[id] || id }));
  const checks = Object.fromEntries(required.map(({ id }) => [id, {
    status: api.rules?.missing_info.includes(id) ? (extraction?.unconfirmed_fields?.[id] ? "unusable" : "missing") : "provided",
    value: values[id] || "", evidence: extraction?.field_evidence?.[id] || "",
    source: extraction?.field_sources?.[id] || "", ...(currentReview?.fields[id] || {}),
    confirmedBy: currentReview?.fields[id]?.status === "confirmed" ? currentReview.reviewer : null,
    checkedAt: currentReview?.checked_at,
  }]));
  const work = workItems.get(api.ticket_id);
  // 검토 대기면 AI 초안(또는 추가정보 요청문), 번역 확인 실패로 보류됐으면 승인했던 글 (다시 발송)
  const canEdit = ["READY_FOR_REVIEW", "ON_HOLD", "HUMAN_QUEUE"].includes(api.status);
  const aiDraft = canEdit ? api.info_request || api.draft?.text || "" : "";
  const displayDraft = canEdit ? api.approval_text ||
    (api.translation_error ? api.approved_reply : null) || aiDraft : "";
  const target = t ?? ({ id: api.ticket_id, events: [], files: [], reviewed: false, source: "api" } as unknown as Ticket);
  const reviewChanged = !t || JSON.stringify(t.specialistFollowup || null) !== JSON.stringify(api.specialist_followup || null) || t.specialistRevision !== (api.specialist_revision ?? 0) || t.customerRevision !== (api.customer_revision ?? 0) || t.informationReviewedAt !== (api.information_review?.checked_at ?? null) || t.apiStatus !== api.status || t.apiApprovalText !== api.approval_text || t.apiBaselineDraft !== aiDraft || JSON.stringify(t.apiChecks) !== JSON.stringify(api.checks) || JSON.stringify(t.apiEvidence) !== JSON.stringify(api.evidence);
  const editing = t && t.draft && (t.draft !== t.aiDraft || rewrites.has(t) || sends.has(t) || api.status === "ON_HOLD" ||
    (t.draftSpecialistRevision ?? 0) !== (api.specialist_revision ?? 0));
  Object.assign(target, {
    source: "api",
    specialistSaving: specialistWrites.has(target),
    regenerating: rewrites.has(target),
    sending: sends.has(target),
    translatingReply: replyTranslations.has(target),
    informationSaving: informationWrites.has(target),
    apiStatus: api.status,
    manualReply: Boolean(api.manual_reply),
    apiBaselineDraft: aiDraft,
    apiSendSource: displayDraft,
    title: inquiry?.subject || (inquiry?.body || "").slice(0, 40) || api.ticket_id,
    body: initialMessage?.body || inquiry?.body || "",
    apiClassification: api.classification,
    apiExtraction: api.extraction,
    apiRules: api.rules,
    fieldLabels: labels,
    analysisReady: Boolean(api.classification && api.extraction && api.rules && api.status !== "ANALYSIS_PENDING"),
    requiredInformation: required,
    infoChecks: checks,
    customerRevision: api.customer_revision ?? 0,
    reviewedReplyKey: currentReview?.reply_id || null,
    informationReviewedAt: api.information_review?.checked_at ?? null,
    channel: inquiry?.channel,
    apiCustomerId: inquiry?.customer_id,
    apiLanguage: inquiry?.language,
    product: api.product_code || "제품 미확인",
    country: inquiry?.country || "—",
    company: inquiry?.customer_id || "웹 고객",
    type: api.category ? CATEGORY_LABEL[api.category] || api.category : "미분류",
    secondaryType: api.classification?.secondary_category ? CATEGORY_LABEL[api.classification.secondary_category] || api.classification.secondary_category : null,
    priority: api.priority || "—",
    status: api.specialist_followup?.status === "in_progress" && !["WAITING_CUSTOMER", "RESOLVED", "REJECTED", "APPROVED"].includes(api.status) ? "사내 분석 중" : STATUS_LABEL[api.status] || api.status,
    sla: CLOSED.has(api.status) ? STATUS_LABEL[api.status] : slaText(api.sla_due_at),
    risk: Boolean(work?.at_risk),
    owner: api.assignee ? agents.get(api.assignee)?.name || api.assignee : "",
    department: api.assigned_dept || "",
    // 고객 언어 (원문 표시·발송 언어). 초안은 늘 영어다 (logic.composerLanguage)
    language: LANGUAGE_LABEL[inquiry?.language || "en"] || inquiry?.language || "English",
    replyLanguage: LANGUAGE_LABEL[inquiry?.language || "en"] || inquiry?.language || "English",
    receivedLabel: inquiry?.received_at ? receivedLabel(inquiry.received_at) : undefined,
    stage: CLOSED.has(api.status) ? 5 : 0,
    sent: api.status === "RESOLVED" || (api.status === "APPROVED" && Boolean(api.final_reply?.trim())),
    workflowVersion: 2,
    customerRequestStatus: api.status === "WAITING_CUSTOMER" ? "waiting" : latestReply ? "received" : "none",
    apiEvidence: api.evidence,
    apiCited: api.draft?.cited || [],
    approvalCited: api.approval_cited,
    investigationInfo: api.investigation_info || null,
    specialistFollowup: api.specialist_followup || null,
    specialistRequests: api.specialist_requests || [],
    specialistRevision: api.specialist_revision ?? 0,
    apiDraftSpecialistRevision: api.draft_specialist_revision ?? 0,
    apiDraftCustomerRevision: api.draft_customer_revision ?? 0,
    apiDraftInformationReviewedAt: api.draft_information_reviewed_at ?? null,
    apiChecks: api.checks,
    apiCheckedText: api.approval_text || api.draft?.text || "",
    apiApprovalText: api.approval_text,
    approvalError: api.approval_error,
    customerQc: api.customer_qc,
    resolution: api.resolution ? { ...api.resolution, confirmedBy: api.resolution.confirmed_by, confirmedAt: api.resolution.confirmed_at } : null,
    resolutionSuperseded: api.resolution?.superseded ?? false,
    apiInfoRequest: Boolean(api.info_request), // 지금 검토할 글이 백엔드 추가정보 요청문인가
    bodyKo: api.body_ko,
    finalReply: api.final_reply,
    translationError: api.translation_error,
  });
  const history = api.processing_history || [];
  const hasSentHistory = history.some((e) => e.kind === "sent");
  const hasCompletedHistory = history.some((e) => e.kind === "completed");
  target.events = target.events.filter((e) => !["processing-api", "assignment-api"].includes(e.source)
    && !(hasSentHistory && e.kind === "sent") && !(hasCompletedHistory && e.kind === "completed")
    && !(api.assignment_history && e.kind === "assignment"));
  for (const event of history) {
    const resolution = event.resolution ? { ...event.resolution,
      confirmedBy: event.resolution.confirmed_by, confirmedAt: event.resolution.confirmed_at,
      superseded: Boolean(api.resolution?.superseded || event.resolution.confirmed_at !== api.resolution?.confirmed_at),
    } : undefined;
    target.events.push({ ...event, source: "processing-api", createdAt: event.created_at,
      time: receivedLabel(event.created_at), masterText: event.master_text,
      replyLanguage: event.reply_language, resolution });
  }
  for (const event of api.assignment_history || []) {
    const name = (id: string | null) => id ? agents.get(id)?.name || id : "미배정";
    target.events.push({ kind: "assignment", source: "assignment-api", createdAt: event.created_at,
      actor: event.assigned_by || "system",
      text: `담당자 ${name(event.from_assignee)} → ${name(event.to_assignee)}${event.reason ? ` · ${event.reason}` : ""}` });
  }
  // Rebuild only server specialist events: polling is idempotent and cross-session history works.
  target.events = target.events.filter((e) => !["specialist-api", "resolution-api", "customer-api", "information-api"].includes(e.source));
  for (const reply of replies) target.events.push({ kind: "customer", id: reply.message_id, text: reply.body,
    createdAt: reply.received_at, time: receivedLabel(reply.received_at), actor: "customer", source: "customer-api",
    providedFields: reply.provided_fields, files: [], informationChecks: currentReview?.reply_id === reply.message_id ? currentReview.fields : undefined });
  for (const review of api.information_reviews || (currentReview ? [currentReview] : [])) target.events.push({
    kind: "information-reviewed", source: "information-api", replyId: review.reply_id, text: "수신 자료 확인",
    actor: review.reviewer, createdAt: review.checked_at, informationChecks: review.fields });
  for (const req of api.specialist_requests || []) {
    target.events.push({ kind: "escalation", id: req.request_id, request: req.text,
      text: `${DEPT_LABEL[req.to_dept] || req.to_dept} 검토 요청 기록`,
      department: DEPT_LABEL[req.to_dept] || req.to_dept, requestingDepartment: "글로벌 C/S 센터",
      actor: req.requested_by, createdAt: req.created_at, channel: req.channel,
      transmittedFiles: req.attachment_names, source: "specialist-api" });
    if (req.reply) target.events.push({ kind: "expert", id: req.reply.reply_id,
      requestId: req.request_id, text: req.reply.text, actor: req.reply.author,
      createdAt: req.reply.created_at, time: receivedLabel(req.reply.created_at), source: "specialist-api" });
  }
  if (api.resolution && !hasCompletedHistory) target.events.push({ kind: "completed", source: "resolution-api",
    text: api.resolution.outcome === "unconfirmed" ? "해결 여부 미확인 종결 · 처리 결과 저장" : "담당자 확인 · 처리 결과 저장 및 문의 완료",
    createdAt: api.resolution.confirmed_at, actor: api.resolution.confirmed_by, resolution: target.resolution });
  target.events.sort((a, b) => (a.createdAt || "").localeCompare(b.createdAt || ""));
  if (!editing) {
    target.draftSpecialistRevision = api.draft_specialist_revision ?? 0;
    target.draftCustomerRevision = api.draft_customer_revision ?? 0;
    target.draftInformationReviewedAt = api.draft_information_reviewed_at ?? null;
    target.draftCited = api.approval_cited ?? api.draft?.cited ?? [];
    target.aiDraft = aiDraft;
    target.draft = displayDraft;
    target.purpose = api.info_request ? "request" : "answer";
    target.composerPurpose = target.purpose;
    // 전문부서 요청서를 쓰는 중이면 그 칸을 닫지 않는다 (동기화·요청서 초안 응답이 덮지 않게)
    const writingExpert = target.activeComposer === "expert";
    const writingManual = isManualReplyTicket(target) && target.activeComposer === "customer";
    target.composerOpen = writingExpert || writingManual || Boolean(displayDraft);
    target.activeComposer = writingExpert ? "expert" : displayDraft || writingManual ? "customer" : null;
    target.draftVersion = displayDraft ? 1 : 0;
    target.draftOrigin = displayDraft ? "ai" : null;
    if (reviewChanged) target.reviewed = false;
    target.draftContext = displayDraft ? answerContext(target) : null;
    target.draftContextKey = displayDraft ? contextKey(target.draftContext) : null;
  }
  if (editing && target.draft === api.approval_text && api.approval_cited !== null && api.approval_cited !== undefined) {
    target.draftCited = api.approval_cited;
  }
  if (reviewChanged) target.reviewed = false;
  if (!target.events.some((e) => e.kind === "registered")) {
    target.events.push({ kind: "registered", text: `${inquiry?.channel || "WEB"} 문의 접수`, createdAt: inquiry?.received_at, actor: "system" });
  }
  // 다른 화면에서 발송한 문의는 이 화면 이력에 발송 기록이 없다. 완료 처리 창이 발송 기록으로 칸을
  // 미리 채우므로, 백엔드가 보낸 글(final_reply)이 있으면 발송 기록을 하나 넣는다.
  if (["APPROVED", "WAITING_CUSTOMER", "RESOLVED"].includes(api.status) && api.final_reply && !target.events.some((e) => e.kind === "sent")) {
    target.events.push({
      kind: "sent", text: api.final_reply, purpose: api.status === "WAITING_CUSTOMER" ? "request" : "answer",
      replyLanguage: api.final_reply_language, actor: target.owner || "system", source: "api",
    });
  }
  target.events.sort((a, b) => (a.createdAt || "").localeCompare(b.createdAt || ""));
  return target;
}

const snapshotKey = (t: Ticket | undefined) => JSON.stringify([t?.apiStatus, t?.aiDraft, t?.apiDraftSpecialistRevision, t?.specialistRevision, t?.customerRevision, t?.reviewedReplyKey, t?.informationReviewedAt, t?.specialistFollowup]);

// 완료 문의는 화면에서 선택한 동안만 갱신한다. 목록 전체를 상세 스토어에 넣지 않는다.
const selectedDetails = new Map<string, number>();
const detailLoads = new Map<string, Promise<Ticket>>();
export function watchTicketDetail(id: string): () => void {
  selectedDetails.set(id, (selectedDetails.get(id) || 0) + 1);
  return () => {
    const count = (selectedDetails.get(id) || 1) - 1;
    if (count) selectedDetails.set(id, count); else selectedDetails.delete(id);
  };
}
export function loadTicketDetail(id: string): Promise<Ticket> {
  const pending = detailLoads.get(id);
  if (pending) return pending;
  const before = snapshotKey(tickets.find((t) => t.id === id));
  const load = (async () => {
    const row = await api.ticket(id);
    const existing = tickets.find((t) => t.id === id);
    if (existing && (before !== snapshotKey(existing) || rewrites.has(existing) || specialistWrites.has(existing) || sends.has(existing) || informationWrites.has(existing) || replyTranslations.has(existing))) return existing;
    const result = apply(existing, row);
    if (!existing) tickets.unshift(result);
    commit();
    return result;
  })().finally(() => detailLoads.delete(id));
  detailLoads.set(id, load);
  return load;
}

let syncing = false;
export async function syncFromApi(): Promise<boolean> {
  if (syncing) return false;
  syncing = true;
  try {
    const [list, roster, answered, completed] = await Promise.all([api.workList(), api.agents(), api.answered(), api.completedPage("", false, 0, 1)]);
    setUi({ completedTotal: completed.total });
    agents = new Map(roster.map((a) => [a.agent_id, a]));
    // 담당자는 앞단 글로벌 C/S 센터 상담원 = 로그인 계정과 같은 이름 (agents.csv GCS_L1, CSA-53).
    // 팀 현황의 수용량은 명단의 max_open 을 따른다.
    for (const p of people) {
      const agent = roster.find((a) => a.name === p.name && a.active);
      if (agent?.max_open) p.capacity = agent.max_open;
    }
    workItems.clear();
    list.forEach((w) => workItems.set(w.ticket_id, w));
    const known = tickets.filter((t) => isApiTicket(t) && !CLOSED.has(t.apiStatus)).map((t) => t.id);
    // 작업 목록(열린 건) + 발송했고 완료 전인 건(다른 브라우저에서 발송했어도 완료 처리할 수 있게) + 이미 아는 건
    const ids = [...new Set([...list.map((w) => w.ticket_id), ...answered, ...known, ...selectedDetails.keys()])];

    const fetched = await Promise.all(ids.map(async (id) => {
      const before = snapshotKey(tickets.find((t) => t.id === id));
      try { return { id, row: await api.ticket(id), before, missing: false }; }
      catch (error) {
        return { id, row: null, before, missing: (error as { status?: number })?.status === 404 };
      }
    }));
    if (!online) {
      tickets.splice(0, tickets.length, ...tickets.filter(isApiTicket)); // 예시 티켓은 뺀다
      // 실제 문의는 agents.csv 담당자에게 자동 배정돼 로그인 상담원의 "내 담당"에 없을 수 있다
      setUi({ filter: "전체", queueScope: "전체" });
    }
    online = true;
    for (const { id, row, before, missing } of fetched) {
      if (!row) {
        const index = tickets.findIndex((t) => t.id === id);
        if (missing && index >= 0 && snapshotKey(tickets[index]) === before) {
          tickets.splice(index, 1);
          workItems.delete(id);
        }
        continue;
      }
      const existing = tickets.find((t) => t.id === row.ticket_id);
      // A mutation/rewrite completed after this poll started: retain the newer response.
      if (before !== snapshotKey(existing) || (existing && (rewrites.has(existing) || specialistWrites.has(existing) || sends.has(existing) || informationWrites.has(existing) || replyTranslations.has(existing)))) continue;
      const t = apply(existing, row);
      if (!existing) tickets.unshift(t);
    }
    const partial = fetched.some((r) => !r.row && !r.missing);
    setUi({ ticketSync: partial ? "error" : "ready", ticketSyncError: partial ? "일부 문의를 갱신하지 못했습니다." : "" });
    commit();
    return !partial;
  } catch {
    setUi({ ticketSync: "error", ticketSyncError: "문의 정보를 불러오지 못했습니다. 서버 연결을 확인해 주세요." });
    return false;
  } finally { syncing = false; }
}

export function startApiSync() {
  void syncFromApi();
  setInterval(() => void syncFromApi(), REFRESH_MS);
}

async function refresh(t: Ticket) {
  const row = await api.ticket(t.id);
  apply(t, row);
  commit();
  return row;
}

/** 고친 글이면 edit_approve, 아니면 approve. 미리 확인한 고객 언어 문구를 사용한다. */
export function specialistDraftStale(t: Ticket): boolean {
  return (t.draftSpecialistRevision ?? 0) !== (t.specialistRevision ?? 0);
}

export function isManualReplyTicket(t: Ticket): boolean {
  return isApiTicket(t) && (t.apiStatus === "HUMAN_QUEUE" || Boolean(t.manualReply));
}
export function replyPreviewKey(t: Ticket): string {
  return JSON.stringify([t.draft, t.apiLanguage, t.replyLanguage, t.purpose, t.customerRevision ?? 0, t.specialistRevision ?? 0, t.informationReviewedAt ?? null, t.apiEvidence, t.apiBaselineDraft]);
}
export function hasCurrentReplyPreview(t: Ticket): boolean {
  return Boolean(t.replyPreview?.final_text?.trim() && t.replyPreviewKey === replyPreviewKey(t));
}
export async function prepareReplyViaApi(t: Ticket): Promise<boolean> {
  if (replyTranslations.has(t) || t.sending || t.regenerating || !t.draft?.trim()) return false;
  let key = replyPreviewKey(t);
  const text = t.draft;
  replyTranslations.add(t); t.translatingReply = true; commit();
  try {
    if (isManualReplyTicket(t)) {
      const row = await api.manualReply(t.id, {
        text, reviewer: signedIn, expected_customer_revision: t.draftCustomerRevision ?? 0,
        expected_specialist_revision: t.draftSpecialistRevision ?? 0,
        expected_information_reviewed_at: t.draftInformationReviewedAt ?? null,
      });
      if (key !== replyPreviewKey(t)) { toast("작성 중인 내용이 변경되었습니다. 다시 확인해 주세요."); return false; }
      apply(t, row);
      key = replyPreviewKey(t);
    }
    const preview = await api.replyPreview(t.id, text);
    if (key !== replyPreviewKey(t)) { toast("초안이나 문의 정보가 변경되었습니다. 다시 변환해 주세요."); return false; }
    t.replyPreview = preview; t.replyPreviewKey = key; t.reviewed = false;
    toast("고객 언어 변환이 완료되었습니다. 발송용 문구를 확인하세요.");
    return true;
  } catch (e) {
    toast.error(`고객 언어 변환 실패: ${e}`); return false;
  } finally { replyTranslations.delete(t); t.translatingReply = false; commit(); }
}

export type SendOptions = { acknowledgedFailures?: boolean };
export async function sendViaApi(t: Ticket, options: SendOptions = {}): Promise<boolean> {
  if (sends.has(t) || !t.draft?.trim()) return false;
  if (t.purpose !== "request" && (waitingReviews(t).length || specialistDraftStale(t))) {
    toast.error("전문부서 회신을 모두 등록한 뒤 최신 회신으로 답변을 다시 작성하고 검토하세요.");
    return false;
  }
  if ((t.draftCustomerRevision ?? 0) !== (t.customerRevision ?? 0) ||
    (t.draftInformationReviewedAt ?? null) !== (t.informationReviewedAt ?? null)) {
    toast.error("새 고객 회신이 있습니다. 최신 회신을 반영해 답변을 다시 작성하세요."); return false;
  }
  if (!hasCurrentReplyPreview(t)) { toast.error("먼저 고객 언어로 변환한 내용을 확인하세요."); return false; }
  const text = t.draft, purpose = t.purpose, edited = text !== String(t.aiDraft || "");
  const sendEdit = edited || Boolean(t.apiSendSource && t.apiSendSource !== text);
  const reviewed = t.reviewed, previewKey = replyPreviewKey(t);
  sends.add(t); t.sending = true; t.customerQc = null; commit();
  try {
    const row = await api.act(t.id, {
      action: sendEdit ? "edit_approve" : "approve", ...(sendEdit ? { edited_text: text } : {}),
      reply_preview_id: t.replyPreview.preview_id,
      reviewer: signedIn, expected_specialist_revision: t.specialistRevision ?? 0, expected_customer_revision: t.draftCustomerRevision ?? 0, expected_information_reviewed_at: t.draftInformationReviewedAt ?? null,
      acknowledged_failures: Boolean(options.acknowledgedFailures),
    });
    const sent = ["APPROVED", "WAITING_CUSTOMER"].includes(row.status) && Boolean(row.final_reply?.trim());
    if (!sent) {
      apply(t, row);
      t.reviewed = Boolean(row.customer_qc?.decision === "ERROR" && reviewed && previewKey === replyPreviewKey(t));
      toast.error(row.approval_error || (row.translation_error
        ? "고객 언어 번역을 확인하지 못해 보류했습니다. 내용을 확인하고 다시 발송해 주세요."
        : "최종 점검 결과를 확인해 주세요. 답변은 발송되지 않았으며 작성 내용은 보존했습니다."));
      return false;
    }
    if (!row.processing_history?.some((e) => e.kind === "sent")) record(t, "sent", row.final_reply!, { purpose, masterText: text, edited,
      failuresAcknowledged: Boolean(options.acknowledgedFailures),
      replyLanguage: row.final_reply_language, approvedBy: signedIn, approvedAt: new Date().toISOString() });
    if (t.draft === text) { t.aiDraft = ""; t.draft = ""; }
    apply(t, row);
    toast(row.status === "WAITING_CUSTOMER" ? "추가정보 요청을 보냈습니다." : "답변을 발송했습니다.");
    return true;
  } catch (e) {
    toast.error(`발송 실패: ${e}`);
    return false;
  } finally {
    sends.delete(t); t.sending = false; commit();
  }
}

/** 처리 결과 기록 및 완료 → 해결 확정 (사례 저장). 로컬 처리 결과 기록은 actions.completeTicket 이 남긴다. */
export async function resolveViaApi(t: Ticket, input: ResolutionIn): Promise<boolean> {
  try {
    const row = await api.resolve(t.id, input);
    if (row.status !== "RESOLVED" || !row.resolution || row.resolution.superseded) {
      toast.error("처리 결과 저장을 확인하지 못했습니다. 입력 내용은 보존했습니다.");
      return false;
    }
    apply(t, row);
    commit();
    return row.status === "RESOLVED" && Boolean(row.resolution && !row.resolution.superseded);
  } catch (e) {
    toast.error(`완료 처리 실패: ${e}`);
    return false;
  }
}

/** 답변 초안 작성: 백엔드 티켓은 AI 초안을 쓴다. */
export function restoreAiDraft(t: Ticket) {
  if (isManualReplyTicket(t)) {
    t.draft ??= "";
    t.composerOpen = true; t.activeComposer = "customer";
    t.purpose = "answer"; t.composerPurpose = "answer";
    t.draftSpecialistRevision = t.specialistRevision ?? 0;
    t.draftCustomerRevision = t.customerRevision ?? 0;
    t.draftInformationReviewedAt = t.informationReviewedAt ?? null;
    t.reviewed = false; commit(); return;
  }
  if (specialistDraftStale(t) || (t.draftCustomerRevision ?? 0) !== (t.customerRevision ?? 0) || (t.draftInformationReviewedAt ?? null) !== (t.informationReviewedAt ?? null)) {
    if (waitingReviews(t).length) { toast("전문부서 회신을 모두 등록한 뒤 작성하세요."); return; }
    void rewriteViaApi(t, "Incorporate the latest customer information and all registered specialist replies as evidence. Distinguish confirmed findings from hypotheses and preserve applicable limitations.");
    return;
  }
  if (!t.aiDraft) {
    toast("AI 초안이 아직 없습니다. 분석이 끝나면 자동으로 들어옵니다.");
    return;
  }
  t.draft = t.aiDraft;
  t.draftSpecialistRevision = t.apiDraftSpecialistRevision ?? 0;
  t.draftCustomerRevision = t.apiDraftCustomerRevision ?? 0;
  t.draftInformationReviewedAt = t.apiDraftInformationReviewedAt ?? null;
  t.draftCited = t.apiCited || [];
  t.reviewed = false;
  t.composerOpen = true;
  t.activeComposer = "customer";
  commit();
}


const agentIdOf = (name: string) => [...agents.values()].find((a) => a.name === name && a.active)?.agent_id;

/** 백엔드가 같은 상태로 새 글을 쓴 뒤에는 화면의 "고치던 글"을 버리고 새 초안을 넣는다. */
function takeNewDraft(t: Ticket, row: ApiTicket) {
  t.draft = "";
  t.aiDraft = "";
  apply(t, row);
}

/** 담당자 변경 (앞단 상담원끼리). 성공하면 true — 화면 이력은 호출한 쪽이 남긴다. */
export async function reassignViaApi(t: Ticket, owner: string, reason: string): Promise<boolean> {
  const agentId = agentIdOf(owner);
  if (!agentId) {
    toast.error(`${owner || "미배정"}은(는) 담당자 명단에 없습니다.`);
    return false;
  }
  try {
    apply(t, await api.assign(t.id, { assignee: agentId, reason, by: signedIn }));
    commit();
    return true;
  } catch (e) {
    toast.error(`담당자 변경 실패: ${e}`);
    return false;
  }
}

/** 초안 수정 요청 → 백엔드가 같은 근거로 다시 쓴다 (rewrite). */
export async function rewriteViaApi(t: Ticket, instruction: string): Promise<boolean> {
  if (rewrites.has(t)) return false;
  if (waitingReviews(t).length) { toast("전문부서 회신을 모두 등록한 뒤 작성하세요."); return false; }
  rewrites.add(t);
  const previous = t.draft;
  const previousRevision = t.draftSpecialistRevision ?? 0;
  t.regenerating = true;
  commit();
  try {
    const row = await api.act(t.id, { action: "rewrite", feedback: instruction, reviewer: signedIn });
    if (row.status !== "READY_FOR_REVIEW" || !row.draft?.text ||
      (row.draft_specialist_revision ?? 0) !== (row.specialist_revision ?? 0) ||
      (row.specialist_revision ?? 0) < (t.specialistRevision ?? 0) ||
      (row.draft_customer_revision ?? 0) !== (row.customer_revision ?? 0) ||
      (row.customer_revision ?? 0) < (t.customerRevision ?? 0) ||
      (row.draft_information_reviewed_at ?? null) !== (row.information_review?.checked_at ?? null) ||
      (row.information_review?.checked_at ?? "") < (t.informationReviewedAt ?? "")) {
      apply(t, row);
      toast.error("새 답변을 생성하지 못했습니다. 기존 작성 내용은 보존했습니다. 다시 작성해 주세요.");
      return false;
    }
    const version = (t.draftVersion || 1) + 1;
    if (previous) record(t, "draft-replaced", "재작성 전 답변 보존", { draft: previous, specialistRevision: previousRevision });
    // Keep edits typed while the network request was in flight; expose the new AI draft separately.
    if (t.draft !== previous) {
      apply(t, row);
      t.aiDraft = row.draft?.text || "";
      t.pendingAnswer = { context: answerContext(t), draft: t.aiDraft, previous: t.draft,
        apiSpecialistRevision: row.draft_specialist_revision ?? 0, apiCustomerRevision: row.draft_customer_revision ?? 0, apiInformationReviewedAt: row.draft_information_reviewed_at ?? null, cited: row.draft?.cited || [] };
      openModal("answer-comparison", { id: t.id });
      toast("새 AI 초안을 받았습니다. 작성 중인 글은 보존했습니다. 초안 갱신에서 비교하세요.");
      return true;
    }
    takeNewDraft(t, row);
    t.draftVersion = version;
    t.draftRequests = [...(t.draftRequests || []), { version, instruction, applied: ["AI 재작성"] }];
    record(t, "draft-rewrite", `AI 초안 재작성 · ${instruction}`, { instruction, version });
    toast(`v${version} 초안을 다시 만들었습니다.`);
    return true;
  } catch (e) {
    toast.error(`초안 재작성 실패: ${e}`);
    return false;
  } finally {
    rewrites.delete(t);
    t.regenerating = false;
    commit();
  }
}

/** 추가정보 요청문 초안 (info_request). 승인하면 고객에게 가고 회신 대기가 된다. */
export async function infoRequestViaApi(t: Ticket): Promise<boolean> {
  if (rewrites.has(t)) return false;
  if (isManualReplyTicket(t)) {
    toast("사람 검토 답변은 담당자가 직접 작성해 주세요.");
    return false;
  }
  if (!["READY_FOR_REVIEW", "ON_HOLD"].includes(t.apiStatus)) {
    toast("검토 대기 또는 보류 중인 문의에서만 추가정보 요청문을 만들 수 있습니다.");
    return false;
  }
  rewrites.add(t);
  t.regenerating = true;
  commit();
  try {
    takeNewDraft(t, await api.act(t.id, { action: "info_request", reviewer: signedIn, info_items: [...new Set([...(t.specialistFollowup?.missing_fields || []), ...(t.investigationInfo?.missing_fields || []), ...(t.requiredInformation || []).filter((item: { id: string }) => !["provided", "confirmed"].includes(t.infoChecks?.[item.id]?.status)).map((item: { id: string }) => item.id)])] }));
    record(t, "draft", "추가정보 요청문 초안 생성", { purpose: "request" });
    toast("추가정보 요청문을 준비했습니다.");
    return true;
  } catch (e) {
    toast.error(`요청문 생성 실패: ${e}`);
    return false;
  } finally {
    rewrites.delete(t);
    t.regenerating = false;
    commit();
  }
}

/** 전문부서 요청서 AI 초안 (부서를 주면 그 부서용). 화면의 요청서 칸을 채운다. */
export async function escalationDraftViaApi(t: Ticket, deptLabel?: string): Promise<boolean> {
  t.expertDraftLoading = true;
  commit();
  try {
    const row = await api.escalationRequest(t.id, deptLabel ? deptCode(deptLabel) : undefined);
    apply(t, row);
    const req = row.escalation_request;
    if (req) {
      t.expertDraft = req.text;
      t.expertDraftDepartment = DEPT_LABEL[req.to_dept] ?? req.to_dept;
    }
    return true;
  } catch (e) {
    toast.error(`요청서 초안 생성 실패: ${e}`);
    return false;
  } finally {
    t.expertDraftLoading = false;
    commit();
  }
}


/** Stable client IDs survive a lost response/reload; duplicate clicks cannot create duplicate records. */
export async function specialistRequestViaApi(t: Ticket, input: { department: string; channel: string; body: string; files: string[] }): Promise<boolean> {
  if (specialistWrites.has(t)) return false;
  const body = { to_dept: deptCode(input.department), text: input.body.trim(), requested_by: signedIn,
    channel: input.channel, attachment_names: input.files };
  if (!body.text) return false;
  const key = JSON.stringify(body);
  if (t.pendingSpecialistRequest?.key !== key) t.pendingSpecialistRequest = { key, id: crypto.randomUUID() };
  specialistWrites.add(t);
  t.specialistSaving = true; commit();
  try {
    apply(t, await api.specialistRequest(t.id, { ...body, request_id: t.pendingSpecialistRequest.id }));
    delete t.pendingSpecialistRequest;
    return true;
  } catch (e) { toast.error(`검토 요청 저장 실패: ${e}`); return false; }
  finally { specialistWrites.delete(t); t.specialistSaving = false; commit(); }
}

export async function specialistReplyViaApi(t: Ticket, requestId: string, text: string): Promise<boolean> {
  if (specialistWrites.has(t) || !text.trim()) return false;
  const body = { text: text.trim(), author: signedIn };
  const key = JSON.stringify([requestId, body]);
  if (t.pendingSpecialistReply?.key !== key) t.pendingSpecialistReply = { key, id: crypto.randomUUID() };
  specialistWrites.add(t);
  t.specialistSaving = true; commit();
  try {
    apply(t, await api.specialistReply(t.id, requestId, { ...body, reply_id: t.pendingSpecialistReply.id }));
    delete t.pendingSpecialistReply;
    return true;
  } catch (e) { toast.error(`회신 저장 실패: ${e}`); return false; }
  finally { specialistWrites.delete(t); t.specialistSaving = false; commit(); }
}


/** Save review of one exact customer reply; never apply old form values to a newer reply. */
export async function informationReviewViaApi(t: Ticket, replyId: string, revision: number,
  fields: Record<string, InformationFieldReview>, expectedReviewedAt: string | null = t.informationReviewedAt ?? null): Promise<boolean> {
  if (informationWrites.has(t)) return false;
  if (expectedReviewedAt !== (t.informationReviewedAt ?? null) || revision !== t.customerRevision || t.events.findLast((e) => e.source === "customer-api")?.id !== replyId) {
    toast.error("새 고객 회신이 있습니다. 최신 회신을 열어 다시 확인해 주세요."); return false;
  }
  informationWrites.add(t); t.informationSaving = true; commit();
  try {
    apply(t, await api.informationReview(t.id, { reply_id: replyId, customer_revision: revision, expected_reviewed_at: expectedReviewedAt, reviewer: signedIn, fields }));
    return true;
  } catch (e) { toast.error(`자료 확인 저장 실패: ${e}`); return false; }
  finally { informationWrites.delete(t); t.informationSaving = false; commit(); }
}


/** 최신 회신 재해석/담당자 판정 확인은 서버 체크포인트에 저장한다. */
export async function specialistFollowupViaApi(t: Ticket, finding?: { reply_id: string; evidence: string }, expectedVersion?: string): Promise<boolean> {
  if (t.followupBusy) return false;
  t.followupBusy = true; commit();
  try {
    const row = finding ? await api.confirmSpecialistFinding(t.id, {
      source_version: expectedVersion || t.specialistFollowup.source_version, reviewer: signedIn, finding,
    }) : await api.analyzeSpecialistFollowup(t.id);
    apply(t, row); commit();
    if (!finding && row.specialist_followup?.error) { toast.error(row.specialist_followup.error); return false; }
    return true;
  } catch (e) { toast.error(`회신 확인 실패: ${e}`); return false; }
  finally { t.followupBusy = false; commit(); }
}
