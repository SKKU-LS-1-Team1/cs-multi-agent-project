// 티켓 상세: 대기열 · 티켓 요약 · 처리 상황 · 문의·답변/처리 이력/고객·제품 정보 · AI Copilot.
import { useEffect, useState, type ReactNode } from "react";
import { Navigate, useParams } from "react-router-dom";
import { Check, ChevronDown, ChevronRight, Paperclip } from "lucide-react";
import { Button } from "@admin/components/ui/button";
import { Card } from "@admin/components/ui/card";
import { Checkbox } from "@admin/components/ui/checkbox";
import { Textarea } from "@admin/components/ui/textarea";
import { Facts, NativeSelect, PriorityTag, SlaTag, StatusTag, Tag, UnderlineTabs, useGo } from "@admin/components/admin/common";
import {
  answerContext, assignmentSummary, cases, contextIsNew, customerLanguage, expertDepartments, informationAssessment, informationSummary,
  latestCustomerReply, needsLocalization, requiredInformation, sourceInquiry, unreadReplies, waitingReviews,
} from "@admin/lib/logic";
import {
  canSend, closeComposer, composeFromCopilot, editDraft, markSeen, openCompletion, openExpertComposer, setReviewed, submitExpertRequest, toggleTranslate,
} from "@admin/lib/actions";
import { commit, findTicket, openModal, setUi, ui, useStore } from "@admin/lib/store";
import { cn } from "@admin/lib/utils";
import type { Ticket } from "@admin/lib/types";

const SAMPLE = "CSV1-000050";
/** AI 가 만든 내용 표시: 프로토타입의 ✦ (네 꼭짓점 별). 글꼴과 무관하게 같은 모양이 나오도록 SVG 로 그린다. */
const AiMark = ({ className }: { className?: string }) => (
  <svg aria-hidden viewBox="0 0 24 24" className={cn("size-[22px] shrink-0 text-info", className)} fill="currentColor"><path d="M12 1.5c.9 6.2 4.3 9.6 10.5 10.5-6.2.9-9.6 4.3-10.5 10.5C11.1 16.3 7.7 12.9 1.5 12 7.7 11.1 11.1 7.7 12 1.5Z" /></svg>
);

type Next = { label: string; run?: () => void; waiting?: boolean };
/** 지금 담당자가 눌러야 할 단 하나의 행동. Copilot 의 '현재 판단'과 같은 규칙을 따른다. */
function nextAction(t: Ticket): Next | null {
  if (t.stage === 5) return null;
  if (t.sent) return { label: "처리 결과 기록 및 완료", run: () => openCompletion(t) };
  const reply = latestCustomerReply(t), c = answerContext(t);
  if (t.customerRequestStatus === "waiting") return { label: "고객 회신 대기 중", waiting: true };
  if (t.customerRequestStatus === "received" && reply && requiredInformation(t).length && reply.id !== t.reviewedReplyKey) return { label: "수신 자료 확인", run: () => openModal("review-customer", { id: t.id }) };
  if (t.draft) {
    if (canSend(t)) return { label: "승인 및 발송", run: () => openModal("send", { id: t.id }) };
    return { label: "영어 초안 검토하기", run: () => document.getElementById("answer-editor")?.scrollIntoView({ behavior: "smooth", block: "center" }) };
  }
  if (c.missingInfo.length) return { label: "추가정보 요청 작성", run: () => composeFromCopilot(t, "request") };
  if (waitingReviews(t).length || t.legacyReviewPending) return { label: "전문부서 회신 등록", run: () => openModal("expert-receive", { id: t.id }) };
  return { label: "답변 초안 작성", run: () => composeFromCopilot(t, "answer") };
}

type StepState = "done" | "current" | "waiting" | "todo" | "optional";
type Step = { key: string; label: string; sub: string; state: StepState; action?: { label: string; run: () => void } };
function flowSteps(t: Ticket): Step[] {
  const items = informationAssessment(t), req = requiredInformation(t).length, reply = latestCustomerReply(t);
  const pending = waitingReviews(t).length + (t.legacyReviewPending ? 1 : 0), gotExpert = t.events.some((e) => e.kind === "expert");
  const missing = items.filter((x) => x.status !== "confirmed").length, needsCheck = t.customerRequestStatus === "received" && reply && req > 0 && reply.id !== t.reviewedReplyKey;
  const writing = !!t.draft && t.purpose === "answer";
  const done = t.stage === 5;
  const steps: Step[] = [
    { key: "intake", label: "접수·분석", sub: "완료", state: "done" },
    { key: "info", label: "고객 정보", sub: !req ? "추가 자료 불필요" : t.customerRequestStatus === "none" && missing ? `자료 필요 ${missing}건` : informationSummary(t), state: !req || !missing ? "done" : "current",
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
    const focus = live.find((i) => steps[i].key === "answer") ?? live[0];
    live.forEach((i) => { if (i !== focus) steps[i].state = "waiting"; });
  }
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
    <div data-ticket-id={t.id} className="mx-auto grid max-w-[1260px] grid-cols-1 gap-6 px-10 pb-44 pt-8 min-[1360px]:grid-cols-[minmax(0,1fr)_370px]">
      <section aria-label="티켓 상세" key={t.id} className="grid min-w-0 content-start gap-6">
        <Header t={t} />
        <Progress t={t} />
        <UnderlineTabs tabs={DETAIL_TABS} value={ui.tab as (typeof DETAIL_TABS)[number][0]} onChange={(v) => setUi({ tab: v })} />
        {ui.tab === "처리 이력" ? <History t={t} /> : ui.tab === "고객·제품 정보" ? <Customer t={t} /> : <Conversation t={t} />}
      </section>
      <AiAnalysis t={t} />
    </div>
  );
}

function evidenceCount(t: Ticket) {
  const c = answerContext(t);
  return c.technical.documents.length + c.technical.similarCases.length + (c.expertResponse ? 1 : 0);
}

function Header({ t }: { t: Ticket }) {
  const go = useGo();
  return (
    <header className="grid gap-4">
      <div className="flex items-center gap-3 text-sm">
        <button className="text-info hover:underline" onClick={() => { setUi({ filter: "전체" }); go.list({ filter: "전체" }); }}>‹ 티켓 목록</button>
        <span className="text-muted-foreground">/ {t.id} · {t.channel || "WEB FORM"}</span>
        <div className="ml-auto flex items-center gap-2">
          <Button variant="outline" title={assignmentSummary(t).join(" · ")} onClick={() => openModal("assign", { id: t.id })}>{t.owner || "담당자 배정"}<ChevronDown /></Button>
        </div>
      </div>
      <h1 className="text-[30px] font-normal leading-tight tracking-tight">{t.id === SAMPLE ? "운전 직후 E.OC 트립 발생" : t.title}</h1>
      <div className="flex flex-wrap items-center gap-2.5 text-sm text-muted-foreground">
        <StatusTag t={t} /><PriorityTag p={t.priority} />{t.stage !== 5 && <SlaTag t={t} />}
        <span>· {t.product} · {t.country} · 고객 언어 {customerLanguage(t)}</span>
      </div>
    </header>
  );
}

/** 처리 진행: 끝난 단계는 체크, 지금 단계만 펼쳐서 "무엇을 해야 하는지"와 버튼 하나를 보여 준다. */
function Progress({ t }: { t: Ticket }) {
  const steps = flowSteps(t), j = judgment(t), next = nextAction(t);
  const doneCount = steps.filter((s) => s.state === "done").length;
  return (
    <section aria-label="처리 진행" className="rounded-2xl bg-card p-6 shadow-card">
      <div className="mb-5 flex items-baseline justify-between"><h2 className="text-lg font-medium">처리 진행</h2><small className="text-muted-foreground">{doneCount} / {steps.length} 단계 완료</small></div>
      <ol>
        {steps.map((s, i) => (
          <li key={s.key} aria-current={s.state === "current" ? "step" : undefined} className="relative grid grid-cols-[28px_minmax(0,1fr)] gap-x-4 pb-5 last:pb-0">
            {i < steps.length - 1 && <span aria-hidden className={cn("absolute bottom-0 left-[13px] top-7 w-px", s.state === "done" ? "bg-success/50" : "bg-border")} />}
            <span className={cn("relative z-10 grid size-7 place-items-center rounded-full border-2 bg-card text-xs font-semibold",
              s.state === "done" && "border-success bg-success text-white", s.state === "current" && "border-[#003377] bg-[#003377] text-white ring-4 ring-[#003377]/15",
              s.state === "todo" && "border-border text-muted-foreground", s.state === "waiting" && "border-[#c98f00] text-[#8a6500]", s.state === "optional" && "border-dashed border-border text-muted-foreground")}>
              {s.state === "done" ? <Check className="size-4" strokeWidth={3} /> : i + 1}
            </span>
            <div className="min-w-0 pt-0.5">
              <div className="flex flex-wrap items-baseline gap-x-3"><span className={cn(s.state === "current" ? "font-medium" : s.state === "done" || s.state === "waiting" ? "" : "text-muted-foreground")}>{s.label}</span><small className="text-muted-foreground">{s.sub}</small>
                {s.action && s.state !== "current" && <button className="text-xs text-info hover:underline" onClick={s.action.run}>{s.action.label}</button>}</div>
              {s.state === "current" && (
                <div className="mt-3 grid gap-3 rounded-xl bg-background p-5">
                  <div><p className="text-[17px] font-medium">{j.title}</p><p className="mt-1 text-sm text-muted-foreground">{j.task}</p></div>
                  {j.missing.length > 0 && <ul className="grid gap-1 text-sm">{j.missing.map((x) => <li key={x} className="flex items-center gap-2"><span aria-hidden className="size-1.5 rounded-full bg-[#c98f00]" />{x}</li>)}</ul>}
                  <div className="flex flex-wrap items-center gap-2">
                    {next && <Button size="lg" disabled={next.waiting} variant={next.waiting ? "outline" : "default"} onClick={next.run}>{next.label}{!next.waiting && " →"}</Button>}
                    {t.stage !== 5 && !t.sent && <Button variant="ghost" onClick={() => openExpertComposer(t)}>전문부서 요청서 작성</Button>}
                    {t.stage !== 5 && !t.sent && !t.draft && next?.label !== "답변 초안 작성" && <Button variant="ghost" onClick={() => composeFromCopilot(t, "answer")}>답변 초안 작성</Button>}
                  </div>
                  <details className="text-sm"><summary className="cursor-pointer text-muted-foreground">판단 이유</summary><p className="mt-2 text-muted-foreground">{j.reason}</p></details>
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

/* ───────── 문의·답변 ───────── */
function Message({ title, right, children, foot }: { title: ReactNode; right?: ReactNode; children?: ReactNode; foot?: ReactNode }) {
  return (
    <Card className="gap-3 p-5 ring-0">
      <div className="flex items-center justify-between gap-3"><strong className="font-semibold">{title}</strong>{right}</div>
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
  const sample = t.id === SAMPLE;
  const text = t.translate ? (sample ? "iS7 75kW가 운전 명령 직후 E.OC로 트립합니다. 재시작해도 같은 현상이 발생합니다." : t.bodyKo || t.title) : sourceInquiry(t);
  return (
    <Message title={sample ? "COMPANY_7979_0029" : t.company} right={<small className="text-muted-foreground">{t.receivedLabel || "10.06 · 17:43 UTC"}</small>}>
      <div className="flex items-center gap-3"><Tag className="rounded-md">원문 · {t.language}</Tag><button className="text-xs text-info hover:underline" onClick={() => toggleTranslate(t)}>{t.translate ? "원문 보기" : "한국어 번역"}</button></div>
      <p className="leading-relaxed">{text}</p>
      {sample && <><p className="text-muted-foreground">FW 4.00 · 부하 69% · 재시작 후 반복</p><Attachments t={t} files={["event_log.csv", "params.bak"]} /></>}
    </Message>
  );
}

const HIDDEN = ["feedback", "feedback_decision", "draft", "saved", "draft-retained", "draft-replaced", "assignment", "registered"];
function Conversation({ t }: { t: Ticket }) {
  const reqName = (e: any) => t.events.find((r) => r.id === e.requestId)?.department || "전문부서";
  return (
    <div className="grid gap-4">
      <section aria-label="고객 소통 이력" className="grid gap-3">
        <h2 className="text-xs font-semibold tracking-wide text-muted-foreground">고객 소통</h2>
        <Original t={t} />
        {t.events.filter((e) => !HIDDEN.includes(e.kind)).map((e, i) => {
          if (["customer", "customer-followup"].includes(e.kind))
            return (
              <Message key={i} title={e.kind === "customer-followup" ? "고객 후속 회신" : "고객 추가정보"} right={<small className="text-muted-foreground">{e.time}</small>}>
                <p>{e.text}</p>
                {e.informationChecks && <div className="flex flex-wrap gap-2">{requiredInformation(t).filter((x) => e.informationChecks[x.id]).map((x) => { const s = e.informationChecks[x.id].status; return <Tag key={x.id} tone={s === "confirmed" ? "green" : ""}>{x.label} · {({ confirmed: "확인 완료", unusable: "보완 필요", missing: "미수신" } as any)[s]}</Tag>; })}</div>}
                <Attachments t={t} files={e.files || []} />
              </Message>
            );
          if (e.kind === "expert")
            return (
              <Message key={i} title={`${reqName(e)} · 검토 회신`} right={<Tag tone="green">수신 완료</Tag>}
                foot={<div className="flex items-center justify-between"><small className="text-muted-foreground">{e.time}</small>{e.requestId && <Button size="sm" variant="outline" onClick={() => openModal("department-review", { ticketId: t.id, requestId: e.requestId })}>연결 요청 확인</Button>}</div>}>
                <p>{e.text}</p>
              </Message>
            );
          if (e.kind === "sent")
            return (
              <Message key={i} title={e.purpose === "request" ? "추가정보 요청 발송" : "고객 답변 발송"} right={<Tag tone="green">발송 완료</Tag>}>
                <p className="whitespace-pre-line">{e.text}</p>
                {e.masterText && e.masterText !== e.text && <details className="text-sm"><summary className="cursor-pointer text-muted-foreground">영어 원본 보기 · 발송 언어 {e.replyLanguage}</summary><p className="mt-2 whitespace-pre-line text-muted-foreground">{e.masterText}</p></details>}
                <small className="text-muted-foreground">{e.time} · {e.actor || t.owner}{e.replyLanguage && e.replyLanguage !== "English" ? ` · ${e.replyLanguage}` : ""}</small>
              </Message>
            );
          if (e.kind === "escalation")
            return (
              <Message key={i} title={`${e.department || "전문부서"} 검토 요청`} right={<small className="text-muted-foreground">{e.time}</small>}
                foot={<div className="flex items-center justify-between"><small className="text-muted-foreground">{e.channel || "미기록"} · {e.id}</small><Button size="sm" variant="outline" onClick={() => openModal("department-review", { ticketId: t.id, requestId: e.id })}>요청·회신 확인</Button></div>}>
                <p className="whitespace-pre-line">{e.request}</p>
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
      <Facts rows={[["완료 구분", ({ resolved: "문제 해결 확인", provided: "정보 제공 완료", unconfirmed: "해결 여부 미확인" } as any)[r.outcome] || "미기록"], ["최종 원인", r.cause || "미기록"], ["수행 조치", r.action || "미기록"], ["처리 결과", r.result || "미기록"], ["확인 근거", r.verification || "미기록"], ["완료 담당자", r.confirmedBy || t.owner || "미기록"]]} />
      <div className="flex gap-2">
        {latestCustomerReply(t) && <Button variant="outline" onClick={() => openModal("customer-reply", { id: t.id })}>고객 회신 보기</Button>}
        <Button variant="ghost" onClick={() => { setUi({ knowledgeTab: "완료 티켓", completedTicket: t.id, completedFilter: "전체 기록", kquery: "" }); go.to("/knowledge"); }}>축적된 처리 기록</Button>
      </div>
    </Card>
  );
}

/** 작성 영역: 영어로 쓴 초안을 검토·수정하고 승인한다. 고객 언어 변환은 승인(발송) 때 자동으로 이뤄진다. */
function Editor({ t }: { t: Ticket }) {
  const [folded, setFolded] = useState(false);
  if (t.activeComposer === "expert") return <ExpertEditor t={t} />;
  if (!t.draft && !t.composerOpen) return null;
  const live = answerContext(t), used = t.draftContext || answerContext(t, t.purpose);
  const isNew = contextIsNew(t), isRequest = (t.purpose || live.purpose) === "request";
  const lang = customerLanguage(t), needs = needsLocalization(t);
  return (
    <Card id="answer-editor" className="sticky bottom-3 z-10 max-h-[min(46dvh,440px)] gap-4 overflow-y-auto p-6 shadow-float">
      <div className="flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold">{isRequest ? "추가정보 요청 작성" : "고객 답변 작성"}
          {t.draft && <button type="button" aria-expanded={!folded} onClick={() => setFolded((v) => !v)} className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-0.5 text-xs font-normal text-muted-foreground hover:text-foreground"><ChevronDown className={cn("size-3.5 transition-transform", folded && "-rotate-90")} aria-hidden />{folded ? "펼치기" : "접기"}</button>}
        </h2>
        <div className="flex items-center gap-2 text-sm text-muted-foreground"><span>작성 English</span>{needs ? <><span aria-hidden>→</span><span>발송 시 <b className="font-medium text-foreground">{lang}</b>로 자동 변환</span></> : <span>· 고객 언어 English</span>}</div>
      </div>
      {!folded && (t.draft ? <Sources c={used} /> : live.purpose === "request" ? <Sources c={live} /> : null)}
      {!folded && isNew && <div className="rounded-xl bg-warning/15 px-4 py-2.5 text-sm text-warning-ink">새 자료가 도착했습니다. 작성 중인 내용과 함께 확인해 주세요.</div>}
      {folded && t.draft ? null : t.draft ? (
        <div className="grid gap-3">
          <div className="flex items-center gap-2 text-sm font-medium"><AiMark />{`미발송 초안 · v${t.draftVersion || 1}`}</div>
          <Textarea aria-label="영어 초안" className="min-h-32 leading-relaxed" value={t.draft} onChange={(e) => editDraft(t, e.target.value)} />
          <label className="flex items-center gap-2 text-sm"><Checkbox checked={!!t.reviewed} onCheckedChange={(v) => setReviewed(t, v === true)} />{live.purpose === "request" ? "요청 항목과 내용을 확인했습니다." : "내용과 근거를 검토했습니다."}</label>
        </div>
      ) : (
        <div className="grid gap-1 rounded-xl bg-background p-6 text-center">
          <strong>{live.purpose === "request" ? "요청할 정보를 확인하고 요청문을 작성하세요." : live.availableReferences.length ? "분석 결과와 근거가 준비되었습니다." : "문의 분석 결과를 확인해 주세요."}</strong>
          <p className="text-sm text-muted-foreground">{live.purpose === "request" ? "추가정보 요청 초안" : "고객 답변 초안"}은 영어로 작성됩니다. 작성하려면 작성 버튼을 눌러 주세요.</p>
          <small className="text-muted-foreground">아직 작성된 답변이 없습니다.</small>
        </div>
      )}
      <div className="flex items-center justify-between gap-3"><small className="text-muted-foreground">{t.draft ? (t.reviewed ? (needs ? `승인하면 ${lang}로 변환해 발송합니다` : "승인하면 발송합니다") : "먼저 영어 내용을 확인해 주세요") : "담당자 검토 후 발송"}</small>
        {t.draft && <Button disabled={!canSend(t)} onClick={() => canSend(t) && openModal("send", { id: t.id })}>승인 및 발송</Button>}
      </div>
    </Card>
  );
}
function Sources({ c }: { c: any }) {
  if (c.purpose === "request") return <div className="flex flex-wrap gap-2">{c.missingInfo.map((v: string) => <Tag key={v}>{v}</Tag>)}</div>;
  if (!c.references.length) return null;
  return <Disclosure title={`사용한 근거 ${c.references.length}건`}><div className="flex flex-wrap gap-2">{c.references.map((r: any) => <Tag key={r.id}>{r.label}</Tag>)}</div></Disclosure>;
}

function ExpertEditor({ t }: { t: Ticket }) {
  const files = [...new Set([...(t.files || []), ...(t.id === SAMPLE ? ["event_log.csv", "params.bak"] : [])])];
  const checked: string[] = t.expertDraftFiles || [];
  return (
    <Card id="answer-editor" className="sticky bottom-3 z-10 max-h-[min(46dvh,440px)] overflow-y-auto p-6 shadow-float">
      <form className="grid gap-4" onSubmit={(e) => {
        e.preventDefault();
        const d = new FormData(e.currentTarget);
        submitExpertRequest(t, { department: String(d.get("department")), channel: String(d.get("channel")), body: t.expertDraft || "", files: checked });
      }}>
        <div className="flex items-center justify-between"><h2 className="text-lg font-bold">전문부서 요청서 작성</h2><Button type="button" size="sm" variant="ghost" onClick={() => closeComposer(t)}>닫기</Button></div>
        <div className="grid grid-cols-2 gap-3">
          <label className="grid gap-1.5 text-sm"><span className="text-muted-foreground">대상 부서</span>
            <NativeSelect name="department" value={t.expertDraftDepartment || expertDepartments[0]} onChange={(e) => { t.expertDraftDepartment = e.target.value; commit(); }}>{expertDepartments.map((n) => <option key={n}>{n}</option>)}</NativeSelect></label>
          <label className="grid gap-1.5 text-sm"><span className="text-muted-foreground">전달 방식</span><NativeSelect name="channel" defaultValue="이메일"><option>이메일</option><option>기업 메신저</option></NativeSelect></label>
        </div>
        <Textarea aria-label="전문부서 요청서" required className="min-h-56 leading-relaxed" value={t.expertDraft || ""} onChange={(e) => { t.expertDraft = e.target.value; commit(); }} />
        <fieldset className="grid gap-2 rounded-xl bg-background p-4"><legend className="px-1 text-sm text-muted-foreground">전달한 자료</legend>
          {files.length ? files.map((f) => (
            <label key={f} className="flex items-center gap-2 text-sm"><Checkbox checked={checked.includes(f)} onCheckedChange={(v) => { t.expertDraftFiles = v === true ? [...checked, f] : checked.filter((x) => x !== f); commit(); }} />{f}</label>
          )) : <small className="text-muted-foreground">등록된 첨부자료 없음</small>}
        </fieldset>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" required className="size-4 accent-[var(--primary)]" />요청 내용과 전달 자료를 확인했습니다.</label>
        <div className="flex items-center justify-between"><small className="text-muted-foreground">외부 전달 후 요청을 기록합니다.</small><Button type="submit">검토 요청 기록</Button></div>
      </form>
    </Card>
  );
}

/* ───────── 처리 이력 · 고객 정보 ───────── */
function History({ t }: { t: Ticket }) {
  const rows = [
    { time: "10.14 · 09:14", title: "문의 접수", sub: `웹폼 · ${t.company}` },
    { time: "10.14 · 09:15", title: "AI 분석 완료", sub: `${t.type} · ${t.product} · 근거 검색` },
    ...t.events.filter((e) => !["feedback", "feedback_decision"].includes(e.kind)).map((e) => ({
      time: e.time || "",
      title: e.kind === "sent" ? (e.purpose === "request" ? "추가정보 요청 발송" : "답변 승인 및 발송") : e.kind === "customer" ? "고객 추가정보 등록" : e.kind === "expert" ? "전문부서 회신 등록" : e.text || "",
      sub: `${e.actor || t.owner || "접수 담당자"}${e.kind === "sent" ? " · 발송 결과 기록" : ""}`,
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
  return (
    <Card className="gap-5 p-6">
      <h2 className="text-lg font-bold">고객·제품 정보</h2>
      <Facts rows={[["회사", t.company], ["국가", t.country], ["답변 언어", customerLanguage(t)], ["제품", t.product], ["문의 유형", t.type], ["오류 코드", t.type === "불량" ? "E.OC" : "—"], ["담당자", t.owner || "미배정"]]} />
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
  if (t.draft && t.stage !== 5 && !t.sent) {
    const lang = customerLanguage(t), isRequest = t.purpose === "request", pending = waitingReviews(t).length || (t.legacyReviewPending ? 1 : 0);
    const what = isRequest ? "추가정보 요청" : "고객 답변";
    const [task, why] = !t.reviewed
      ? ["영어 초안을 검토하고, 필요하면 고쳐 주세요.", "초안은 영어로 작성됩니다. 승인하면 고객 언어로 자동 변환해 발송합니다."]
      : [needsLocalization(t) ? `검토가 끝났습니다. 승인하면 ${lang}로 자동 변환해 발송합니다.` : "검토가 끝났습니다. 승인하고 발송하세요.", "발송하면 영어 원본과 발송본이 함께 이력에 남습니다."];
    return { title: `${what} 작성 중`, task: pending ? `${task} (전문부서 회신 ${pending}건 대기 중)` : task, reason: why, missing: [] as string[] };
  }
  const c = answerContext(t), missing = c.missingInfo.length, expertPending = waitingReviews(t).length || t.legacyReviewPending;
  let title: string, task: string, reason: string;
  const reply = latestCustomerReply(t);
  if (t.stage === 5) { title = "처리 완료"; task = "최종 처리 결과가 기록되었습니다."; reason = "재문의는 기존 티켓에서 이어서 처리합니다."; }
  else if (t.sent && t.customerOutcome === "resolved") { title = "고객 해결 확인 수신"; task = "회신과 최종 처리 결과를 확인하고 완료하세요."; reason = "해결 확인 근거는 고객 회신 이력에 남아 있습니다."; }
  else if (t.sent && t.customerOutcome === "provided") { title = "고객 정보 확인 완료"; task = "응대 결과를 기록하고 완료하세요."; reason = "정보 확인 회신과 기술적 해결 확인은 구분합니다."; }
  else if (t.sent) { title = "고객 답변 발송 완료"; task = "고객 회신이나 처리 결과를 확인하세요."; reason = "회신이 없으면 해결 여부는 미확인입니다."; }
  else if (t.customerOutcome === "needs-support") { title = "후속 문의 · 재검토 필요"; task = "이전 조치와 고객의 새 증상을 함께 확인하세요."; reason = "이전 완료 결과는 현재 해결 근거로 확정하지 않습니다."; }
  else if (t.customerRequestStatus === "waiting") { title = "고객 회신 대기"; task = "고객이 요청 자료를 제출하기를 기다리고 있습니다."; reason = "회신이 들어오면 같은 티켓에서 내용을 확인합니다."; }
  else if (t.customerRequestStatus === "received" && reply && requiredInformation(t).length && reply.id !== t.reviewedReplyKey) { title = "고객 자료 수신 · 확인 필요"; task = "수신된 내용과 첨부자료를 확인하세요."; reason = "회신 수신만으로 필요한 자료가 충족된 것은 아닙니다."; }
  else if (missing) { title = t.customerRequestStatus === "received" ? "회신 수신 · 추가정보 미충족" : "추가정보 필요 · 원인 미확정"; task = t.customerRequestStatus === "received" ? "아직 충족되지 않은 자료만 추가로 요청하세요." : "고객에게 아래 자료를 요청하세요."; reason = "제품 상태와 모터 정보를 확인해야 원인 후보를 구분할 수 있습니다."; }
  else if (expertPending) { title = "전문부서 회신 대기"; task = "검토 결과를 받으면 해당 요청에 등록하세요."; reason = "회신을 확인한 뒤 고객 답변에 활용합니다."; }
  else if (c.expertResponse) { title = "전문부서 회신 수신"; task = "회신 내용을 검토하고 고객 답변을 작성하세요."; reason = "회신은 아래 참고 근거에서 확인할 수 있습니다."; }
  else if (c.availableReferences.length) { title = "참고 근거 확보 · 원인 미확정"; task = "현재 문의와 사례의 차이를 검토하세요."; reason = "과거 사례의 원인이 현재 고장의 원인과 같다고 확정할 수 없습니다."; }
  else { title = "기술 근거 확인 필요"; task = "현재 자료로 답변 가능한지 확인하세요."; reason = "전문 판단이 필요하면 검토 요청서를 작성하세요."; }
  return { title, task, reason, missing: (missing > 0 && t.stage !== 5 ? c.missingInfo : []) as string[] };
}

/** 처리 진행 옆에 항상 보이는 AI 분석. 위는 AI가 파악한 내용, 아래는 그 근거(항목별로 접힘). */
function AiAnalysis({ t }: { t: Ticket }) {
  const go = useGo();
  const c = answerContext(t), infoItems = informationAssessment(t);
  const facts: [string, ReactNode][] = [
    ["유형·제품", `${c.analysis.type} · ${c.analysis.product}`],
    ...(c.analysis.errorCode ? ([["오류 코드", c.analysis.errorCode]] as [string, ReactNode][]) : []),
    ...(c.analysis.conditions.firmware ? ([["확인된 조건", `FW ${c.analysis.conditions.firmware} · 부하 ${c.analysis.conditions.load} · 이벤트 로그 확보`]] as [string, ReactNode][]) : []),
    ["고객 자료", infoItems.length ? infoItems.map((x) => `${x.label} ${x.status === "confirmed" ? "✓ 확인" : "· 필요"}`).join(", ") : "추가 자료 불필요"],
    ["추정 원인", c.technical.possibleCause ? `${c.technical.possibleCause} (확정 아님)` : "근거 부족 · 확정 불가"],
    ["권장 확인", c.technical.recommendation || "—"],
  ];
  return (
    <aside aria-label="AI 분석" className="grid content-start gap-4 self-start rounded-2xl bg-card p-5 shadow-card min-[1360px]:sticky min-[1360px]:top-6 min-[1360px]:max-h-[calc(100dvh-3rem)] min-[1360px]:overflow-y-auto">
      <div className="flex items-center gap-2"><AiMark /><h2 className="text-lg font-medium">AI 분석</h2><small className="ml-auto text-muted-foreground">원인 확정 전</small></div>
      <section aria-label="문의 분석" className="grid gap-3 rounded-xl bg-background p-4">
        <p className="font-medium leading-snug">{c.analysis.summary}</p>
        <Facts className="grid-cols-[72px_minmax(0,1fr)]" rows={facts} />
      </section>
      <section aria-label="근거" className="grid gap-2.5">
        <h3 className="px-1 text-sm font-semibold text-muted-foreground">근거</h3>
        {c.expertResponse && <Disclosure defaultOpen title="전문부서 회신" count={<Tag tone="green">수신</Tag>}><p>{c.expertResponse.text}</p></Disclosure>}
        {c.technical.documents.length > 0 && (
          <Disclosure title="관련 기술문서" count={`${c.technical.documents.length}건`}>
            {c.technical.documents.map((d: any) => <div key={d.id} className="grid gap-1"><div className="font-medium">{d.label}</div><p className="text-muted-foreground">{d.text}</p><button className="w-fit text-info hover:underline" onClick={() => openModal("document")}>문서 확인</button></div>)}
          </Disclosure>
        )}
        {c.technical.similarCases.length > 0 && (
          <Disclosure title="유사 사례 비교" count={`${c.technical.similarCases.length}건`}>
            {c.technical.similarCases.map((r: any) => (
              <section key={r.id} className="grid gap-2 rounded-xl bg-background p-3">
                <div className="flex items-center justify-between"><strong>{r.id}</strong><small className="text-muted-foreground">{r.matches ? "발생 조건 유사" : "발생 조건 차이"}</small></div>
                <Facts className="grid-cols-[48px_1fr]" rows={[["원인", r.cause], ["조치", r.action], ["결과", <span key="r" className="text-success">{r.result}</span>]]} />
                <button className="w-fit text-info hover:underline" onClick={() => { setUi({ knowledgeTab: "해결 사례", kquery: "", knowledge: cases.findIndex((x) => x.id === r.id) }); go.to("/knowledge"); }}>사례 상세</button>
              </section>
            ))}
          </Disclosure>
        )}
        {!evidenceCount(t) && <p className="rounded-xl bg-background px-4 py-6 text-center text-sm text-muted-foreground">아직 연결된 근거가 없습니다.</p>}
      </section>
    </aside>
  );
}
