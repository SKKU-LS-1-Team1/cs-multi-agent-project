// 모든 모달 모음. 열림 상태는 store 의 ui.modal 하나로 관리한다.
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { cn } from "@admin/lib/utils";
import { ArrowRight, Building2, ChevronDown, CircleCheck, Clock, LoaderCircle, ShieldAlert, Paperclip } from "lucide-react";
import { Button } from "@admin/components/ui/button";
import { Checkbox } from "@admin/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@admin/components/ui/dialog";
import { Input } from "@admin/components/ui/input";
import { Textarea } from "@admin/components/ui/textarea";
import { documentCatalog } from "@admin/data/knowledge-data";
import { AiMark, Facts, Field, Mono, NativeSelect, PersonAvatar, Tag } from "./common";
import DocContent from "./DocContent";
import { useNavigate } from "react-router-dom";
import {
  canSend, applyPendingAnswer, assignOwner, completeTicket, confirmSend, createTicket, keepCurrentAnswer, saveInfoReview, submitExpertReply,
} from "@admin/lib/actions";
import {
  candidates, completionDraft, customerLanguage, informationAssessment, replyLanguages, runChecks, latestCustomerReply, people, expertDepartments, recommend, referralRows, resource, resourceReason, signedIn, waitingReviews,
} from "@admin/lib/logic";
import { closeModal, findTicket, openModal, tickets, ui, useStore } from "@admin/lib/store";
import { kindLabel, rememberProgressNotice, type CareKind } from "@admin/lib/care";
import { NoticeSession, preparedNotice, type NoticeState } from "@admin/lib/progress-notice";
import { checkBeforeSend, SendQcSession, type QcState } from "@admin/lib/send-qc";
import { isApiTicket, replyPreviewKey } from "@admin/lib/api-sync";
import { AI_STYLE } from "./CareButtons";
import { SEGMENT_KO, STATUS_KO, useCustomers, type Customer } from "@admin/lib/customers";
import type { Ticket } from "@admin/lib/types";

const TITLES: Record<string, string> = {
  "new-ticket": "새 문의 등록", assign: "담당자 및 리소스 확인", send: "발송 확인", "answer-comparison": "답변 초안 갱신", "review-customer": "수신 자료 확인",
  "expert-receive": "전문부서 회신 등록", completion: "문의 완료 처리", "customer-reply": "고객 회신", "department-review": "전문부서 요청·회신", file: "첨부파일",
  document: "기술문서 · iS7 고장 가이드", "knowledge-document": "근거 문서",
};
const WIDE = ["care", "new-ticket", "review-customer", "answer-comparison", "department-review", "knowledge-document", "completion"];

export default function ModalHost() {
  useStore();
  const [sendBusy, setSendBusy] = useState(false);
  const m = ui.modal;
  const t = findTicket(m?.props?.id);
  return (
    <Dialog open={!!m} onOpenChange={(o) => !o && !sendBusy && closeModal()}>
      {m && (
        <DialogContent showCloseButton={!sendBusy} className={cn(MODAL, WIDE.includes(m.type) ? "sm:max-w-2xl" : "sm:max-w-lg")}>
          <DialogHeader className="pr-8"><DialogTitle className="text-[22px] font-semibold">{m.type === "send" && t ? (t.purpose === "request" ? "고객 질의서 발송" : "고객 답변 발송") : m.type === "care" ? kindLabel(m.props?.kind) : TITLES[m.type] || "알림"}</DialogTitle></DialogHeader>
          {m.type === "send" && t ? <Send key={t.id} t={t} onBusy={setSendBusy} /> : <Body type={m.type} props={m.props || {}} t={t} />}
        </DialogContent>
      )}
    </Dialog>
  );
}

function Body({ type, props, t }: { type: string; props: Record<string, any>; t?: Ticket }) {
  switch (type) {
    case "new-ticket": return <NewTicket />;
    case "assign": return t ? <Assign t={t} /> : null;
    case "answer-comparison": return t ? <Comparison t={t} /> : null;
    case "review-customer": return t ? <ReviewCustomer t={t} /> : null;
    case "expert-receive": return t ? <ExpertReceive t={t} requestId={props.requestId} /> : null;
    case "completion": return t ? <Completion t={t} /> : null;
    case "customer-reply": return t ? <CustomerReply t={t} /> : null;
    case "department-review": return <DepartmentReview props={props} />;
    case "care": return <CareModal customerId={props.customerId} kind={props.kind} ticketId={props.ticketId} />;
    case "file": return <FileInfo file={props.file} t={t} />;
    case "document": return <DocumentView />;
    case "knowledge-document": return <KnowledgeDoc id={props.docId} />;
    default: return null;
  }
}
/** 모든 모달의 여백: 안쪽 32px, 구역 사이 24px. 닫기 버튼과 아래 버튼 줄도 같은 여백에 맞춘다. */
const MODAL = "max-h-[90dvh] gap-6 overflow-y-auto rounded-2xl p-8 text-[15px] leading-relaxed [&>[data-slot=dialog-close]]:top-5 [&>[data-slot=dialog-close]]:right-5";
const Footer = ({ children }: { children: ReactNode }) => <DialogFooter className="-mx-8 -mb-8 mt-2 px-8 py-5">{children}</DialogFooter>;
const Close = ({ label = "닫기" }: { label?: string }) => <Button type="button" variant="outline" onClick={closeModal}>{label}</Button>;

function NewTicket() {
  const nav = useNavigate();
  const [channel, setChannel] = useState("이메일"), [product, setProduct] = useState("iS7 75kW"), [language, setLanguage] = useState("English");
  const p = recommend();
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = e.currentTarget, d = Object.fromEntries(new FormData(f)) as Record<string, any>;
    const files = [...(f.elements.namedItem("files") as HTMLInputElement).files!].map((x) => x.name);
    nav("/tickets/" + createTicket({ ...d, channel, product, language }, files));
  };
  return (
    <form onSubmit={submit} className="grid gap-4">
      <div className="flex gap-2" role="group">{["전화", "이메일", "채팅"].map((v) => <Button key={v} type="button" size="sm" variant={channel === v ? "default" : "outline"} onClick={() => setChannel(v)}>{v}</Button>)}</div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="고객·회사"><Input name="company" required placeholder="회사명 또는 고객명" /></Field>
        <Field label="회신 이메일"><Input name="email" type="email" required placeholder="name@company.com" /></Field>
        <Field label="제품"><NativeSelect value={product} onChange={(e) => setProduct(e.target.value)}>{["iS7 75kW", "H100 22kW", "S100 7.5kW", "XGI CPU", "MCCB 100AF"].map((v) => <option key={v}>{v}</option>)}</NativeSelect></Field>
        <Field label="문의 유형"><NativeSelect name="type">{["불량", "설치", "펌웨어", "사양", "문서 요청", "인증·규격", "납기", "견적", "반품", "보증"].map((v) => <option key={v}>{v}</option>)}</NativeSelect></Field>
        <Field label="국가"><Input name="country" required defaultValue="Australia" /></Field>
        <Field label="고객 답변 언어"><NativeSelect value={language} onChange={(e) => setLanguage(e.target.value)}>{replyLanguages.map((v) => <option key={v}>{v}</option>)}</NativeSelect></Field>
        <Field label="제목" className="col-span-2"><Input name="title" required placeholder="문의의 핵심 내용을 입력하세요" /></Field>
        <Field label="문의 내용" className="col-span-2"><Textarea name="body" required placeholder="고객 문의 내용을 입력하세요" /></Field>
        <Field label="첨부파일" className="col-span-2"><Input name="files" type="file" multiple /></Field>
      </div>
      <div className="grid gap-1 rounded-xl bg-muted p-4">
        <div className="flex items-center justify-between"><strong>시스템 자동 배정</strong><Tag tone="green">{p?.name || "미배정"}</Tag></div>
        <p className="text-sm text-muted-foreground">{resourceReason(p)}</p>
      </div>
      <Footer><Close label="취소" /><Button type="submit">등록 및 자동 배정</Button></Footer>
    </form>
  );
}

function Assign({ t }: { t: Ticket }) {
  const eligible = candidates(t.id), best = eligible[0];
  const [owner, setOwner] = useState(t.owner);
  return (
    <form onSubmit={(e) => { e.preventDefault(); assignOwner(t, owner); }} className="grid gap-4">
      <div className="grid gap-2">
        {people.map((p) => {
          const r = resource(p, t.id), ok = eligible.includes(p);
          return (
            <div key={p.name} className="grid gap-1 rounded-xl bg-muted p-4">
              <div className="flex items-center justify-between"><strong className="flex items-center gap-2.5"><PersonAvatar name={p.name} size={32} />{p.name}</strong><Tag tone={p === best ? "green" : ""}>{p === best ? "추천" : ok ? "배정 가능" : "수용량 가득"}</Tag></div>
              <small className="text-muted-foreground">진행 중 {r.count}건</small>
            </div>
          );
        })}
      </div>
      <Field label="담당자">
        <NativeSelect value={owner} onChange={(e) => setOwner(e.target.value)}><option value="">미배정</option>{eligible.map((p) => <option key={p.name}>{p.name}</option>)}</NativeSelect>
      </Field>
      <small className="text-muted-foreground">모든 담당자가 동등하게 응대할 수 있다고 보고, 미완료 건수가 가장 적은 담당자를 추천합니다.</small>
      <Footer><Close label="취소" /><Button type="submit">배정 저장</Button></Footer>
    </form>
  );
}

function Send({ t, onBusy }: { t: Ticket; onBusy: (busy: boolean) => void }) {
  const checks = runChecks(t), pending = checks.some((c) => c.pending);
  const failed = checks.filter((c) => !c.passed && !c.pending);
  const signature = JSON.stringify([t.draft, t.body, t.specialistRevision, t.customerRevision, t.informationReviewedAt, t.apiEvidence, t.approvalError, checks]);
  const [ackFor, setAckFor] = useState("");
  const [qc, setQc] = useState<QcState>({ phase: "idle" });
  const session = useRef<SendQcSession | null>(null);
  useEffect(() => {
    const active = new SendQcSession(setQc);
    session.current = active;
    return () => { active.cancel(); onBusy(false); };
  }, [onBusy]);
  const ack = ackFor === signature, busy = Boolean(t.sending) || qc.phase === "checking" || qc.phase === "sending";
  useEffect(() => { onBusy(busy); }, [busy, onBusy]);
  const demo = !isApiTicket(t);
  const start = () => {
    if (busy || !canSend(t) || (failed.length > 0 && !ack)) return;
    if (!demo) {
      void session.current?.runServer(async () => {
        const sent = await confirmSend(t, { acknowledgedFailures: failed.length > 0 && ack, keepModalOpen: true });
        return { sent, qc: t.customerQc, error: t.approvalError };
      });
      return;
    }
    const key = replyPreviewKey(t), preview = t.replyPreview?.final_text;
    void session.current?.run({
      input: { sourceText: t.draft, finalText: preview || "", language: customerLanguage(t) },
      check: (input) => checkBeforeSend(input, demo),
      isCurrent: () => key === replyPreviewKey(t) && preview === t.replyPreview?.final_text && canSend(t),
      send: () => confirmSend(t, { acknowledgedFailures: failed.length > 0 && ack, keepModalOpen: true }),
    });
  };
  useEffect(() => {
    // 편집 화면의 발송하기에서 바로 검증을 시작한다. 기존 점검 실패는 먼저 확인받는다.
    if (failed.length === 0) start();
  }, [t.id]);
  if (qc.phase === "checking" || qc.phase === "sending") return (
    <div role="status" aria-live="polite" aria-busy="true" className="grid justify-items-center gap-4 py-10 text-center">
      <LoaderCircle aria-hidden="true" className="size-9 animate-spin text-primary" />
      <strong className="text-lg">{qc.phase === "checking" ? "발송 전 내용을 검증하고 있습니다" : "검증 완료 · 발송 처리 중입니다"}</strong>
      <p className="text-sm text-muted-foreground">욕설·모욕·위협 표현과 회사 중요 정보 유출 여부를 확인합니다.</p>
    </div>
  );
  if (qc.phase === "sent") return (
    <>
      <div role="status" aria-live="polite" className="grid justify-items-center gap-4 py-8 text-center">
        <CircleCheck aria-hidden="true" className="size-12 text-emerald-600" />
        <strong className="text-xl">발송 완료</strong>
        <p className="text-sm text-muted-foreground">{`${t.company}에 ${t.purpose === "request" ? "고객 질의서" : "답변"} 발송이 완료되었습니다.`}</p>
      </div>
      <Footer><Button onClick={closeModal}>확인</Button></Footer>
    </>
  );
  if (qc.phase === "blocked" || qc.phase === "error") return (
    <>
      <section role="alert" className="grid gap-3 rounded-xl bg-destructive/10 p-5">
        <strong className="flex items-center gap-2 text-destructive"><ShieldAlert className="size-5" />{qc.phase === "blocked" ? "수정이 필요하여 발송하지 않았습니다" : "검증을 완료하지 못했습니다"}</strong>
        {qc.phase === "error" ? <p className="text-sm">{qc.message}</p> : <ul className="grid gap-4">
          {qc.issues.map((issue, index) => <li key={index} className="grid gap-1 text-sm">
            <b>{issue.category === "abuse" ? "부적절한 표현" : "회사 중요 정보"}</b>
            <blockquote dir="auto" className="whitespace-pre-wrap rounded-lg bg-background p-3">{issue.excerpt}</blockquote>
            <p>{issue.reason}</p>
          </li>)}
        </ul>}
      </section>
      <Footer><Button variant="outline" onClick={closeModal}>돌아가서 수정</Button>{qc.phase === "error" && <Button disabled={!canSend(t)} onClick={start}>다시 검증</Button>}</Footer>
    </>
  );
  return (
    <>
      <p className="text-sm">{t.company}에 {t.purpose === "request" ? "고객 질의서를" : "답변을"} 발송하고 처리 이력에 기록합니다. 영어 원문과 아래의 고객 언어 문구를 함께 기록합니다.</p>
      <p dir="auto" className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded-xl bg-muted px-5 py-4">{t.replyPreview?.final_text}</p>
      <p className="text-sm text-muted-foreground">발송하기를 누르면 욕설·모욕·위협 표현과 회사 중요 정보 유출 여부를 검증합니다. 검증을 통과한 문구만 발송합니다.</p>
      {pending && <p role="status" className="text-sm text-muted-foreground">본문이 변경되어 최종 점검이 필요합니다. 발송 요청 시 현재 내용을 점검하며, 새 오류가 발견되면 발송을 보류합니다.</p>}
      {t.approvalError && <p role="alert" className="text-sm text-destructive">{t.approvalError}</p>}
      {failed.length > 0 && (
        <section role="alert" className="grid gap-2 rounded-xl bg-destructive/10 p-4">
          <strong className="text-destructive">자동 점검에서 확인이 필요한 항목이 {failed.length}건 있습니다</strong>
          <ul className="grid gap-1 text-sm">{failed.map((c) => <li key={c.name}><b className="font-semibold">{c.label}</b> · {c.reason}</li>)}</ul>
          <label className="flex items-center gap-2 text-sm"><Checkbox disabled={busy} checked={ack} onCheckedChange={(v) => setAckFor(v === true ? signature : "")} />확인했고, 그대로 발송합니다.</label>
        </section>
      )}
      <Footer><Button variant="outline" disabled={busy} onClick={closeModal}>계속 수정</Button><Button disabled={busy || !canSend(t) || (failed.length > 0 && !ack)} onClick={start}>{busy ? "처리 중…" : "발송하기"}</Button></Footer>
    </>
  );
}

function Comparison({ t }: { t: Ticket }) {
  const p = t.pendingAnswer;
  if (!p) return null;
  return (
    <>
      <div className="flex flex-wrap gap-2">{p.context.references.map((r: any) => <Tag key={r.id}>{r.label}</Tag>)}</div>
      <p className="text-sm">작성 중인 답변을 최신 자료로 다시 작성할까요? 현재 답변은 처리 이력에 남깁니다.</p>
      <Footer><Button variant="outline" onClick={() => keepCurrentAnswer(t)}>현재 답변 유지</Button><Button onClick={() => applyPendingAnswer(t)}>새 초안 적용</Button></Footer>
    </>
  );
}

function ReviewCustomer({ t }: { t: Ticket }) {
  const [snapshot] = useState(() => ({ replyId: latestCustomerReply(t)?.id, revision: t.customerRevision, reviewedAt: t.informationReviewedAt ?? null, items: informationAssessment(t) }));
  const reply = t.events.find((e) => e.id === snapshot.replyId), items = snapshot.items;
  const [vals, setVals] = useState<Record<string, { status: string; value: string; evidence: string }>>(() => Object.fromEntries(items.map((x) => [x.id, { status: x.status, value: x.value || "", evidence: x.evidence || "" }])));
  if (!reply) return null;
  const stale = t.source === "api" && (snapshot.reviewedAt !== (t.informationReviewedAt ?? null) || snapshot.revision !== t.customerRevision || latestCustomerReply(t)?.id !== snapshot.replyId);
  const busy = Boolean(t.informationSaving);
  const set = (id: string, patch: Partial<{ status: string; value: string; evidence: string }>) => setVals((v) => ({ ...v, [id]: { ...v[id], ...patch } }));
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (!stale && !busy) void saveInfoReview(t, reply.id!, vals, snapshot.revision, snapshot.reviewedAt); }} className="grid gap-4">
      {stale && <p role="alert" className="text-sm text-destructive">새 고객 회신이 도착했습니다. 창을 닫고 최신 회신을 다시 확인해 주세요.</p>}
      <article className="grid gap-2 rounded-xl bg-muted p-4">
        <h3 className="font-semibold">고객 회신</h3><small className="text-muted-foreground">{reply.time || "수신 시각 미기록"}</small><p className="text-sm">{reply.text}</p>
        <div className="flex flex-wrap gap-2">{(reply.files || []).map((f: string) => <Button key={f} type="button" size="sm" variant="outline" onClick={() => openModal("file", { file: f, id: t.id })}>{f}</Button>)}{!(reply.files || []).length && <small className="text-muted-foreground">연결된 첨부자료 없음</small>}</div>
      </article>
      <fieldset disabled={busy || stale} className="grid gap-3"><legend className="mb-1 text-sm font-semibold">자료 충족 여부</legend>
        {items.map((x) => (
          <div key={x.id} className="grid grid-cols-[150px_150px_1fr] items-center gap-2">
            <label htmlFor={"check-" + x.id} className="text-sm">{x.label}</label>
            <NativeSelect id={"check-" + x.id} value={vals[x.id].status} onChange={(e) => set(x.id, { status: e.target.value })}>
              <option value="provided" disabled>추출됨 · 확인 필요</option><option value="missing">미수신</option><option value="unusable">수신 · 보완 필요</option><option value="confirmed">확인 완료</option>
            </NativeSelect>
            <div className="grid gap-2">
              {t.source === "api" && <Input aria-label={`${x.label} 확인값`} placeholder="실제 확인한 값" required={vals[x.id].status === "confirmed"} value={vals[x.id].value} onChange={(e) => set(x.id, { value: e.target.value })} />}
              <Input aria-label={`${x.label} 확인 근거`} placeholder="자료에서 확인한 내용" required={vals[x.id].status === "confirmed"} value={vals[x.id].evidence} onChange={(e) => set(x.id, { evidence: e.target.value })} />
            </div>
          </div>
        ))}
      </fieldset>
      <Footer><Close label="취소" /><Button type="submit" disabled={busy || stale}>{busy ? "저장 중…" : "확인 결과 저장"}</Button></Footer>
    </form>
  );
}

function ExpertReceive({ t, requestId }: { t: Ticket; requestId?: string }) {
  const pending = waitingReviews(t);
  const [sel, setSel] = useState(requestId && pending.some((r) => r.id === requestId) ? requestId : pending[0]?.id || (t.legacyReviewPending ? "legacy" : ""));
  const [body, setBody] = useState("");
  return (
    <form onSubmit={(e) => { e.preventDefault(); submitExpertReply(t, sel, body); }} className="grid gap-4">
      <Field label="연결 요청">
        <NativeSelect disabled={t.specialistSaving} value={sel} onChange={(e) => setSel(e.target.value)}>
          {pending.map((r) => <option key={r.id} value={r.id}>{r.department} · {r.id}</option>)}
          {t.legacyReviewPending && <option value="legacy">기존 검토 · 요청 정보 미기록</option>}
        </NativeSelect>
      </Field>
      <Field label="회신 내용"><Textarea disabled={t.specialistSaving} required className="min-h-32" value={body} onChange={(e) => setBody(e.target.value)} placeholder="전문부서에서 받은 원인·점검 결과·권장 조치를 입력하세요." /></Field>
      <Footer><Close label="취소" /><Button type="submit" disabled={t.specialistSaving || !body.trim() || !sel}>{t.specialistSaving ? "저장 중…" : "회신 등록"}</Button></Footer>
    </form>
  );
}

function Completion({ t }: { t: Ticket }) {
  const ai = completionDraft(t);
  const previous = t.resolutionSuperseded ? undefined : t.resolution;
  const [v, setV] = useState({ outcome: previous?.outcome || ai.outcome, cause: previous?.cause || ai.cause, action: previous?.action || ai.action, result: previous?.result || ai.result, verification: previous?.verification || ai.verification, ...t.resolutionDraft });
  const [busy, setBusy] = useState(false);
  const bind = (k: keyof typeof v) => ({ disabled: busy, value: v[k], onChange: (e: any) => setV({ ...v, [k]: e.target.value }) });
  return (
    <form onSubmit={async (e) => { e.preventDefault(); if (busy) return; setBusy(true); try { await completeTicket(t, v); } finally { setBusy(false); } }} className="grid gap-4">
      <div className="flex items-center justify-between rounded-xl bg-muted p-4"><strong><Mono>{t.id}</Mono> · {t.title}</strong><Tag tone="green">답변 발송 완료</Tag></div>
      {ai.from.length > 0 && <p className="flex items-center gap-2 rounded-xl bg-[#003377]/[0.06] px-4 py-3 text-sm"><AiMark />이력({ai.from.join(" · ")})에 있는 기록으로 미리 채웠습니다. 최종 원인과 실제 수행 조치는 확인 후 입력해 주세요.</p>}
      <Field label="처리 결과 구분">
        <NativeSelect required {...bind("outcome")}><option value="">선택</option><option value="resolved">문제 해결 확인</option><option value="provided">정보 제공 완료</option><option value="unconfirmed">해결 여부 미확인 종결</option></NativeSelect>
      </Field>
      <Field label={["불량", "설치", "펌웨어"].includes(t.type) ? "최종 확인 원인" : "최종 판단·처리 사유"}><Textarea required placeholder="확인된 원인 또는 처리 판단을 기록하세요." {...bind("cause")} /></Field>
      <Field label="수행 조치"><Textarea required placeholder="실제로 수행한 조치를 기록하세요." {...bind("action")} /></Field>
      <Field label="처리 결과"><Textarea required placeholder="해결 여부와 확인 근거를 기록하세요." {...bind("result")} /></Field>
      <Field label="확인 근거"><Input required placeholder="예: 전문부서 회신, 고객 회신, 현장 확인 기록" {...bind("verification")} /></Field>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" required className="size-4 accent-[var(--primary)]" />처리 결과를 확인했으며 문의를 완료합니다.</label>
      <Footer><Close label="취소" /><Button type="submit" disabled={busy}>{busy ? "완료 처리 중…" : "결과 저장 및 완료"}</Button></Footer>
    </form>
  );
}

function CustomerReply({ t }: { t: Ticket }) {
  const r = latestCustomerReply(t);
  if (!r) return null;
  return (
    <>
      <article className="grid gap-2 rounded-xl bg-muted p-4"><small className="text-muted-foreground">{r.time || "수신 시각 미기록"}</small><p className="text-sm">{r.text}</p>
        <div className="flex flex-wrap gap-2">{(r.files || []).map((f: string) => <Button key={f} size="sm" variant="outline" onClick={() => openModal("file", { file: f, id: t.id })}>{f}</Button>)}</div></article>
      <Footer><Close /></Footer>
    </>
  );
}

type NoticeTicket = { id: string; title: string; status: string; apiLanguage: string | null };

/** 진행상황 안내: 영어 초안 검토 → 고객 언어 문구 준비. 발송은 하지 않는다. */
function CareModal({ customerId, ticketId }: { customerId: string; kind: CareKind; ticketId?: string }) {
  const { rows, error } = useCustomers();
  const known = rows?.find((x) => x.id === customerId);
  const linked: NoticeTicket[] = (known?.notice_tickets || []).map((t) => ({ ...t,
    apiLanguage: t.language, status: STATUS_KO[t.status] || t.status }));
  const c = known;
  return c ? <><p role={error ? "alert" : undefined} className="text-sm text-destructive">{error && `${error} 마지막 조회 정보를 표시합니다.`}</p><CareForm key={customerId} c={c} ticketId={ticketId} linked={linked} /></>
    : <p className="text-sm text-muted-foreground">{error || (rows ? "서버에 연결된 고객 문의가 없습니다." : "고객 문의를 불러오는 중입니다.")}</p>;
}
function CareForm({ c, ticketId, linked }: { c: Pick<Customer, "id" | "name"> & Partial<Customer>; ticketId?: string; linked: NoticeTicket[] }) {
  const [sel, setSel] = useState<string[]>(ticketId ? [ticketId] : linked.slice(0, 10).map((t) => t.id));
  const [state, setState] = useState<NoticeState>({ ticketIds: [], text: "", notice: null, busy: null, error: "" });
  const [session] = useState(() => new NoticeSession(setState));
  const selected = linked.filter((t) => sel.includes(t.id));
  const selectedKey = JSON.stringify(selected.map((t) => t.id).sort());
  useEffect(() => {
    session.select(JSON.parse(selectedKey)); void session.restore();
    return () => session.dispose();
  }, [session, selectedKey]);
  const prepared = preparedNotice(state), busy = Boolean(state.busy);
  const unavailable = !linked.length ? "진행상황을 안내할 미완료 문의가 없습니다."
    : !selected.length ? "안내할 문의를 선택하세요."
      : selected.some((t) => !t.apiLanguage) ? "고객 언어가 확인된 문의를 선택하세요."
        : new Set(selected.map((t) => t.apiLanguage)).size > 1 ? "고객 언어가 같은 문의끼리 선택하세요." : "";
  const changedPrepared = state.notice?.status === "prepared" && state.text !== state.notice.approved_text;
  const write = async () => { if (!unavailable) await session.generate(); };
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (unavailable || busy) return;
    const result = await session.prepare(signedIn);
    if (result) { rememberProgressNotice(result); toast("고객 언어 문구를 저장했습니다. 실제 발송은 하지 않았습니다."); }
  };
  return (
    <form onSubmit={submit} className="grid gap-5">
      <p className="text-[15px] text-muted-foreground"><b className="font-semibold text-foreground">{c.name}</b>{c.tier && ` · ${c.tier}`}{c.seg && ` · ${SEGMENT_KO[c.seg] || c.seg}`}</p>
      {(linked.length > 0 || (c.urgent?.length || 0) > 0) && (
        <fieldset className="grid gap-1.5">
          <legend className="mb-1 text-sm text-muted-foreground">안내할 문의 <span className="tabular-nums">{selected.length}/{linked.length || c.urgent?.length}</span> · 최대 10건</legend>
          {linked.length ? linked.map((t) => (
            <label key={t.id} className="flex cursor-pointer items-center gap-3 rounded-xl bg-muted/60 px-4 py-2.5 text-[15px]">
              <Checkbox disabled={busy || (!sel.includes(t.id) && selected.length >= 10)} checked={sel.includes(t.id)} onCheckedChange={(v) => setSel((s) => v === true ? [...s, t.id] : s.filter((id) => id !== t.id))} />
              <span className="min-w-0 flex-1"><span className="block truncate font-medium">{t.title}</span><Mono className="text-xs text-muted-foreground">{t.id}</Mono></span>
              <span className="shrink-0 text-sm text-muted-foreground">{t.status}</span>
            </label>
          )) : c.urgent?.map((u) => (
            <label key={u[0]} className="flex items-center gap-3 rounded-xl bg-muted/60 px-4 py-2.5 text-[15px]">
              <Checkbox disabled checked={false} /><span className="min-w-0 flex-1"><span className="block truncate font-medium">{u[1]}</span><Mono className="text-xs text-muted-foreground">{u[0]}</Mono></span><span className="text-sm text-muted-foreground">문의 조회 필요</span>
            </label>
          ))}
        </fieldset>
      )}
      {unavailable && <p className="text-sm text-muted-foreground">{unavailable}</p>}
      <div className="grid gap-2.5">
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm text-muted-foreground">안내 메일 · 담당자 검토용 영어 초안</span>
          <Button type="button" size="sm" className={AI_STYLE} disabled={busy || Boolean(unavailable)} onClick={write}><AiMark className="size-3.5 text-white" />{state.busy === "generate" ? "작성 중…" : state.busy === "load" ? "불러오는 중…" : state.text ? "다시 작성" : "AI 초안 작성"}</Button>
        </div>
        <Textarea aria-label="진행상황 영어 초안" className="min-h-40 leading-relaxed" disabled={Boolean(unavailable) || Boolean(prepared)} value={state.text} onChange={(e) => session.edit(e.target.value)} placeholder="실제 문의 상태와 처리 기록으로 영어 초안을 만듭니다. 담당자가 확인한 뒤 고객 언어로 변환합니다." />
        {state.notice?.draft_text && state.notice.draft_text !== state.text && <details className="text-sm text-muted-foreground"><summary className="cursor-pointer">AI가 작성한 영어 원문</summary><p className="mt-2 whitespace-pre-wrap">{state.notice.draft_text}</p></details>}
        {state.notice?.source_facts?.length ? <details className="text-sm text-muted-foreground"><summary className="cursor-pointer">초안에 사용한 문의 기록 · {state.notice.source_facts.length}건</summary><ul className="mt-2 grid gap-2">{state.notice.source_facts.map((f) => <li key={f.ticket_id}><Mono>{f.ticket_id}</Mono> · {STATUS_KO[f.status] || ({ READY_FOR_REVIEW: "답변 검토", ON_HOLD: "보류", APPROVED: "답변 승인", HUMAN_QUEUE: "사람 검토", ANALYSIS_PENDING: "분석 대기", REJECTED: "반려" } as Record<string, string>)[f.status] || f.status}{f.product_code && ` · ${f.product_code}`}<p>전문부서 회신 대기 {f.pending_specialist_count}건 · 회신 수신 {f.received_specialist_count}건{f.waiting_for_customer && " · 고객 회신 대기"}{f.resolution_outcome && ` · 처리 결과: ${{ resolved: "해결 확인", provided: "정보 제공 확인", unconfirmed: "해결 미확인 종결" }[f.resolution_outcome] || f.resolution_outcome}`}</p></li>)}</ul></details> : null}
      </div>
      {state.error && <p role="alert" className="text-sm text-destructive">{state.error}</p>}
      {changedPrepared && <p className="text-sm text-warning-ink">확인 요청 중 변경한 본문을 보존했습니다. 다시 작성하여 새 안내문을 확인해 주세요.</p>}
      {prepared && <div className="grid gap-2 rounded-xl bg-muted/60 p-4"><strong className="text-sm">발송용 문구 준비 · 실제 발송 안 함</strong><small className="text-muted-foreground">고객 언어 · {prepared.target_language}</small><p lang={prepared.target_language} dir="auto" className="whitespace-pre-wrap text-sm leading-relaxed">{prepared.final_text}</p></div>}
      <Footer><Close /><Button type="submit" disabled={busy || Boolean(unavailable) || !state.notice || !state.text.trim() || Boolean(prepared) || changedPrepared}>{state.busy === "prepare" ? "문구 준비 중…" : prepared ? "문구 저장 완료" : "확인 후 고객 언어로 변환"}</Button></Footer>
    </form>
  );
}

const stamp = (iso?: string | null) => {
  if (!iso) return "미기록";
  const d = new Date(iso), z = (n: number) => String(n).padStart(2, "0");
  return `${z(d.getMonth() + 1)}.${z(d.getDate())} ${z(d.getHours())}:${z(d.getMinutes())}`;
};
const Cell = ({ label, children, wide }: { label: string; children: ReactNode; wide?: boolean }) => (
  <div className={wide ? "col-span-3" : ""}><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-0.5 font-medium">{children}</dd></div>
);

/** 전문부서 요청·회신: 위에서 아래로 "무슨 요청인가 → 누구에게 언제 → 요청 내용 → 회신" 순서. 회신 상태는 색으로 바로 보인다. */
function DepartmentReview({ props }: { props: Record<string, any> }) {
  const nav = useNavigate();
  const r = props.key ? referralRows().find((x) => x.key === props.key) : referralRows().find((x) => x.ticket.id === props.ticketId && x.requestId === props.requestId);
  if (!r?.event) return null;
  const e = r.event, c = e.requestContext, files: string[] | null = Array.isArray(e.transmittedFiles) ? e.transmittedFiles : null;
  const canReply = !r.response && r.ticket.stage !== 5;
  return (
    <div className="grid gap-5">
      <header className="grid gap-2">
        <div className="flex items-center justify-between">
          <span className="inline-flex h-6 items-center gap-1.5 rounded-full bg-slate-200/70 px-2.5 text-xs font-medium text-slate-700"><Building2 className="size-3.5" aria-hidden />전문부서 요청</span>
          <Tag tone={r.response ? "green" : "amber"}>{r.response ? "회신 받음" : "회신 대기"}</Tag>
        </div>
        <h3 className="text-xl font-bold leading-snug">{r.ticket.title}</h3>
        <p className="text-sm text-muted-foreground"><Mono>{r.requestId}</Mono> · <Mono>{r.ticket.id}</Mono> · {r.ticket.product}</p>
      </header>

      <dl className="grid grid-cols-3 gap-x-6 gap-y-4 rounded-xl bg-muted/60 p-4 text-[15px]">
        <Cell wide label="요청 → 대상 부서"><span className="inline-flex items-center gap-2">{r.source || "부서 미기록"}<ArrowRight className="size-4 text-muted-foreground" aria-hidden />{r.target || "부서 미기록"}</span></Cell>
        <Cell label="요청 담당자">{e.actor || "미기록"}</Cell>
        <Cell label="요청일">{stamp(r.when)}</Cell>
        <Cell label="전달 방식">{e.channel || "미기록"}</Cell>
      </dl>

      <section className="grid gap-2">
        <h4 className="text-sm font-semibold">검토 요청사항</h4>
        <p className="whitespace-pre-line rounded-xl bg-[#003377]/[0.05] p-4 text-[15px] leading-relaxed">{e.request || e.text}</p>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">전달 자료</span>
          {files?.length ? files.map((f) => <span key={f} className="inline-flex h-6 items-center gap-1.5 rounded-full bg-muted px-2.5 text-xs"><Paperclip className="size-3" aria-hidden />{f}</span>) : <span className="text-muted-foreground">{files ? "없음" : "미기록"}</span>}
        </div>
      </section>

      {c && (
        <details className="group/ctx text-sm"><summary className="flex w-fit cursor-pointer list-none items-center gap-1 text-muted-foreground hover:text-foreground [&::-webkit-details-marker]:hidden">요청 당시 검토 정보<ChevronDown className="size-3.5 transition-transform group-open/ctx:rotate-180" aria-hidden /></summary>
          <Facts className="mt-3" rows={[["제품·오류", c.analysis.product + (c.analysis.errorCode ? " · " + c.analysis.errorCode : "")], ["누락 항목", c.missingInfo.join(" · ") || "확인된 누락 항목 없음"], ["참고 근거", c.references.map((x: any) => x.label).join(" · ") || "연결된 근거 없음"]]} /></details>
      )}

      {r.response ? (
        <section className="grid gap-2 rounded-xl bg-success/10 p-4">
          <div className="flex items-center justify-between"><h4 className="flex items-center gap-1.5 text-sm font-semibold text-success"><CircleCheck className="size-4" aria-hidden />전문부서 회신</h4><small className="text-muted-foreground">{r.response.time} · 등록 {r.response.actor || "미기록"}</small></div>
          <p className="whitespace-pre-line text-[15px] leading-relaxed">{r.response.text}</p>
        </section>
      ) : (
        <section className="flex items-center gap-2.5 rounded-xl border border-dashed p-4 text-sm text-muted-foreground"><Clock className="size-4 text-warning" aria-hidden />전문부서의 회신을 기다리고 있습니다.</section>
      )}

      <Footer>
        <Close />
        <Button variant="outline" onClick={() => { closeModal(); nav("/tickets/" + r.ticket.id); }}>원본 문의 열기</Button>
        {canReply && <Button onClick={() => openModal("expert-receive", { id: r.ticket.id, requestId: r.requestId })}>회신 등록</Button>}
      </Footer>
    </div>
  );
}

function FileInfo({ file, t }: { file: string; t?: Ticket }) {
  return (
    <>
      <p className="text-sm text-muted-foreground"><b className="text-foreground">{file}</b><br />{t?.files?.includes(file) ? "등록된 파일명입니다. 로컬 화면에서 파일 원본은 저장하지 않습니다." : "이 문의에 연결된 첨부파일 항목입니다. 원본 파일은 아직 연결되지 않았습니다."}</p>
      <Footer><Close /></Footer>
    </>
  );
}
function DocumentView() {
  return (
    <>
      <div className="text-sm text-info">§3.2 / §3.3 · E.OC</div>
      <h3 className="font-semibold">발생 조건별 검토</h3>
      <p className="text-sm text-muted-foreground">운전 시작 시점, 운전 부하 및 이벤트 로그를 확인해 원인 후보를 구분합니다. 현장 점검 결과와 유사 해결 사례를 비교한 뒤 전문부서에서 조치를 판단합니다.</p>
      <div className="rounded-lg bg-secondary px-4 py-3 text-sm text-muted-foreground">연결된 원본 문서가 없는 로컬 화면입니다. 현재 표시된 문구는 화면 검토용이며 실제 기술문서의 인용문이 아닙니다.</div>
      <Footer><Close /></Footer>
    </>
  );
}
function KnowledgeDoc({ id }: { id: string }) {
  const d = documentCatalog.find((x) => x.doc_id === id);
  if (!d) return <><p className="text-sm text-muted-foreground">연결된 문서를 찾을 수 없습니다.</p><Footer><Close /></Footer></>;
  return (
    <>
      <div className="text-sm text-info">{d.doc_id} · Rev {d.revision}</div>
      <div className="max-h-[60dvh] overflow-y-auto pr-1"><DocContent text={d.content} /></div>
      <Footer><Close /></Footer>
    </>
  );
}
