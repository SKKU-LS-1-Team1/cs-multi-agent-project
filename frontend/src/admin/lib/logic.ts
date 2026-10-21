// 레거시 app.js 의 업무 규칙(집계·배정·답변 컨텍스트·초안 문구)을 그대로 옮긴 순수 로직.
import { caseCatalog } from "@admin/data/knowledge-data";
import { onBeforeCommit, save, tickets } from "./store";
import type { Ev, Person, Ticket } from "./types";

export const signedIn = "Doyeon Kim";

export const people: Person[] = [
  { name: "Minji Park", department: "자동화 기술지원", capacity: 6, skills: ["인버터", "PLC"], languages: ["English"], available: true },
  { name: "Doyeon Kim", department: "자동화 기술지원", capacity: 6, skills: ["인버터", "PLC"], languages: ["English"], available: true },
  { name: "Jun Lee", department: "자동화 기술지원", capacity: 6, skills: ["인버터"], languages: ["English"], available: true },
  { name: "Hana Choi", department: "저압 기술지원", capacity: 6, skills: ["차단기", "인버터"], languages: ["English"], available: true },
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
  scope === "내 담당" ? ownedTickets()
  : scope === "미배정" ? openTickets().filter((t) => !t.owner)
  : scope === "SLA 위험" ? openTickets().filter((t) => t.risk)
  : scope === "답변 준비" ? openTickets().filter((t) => (t.responseReady || (t.draft && t.purpose === "answer")) && !t.sent)
  : tickets;

export function resource(p: Person, excludeId?: string) {
  const count = ownedTickets(p.name).filter((t) => t.id !== excludeId).length;
  return { count, capacity: p.capacity, free: Math.max(0, p.capacity - count), ratio: count / p.capacity };
}
export const productSkill = (product: string) => (/MCCB|ACB/.test(product) ? "차단기" : /XGI|PLC/.test(product) ? "PLC" : "인버터");
export const departmentFor = (product: string) => (productSkill(product) === "차단기" ? "저압 기술지원" : "자동화 기술지원");
export function candidates(product: string, language = "English", excludeId?: string) {
  return people
    .filter((p) => p.available && p.department === departmentFor(product) && p.skills.includes(productSkill(product)) && p.languages.includes(language) && resource(p, excludeId).free > 0)
    .sort((a, b) => resource(a, excludeId).ratio - resource(b, excludeId).ratio || a.name.localeCompare(b.name));
}
export function checkAssign(t: Ticket, p: Person): { ok: boolean; reason?: string } {
  if (!p.available) return { ok: false, reason: `${p.name}은(는) 배정 제외 상태입니다` };
  const dept = departmentFor(t.product), skill = productSkill(t.product);
  if (p.department !== dept) return { ok: false, reason: `${dept} 담당자만 배정할 수 있습니다` };
  if (!p.skills.includes(skill)) return { ok: false, reason: `${skill} 제품 역량이 없습니다` };
  if (!p.languages.includes(t.language)) return { ok: false, reason: `${t.language} 응대가 불가능합니다` };
  const r = resource(p, t.id);
  if (r.free <= 0) return { ok: false, reason: `수용량이 가득 찼습니다 (${r.count}/${r.capacity}건)` };
  return { ok: true };
}
export const recommend = (product: string, language = "English", excludeId?: string) => candidates(product, language, excludeId)[0];
export function resourceReason(p: Person | undefined, product: string, language: string, excludeId?: string) {
  if (!p) return "조건에 맞는 담당자 없음 · 미배정으로 등록";
  const r = resource(p, excludeId);
  return `${p.department} · ${productSkill(product)} / ${language} · 미완료 ${r.count}/${r.capacity}건 · 여유 ${r.free}건`;
}

export function assignmentSummary(t: Ticket) {
  const person = people.find((p) => p.name === t.owner);
  return [person?.department || departmentFor(t.product), person ? `담당 미완료 ${ownedTickets(person.name).length}/${person.capacity}건` : "미배정"];
}
export const ticketDepartment = (t: Ticket) => t.department || people.find((p) => p.name === t.owner)?.department || departmentFor(t.product);
export const departmentNames = () => [...new Set([...people.map((p) => p.department), ...tickets.map(ticketDepartment), "현장 서비스"])];
export const departmentTickets = (name: string) => openTickets().filter((t) => ticketDepartment(t) === name);
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
export function stats() {
  return {
    open: tickets.filter((t) => t.stage !== 5).length,
    unassigned: tickets.filter((t) => !t.owner && t.stage !== 5).length,
    risk: tickets.filter((t) => t.risk && t.stage !== 5).length,
    review: tickets.filter((t) => (t.responseReady || (t.draft && t.purpose === "answer")) && !t.sent).length,
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
export const waitingReviews = (t: Ticket) => t.events.filter((e) => e.kind === "escalation" && !t.events.some((r) => r.kind === "expert" && r.requestId === e.id));
export const ticketProgress = (t: Ticket) => (t.stage === 5 ? "완료" : t.owner ? "진행 중" : "미배정");
/** 담당자가 아직 열어 보지 않은 고객 회신 수. 티켓 상세를 열면 읽음 처리된다. */
export const unreadReplies = (t: Ticket) =>
  t.stage === 5 ? 0 : t.events.filter((e) => ["customer", "customer-followup"].includes(e.kind) && (!t.seenAt || (e.createdAt && e.createdAt > t.seenAt))).length;
export const latestCustomerReply = (t: Ticket): Ev | undefined => t.events.findLast((e) => ["customer", "customer-followup"].includes(e.kind));
export const sourceInquiry = (t: Ticket) => t.body || (t.id === "CSV1-000050" ? "The iS7 75kW trips with E.OC immediately at run command. Restarting did not resolve the issue." : t.title);

export const expertDepartments = ["자동화 기술지원", "저압 기술지원", "현장 서비스"];
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
  if (t.id === "CSV1-000050") return [{ id: "product-photo", label: "제품·오류 화면 사진" }, { id: "motor-nameplate", label: "모터 명판" }];
  return [];
}
export const informationAssessment = (t: Ticket) =>
  requiredInformation(t).map((item) => ({ ...item, ...(t.infoChecks?.[item.id] || {}), status: (t.infoChecks?.[item.id]?.status || "missing") as string, evidence: t.infoChecks?.[item.id]?.evidence as string | undefined }));
export function informationSummary(t: Ticket) {
  const items = informationAssessment(t), remaining = items.filter((x) => x.status !== "confirmed").length;
  if (!items.length) return t.customerRequestStatus === "received" ? "회신 수신" : "요청 없음";
  if (t.customerRequestStatus === "waiting") return `회신 대기 · 필요 ${remaining}건`;
  if (t.customerRequestStatus === "received" && !latestCustomerReply(t)) return "수신 내역 미기록";
  if (t.customerRequestStatus === "received") return remaining ? `회신 수신 · 미충족 ${remaining}건` : "요청 자료 확인 완료";
  return "요청 없음";
}

export const replyLanguages = ["English", "한국어", "日本語", "Deutsch", "Français", "Español", "Tiếng Việt", "中文"];
/** 초안은 항상 영어로 쓴다(근거 문서·점검 기준이 영어). 고객 언어본은 여기서 변환해 만든다. */
export const composerLanguage = (_t?: Ticket): string => "English";
const LANGUAGE_BY_COUNTRY: Record<string, string> = { Germany: "Deutsch", Austria: "Deutsch", Spain: "Español", Mexico: "Español", Vietnam: "Tiếng Việt", Japan: "日本語", China: "中文", France: "Français", Korea: "한국어", "South Korea": "한국어" };
/** 고객에게 보낼 언어. 티켓에 지정이 없으면 국가로 추정하고, 모르면 영어. */
export const customerLanguage = (t: Ticket): string => t.replyLanguage || LANGUAGE_BY_COUNTRY[t.country] || "English";
export const needsLocalization = (t: Ticket) => customerLanguage(t) !== "English";
export const composerKey = (purpose: string, language: string) => purpose + "::" + language;

export type Ctx = any;
/** 백엔드 티켓의 검색 근거 (CSA-61, api-sync 가 apiEvidence 로 넣는다). 공식 문서 상위 3개. */
function apiDocuments(t: Ticket) {
  return (t.apiEvidence || [])
    .filter((e: any) => e.source === "docs")
    .slice(0, 3)
    .map((e: any) => ({ id: e.section ? `${e.doc_id}#${e.section}` : e.doc_id, label: e.section ? `${e.doc_id} §${e.section}` : e.doc_id, text: String(e.text || "").slice(0, 240), kind: "document" }));
}
export function answerContext(t: Ticket, purpose?: string): Ctx {
  const isSample = t.id === "CSV1-000050";
  const extra = t.events.filter((e) => ["customer", "customer-followup"].includes(e.kind));
  const expert = t.events.findLast((e) => e.kind === "expert");
  const missing = informationAssessment(t).filter((x) => x.status !== "confirmed").map((x) => x.label);
  const documents = isSample ? [{ id: "TG-iS7-3.2", label: "iS7 Guide §3.2 · §3.3", text: "E.OC 발생 시점별 과전류 검토", kind: "document" }] : apiDocuments(t);
  const similar = isSample
    ? cases
        .filter((c) => c.ticketId !== t.id && c.product.includes("iS7") && c.raw.error_code === "E.OC")
        .sort((a, b) => Number(b.raw.reference_section === "3.2") - Number(a.raw.reference_section === "3.2"))
        .slice(0, 2)
        .map((c) => ({ ...c, kind: "case", matches: c.raw.reference_section === "3.2", label: c.id + " · " + c.title }))
    : [];
  const refs: any[] = [
    ...documents, ...similar,
    ...(expert ? [{ id: expert.createdAt || "expert-" + t.events.indexOf(expert), label: (t.events.find((e) => e.id === expert.requestId)?.department || "전문부서") + " 검토 회신", kind: "expert", text: expert.text }] : []),
  ];
  const selected = refs.filter((r) => (t.answerReferenceIds ? t.answerReferenceIds.includes(r.id) || r.kind === "expert" : r.kind !== "case" || r.matches));
  return {
    ticketId: t.id,
    language: composerLanguage(t),
    purpose: purpose || t.composerPurpose || (t.draft ? t.purpose : null) || (missing.length && !expert ? "request" : "answer"),
    analysis: { inquiry: sourceInquiry(t), summary: t.title, type: t.type, product: t.product, errorCode: isSample ? "E.OC" : null, conditions: isSample ? { firmware: "4.00", load: "69%" } : {} },
    missingInfo: missing,
    additionalInfo: extra.map((e) => ({ text: e.text, files: e.files || [], createdAt: e.createdAt, kind: e.kind })),
    technical: { documents, similarCases: similar, possibleCause: isSample ? "모터·출력 케이블 상태 검토 필요" : null, recommendation: isSample ? "근거와 현장 상태를 비교해 전문부서에서 판단" : "제품과 문의 조건에 맞는 근거 확인", causeConfirmed: false },
    expertResponse: expert ? { text: expert.text, createdAt: expert.createdAt } : null,
    availableReferences: refs,
    references: selected,
  };
}
export function contextKey(c: Ctx) {
  if (c.purpose === "request") return JSON.stringify({ purpose: "request", language: c.language, product: c.analysis.product, missingInfo: c.missingInfo });
  return JSON.stringify({ analysis: c.analysis, missing: c.missingInfo, extra: c.additionalInfo, expert: c.expertResponse, references: c.references.map((r: any) => r.id), purpose: c.purpose, language: c.language });
}
export function contextIsNew(t: Ticket) {
  if (!t.draft) return false;
  const c = answerContext(t);
  return Boolean(t.draftContextKey && t.draftContextKey !== contextKey(c)) || (!t.draftContextKey && t.events.some((e) => ["customer", "expert"].includes(e.kind)));
}

const localeText: Record<string, Record<string, string>> = {
  English: { request: "Thank you for reporting the issue with", ask: "Please provide the following information for review:", photo: "Photos of the product and error display", nameplate: "A clear photo of the motor nameplate", review: "We will review these together with the reported symptoms and supporting information.", received: "We have received your inquiry about", pending: "The cause has not been confirmed. We will review the available evidence before recommending the next steps.", case: "Comparison reference", expert: "The technical department provided a review.", original: "Technical review — original text", close: "Please reply to this ticket if you need further assistance." },
  한국어: { request: "문의하신 제품의 증상을 확인했습니다:", ask: "검토를 위해 아래 자료를 보내 주세요.", photo: "제품 및 오류 화면 사진", nameplate: "모터 명판 사진", review: "보내 주신 자료를 문의 증상과 관련 근거와 함께 검토하겠습니다.", received: "문의 내용을 확인했습니다:", pending: "현재 원인은 확정되지 않았습니다. 확보한 근거를 검토한 뒤 다음 조치를 안내드리겠습니다.", case: "비교 참고 사례", expert: "전문부서 검토 회신을 받았습니다.", original: "전문부서 회신 원문", close: "추가 문의는 이 티켓으로 회신해 주세요." },
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
  return `${t.id} / ${t.product}\n\n문의: ${c.analysis.inquiry}\n\n확보 자료: ${(t.files || []).join(", ") || "등록된 첨부자료 없음"}${t.id === "CSV1-000050" ? " · 이벤트 로그 · FW 4.00 · 부하 69%" : ""}\n추가 확인: ${c.missingInfo.join(", ") || "현재 확인된 누락 항목 없음"}\n\n검토 근거: ${c.references.map((r: any) => r.label).join(", ") || "연결된 기술 근거 없음"}\n\n요청사항: 위 증상과 자료를 검토하고, 가능한 원인·추가 점검사항·권장 조치를 회신해 주세요. 현재 원인은 미확정입니다.`;
}

/* ───────── 완료 기록 ───────── */
export function completionRecords() {
  return tickets
    .map((t) => {
      const e = t.events.findLast((x) => x.kind === "completed");
      const r = e?.resolution || t.resolution;
      if (!r) return null;
      return {
        ticket: t, resolution: r, time: e?.createdAt || r.confirmedAt,
        verified: t.stage === 5 && !t.resolutionSuperseded && r.outcome === "resolved" && ["cause", "action", "result", "verification"].every((k) => String(r[k] || "").trim()),
        superseded: t.stage !== 5 || t.resolutionSuperseded,
      };
    })
    .filter(Boolean) as { ticket: Ticket; resolution: any; time: string; verified: boolean; superseded: boolean }[];
}

/* ───────── 저장된 데이터 정규화 ───────── */
export function storeComposer(t: Ticket) {
  if (!t.draft) return;
  t.composerDrafts ??= {};
  t.composerDrafts[composerKey(t.purpose || t.composerPurpose || answerContext(t).purpose, composerLanguage(t))] = {
    draft: t.draft, draftContext: t.draftContext, draftContextKey: t.draftContextKey, draftVersion: t.draftVersion, draftOrigin: t.draftOrigin, ignoredContextKey: t.ignoredContextKey,
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
  if (t.id === "CSV1-000056" && !t.seededReply && t.stage !== 5 && !t.sent && !t.events.some((e) => e.kind === "customer")) {
    t.events.push({ kind: "customer", text: "Additional info: the unit was bought through our local distributor in March. The invoice is attached.", time: "오전 09:42", createdAt: new Date().toISOString(), files: ["invoice.pdf"], actor: "customer" });
    t.seededReply = true;
  }
}

/** 고객 시스템에서 들어온 회신/후속 회신 이벤트를 티켓 상태에 반영한다. */
export function synchronizeCustomerEvents() {
  for (const t of tickets) {
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
onBeforeCommit(synchronizeCustomerEvents);
synchronizeCustomerEvents();
save();
