// 레거시 click/submit 핸들러의 상태 변경을 함수로 분리했다. 모두 로컬 기록이며 외부 전송은 하지 않는다.
import { toast } from "sonner";
import {
  answerContext, buildExpertRequest, checkAssign, composeAnswer, composerKey, composerLanguage, contextIsNew, contextKey, customerLanguage, FRONTLINE, isEdited, needsLocalization, runChecks, translateText,
  informationAssessment, people, recommend, record, requiredInformation, resourceReason, signedIn, storeComposer, ticketProgress,
  waitingReviews,
} from "./logic";
import { closeModal, commit, openModal, setUi, tickets } from "./store";
import type { Ticket } from "./types";
import { isApiTicket, resolveViaApi, restoreAiDraft, sendViaApi } from "./api-sync";

const scrollToEditor = () => setTimeout(() => document.getElementById("answer-editor")?.scrollIntoView({ behavior: "smooth", block: "center" }), 60);

/* ───────── 초안 작성 ───────── */
export function switchComposer(t: Ticket, purpose: string, language = composerLanguage(t)) {
  storeComposer(t);
  t.activeComposer = "customer"; t.composerPurpose = purpose; t.responseLanguage = language; t.purpose = purpose;
  const saved = t.composerDrafts?.[composerKey(purpose, language)];
  for (const key of ["draft", "draftContext", "draftContextKey", "draftVersion", "draftOrigin", "ignoredContextKey", "draftOriginal", "draftRequests"])
    t[key] = saved?.[key] ?? (key === "draft" ? "" : key === "draftVersion" ? 0 : null);
  t.reviewed = false; t.pendingAnswer = null;
  commit(); scrollToEditor();
}

function applyGeneratedAnswer(t: Ticket, c: any, draft: string) {
  t.draft = draft; t.purpose = c.purpose; t.draftVersion = (t.draftVersion || 0) + 1; t.reviewed = false;
  t.draftContext = c; t.draftContextKey = contextKey(c); t.composerPurpose = c.purpose; t.responseLanguage = c.language;
  t.draftOrigin = "user-requested"; t.ignoredContextKey = null; t.draftOriginal = draft; t.draftRequests = [];
  storeComposer(t);
  record(t, "draft", c.purpose === "request" ? "문의 분석 기반 고객 질의서 초안 생성" : "분석·근거·검토 결과 기반 답변 초안 생성", { version: t.draftVersion, draft: t.draft, generationContext: c, generationMode: "local-preview" });
  commit();
  toast(c.purpose === "request" ? "누락 항목으로 요청문을 준비했습니다." : "선택한 분석·근거로 답변 초안을 준비했습니다.");
}

export function generate(t: Ticket, purpose?: string) {
  if (isApiTicket(t)) return restoreAiDraft(t); // 백엔드 티켓은 AI 초안 (CSA-61)
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

/* ───────── 피드백 루프: 담당자의 수정 지시로 초안을 다시 만든다 ───────── */
// 백엔드 review 단계의 rewrite(수정 지시) 동작을 흉내 낸다. 프로토타입은 아래 키워드 규칙만 반영하고, 연결되면 자유 문장을 LLM 이 반영한다.
export const QUICK_INSTRUCTIONS = ["더 짧게", "더 정중하게", "사과 문구 추가", "근거 명시", "단계별로 정리", "원인 미확정 강조"] as const;
const sentences = (p: string) => p.split(/(?<=[.!?])\s+/).filter(Boolean);

function applyInstruction(text: string, ask: string, refs: string[]) {
  let paras = text.split(/\n\n/);
  const applied: string[] = [], has = (re: RegExp) => re.test(ask);
  const close = () => paras.length - 1;
  if (has(/짧|간단|간결|줄여|요약|brief|short|concise/i)) {
    paras = paras.map((p, i) => (i === 0 || i === close() ? p : sentences(p)[0] || p)); applied.push("더 짧게");
  }
  if (has(/사과|죄송|apolog|sorry/i) && !/apologi[sz]e/i.test(text)) {
    paras.splice(1, 0, "We apologize for the inconvenience this issue has caused."); applied.push("사과 문구 추가");
  }
  if (has(/원인|확정|추정|단정|uncertain|unconfirmed/i) && !/not been confirmed|not confirmed/i.test(paras.join(" "))) {
    paras.splice(Math.max(1, close()), 0, "Please note that the root cause has not been confirmed yet. The information above is based on the evidence available so far."); applied.push("원인 미확정 강조");
  }
  if (has(/근거|출처|문서|reference|source/i) && refs.length && !/^Reference:/m.test(paras.join("\n"))) {
    paras.splice(Math.max(1, close()), 0, `Reference: ${refs.join(", ")}`); applied.push("근거 명시");
  }
  if (has(/단계|절차|순서|번호|step|list/i)) {
    let best = -1;
    paras.forEach((p, i) => { if (i > 0 && i < close() && sentences(p).length > 1 && (best < 0 || p.length > paras[best].length)) best = i; });
    if (best >= 0) { paras[best] = sentences(paras[best]).map((s, i) => `${i + 1}. ${s}`).join("\n"); applied.push("단계별로 정리"); }
  }
  if (has(/친절|부드|따뜻|friendly|warm/i)) {
    if (!/^(Hello|Dear)/.test(paras[0])) paras[0] = `Hello,\n\n${paras[0]}`;
    if (!/Thank you for your patience/.test(paras.join(" "))) paras.splice(close(), 0, "Thank you for your patience while we look into this."); applied.push("친절하게");
  }
  if (has(/정중|공손|격식|formal|polite/i)) {
    paras = paras.map((p) => p.replace(/\bwe'll\b/gi, "we will").replace(/\bcan't\b/gi, "cannot").replace(/\bdon't\b/gi, "do not"));
    if (!/^Dear/.test(paras[0])) paras[0] = `Dear Customer,\n\n${paras[0].replace(/^Hello,\n\n/, "")}`;
    if (!/Best regards/.test(paras.join(" "))) paras.push("Best regards,\nLS ELECTRIC Customer Support"); applied.push("더 정중하게");
  }
  return { text: paras.join("\n\n"), applied };
}

// BACKEND: 초안 수정 요청(피드백 루프)
// 필요: 검토 단계의 rewrite 동작 — 담당자의 수정 지시(feedback)를 받아 같은 근거로 초안을 다시 만든다(v+1). 지시 기록은 이력에 남긴다.
// 지금: applyInstruction() 이 키워드 몇 개(짧게·정중하게·친절하게·사과·근거 명시·단계별·원인 미확정)만 규칙으로 처리한다. 백엔드 티켓에서는 아직 막혀 있다.
export function regenerateDraft(t: Ticket, instruction: string) {
  const ask = instruction.trim();
  if (!t.draft || !ask || t.regenerating) return;
  if (isApiTicket(t)) { toast("백엔드 티켓의 수정 지시 재생성은 아직 연결되지 않았습니다."); return; }
  const refs = (t.draftContext?.references || []).map((r: any) => r.label);
  const out = applyInstruction(t.draft, ask, refs);
  if (!out.applied.length) { toast("지금은 짧게·정중하게·사과·근거·단계별·원인 미확정 지시만 반영합니다. 자유로운 문장은 백엔드가 연결되면 반영됩니다."); return; }
  if (out.text === t.draft) { toast(`이미 반영돼 있습니다 · ${out.applied.join(", ")}`); return; }
  t.regenerating = true; commit();
  setTimeout(() => {
    t.draft = out.text; t.draftOriginal = out.text; t.draftVersion = (t.draftVersion || 0) + 1; t.reviewed = false; t.regenerating = false;
    t.draftRequests = [...(t.draftRequests || []), { version: t.draftVersion, instruction: ask, applied: out.applied }];
    storeComposer(t);
    record(t, "draft-rewrite", `AI 초안 재작성 · ${ask}`, { instruction: ask, version: t.draftVersion, applied: out.applied });
    commit(); toast(`v${t.draftVersion} 초안을 다시 만들었습니다 · ${out.applied.join(", ")}`);
  }, 900);
}
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
  if (t.purpose !== "request" && (waitingReviews(t).length || t.legacyReviewPending)) return false; // 전문부서 회신을 기다리는 동안은 고객 답변을 발송하지 않는다
  return t.reviewed && (!isNew || t.ignoredContextKey === contextKey(answerContext(t)));
}
export function confirmSend(t: Ticket, feedback: { reason?: string; note?: string; acknowledgedFailures?: boolean } = {}) {
  if (isApiTicket(t)) { closeModal(); void sendViaApi(t); return; } // 백엔드로 승인·발송 (CSA-61)
  // 백엔드와 같은 순서: 담당자가 승인하면 고객 언어로 자동 변환해 발송한다(프로토타입은 정해진 문구만 옮기는 시뮬레이션).
  const sentText = needsLocalization(t) ? translateText(t.draft, "English", customerLanguage(t)) : t.draft;
  record(t, "sent", sentText, {
    purpose: t.purpose || "answer", draftVersion: t.draftVersion || 1, finalApprovedDraft: sentText, masterText: t.draft, replyLanguage: needsLocalization(t) ? customerLanguage(t) : composerLanguage(t),
    generationContext: t.draftContext || null, currentContext: answerContext(t), unreflectedContextAcknowledged: t.ignoredContextKey || null,
    approvedBy: signedIn, approvedAt: new Date().toISOString(),
    edited: isEdited(t), feedbackReason: isEdited(t) ? feedback.reason || null : null, feedbackNote: isEdited(t) ? feedback.note || null : null,
    checks: runChecks(t), failuresAcknowledged: !!feedback.acknowledgedFailures, rewrites: t.draftRequests || [],
  });
  if (t.purpose === "request") t.customerRequestStatus = "waiting";
  t.status = ticketProgress(t);
  delete t.composerDrafts?.[composerKey(t.purpose || "answer", composerLanguage(t))];
  t.draft = ""; t.draftOriginal = ""; t.draftRequests = []; t.composerOpen = false; t.reviewed = false;
  if (t.purpose !== "request") t.sent = true;
  closeModal(); commit(); toast("로컬 발송 이력에 기록했습니다.");
}

/* ───────── 폼 제출 ───────── */
export function createTicket(d: Record<string, any>, files: string[]): string {
  const p = recommend();
  // 서버 ID(T-...)와 잘못된 기존 값은 로컬 일련번호 계산에서 제외한다.
  const last = tickets.reduce((max, t) => {
    const match = /^CSV1-(\d+)$/.exec(t.id);
    return match ? (BigInt(match[1]) > max ? BigInt(match[1]) : max) : max;
  }, 0n);
  const id = "CSV1-" + String(last + 1n).padStart(6, "0");
  const n: Ticket = {
    id, title: d.title, product: d.product, country: d.country, company: d.company, email: d.email, type: d.type, replyLanguage: d.language, department: FRONTLINE,
    priority: ["불량", "반품"].includes(d.type) ? "P2" : "P3", status: p ? "진행 중" : "미배정", sla: "신규", owner: p?.name || "", language: "English",
    stage: 0, risk: false, events: [], files, draft: "", reviewed: false, workflowVersion: 2, customerRequestStatus: "none", body: d.body, channel: d.channel,
  };
  tickets.unshift(n);
  record(n, "registered", `${n.channel} 문의 등록${n.owner ? " · " + n.owner + " 자동 배정" : ""}`, { assignmentReason: resourceReason(p, n.id) });
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
  t.department = FRONTLINE;
  if (t.stage === 0) t.status = t.owner ? "진행 중" : "미배정";
  record(t, "assignment", `담당자 ${before || "미배정"} → ${t.owner}`);
  closeModal(); commit(); toast("담당자를 변경했습니다.");
}
const completing = new WeakSet<Ticket>();
export async function completeTicket(t: Ticket, d: Record<string, string>) {
  if (completing.has(t) || t.stage === 5) return;
  completing.add(t);
  const input = { ...d }, previousSla = t.sla;
  t.resolutionDraft = input;
  commit(); // 실패하거나 창을 다시 열어도 제출한 입력을 복구한다.
  try {
    const references = answerContext(t, "answer").references.map((r: any) => ({ id: r.id, label: r.label, kind: r.kind }));
    // 기존 완료 API가 성공한 경우에만 완료 이력과 상세 결과를 확정한다.
    if (isApiTicket(t) && !(await resolveViaApi(t))) return;
    t.preCompletionSla = previousSla;
    if (!isApiTicket(t)) {
      t.stage = 5; t.status = "완료"; t.sla = t.risk ? "기한 초과 완료" : "기한 내 완료";
    }
    t.resolutionSuperseded = false;
    t.resolution = {
      ...input, references, confirmedBy: signedIn, confirmedAt: new Date().toISOString(),
    };
    delete t.resolutionDraft;
    record(t, "completed", "담당자 확인 · 처리 결과 저장 및 티켓 완료", { resolution: t.resolution, actor: signedIn });
    closeModal(); commit(); toast("처리 결과를 저장했습니다.");
  } finally {
    completing.delete(t);
  }
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
  t.department = FRONTLINE;
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

/** 목록에서 고른 여러 티켓을 한 담당자에게 배정한다. 수용량이 가득 찬 경우에는 건너뛰고 사유를 알린다. */
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
