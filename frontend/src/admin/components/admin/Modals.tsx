// 모든 모달 모음. 열림 상태는 store 의 ui.modal 하나로 관리한다.
import { useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { cn } from "@admin/lib/utils";
import { ArrowRight, Building2, ChevronDown, CircleCheck, Clock, Paperclip } from "lucide-react";
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
  applyPendingAnswer, assignOwner, completeTicket, confirmSend, createTicket, keepCurrentAnswer, saveInfoReview, submitExpertReply,
} from "@admin/lib/actions";
import {
  candidates, customerLanguage, FEEDBACK_REASONS, informationAssessment, isEdited, needsLocalization, replyLanguages, runChecks, latestCustomerReply, people, expertDepartments, recommend, referralRows, resource, resourceReason, waitingReviews,
} from "@admin/lib/logic";
import { closeModal, findTicket, openModal, ui, useStore } from "@admin/lib/store";
import { addCareAction, KIND_LABEL, kindLabel, type CareKind } from "@admin/lib/care";
import { AI_KINDS, AI_STYLE } from "./CareButtons";
import { isLate, lateText, SEGMENT_KO, useCustomers, type Customer } from "@admin/lib/customers";
import type { Ticket } from "@admin/lib/types";

const TITLES: Record<string, string> = {
  "new-ticket": "새 티켓 등록", assign: "담당자 및 리소스 확인", send: "발송 확인", "answer-comparison": "답변 초안 갱신", "review-customer": "수신 자료 확인",
  "expert-receive": "전문부서 회신 등록", completion: "티켓 완료 처리", "customer-reply": "고객 회신", "department-review": "전문부서 요청·회신", file: "첨부파일",
  document: "기술문서 · iS7 고장 가이드", "knowledge-document": "근거 문서",
};
const WIDE = ["care", "new-ticket", "review-customer", "answer-comparison", "department-review", "knowledge-document", "completion"];

export default function ModalHost() {
  useStore();
  const m = ui.modal;
  const t = findTicket(m?.props?.id);
  return (
    <Dialog open={!!m} onOpenChange={(o) => !o && closeModal()}>
      {m && (
        <DialogContent className={WIDE.includes(m.type) ? "max-h-[90dvh] overflow-y-auto sm:max-w-2xl" : "max-h-[90dvh] overflow-y-auto sm:max-w-lg"}>
          <DialogHeader><DialogTitle>{m.type === "send" && t ? (t.purpose === "request" ? "고객 질의서 발송" : "고객 답변 발송") : m.type === "care" ? kindLabel(m.props?.kind) : TITLES[m.type] || "알림"}</DialogTitle></DialogHeader>
          <Body type={m.type} props={m.props || {}} t={t} />
        </DialogContent>
      )}
    </Dialog>
  );
}

function Body({ type, props, t }: { type: string; props: Record<string, any>; t?: Ticket }) {
  switch (type) {
    case "new-ticket": return <NewTicket />;
    case "assign": return t ? <Assign t={t} /> : null;
    case "send": return t ? <Send t={t} /> : null;
    case "answer-comparison": return t ? <Comparison t={t} /> : null;
    case "review-customer": return t ? <ReviewCustomer t={t} /> : null;
    case "expert-receive": return t ? <ExpertReceive t={t} requestId={props.requestId} /> : null;
    case "completion": return t ? <Completion t={t} /> : null;
    case "customer-reply": return t ? <CustomerReply t={t} /> : null;
    case "department-review": return <DepartmentReview props={props} />;
    case "care": return <CareModal customerId={props.customerId} kind={props.kind} />;
    case "file": return <FileInfo file={props.file} t={t} />;
    case "document": return <DocumentView />;
    case "knowledge-document": return <KnowledgeDoc id={props.docId} />;
    default: return null;
  }
}
const Footer = ({ children }: { children: ReactNode }) => <DialogFooter className="mt-2">{children}</DialogFooter>;
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
              <small className="text-muted-foreground">이 티켓 제외 미완료 {r.count}/{r.capacity}건 · 여유 {r.free}건</small>
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

function Send({ t }: { t: Ticket }) {
  const failed = runChecks(t).filter((c) => !c.passed), edited = isEdited(t);
  const [ack, setAck] = useState(false), [reason, setReason] = useState(""), [note, setNote] = useState("");
  return (
    <>
      <p className="text-sm">{t.company}에 {t.purpose === "request" ? "고객 질의서를" : "답변을"} 발송하고 처리 이력에 기록합니다.{needsLocalization(t) && <> 승인하면 영어 초안을 <b>{customerLanguage(t)}</b>로 자동 변환해 보내며, 영어 원본도 함께 기록합니다.</>}</p>
      {failed.length > 0 && (
        <section role="alert" className="grid gap-2 rounded-xl bg-destructive/10 p-4">
          <strong className="text-destructive">자동 점검에서 확인이 필요한 항목이 {failed.length}건 있습니다</strong>
          <ul className="grid gap-1 text-sm">{failed.map((c) => <li key={c.name}><b className="font-semibold">{c.label}</b> · {c.reason}</li>)}</ul>
          <label className="flex items-center gap-2 text-sm"><Checkbox checked={ack} onCheckedChange={(v) => setAck(v === true)} />확인했고, 그대로 발송합니다.</label>
        </section>
      )}
      {edited && (
        <section className="grid gap-2.5 rounded-xl bg-muted p-4">
          <strong className="text-sm">AI 초안에서 고치셨네요. 무엇을 고치셨나요? <span className="font-normal text-muted-foreground">(선택 · 다음 초안을 개선하는 데 쓰입니다)</span></strong>
          <div className="flex flex-wrap gap-2" role="group" aria-label="수정 사유">
            {FEEDBACK_REASONS.map(([key, label]) => <Button key={key} type="button" size="sm" variant={reason === key ? "default" : "outline"} aria-pressed={reason === key} onClick={() => setReason(reason === key ? "" : key)}>{label}</Button>)}
          </div>
          <Input aria-label="한 줄 메모" placeholder="한 줄 메모(선택)" value={note} onChange={(e) => setNote(e.target.value)} />
        </section>
      )}
      <Footer><Close label="계속 수정" /><Button disabled={failed.length > 0 && !ack} onClick={() => confirmSend(t, { reason, note, acknowledgedFailures: failed.length > 0 && ack })}>발송 기록</Button></Footer>
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
  const reply = latestCustomerReply(t), items = informationAssessment(t);
  const [vals, setVals] = useState<Record<string, { status: string; evidence: string }>>(() => Object.fromEntries(items.map((x) => [x.id, { status: x.status, evidence: x.evidence || "" }])));
  if (!reply) return null;
  const set = (id: string, patch: Partial<{ status: string; evidence: string }>) => setVals((v) => ({ ...v, [id]: { ...v[id], ...patch } }));
  return (
    <form onSubmit={(e) => { e.preventDefault(); saveInfoReview(t, reply.id!, vals); }} className="grid gap-4">
      <article className="grid gap-2 rounded-xl bg-muted p-4">
        <h3 className="font-semibold">고객 회신</h3><small className="text-muted-foreground">{reply.time || "수신 시각 미기록"}</small><p className="text-sm">{reply.text}</p>
        <div className="flex flex-wrap gap-2">{(reply.files || []).map((f: string) => <Button key={f} type="button" size="sm" variant="outline" onClick={() => openModal("file", { file: f, id: t.id })}>{f}</Button>)}{!(reply.files || []).length && <small className="text-muted-foreground">연결된 첨부자료 없음</small>}</div>
      </article>
      <fieldset className="grid gap-3"><legend className="mb-1 text-sm font-semibold">자료 충족 여부</legend>
        {items.map((x) => (
          <div key={x.id} className="grid grid-cols-[150px_150px_1fr] items-center gap-2">
            <label htmlFor={"check-" + x.id} className="text-sm">{x.label}</label>
            <NativeSelect id={"check-" + x.id} value={vals[x.id].status} onChange={(e) => set(x.id, { status: e.target.value })}>
              <option value="missing">미수신</option><option value="unusable">수신 · 보완 필요</option><option value="confirmed">확인 완료</option>
            </NativeSelect>
            <Input aria-label={`${x.label} 확인 근거`} placeholder="자료에서 확인한 내용" required={vals[x.id].status === "confirmed"} value={vals[x.id].evidence} onChange={(e) => set(x.id, { evidence: e.target.value })} />
          </div>
        ))}
      </fieldset>
      <Footer><Close label="취소" /><Button type="submit">확인 결과 저장</Button></Footer>
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
        <NativeSelect value={sel} onChange={(e) => setSel(e.target.value)}>
          {pending.map((r) => <option key={r.id} value={r.id}>{r.department} · {r.id}</option>)}
          {t.legacyReviewPending && <option value="legacy">기존 검토 · 요청 정보 미기록</option>}
        </NativeSelect>
      </Field>
      <Field label="회신 내용"><Textarea required className="min-h-32" value={body} onChange={(e) => setBody(e.target.value)} placeholder="전문부서에서 받은 원인·점검 결과·권장 조치를 입력하세요." /></Field>
      <Footer><Close label="취소" /><Button type="submit">회신 등록</Button></Footer>
    </form>
  );
}

function Completion({ t }: { t: Ticket }) {
  const [v, setV] = useState({ outcome: t.customerOutcome === "resolved" || t.customerOutcome === "provided" ? t.customerOutcome : "", cause: t.resolution?.cause || "", action: t.resolution?.action || "", result: t.resolution?.result || "", verification: t.resolution?.verification || "", ...t.resolutionDraft });
  const [busy, setBusy] = useState(false);
  const bind = (k: keyof typeof v) => ({ disabled: busy, value: v[k], onChange: (e: any) => setV({ ...v, [k]: e.target.value }) });
  return (
    <form onSubmit={async (e) => { e.preventDefault(); if (busy) return; setBusy(true); try { await completeTicket(t, v); } finally { setBusy(false); } }} className="grid gap-4">
      <div className="flex items-center justify-between rounded-xl bg-muted p-4"><strong><Mono>{t.id}</Mono> · {t.title}</strong><Tag tone="green">답변 발송 완료</Tag></div>
      <Field label="처리 결과 구분">
        <NativeSelect required {...bind("outcome")}><option value="">선택</option><option value="resolved">문제 해결 확인</option><option value="provided">정보 제공 완료</option><option value="unconfirmed">해결 여부 미확인 종결</option></NativeSelect>
      </Field>
      <Field label={["불량", "설치", "펌웨어"].includes(t.type) ? "최종 확인 원인" : "최종 판단·처리 사유"}><Textarea required placeholder="확인된 원인 또는 처리 판단을 기록하세요." {...bind("cause")} /></Field>
      <Field label="수행 조치"><Textarea required placeholder="실제로 수행한 조치를 기록하세요." {...bind("action")} /></Field>
      <Field label="처리 결과"><Textarea required placeholder="해결 여부와 확인 근거를 기록하세요." {...bind("result")} /></Field>
      <Field label="확인 근거"><Input required placeholder="예: 전문부서 회신, 고객 회신, 현장 확인 기록" {...bind("verification")} /></Field>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" required className="size-4 accent-[var(--primary)]" />처리 결과를 확인했으며 티켓을 완료합니다.</label>
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

/** 고객 조치 창: 안내·사과 초안 / 담당자 변경 / 근본 원인 검토 요청 / 다음 확인 일정. 저장하면 고객의 "조치 내역"에 남는다. */
function CareModal({ customerId, kind }: { customerId: string; kind: CareKind }) {
  const c = useCustomers()?.find((x) => x.id === customerId);
  return c ? <CareForm c={c} kind={kind} /> : null;
}
/** 티켓마다 상태가 다르므로 안내 문구도 티켓의 상태에 맞춰 한 줄씩 쓴다. */
const STATUS_EN: Record<string, string> = { IN_PROGRESS: "being handled by our support team", ESCALATED: "under review by our specialist team", NEW: "received and queued for handling" };
const careDraft = (c: Customer, picked: Customer["urgent"]) => {
  const list = picked.length ? `\n\n${picked.map((u) => `- ${u[1]} (${u[0]}): ${STATUS_EN[u[5]] || "being handled by our team"}`).join("\n")}` : "";
  return `Dear ${c.name} team,\n\nWe would like to update you on your open ${picked.length > 1 ? "requests" : "request"}:${list || " (details to be confirmed)"}\n\nWe will keep you informed as soon as there is further progress.\n\nWe appreciate your patience.\n\nBest regards,\nLS ELECTRIC Customer Support`;
};
function CareForm({ c }: { c: Customer; kind: CareKind }) {
  const [text, setText] = useState(""), [busy, setBusy] = useState(false);
  const [sel, setSel] = useState<string[]>(c.urgent.map((u) => u[0])); // 안내할 티켓(기본: 지연·임박 전부)
  const picked = c.urgent.filter((u) => sel.includes(u[0]));
  // BACKEND: 고객 대응 AI 초안 (진행 상황 안내)
  // 필요(제안): POST /customers/{id}/care-draft  { kind: "notice", ticket_ids?: string[], note?: string, language }
  //            → { draft_en, sources[] }   sources = 초안에 쓴 티켓·상태·전문부서 회신 등 근거 목록
  // 입력: ticket_ids = 화면에서 담당자가 체크한 티켓(기본은 지연·임박 전부), note = 담당자가 아는 사유·예상 시점(선택, 지금 화면은 받지 않는다).
  //       진행 상황은 티켓마다 다르므로 초안은 선택한 티켓 한 줄씩 그 티켓의 실제 상태·최근 처리 내용으로 써야 한다.
  // 규칙: 확인되지 않은 사유·일정·약속은 지어내지 않는다(아래 문구 틀도 시한을 약속하지 않는다). 사람이 검토·수정한 뒤 발송한다.
  // 지금: careDraft() 문구 틀에 고객 이름과 선택한 티켓(번호·제목·티켓 상태별 한 줄)을 채우는 시뮬레이션(버튼을 누르면 약 1초 뒤 채워진다).
  const write = () => { setBusy(true); setTimeout(() => { setText(careDraft(c, picked)); setBusy(false); }, 900); };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (busy || !text.trim()) return;
    addCareAction(c.id, "notice_draft", text, undefined, { ticketIds: picked.map((u) => u[0]), language: "en" });
    closeModal(); toast("안내문을 이 브라우저에 보관했습니다. 실제 발송은 하지 않았습니다.");
  };
  return (
    <form onSubmit={submit} className="grid gap-5">
      <p className="text-[15px] text-muted-foreground"><b className="font-semibold text-foreground">{c.name}</b> · {c.tier} · {SEGMENT_KO[c.seg] || c.seg}</p>
      {c.urgent.length > 0 && (
        <fieldset className="grid gap-1.5">
          <legend className="mb-1 text-sm text-muted-foreground">안내할 티켓 <span className="tabular-nums">{picked.length}/{c.urgent.length}</span></legend>
          {c.urgent.map((u) => (
            <label key={u[0]} className="flex cursor-pointer items-center gap-3 rounded-xl bg-muted/60 px-4 py-2.5 text-[15px]">
              <Checkbox disabled={busy} checked={sel.includes(u[0])} onCheckedChange={(v) => { setSel((s) => (v === true ? [...s, u[0]] : s.filter((x) => x !== u[0]))); setText(""); }} />
              <span className="min-w-0 flex-1"><span className="block truncate font-medium">{u[1]}</span><Mono className="text-xs text-muted-foreground">{u[0]}</Mono></span>
              <span className={cn("shrink-0 text-sm", isLate(u) ? "text-destructive" : "text-warning-ink")}>{lateText(u)}</span>
            </label>
          ))}
        </fieldset>
      )}
      <div className="grid gap-2.5">
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm text-muted-foreground">안내 메일 (영어 · 현재는 로컬 초안 보관)</span>
          <Button type="button" size="sm" className={AI_STYLE} disabled={busy || (c.urgent.length > 0 && picked.length === 0)} onClick={write}><AiMark className="size-3.5 text-white" />{busy ? "작성 중…" : text ? "다시 작성" : "AI 초안 작성"}</Button>
        </div>
        <Textarea aria-label="AI 초안" className="min-h-40 leading-relaxed" disabled={busy} value={text} onChange={(e) => setText(e.target.value)} placeholder={busy ? "고객 이력을 보고 초안을 쓰는 중입니다…" : "현재는 예시 문구를 만듭니다. 수정한 본문을 로컬에 보관할 수 있으며 실제 AI 생성·번역·발송은 연결 전입니다."} />
      </div>
      <Footer><Close label="취소" /><Button type="submit" disabled={busy || !text.trim()}>초안 보관</Button></Footer>
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
        <Button variant="outline" onClick={() => { closeModal(); nav("/tickets/" + r.ticket.id); }}>원본 티켓 열기</Button>
        {canReply && <Button onClick={() => openModal("expert-receive", { id: r.ticket.id, requestId: r.requestId })}>회신 등록</Button>}
      </Footer>
    </div>
  );
}

function FileInfo({ file, t }: { file: string; t?: Ticket }) {
  return (
    <>
      <p className="text-sm text-muted-foreground"><b className="text-foreground">{file}</b><br />{t?.files?.includes(file) ? "등록된 파일명입니다. 로컬 화면에서 파일 원본은 저장하지 않습니다." : "이 티켓에 연결된 첨부파일 항목입니다. 원본 파일은 아직 연결되지 않았습니다."}</p>
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
