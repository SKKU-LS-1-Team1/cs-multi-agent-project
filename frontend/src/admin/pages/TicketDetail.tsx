// 문의 상세: 대기열 · 문의 요약 · 처리 상황 · 문의·답변/처리 이력/고객·제품 정보 · AI Copilot.
import { useEffect, useState, type ReactNode } from "react";
import { Navigate, useParams } from "react-router-dom";
import { ArrowRight, BookOpen, Building2, ChevronDown, ChevronRight, CircleCheck, CircleDashed, CircleDot, Circle, Clock, Compass, FileText, Paperclip, Send, User, type LucideIcon } from "lucide-react";
import { Button } from "@admin/components/ui/button";
import { Card } from "@admin/components/ui/card";
import { Checkbox } from "@admin/components/ui/checkbox";
import { Input } from "@admin/components/ui/input";
import { Textarea } from "@admin/components/ui/textarea";
import { AiMark, Facts, Mono, NativeSelect, PersonAvatar, PriorityTag, SlaTag, StatusTag, Tag, UnderlineTabs, useGo } from "@admin/components/admin/common";
import {
  answerContext, assignmentSummary, branchChoice, cases, contextIsNew, customerLanguage, expertDepartments, feedbackLabel, informationAssessment, informationSummary, inquirySummary, isEdited,
  canAssign, latestCustomerReply, referralRows, requiredInformation, runChecks, sourceInquiry, unreadReplies, waitingReviews,
} from "@admin/lib/logic";
import {
  prepareCustomerReply, canSend, closeComposer, composeFromCopilot, editDraft, markSeen, openCompletion, openExpertComposer, QUICK_INSTRUCTIONS, regenerateDraft, setReviewed, submitExpertRequest, toggleTranslate,
} from "@admin/lib/actions";
import { isManualReplyTicket, hasCurrentReplyPreview, escalationDraftViaApi } from "@admin/lib/api-sync";
import { commit, findTicket, openModal, setUi, ui, useStore } from "@admin/lib/store";
import { cn } from "@admin/lib/utils";
import type { Ticket } from "@admin/lib/types";

type Choice = "answer" | "expert" | "request";
const SAMPLE = "CSV1-000050";
/** 샘플 문의가 접수된 시각. 대화 머리와 처리 이력이 같은 값을 쓴다. */
const INQUIRY_AT = "10.06 · 17:43";
type Next = { label: string; run?: () => void; waiting?: boolean };
/** 지금 담당자가 눌러야 할 단 하나의 행동. Copilot 의 '현재 판단'과 같은 규칙을 따른다. */
function nextAction(t: Ticket): Next | null {
  if (t.stage === 5) return null;
  if (t.source === "api" && !t.analysisReady && !isManualReplyTicket(t) && !t.sent) return { label: "문의 분석 확인 대기", waiting: true };
  if (t.sent) return { label: "처리 결과 기록 및 완료", run: () => openCompletion(t) };
  if (t.activeComposer === "expert") return null; // 요청서를 쓰는 중에는 판단 카드가 따로 안내한다
  if (!t.owner) return canAssign ? { label: "담당자 배정", run: () => openModal("assign", { id: t.id }) } : { label: "팀장이 배정합니다", waiting: true };
  const reply = latestCustomerReply(t), c = answerContext(t);
  if (t.customerRequestStatus === "waiting") return { label: "고객 회신 대기 중", waiting: true };
  if (t.customerRequestStatus === "received" && reply && requiredInformation(t).length && reply.id !== t.reviewedReplyKey) return { label: "수신 자료 확인", run: () => openModal("review-customer", { id: t.id }) };
  if (t.draft && t.purpose !== "request" && (waitingReviews(t).length || t.legacyReviewPending)) return { label: "전문부서 회신 등록", run: () => openModal("expert-receive", { id: t.id }) };
  if (isManualReplyTicket(t) && (!t.draft || (t.draftSpecialistRevision ?? 0) !== (t.specialistRevision ?? 0)
    || (t.draftCustomerRevision ?? 0) !== (t.customerRevision ?? 0)
    || (t.draftInformationReviewedAt ?? null) !== (t.informationReviewedAt ?? null))) {
    return { label: "담당자 답변 작성·검토", run: () => composeFromCopilot(t, "answer") };
  }
  if (t.draft) {
    if (t.source === "api" && (t.draftInformationReviewedAt ?? null) !== (t.informationReviewedAt ?? null)) return {
      label: "확인된 자료 반영해 재작성", run: () => regenerateDraft(t, "Reflect the latest staff-confirmed information and remove withdrawn facts.") };
    if (t.source === "api" && (t.draftCustomerRevision ?? 0) !== (t.customerRevision ?? 0)) return {
      label: "최신 고객 회신 반영해 재작성", run: () => regenerateDraft(t, "Reflect the latest customer reply and confirmed information in the answer.") };
    if (t.source === "api" && t.purpose !== "request" && (t.draftSpecialistRevision ?? 0) !== (t.specialistRevision ?? 0)) {
      return { label: "전문부서 회신 반영해 재작성", run: () => regenerateDraft(t, "Incorporate all registered specialist replies as evidence, distinguishing confirmed findings from hypotheses.") };
    }
    if (!hasCurrentReplyPreview(t)) return { label: t.translatingReply ? "변환 중…" : "고객 언어로 변환", run: () => { void prepareCustomerReply(t); } };
    if (canSend(t)) return { label: "발송하기", run: () => openModal("send", { id: t.id }) };
    return { label: "발송 문구 검토하기", run: () => { document.getElementById("answer-editor")?.scrollIntoView({ behavior: "smooth", block: "center" }); } };
  }
  if (c.missingInfo.length) return { label: "고객 질의서 작성", run: () => composeFromCopilot(t, "request") };
  if (waitingReviews(t).length || t.legacyReviewPending) return { label: "전문부서 회신 등록", run: () => openModal("expert-receive", { id: t.id }) };
  return { label: "답변 초안 작성", run: () => composeFromCopilot(t, "answer") };
}

type StepState = "done" | "current" | "waiting" | "todo" | "optional";
type Step = { key: string; label: string; sub: string; state: StepState; action?: { label: string; run: () => void } };
function flowSteps(t: Ticket): Step[] {
  const items = informationAssessment(t), req = requiredInformation(t).length, reply = latestCustomerReply(t);
  const pending = waitingReviews(t).length + (t.legacyReviewPending ? 1 : 0), gotExpert = t.events.some((e) => e.kind === "expert");
  const missing = items.filter((x) => !["provided", "confirmed"].includes(x.status)).length, needsCheck = t.customerRequestStatus === "received" && reply && req > 0 && reply.id !== t.reviewedReplyKey;
  const writing = !!t.draft && t.purpose === "answer";
  const done = t.stage === 5, analysisReady = t.source !== "api" || t.analysisReady;
  const steps: Step[] = [
    { key: "intake", label: "접수·분석", sub: analysisReady ? "완료" : t.status, state: analysisReady ? "done" : "current" },
    { key: "info", label: "고객 정보", sub: !analysisReady ? "필수정보 확인 대기" : !req ? "추가 자료 불필요" : t.customerRequestStatus === "none" && missing ? `자료 필요 ${missing}건` : informationSummary(t), state: !analysisReady ? "todo" : !req || !missing ? "done" : t.customerRequestStatus === "waiting" ? "waiting" : "current",
      action: needsCheck && !done ? { label: "수신 자료 확인", run: () => openModal("review-customer", { id: t.id }) } : undefined },
    { key: "expert", label: "전문부서", sub: pending ? `회신 대기 ${pending}건` : gotExpert ? "회신 수신" : "요청 없음 (선택)", state: pending ? "current" : gotExpert ? "done" : "optional",
      action: pending && !done ? { label: "회신 등록", run: () => openModal("expert-receive", { id: t.id }) } : undefined },
    { key: "answer", label: "답변 작성", sub: t.sent ? "작성 완료" : writing ? (t.reviewed ? "발송 준비 완료" : "영어 초안 검토 중") : "작성 전", state: t.sent ? "done" : writing ? "current" : "todo" },
    { key: "send", label: "발송", sub: t.sent ? (t.customerOutcome === "resolved" ? "해결 회신 수신" : t.customerOutcome === "provided" ? "정보 확인 회신" : "발송 완료") : "대기", state: t.sent ? "done" : "todo",
      action: reply ? { label: "고객 회신 보기", run: () => openModal("customer-reply", { id: t.id }) } : undefined },
    { key: "done", label: "완료", sub: done ? "처리 완료" : "대기", state: done ? "done" : "todo" },
  ];
  if (done) steps.forEach((x) => (x.state = "done"));
  else if (!steps.some((x) => x.state === "current")) { const i = steps.findIndex((x) => x.state === "todo"); if (i >= 0) steps[i].state = "current"; }
  // 병행 중인 단계가 둘 이상이면 하나만 "지금 단계"로 펼치고(답변 작성 중이면 답변 작성), 나머지는 "대기"로 접는다.
  const live = steps.map((x, i) => (x.state === "current" ? i : -1)).filter((i) => i >= 0);
  if (live.length > 1) {
    // 전문부서 회신을 기다리는 중이면 그 단계가 지금 단계(답변 초안이 있어도 회신 전에는 발송하지 못한다).
    const focus = live.find((i) => steps[i].key === (pending ? "expert" : "answer")) ?? live[0];
    live.forEach((i) => { if (i !== focus) steps[i].state = steps[i].key === "expert" ? "waiting" : "todo"; });
    if (pending && steps[focus].key === "expert") steps[focus].state = "waiting";
  }
  if (pending && !done) { const e = steps.find((x) => x.key === "expert"); if (e) e.state = "waiting"; } // 회신을 기다리는 단계는 항상 시계 아이콘
  return steps;
}

const DETAIL_TABS = [["문의·답변", "문의·답변"], ["처리 이력", "처리 이력"], ["고객·제품 정보", "고객·제품 정보"]] as const;

export default function TicketDetail() {
  useStore();
  const { ticketId } = useParams();
  const t = findTicket(ticketId);
  useEffect(() => { if (t && unreadReplies(t) > 0) markSeen(t); }, [t?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!t) return <Navigate to="/tickets" replace />;
  return (
    <div data-ticket-id={t.id} className="grid grid-cols-1 items-start min-[1360px]:grid-cols-[minmax(0,1fr)_400px]">
      <section aria-label="문의 상세" key={t.id} className="grid min-w-0 content-start gap-8 px-12 pb-16">
        {/* 제목·진행 단계·탭은 스크롤해도 맨 위에 고정된다 */}
        <div className="sticky top-0 z-20 -mx-12 grid gap-6 bg-background px-12 pb-1 pt-10">
          <Header t={t} />
          <Progress t={t} />
          <UnderlineTabs tabs={DETAIL_TABS} value={ui.tab as (typeof DETAIL_TABS)[number][0]} onChange={(v) => setUi({ tab: v })} />
        </div>
        {ui.tab === "처리 이력" ? <History t={t} /> : ui.tab === "고객·제품 정보" ? <Customer t={t} /> : <Conversation t={t} />}
      </section>
      <Copilot t={t} />
    </div>
  );
}

function evidenceCount(t: Ticket) {
  const c = answerContext(t);
  return c.technical.documents.length + c.technical.similarCases.length + (c.expertReferences?.length || 0);
}

function Header({ t }: { t: Ticket }) {
  const go = useGo();
  return (
    <header className="grid gap-5">
      <div className="flex items-center gap-3 text-sm">
        <button className="text-info hover:underline" onClick={() => { setUi({ filter: "전체" }); go.list({ filter: "전체" }); }}>‹ 문의 목록</button>
        <span className="text-muted-foreground">/ <Mono>{t.id}</Mono> · {t.channel || "WEB FORM"}</span>
        <div className="ml-auto flex items-center gap-2">
          {t.source === "api" && t.apiCustomerId && <Button size="sm" variant="outline" onClick={() => openModal("care", { customerId: t.apiCustomerId, ticketId: t.id, kind: "notice" })}>진행 상황 안내</Button>}
          {canAssign ? <Button variant="outline" title={assignmentSummary(t).join(" · ")} onClick={() => openModal("assign", { id: t.id })}>{t.owner && <PersonAvatar name={t.owner} size={22} />}{t.owner || "담당자 배정"}<ChevronDown /></Button>
            : <span title="담당자 배정은 팀장만 할 수 있습니다" className="inline-flex h-9 items-center gap-2 rounded-full bg-card px-4 text-sm shadow-card">{t.owner && <PersonAvatar name={t.owner} size={22} />}{t.owner || "미배정"}</span>}
        </div>
      </div>
      <h1 className="text-[30px] font-bold leading-tight tracking-tight">{t.source !== "api" && t.id === SAMPLE ? "운전 직후 E.OC 트립 발생" : t.title}</h1>
      <div className="flex flex-wrap items-center gap-2.5 text-sm text-muted-foreground">
        <StatusTag t={t} /><PriorityTag p={t.priority} />{t.stage !== 5 && <SlaTag t={t} />}
        <span>· {t.product} · {t.country} · 고객 언어 {customerLanguage(t)}</span>
      </div>
    </header>
  );
}

const STEP_ICON: Record<StepState, [LucideIcon, string, string]> = {
  done: [CircleCheck, "text-success", "완료"],
  current: [CircleDot, "text-[#003377]", "진행 중"],
  waiting: [Clock, "text-warning", "회신 대기"],
  todo: [Circle, "text-muted-foreground/60", "대기"],
  optional: [CircleDashed, "text-muted-foreground/60", "선택"],
};
/** 처리 진행: 큰 단계 이름과 상태 아이콘만. 단계마다 마우스를 올리면 한 줄 설명이 뜬다. 지금 할 일은 오른쪽 Copilot 의 "현재 판단"이 알려 준다. */
function Progress({ t }: { t: Ticket }) {
  const steps = flowSteps(t);
  return (
    <section aria-label="처리 진행" className="rounded-2xl bg-card px-7 py-5 shadow-card">
      <ol className="grid grid-cols-6 gap-4">
        {steps.map((s) => {
          const [Icon, tone, text] = STEP_ICON[s.state];
          return (
            <li key={s.key} title={s.sub} aria-current={s.state === "current" ? "step" : undefined} className="flex items-center gap-2.5">
              <Icon className={cn("size-5 shrink-0", tone)} aria-hidden />
              <span className={cn("text-[15px]", s.state === "current" ? "font-semibold" : s.state === "todo" || s.state === "optional" ? "text-muted-foreground" : "font-medium")}>{s.label}</span>
              <span className="sr-only">{text}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/* ───────── 문의·답변 ───────── */
/** 카드마다 맨 앞에 "누가 한 말인지" 라벨을 붙인다: 고객(파랑) · 우리 발송(남색 채움). 전문부서 요청·회신은 고객이 못 본 내부 업무라 오른쪽 Copilot 에서 보여 준다. */
const ROLE = {
  customer: { Icon: User, tone: "bg-[#026bb4]/10 text-[#026bb4]" },
  us: { Icon: Send, tone: "bg-[#003377] text-white" },
} as const;
function Message({ role, label, title, right, children, foot }: { role: keyof typeof ROLE; label: string; title: ReactNode; right?: ReactNode; children?: ReactNode; foot?: ReactNode }) {
  const { Icon, tone } = ROLE[role];
  return (
    <Card className="gap-4 p-7 text-[15px] leading-[1.7] ring-0">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className={cn("inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full px-3 text-[13px] font-medium", tone)}><Icon className="size-3.5" aria-hidden />{label}</span>
          <strong className="truncate text-base font-semibold">{title}</strong>
        </div>
        {right}
      </div>
      {children}{foot}
    </Card>
  );
}
const Attachments = ({ files, t }: { files: string[]; t: Ticket }) => (
  <div className="flex flex-wrap gap-2">
    {files.map((f) => <Button key={f} size="sm" variant="outline" onClick={() => openModal("file", { file: f, id: t.id })}><Paperclip />{f}</Button>)}
  </div>
);

function Original({ t }: { t: Ticket }) {
  const sample = t.source !== "api" && t.id === SAMPLE;
  const text = t.translate ? (sample ? "iS7 75kW가 운전 명령 직후 E.OC로 트립합니다. 재시작해도 같은 현상이 발생합니다." : t.bodyKo || "한국어 번역이 아직 준비되지 않았습니다. 원문을 확인해 주세요.") : sourceInquiry(t);
  return (
    <Message role="customer" label="고객 문의" title={t.company} right={<small className="text-muted-foreground">{t.receivedLabel || (t.source === "api" ? "접수 시각 미기록" : `${INQUIRY_AT} UTC`)}</small>}>
      <div className="flex items-center gap-3"><Tag className="rounded-md">원문 · {t.language}</Tag><button className="text-xs text-info hover:underline" onClick={() => toggleTranslate(t)}>{t.translate ? "원문 보기" : "한국어 번역"}</button></div>
      <p className="leading-relaxed">{text}</p>
      {sample && <><p className="text-muted-foreground">FW 4.00 · 부하 69% · 재시작 후 반복</p><Attachments t={t} files={["event_log.csv", "params.bak"]} /></>}
    </Message>
  );
}

const HIDDEN = ["escalation", "expert", "feedback", "feedback_decision", "draft", "draft-rewrite", "saved", "draft-retained", "draft-replaced", "assignment", "registered"];
function Conversation({ t }: { t: Ticket }) {
  const reqName = (e: any) => t.events.find((r) => r.id === e.requestId)?.department || "전문부서";
  return (
    <div className="grid gap-8">
      <section aria-label="고객 소통" className="grid gap-5">
        <h2 className="text-sm font-semibold">고객 소통</h2>
        <Original t={t} />
        {t.events.filter((e) => !HIDDEN.includes(e.kind)).map((e, i) => {
          if (["customer", "customer-followup"].includes(e.kind))
            return (
              <Message key={i} role="customer" label="고객 회신" title={e.kind === "customer-followup" ? "후속 회신" : "추가정보"} right={<small className="text-muted-foreground">{e.time}</small>}>
                <p>{e.text}</p>
                {e.informationChecks && <div className="flex flex-wrap gap-2">{requiredInformation(t).filter((x) => e.informationChecks[x.id]).map((x) => { const s = e.informationChecks[x.id].status; return <Tag key={x.id} tone={s === "confirmed" ? "green" : ""}>{x.label} · {({ confirmed: "확인 완료", unusable: "보완 필요", missing: "미수신" } as any)[s]}</Tag>; })}</div>}
                <Attachments t={t} files={e.files || []} />
              </Message>
            );
          if (e.kind === "sent")
            return (
              <Message key={i} role="us" label="우리 발송" title={e.purpose === "request" ? "고객 질의서" : "고객 답변"} right={<Tag tone="green">발송 완료</Tag>}>
                <p className="whitespace-pre-line">{e.text}</p>
                {e.masterText && e.masterText !== e.text && <details className="text-sm"><summary className="cursor-pointer text-muted-foreground">영어 원본 보기 · 발송 언어 {e.replyLanguage}</summary><p className="mt-2 whitespace-pre-line text-muted-foreground">{e.masterText}</p></details>}
                <small className="text-muted-foreground">{e.time} · {e.actor || t.owner}{e.replyLanguage && e.replyLanguage !== "English" ? ` · ${e.replyLanguage}` : ""}{e.edited === true ? ` · 수정 후 승인${e.feedbackReason ? ` (${feedbackLabel(e.feedbackReason)})` : ""}` : e.edited === false ? " · AI 초안 그대로 승인" : ""}{e.checks && e.checks.some((c: any) => !c.passed) ? " · 점검 실패 확인 후 발송" : ""}</small>
              </Message>
            );
          return (
            <div key={i} className="flex items-center gap-3 px-1 text-sm"><span className="text-success">✓</span><b className="font-medium">{e.text}</b><small className="ml-auto text-muted-foreground">{e.time}</small></div>
          );
        })}
      </section>
      {t.stage === 5 ? <Completed t={t} /> : (
        <>
          <Editor t={t} />
          {t.sent && <div className="flex justify-end"><Button variant="outline" onClick={() => openCompletion(t)}>처리 결과 기록 및 완료</Button></div>}
        </>
      )}
    </div>
  );
}

function Completed({ t }: { t: Ticket }) {
  const r = t.resolution || {};
  const go = useGo();
  return (
    <Card className="gap-5 p-6">
      <div className="flex items-center justify-between"><h2 className="text-lg font-bold">처리 완료</h2>{t.sent && <Tag tone="green">답변 발송됨</Tag>}</div>
      {!Object.values(r).some(Boolean) ? <p className="text-[15px] text-muted-foreground">완료할 때 입력된 처리 결과가 없습니다.</p> : <Facts rows={[["완료 구분", ({ resolved: "문제 해결 확인", provided: "정보 제공 완료", unconfirmed: "해결 여부 미확인" } as any)[r.outcome] || "미기록"], ["최종 원인", r.cause || "미기록"], ["수행 조치", r.action || "미기록"], ["처리 결과", r.result || "미기록"], ["확인 근거", r.verification || "미기록"], ["완료 담당자", r.confirmedBy || t.owner || "미기록"]]} />}
      <div className="flex gap-2">
        {latestCustomerReply(t) && <Button variant="outline" onClick={() => openModal("customer-reply", { id: t.id })}>고객 회신 보기</Button>}
        <Button variant="ghost" onClick={() => go.knowledge("완료 문의", { completedTicket: t.id, completedFilter: "전체 기록", kquery: "" })}>축적된 처리 기록</Button>
      </div>
    </Card>
  );
}

/** 작성 카드: 화면 아래에 붙어 있고, 내용이 길면 카드 안에서만 스크롤된다. 영어로 쓴 초안을 검토·수정하고, AI 에게 수정을 지시하고, 승인한다. */
function Editor({ t }: { t: Ticket }) {
  const [folded, setFolded] = useState(false);
  if (t.activeComposer === "expert") return <ExpertEditor t={t} />;
  if (!t.draft && !t.composerOpen) return null;
  const manual = isManualReplyTicket(t);
  const isRequestDraft = t.purpose === "request", expertWaiting = waitingReviews(t).length > 0 || !!t.legacyReviewPending;
  // 전문부서 회신을 기다리는 동안은 고객 답변 작성칸을 열지 않는다(회신을 보고 써야 하므로). 고객에게 보내는 질의서는 해당 없음.
  if (!isRequestDraft && expertWaiting && !t.sent && t.stage !== 5) {
    return (
      <Card className="grid gap-1.5 p-8 text-center">
        <strong className="text-base">전문부서 회신을 기다리는 중입니다</strong>
        <p className="text-sm text-muted-foreground">회신을 등록하면 고객 답변을 작성할 수 있습니다.{t.draft ? " 미리 써 둔 초안은 그때 이어서 볼 수 있습니다." : ""}</p>
      </Card>
    );
  }
  const live = answerContext(t), used = t.source === "api" ? answerContext(t, t.purpose) : t.draftContext || answerContext(t, t.purpose);
  const isNew = contextIsNew(t), isRequest = (t.purpose || live.purpose) === "request";
  const lang = customerLanguage(t), busy = !!t.regenerating || !!t.sending;
  return (
    <Card id="answer-editor" className="scroll-mt-6 gap-0 p-0 shadow-float ring-1 ring-black/5">
      <div className="flex items-center justify-between gap-4 px-8 pb-3 pt-7">
        <h2 className="flex items-center gap-3 text-xl font-bold">{isRequest ? "고객 질의서 작성" : "고객 답변 작성"}
          {t.draft && <button type="button" aria-expanded={!folded} onClick={() => setFolded((v) => !v)} className="inline-flex items-center gap-1 rounded-full bg-muted px-3 py-1 text-xs font-normal text-muted-foreground hover:text-foreground"><ChevronDown className={cn("size-3.5 transition-transform", folded && "-rotate-90")} aria-hidden />{folded ? "펼치기" : "접기"}</button>}
        </h2>
        <div className="flex items-center gap-2 text-sm text-muted-foreground"><span>작성 English</span><span>→ 고객 언어 <b className="font-medium text-foreground">{lang}</b></span></div>
      </div>
      {!folded && (
        <div className="grid gap-6 px-8 pb-7 pt-2">
          {t.draft ? <Sources c={used} /> : live.purpose === "request" ? <Sources c={live} /> : null}
          {isNew && <div className="rounded-2xl bg-warning/15 px-5 py-3 text-sm text-warning-ink">{t.source === "api" && (t.draftSpecialistRevision ?? 0) !== (t.specialistRevision ?? 0) ? "새 전문부서 회신을 반영해 AI에게 답변 재작성을 요청한 뒤 검토하세요. 기존 초안은 보존됩니다." : "새 자료가 도착했습니다. 작성 중인 내용과 함께 확인해 주세요."}</div>}
          {t.draft || manual ? (
            <>
              <div className="grid gap-3">
                <div className="flex items-center gap-2.5 text-sm font-medium">{!manual && <AiMark />}{manual ? "담당자 작성 · 영어 답변" : `미발송 초안 · v${t.draftVersion || 1}`}{!manual && isEdited(t) && <Tag tone="amber">AI 초안에서 수정됨</Tag>}{busy && <small className="font-normal text-info">AI가 다시 만드는 중…</small>}</div>
                <Textarea aria-label="영어 초안" disabled={busy} className="min-h-36 max-h-56 rounded-2xl border-0 bg-muted/60 px-5 py-4 text-base leading-[1.8]" value={t.draft} onChange={(e) => editDraft(t, e.target.value)} />
              </div>
              {!manual && <RewriteBox t={t} busy={busy} />}
              {hasCurrentReplyPreview(t) && <section className="grid gap-2 rounded-2xl bg-muted/60 p-5">
                <strong className="text-sm">{lang} · 발송용 문구{t.source !== "api" ? " (예시 시뮬레이션)" : ""}</strong>
                <p dir="auto" className="whitespace-pre-wrap text-base leading-[1.8]">{t.replyPreview.final_text}</p>
              </section>}
            </>
          ) : (
            <div className="grid gap-2 rounded-2xl bg-muted/60 p-8 text-center">
              <strong className="text-base">{live.purpose === "request" ? "요청할 정보를 확인하고 요청문을 작성하세요." : live.availableReferences.length ? "분석 결과와 근거가 준비되었습니다." : "문의 분석 결과를 확인해 주세요."}</strong>
              <p className="text-sm text-muted-foreground">{live.purpose === "request" ? "고객 질의서 초안" : "고객 답변 초안"}은 영어로 작성됩니다. 작성하려면 작성 버튼을 눌러 주세요.</p>
            </div>
          )}
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-4 border-t px-8 py-5">
        {t.draft && hasCurrentReplyPreview(t) ? (
          <div className="grid gap-1">
            <label className="flex items-center gap-2.5 text-[15px]"><Checkbox checked={!!t.reviewed} onCheckedChange={(v) => setReviewed(t, v === true)} />{live.purpose === "request" ? "요청 항목과 내용을 확인했습니다." : "내용과 근거를 검토했습니다."}</label>
            <small className="pl-[26px] text-muted-foreground">{!isRequestDraft && expertWaiting ? "전문부서 회신을 등록한 뒤 발송할 수 있습니다" : t.reviewed ? "검토가 끝났습니다. 발송하기를 눌러 주세요" : "영어 초안과 변환된 발송용 문구를 확인한 뒤 체크해 주세요"}</small>
          </div>
        ) : <small className="text-muted-foreground">담당자 검토 후 발송</small>}
        {t.draft && <div className="ml-auto flex shrink-0 items-center gap-2">
          {hasCurrentReplyPreview(t) ? (
            <Button size="lg" className="px-6" disabled={!canSend(t) || busy} onClick={() => canSend(t) && openModal("send", { id: t.id })}>발송하기</Button>
          ) : (
            <Button variant="outline" size="lg" disabled={busy || t.translatingReply} onClick={() => void prepareCustomerReply(t)}>{t.translatingReply ? "변환 중…" : "고객 언어로 변환"}</Button>
          )}
        </div>}
      </div>
    </Card>
  );
}

/** 피드백 루프: "이렇게 바꿔 줘"를 보내면 그 지시대로 초안을 다시 만든다. 한 번 탭으로 고를 수 있는 지시도 있다. */
function RewriteBox({ t, busy }: { t: Ticket; busy: boolean }) {
  const [ask, setAsk] = useState("");
  const history: { version: number; instruction: string }[] = t.draftRequests || [];
  const last = history[history.length - 1];
  const submit = () => { if (ask.trim() && !busy) { regenerateDraft(t, ask); setAsk(""); } };
  return (
    <section aria-label="AI에게 수정 요청" className="grid gap-3">
      <form className="flex items-center gap-3" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <Input aria-label="수정 지시" className="h-11 flex-1 rounded-full border-0 bg-muted/60 px-5 text-[15px]" disabled={busy} placeholder="AI에게 수정 요청 (예: 더 정중하게, 원인은 확정이 아니라고 분명히)" value={ask} onChange={(e) => setAsk(e.target.value)} />
        <Button type="submit" size="lg" variant="secondary" disabled={busy || !ask.trim()}>{busy ? "만드는 중…" : "다시 생성"}</Button>
      </form>
      <div className="flex flex-wrap items-center gap-2">
        {QUICK_INSTRUCTIONS.map((q) => <button key={q} type="button" disabled={busy} onClick={() => setAsk((cur) => (cur.includes(q) ? cur : cur ? `${cur}, ${q}` : q))} className="rounded-full bg-[#003377]/[0.06] px-3.5 py-1.5 text-[13px] text-[#003377] transition-colors hover:bg-[#003377]/10 disabled:opacity-50">{q}</button>)}
        {last && <small aria-label="수정 요청 기록" className="ml-auto truncate text-muted-foreground">v{last.version} · {last.instruction}{history.length > 1 ? ` 외 ${history.length - 1}건` : ""}</small>}
      </div>
    </section>
  );
}
function Sources({ c }: { c: any }) {
  if (c.purpose === "request") return <div className="flex flex-wrap gap-2">{c.missingInfo.map((v: string) => <Tag key={v}>{v}</Tag>)}</div>;
  if (!c.references.length) return null;
  return <Disclosure title={`사용한 근거 ${c.references.length}건`}><div className="flex flex-wrap gap-2">{c.references.map((r: any) => <Tag key={r.id}>{r.label}</Tag>)}</div></Disclosure>;
}

function ExpertEditor({ t }: { t: Ticket }) {
  const files = [...new Set([...(t.files || []), ...(t.source !== "api" && t.id === SAMPLE ? ["event_log.csv", "params.bak"] : [])])];
  const checked: string[] = t.expertDraftFiles || [];
  return (
    <Card id="answer-editor" className="scroll-mt-6 p-6 shadow-float ring-1 ring-black/5">
      <form className="grid gap-4" onSubmit={(e) => {
        e.preventDefault();
        const d = new FormData(e.currentTarget);
        submitExpertRequest(t, { department: String(d.get("department")), channel: String(d.get("channel")), body: t.expertDraft || "", files: checked });
      }}>
        <div className="flex items-center justify-between"><h2 className="text-lg font-bold">전문부서 요청서 작성 · 한국어</h2><Button type="button" size="sm" variant="ghost" onClick={() => closeComposer(t)}>닫기</Button></div>
        <div className="grid grid-cols-2 gap-3">
          <label className="grid gap-1.5 text-sm"><span className="text-muted-foreground">대상 부서</span>
            <NativeSelect disabled={t.specialistSaving} name="department" value={t.expertDraftDepartment || expertDepartments[0]} onChange={(e) => { t.expertDraftDepartment = e.target.value; commit(); if (t.source === "api") void escalationDraftViaApi(t, e.target.value); }}>{expertDepartments.map((n) => <option key={n}>{n}</option>)}</NativeSelect></label>
          <label className="grid gap-1.5 text-sm"><span className="text-muted-foreground">전달 방식</span><NativeSelect disabled={t.specialistSaving} name="channel" defaultValue="이메일"><option>이메일</option><option>기업 메신저</option></NativeSelect></label>
        </div>
        {t.expertDraftLoading && <small className="text-muted-foreground">AI가 요청서 초안을 쓰는 중이에요…</small>}
        <Textarea disabled={t.specialistSaving} aria-label="전문부서 요청서" required className="min-h-32 max-h-44 leading-relaxed" value={t.expertDraft || ""} onChange={(e) => { t.expertDraft = e.target.value; commit(); }} />
        <fieldset className="grid gap-2 rounded-xl bg-background p-4"><legend className="px-1 text-sm text-muted-foreground">전달한 자료</legend>
          {files.length ? files.map((f) => (
            <label key={f} className="flex items-center gap-2 text-sm"><Checkbox checked={checked.includes(f)} onCheckedChange={(v) => { t.expertDraftFiles = v === true ? [...checked, f] : checked.filter((x) => x !== f); commit(); }} />{f}</label>
          )) : <small className="text-muted-foreground">등록된 첨부자료 없음</small>}
        </fieldset>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" required className="size-4 accent-[var(--primary)]" />요청 내용과 전달 자료를 확인했습니다.</label>
        <div className="flex items-center justify-between"><small className="text-muted-foreground">외부 전달 후 요청을 기록합니다.</small><Button type="submit" disabled={t.specialistSaving || t.expertDraftLoading}>{t.specialistSaving ? "저장 중…" : "검토 요청 기록"}</Button></div>
      </form>
    </Card>
  );
}

/* ───────── 처리 이력 · 고객 정보 ───────── */
/** 처리 이력 시각: 기록에 시각이 있으면 그 값을 같은 형식으로, 없으면 적어 둔 글자를 쓴다. */
const stamp = (e: { createdAt?: string; time?: string }) => (e.createdAt ? new Date(e.createdAt).toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).replace(/\.\s*/g, ".").replace(/\.(\d{2}):/, ". $1:").replace(/^(\d{2}\.\d{2})\.\s?/, "$1 · ") : e.time || "");
const ACTOR: Record<string, string> = { customer: "고객", system: "시스템" };
function History({ t }: { t: Ticket }) {
  const rows = [
    ...(t.source === "api" ? [] : [
      { time: `${INQUIRY_AT}`, title: "문의 접수", sub: `웹폼 · ${t.company}` },
      { time: `${INQUIRY_AT}`, title: "AI 분석 완료", sub: `${t.type} · ${t.product} · 근거 검색` },
    ]),
    ...t.events.filter((e) => !["feedback", "feedback_decision"].includes(e.kind)).map((e) => ({
      time: stamp(e),
      title: e.kind === "sent" ? (e.purpose === "request" ? "고객 질의서 발송" : "답변 발송하기") : e.kind === "customer" ? "고객 추가정보 등록" : e.kind === "expert" ? "전문부서 회신 등록" : e.text || "",
      sub: `${ACTOR[e.actor || ""] || e.actor || t.owner || "접수 담당자"}${e.kind === "sent" ? " · 발송 결과 기록" : ""}${e.kind === "sent" && e.edited === true ? ` · 수정 후 승인${e.feedbackReason ? ` · 사유 ${feedbackLabel(e.feedbackReason)}` : ""}` : e.kind === "sent" && e.edited === false ? " · 그대로 승인" : ""}${e.feedbackNote ? ` · “${e.feedbackNote}”` : ""}`,
    })),
  ];
  return (
    <Card className="gap-0 divide-y p-0">
      {rows.map((r, i) => (
        <div key={i} className="grid grid-cols-[110px_1fr] gap-4 px-6 py-4"><small className="pt-0.5 text-muted-foreground">{r.time}</small><div><strong>{r.title}</strong><p className="text-sm text-muted-foreground">{r.sub}</p></div></div>
      ))}
    </Card>
  );
}
function Customer({ t }: { t: Ticket }) {
  const additionalFields: [string, ReactNode][] = Object.entries(t.apiExtraction?.field_values || {})
    .filter(([id]) => !["product_model", "current_fw", "error_code", "serial_no"].includes(id))
    .map(([id, value]) => [t.fieldLabels?.[id] || id, String(value)]);
  if (t.secondaryType) additionalFields.unshift(["보조 유형", t.secondaryType]);
  return (
    <Card className="gap-5 p-6">
      <h2 className="text-lg font-bold">고객·제품 정보</h2>
      <Facts rows={[["회사", t.company], ["국가", t.country], ["답변 언어", customerLanguage(t)], ["제품", t.product], ["문의 유형", t.type], ["오류 코드", answerContext(t).analysis.errorCode || "—"], ["펌웨어", t.apiExtraction?.fw_version || "—"], ["시리얼", t.apiExtraction?.serial_no || "—"], ["긴급도 판단", t.apiExtraction?.assessed_urgency || t.apiExtraction?.urgency || "미확인"], ["담당자", t.owner || "미배정"], ...additionalFields]} />
    </Card>
  );
}

/* ───────── AI Copilot ───────── */
function Disclosure({ title, count, children, defaultOpen }: { title: ReactNode; count?: ReactNode; children: ReactNode; defaultOpen?: boolean }) {
  return (
    <details open={defaultOpen} className="group rounded-xl bg-background">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-semibold [&::-webkit-details-marker]:hidden">
        <ChevronRight className="size-4 text-muted-foreground transition-transform group-open:rotate-90" /><span>{title}</span><span className="ml-auto text-xs font-normal text-muted-foreground">{count}</span>
      </summary>
      <div className="grid gap-3 px-4 pb-4 text-sm">{children}</div>
    </details>
  );
}

function judgment(t: Ticket) {
  if (t.source === "api" && !t.analysisReady && !isManualReplyTicket(t) && !t.sent && t.stage !== 5) return { title: t.status || "분석 확인 대기",
    task: "문의 분석과 필수정보 결과를 확인한 뒤 다음 작업을 진행하세요.", note: "", reason: "아직 조회되지 않은 값을 충족으로 판단하지 않습니다.", missing: [] as string[] };
  if (!t.owner && t.stage !== 5 && !t.sent) return { title: "담당자 미배정", task: canAssign ? "담당자를 배정한 뒤 처리를 시작하세요." : "팀장이 담당자를 배정하면 처리를 시작할 수 있습니다.", note: "", reason: "배정하면 담당자의 오늘 할 일에 올라갑니다.", missing: [] as string[] };
  if (t.activeComposer === "expert" && t.stage !== 5 && !t.sent) return { title: "전문부서 요청서 작성 중", task: "대상 부서와 요청 내용을 확인하고 요청서를 보내세요.", note: "", reason: "보내면 이 문의는 회신이 올 때까지 전문부서 회신 대기가 됩니다.", missing: [] as string[] };
  if (isManualReplyTicket(t) && !t.draft && !t.sent && t.stage !== 5) return {
    title: "담당자 검토 필요", task: "문의와 근거를 확인하고 영어 답변을 직접 작성하세요.",
    note: "", reason: "작성한 답변은 고객 언어 변환과 최종 점검을 거칩니다.", missing: [] as string[],
  };
  const reply0 = latestCustomerReply(t);
  // nextAction 과 같은 순서: 고객 회신을 기다리거나 확인할 일이 있으면 초안이 있어도 그 일이 먼저다.
  const customerFirst = t.customerOutcome === "needs-support" || t.customerRequestStatus === "waiting" || (t.customerRequestStatus === "received" && !!reply0 && requiredInformation(t).length > 0 && reply0.id !== t.reviewedReplyKey);
  if (t.draft && t.stage !== 5 && !t.sent && !customerFirst) {
    const lang = customerLanguage(t), isRequest = t.purpose === "request", pending = waitingReviews(t).length || (t.legacyReviewPending ? 1 : 0);
    if (!isRequest && pending) return { title: "전문부서 회신 대기", task: "회신을 등록하면 고객 답변을 작성할 수 있습니다.", note: `전문부서 회신 ${pending}건 대기 중`, reason: "답변은 전문부서 회신을 확인한 뒤 작성합니다.", missing: [] as string[] };
    const what = isRequest ? "고객 질의서" : "고객 답변";
    const [task, why] = !hasCurrentReplyPreview(t)
      ? ["영어 초안을 검토하고, 필요하면 고쳐 주세요.", "초안은 영어로 작성됩니다. 검토 후 고객 언어로 변환 버튼을 눌러 주세요."]
      : [t.reviewed ? `${lang} 발송용 문구를 확인한 뒤 발송하세요.` : "영어 초안과 변환된 문구를 확인하고 검토 완료에 체크해 주세요.", "발송하면 영어 원본과 발송본이 함께 이력에 남습니다."];
    const lacking = !isRequest ? answerContext(t).missingInfo.length : 0;
    return { title: `${what} 작성 중`, task, note: lacking ? `아직 받지 못한 자료 ${lacking}건` : "", reason: why, missing: [] as string[] };
  }
  const c = answerContext(t), missing = c.missingInfo.length, expertPending = waitingReviews(t).length || t.legacyReviewPending;
  let title: string, task: string, reason: string;
  const reply = reply0;
  if (t.apiStatus === "REJECTED") { title = "반려된 문의"; task = "문의가 반려 처리되었습니다."; reason = "처리 이력에서 반려 기록을 확인하세요."; }
  else if (t.stage === 5) { const rec = Object.values(t.resolution || {}).some(Boolean); title = "처리 완료"; task = rec ? "최종 처리 결과가 기록되었습니다." : "문의는 완료됐지만 처리 결과 기록은 비어 있습니다."; reason = "재문의는 기존 문의에서 이어서 처리합니다."; }
  else if (t.sent && t.customerOutcome === "resolved") { title = "고객 해결 확인 수신"; task = "회신과 최종 처리 결과를 확인하고 완료하세요."; reason = "해결 확인 근거는 고객 회신 이력에 남아 있습니다."; }
  else if (t.sent && t.customerOutcome === "provided") { title = "고객 정보 확인 완료"; task = "응대 결과를 기록하고 완료하세요."; reason = "정보 확인 회신과 기술적 해결 확인은 구분합니다."; }
  else if (t.sent) { title = "고객 답변 발송 완료"; task = "고객 회신이나 처리 결과를 확인하세요."; reason = "회신이 없으면 해결 여부는 미확인입니다."; }
  else if (t.customerOutcome === "needs-support") { title = "후속 문의 · 재검토 필요"; task = "이전 조치와 고객의 새 증상을 함께 확인하세요."; reason = "이전 완료 결과는 현재 해결 근거로 확정하지 않습니다."; }
  else if (t.customerRequestStatus === "waiting") { title = "고객 회신 대기"; task = "고객이 요청 자료를 제출하기를 기다리고 있습니다."; reason = "회신이 들어오면 같은 문의에서 내용을 확인합니다."; }
  else if (t.customerRequestStatus === "received" && reply && requiredInformation(t).length && reply.id !== t.reviewedReplyKey) { title = "고객 자료 수신 · 확인 필요"; task = "수신된 내용과 첨부자료를 확인하세요."; reason = "회신 수신만으로 필요한 자료가 충족된 것은 아닙니다."; }
  else if (missing) { title = t.customerRequestStatus === "received" ? "회신 수신 · 추가정보 미충족" : "추가정보 필요 · 원인 미확정"; task = t.customerRequestStatus === "received" ? "아직 충족되지 않은 자료만 추가로 요청하세요." : "고객에게 아래 자료를 요청하세요."; reason = "이 자료가 있어야 원인 후보를 좁히고 정확한 답변을 쓸 수 있습니다."; }
  else if (t.customerRequestStatus === "received" && reply && !expertPending) { title = "고객 회신 수신"; task = "회신 내용을 확인하고 고객 답변을 작성하세요."; reason = "회신 내용은 고객 소통에서 볼 수 있습니다."; }
  else if (expertPending) { title = "전문부서 회신 대기"; task = "검토 결과를 받으면 해당 요청에 등록하세요."; reason = "회신을 확인한 뒤 고객 답변에 활용합니다."; }
  else if (c.expertResponse) { title = "전문부서 회신 수신"; task = "회신 내용을 검토하고 고객 답변을 작성하세요."; reason = "회신은 아래 참고 근거에서 확인할 수 있습니다."; }
  else if (c.availableReferences.length) { title = "참고 근거 확보 · 원인 미확정"; task = "현재 문의와 사례의 차이를 검토하세요."; reason = "과거 사례의 원인이 현재 고장의 원인과 같다고 확정할 수 없습니다."; }
  else if (branchChoice(t) === "expert") { title = "근거 부족 · 전문부서 확인 권장"; task = "연결된 참고 근거가 없어 전문부서 검토를 요청하는 것이 좋습니다."; reason = "일반 안내로 바로 답변하거나, 고객에게 자료를 요청할 수도 있습니다."; }
  else { title = "답변 작성 가능"; task = "추가 자료 없이 답변을 작성할 수 있습니다."; reason = "연결된 참고 근거가 없어 초안은 일반 안내 수준입니다. 전문 판단이 필요하면 전문부서에 요청하세요."; }
  return { title, task, note: "", reason, missing: (missing > 0 && t.stage !== 5 ? c.missingInfo : []) as string[] };
}

const SECTION_TONE = { info: "bg-info/10 text-info", navy: "bg-[#003377]/10 text-[#003377]", success: "bg-success/10 text-success" } as const;
/** Copilot 구역: 접지 않고 항상 보인다. 아이콘 색과 제목만 다르다. */
function PanelBlock({ icon: Icon, tone, title, count, children }: { icon: LucideIcon; tone: keyof typeof SECTION_TONE; title: ReactNode; count?: ReactNode; children: ReactNode }) {
  return (
    <section aria-label={typeof title === "string" ? title : undefined} className="py-6">
      <h3 className="mb-4 flex items-center gap-2.5 text-base font-semibold">
        <span className={cn("grid size-8 place-items-center rounded-full", SECTION_TONE[tone])}><Icon className="size-[18px]" aria-hidden /></span>{title}
        {count && <span className="ml-auto text-sm font-normal text-muted-foreground">{count}</span>}
      </h3>
      {children}
    </section>
  );
}
const LinkRow = ({ label, hint, onClick }: { label: ReactNode; hint?: ReactNode; onClick: () => void }) => (
  <button onClick={onClick} className="flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-muted">
    <span className="min-w-0 truncate text-[15px] font-medium">{label}</span>
    {hint && <span className="shrink-0 text-xs text-muted-foreground">{hint}</span>}
  </button>
);

/** AI Copilot: 오른쪽에 붙어서 따라 내려온다. 핵심만: 문의 요약 · 현재 판단(행동 버튼) · 전문부서 · 근거. */
function Copilot({ t }: { t: Ticket }) {
  const go = useGo();
  const c = answerContext(t), sum = inquirySummary(t), j = judgment(t), next = nextAction(t);
  const requests = referralRows().filter((r) => r.ticket.id === t.id);
  // 근거: 눌러서 이동하지 않고, 이름 아래에 핵심만 한두 줄로 보여 준다.
  const evidence: { key: string; label: React.ReactNode; hint: string; summary: string }[] = [
    ...Object.entries(c.analysis.fieldEvidence).map(([field, text]) => ({ key: `field:${field}`,
      label: t.fieldLabels?.[field] || field,
      hint: ["customer", "customer_form"].includes(c.analysis.fieldSources[field]) ? "고객 입력값" : c.analysis.fieldSources[field] === "staff" ? "담당자 확인" : "추출 근거",
      summary: String(text) })),
    ...Object.entries(c.analysis.unconfirmed).map(([field, reason]) => ({ key: `unconfirmed:${field}`,
      label: t.fieldLabels?.[field] || field, hint: "미확인",
      summary: [reason, t.apiExtraction?.unconfirmed_evidence?.[field]].filter(Boolean).join(" · ") })),
    ...c.expertReferences.map((r: any) => ({ key: r.id, label: r.label, hint: "회신", summary: String(r.text || "") })),
    ...c.technical.documents.map((d: any) => ({ key: d.id, label: d.label, hint: "기술문서", summary: String(d.text || "") })),
    ...c.technical.similarCases.map((r: any) => ({ key: r.id, label: <>유사 사례 <Mono>{r.id}</Mono></>, hint: r.matches ? "조건 유사" : "조건 차이", summary: r.text || `원인: ${r.cause} → 조치: ${r.action}` })),
  ];
  const open = t.stage !== 5 && !t.sent;
  const choice = branchChoice(t);
  const BRANCH: Record<Choice, [string, () => void]> = {
    answer: ["답변 초안 작성", () => composeFromCopilot(t, "answer")],
    expert: ["전문부서 요청서 작성", () => openExpertComposer(t)],
    request: ["고객 질의서 작성", () => composeFromCopilot(t, "request")],
  };
  const branches = choice ? [choice, ...(["answer", "expert", "request"] as Choice[]).filter((x) => x !== choice)] : [];
  const showNext = !!next && next.label !== "영어 초안 검토하기"; // 작성 카드가 바로 옆에 있어 같은 곳으로 보내는 버튼은 뺀다
  return (
    <aside aria-label="AI Copilot" className="m-4 ml-0 rounded-3xl bg-gradient-to-b from-[#026bb4]/[0.10] via-card via-[140px] to-card px-7 pb-3 pt-7 shadow-card max-[1359px]:mx-12 max-[1359px]:mb-12 max-[1359px]:mt-0 min-[1360px]:sticky min-[1360px]:top-4 min-[1360px]:max-h-[calc(100dvh-2rem)] min-[1360px]:overflow-y-auto">
      <div className="mb-2 flex items-center gap-2.5"><AiMark /><h2 className="text-xl font-bold">AI Copilot</h2></div>
      <div className="divide-y">
        <PanelBlock icon={FileText} tone="info" title="문의 요약">
          <div className="grid gap-2.5 text-[15px] leading-[1.7]">{sum.lines.map((l, i) => <p key={i}>{l}</p>)}</div>
          {t.apiExtraction?.safety_review_required && <p className="mt-2 text-sm text-warning-ink">안전 관련 담당자 검토가 필요합니다.</p>}
          {!!c.analysis.issues.length && <p className="mt-2 break-words text-xs text-muted-foreground">분석 검토 항목: {c.analysis.issues.join(" · ")}</p>}
        </PanelBlock>
        <PanelBlock icon={Compass} tone="navy" title="현재 판단">
          <div className="rounded-2xl bg-[#003377]/[0.06] p-5">
            <p className="text-[17px] font-semibold leading-snug tracking-[-0.01em]">{j.title}</p>
            <p className="mt-1.5 text-[15px] leading-[1.65] text-muted-foreground">{j.task}</p>
            {j.note && <p className="mt-2 flex items-center gap-1.5 text-sm text-warning-ink"><Clock className="size-4" aria-hidden />{j.note}</p>}
            {j.missing.length > 0 && <ul className="mt-3 grid gap-1.5 text-[15px]">{j.missing.map((x) => <li key={x} className="flex items-center gap-2"><span aria-hidden className="size-1.5 rounded-full bg-warning" />{x}</li>)}</ul>}
            {(choice || showNext) && (
              <div className="mt-5 grid gap-2.5">
                {choice ? branches.map((k, i) => <Button key={k} className="w-full" variant={i === 0 ? "default" : "outline"} onClick={BRANCH[k][1]}>{BRANCH[k][0]}</Button>)
                  : next && <Button className="w-full" disabled={next.waiting} variant={next.waiting ? "outline" : "default"} onClick={next.run}>{next.label}</Button>}
              </div>
            )}
          </div>
        </PanelBlock>
        {requests.length > 0 && (
          <PanelBlock icon={Building2} tone="navy" title="전문부서" count={`${requests.length}건`}>
            <ul className="-mx-3 grid">
              {requests.map((r) => (
                <li key={r.key}><LinkRow label={<>{r.source || "부서 미기록"} → {r.target || "부서 미기록"}</>} hint={<Tag tone={r.response ? "green" : "amber"}>{r.response ? "회신 받음" : "회신 대기"}</Tag>} onClick={() => (r.event ? openModal("department-review", { key: r.key }) : openModal("expert-receive", { id: t.id }))} /></li>
              ))}
            </ul>
          </PanelBlock>
        )}
        {evidence.length > 0 && (
          <PanelBlock icon={BookOpen} tone="success" title="근거" count={`${evidence.length}건`}>
            <ul className="-mx-3 grid">{evidence.slice(0, 4).map((e) => <li key={e.key} className="grid gap-1 px-3 py-2.5">
              <span className="flex items-center justify-between gap-3"><span className="min-w-0 truncate text-[15px] font-medium">{e.label}</span><span className="shrink-0 text-xs text-muted-foreground">{e.hint}</span></span>
              {e.summary && <span className="line-clamp-2 text-sm leading-relaxed text-muted-foreground">{e.summary}</span>}
            </li>)}</ul>
            {evidence.length > 4 && <p className="mt-1 px-3 text-xs text-muted-foreground">외 {evidence.length - 4}건</p>}
          </PanelBlock>
        )}
      </div>
    </aside>
  );
}
