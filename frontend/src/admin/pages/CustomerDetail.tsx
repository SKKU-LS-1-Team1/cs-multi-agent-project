// 고객 상세: 왼쪽 = 지연·임박 티켓(안내 버튼) + 내부 메모, 오른쪽 = 활동(문의와 대응을 한 흐름으로). 중점 관리 직접 지정·해제.
import { useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { Button } from "@admin/components/ui/button";
import { Textarea } from "@admin/components/ui/textarea";
import { ActionButton, CareButtons } from "@admin/components/admin/CareButtons";
import { CareTag, Ids, Mono, Tag, TierTag, useGo } from "@admin/components/admin/common";
import { addNote, careStatus, recordOf, setPinned, useCare } from "@admin/lib/care";
import { CATEGORY_KO, FAMILY_KO, flag, focusOf, isLate, lateText, PRIORITY_KO, SEGMENT_KO, STATUS_KO, useCustomers, type Customer } from "@admin/lib/customers";
import { findTicket, tickets, useStore } from "@admin/lib/store";
import { INQUIRY_ISO } from "@admin/lib/logic";
import { cn } from "@admin/lib/utils";

const Card = ({ title, aside, children, className }: { title: string; aside?: React.ReactNode; children: React.ReactNode; className?: string }) => (
  <section aria-label={title} className={cn("rounded-2xl bg-card p-7 shadow-card", className)}>
    <div className="mb-5 flex items-center justify-between gap-3"><h2 className="text-lg font-semibold">{title}</h2>{aside}</div>
    {children}
  </section>
);
const md = (iso: string) => iso.slice(5, 10).replace("-", ".");
const hm = (iso: string) => new Date(iso).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false });
/** 타임라인 한 줄. 문의(회색)와 대응(남색)을 라벨로 구분한다. */
type Item = { key: string; at: string; type: "문의" | "대응"; title: React.ReactNode; sub: React.ReactNode; onOpen?: () => void; tags?: React.ReactNode };

export default function CustomerDetail() {
  useStore();
  const { customerId } = useParams();
  const go = useGo();
  const rows = useCustomers();
  const care = useCare();
  const [note, setNote] = useState("");
  if (!rows) return <p className="px-10 py-16 text-center text-sm text-muted-foreground">불러오는 중입니다.</p>;
  const c: Customer | undefined = rows.find((x) => x.id === customerId);
  if (!c) return <Navigate to="/customers" replace />;
  const rec = recordOf(c.id), status = careStatus(care[c.id]), f = focusOf(c, care[c.id]);
  const linked = tickets.filter((t) => t.customerId === c.id); // 이 시스템에서 열 수 있는 티켓

  // 활동: 문의(이 시스템의 티켓 + 학습 데이터의 최근 문의)와 대응(안내·종결)을 날짜 내림차순으로 한 흐름에 섞는다.
  const items: Item[] = [
    ...rec.actions.map((a): Item => ({ key: a.id, at: a.at, type: "대응", title: <Ids text={a.text} />, sub: <>{a.by}</> })),
    ...linked.map((t): Item => ({ key: t.id, at: INQUIRY_ISO, type: "문의", title: t.title, onOpen: () => go.ticket(t.id), sub: <><Mono>{t.id}</Mono> · {t.product}</>, tags: <><Tag tone={t.priority === "P1" ? "red" : t.priority === "P2" ? "amber" : ""}>{t.priority} {PRIORITY_KO[t.priority]}</Tag><span className={cn("text-sm", t.stage !== 5 && "font-medium")}>{t.stage === 5 ? "완료" : t.status}</span></> })),
    ...c.t.map(([id, date, subject, cat, fam, pri, st, sla]): Item => ({ key: id, at: date, type: "문의", title: subject, onOpen: findTicket(id) ? () => go.ticket(id) : undefined, sub: <>{CATEGORY_KO[cat] || cat} · {FAMILY_KO[fam] || fam}</>,
      tags: <><Tag tone={pri === "P1" ? "red" : pri === "P2" ? "amber" : ""}>{pri} {PRIORITY_KO[pri]}</Tag>{sla === "BREACHED" && <Tag tone="red">SLA 초과</Tag>}<span className={cn("text-sm", ["IN_PROGRESS", "ESCALATED", "NEW", "WAITING_CUSTOMER"].includes(st) && "font-medium")}>{STATUS_KO[st] || st}</span></> })),
  ].sort((a, b) => b.at.localeCompare(a.at));

  return (
    <div className="grid gap-7 px-10 pb-14 pt-10">
      <button onClick={() => go.to("/customers")} className="w-fit text-sm text-info hover:underline">‹ 고객 관리</button>
      <header className="flex items-center gap-5">
        <span title={c.cn} aria-label={c.cn} className="grid size-[72px] place-items-center rounded-full bg-muted text-4xl">{flag(c.c)}</span>
        <div className="grid gap-2">
          <h1 className="flex items-center gap-3 text-[32px] font-bold tracking-tight">{c.name}<TierTag tier={c.tier} className="h-6 text-sm" /></h1>
          <p className="text-muted-foreground">{SEGMENT_KO[c.seg] || c.seg} · {c.since}년부터 거래 · 12개월 문의 {c.n}건 · 기한 넘긴 적 {c.breach}회{c.fam[0][1] >= 4 ? ` · ${FAMILY_KO[c.fam[0][0]] || c.fam[0][0]} ${c.fam[0][1]}회 반복 문의` : ""}</p>
        </div>
        <div className="ml-auto flex items-center gap-3">
          {rec.actions.length > 0 && <CareTag status={status} />}
          {rec.pinned ? <Button variant="outline" onClick={() => setPinned(c.id, false)}>중점 관리 해제</Button> : <Button variant="outline" onClick={() => setPinned(c.id, true)}>{f ? "중점 관리 고정" : "중점 관리 지정"}</Button>}
        </div>
      </header>

      <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)] items-start gap-6">
        <div className="grid gap-6">
          {c.urgent.length > 0 && (
            <Card title="지연·임박 티켓" aside={<ActionButton c={c} kind="notice" />}>
              <ul className="-my-2 divide-y">
                {c.urgent.map((u) => (
                  <li key={u[0]} className="flex items-center justify-between gap-4 py-3">
                    <span className="min-w-0"><span className="block truncate font-medium">{u[1]}</span><Mono className="text-xs text-muted-foreground">{u[0]}</Mono></span>
                    <span className={cn("shrink-0 text-sm font-medium", isLate(u) ? "text-destructive" : "text-warning-ink")}>{lateText(u)}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
          {/* BACKEND: 내부 메모 — GET/POST /customers/{id}/notes (lib/care.ts 의 addNote 참고). 고객에게 보이지 않는다. */}
          <Card title="내부 메모" aside={<small className="text-muted-foreground">고객에게 보이지 않습니다</small>}>
            <form className="grid gap-2.5" onSubmit={(e) => { e.preventDefault(); if (note.trim()) { addNote(c.id, note); setNote(""); } }}>
              <Textarea aria-label="내부 메모" className="min-h-20 leading-relaxed" placeholder="상담원끼리 공유할 이 고객의 특이사항" value={note} onChange={(e) => setNote(e.target.value)} />
              <Button type="submit" size="sm" className="w-fit" disabled={!note.trim()}>메모 남기기</Button>
            </form>
            {(rec.notes || []).length > 0 && (
              <ul className="mt-5 grid gap-4 border-t pt-5">
                {rec.notes!.map((n) => <li key={n.id} className="grid gap-0.5"><p className="whitespace-pre-line text-[15px] leading-relaxed">{n.text}</p><small className="text-muted-foreground">{md(n.at)} {hm(n.at)} · {n.by}</small></li>)}
              </ul>
            )}
          </Card>
        </div>

        <Card title="활동" aside={rec.actions.length > 0 ? <CareButtons c={c} /> : undefined} className="overflow-hidden p-0 [&>div:first-child]:px-7 [&>div:first-child]:pt-7">
          <ol className="divide-y">
            {items.map((it) => {
              const Row = it.onOpen ? "button" : "div";
              return (
                <li key={it.key}>
                  <Row {...(it.onOpen ? { onClick: it.onOpen } : {})} className={cn("grid w-full grid-cols-[48px_auto_minmax(0,1fr)_auto] items-start gap-3.5 px-7 py-4 text-left", it.onOpen && "transition-colors hover:bg-muted/70")}>
                    <span className="pt-0.5 text-sm tabular-nums text-muted-foreground">{md(it.at)}</span>
                    <span className={cn("inline-flex h-6 items-center rounded-full px-2.5 text-xs font-medium", it.type === "대응" ? "bg-[#003377]/10 text-[#003377]" : "bg-muted text-foreground/70")}>{it.type}</span>
                    <span className="grid min-w-0 gap-1"><span className="font-medium leading-snug">{it.title}</span><span className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">{it.sub}{it.tags}</span></span>
                    {it.onOpen ? <ChevronRight className="mt-1 size-4 text-muted-foreground" aria-hidden /> : <span />}
                  </Row>
                </li>
              );
            })}
          </ol>
        </Card>
      </div>
    </div>
  );
}
