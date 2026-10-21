// 레거시 click/submit 핸들러의 상태 변경을 함수로 분리했다. 모두 로컬 기록이며 외부 전송은 하지 않는다.
import { toast } from "sonner";
import {
  answerContext, buildExpertRequest, checkAssign, composeAnswer, composerKey, composerLanguage, contextIsNew, contextKey, customerLanguage, departmentFor, needsLocalization, translateText,
  departmentTickets, informationAssessment, people, recommend, record, requiredInformation, resourceReason, signedIn, storeComposer, ticketProgress,
  waitingReviews,
} from "./logic";
import { closeModal, commit, openModal, setUi, tickets } from "./store";
import type { Ticket } from "./types";

const scrollToEditor = () => setTimeout(() => document.getElementById("answer-editor")?.scrollIntoView({ behavior: "smooth", block: "center" }), 60);

/* ───────── 초안 작성 ───────── */
export function switchComposer(t: Ticket, purpose: string, language = composerLanguage(t)) {
  storeComposer(t);
  t.activeComposer = "customer"; t.composerPurpose = purpose; t.responseLanguage = language; t.purpose = purpose;
  const saved = t.composerDrafts?.[composerKey(purpose, language)];
  for (const key of ["draft", "draftContext", "draftContextKey", "draftVersion", "draftOrigin", "ignoredContextKey"])
    t[key] = saved?.[key] ?? (key === "draft" ? "" : key === "draftVersion" ? 0 : null);
  t.reviewed = false; t.pendingAnswer = null;
  commit(); scrollToEditor();
}

function applyGeneratedAnswer(t: Ticket, c: any, draft: string) {
  t.draft = draft; t.purpose = c.purpose; t.draftVersion = (t.draftVersion || 0) + 1; t.reviewed = false;
  t.draftContext = c; t.draftContextKey = contextKey(c); t.composerPurpose = c.purpose; t.responseLanguage = c.language;
  t.draftOrigin = "user-requested"; t.ignoredContextKey = null;
  storeComposer(t);
  record(t, "draft", c.purpose === "request" ? "문의 분석 기반 추가정보 요청 초안 생성" : "분석·근거·검토 결과 기반 답변 초안 생성", { version: t.draftVersion, draft: t.draft, generationContext: c, generationMode: "local-preview" });
  commit();
  toast(c.purpose === "request" ? "누락 항목으로 요청문을 준비했습니다." : "선택한 분석·근거로 답변 초안을 준비했습니다.");
}

export function generate(t: Ticket, purpose?: string) {
  const full = answerContext(t, purpose);
  const c = full.purpose === "request"
    ? { ...full, references: [], availableReferences: [], technical: { documents: [], similarCases: [], possibleCause: null, recommendation: null, causeConfirmed: false }, expertResponse: null }
    : full;
  if (c.purpose === "request" && !c.missingInfo.length) { toast("현재 요청할 누락 항목이 없습니다. 문의 정보를 먼저 확인하세요."); return; }
  const draft = composeAnswer(c);
  if (t.draft && t.draftContextKey === contextKey(c)) { scrollToEditor(); return; }
  if (t.draft && c.purpose === "request") {
    t.requestDraftVersions ??= [];
    t.requestDraftVersions.push({ draft: t.draft, context: t.draftContext, version: t.draftVersion, language: composerLanguage(t), savedAt: new Date().toISOString() });
    applyGeneratedAnswer(t, c, draft); return;
  }
  if (t.draft) { t.pendingAnswer = { context: c, draft, previous: t.draft }; commit(); openModal("answer-comparison", { id: t.id }); return; }
  applyGeneratedAnswer(t, c, draft);
}

export function composeFromCopilot(t: Ticket, purpose: string) {
  setUi({ tab: "문의·답변" });
  t.composerOpen = true;
  switchComposer(t, purpose);
  if (!t.draft || (purpose === "request" && contextIsNew(t))) generate(t, purpose);
  scrollToEditor();
}
export function openExpertComposer(t: Ticket) {
  setUi({ tab: "문의·답변" });
  t.activeComposer = "expert"; t.expertDraft ??= buildExpertRequest(t); t.reviewed = false;
  commit(); scrollToEditor();
}
export function closeComposer(t: Ticket) { t.activeComposer = null; t.composerOpen = false; commit(); }

export function applyPendingAnswer(t: Ticket) {
  const p = t.pendingAnswer;
  if (!p) return;
  record(t, "draft-replaced", "초안 갱신 전 작성 내용", { draft: t.draft });
  t.pendingAnswer = null; closeModal();
  applyGeneratedAnswer(t, p.context, p.draft);
}
export function keepCurrentAnswer(t: Ticket) {
  const p = t.pendingAnswer;
  if (!p) return;
  t.ignoredContextKey = contextKey(p.context);
  record(t, "draft-retained", "새 검토 결과 확인 · 현재 답변 유지", { generationContext: p.context, draft: t.draft });
  t.pendingAnswer = null; closeModal(); commit();
}
export function editDraft(t: Ticket, value: string) { t.draft = value; t.reviewed = false; commit(); }
export function setReviewed(t: Ticket, checked: boolean) {
  t.reviewed = checked;
  if (checked) t.ignoredContextKey = contextKey(answerContext(t));
  commit();
}
export function toggleReference(t: Ticket, id: string, checked: boolean) {
  const ids = new Set<string>(answerContext(t).references.map((r: any) => r.id));
  checked ? ids.add(id) : ids.delete(id);
  t.answerReferenceIds = [...ids]; t.reviewed = false; commit();
}

export function canSend(t: Ticket) {
  const isNew = contextIsNew(t);
  return t.reviewed && (!isNew || t.ignoredContextKey === contextKey(answerContext(t)));
}
export function confirmSend(t: Ticket) {
  // 백엔드와 같은 순서: 담당자가 승인하면 고객 언어로 자동 변환해 발송한다(프로토타입은 정해진 문구만 옮기는 시뮬레이션).
  const sentText = needsLocalization(t) ? translateText(t.draft, "English", customerLanguage(t)) : t.draft;
  record(t, "sent", sentText, {
    purpose: t.purpose || "answer", draftVersion: t.draftVersion || 1, finalApprovedDraft: sentText, masterText: t.draft, replyLanguage: needsLocalization(t) ? customerLanguage(t) : composerLanguage(t),
    generationContext: t.draftContext || null, currentContext: answerContext(t), unreflectedContextAcknowledged: t.ignoredContextKey || null,
    approvedBy: signedIn, approvedAt: new Date().toISOString(),
  });
  if (t.purpose === "request") t.customerRequestStatus = "waiting";
  t.status = ticketProgress(t);
  delete t.composerDrafts?.[composerKey(t.purpose || "answer", composerLanguage(t))];
  t.draft = ""; t.composerOpen = false; t.reviewed = false;
  if (t.purpose !== "request") t.sent = true;
  closeModal(); commit(); toast("로컬 발송 이력에 기록했습니다.");
}

/* ───────── 폼 제출 ───────── */
export function createTicket(d: Record<string, any>, files: string[]): string {
  const p = recommend(d.product, "English");
  const id = "CSV1-" + String(Math.max(...tickets.map((t) => +t.id.split("-")[1])) + 1).padStart(6, "0");
  const n: Ticket = {
    id, title: d.title, product: d.product, country: d.country, company: d.company, email: d.email, type: d.type, replyLanguage: d.language, department: departmentFor(d.product),
    priority: ["불량", "반품"].includes(d.type) ? "P2" : "P3", status: p ? "진행 중" : "미배정", sla: "신규", owner: p?.name || "", language: "English",
    stage: 0, risk: false, events: [], files, draft: "", reviewed: false, workflowVersion: 2, customerRequestStatus: "none", body: d.body, channel: d.channel,
  };
  tickets.unshift(n);
  record(n, "registered", `${n.channel} 문의 등록${n.owner ? " · " + n.owner + " 자동 배정" : ""}`, { assignmentReason: resourceReason(p, n.product, n.language, n.id) });
  closeModal(); commit(); toast("티켓을 등록했습니다.");
  return id;
}

export function saveInfoReview(t: Ticket, replyId: string, values: Record<string, { status: string; evidence: string }>) {
  const reply = t.events.find((x) => x.id === replyId && ["customer", "customer-followup"].includes(x.kind));
  if (!reply) return;
  const checks: Record<string, any> = {};
  for (const item of requiredInformation(t)) {
    const v = values[item.id], evidence = (v?.evidence || "").trim();
    if (!v || !["missing", "unusable", "confirmed"].includes(v.status) || (v.status === "confirmed" && !evidence)) { toast("확인 완료 항목의 근거를 입력하세요."); return; }
    checks[item.id] = { status: v.status, evidence, confirmedBy: v.status === "confirmed" ? signedIn : null, checkedAt: new Date().toISOString() };
  }
  t.infoChecks = { ...(t.infoChecks || {}), ...checks }; t.reviewedReplyKey = reply.id; t.reviewed = false;
  record(t, "information-reviewed", "수신 자료 확인", { replyId: reply.id, informationChecks: checks, actor: signedIn });
  closeModal(); commit();
  toast(informationAssessment(t).some((x) => x.status !== "confirmed") ? "확인 완료 · 남은 자료가 있습니다." : "요청 자료 확인 완료");
}

export function submitExpertRequest(t: Ticket, d: { department: string; channel: string; body: string; files: string[] }) {
  t.status = ticketProgress(t); t.reviewed = false;
  record(t, "escalation", `${d.department} 검토 요청 기록`, { request: d.body, channel: d.channel, department: d.department, actor: signedIn, transmittedFiles: d.files, requestContext: answerContext(t, "answer") });
  t.activeComposer = null; t.expertDraft = null; t.expertDraftFiles = [];
  closeModal(); commit(); toast("검토 요청을 기록했습니다.");
}
export function submitExpertReply(target: Ticket, selected: string, body: string) {
  if (!(selected === "legacy" && target.legacyReviewPending) && !waitingReviews(target).some((x) => x.id === selected)) { toast("회신 대기 요청을 선택하세요."); return; }
  target.status = ticketProgress(target);
  if (selected === "legacy") target.legacyReviewPending = false;
  target.reviewed = false;
  record(target, "expert", body, { requestId: selected === "legacy" ? null : selected, actor: signedIn });
  closeModal(); commit(); toast("전문부서 회신을 등록했습니다.");
}
export function assignOwner(t: Ticket, owner: string) {
  const before = t.owner;
  t.owner = owner;
  t.department = people.find((p) => p.name === owner)?.department || departmentFor(t.product);
  if (t.stage === 0) t.status = t.owner ? "진행 중" : "미배정";
  record(t, "assignment", `담당자 ${before || "미배정"} → ${t.owner}`);
  closeModal(); commit(); toast("담당자를 변경했습니다.");
}
export function autoAssignDepartment(department: string) {
  const list = departmentTickets(department).filter((t) => !t.owner);
  let assigned = 0;
  for (const t of list) {
    const p = recommend(t.product, t.language);
    if (p) {
      t.owner = p.name; t.department = p.department; t.status = "진행 중";
      record(t, "assignment", `${p.name} 시스템 자동 배정`, { assignmentReason: resourceReason(p, t.product, t.language, t.id) });
      assigned++;
    }
  }
  commit();
  toast(`${assigned}건 자동 배정${list.length - assigned ? " · " + (list.length - assigned) + "건은 배정 조건 확인 필요" : ""}`);
}
export function completeTicket(t: Ticket, d: Record<string, string>) {
  t.preCompletionSla = t.sla; t.stage = 5; t.status = "완료"; t.sla = t.risk ? "기한 초과 완료" : "기한 내 완료"; t.resolutionSuperseded = false;
  t.resolution = {
    outcome: d.outcome, references: answerContext(t, "answer").references.map((r: any) => ({ id: r.id, label: r.label, kind: r.kind })),
    cause: d.cause, action: d.action, result: d.result, verification: d.verification, confirmedBy: signedIn, confirmedAt: new Date().toISOString(),
  };
  record(t, "completed", "담당자 확인 · 처리 결과 저장 및 티켓 완료", { resolution: t.resolution, actor: signedIn });
  closeModal(); commit(); toast("처리 결과를 저장했습니다.");
}
export function toggleTranslate(t: Ticket) { t.translate = !t.translate; commit(); }
export function openCompletion(t: Ticket) {
  if (!t.sent || t.stage === 5) { toast("답변 발송 후 최종 처리 결과를 확인해 주세요."); return; }
  openModal("completion", { id: t.id });
}

/** 리소스 보드에서 담당자를 바꾼다. 검증은 호출하는 쪽에서 checkAssign 으로 한다. */
export function moveTicket(t: Ticket, owner: string, opts: { silent?: boolean } = {}) {
  if (t.owner === owner) return;
  const before = t.owner, beforeDept = t.department, beforeStatus = t.status;
  t.owner = owner;
  t.department = people.find((p) => p.name === owner)?.department || departmentFor(t.product);
  if (t.stage === 0) t.status = owner ? "진행 중" : "미배정";
  record(t, "assignment", `담당자 ${before || "미배정"} → ${owner || "미배정"} (리소스 배정)`);
  commit();
  if (opts.silent) return;
  toast(`${t.id} · ${owner || "미배정"}으로 변경했습니다.`, {
    action: {
      label: "되돌리기",
      onClick: () => {
        t.owner = before; t.department = beforeDept; t.status = beforeStatus;
        record(t, "assignment", `담당자 ${owner || "미배정"} → ${before || "미배정"} (되돌림)`);
        commit();
      },
    },
  });
}

/** 목록에서 고른 여러 티켓을 한 담당자에게 배정한다. 조건에 맞지 않는 티켓은 건너뛰고 사유를 알린다. */
export function bulkAssign(ids: string[], owner: string) {
  const p = people.find((x) => x.name === owner);
  if (!p) return;
  const failed: string[] = [];
  let done = 0;
  for (const id of ids) {
    const t = tickets.find((x) => x.id === id);
    if (!t || t.stage === 5 || t.owner === owner) continue;
    const v = checkAssign(t, p);
    if (!v.ok) { failed.push(`${t.id}: ${v.reason}`); continue; }
    moveTicket(t, owner, { silent: true });
    done++;
  }
  if (failed.length) toast.error(`${done}건 배정, ${failed.length}건 제외`, { description: failed.slice(0, 3).join("\n") });
  else toast(`${done}건을 ${owner}에게 배정했습니다.`);
}

/** 티켓 상세를 열면 고객 회신을 읽은 것으로 표시한다. */
export function markSeen(t: Ticket) {
  t.seenAt = new Date().toISOString();
  commit();
}
