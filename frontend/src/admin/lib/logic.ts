// 레거시 app.js 의 업무 규칙(집계·배정·답변 컨텍스트·초안 문구)을 그대로 옮긴 순수 로직.
import { caseCatalog } from "@admin/data/knowledge-data";
import { ACCOUNTS, currentAccount } from "./auth";
import { onBeforeCommit, save, tickets } from "./store";
import type { Ev, Person, Ticket } from "./types";

/** 로그인한 사람의 고유번호(계정 키). */
export const signedInId = currentAccount()?.userId ?? ACCOUNTS[0].userId;
export const signedIn = currentAccount()?.name ?? ACCOUNTS[0].name; // 로그인한 사람(로그인·로그아웃은 화면을 다시 불러오므로 상수로 충분하다)
/** 팀장: 팀원이면서 배정을 맡는다. 이름 옆에 "팀장"으로 표시한다. */
export const teamLead = ACCOUNTS.find((a) => a.role === "LEAD")!.name; // 역할이 팀장인 계정
/** 실제 배정(담당자 변경·재배정·일괄 배정)은 팀장만 할 수 있다. 팀원은 화면을 모두 볼 수 있지만 배정 버튼이 없다. */
export const canAssign = signedIn === teamLead;
/** 이 도구를 쓰는 상담원은 모두 앞단(L1) 글로벌 C/S 센터 소속이다. 자동화·저압 기술지원 등은 전문부서 요청을 받는 쪽이다. */
export const FRONTLINE = "글로벌 C/S 센터";

export const people: Person[] = [
  { name: "Minji Park", userId: ACCOUNTS.find((a) => a.name === "Minji Park")!.userId, rank: "과장", department: FRONTLINE, capacity: 6, available: true },
  { name: "Doyeon Kim", userId: ACCOUNTS.find((a) => a.name === "Doyeon Kim")!.userId, rank: "팀장", department: FRONTLINE, capacity: 6, available: true },
  { name: "Jun Lee", userId: ACCOUNTS.find((a) => a.name === "Jun Lee")!.userId, rank: "대리", department: FRONTLINE, capacity: 6, available: true },
  { name: "Hana Choi", userId: ACCOUNTS.find((a) => a.name === "Hana Choi")!.userId, rank: "사원", department: FRONTLINE, capacity: 6, available: true },
];

const phraseMap: Record<string, string> = {
  "Over-current trip immediately at run command": "운전 명령 직후 과전류 트립",
  "Over-current trip even with motor disconnected": "모터 분리 후에도 과전류 트립",
  "Over-current trip during acceleration": "가속 중 과전류 트립",
  "Motor cable insulation breakdown (phase-to-phase short)": "모터 케이블 절연 손상 · 상간 단락",
  "Supply voltage above tolerance (> 528 V)": "전원 전압 허용 범위 초과 가설",
  "Output IGBT module damaged": "출력 IGBT 모듈 손상",
  "Replace damaged motor cable section": "손상된 모터 케이블 구간 교체",
  "Replace power module under RMA": "RMA를 통한 전력 모듈 교체",
  RESOLVED_ONSITE: "현장 조치 완료",
  REPLACED_UNDER_RMA: "RMA 교체 후 현장 확인",
  RESOLVED_NORMAL_OPERATION: "정상 운전 복귀",
  PART_REPLACED: "부품 교체 후 정상 운전",
  "Disconnect motor cable, megger test cable and motor at 1,000 V": "모터 케이블 분리 후 케이블·모터 절연 검사 수행(원문 기록: 1,000 V)",
  "Diode test on output terminals U/V/W shows short circuit": "출력 단자 U/V/W의 다이오드 검사에서 단락 확인",
  SITE_CONDITION: "설치·사용 환경",
  HARDWARE: "하드웨어",
  WEAR_PART: "소모·마모 부품",
  TS_AUTO: "자동화 기술지원",
  TS_LV: "저압 기술지원",
  FIELD_SVC: "현장 서비스",
  WARRANTY_DESK: "보증·RMA 담당",
  QA_CLAIM: "품질 클레임",
  "Advise customer on site conditions and periodic inspection.": "사용 환경 및 정기 점검 안내",
  "Quality feedback sent to factory for lot analysis.": "생산 부서에 로트 분석을 위한 품질 피드백 전달",
};
export const translated = (x: any): string => phraseMap[x] || x || "미기록";

export type CaseRow = { id: string; ticketId: string; title: string; product: string; symptom: string; cause: string; action: string; result: string; raw: any };
export const cases: CaseRow[] = caseCatalog.map((r) => ({
  id: r.case_id,
  ticketId: r.ticket_id,
  title: translated(r.symptom),
  product: r.product_name,
  symptom: translated(r.symptom),
  cause: translated(r.root_cause),
  action: translated(r.action_taken),
  result: translated(r.resolution_result),
  raw: r,
}));

/* ───────── 집계 · 배정 ───────── */
export const openTickets = () => tickets.filter((t) => t.stage !== 5);
export const ownedTickets = (owner = signedIn) => openTickets().filter((t) => t.owner === owner);
export const scopeTickets = (scope: string): Ticket[] =>
  scope === "내 담당" ? tickets.filter((t) => t.owner === signedIn) // 내가 완료한 것도 포함(목록의 "완료" 묶음에 나온다)
  : scope === "답변 준비" ? openTickets().filter(awaitingReview)
  : openTickets(); // "전체"는 진행 중인 문의만. 완료한 건은 "완료 문의" 탭(그리고 내 것은 "내 담당")에서 본다.

export function resource(p: Person, excludeId?: string) {
  const count = ownedTickets(p.name).filter((t) => t.id !== excludeId).length;
  return { count, capacity: p.capacity, free: Math.max(0, p.capacity - count), ratio: count / p.capacity };
}
// BACKEND: 담당자 배정
// 규칙: 모든 담당자가 동등하게 응대할 수 있다고 보고 수용량(부하)만 확인한다. 가득 찬 담당자와 배정 제외 상태는 막고, 추천은 미완료 건수가 가장 적은 사람.
// 필요: 담당자별 미완료 건수·수용량·배정 제외 여부 조회, 담당자 변경 API(되돌리기 포함). 지금: people 상수와 로컬 문의로 계산한다.
/** 배정 가능한 담당자: 모두 동등하게 응대할 수 있다는 전제로, 배정 제외가 아니고 수용량에 여유가 있는 사람. 부하가 가장 낮은 순. */
export function candidates(excludeId?: string) {
  return people
    .filter((p) => p.available && resource(p, excludeId).free > 0)
    .sort((a, b) => resource(a, excludeId).ratio - resource(b, excludeId).ratio || a.name.localeCompare(b.name));
}
/** 배정 검증은 부하만 본다(제품 역량·언어·부서는 따지지 않는다). */
export function checkAssign(t: Ticket, p: Person): { ok: boolean; reason?: string } {
  if (!p.available) return { ok: false, reason: `${p.name}은(는) 배정 제외 상태입니다` };
  const r = resource(p, t.id);
  if (r.free <= 0) return { ok: false, reason: `수용량이 가득 찼습니다 (${r.count}/${r.capacity}건)` };
  return { ok: true };
}
export const recommend = (excludeId?: string) => candidates(excludeId)[0];
export function resourceReason(p: Person | undefined, excludeId?: string) {
  if (!p) return "배정할 수 있는 담당자가 없습니다(모두 가득 참) · 미배정으로 등록";
  const r = resource(p, excludeId);
  return `${p.department} · 미완료 ${r.count}/${r.capacity}건 · 여유 ${r.free}건`;
}

export function assignmentSummary(t: Ticket) {
  const person = people.find((p) => p.name === t.owner);
  return [FRONTLINE, person ? `담당 미완료 ${ownedTickets(person.name).length}/${person.capacity}건` : "미배정"];
}
/** 문의를 처리하는 팀(전문부서 요청을 보내는 쪽). 지금은 글로벌 C/S 센터 하나다. */
export const ticketDepartment = (_t?: Ticket) => FRONTLINE;
export const overdue = (t: Ticket) => t.stage !== 5 && /초과/.test(t.sla);
export const departmentRisk = (t: Ticket) => t.stage !== 5 && (overdue(t) || Boolean(t.risk));
export const urgentTicket = (t: Ticket) => t.urgent === true || t.priority === "P1";
export function slaMinutes(t: Ticket): number | null {
  const text = String(t.sla || "");
  const h = text.match(/(\d+)h/), m = text.match(/(\d+)m/);
  return h || m ? Number(h?.[1] || 0) * 60 + Number(m?.[1] || 0) : null;
}
export const departmentRank = (t: Ticket) => (overdue(t) ? 0 : t.risk ? 1 : urgentTicket(t) ? 2 : 3);
export function departmentLoad(p: Person) {
  const count = ownedTickets(p.name).length, capacity = Number.isFinite(p.capacity) && p.capacity > 0 ? p.capacity : null;
  return { count, capacity };
}
// BACKEND: 업무 현황 숫자
// 필요: 열린 문의 수, 미배정, SLA 위험(기한을 넘겼거나 임박), 답변 검토 대기 건수. 지금: 로컬 문의에서 센다.
export function stats() {
  return {
    open: tickets.filter((t) => t.stage !== 5).length,
    unassigned: tickets.filter((t) => !t.owner && t.stage !== 5).length,
    risk: tickets.filter((t) => t.risk && t.stage !== 5).length,
    review: tickets.filter(awaitingReview).length,
  };
}
export function priorityTickets() {
  return openTickets().sort(
    (a, b) =>
      Number(departmentRisk(b)) - Number(departmentRisk(a)) ||
      Number(!b.owner) - Number(!a.owner) ||
      Number(b.priority === "P1") - Number(a.priority === "P1") ||
      Number(b.priority === "P2") - Number(a.priority === "P2"),
  );
}

/* ───────── 이력 · 상태 ───────── */
export const now = () => new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
export function record(t: Ticket, kind: string, text: string, extra: Record<string, any> = {}) {
  t.events.push({
    kind, text, time: now(), createdAt: new Date().toISOString(),
    ...(kind === "escalation" ? { id: "REQ-" + crypto.randomUUID().slice(0, 8).toUpperCase(), requestingDepartment: ticketDepartment(t) } : {}),
    actor: t.owner || "Doyeon Kim", ...extra,
  });
  save();
}
export const waitingReviews = (t: Ticket) => t.events.filter((e) => e.kind === "escalation" && (t.source !== "api" || e.source === "specialist-api") && !t.events.some((r) => r.kind === "expert" && r.requestId === e.id));
export const ticketProgress = (t: Ticket) => (t.stage === 5 ? "완료" : t.owner ? "진행 중" : "미배정");
/** 담당자가 아직 열어 보지 않은 고객 회신 수. 문의 상세를 열면 읽음 처리된다. */
export const unreadReplies = (t: Ticket) =>
  t.stage === 5 ? 0 : t.events.filter((e) => ["customer", "customer-followup"].includes(e.kind) && (!t.seenAt || (e.createdAt && e.createdAt > t.seenAt))).length;
export const latestCustomerReply = (t: Ticket): Ev | undefined => t.events.findLast((e) => ["customer", "customer-followup"].includes(e.kind));
export const sourceInquiry = (t: Ticket) => t.body || (t.source !== "api" && t.id === "CSV1-000050" ? "The iS7 75kW trips with E.OC immediately at run command. Restarting did not resolve the issue." : t.title);

// 전문부서 요청 대상 = 백엔드 이관 대상(agents/escalation.py ESCALATION_TARGETS)의 이름 (departments.csv)
export const expertDepartments = ["자동화 기술지원", "저압기기 기술지원", "고압·배전반 기술지원", "변압기 기술지원", "에너지솔루션 기술지원", "현장 서비스", "품질보증/클레임", "펌웨어 개발", "인증·규격", "보증·RMA 데스크", "해외영업 운영", "주문·물류"];
export function referralRows() {
  const rows: any[] = [];
  for (const t of tickets) {
    for (const e of t.events.filter((x) => x.kind === "escalation")) {
      const response = t.events.find((x) => x.kind === "expert" && x.requestId === e.id);
      rows.push({ ticket: t, event: e, response, source: e.requestingDepartment || null, target: e.department || null, requestId: e.id, when: e.createdAt || null, time: e.time || null, status: response ? "회신 수신" : "회신 대기", resultSeen: response?.reviewed ? "확인 완료" : "미기록", key: t.id + ":" + e.id });
    }
    if (t.legacyReviewPending) rows.push({ ticket: t, event: null, response: null, source: null, target: null, requestId: null, when: null, time: null, status: "회신 대기", resultSeen: "미기록", key: t.id + ":unknown" });
  }
  return rows;
}
export const referralDepartments = () => [...new Set([...expertDepartments, ...referralRows().map((r) => r.target || "대상 부서 미기록")])];
export const departmentReviewRows = (name: string) => referralRows().filter((r) => (r.target || "대상 부서 미기록") === name);
export const requestRow = (ticketId: string, requestId: string) => referralRows().find((r) => r.ticket.id === ticketId && r.requestId === requestId);

/* ───────── 추가정보 · 답변 컨텍스트 ───────── */
export function requiredInformation(t: Ticket): { id: string; label: string }[] {
  if (Array.isArray(t.requiredInformation)) return t.requiredInformation;
  if (t.source !== "api" && t.id === "CSV1-000050") return [{ id: "product-photo", label: "제품·오류 화면 사진" }, { id: "motor-nameplate", label: "모터 명판" }];
  return [];
}
export const informationAssessment = (t: Ticket) =>
  requiredInformation(t).map((item) => ({ ...item, ...(t.infoChecks?.[item.id] || {}), status: (t.infoChecks?.[item.id]?.status || "missing") as string, evidence: t.infoChecks?.[item.id]?.evidence as string | undefined }));
export function informationSummary(t: Ticket) {
  const items = informationAssessment(t), remaining = items.filter((x) => !["provided", "confirmed"].includes(x.status)).length;
  if (t.source === "api" && !t.analysisReady) return "필수정보 확인 대기";
  if (!items.length) return t.customerRequestStatus === "received" ? "회신 수신" : "요청 없음";
  if (t.customerRequestStatus === "waiting") return `회신 대기 · 필요 ${remaining}건`;
  if (t.customerRequestStatus === "received" && !latestCustomerReply(t)) return "수신 내역 미기록";
  if (t.source === "api" && t.customerRequestStatus === "received" && latestCustomerReply(t)?.id !== t.reviewedReplyKey) return "회신 수신 · 담당자 확인 필요";
  if (t.customerRequestStatus === "received") return remaining ? `회신 수신 · 미충족 ${remaining}건` : "요청 자료 확인 완료";
  return "요청 없음";
}

export const replyLanguages = ["English", "한국어", "日本語", "Deutsch", "Français", "Español", "Tiếng Việt", "中文"];
/** 초안은 항상 영어로 쓴다(근거 문서·점검 기준이 영어). 고객 언어본은 여기서 변환해 만든다. */
export const composerLanguage = (_t?: Ticket): string => "English";
const LANGUAGE_BY_COUNTRY: Record<string, string> = { Germany: "Deutsch", Austria: "Deutsch", Spain: "Español", Mexico: "Español", Vietnam: "Tiếng Việt", Japan: "日本語", China: "中文", France: "Français", Korea: "한국어", "South Korea": "한국어" };
/** 고객에게 보낼 언어. 문의에 지정이 없으면 국가로 추정하고, 모르면 영어. */
export const customerLanguage = (t: Ticket): string => t.replyLanguage || LANGUAGE_BY_COUNTRY[t.country] || "English";
export const needsLocalization = (t: Ticket) => customerLanguage(t) !== "English";
export const composerKey = (purpose: string, language: string) => purpose + "::" + language;

export type Ctx = any;
/** 백엔드 티켓의 검색 근거 (CSA-61, api-sync 가 apiEvidence 로 넣는다). 공식 문서 상위 3개. */
function apiDocuments(t: Ticket) {
  return (t.apiEvidence || [])
    .filter((e: any) => e.source === "docs")
    .map((e: any) => ({ id: e.section ? `${e.doc_id}#${e.section}` : e.doc_id, label: e.section ? `${e.doc_id} §${e.section}` : e.doc_id, text: String(e.text || "").slice(0, 240), kind: "document" }));
}
export function answerContext(t: Ticket, purpose?: string): Ctx {
  const isSample = t.source !== "api" && t.id === "CSV1-000050";
  const extra = t.events.filter((e) => ["customer", "customer-followup"].includes(e.kind));
  const expertEvents = t.events.filter((e) => e.kind === "expert" && (t.source !== "api" || e.source === "specialist-api"));
  const expert = expertEvents.at(-1);
  const expertReferences = expertEvents.map((e) => ({
    id: e.source === "specialist-api" ? `specialist:${e.id}` : e.createdAt || "expert-" + t.events.indexOf(e),
    label: (t.events.find((req) => req.id === e.requestId)?.department || "전문부서") + " 검토 회신",
    kind: "expert", text: e.text, createdAt: e.createdAt,
  }));
  const missing = informationAssessment(t).filter((x) => !["provided", "confirmed"].includes(x.status)).map((x) => x.label);
  const documents = isSample ? [{ id: "TG-iS7-3.2", label: "iS7 Guide §3.2 · §3.3", text: "E.OC 발생 시점별 과전류 검토", kind: "document" }] : apiDocuments(t);
  const similar = isSample
    ? cases
        .filter((c) => c.ticketId !== t.id && c.product.includes("iS7") && c.raw.error_code === "E.OC")
        .sort((a, b) => Number(b.raw.reference_section === "3.2") - Number(a.raw.reference_section === "3.2"))
        .slice(0, 2)
        .map((c) => ({ ...c, kind: "case", matches: c.raw.reference_section === "3.2", label: c.id + " · " + c.title }))
    : (t.apiEvidence || []).filter((e: any) => e.source === "cases").map((e: any) => ({
        id: e.section ? `${e.doc_id}#${e.section}` : e.doc_id, label: e.metadata?.title || e.doc_id,
        text: e.text, kind: "case", matches: false,
      }));
  const refs: any[] = [
    ...documents, ...similar,
    ...expertReferences,
  ];
  const checkedCitations = t.draft && t.draft !== t.apiCheckedText ? [] : t.draftCited || [];
  const selected = refs.filter((r) => t.source === "api" ? checkedCitations.includes(r.id) : (t.answerReferenceIds ? t.answerReferenceIds.includes(r.id) || r.kind === "expert" : r.kind !== "case" || r.matches));
  return {
    ticketId: t.id,
    language: composerLanguage(t),
    purpose: purpose || t.composerPurpose || (t.draft ? t.purpose : null) || (missing.length && !expert ? "request" : "answer"),
    analysis: { inquiry: sourceInquiry(t), summary: t.title, type: t.type, product: t.product, errorCode: isSample ? "E.OC" : t.apiExtraction?.error_code || null, conditions: isSample ? { firmware: "4.00", load: "69%" } : { firmware: t.apiExtraction?.fw_version || null }, fieldValues: t.apiExtraction?.field_values || {}, fieldEvidence: t.apiExtraction?.field_evidence || {}, fieldSources: t.apiExtraction?.field_sources || {}, unconfirmed: t.apiExtraction?.unconfirmed_fields || {}, issues: t.apiExtraction?.issues || [] },
    missingInfo: missing,
    additionalInfo: extra.map((e) => ({ text: e.text, files: e.files || [], createdAt: e.createdAt, kind: e.kind })),
    technical: { documents, similarCases: similar, possibleCause: isSample ? "모터·출력 케이블 상태 검토 필요" : null, recommendation: isSample ? "근거와 현장 상태를 비교해 전문부서에서 판단" : "제품과 문의 조건에 맞는 근거 확인", causeConfirmed: false },
    expertReferences,
    specialistRevision: t.specialistRevision ?? 0,
    customerRevision: t.customerRevision ?? 0,
    expertResponse: expert ? { text: expert.text, createdAt: expert.createdAt } : null,
    referenceContextIds: t.source === "api" ? refs.map((r) => r.id) : undefined,
    availableReferences: refs,
    references: selected,
  };
}
export function contextKey(c: Ctx) {
  if (c.purpose === "request") return JSON.stringify({ purpose: "request", language: c.language, product: c.analysis.product, missingInfo: c.missingInfo });
  return JSON.stringify({ analysis: c.analysis, missing: c.missingInfo, extra: c.additionalInfo, expert: c.expertReferences ?? c.expertResponse, specialistRevision: c.specialistRevision, customerRevision: c.customerRevision, references: c.referenceContextIds || c.references.map((r: any) => r.id), purpose: c.purpose, language: c.language });
}
export function contextIsNew(t: Ticket) {
  if (!t.draft) return false;
  if (t.source === "api" && (t.draftInformationReviewedAt ?? null) !== (t.informationReviewedAt ?? null)) return true;
  if (t.source === "api" && (t.draftCustomerRevision ?? 0) !== (t.customerRevision ?? 0)) return true;
  if (t.source === "api" && (t.draftSpecialistRevision ?? 0) !== (t.specialistRevision ?? 0)) return true;
  const c = answerContext(t);
  return Boolean(t.draftContextKey && t.draftContextKey !== contextKey(c)) || (!t.draftContextKey && t.events.some((e) => ["customer", "expert"].includes(e.kind)));
}

const localeText: Record<string, Record<string, string>> = {
  English: { request: "Thank you for reporting the issue with", ask: "Please provide the following information for review:", photo: "Photos of the product and error display", nameplate: "A clear photo of the motor nameplate", review: "We will review these together with the reported symptoms and supporting information.", received: "We have received your inquiry about", pending: "The cause has not been confirmed. We will review the available evidence before recommending the next steps.", case: "Comparison reference", expert: "The technical department provided a review.", original: "Technical review — original text", close: "Please reply to this ticket if you need further assistance." },
  한국어: { request: "문의하신 제품의 증상을 확인했습니다:", ask: "검토를 위해 아래 자료를 보내 주세요.", photo: "제품 및 오류 화면 사진", nameplate: "모터 명판 사진", review: "보내 주신 자료를 문의 증상과 관련 근거와 함께 검토하겠습니다.", received: "문의 내용을 확인했습니다:", pending: "현재 원인은 확정되지 않았습니다. 확보한 근거를 검토한 뒤 다음 조치를 안내드리겠습니다.", case: "비교 참고 사례", expert: "전문부서 검토 회신을 받았습니다.", original: "전문부서 회신 원문", close: "추가 문의는 이 문의로 회신해 주세요." },
  日本語: { request: "お問い合わせの製品について症状を確認しました：", ask: "確認のため、次の資料をお送りください。", photo: "製品およびエラー表示の写真", nameplate: "モーター銘板の写真", review: "いただいた資料を症状および関連情報と併せて確認します。", received: "お問い合わせを受け付けました：", pending: "原因はまだ確定していません。確認できる根拠を検討した上で、次の対応をご案内します。", case: "比較参考事例", expert: "専門部署から確認結果を受け取りました。", original: "専門部署の回答原文", close: "追加のご質問は、このチケットにご返信ください。" },
  Deutsch: { request: "Wir haben die gemeldeten Symptome für das folgende Produkt erfasst:", ask: "Bitte senden Sie uns die folgenden Informationen zur Prüfung:", photo: "Fotos des Produkts und der Fehleranzeige", nameplate: "Ein Foto des Motortypenschilds", review: "Wir prüfen die Unterlagen zusammen mit den gemeldeten Symptomen und den verfügbaren Nachweisen.", received: "Wir haben Ihre Anfrage erhalten:", pending: "Die Ursache ist noch nicht bestätigt. Wir prüfen die verfügbaren Nachweise, bevor wir weitere Schritte empfehlen.", case: "Vergleichsfall", expert: "Die Fachabteilung hat eine Rückmeldung gegeben.", original: "Rückmeldung der Fachabteilung — Originaltext", close: "Bitte antworten Sie bei weiteren Fragen auf dieses Ticket." },
  Français: { request: "Nous avons enregistré les symptômes signalés pour le produit suivant :", ask: "Veuillez nous transmettre les éléments suivants pour examen :", photo: "Photos du produit et du message d’erreur", nameplate: "Photo de la plaque signalétique du moteur", review: "Nous examinerons ces éléments avec les symptômes signalés et les informations disponibles.", received: "Nous avons reçu votre demande concernant :", pending: "La cause n’est pas encore confirmée. Nous examinerons les éléments disponibles avant de recommander les prochaines étapes.", case: "Cas de comparaison", expert: "Le service spécialisé a transmis son retour.", original: "Retour du service spécialisé — texte original", close: "Pour toute question supplémentaire, veuillez répondre à ce ticket." },
  Español: { request: "Hemos registrado los síntomas del siguiente producto:", ask: "Envíe la siguiente información para su revisión:", photo: "Fotos del producto y del mensaje de error", nameplate: "Foto de la placa del motor", review: "Revisaremos estos datos junto con los síntomas y la información disponible.", received: "Hemos recibido su consulta sobre:", pending: "La causa aún no está confirmada. Revisaremos las pruebas disponibles antes de recomendar los siguientes pasos.", case: "Caso de comparación", expert: "El departamento especializado ha enviado su evaluación.", original: "Evaluación del departamento — texto original", close: "Si necesita más ayuda, responda a este ticket." },
  "Tiếng Việt": { request: "Chúng tôi đã ghi nhận triệu chứng của sản phẩm sau:", ask: "Vui lòng cung cấp các thông tin sau để kiểm tra:", photo: "Ảnh sản phẩm và màn hình báo lỗi", nameplate: "Ảnh nhãn động cơ", review: "Chúng tôi sẽ xem xét tài liệu cùng triệu chứng và thông tin hiện có.", received: "Chúng tôi đã nhận được yêu cầu về:", pending: "Nguyên nhân chưa được xác nhận. Chúng tôi sẽ kiểm tra các thông tin hiện có trước khi đề xuất bước tiếp theo.", case: "Trường hợp tham khảo", expert: "Bộ phận chuyên môn đã gửi kết quả kiểm tra.", original: "Phản hồi chuyên môn — văn bản gốc", close: "Vui lòng trả lời phiếu này nếu cần hỗ trợ thêm." },
  中文: { request: "我们已记录以下产品的问题：", ask: "请提供以下资料以便核查：", photo: "产品及错误显示屏的照片", nameplate: "电机铭牌照片", review: "我们将结合所述症状及现有资料进行核查。", received: "我们已收到关于以下产品的咨询：", pending: "目前尚未确认原因。我们将核查现有依据后，再提供后续处理建议。", case: "对比参考案例", expert: "专业部门已提供核查结果。", original: "专业部门回复原文", close: "如需进一步帮助，请回复此工单。" },
};
/**
 * 번역 시뮬레이션(프로토타입). 실제 번역 호출은 연결하지 않았다.
 * 이 화면이 만드는 정해진 문구만 옮기고, 담당자가 직접 쓴 문장·전문부서 회신은 원문 그대로 둔다.
 */
const PHRASES = ["request", "ask", "photo", "nameplate", "review", "received", "pending", "case", "expert", "original", "close"] as const;
export function translateText(text: string, from: string, to: string): string {
  const f = localeText[from], t = localeText[to];
  if (!f || !t || from === to) return text;
  const bullets = new Map([[f.photo, t.photo], [f.nameplate, t.nameplate]]);
  return text
    .split("\n")
    .map((line) => {
      if (line.startsWith("• ")) return bullets.has(line.slice(2)) ? "• " + bullets.get(line.slice(2)) : line;
      for (const k of PHRASES) {
        const src = f[k];
        if (line === src) return t[k];
        if (line === src + ":") return t[k] + ":";
        if (line.startsWith(src + ": ") || line.startsWith(src + " ")) return t[k] + line.slice(src.length);
      }
      return line;
    })
    .join("\n");
}

export function composeAnswer(c: Ctx) {
  const l = localeText[c.language];
  if (!l) return "";
  if (c.purpose === "request") {
    const map: Record<string, string> = { "제품·오류 화면 사진": l.photo, "모터 명판": l.nameplate };
    return `${l.request} ${c.analysis.product}\n\n${l.ask}\n${c.missingInfo.map((v: string) => "• " + (map[v] || v)).join("\n")}\n\n${l.review}`;
  }
  const refs = c.references.filter((r: any) => r.kind === "case").map((r: any) => r.id).join(", ");
  const followup = c.additionalInfo.findLast((x: any) => x.kind === "customer-followup");
  return `${l.received} ${c.analysis.product}${followup ? "\n\n" + (c.language === "한국어" ? "고객 후속 회신 원문" : "Customer follow-up (original)") + ":\n" + followup.text : ""}\n\n${c.expertResponse ? `${l.expert}\n\n${l.original}:\n${c.expertResponse.text}` : l.pending}${!c.expertResponse && refs ? "\n\n" + l.case + ": " + refs : ""}\n\n${l.close}`;
}
export function buildExpertRequest(t: Ticket) {
  const c = answerContext(t);
  return `${t.id} / ${t.product}\n\n문의: ${c.analysis.inquiry}\n\n확보 자료: ${(t.files || []).join(", ") || "등록된 첨부자료 없음"}${t.source !== "api" && t.id === "CSV1-000050" ? " · 이벤트 로그 · FW 4.00 · 부하 69%" : ""}\n추가 확인: ${c.missingInfo.join(", ") || "현재 확인된 누락 항목 없음"}\n\n검토 근거: ${c.references.map((r: any) => r.label).join(", ") || "연결된 기술 근거 없음"}\n\n요청사항: 위 증상과 자료를 검토하고, 가능한 원인·추가 점검사항·권장 조치를 회신해 주세요. 현재 원인은 미확정입니다.`;
}

/* ───────── 완료 기록 ───────── */
export function completionRecords() {
  return tickets
    .map((t) => {
      const e = t.events.findLast((x) => x.kind === "completed");
      const r = t.source === "api" ? t.resolution : e?.resolution || t.resolution;
      if (!r) return null;
      return {
        ticket: t, resolution: r, time: e?.createdAt || r.confirmedAt,
        verified: t.stage === 5 && !t.resolutionSuperseded && r.outcome === "resolved" && ["cause", "action", "result", "verification"].every((k) => String(r[k] || "").trim()),
        superseded: t.stage !== 5 || t.resolutionSuperseded,
      };
    })
    .filter(Boolean) as { ticket: Ticket; resolution: any; time: string; verified: boolean; superseded: boolean }[];
}

/** 완료한 문의 전부: 처리 결과를 기록한 것은 그 기록과 함께, 기록이 없는 것은 "미기록"으로 포함한다. */
export function completedTickets() {
  const recs = completionRecords(), have = new Set(recs.map((r) => r.ticket.id));
  const extra = tickets.filter((t) => t.stage === 5 && !have.has(t.id)).map((t) => ({ ticket: t, resolution: {} as any, time: "", verified: false, superseded: false }));
  return [...recs, ...extra];
}

/* ───────── 저장된 데이터 정규화 ───────── */
export function storeComposer(t: Ticket) {
  if (!t.draft) return;
  t.composerDrafts ??= {};
  t.composerDrafts[composerKey(t.purpose || t.composerPurpose || answerContext(t).purpose, composerLanguage(t))] = {
    draft: t.draft, draftSpecialistRevision: t.draftSpecialistRevision, draftCustomerRevision: t.draftCustomerRevision, draftInformationReviewedAt: t.draftInformationReviewedAt, draftCited: t.draftCited, draftContext: t.draftContext, draftContextKey: t.draftContextKey, draftVersion: t.draftVersion, draftOrigin: t.draftOrigin, ignoredContextKey: t.ignoredContextKey, draftOriginal: t.draftOriginal, draftRequests: t.draftRequests,
  };
}
export function resumeTicket(t: Ticket) {
  if (t.draft) record(t, "draft-replaced", "후속 문의 이전 작성 내용", { draft: t.draft });
  storeComposer(t);
  t.stage = 0; t.status = t.owner ? "진행 중" : "미배정"; t.sent = false; t.customerOutcome = "needs-support"; t.resolutionSuperseded = true;
  t.draft = ""; t.reviewed = false; t.composerOpen = false; t.activeComposer = null; t.pendingAnswer = null;
  delete t.composerDrafts?.[composerKey("answer", composerLanguage(t))];
  if (t.preCompletionSla) { t.sla = t.preCompletionSla; t.preCompletionSla = null; }
  record(t, "reopen", "고객 후속 문의로 처리 재개", { actor: signedIn });
}

for (const t of tickets) {
  if (t.source === "api") continue;
  if (t.stage === 0 && t.owner && t.status === "검토 중") t.status = "진행 중";
  if (!t.workflowVersion) {
    // 전체 상태와 고객 추가정보/전문부서 요청 상태를 분리한다.
    t.responseReady = t.stage === 4 && !t.sent;
    t.customerRequestStatus = t.stage === 1 ? "waiting" : t.stage === 2 ? "received" : "none";
    t.legacyReviewPending = t.stage === 3 && !t.events.some((e) => e.kind === "escalation");
    if (t.stage !== 5) { t.stage = 0; t.status = t.owner ? "진행 중" : "미배정"; }
    t.workflowVersion = 2;
  }
}

for (const t of tickets) {
  if (t.source === "api") continue;
  if (t.id === "CSV1-000056" && !t.seededReply && t.stage !== 5 && !t.sent && !t.events.some((e) => e.kind === "customer")) {
    t.events.push({ kind: "customer", text: "Additional info: the unit was bought through our local distributor in March. The invoice is attached.", time: "오전 09:42", createdAt: new Date().toISOString(), files: ["invoice.pdf"], actor: "customer" });
    t.seededReply = true;
  }
}

// 고객 관리와 연결: 샘플 문의마다 국가가 맞는 학습 데이터 고객을 붙인다(고객 상세의 "최근 문의"에서 이 문의를 열 수 있다).
/** 샘플 문의가 접수된 시각(문의 상세의 접수 시각과 같다). */
export const INQUIRY_ISO = "2026-10-06T17:43:00Z";
const CUSTOMER_OF: Record<string, string> = { "CSV1-000049": "CUST-0600", "CSV1-000050": "CUST-0256", "CSV1-000051": "CUST-0600", "CSV1-000056": "CUST-0600", "CSV1-000052": "CUST-0160", "CSV1-000053": "CUST-0433", "CSV1-000054": "CUST-0325", "CSV1-000055": "CUST-0147", "CSV1-000057": "CUST-0462" };
// 같은 고객은 어느 화면에서나 같은 이름으로 보이도록, 연결된 고객의 이름(고객 관리 데이터)을 문의의 회사명으로 쓴다.
// BACKEND: 문의는 customerId 만 들고 오고, 회사명·국가는 고객 정보에서 가져온다(두 곳에 따로 적지 않는다).
const CUSTOMER_NAME: Record<string, string> = { "CUST-0256": "COMPANY_8291_0256", "CUST-0600": "COMPANY_1337_0600", "CUST-0160": "COMPANY_3039_0160", "CUST-0433": "COMPANY_9541_0433", "CUST-0325": "COMPANY_2368_0325", "CUST-0147": "COMPANY_4257_0147", "CUST-0462": "COMPANY_6741_0462" };
const linkCustomers = () => { for (const t of tickets) if (t.source !== "api" && CUSTOMER_OF[t.id]) { t.customerId = CUSTOMER_OF[t.id]; t.company = CUSTOMER_NAME[t.customerId] || t.company; } };
linkCustomers();

// 예전 저장 데이터 정리: 요청하는 쪽 부서를 글로벌 C/S 센터로 통일한다.
for (const t of tickets) {
  t.department = FRONTLINE;
  for (const e of t.events) if (e.kind === "escalation" && ["자동화 기술지원", "저압 기술지원"].includes(e.requestingDepartment)) e.requestingDepartment = FRONTLINE;
}

// 샘플: 전문부서 요청. 대기 2건 + 회신 받음 1건. 이미 만든 적이 있으면(seededCollab) 다시 만들지 않는다.
{
  const ago = (h: number) => new Date(Date.now() - h * 3600e3).toISOString();
  const request = (t: Ticket, id: string, department: string, text: string, hoursAgo: number, channel = "이메일") => {
    t.events.push({ kind: "escalation", id, text: `${department} 검토 요청`, request: text, department, requestingDepartment: ticketDepartment(t), channel, time: "오늘", createdAt: ago(hoursAgo), actor: t.owner || "Doyeon Kim" });
  };
  const byId = (id: string) => tickets.find((x) => x.source !== "api" && x.id === id);
  const a = byId("CSV1-000053"), b = byId("CSV1-000052"), c = byId("CSV1-000054");
  if (a && !a.seededCollab) { a.seededCollab = true; a.legacyReviewPending = false; request(a, "REQ-S100OVH1", "현장 서비스", "S100 7.5kW 과열 알람이 반복됩니다. 현장 냉각 팬과 설치 환경 점검 가능 여부를 회신해 주세요.", 5); }
  if (b && !b.seededCollab) { b.seededCollab = true; request(b, "REQ-XGIFW002", "자동화 기술지원", "XGI CPU 펌웨어 업데이트 순서와 주의사항을 확인해 주세요.", 2, "기업 메신저"); }
  if (c && !c.seededCollab) {
    c.seededCollab = true; request(c, "REQ-MCCB0031", "저압 기술지원", "MCCB 100AF 최신 기술문서 개정 번호를 확인해 주세요.", 20);
    c.events.push({ kind: "expert", text: "최신 개정은 Rev.4이며, 이전 Rev.3 대비 단락 차단 용량 표기가 바뀌었습니다.", requestId: "REQ-MCCB0031", department: "저압 기술지원", time: "어제", createdAt: ago(8), actor: "저압 기술지원" });
  }
}

// 샘플: 내가 완료한 문의(내 담당·완료 문의 탭에서 보이는 모습). 이미 있으면 다시 만들지 않는다.
if (!tickets.some((t) => t.id === "CSV1-000049")) {
  const done = new Date(Date.now() - 26 * 3600e3).toISOString();
  const resolution = { outcome: "resolved", cause: "출력 케이블 접지 불량으로 인한 과전류 트립", action: "접지 단자 재체결 후 파라미터 초기화", result: "재시작 후 E.OC 재발 없음", verification: "고객이 24시간 연속 운전 확인 회신", confirmedBy: signedIn, confirmedAt: done, references: [] };
  tickets.push({
    id: "CSV1-000049", title: "S100 가동 직후 과전류 트립", product: "S100 7.5kW", country: "Germany", company: "Nordwerk GmbH", type: "불량", priority: "P3", status: "완료", sla: "기한 내 완료",
    owner: signedIn, language: "English", stage: 5, risk: false, draft: "", files: [], reviewed: false, sent: true, customerOutcome: "resolved", resolution,
    events: [
      { kind: "sent", text: "We have received your inquiry about S100 7.5kW.", purpose: "answer", time: "어제 오후 02:10", createdAt: done, actor: signedIn, edited: false },
      { kind: "completed", text: "처리 결과 기록 및 완료", time: "어제 오후 05:40", createdAt: done, actor: signedIn, resolution },
    ],
  } as Ticket);
}

/** 고객 시스템에서 들어온 회신/후속 회신 이벤트를 문의 상태에 반영한다. */
export function synchronizeCustomerEvents() {
  for (const t of tickets) {
    if (t.source === "api") continue; // Server status/revisions are authoritative.
    for (const e of t.events) if (["customer", "customer-followup"].includes(e.kind) && !e.id) e.id = "CUSTOMER-" + crypto.randomUUID().slice(0, 8);
    const ri = t.events.findLastIndex((e) => e.kind === "sent" && e.purpose === "request");
    const ci = t.events.findLastIndex((e) => ["customer", "customer-followup"].includes(e.kind));
    if (ri >= 0 || ci >= 0) {
      const value = ci > ri ? "received" : "waiting";
      if (t.customerRequestStatus !== value) t.customerRequestStatus = value;
    }
    const i = t.events.findLastIndex((e) => e.kind === "customer-followup");
    if (i >= 0) {
      const e = t.events[i], key = e.id || e.createdAt || String(i);
      if (t.handledFollowupKey !== key) {
        const afterCompletion = i > t.events.findLastIndex((x) => x.kind === "completed");
        if (afterCompletion) {
          t.customerOutcome = e.customerResult || null;
          if (e.customerResult === "needs-support" && i > t.events.findLastIndex((x) => x.kind === "reopen")) resumeTicket(t);
        }
        t.handledFollowupKey = key;
      }
    }
  }
}
linkCustomers(); // 049 등 뒤에서 만든 샘플까지 고객 이름을 맞춘다
onBeforeCommit(synchronizeCustomerEvents);
synchronizeCustomerEvents();
save();

/** 아직 길이 정해지지 않은 문의의 세 갈래: 고객 질의서 · 전문부서 요청서 · 답변 초안. 이미 초안이 있거나 누구의 회신을 기다리는 중이면 갈래가 아니라 그 상태가 보인다. */
export type Choice = "answer" | "expert" | "request";
export function branchChoice(t: Ticket): Choice | null {
  // 백엔드 문의는 처음부터 AI 답변 초안이 있다. 고치기 전에는 전문부서 요청·고객 질의서로도 갈 수 있게 갈림길을 보인다 (CSA-61)
  if (t.source === "api" && !t.analysisReady) return null;
  const untouchedAiDraft = t.source === "api" && t.purpose === "answer" && !!t.draft && t.draft === t.aiDraft;
  if (t.stage === 5 || t.sent || !t.owner || (t.draft && !untouchedAiDraft) || t.activeComposer === "expert") return null;
  const reply = latestCustomerReply(t), c = answerContext(t);
  if (t.customerOutcome === "needs-support" || t.customerRequestStatus === "waiting") return null;
  if (t.customerRequestStatus === "received" && reply && requiredInformation(t).length && reply.id !== t.reviewedReplyKey) return null;
  if (waitingReviews(t).length || t.legacyReviewPending) return null;
  if (c.missingInfo.length) return "request";
  if (!c.expertResponse && !c.availableReferences.length && ["불량", "설치", "펌웨어"].includes(t.type) && !(t.customerRequestStatus === "received" && reply)) return "expert";
  return "answer";
}

// BACKEND: 완료 기록 초안
// 필요: 문의 대화·전문부서 회신·발송한 답변을 읽고 { outcome, cause, action, result, verification } 초안을 만들어 준다(담당자는 확인·수정만 한다).
// 지금: 이력에서 확인된 사실(전문부서 회신, 고객 회신, 발송 기록)만 모아 흉내 낸다. 이력에 없는 원인은 지어내지 않고 비워 둔다.
/** 완료 입력창을 미리 채운다. from 은 채운 근거(화면에 "무엇을 보고 채웠는지"로 보여 준다). */
export function completionDraft(t: Ticket) {
  const expert = t.events.findLast((e) => e.kind === "expert"), reply = latestCustomerReply(t);
  const sent = t.events.findLast((e) => e.kind === "sent");
  // 최신 발송 뒤 고객이 명시적으로 기록한 결과만 사용한다. 과거 해결 상태를 재사용하지 않는다.
  const replyAfterSend = !!reply && (!sent || t.events.indexOf(reply) > t.events.indexOf(sent));
  const outcome = replyAfterSend && ["resolved", "provided"].includes(reply.customerResult)
    ? reply.customerResult as string : "";
  const sentLabel = sent?.purpose === "request" ? "추가정보 요청 발송 기록" : "고객 답변 발송 기록";
  const from = [expert && "전문부서 회신", reply && "고객 회신", sent && sentLabel].filter(Boolean) as string[];
  // 회신 원문·유사 사례의 추정 원인은 최종 확인 원인이 아니다. 담당자가 확인해 입력한다.
  const cause = "";
  const action = [expert && "전문부서 회신을 수신했습니다.", reply && "고객 회신을 수신했습니다.", sent && `${sentLabel}이 있습니다.`].filter(Boolean).join(" ");
  const result = outcome === "resolved" ? "고객 회신에 해결 확인이 기록되어 있습니다."
    : outcome === "provided" ? "고객 회신에 정보 확인이 기록되어 있습니다."
    : reply ? "고객 회신이 있으나 최종 해결 여부는 확인되지 않았습니다."
    : sent ? "고객 회신이 없어 해결 여부는 확인되지 않았습니다." : "";
  return { outcome, cause, action, result, verification: from.join(", "), from };
}

/** 답변 검토 대기: 고객 답변 초안이 만들어져 있고 아직 보내지 않은 문의(전문부서 회신을 기다리는 중이면 제외). */
export const awaitingReview = (t: Ticket) => !!t.draft && t.purpose === "answer" && !t.sent && t.stage !== 5 && !waitingReviews(t).length && !t.legacyReviewPending;

/* ───────── 문의 한눈 요약(시뮬레이션) ───────── */
// BACKEND: 문의 한눈 요약
// 필요: 분석 결과에서 한국어 3줄 요약 + 핵심 값(제품·유형·긴급도·고객 언어, 오류 코드, 추정 원인, 권장 확인). 번역(CSA-57)·분석 결과를 쓴다.
// 지금: 화면에서 분석 컨텍스트(answerContext)로 조립한다.
/** 상담원이 영어 원문을 다 읽지 않아도 방향을 잡도록 한국어 3줄 + 핵심 값을 만든다. 실제로는 번역(CSA-57)·분석 결과를 쓴다. */
export function inquirySummary(t: Ticket) {
  const c = answerContext(t), a = c.analysis;
  const pendingReview = waitingReviews(t).length + (t.legacyReviewPending ? 1 : 0);
  const facts = [a.errorCode && `오류 코드 ${a.errorCode}`, a.conditions.firmware && `FW ${a.conditions.firmware}${a.conditions.load ? " · 부하 " + a.conditions.load : ""}`, t.files?.length ? `첨부 ${t.files.length}건` : ""].filter(Boolean).join(" · ");
  // 백엔드 문의는 원문 한국어 번역(body_ko, CSA-57) 앞부분으로 요지를 보인다
  const ko = typeof t.bodyKo === "string" ? t.bodyKo.split(/(?<=[.!?。])\s+/).slice(0, 2).join(" ").slice(0, 180) : "";
  const gist = t.source !== "api" && t.id === "CSV1-000050" ? "운전 명령 직후 E.OC(과전류) 트립이 발생하고, 재시작해도 같은 증상이 반복됩니다." : ko || `‘${t.title}’ 내용입니다.`;
  const reply = latestCustomerReply(t);
  const next = t.stage === 5 ? "처리가 완료된 문의입니다."
    : t.sent ? "고객 답변을 발송했습니다."
    : !t.owner ? "담당자가 아직 배정되지 않았습니다."
    : c.missingInfo.length
    ? `답변 전에 필요한 자료: ${c.missingInfo.join(", ")}`
    : pendingReview ? `전문부서 회신 ${pendingReview}건을 기다리는 중입니다.`
    : c.expertResponse ? "전문부서 회신이 도착했습니다. 답변에 반영하세요."
    : t.customerRequestStatus === "received" && reply ? `고객이 추가정보를 보냈습니다${reply.files?.length ? `(첨부 ${reply.files.length}건)` : ""}. 확인하고 답변을 작성하세요.`
    : t.source === "api" && !t.analysisReady ? "문의 분석과 필수정보 확인이 아직 완료되지 않았습니다."
    : "추가 자료 없이 답변을 작성할 수 있습니다.";
  const urgent = ["P1", "P2"].includes(t.priority);
  return {
    lines: [`${t.company}(${t.country})의 ${t.product} 관련 ${t.type} 문의입니다.`, gist + (facts ? ` (${facts})` : ""), next],
    chips: [
      { label: "제품", value: t.product, tone: "" as const },
      { label: "유형", value: t.type, tone: "" as const },
      ...(a.errorCode ? [{ label: "오류 코드", value: a.errorCode as string, tone: "amber" as const }] : []),
      { label: "우선순위", value: t.priority, tone: (urgent ? "red" : "") as "red" | "" },
      { label: "고객 언어", value: customerLanguage(t), tone: "" as const },
    ],
  };
}

/* ───────── 자동 점검(시뮬레이션) ───────── */
export type CheckItem = { name: string; label: string; passed: boolean; reason: string; pending?: boolean };
const norm = (s: string) => s.toLowerCase().replace(/\s+/g, "");
function evidenceText(t: Ticket) {
  const c = answerContext(t);
  return [
    sourceInquiry(t), t.title, t.product, c.analysis.product, c.analysis.errorCode || "", c.technical.recommendation || "",
    ...c.additionalInfo.map((x: any) => x.text), c.expertResponse?.text || "",
    ...c.references.map((r: any) => [r.label, r.text, r.cause, r.action, r.result].filter(Boolean).join(" ")),
  ].join(" \n ");
}
// BACKEND: 자동 점검(CheckResult)
// 필요: 초안을 만들거나 고칠 때마다 서버가 CheckResult[] { name, passed, reason } 를 내려 준다. 항목 6개: slots · values · specs · language · banned · grounding.
// 지금: 화면에서 문자열 규칙으로 흉내 낸다(근거에 없는 수치·규격, 영어 여부, 단정 표현, 근거 연결).
/**
 * 백엔드 verification 의 점검 항목(슬롯·수치·규격·언어·단정 표현·근거)을 흉내 낸 계산이다.
 * 담당자가 초안을 고치면 바로 다시 계산돼, 어떤 수정이 점검에 걸리는지 화면에서 확인할 수 있다.
 */
export function runChecks(t: Ticket): CheckItem[] {
  if (t.source === "api") {
    if (t.draft && (t.draft !== t.apiCheckedText || (t.draftCustomerRevision ?? 0) !== (t.customerRevision ?? 0) || (t.draftInformationReviewedAt ?? null) !== (t.informationReviewedAt ?? null) || (t.draftSpecialistRevision ?? 0) !== (t.specialistRevision ?? 0))) return [{ name: "pending", label: "최종본 재점검 필요",
      passed: false, pending: true, reason: "본문 또는 근거가 변경되었습니다. 최신 내용을 반영한 뒤 서버 최종 점검을 받습니다." }];
    const labels: Record<string, string> = { slots: "필수 항목", values: "수치 일치", specs: "규격·사양", language: "초안 언어", banned: "단정 표현", grounding: "근거 연결", analysis_unavailable: "분류 미확인" };
    return (t.apiChecks || []).map((c: { name: string; passed: boolean; reason: string }) => ({ ...c, label: labels[c.name] || c.name }));
  }
  const draft = t.draft || "", ev = norm(evidenceText(t)), c = answerContext(t);
  const purpose = t.purpose || c.purpose, isDiag = ["불량", "설치", "펌웨어"].includes(t.type), isPolicy = ["보증", "반품"].includes(t.type);
  const missingIn = (found: string[]) => [...new Set(found)].filter((x) => !ev.includes(norm(x)));

  const bullets = draft.split("\n").filter((l) => l.startsWith("• ")).length;
  const slots = purpose === "request"
    ? { passed: bullets >= c.missingInfo.length, reason: `요청 항목 ${c.missingInfo.length}개 중 ${bullets}개만 들어 있습니다` }
    : { passed: draft.includes(t.product), reason: "제품명이 답변에 들어 있지 않습니다" };

  const values = missingIn(draft.match(/\b\d[\d.,]*\s?(?:kva|kv|ka|kw|hz|°c|mm|ms|v|a)\b/gi) || []);
  const specs = missingIn([...(draft.match(/\b(?:iec|ul|en|iso)\s?-?\d[\d-]*/gi) || []), ...(draft.match(/\bip\d{2}\b/gi) || [])]);
  // 전문부서 회신 원문 인용(내부 부서가 쓴 원문 그대로)은 영어 여부 점검에서 뺀다. 번역은 발송 때 고객 언어로 따로 처리된다.
  const quote = localeText.English.original + ":";
  const body = draft.split("\n\n").filter((blk) => !blk.startsWith(quote)).join("\n\n");
  const nonEnglish = /[가-힣ㄱ-ㅎ]|[Ѐ-ӿ]|[؀-ۿ]|[一-鿿]|[぀-ヿ]/.test(body);
  const banned = isDiag ? /\b(the|this)\s+(root\s+)?cause\s+(is|was)\b|\bcaused by\b|\bdefinitely\b|\bcertainly\b/i.exec(draft)
    : isPolicy ? /\b(approved|rejected|denied)\b|free of charge/i.exec(draft) : null;

  const phrases = Object.values(localeText.English);
  const courtesy = /^(Dear |Hello|Best regards|Sincerely|Thank you|We apologi[sz]e|Please note that|Reference:|LS ELECTRIC Customer Support)/i; // 인사·사과·맺음말은 근거가 필요한 주장이 아니다
  const ungrounded = draft.split(/\n+/).map((l) => l.replace(/^•\s*/, "").replace(/^\d+\.\s+/, "").trim())
    .filter((l) => l.length >= 25 && !courtesy.test(l) && !phrases.some((p) => l.startsWith(p)) && !ev.includes(norm(l)));

  return [
    { name: "slots", label: "필수 항목", ...slots },
    { name: "values", label: "수치 일치", passed: !values.length, reason: `근거에 없는 수치: ${values.join(", ")}` },
    { name: "specs", label: "규격·사양", passed: !specs.length, reason: `근거에 없는 규격: ${specs.join(", ")}` },
    { name: "language", label: "초안 언어", passed: !nonEnglish, reason: "초안은 영어로 작성해야 합니다(발송 때 고객 언어로 변환됩니다)" },
    { name: "banned", label: "단정 표현", passed: !banned, reason: isPolicy ? `정책 결정을 단정하는 표현: “${banned?.[0]}”` : `원인을 단정하는 표현: “${banned?.[0]}”` },
    { name: "grounding", label: "근거 연결", passed: !ungrounded.length, reason: `근거가 연결되지 않은 문장 ${ungrounded.length}개: “${(ungrounded[0] || "").slice(0, 46)}${(ungrounded[0] || "").length > 46 ? "…" : ""}”` },
  ].map((x) => ({ ...x, reason: x.passed ? "" : x.reason }));
}

/* ───────── 수정 사유 ───────── */
/** 백엔드 FeedbackReason(FACT_ERROR·WEAK_EVIDENCE·TONE·ROUTING_ERROR)과 같은 4가지. */
export const FEEDBACK_REASONS = [["FACT_ERROR", "사실 오류"], ["WEAK_EVIDENCE", "근거 부족"], ["TONE", "어투·표현"], ["ROUTING_ERROR", "분류·담당 오류"]] as const;
export const feedbackLabel = (k?: string) => FEEDBACK_REASONS.find(([key]) => key === k)?.[1];
/** AI 가 만든 초안에서 담당자가 고쳤는가. */
export const isEdited = (t: Ticket) => {
  const original = t.source === "api" ? t.aiDraft : t.draftOriginal;
  return !!t.draft && !!original && (t.source === "api" ? t.draft !== String(original) : t.draft.trim() !== String(original).trim());
};

// BACKEND: 오늘 내가 할 일
// 필요: 담당 문의마다 "지금 해야 할 행동 하나"(고객 회신 확인 · 초안 검토 · 승인·발송 · 답변 작성 · 완료 기록)와 기한. 고객·전문부서 회신을 기다리는 건은 제외.
// 지금: 화면에서 문의 상태로 계산한다.
/** 오늘 내가 할 일: 내 담당 문의마다 "지금 해야 할 행동 하나"를 뽑는다. 고객·전문부서 회신을 기다리는 건은 내 할 일이 아니라 제외. 급한 순. */
export function todayTasks(owner = signedIn) {
  const label = (t: Ticket): string | null => {
    if (t.sent) return "처리 결과 기록하고 완료하기";
    if (t.customerRequestStatus === "waiting") return null;
    if (t.customerRequestStatus === "received" && unreadReplies(t) > 0) return "고객 회신 확인하기";
    if (t.draft) return t.reviewed ? "승인하고 발송하기" : "영어 초안 검토하기";
    if (waitingReviews(t).length || t.legacyReviewPending) return null;
    const pick = branchChoice(t);
    return pick === "request" ? "고객 질의서 작성하기" : pick === "expert" ? "전문부서 요청서 작성하기" : "답변 작성 시작하기";
  };
  return ownedTickets(owner)
    .map((t) => ({ ticket: t, label: label(t) }))
    .filter((x): x is { ticket: Ticket; label: string } => x.label !== null)
    .sort((a, b) => departmentRank(a.ticket) - departmentRank(b.ticket) || (slaMinutes(a.ticket) ?? Infinity) - (slaMinutes(b.ticket) ?? Infinity));
}
