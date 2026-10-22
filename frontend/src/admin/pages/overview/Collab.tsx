// 전문부서 협업: 회신 대기 → 회신 받음 두 칸. 카드에는 제목·부서·SLA·버튼만 둔다.
// 카드를 "회신 받음" 칸으로 끌어 놓아도 회신 등록 창이 열린다(눈에 보이는 손잡이는 두지 않는다).
import { useState } from "react";
import { DndContext, DragOverlay, PointerSensor, pointerWithin, useDraggable, useDroppable, useSensor, useSensors, type DragEndEvent, type DragStartEvent } from "@dnd-kit/core";
import { ArrowRight } from "lucide-react";
import { Button } from "@admin/components/ui/button";
import { PageHeader, SlaTag, useGo } from "@admin/components/admin/common";
import { departmentRank, departmentReviewRows, referralDepartments, referralRows, slaMinutes } from "@admin/lib/logic";
import { openModal, setUi, ui, useStore } from "@admin/lib/store";
import { cn } from "@admin/lib/utils";

type Row = ReturnType<typeof referralRows>[number];
const byUrgency = (a: Row, b: Row) => departmentRank(a.ticket) - departmentRank(b.ticket) || (slaMinutes(a.ticket) ?? Infinity) - (slaMinutes(b.ticket) ?? Infinity);

export default function Collab({ tabs }: { tabs: React.ReactNode }) {
  useStore();
  const go = useGo();
  const [active, setActive] = useState<Row | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  const names = referralDepartments();
  const selected = ui.department !== "전체 부서" && !names.includes(ui.department) ? "전체 부서" : ui.department;
  const requests = selected === "전체 부서" ? referralRows() : departmentReviewRows(selected);
  const pending = requests.filter((r) => !r.response).sort(byUrgency), answered = requests.filter((r) => r.response);

  const open = (r: Row) => (r.event ? openModal("department-review", { key: r.key }) : go.ticket(r.ticket.id));
  const reply = (r: Row) => openModal("expert-receive", { id: r.ticket.id, requestId: r.requestId || undefined });
  const canReply = (r: Row) => !r.response && r.ticket.stage !== 5;

  const onStart = (e: DragStartEvent) => setActive(requests.find((r) => r.key === e.active.id) || null);
  const onEnd = (e: DragEndEvent) => {
    const r = active; setActive(null);
    if (r && e.over?.id === "received" && canReply(r)) reply(r);
  };

  return (
    <>
      <PageHeader title="전문부서 협업 현황">{tabs}</PageHeader>
      <DndContext sensors={sensors} collisionDetection={pointerWithin} onDragStart={onStart} onDragEnd={onEnd} onDragCancel={() => setActive(null)}>
        <div className="grid grid-cols-[minmax(0,1fr)_340px] items-start gap-5 px-10 pb-12">
          <div className="grid grid-cols-2 items-stretch gap-4">
          <Lane id="waiting" title="회신 대기" count={pending.length}>
            {pending.map((r) => <Card key={r.key} r={r} draggable={canReply(r)} onOpen={() => open(r)} onReply={canReply(r) ? () => reply(r) : undefined} />)}
            {!pending.length && <Empty>회신을 기다리는 요청이 없습니다.</Empty>}
          </Lane>
          <Lane id="received" title="회신 받음" count={answered.length} accept={!!active && canReply(active)} dragging={!!active}>
            {answered.map((r) => <Card key={r.key} r={r} onOpen={() => open(r)} />)}
            {!answered.length && <Empty>{active ? "여기에 놓으면 회신 등록 창이 열립니다." : "아직 받은 회신이 없습니다."}</Empty>}
          </Lane>
          </div>
          <section aria-label="부서별 현황" className="rounded-2xl bg-card p-6 shadow-card">
            <h2 className="mb-3 text-lg font-medium">부서별 현황</h2>
            <ul className="grid gap-1">
              {["전체 부서", ...names].map((n) => {
                const wait = (n === "전체 부서" ? referralRows() : departmentReviewRows(n)).filter((r) => !r.response).length;
                return (
                  <li key={n}>
                    <button onClick={() => setUi({ department: n })} aria-pressed={selected === n} className={cn("flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm transition-colors", selected === n ? "bg-[#003377] text-white" : "hover:bg-muted")}>
                      <span className="truncate font-medium">{n}</span>
                      <span className={cn("tabular-nums", selected === n ? "text-white/80" : "text-muted-foreground")}><b className={cn("font-medium", selected !== n && "text-foreground")}>{wait}</b> 대기</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        </div>
        <DragOverlay dropAnimation={null}>{active && <CardBody r={active} overlay />}</DragOverlay>
      </DndContext>
    </>
  );
}

const Empty = ({ children }: { children: React.ReactNode }) => <p className="py-12 text-center text-sm text-muted-foreground">{children}</p>;

function Lane({ id, title, count, accept, dragging, children }: { id: string; title: string; count: number; accept?: boolean; dragging?: boolean; children: React.ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id });
  return (
    <section ref={setNodeRef} aria-label={`${title} 열`}
      className={cn("flex min-h-72 flex-col gap-3 rounded-2xl bg-muted/70 p-4 transition-colors", id === "received" && dragging && (accept ? "bg-success/10 ring-1 ring-success/50" : "opacity-50"), id === "received" && isOver && accept && "ring-2 ring-success")}>
      <h2 className="px-1 text-lg font-medium">{title} <span className="tabular-nums text-muted-foreground">{count}</span></h2>
      <div className="grid content-start gap-3">{children}</div>
    </section>
  );
}

function Card({ r, draggable, onOpen, onReply }: { r: Row; draggable?: boolean; onOpen: () => void; onReply?: () => void }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: r.key, disabled: !draggable });
  return <div ref={setNodeRef} {...(draggable ? { ...attributes, ...listeners } : {})} className={cn(isDragging && "opacity-30")}><CardBody r={r} onOpen={onOpen} onReply={onReply} /></div>;
}

function CardBody({ r, onOpen, onReply, overlay }: { r: Row; onOpen?: () => void; onReply?: () => void; overlay?: boolean }) {
  return (
    <article onClick={onOpen} className={cn("grid cursor-pointer gap-3 rounded-xl bg-card p-4 shadow-card transition-shadow hover:shadow-float", overlay && "w-[420px] shadow-float")}>
      <div className="grid gap-1">
        <h3 className="font-semibold leading-snug">{r.ticket.title}</h3>
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground"><span className="truncate">{r.source || "부서 미기록"}</span><ArrowRight className="size-3.5 shrink-0" aria-hidden /><span className="truncate">{r.target || "부서 미기록"}</span></p>
      </div>
      <div className="flex items-center justify-between gap-3">
        {r.response ? <span className="text-sm text-success">회신 받음</span> : <SlaTag t={r.ticket} />}
        {onReply && <Button size="sm" onClick={(e) => { e.stopPropagation(); onReply(); }}>회신 등록</Button>}
      </div>
    </article>
  );
}
