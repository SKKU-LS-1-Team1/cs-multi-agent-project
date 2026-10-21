// 전문부서 협업: ① 핵심 3수치 ② 부서 칩 ③ 요청 상태 보드(회신 대기 → 회신 수신).
// 카드를 "회신 수신"으로 끌어 놓으면 회신 등록 창이 열린다. 카드를 누르면 요청·회신 상세가 열린다.
import { useState } from "react";
import { DndContext, DragOverlay, PointerSensor, pointerWithin, useDraggable, useDroppable, useSensor, useSensors, type DragEndEvent, type DragStartEvent } from "@dnd-kit/core";
import { AlarmClock, CheckCheck, GripVertical, Hourglass } from "lucide-react";
import { Button } from "@admin/components/ui/button";
import { ActionTile, SlaTag, Tag, useGo } from "@admin/components/admin/common";
import { departmentRank, departmentReviewRows, departmentRisk, referralDepartments, referralRows, slaMinutes } from "@admin/lib/logic";
import { openModal, setUi, ui, useStore } from "@admin/lib/store";
import { cn } from "@admin/lib/utils";

type Row = ReturnType<typeof referralRows>[number];
const when = (r: Row) => (r.when ? new Date(r.when).toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : r.time ? r.time : "요청일 미기록");
const byUrgency = (a: Row, b: Row) => departmentRank(a.ticket) - departmentRank(b.ticket) || (slaMinutes(a.ticket) ?? Infinity) - (slaMinutes(b.ticket) ?? Infinity);

export default function Collab() {
  useStore();
  const go = useGo();
  const [riskOnly, setRiskOnly] = useState(false);
  const [active, setActive] = useState<Row | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  const names = referralDepartments();
  const selected = ui.department !== "전체 부서" && !names.includes(ui.department) ? "전체 부서" : ui.department;
  const requests = selected === "전체 부서" ? referralRows() : departmentReviewRows(selected);
  const pendingAll = requests.filter((r) => !r.response), answered = requests.filter((r) => r.response);
  const riskCount = new Set(pendingAll.filter((r) => departmentRisk(r.ticket)).map((r) => r.ticket.id)).size;
  const pending = pendingAll.filter((r) => !riskOnly || departmentRisk(r.ticket)).sort(byUrgency);
  const oldest = [...pendingAll].sort(byUrgency)[0];

  const open = (r: Row) => (r.event ? openModal("department-review", { key: r.key }) : go.ticket(r.ticket.id));
  const reply = (r: Row) => openModal("expert-receive", { id: r.ticket.id, requestId: r.requestId || undefined });
  const canReply = (r: Row) => !r.response && r.ticket.stage !== 5;

  const onStart = (e: DragStartEvent) => setActive(requests.find((r) => r.key === e.active.id) || null);
  const onEnd = (e: DragEndEvent) => {
    const r = active; setActive(null);
    if (r && e.over?.id === "received" && canReply(r)) reply(r);
  };

  return (
    <div className="grid gap-7 px-10 pb-12">
      <section aria-label="협업 요청 현황" className="grid grid-cols-3 gap-4">
        <ActionTile icon={Hourglass} label="회신 대기" sub={oldest ? `${pendingAll.length}건 · 가장 급한 것: ${oldest.ticket.title}` : "대기 중인 요청 없음"} onClick={() => setRiskOnly(false)} />
        <ActionTile icon={AlarmClock} label="SLA 위험 티켓" sub={riskCount ? (riskOnly ? `${riskCount}건 · 위험만 보는 중 (다시 누르면 해제)` : `${riskCount}건 · 눌러서 위험만 보기`) : "위험 티켓 없음"} tone={riskCount ? "red" : ""} onClick={() => setRiskOnly(!riskOnly)} />
        <ActionTile icon={CheckCheck} label="회신 수신" sub={`${answered.length}건 · 전체 요청 ${requests.length}건 중`} onClick={() => setRiskOnly(false)} />
      </section>

      <nav aria-label="부서 선택" className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground">부서</span>
        {["전체 부서", ...names].map((n) => {
          const rows = n === "전체 부서" ? referralRows() : departmentReviewRows(n), wait = rows.filter((r) => !r.response).length;
          return (
            <Button key={n} size="sm" variant={selected === n ? "default" : "outline"} onClick={() => setUi({ department: n })}>
              {n} <span className={cn("tabular-nums", selected === n ? "opacity-80" : wait ? "font-semibold text-info" : "opacity-60")}>{wait}</span>
            </Button>
          );
        })}
        {riskOnly && <Button size="sm" variant="secondary" onClick={() => setRiskOnly(false)}>SLA 위험만 보는 중 ×</Button>}
      </nav>

      <DndContext sensors={sensors} collisionDetection={pointerWithin} onDragStart={onStart} onDragEnd={onEnd} onDragCancel={() => setActive(null)}>
        <div className="grid grid-cols-2 gap-4">
          <Lane id="waiting" title="회신 대기" count={pending.length} hint="전문부서의 회신을 기다리는 요청" dragging={!!active}>
            {pending.map((r) => <RequestCard key={r.key} r={r} draggable={canReply(r)} onOpen={() => open(r)} />)}
            {!pending.length && <Empty>{riskOnly ? "SLA 위험 요청이 없습니다." : "대기 중인 요청이 없습니다."}</Empty>}
          </Lane>
          <Lane id="received" title="회신 수신" count={answered.length} hint={active ? "여기에 놓으면 회신 등록 창이 열립니다" : "회신이 등록된 요청"} dragging={!!active} accept={!!active && canReply(active)}>
            {answered.map((r) => <RequestCard key={r.key} r={r} onOpen={() => open(r)} />)}
            {!answered.length && <Empty>아직 수신한 회신이 없습니다.</Empty>}
          </Lane>
        </div>
        <DragOverlay dropAnimation={null}>{active && <RequestCard r={active} overlay />}</DragOverlay>
      </DndContext>
    </div>
  );
}

const Empty = ({ children }: { children: React.ReactNode }) => <p className="rounded-xl bg-card/60 py-10 text-center text-sm text-muted-foreground">{children}</p>;

function Lane({ id, title, count, hint, dragging, accept, children }: { id: string; title: string; count: number; hint: string; dragging: boolean; accept?: boolean; children: React.ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id });
  return (
    <section ref={setNodeRef} aria-label={`${title} 열`}
      className={cn("flex min-h-72 flex-col gap-3 rounded-2xl bg-muted/70 p-3 transition-colors",
        id === "received" && dragging && (accept ? "ring-1 ring-success/60 bg-success/5" : "opacity-50"),
        id === "received" && isOver && accept && "ring-2 ring-success bg-success/10")}>
      <header className="flex items-baseline justify-between gap-3 px-1">
        <div><h3 className="font-semibold">{title}</h3><p className={cn("text-xs text-muted-foreground", dragging && id === "received" && accept && "font-medium text-success")}>{hint}</p></div>
        <span className="rounded bg-card px-1.5 py-0.5 text-xs tabular-nums ring-1 ring-border">{count}</span>
      </header>
      <div className="grid content-start gap-2">{children}</div>
    </section>
  );
}

function RequestCard({ r, draggable, onOpen, overlay }: { r: Row; draggable?: boolean; onOpen?: () => void; overlay?: boolean }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: r.key, disabled: !draggable || overlay });
  return (
    <div ref={overlay ? undefined : setNodeRef} className={cn(isDragging && "opacity-30")}>
      <article className={cn("grid gap-2 rounded-xl bg-card p-3.5 text-sm shadow-card", overlay && "w-[320px] shadow-lg ring-1 ring-ring", departmentRisk(r.ticket) && !r.response && "border-destructive/40")}>
        <div className="flex items-start gap-1.5">
          {draggable ? (
            <button type="button" aria-label="끌어서 회신 등록" className="mt-0.5 cursor-grab touch-none text-muted-foreground hover:text-foreground active:cursor-grabbing" {...attributes} {...listeners}><GripVertical className="size-4" /></button>
          ) : <span className="w-4" />}
          <button type="button" onClick={onOpen} className="min-w-0 flex-1 text-left font-semibold leading-snug hover:underline">{r.ticket.title}</button>
          <Tag tone={r.response ? "green" : ""}>{r.status}</Tag>
        </div>
        <div className="flex items-center justify-between pl-[22px] text-xs text-muted-foreground">
          <span className="truncate">{r.ticket.id} · {r.source || "요청 부서 미기록"} → {r.target || "대상 부서 미기록"}</span>
          <span className="shrink-0 pl-2">{when(r)}</span>
        </div>
        <div className="flex items-center justify-between pl-[22px]">
          <div className="flex items-center gap-2 text-xs text-muted-foreground"><span>원본 SLA</span><SlaTag t={r.ticket} /></div>
          <span className="text-xs text-muted-foreground">{r.event?.actor || r.ticket.owner || "담당 미기록"}</span>
        </div>
      </article>
    </div>
  );
}
