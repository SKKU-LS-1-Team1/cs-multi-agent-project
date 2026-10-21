// 티켓 관리: 밑줄 탭(범위) + 검색 + 그룹별 한 줄 목록. 세부 필터와 여러 건 선택은 눌러야 보인다.
import { useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import { Button } from "@admin/components/ui/button";
import { Checkbox } from "@admin/components/ui/checkbox";
import { Input } from "@admin/components/ui/input";
import { NativeSelect, PageHeader, TicketRow, UnderlineTabs, useGo } from "@admin/components/admin/common";
import { bulkAssign } from "@admin/lib/actions";
import { departmentNames, departmentRisk, people, scopeTickets, ticketDepartment } from "@admin/lib/logic";
import { openModal, setUi, tickets, ui, useStore } from "@admin/lib/store";
import { cn } from "@admin/lib/utils";
import type { Ticket } from "@admin/lib/types";

const SCOPES = ["내 담당", "미배정", "전체", "SLA 위험"] as const;
const scoped = (scope: string) => scopeTickets(scope).filter((t) => (!ui.listDepartment || ticketDepartment(t) === ui.listDepartment) && (!ui.listOwner || t.owner === ui.listOwner));
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

  const rows = filtered();
  const picked = [...sel].filter((id) => rows.some((t) => t.id === id));
  const activeFilters = [ui.status, ui.priority, ui.product, ui.listDepartment].filter(Boolean).length;
  const toggle = (id: string, on: boolean) => setSel((s) => { const n = new Set(s); on ? n.add(id) : n.delete(id); return n; });
  const opt = (first: string, values: string[]) => [<option key="" value="">{first}</option>, ...values.map((v) => <option key={v}>{v}</option>)];
  const exitSelect = () => { setSelectMode(false); setSel(new Set()); };
  const hasFilter = ui.query || activeFilters || ui.listOwner;

  return (
    <>
      <PageHeader title="티켓 관리" actions={<Button size="lg" onClick={() => openModal("new-ticket")}>+ 새 티켓 등록</Button>}>
        <UnderlineTabs tabs={SCOPES.map((v) => [v, `${v}  ${scoped(v).length}`] as const)} value={ui.filter as (typeof SCOPES)[number]} onChange={(v) => { exitSelect(); setUi({ filter: v }); }} />
      </PageHeader>

      <div className="flex flex-wrap items-center gap-2 px-10 pb-4">
        <Input className="h-10 w-72 rounded-full bg-card px-4 shadow-card" aria-label="티켓 검색" placeholder="번호·고객·제품 검색" value={ui.query} onChange={(e) => setUi({ query: e.target.value })} />
        <Button variant={showFilters || activeFilters ? "secondary" : "ghost"} aria-expanded={showFilters} onClick={() => setShowFilters((v) => !v)}>
          <SlidersHorizontal />필터{activeFilters > 0 && <span className="tabular-nums text-info"> {activeFilters}</span>}
        </Button>
        {ui.listOwner && <Button variant="secondary" onClick={() => setUi({ listOwner: "" })}>{ui.listOwner} ×</Button>}
        <Button className="ml-auto" variant={selectMode ? "secondary" : "ghost"} onClick={() => (selectMode ? exitSelect() : setSelectMode(true))}>{selectMode ? "선택 끝내기" : "여러 건 선택"}</Button>
      </div>

      {showFilters && (
        <div className="mx-10 mb-4 flex flex-wrap items-center gap-2 rounded-2xl bg-card p-3 shadow-card">
          <NativeSelect className="rounded-full pl-4" aria-label="전체 상태" value={ui.status} onChange={(e) => setUi({ status: e.target.value })}>{opt("전체 상태", [...new Set(tickets.map((t) => t.status))])}</NativeSelect>
          <NativeSelect className="rounded-full pl-4" aria-label="우선순위" value={ui.priority} onChange={(e) => setUi({ priority: e.target.value })}>{opt("우선순위", ["P2", "P3", "P4"])}</NativeSelect>
          <NativeSelect className="rounded-full pl-4" aria-label="전체 제품" value={ui.product} onChange={(e) => setUi({ product: e.target.value })}>{opt("전체 제품", [...new Set(tickets.map((t) => t.product))])}</NativeSelect>
          <NativeSelect className="rounded-full pl-4" aria-label="전체 부서" value={ui.listDepartment} onChange={(e) => setUi({ listDepartment: e.target.value })}>{opt("전체 부서", departmentNames())}</NativeSelect>
          {activeFilters > 0 && <Button size="sm" variant="ghost" onClick={() => setUi({ status: "", priority: "", product: "", listDepartment: "" })}>초기화</Button>}
        </div>
      )}

      {selectMode && (
        <div role="region" aria-label="일괄 작업" className="mx-10 mb-4 flex items-center gap-3 rounded-2xl bg-card px-5 py-3 text-sm shadow-card">
          <strong>{picked.length}건 선택</strong>
          <span className="text-muted-foreground">선택한 티켓을</span>
          <NativeSelect className="rounded-full pl-4" aria-label="일괄 배정 담당자" value={bulkOwner} onChange={(e) => setBulkOwner(e.target.value)}>{people.map((p) => <option key={p.name}>{p.name}</option>)}</NativeSelect>
          <Button size="sm" disabled={!picked.length} onClick={() => { bulkAssign(picked, bulkOwner); exitSelect(); }}>에게 배정</Button>
        </div>
      )}

      <div className="grid gap-6 px-10 pb-12">
        {rows.length === 0 ? (
          <div className="grid justify-items-center gap-3 rounded-2xl bg-card px-6 py-16 text-center shadow-card">
            <strong className="font-medium">조건에 맞는 티켓이 없습니다.</strong>
            <p className="max-w-sm text-sm text-muted-foreground">{hasFilter ? "걸어 둔 검색·필터를 풀면 더 많은 티켓이 보입니다." : "이 범위에는 처리할 티켓이 없습니다. 전체 범위를 보거나 새 티켓을 등록하세요."}</p>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setUi({ query: "", status: "", priority: "", product: "", listDepartment: "", listOwner: "", filter: "전체" })}>검색·필터 초기화</Button>
              <Button onClick={() => openModal("new-ticket")}>새 티켓 등록</Button>
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
        {rows.length > 0 && <p className="px-1 text-xs text-muted-foreground">{rows.length}개 티켓{selectMode ? " · 행을 눌러 선택하세요" : ""}</p>}
      </div>
    </>
  );
}
