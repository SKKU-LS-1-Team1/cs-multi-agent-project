import { useCopilot, ReadingSummary, Statement, InsightStatus, CaseComparisons, RequestChecklist } from "../components/admin/CopilotReading";
import { investigationTask, copilotPresentation, referralSuggestions } from "@admin/lib/investigation";
// 문의 상세: 대기열 · 문의 요약 · 처리 상황 · 문의·답변/처리 이력/고객·제품 정보 · AI Copilot.
import { useEffect, useState, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { ArrowRight, BookOpen, Building2, ChevronDown, ChevronRight, CircleCheck, CircleDashed, CircleDot, Circle, Clock, Compass, FileText, Headset, Image as ImageIcon, Link2, Paperclip, Send, User, type LucideIcon } from "lucide-react";
import { FAMILY_KO } from "@admin/lib/customers";
import { Button, buttonVariants } from "@admin/components/ui/button";
import { Card } from "@admin/components/ui/card";
import { Checkbox } from "@admin/components/ui/checkbox";
import { Input } from "@admin/components/ui/input";
import { Textarea } from "@admin/components/ui/textarea";
import { AiMark, Facts, Mono, NativeSelect, PersonAvatar, PriorityTag, SlaTag, StatusTag, Tag, UnderlineTabs, useGo } from "@admin/components/admin/common";
import {
  answerContext, assignmentSummary, branchChoice, escalationRecommended, cases, contextIsNew, customerLanguage, expertDepartments, expertPhase, feedbackLabel, inquirySummary, isEdited,
  canAssign, isNewAssignment, latestCustomerReply, pendingCustomerInfo, referralRows, requiredInformation, runChecks, sourceInquiry, unreadReplies, waitingReviews,
} from "@admin/lib/logic";
import {
  requestInvestigationInfo, judgment, nextAction, prepareCustomerReply, canSend, closeComposer, composeFromCopilot, editDraft, markSeen, openCompletion, openExpertComposer, openExpertReview, QUICK_INSTRUCTIONS, regenerateDraft, setReviewed, submitExpertRequest, toggleTranslate,
} from "@admin/lib/actions";
import { DEPT_LABEL, rewriteViaApi, loadTicketDetail, watchTicketDetail, isManualReplyTicket, hasCurrentReplyPreview, escalationDraftViaApi, manualDraftViaApi } from "@admin/lib/api-sync";
import { commit, findTicket, openModal, setUi, ui, useStore } from "@admin/lib/store";
import { flowSteps, type Step, type StepState } from "@admin/lib/flow-steps";
import { cn } from "@admin/lib/utils";
import type { Ticket } from "@admin/lib/types";
import { api, type InquiryAttachment } from "../../api/client";
import { FollowupEvidence } from "../components/admin/FollowupEvidence";

type Choice = "answer" | "expert" | "request";
const SAMPLE = "CSV1-000050";
/** 샘플 문의가 접수된 시각. 대화 머리와 처리 이력이 같은 값을 쓴다. */
const INQUIRY_AT = "10.06 · 17:43";
const DETAIL_TABS = [["문의·답변", "문의·답변"], ["처리 이력", "처리 이력"], ["고객·제품 정보", "고객·제품 정보"]] as const;

export default function TicketDetail() {
  useStore();
  const { ticketId } = useParams();
  const t = findTicket(ticketId);
  const [loadError, setLoadError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!ticketId) return;
    let cancelled = false;
    setLoadError("");
    const stop = watchTicketDetail(ticketId);
    void loadTicketDetail(ticketId).catch(() => { if (!cancelled) setLoadError("문의 상세를 불러오지 못했습니다."); });
    return () => { cancelled = true; stop(); };
  }, [ticketId, retry]);
  useEffect(() => { if (t && (unreadReplies(t) > 0 || isNewAssignment(t))) markSeen(t); }, [t?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!t) return <div className="p-10" role={loadError ? "alert" : "status"}>{loadError || "문의 상세를 불러오는 중입니다."}{loadError && <Button variant="outline" onClick={() => setRetry((v) => v + 1)}>다시 시도</Button>}</div>;
  return (
    <div data-ticket-id={t.id} className="grid h-[calc(100dvh-1.5rem)] min-h-0 grid-cols-1 items-start overflow-y-auto overscroll-contain min-[1360px]:grid-cols-[minmax(0,1fr)_400px] min-[1360px]:items-stretch min-[1360px]:overflow-hidden">
      <section aria-label="문의 상세" tabIndex={0} key={t.id} className="grid min-h-0 min-w-0 content-start gap-8 px-12 pb-16 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/30 min-[1360px]:h-full min-[1360px]:overflow-y-auto min-[1360px]:overscroll-contain">
        {/* 제목·진행 단계·탭은 스크롤해도 맨 위에 고정된다 */}
        <div className="sticky top-0 z-20 -mx-12 grid gap-6 bg-background px-12 pb-1 pt-10">
          <Header t={t} />
          <FollowupLink key={t.id} t={t} />
          <Progress t={t} />
          <UnderlineTabs tabs={DETAIL_TABS} value={ui.tab as (typeof DETAIL_TABS)[number][0]} onChange={(v) => setUi({ tab: v })} />
        </div>
        {ui.tab === "처리 이력" ? <History t={t} /> : ui.tab === "고객·제품 정보" ? <Customer t={t} /> : <Conversation t={t} />}
      </section>
      <Copilot t={t} />
    </div>
  );
}

function FollowupLink({ t }: { t: Ticket }) {
  const go = useGo();
  const link = t.followupLink;
  if ((!link || link.dismissed) && !t.followupContextStale) return null;
  return <section aria-label="후속 문의 연결" className="min-w-0 rounded-2xl border border-info/50 bg-info/5 p-5 text-foreground shadow-card">
    {link && !link.dismissed && <div className="flex flex-wrap items-center gap-5">
      <div className="flex min-w-0 flex-1 items-start gap-3.5">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-info/10 text-info"><Link2 className="size-5" aria-hidden="true" /></span>
        <div className="min-w-0 [overflow-wrap:anywhere]">
          <h2 className="text-base font-semibold">이전 문의에서 이어진 후속 문의</h2>
          <p className="mt-2 text-base font-semibold">{link.previous_subject || "이전 문의"}</p>
          <p className="mt-1 font-mono text-xs text-muted-foreground">{link.previous_ticket_id}</p>
        </div>
      </div>
      <Button variant="outline" size="sm" className="shrink-0 bg-card text-foreground" onClick={() => go.ticket(link.previous_ticket_id)}>이전 문의 보기<ArrowRight className="size-4" aria-hidden="true" /></Button>
    </div>}
    {t.followupContextStale && <div className="grid gap-2"><p role="status" className="text-sm text-amber-700">이전 문의 연결이 해제되었습니다. 답변 초안을 재작성한 뒤 발송해 주세요.</p><Button variant="outline" size="sm" className="w-fit bg-card text-foreground" disabled={t.regenerating} onClick={() => void rewriteViaApi(t, "이전 문의 연결을 제외하고 현재 문의와 확인된 근거로 다시 작성해 주세요.", "answer")}>답변 초안 재작성</Button></div>}
  </section>;
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

// 고객이 문의서에 올린 파일 (GET /api/inquiries/{id}/attachments). 사진은 썸네일, 누르면 새 탭에서 원본
const INLINE = /^image\/(png|jpeg|gif|webp|bmp)$/;
function UploadedFiles({ ticketId }: { ticketId: string }) {
  const [rows, setRows] = useState<InquiryAttachment[]>([]);
  useEffect(() => {
    let live = true;
    api.inquiryAttachments(ticketId).then((r) => { if (live) setRows(r); }, () => {});
    return () => { live = false; };
  }, [ticketId]);
  if (!rows.length) return null;
  return (
    <div className="grid gap-2">
      <small className="text-muted-foreground">고객 첨부 {rows.length}건</small>
      <div className="flex flex-wrap gap-3">
        {rows.map((a) => {
          const url = api.attachmentUrl(ticketId, a.attachment_id);
          return INLINE.test(a.content_type) ? (
            <a key={a.attachment_id} href={url} target="_blank" rel="noreferrer" title={a.name} className="block w-28 overflow-hidden rounded-xl ring-1 ring-black/10 hover:ring-primary">
              <img src={url} alt={a.name} loading="lazy" className="aspect-square w-full object-cover" />
              <span className="block truncate px-2 py-1 text-xs text-muted-foreground">{a.name}</span>
            </a>
          ) : (
            <a key={a.attachment_id} href={url} download={a.name} className={buttonVariants({ size: "sm", variant: "outline" })}><Paperclip />{a.name}</a>
          );
        })}
      </div>
    </div>
  );
}

/** 제품군 코드: 서버 분석 값이 있으면 그것, 없으면(로컬 샘플) 제품명으로 짐작한다. */
const familyCode = (t: Ticket): string => t.apiExtraction?.product_family
  || (/MCCB|ACB|Breaker/i.test(t.product) ? "LV_BREAKER" : /Transformer/i.test(t.product) ? "TRANSFORMER" : /XGI|PLC/i.test(t.product) ? "PLC" : /HMI/i.test(t.product) ? "HMI" : /ESS/i.test(t.product) ? "ESS" : /Contactor/i.test(t.product) ? "CONTROL" : /iS7|S100|H100|inverter/i.test(t.product) ? "DRIVE" : "");
const imageName = /\.(png|jpe?g|gif|webp|bmp)$/i;

function Original({ t }: { t: Ticket }) {
  const sample = t.source !== "api" && t.id === SAMPLE;
  const text = t.translate ? (sample ? "iS7 75kW가 운전 명령 직후 E.OC로 트립합니다. 재시작해도 같은 현상이 발생합니다." : t.bodyKo || "한국어 번역이 아직 준비되지 않았습니다. 원문을 확인해 주세요.") : sourceInquiry(t);
  const family = familyCode(t), files = [...new Set([...(t.files || []), ...(sample ? ["event_log.csv", "params.bak"] : [])])];
  return (
    <Message role="customer" label="고객 문의" title={t.company} right={<small className="text-muted-foreground">{t.receivedLabel || (t.source === "api" ? "접수 시각 미기록" : `${INQUIRY_AT} UTC`)}</small>}>
      <div className="mt-3 grid gap-8">
        <dl className="grid grid-cols-3 gap-4 rounded-2xl bg-muted/60 px-6 py-5 text-sm max-[900px]:grid-cols-1">
          <div className="grid gap-1"><dt className="text-xs text-muted-foreground">제품군</dt><dd className="font-semibold">{(family && FAMILY_KO[family]) || "제품군 미확인"}</dd></div>
          <div className="grid gap-1"><dt className="text-xs text-muted-foreground">제품</dt><dd className="font-semibold">{t.product}</dd></div>
          <div className="grid gap-1"><dt className="text-xs text-muted-foreground">문의 유형</dt><dd className="font-semibold">{t.type || "미분류"}</dd></div>
        </dl>
        <section aria-label="문의 내용" className="grid gap-3.5">
          <div className="flex items-center gap-3"><h3 className="text-sm font-medium">문의 내용</h3><Tag className="rounded-md">원문 · {t.language}</Tag><button className="text-xs text-info hover:underline" onClick={() => toggleTranslate(t)}>{t.translate ? "원문 보기" : "한국어 번역"}</button></div>
          <div className="rounded-2xl bg-muted/60 px-5 py-4 text-base leading-[1.8]">{text}</div>
          {sample && <p className="text-sm text-muted-foreground">FW 4.00 · 부하 69% · 재시작 후 반복</p>}
        </section>
        {t.source === "api" ? <UploadedFiles ticketId={t.id} /> : (
          <section aria-label="첨부 자료" className="grid gap-3.5">
            <h3 className="text-sm font-medium">첨부 자료 {files.length ? `${files.length}건` : ""}</h3>
            {files.length ? (
              <div className="flex flex-wrap gap-2">
                {files.map((f) => <Button key={f} size="sm" variant="outline" onClick={() => openModal("file", { file: f, id: t.id })}>{imageName.test(f) ? <ImageIcon /> : <Paperclip />}{f}</Button>)}
              </div>
            ) : <p className="text-sm text-muted-foreground">고객이 첨부한 자료가 없습니다.</p>}
          </section>
        )}
      </div>
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
  if (t.activeComposer === "expert") return <ExpertEditor t={t} />;
  if (!t.draft && !t.composerOpen) return null;
  const manual = isManualReplyTicket(t);
  const isRequestDraft = t.purpose === "request", expertWaiting = waitingReviews(t).length > 0 || !!t.legacyReviewPending;
  // 전문부서 회신을 기다리는 동안은 고객 답변 작성칸을 열지 않는다(회신을 보고 써야 하므로). 고객에게 보내는 질의서는 해당 없음.
  if (!isRequestDraft && expertPhase(t) === "review" && !t.sent && t.stage !== 5 && !t.specialistFollowup) {
    return (
      <Card className="grid justify-items-center gap-2 p-8 text-center">
        <strong className="text-base">전문부서 회신이 도착했습니다</strong>
        <p className="text-sm text-muted-foreground">회신이 요청에 맞는지 확인한 뒤 답변에 반영하세요. 부족하면 추가 질의나 고객 자료 요청으로 돌아갈 수 있습니다.</p>
        <Button className="mt-1" onClick={() => openExpertReview(t)}>회신 검토</Button>
      </Card>
    );
  }
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
    <Card id="answer-editor" className="min-w-0 scroll-mt-6 gap-0 p-0 shadow-float ring-1 ring-black/5">
      <div className="flex items-center justify-between gap-4 px-8 pb-3 pt-7">
        <h2 className="flex items-center gap-3 text-base font-semibold"><span className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full bg-[#d6336c]/10 px-3 text-[13px] font-medium text-[#c2255c]"><Headset className="size-3.5" aria-hidden />{isRequest ? "관리자 질의" : "관리자 답변"}</span>{isRequest ? "고객 질의서 작성" : "고객 답변 작성"}
        </h2>
        <div className="flex items-center gap-2 text-sm text-muted-foreground"><span>작성 English</span><span>→ 고객 언어 <b className="font-medium text-foreground">{lang}</b></span></div>
      </div>
      {(
        <div className="grid min-w-0 grid-cols-1 gap-6 px-8 pb-7 pt-2 *:min-w-0">
          {isRequest && t.copilot && <div><Button variant="outline" size="sm" disabled={busy} onClick={() => openModal("request-plan", { id: t.id })}>요청 항목 선택</Button></div>}
          {t.draft ? <Sources c={used} t={t} /> : live.purpose === "request" ? <Sources c={live} t={t} /> : null}
          {isNew && <div className="rounded-2xl bg-warning/15 px-5 py-3 text-sm text-warning-ink">{t.source === "api" && (t.draftSpecialistRevision ?? 0) !== (t.specialistRevision ?? 0) ? "새 전문부서 회신을 반영해 AI에게 답변 재작성을 요청한 뒤 검토하세요. 기존 초안은 보존됩니다." : "새 자료가 도착했습니다. 작성 중인 내용과 함께 확인해 주세요."}</div>}
          {t.draft || manual ? (
            <>
              <div className="grid gap-3">
                <div className="flex items-center gap-2.5 text-sm font-medium">{!manual && <AiMark />}{manual ? "담당자 작성 · 영어 답변" : `미발송 초안 · v${t.draftVersion || 1}`}{!manual && isEdited(t) && <Tag tone="amber">AI 초안에서 수정됨</Tag>}{busy && <small className="font-normal text-info">AI가 다시 만드는 중…</small>}
                  {manual && <Button type="button" size="sm" variant="outline" className="ml-auto" disabled={busy || !!t.aiDrafting || expertWaiting} title={expertWaiting ? "전문부서 회신을 모두 등록한 뒤 만들 수 있습니다" : "처음 문의와 전문부서 회신을 바탕으로 영어 초안을 만듭니다"}
                    onClick={() => { if (t.draft?.trim() && !window.confirm("작성 중인 내용을 AI 초안으로 바꿉니다. 계속할까요?")) return; void manualDraftViaApi(t); }}><AiMark className="size-3.5" />{t.aiDrafting ? "초안 작성 중…" : "AI 초안 작성"}</Button>}</div>
                <Textarea aria-label="영어 초안" disabled={busy} className="field-sizing-fixed min-w-0 min-h-36 max-h-56 rounded-2xl border-0 bg-muted/60 px-5 py-4 text-base leading-[1.8]" value={t.draft} onChange={(e) => editDraft(t, e.target.value)} />
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
            <Button variant="outline" size="lg" disabled={busy || t.translatingReply || (!isRequestDraft && t.followupContextStale)} onClick={() => void prepareCustomerReply(t)}>{t.translatingReply ? "변환 중…" : "고객 언어로 변환"}</Button>
          )}
        </div>}
        {!t.draft && !manual && <div className="ml-auto flex shrink-0 items-center gap-2">
          <Button size="lg" className="px-6" disabled={busy || t.expertDraftLoading} onClick={() => composeFromCopilot(t, isRequest ? "request" : "answer")}>{busy ? "작성 중…" : isRequest ? "질의서 작성" : "답변 초안 작성"}</Button>
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
        <AiMark />
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
function Sources({ c, t }: { c: any; t: Ticket }) {
  if (c.purpose === "request") {
    const workflow = t.copilot?.workflow;
    const fields = workflow?.mode === "customer_request"
      ? workflow.request_fields.map((field: string) => t.fieldLabels?.[field] || field) : c.missingInfo;
    return <div className="flex flex-wrap gap-2">{fields.map((v: string) => <Tag key={v}>{v}</Tag>)}</div>;
  }
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
        <div className="flex items-center justify-between"><h2 className="flex items-center gap-2.5 text-lg font-bold">{t.source === "api" && <AiMark />}전문부서 요청서 작성 · 한국어</h2><Button type="button" size="sm" variant="ghost" onClick={() => closeComposer(t)}>닫기</Button></div>
        <div className="grid grid-cols-2 gap-3">
          <label className="grid gap-1.5 text-sm"><span className="text-muted-foreground">대상 부서</span>
            <NativeSelect disabled={t.specialistSaving || t.expertDraftLoading} name="department" value={t.expertDraftDepartment || expertDepartments[0]} onChange={(e) => { t.expertDraftDepartment = e.target.value; commit(); if (t.source === "api") void escalationDraftViaApi(t, e.target.value); }}>{expertDepartments.map((n) => <option key={n}>{n}</option>)}</NativeSelect></label>
          <label className="grid gap-1.5 text-sm"><span className="text-muted-foreground">전달 방식</span><NativeSelect disabled={t.specialistSaving} name="channel" defaultValue="이메일"><option>이메일</option><option>기업 메신저</option></NativeSelect></label>
        </div>
        {t.expertDraftLoading && <small className="flex items-center gap-2 text-muted-foreground"><AiMark />AI가 요청서 초안을 쓰는 중이에요…</small>}
        <Textarea disabled={t.specialistSaving} aria-label="전문부서 요청서" required className="min-h-32 max-h-44 leading-relaxed" value={t.expertDraft || ""} onChange={(e) => { t.expertDraft = e.target.value; commit(); }} />
        <div role="group" aria-labelledby="expert-files-label" className="grid gap-1.5 text-sm"><span id="expert-files-label" className="text-muted-foreground">전달한 자료</span>
          <div className="grid gap-2 rounded-xl border bg-background p-4">
          {files.length ? files.map((f) => (
            <label key={f} className="flex items-center gap-2 text-sm"><Checkbox checked={checked.includes(f)} onCheckedChange={(v) => { t.expertDraftFiles = v === true ? [...checked, f] : checked.filter((x) => x !== f); commit(); }} />{f}</label>
          )) : <small className="text-muted-foreground">등록된 첨부자료 없음</small>}
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" required className="size-4 accent-[var(--primary)]" />요청 내용과 전달 자료를 확인했습니다.</label>
        <div className="flex items-center justify-between"><small className="text-muted-foreground">외부 전달 후 요청을 기록합니다.</small><Button type="submit" disabled={t.specialistSaving || t.expertDraftLoading}>{t.specialistSaving ? "저장 중…" : "검토 요청"}</Button></div>
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

const SECTION_TONE = { info: "bg-info/10 text-info", navy: "bg-[#003377]/10 text-[#003377]", success: "bg-success/10 text-success" } as const;
/** Copilot 구역: 접지 않고 항상 보인다. 아이콘 색과 제목만 다르다. */
function PanelBlock({ icon: Icon, tone, title, count, foldable, children }: { icon: LucideIcon; tone: keyof typeof SECTION_TONE; title: ReactNode; count?: ReactNode; foldable?: boolean; children: ReactNode }) {
  const head = (
    <>
      <span className={cn("grid size-8 place-items-center rounded-full", SECTION_TONE[tone])}><Icon className="size-[18px]" aria-hidden /></span>{title}
      {count && <span className="ml-auto text-sm font-normal text-muted-foreground">{count}</span>}
      {foldable && <ChevronDown className={cn("size-4 text-muted-foreground transition-transform group-open/fold:rotate-180", !count && "ml-auto")} aria-hidden />}
    </>
  );
  return (
    <section aria-label={typeof title === "string" ? title : undefined} className="py-6">
      {foldable ? (
        <details open className="group/fold">
          <summary className="mb-4 flex cursor-pointer list-none items-center gap-2.5 text-base font-semibold [&::-webkit-details-marker]:hidden"><h3 className="contents">{head}</h3></summary>
          {children}
        </details>
      ) : (
        <>
          <h3 className="mb-4 flex items-center gap-2.5 text-base font-semibold">{head}</h3>
          {children}
        </>
      )}
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
  const insight = useCopilot(t);
  const c = answerContext(t), sum = inquirySummary(t), j = judgment(t), next = nextAction(t);
  const requests = referralRows().filter((r) => r.ticket.id === t.id);
  const choice = branchChoice(t);
  const presentation = copilotPresentation(t, choice);
  const requestRows = presentation.requestRows;
  const suggested = referralSuggestions(t);
  const reason = presentation.showNextReason ? insight.data?.reading?.next_reason : null;
  // Customer facts belong to the summary/request checklist; case comparisons have their own section.
  // Only actual documents and specialist replies belong in the technical sources list.
  const evidence = presentation.showTechnicalContext ? [
    ...c.expertReferences.map((r: any) => ({ key: r.id, label: r.label, hint: "전문부서 회신", summary: String(r.text || "") })),
    ...c.technical.documents.map((d: any) => ({ key: d.id, label: d.label, hint: "기술문서", summary: String(d.text || "") })),
  ] : [];
  const BRANCH: Record<Choice, [string, () => void]> = {
    answer: [isManualReplyTicket(t) && !t.draft ? "담당자 답변 작성·검토" : "답변 초안 작성", () => composeFromCopilot(t, "answer")],
    expert: ["전문부서 요청서 작성", () => openExpertComposer(t)],
    request: ["고객 질의서 작성", () => composeFromCopilot(t, "request")],
  };
  const branches = choice ? [choice, ...(["answer", "expert", "request"] as Choice[]).filter((x) => x !== choice)] : [];
  const showNext = !!next && next.label !== "영어 초안 검토하기"; // 작성 카드가 바로 옆에 있어 같은 곳으로 보내는 버튼은 뺀다
  return (
    <aside aria-label="AI Copilot" tabIndex={0} className="m-4 ml-0 min-h-0 min-w-0 rounded-3xl bg-gradient-to-b from-[#026bb4]/[0.10] via-card via-[140px] to-card px-7 pb-3 pt-7 shadow-card max-[1359px]:mx-12 max-[1359px]:mb-12 max-[1359px]:mt-0 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/30 min-[1360px]:h-[calc(100%-2rem)] min-[1360px]:overflow-y-auto min-[1360px]:overscroll-contain">
      <div className="mb-2 flex items-center gap-2.5"><AiMark /><h2 className="text-xl font-bold">AI Copilot</h2></div>
      <div className="divide-y">
        <PanelBlock icon={Compass} tone="navy" title="현재 할 일">
          <div className="rounded-2xl bg-[#003377]/[0.06] p-5">
            <p className="text-[17px] font-semibold leading-snug tracking-[-0.01em]">{j.title}</p>
            <p className="mt-1.5 text-[15px] leading-[1.65] text-muted-foreground">{j.task}</p>
            {reason && <div className="mt-3 border-t border-border pt-3"><p className="mb-1 text-sm font-medium">{presentation.reasonTitle}</p><Statement value={reason} sources={insight.data!.sources} /></div>}
            {j.note && <p className="mt-2 flex items-center gap-1.5 text-sm text-warning-ink"><Clock className="size-4" aria-hidden />{j.note}</p>}
            {requestRows.length === 0 && j.missing.length > 0 && <ul className="mt-3 grid gap-1.5 text-[15px]">{j.missing.map((x) => <li key={x} className="flex items-center gap-2"><span aria-hidden className="size-1.5 rounded-full bg-warning" />{x}</li>)}</ul>}
            {t.specialistFollowup?.confirmation && <p className="mt-2 text-xs font-bold text-success">{t.specialistFollowup.confirmation.reviewer} · 전문부서 검토 결과 확인 완료</p>}
            {(choice || showNext) && (
              <div className="mt-5 grid gap-2.5">
                {choice ? <>
                  {t.draft && t.composerOpen && next ? <Button className="w-full" disabled={next.waiting || t.regenerating} onClick={next.run}>{next.label}</Button> : null}
                  {branches.filter((k) => !(t.draft && t.composerOpen && next && k === choice)).map((k, i) => <Button key={k} className="w-full" title={k === "expert" && pendingCustomerInfo(t) > 0 ? "고객 정보 확인이 끝나야 전문부서에 요청할 수 있습니다" : undefined} disabled={t.regenerating || t.expertDraftLoading || (k === "expert" && pendingCustomerInfo(t) > 0)} variant={i === 0 && !(t.draft && t.composerOpen && next) ? "default" : "outline"} onClick={BRANCH[k][1]}>{BRANCH[k][0]}</Button>)}
                </>
                  : next && <Button className="w-full" disabled={next.waiting} variant={next.waiting ? "outline" : "default"} onClick={next.run}>{next.label}</Button>}
              </div>
            )}
          </div>
        </PanelBlock>
        {escalationRecommended(t) && t.activeComposer !== "expert" && (
          <PanelBlock icon={Building2} tone="navy" title={pendingCustomerInfo(t) > 0 || t.customerRequestStatus === "waiting" ? "전문부서 이관 예상" : "전문부서 이관 권장"} count={t.escalationAdvice.source === "ai" ? "AI 판단" : "규칙"}>
            <div className="grid gap-2 text-sm leading-relaxed">
              <p className="font-medium">{DEPT_LABEL[t.escalationAdvice.to_dept] || t.escalationAdvice.to_dept}</p>
              {t.escalationAdvice.reason && <p>{t.escalationAdvice.reason}</p>}
              {t.escalationAdvice.quote && <p className="break-words text-muted-foreground">고객 문의: “{t.escalationAdvice.quote}”</p>}
              {(pendingCustomerInfo(t) > 0 || t.customerRequestStatus === "waiting") && <p className="text-muted-foreground">고객 자료를 받으면 이관 여부를 다시 판단합니다.</p>}
            </div>
          </PanelBlock>
        )}
        {t.followupLink && !t.followupLink.dismissed && (
          <PanelBlock icon={BookOpen} tone="info" title="이전 문의와의 연결 근거">
            <FollowupEvidence link={t.followupLink} />
          </PanelBlock>
        )}
        {requestRows.length > 0 && (
          <PanelBlock icon={Paperclip} tone="info" title={presentation.reasonTitle}>
            <RequestChecklist rows={requestRows} data={insight.data} />
          </PanelBlock>
        )}
        <PanelBlock icon={FileText} tone="info" title="문의 요약">
          {insight.data?.reading ? <ReadingSummary data={insight.data} showUnresolved={presentation.showUnresolved} omitChangedFields={requestRows.map((row: { field: string }) => row.field)} /> : <div className="grid gap-2.5 rounded-2xl bg-[#026bb4]/[0.06] p-4 text-[15px] leading-[1.7]">{sum.lines.slice(0, 2).map((l, i) => <p key={i}>{l}</p>)}</div>}
          <InsightStatus busy={insight.busy} error={insight.error} retry={insight.retry} />
          {t.apiExtraction?.safety_review_required && <p className="mt-2 text-sm text-warning-ink">안전 관련 담당자 검토가 필요합니다.</p>}
          {!!c.analysis.issues.length && <p className="mt-2 break-words text-xs text-muted-foreground">분석 검토 항목: {c.analysis.issues.join(" · ")}</p>}
        </PanelBlock>
        {suggested.length > 0 && (
          <PanelBlock icon={Paperclip} tone="info" title="이관 준비 · 추가로 확인할 자료">
            <p className="text-sm text-muted-foreground">이관 요청서에 이미 확보한 정보는 포함되어 있습니다. 아직 받지 못한 권장 자료는 질의서에 기본 포함됩니다. 고객이 제공할 수 없는 자료는 사유를 남기고 이관할 수 있습니다.</p>
            <ul className="mt-2 grid gap-1 text-sm">{suggested.map((row: { field: string; label: string }) => <li key={row.field}>• {row.label}</li>)}</ul>
            {["READY_FOR_REVIEW", "ON_HOLD"].includes(t.apiStatus) && !t.manualReply && t.owner && t.customerRequestStatus !== "waiting" && <Button className="mt-3 w-full" variant="outline" disabled={t.regenerating} onClick={() => requestInvestigationInfo(t)}>필요한 자료 선택·요청문 작성</Button>}
          </PanelBlock>
        )}
        {requests.length > 0 && (
          <PanelBlock icon={Building2} tone="navy" title="전문부서" count={`${requests.length}건`}>
            <ul className="-mx-3 grid">
              {requests.map((r) => (
                <li key={r.key}><LinkRow label={<>{r.source || "부서 미기록"} → {r.target || "부서 미기록"}</>} hint={<Tag tone={r.response ? "green" : "amber"}>{r.response ? "회신 받음" : "회신 대기"}</Tag>} onClick={() => (r.event ? openModal("department-review", { key: r.key }) : openModal("expert-receive", { id: t.id }))} /></li>
              ))}
            </ul>
          </PanelBlock>
        )}
        {presentation.showTechnicalContext && !!insight.data?.reading?.cases.length && (
          <PanelBlock icon={BookOpen} tone="info" title="비슷한 과거 문의">
            <CaseComparisons data={insight.data} showHeading={false} />
          </PanelBlock>
        )}
        {presentation.showTechnicalContext && !insight.data?.reading?.cases.length && c.technical.similarCases.length > 0 && (
          <PanelBlock icon={BookOpen} tone="info" title="검색된 과거 문의">
            <p className="mb-3 text-sm text-muted-foreground">현재 문의와의 조건 비교는 아직 확인되지 않았습니다.</p>
            <ul className="grid gap-3 rounded-2xl bg-muted/60 p-4">{c.technical.similarCases.map((item: any) => <li key={item.id} className="min-w-0">
              <p className="break-words text-sm font-semibold">{item.label || item.id}</p>
              <details className="mt-2 text-sm text-muted-foreground"><summary className="cursor-pointer">사례 원문 보기</summary><p className="mt-2 whitespace-pre-wrap [overflow-wrap:anywhere]">{item.text}</p></details>
            </li>)}</ul>
          </PanelBlock>
        )}
        {evidence.length > 0 && (
          <PanelBlock icon={BookOpen} tone="success" title="참고한 자료" foldable count={`${evidence.length}건`}>
            <ul className="grid min-w-0 rounded-2xl bg-muted/60 p-2">{evidence.slice(0, 4).map((e) => <li key={e.key} className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-1 px-3 py-2.5">
              <span className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-start gap-3"><span className="min-w-0 whitespace-normal text-[15px] font-medium [overflow-wrap:anywhere]">{e.label}</span><span className="max-w-20 whitespace-normal text-right text-xs text-muted-foreground [overflow-wrap:anywhere]">{e.hint}</span></span>
              {e.summary && <span className="min-w-0 [overflow-wrap:anywhere] line-clamp-2 text-sm leading-relaxed text-muted-foreground">{e.summary}</span>}
            </li>)}</ul>
            {evidence.length > 4 && <p className="mt-1 px-3 text-xs text-muted-foreground">외 {evidence.length - 4}건</p>}
          </PanelBlock>
        )}
      </div>
    </aside>
  );
}
