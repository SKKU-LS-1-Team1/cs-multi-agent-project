import { useEffect, useState, type ReactNode } from "react";
import { LoaderCircle } from "lucide-react";
import { api, type CopilotInsight, type CopilotStatement } from "../../../api/client";
import { Button } from "../ui/button";
import { requestFieldLabel } from "../../lib/investigation";
import type { Ticket } from "../../lib/types";

const pending = new Map<string, Promise<CopilotInsight>>();

export function useCopilot(t: Ticket) {
  const current = t.copilot as CopilotInsight | undefined;
  const key = current?.context_key;
  const [local, setLocal] = useState<CopilotInsight>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setLocal(undefined); setError(""); setBusy(false);
    if (!key || current?.reading || t.source !== "api") return;
    setBusy(true);
    const id = `${t.id}:${key}`;
    let request = pending.get(id);
    if (!request) {
      request = api.copilot(t.id);
      pending.set(id, request);
      void request.finally(() => pending.delete(id)).catch(() => {});
    }
    void request.then((data) => {
      if (!active) return;
      if (data.context_key === key && t.copilot?.context_key === key) { t.copilot = data; setLocal(data); }
      else setError("문의 내용이 변경되었습니다. 최신 내용으로 다시 확인해 주세요.");
    }).catch(() => { if (active) setError("AI 요약을 불러오지 못했습니다. 기존 업무는 계속할 수 있습니다."); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [t.id, key, attempt]);
  return { data: local?.context_key === key ? local : current, busy, error, retry: () => setAttempt((n) => n + 1) };
}

/** 원문 전체를 보여 주고, 근거로 인용한 부분(quote)에 형광펜을 칠한다. 원문에서 못 찾으면 인용문만 형광펜으로 보인다. */
function Highlighted({ text, quotes }: { text: string; quotes: string[] }) {
  const spans = quotes.map((q) => ({ at: text.indexOf(q), len: q.length })).filter((x) => x.at >= 0 && x.len > 0).sort((x, y) => x.at - y.at);
  const merged: { at: number; end: number }[] = [];
  for (const { at, len } of spans) {
    const last = merged[merged.length - 1];
    if (last && at <= last.end) last.end = Math.max(last.end, at + len); else merged.push({ at, end: at + len });
  }
  if (!merged.length) return <mark className="rounded-sm bg-yellow-200/80 px-0.5 text-foreground [box-decoration-break:clone]">{quotes.join("\n")}</mark>;
  const parts: ReactNode[] = []; let pos = 0;
  merged.forEach(({ at, end }, i) => {
    if (at > pos) parts.push(text.slice(pos, at));
    parts.push(<mark key={i} className="rounded-sm bg-yellow-200/80 px-0.5 text-foreground [box-decoration-break:clone]">{text.slice(at, end)}</mark>);
    pos = end;
  });
  if (pos < text.length) parts.push(text.slice(pos));
  return <>{parts}</>;
}

/** Keep the claim visible; collect its exact supporting quotations at the section boundary. */
export function EvidenceGroup({ statements, sources, label = "근거 원문 보기" }: {
  statements: CopilotStatement[]; sources: CopilotInsight["sources"]; label?: string;
}) {
  const refs = new Map<string, { quotes: Set<string>; claims: Set<string> }>();
  for (const statement of statements) for (const ref of statement.references) {
    const item = refs.get(ref.source_id) || { quotes: new Set<string>(), claims: new Set<string>() };
    item.quotes.add(ref.quote); item.claims.add(statement.text); refs.set(ref.source_id, item);
  }
  if (!refs.size) return null;
  return <details className="mt-3 text-sm text-muted-foreground">
    <summary className="cursor-pointer rounded-sm py-1 focus-visible:outline-2 focus-visible:outline-primary">{label} <span className="ml-1 text-xs">{refs.size}건</span></summary>
    <div className="mt-3 grid gap-4 border-l-2 border-primary/20 pl-3">
      {[...refs.entries()].map(([id, ref]) => <div key={id} className="min-w-0">
        <p className="font-semibold text-foreground">{sources[id]?.label || "원문"}</p>
        <ul className="mt-1 grid gap-1 text-xs">{[...ref.claims].map((text) => <li key={text} className="break-words">관련 설명: {text}</li>)}</ul>
        <blockquote className="mt-2 whitespace-pre-wrap break-words leading-relaxed"><Highlighted text={sources[id]?.text || ""} quotes={[...ref.quotes]} /></blockquote>
      </div>)}
    </div>
  </details>;
}

export function Statement({ value, sources, showEvidence = true }: {
  value: CopilotStatement; sources: CopilotInsight["sources"]; showEvidence?: boolean;
}) {
  return <div className="min-w-0 break-words text-[15px] leading-[1.7]">
    <p>{value.text}</p>
    {showEvidence && <EvidenceGroup statements={[value]} sources={sources} />}
  </div>;
}

export function ReadingSummary({ data, showUnresolved = true, omitChangedFields = [] }: { data: CopilotInsight; showUnresolved?: boolean; omitChangedFields?: string[] }) {
  if (!data.reading) return null;
  const reading = data.reading;
  const changes = data.changes.filter((item) => !omitChangedFields.includes(item.field));
  const unresolved = showUnresolved ? reading.unresolved : [];
  return <div className="grid gap-3">
    <div className="rounded-2xl bg-[#026bb4]/[0.06] p-4">
      <h4 className="mb-2 text-sm font-semibold">고객이 요청한 내용</h4>
      <Statement value={reading.request} sources={data.sources} showEvidence={false} />
    </div>
    {!!changes.length && <section aria-label="변경된 정보" className="rounded-2xl bg-muted/60 p-4 text-sm">
      <h4 className="mb-2 font-semibold">이전 확인 이후 변경</h4>
      <ul className="grid gap-2">{changes.map((item) => <li key={item.field} className="break-words"><span className="font-medium">{item.label}</span><p className="mt-0.5"><span className="text-muted-foreground">{String(item.before ?? "미확인")}</span> → {String(item.after ?? "미확인")}</p></li>)}</ul>
    </section>}
    {!!reading.confirmed.length && <section aria-label="확인된 정보" className="rounded-2xl bg-success/[0.06] p-4">
      <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold">확인된 정보<span className="text-xs font-normal text-muted-foreground">{reading.confirmed.length}건</span></h4>
      <ul className="grid gap-2">{reading.confirmed.map((item, i) => <li key={i}><Statement value={item} sources={data.sources} showEvidence={false} /></li>)}</ul>
    </section>}
    {!!unresolved.length && <section aria-label="추가 확인할 내용" className="rounded-2xl bg-warning/[0.10] p-4">
      <h4 className="mb-2 text-sm font-semibold">추가 확인할 내용</h4>
      <ul className="grid gap-2">{unresolved.map((item, i) => <li key={i}><Statement value={item} sources={data.sources} showEvidence={false} /></li>)}</ul>
    </section>}
    <EvidenceGroup statements={[reading.request, ...reading.confirmed, ...unresolved]} sources={data.sources} label="요약의 근거 원문 보기" />
  </div>;
}

export function RequestChecklist({ rows, data }: { rows: CopilotInsight["request_plan"]; data?: CopilotInsight }) {
  const reasons = data?.workflow?.mode === "customer_request" ? data.reading?.request_reasons || [] : [];
  const usedReasons = reasons.filter((item) => rows.some((row) => row.field === item.field));
  return <div className="rounded-2xl bg-warning/[0.10] p-4">
    <ul className="grid gap-4">{rows.map((row) => {
      const reason = usedReasons.find((item) => item.field === row.field);
      return <li key={row.field} className="min-w-0">
        <div className="flex items-start justify-between gap-3">
          <h4 className="min-w-0 break-words text-[15px] font-semibold">{requestFieldLabel(row.field, row.label)}</h4>
          <span className="shrink-0 rounded-full bg-background/80 px-2 py-0.5 text-xs text-warning-ink">{row.status === "clarify" ? "재확인" : "미확인"}</span>
        </div>
        <p className="mt-1 break-words text-sm leading-relaxed">{reason?.text || row.reason}</p>
      </li>;
    })}</ul>
    {data && <EvidenceGroup statements={usedReasons} sources={data.sources} label="요청 이유의 근거 원문 보기" />}
  </div>;
}

export function InsightStatus({ busy, error, retry }: { busy: boolean; error: string; retry: () => void }) {
  if (busy) return <p role="status" className="mt-3 flex items-center gap-2 text-sm text-muted-foreground"><LoaderCircle className="size-4 animate-spin" />원문과 확인값을 정리하고 있습니다.</p>;
  if (!error) return null;
  return <div role="status" className="mt-3 text-sm text-muted-foreground"><p>{error}</p><Button variant="ghost" size="sm" onClick={retry}>다시 확인</Button></div>;
}

export function CaseComparisons({ data, showHeading = true }: { data: CopilotInsight; showHeading?: boolean }) {
  if (!data.reading?.cases.length) return null;
  return <section aria-label={showHeading ? "비슷한 과거 문의" : undefined} className="min-w-0">
    {showHeading && <h4 className="text-sm font-semibold">비슷한 과거 문의</h4>}
    <p className="mb-4 mt-1 text-sm leading-relaxed text-muted-foreground">과거 문의와 비교한 내용입니다. 증상이 비슷해도 원인과 해결 방법은 다를 수 있습니다.</p>
    <div className="grid gap-4">{data.reading.cases.map((item, index) => <article key={item.case_id} className="min-w-0 rounded-2xl bg-muted/60 p-4">
      <header className="mb-4 grid gap-1 border-b border-border pb-3">
        <h5 className="text-[15px] font-semibold">과거 문의 {index + 1}</h5>
        <span className="break-all text-xs text-muted-foreground">사례 번호 · {data.sources[item.case_id]?.label || item.case_id}</span>
      </header>
      {([["현재 문의와 비슷한 점", item.matches], ["현재 문의와 다른 점", item.differences], ["추가 확인이 필요한 정보", item.unknowns]] as const).map(([label, statements]) => statements.length > 0 && <section key={label} aria-label={label} className="mb-4">
        <h6 className="mb-1 text-sm font-semibold">{label}</h6>
        <ul className="grid gap-2">{statements.map((value, i) => <li key={i}><Statement value={value} sources={data.sources} showEvidence={false} /></li>)}</ul>
      </section>)}
      <section aria-label="이 사례를 참고할 때" className="border-t border-border pt-3">
        <h6 className="mb-1 text-sm font-semibold">이 사례를 참고할 때</h6>
        <Statement value={item.use_limit} sources={data.sources} showEvidence={false} />
      </section>
      <EvidenceGroup statements={[...item.matches, ...item.differences, ...item.unknowns, item.use_limit]} sources={data.sources} label="이 사례의 근거 원문 보기" />
    </article>)}</div>
  </section>;
}
