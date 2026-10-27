// 문의 관리: 밑줄 탭(범위) + 검색 + 그룹별 한 줄 목록. 세부 필터와 여러 건 선택은 눌러야 보인다.
// 맨 오른쪽 "완료 문의" 탭에서는 처리 결과를 기록해 완료한 문의를 본다.
import { useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import { Button } from "@admin/components/ui/button";
import { Checkbox } from "@admin/components/ui/checkbox";
import { Input } from "@admin/components/ui/input";
import { NativeSelect, PageHeader, TicketRow, UnderlineTabs, useGo } from "@admin/components/admin/common";
import { CompletedTickets } from "@admin/pages/Knowledge";
import { bulkAssign } from "@admin/lib/actions";
import { canAssign, completedTickets, departmentRisk, people, scopeTickets } from "@admin/lib/logic";
import { openModal, setUi, tickets, ui, useStore } from "@admin/lib/store";
import { cn } from "@admin/lib/utils";
import type { Ticket } from "@admin/lib/types";

const SCOPES = ["내 담당", "전체"] as const;
const DONE_TAB = "완료 문의";
const Count = ({ label, n }: { label: string; n: number }) => <>{label}<span className="ml-1.5 text-sm font-normal tabular-nums text-muted-foreground">{n}</span></>;
const scoped = (scope: string) => scopeTickets(scope).filter((t) => (!ui.listOwner || t.owner === ui.listOwner));
function filtered() {
  const q = ui.query.toLowerCase();
  return scoped(ui.filter).filter(
    (t) =>
      (!q || [t.id, t.title, t.company, t.product, t.country].join(" ").toLowerCase().includes(q)) &&
      (!ui.status || t.status === ui.status) && (!ui.priority || t.priority === ui.priority) && (!ui.product || t.product === ui.product),
  );
}
/** 지금 봐야 할 것부터 묶는다: 위험 → 미배정 → 진행 중 → 완료. */
function groups(rows: Ticket[]) {
  const defs: [string, (t: Ticket) => boolean][] = [
    ["지금 위험", (t) => departmentRisk(t)],
    ["미배정", (t) => t.stage !== 5 && !t.owner],
    ["진행 중", (t) => t.stage !== 5],
    ["완료", () => true],
  ];
  const used = new Set<string>();
  return defs.map(([label, fn]) => {
    const list = rows.filter((t) => !used.has(t.id) && fn(t));
    list.forEach((t) => used.add(t.id));
    return { label, list };
  }).filter((g) => g.list.length);
}

export default function Tickets() {
  useStore();
  const go = useGo();
  const [showFilters, setShowFilters] = useState(false);
  const [selectMode, setSelectMode] = useState(false);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [bulkOwner, setBulkOwner] = useState(people[0].name);

  const doneTab = ui.filter === DONE_TAB;
  const rows = doneTab ? [] : filtered();
  const picked = [...sel].filter((id) => rows.some((t) => t.id === id));
  const activeFilters = [ui.status, ui.priority, ui.product].filter(Boolean).length;
  const toggle = (id: string, on: boolean) => setSel((s) => { const n = new Set(s); on ? n.add(id) : n.delete(id); return n; });
  const opt = (first: string, values: string[]) => [<option key="" value="">{first}</option>, ...values.map((v) => <option key={v}>{v}</option>)];
  const exitSelect = () => { setSelectMode(false); setSel(new Set()); };
  const hasFilter = ui.query || activeFilters || ui.listOwner;

  return (
    <>
      <PageHeader title="문의 관리" actions={<Button size="lg" onClick={() => openModal("new-ticket")}>+ 새 문의 등록</Button>}>
        <UnderlineTabs
          tabs={[...SCOPES.map((v) => [v, <Count key={v} label={v} n={scoped(v).filter((t) => v !== "내 담당" || t.stage !== 5).length} />] as const), [DONE_TAB, <Count key={DONE_TAB} label={DONE_TAB} n={completedTickets().length} />] as const]}
          value={ui.filter as string}
          onChange={(v) => { exitSelect(); setUi(v === DONE_TAB ? { filter: v, kquery: "" } : { filter: v }); }} />
      </PageHeader>
      {ui.ticketSync !== "ready" && <p role={ui.ticketSync === "error" ? "alert" : "status"} className="px-10 pb-4 text-sm text-muted-foreground">{ui.ticketSyncError || "서버 문의를 불러오는 중입니다."}{tickets.length > 0 && " 마지막 조회 정보를 표시합니다."}</p>}
      {doneTab ? <CompletedTickets /> : <>

      <div className="flex flex-wrap items-center gap-2 px-10 pb-4">
        <Input className="h-10 w-72 rounded-full bg-card px-4 shadow-card" aria-label="문의 검색" placeholder="번호·고객·제품 검색" value={ui.query} onChange={(e) => setUi({ query: e.target.value })} />
        <Button variant={showFilters || activeFilters ? "secondary" : "ghost"} aria-expanded={showFilters} onClick={() => setShowFilters((v) => !v)}>
          <SlidersHorizontal />필터{activeFilters > 0 && <span className="tabular-nums text-info"> {activeFilters}</span>}
        </Button>
        {ui.listOwner && <Button variant="secondary" onClick={() => setUi({ listOwner: "" })}>{ui.listOwner} ×</Button>}
        {canAssign && <Button className="ml-auto" variant={selectMode ? "secondary" : "ghost"} onClick={() => (selectMode ? exitSelect() : setSelectMode(true))}>{selectMode ? "선택 끝내기" : "여러 건 선택"}</Button>}
      </div>

      {showFilters && (
        <div className="mx-10 mb-4 flex flex-wrap items-center gap-2 rounded-2xl bg-card p-3 shadow-card">
          <NativeSelect className="rounded-full pl-4" aria-label="전체 상태" value={ui.status} onChange={(e) => setUi({ status: e.target.value })}>{opt("전체 상태", [...new Set(tickets.map((t) => t.status))])}</NativeSelect>
          <NativeSelect className="rounded-full pl-4" aria-label="우선순위" value={ui.priority} onChange={(e) => setUi({ priority: e.target.value })}>{opt("우선순위", ["P1", "P2", "P3", "P4"])}</NativeSelect>
          <NativeSelect className="rounded-full pl-4" aria-label="전체 제품" value={ui.product} onChange={(e) => setUi({ product: e.target.value })}>{opt("전체 제품", [...new Set(tickets.map((t) => t.product))])}</NativeSelect>
          {activeFilters > 0 && <Button size="sm" variant="ghost" onClick={() => setUi({ status: "", priority: "", product: "" })}>초기화</Button>}
        </div>
      )}

      {selectMode && (
        <div role="region" aria-label="일괄 작업" className="mx-10 mb-4 flex items-center gap-3 rounded-2xl bg-card px-5 py-3 text-sm shadow-card">
          <strong>{picked.length}건 선택</strong>
          <span className="text-muted-foreground">선택한 문의를</span>
          <NativeSelect className="rounded-full pl-4" aria-label="일괄 배정 담당자" value={bulkOwner} onChange={(e) => setBulkOwner(e.target.value)}>{people.map((p) => <option key={p.name}>{p.name}</option>)}</NativeSelect>
          <Button size="sm" disabled={!picked.length} onClick={() => { bulkAssign(picked, bulkOwner); exitSelect(); }}>에게 배정</Button>
        </div>
      )}

      <div className="grid gap-6 px-10 pb-12">
        {rows.length === 0 ? (
          <div className="grid justify-items-center gap-3 rounded-2xl bg-card px-6 py-16 text-center shadow-card">
            <strong className="font-medium">{ui.ticketSync === "loading" ? "문의 조회 중입니다." : ui.ticketSync === "error" ? "문의 조회를 완료하지 못했습니다." : "조건에 맞는 문의가 없습니다."}</strong>
            <p className="max-w-sm text-sm text-muted-foreground">{ui.ticketSync !== "ready" ? "서버 조회가 완료되면 문의 목록을 갱신합니다." : hasFilter ? "걸어 둔 검색·필터를 풀면 더 많은 문의가 보입니다." : "이 범위에는 처리할 문의가 없습니다. 전체 범위를 보거나 새 문의를 등록하세요."}</p>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setUi({ query: "", status: "", priority: "", product: "", listOwner: "", filter: "전체" })}>검색·필터 초기화</Button>
              <Button onClick={() => openModal("new-ticket")}>새 문의 등록</Button>
            </div>
          </div>
        ) : groups(rows).map((g) => (
          <section key={g.label} aria-label={g.label}>
            <h2 className="mb-2 px-1 text-sm text-muted-foreground">{g.label} <span className="tabular-nums">{g.list.length}</span></h2>
            <div className="divide-y overflow-hidden rounded-2xl bg-card shadow-card">
              {g.list.map((t) => (
                <div key={t.id} className={cn(sel.has(t.id) && "bg-accent/60")}>
                  <TicketRow t={t} onOpen={() => (selectMode ? t.stage !== 5 && toggle(t.id, !sel.has(t.id)) : go.ticket(t.id))}
                    lead={selectMode ? <span className="grid size-10 place-items-center">{t.stage !== 5 && <Checkbox aria-label={`${t.id} 선택`} checked={sel.has(t.id)} onCheckedChange={(v) => toggle(t.id, v === true)} onClick={(e) => e.stopPropagation()} />}</span> : undefined} />
                </div>
              ))}
            </div>
          </section>
        ))}
        {rows.length > 0 && <p className="px-1 text-xs text-muted-foreground">{rows.filter((t) => t.stage !== 5).length}건 진행 중{rows.some((t) => t.stage === 5) ? ` · 완료 ${rows.filter((t) => t.stage === 5).length}건` : ""}{selectMode ? " · 행을 눌러 선택하세요" : ""}</p>}
      </div>
      </>}
    </>
  );
}
