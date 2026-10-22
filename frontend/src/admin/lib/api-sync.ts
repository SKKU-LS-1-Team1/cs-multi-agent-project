// 관리자 화면 ↔ 백엔드 API 연결 (CSA-61 · 담당 김동규). 페이지·디자인(CSA-59 · 김도연)은 그대로 두고
// 데이터만 잇는다.
//
// - startApiSync(): 백엔드 작업 목록(GET /api/tickets)과 각 티켓(GET /api/tickets/{id})을 10초마다 읽어
//   프로토타입 Ticket 모양으로 store.tickets 에 넣는다. 백엔드에 처음 닿으면 예시 티켓은 빼고
//   실제 문의만 보이고 목록은 "전체" 탭으로 연다. 백엔드가 없으면(프로토타입만 띄움) 예시 티켓으로
//   그대로 동작한다.
// - 백엔드 티켓(source "api")에서 API 로 보내는 동작 (actions.ts 가 여기로 넘긴다)
//   · 승인 및 발송 → POST /action  approve (AI 초안 그대로) / edit_approve (고친 글)
//     추가정보 요청문 초안이면 승인 후 고객 회신 대기(WAITING_CUSTOMER)가 된다.
//     고객 언어 번역은 백엔드가 승인 뒤에 한다. 번역 확인이 실패하면 보류(ON_HOLD) → 다시 발송.
//   · 처리 결과 기록 및 완료 → POST /resolve (해결 사례로 남는다)
//   · 답변 초안 작성 → 로컬 문구를 만들지 않고 AI 초안(aiDraft)을 다시 넣는다
// - 화면 표시: 원문 언어(language)·접수 시각(receivedLabel)·한국어 번역(bodyKo, "한국어 번역" 토글)·
//   근거 문서(apiEvidence → logic.answerContext 의 관련 기술문서)
// - 담당자 배정·전문부서 요청·자료 확인은 아직 로컬 기록이다 (담당자는 백엔드 자동 배정을 보여 준다).
import { toast } from "sonner";
import { api, type Agent, type Ticket as ApiTicket, type WorkItem } from "../../api/client";
import { answerContext, contextKey, record, signedIn } from "./logic";
import { commit, setUi, tickets } from "./store";
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

let agents = new Map<string, Agent>();
let online = false;
const workItems = new Map<string, WorkItem>();

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
function apply(t: Ticket | undefined, api: ApiTicket): Ticket {
  const inquiry = api.inquiry;
  const work = workItems.get(api.ticket_id);
  // 검토 대기면 AI 초안(또는 추가정보 요청문), 번역 확인 실패로 보류됐으면 승인했던 글 (다시 발송)
  const aiDraft =
    api.status === "READY_FOR_REVIEW" ? api.info_request || api.draft?.text || ""
    : api.status === "ON_HOLD" && api.translation_error ? api.approved_reply || ""
    : "";
  const target = t ?? ({ id: api.ticket_id, events: [], files: [], reviewed: false, source: "api" } as unknown as Ticket);
  const reviewChanged = !t || t.apiStatus !== api.status || t.aiDraft !== aiDraft || JSON.stringify(t.apiChecks) !== JSON.stringify(api.checks) || JSON.stringify(t.apiEvidence) !== JSON.stringify(api.evidence);
  const editing = t && t.draft && t.draft !== t.aiDraft && t.apiStatus === api.status;
  Object.assign(target, {
    source: "api",
    apiStatus: api.status,
    title: inquiry?.subject || (inquiry?.body || "").slice(0, 40) || api.ticket_id,
    body: inquiry?.body || "",
    channel: inquiry?.channel,
    product: api.product_code || "제품 미확인",
    country: inquiry?.country || "—",
    company: inquiry?.customer_id || "웹 고객",
    type: api.category ? CATEGORY_LABEL[api.category] || api.category : "미분류",
    priority: api.priority || "—",
    status: STATUS_LABEL[api.status] || api.status,
    sla: CLOSED.has(api.status) ? "기한 내 완료" : slaText(api.sla_due_at),
    risk: Boolean(work?.at_risk),
    owner: api.assignee ? agents.get(api.assignee)?.name || api.assignee : "",
    department: api.assigned_dept || "",
    // 고객 언어 (원문 표시·발송 언어). 초안은 늘 영어다 (logic.composerLanguage)
    language: LANGUAGE_LABEL[inquiry?.language || "en"] || inquiry?.language || "English",
    replyLanguage: LANGUAGE_LABEL[inquiry?.language || "en"] || inquiry?.language || "English",
    receivedLabel: inquiry?.received_at ? receivedLabel(inquiry.received_at) : undefined,
    stage: CLOSED.has(api.status) ? 5 : 0,
    sent: ["APPROVED", "RESOLVED"].includes(api.status),
    workflowVersion: 2,
    customerRequestStatus: api.status === "WAITING_CUSTOMER" ? "waiting" : "none",
    apiEvidence: api.evidence,
    apiChecks: api.checks,
    bodyKo: api.body_ko,
    finalReply: api.final_reply,
    translationError: api.translation_error,
  });
  if (!editing) {
    target.aiDraft = aiDraft;
    target.draft = aiDraft;
    target.purpose = api.info_request ? "request" : "answer";
    target.composerPurpose = target.purpose;
    target.composerOpen = Boolean(aiDraft);
    target.activeComposer = aiDraft ? "customer" : null;
    target.draftVersion = aiDraft ? 1 : 0;
    target.draftOrigin = aiDraft ? "ai" : null;
    if (reviewChanged) target.reviewed = false;
    target.draftContextKey = aiDraft ? contextKey(answerContext(target)) : null;
  }
  if (reviewChanged) target.reviewed = false;
  if (!target.events.length) {
    target.events.push({ kind: "registered", text: `${inquiry?.channel || "WEB"} 문의 접수 · AI 분석`, createdAt: inquiry?.received_at, actor: "system" });
  }
  return target;
}

export async function syncFromApi(): Promise<boolean> {
  try {
    const [list, roster] = await Promise.all([api.workList(), api.agents()]);
    agents = new Map(roster.map((a) => [a.agent_id, a]));
    workItems.clear();
    list.forEach((w) => workItems.set(w.ticket_id, w));
    const known = tickets.filter(isApiTicket).map((t) => t.id);
    const ids = [...new Set([...list.map((w) => w.ticket_id), ...known])];
    const fetched = await Promise.all(ids.map((id) => api.ticket(id).catch(() => null)));
    if (!online) {
      tickets.splice(0, tickets.length, ...tickets.filter(isApiTicket)); // 예시 티켓은 뺀다
      // 실제 문의는 agents.csv 담당자에게 자동 배정돼 로그인 상담원의 "내 담당"에 없을 수 있다
      setUi({ filter: "전체", queueScope: "전체" });
    }
    online = true;
    for (const row of fetched) {
      if (!row) continue;
      const existing = tickets.find((t) => t.id === row.ticket_id);
      const t = apply(existing, row);
      if (!existing) tickets.unshift(t);
    }
    commit();
    return true;
  } catch {
    return false; // 백엔드가 없으면 프로토타입(예시 티켓)으로 둔다
  }
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

/** 승인 및 발송: 고친 글이면 edit_approve, 아니면 approve. 번역은 백엔드가 승인 뒤에 한다. */
export async function sendViaApi(t: Ticket): Promise<boolean> {
  const edited = t.draft.trim() !== String(t.aiDraft || "").trim();
  try {
    const row = await api.act(t.id, edited ? { action: "edit_approve", edited_text: t.draft, reviewer: signedIn } : { action: "approve", reviewer: signedIn });
    t.aiDraft = "";
    t.draft = "";
    apply(t, row);
    if (row.status === "ON_HOLD" && row.translation_error) {
      toast.error("고객 언어 번역을 확인하지 못해 보류했습니다. 다시 발송하면 번역을 재시도합니다.");
    } else {
      record(t, "sent", row.final_reply || "", { purpose: t.purpose, replyLanguage: row.final_reply_language, approvedBy: signedIn, approvedAt: new Date().toISOString() });
      toast(row.status === "WAITING_CUSTOMER" ? "추가정보 요청을 보냈습니다." : "답변을 발송했습니다.");
    }
    commit();
    return ["APPROVED", "WAITING_CUSTOMER"].includes(row.status);
  } catch (e) {
    toast.error(`발송 실패: ${e}`);
    return false; // 실패 시 작성 중인 내용을 유지한다.
  }
}

/** 처리 결과 기록 및 완료 → 해결 확정 (사례 저장). 로컬 처리 결과 기록은 actions.completeTicket 이 남긴다. */
export async function resolveViaApi(t: Ticket): Promise<boolean> {
  try {
    const row = await api.resolve(t.id);
    apply(t, row);
    commit();
    return row.status === "RESOLVED";
  } catch (e) {
    toast.error(`완료 처리 실패: ${e}`);
    return false;
  }
}

/** 답변 초안 작성: 백엔드 티켓은 AI 초안을 쓴다. */
export function restoreAiDraft(t: Ticket) {
  if (!t.aiDraft) {
    toast("AI 초안이 아직 없습니다. 분석이 끝나면 자동으로 들어옵니다.");
    return;
  }
  t.draft = t.aiDraft;
  t.reviewed = false;
  t.composerOpen = true;
  t.activeComposer = "customer";
  commit();
}
