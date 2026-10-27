// 리소스 배정 보드: 열 = 담당자, 카드 = 미완료 문의. 카드를 끌어 놓으면 배정이 바뀐다.
// 모두 동등하게 응대할 수 있다고 보고 수용량(부하)만 본다. 가득 찬 담당자 열에는 놓을 수 없고, 사유를 안내한다.
import { useState } from "react";
import { DndContext, DragOverlay, PointerSensor, pointerWithin, useDraggable, useDroppable, useSensor, useSensors, type DragEndEvent, type DragStartEvent } from "@dnd-kit/core";
import { toast } from "sonner";
import { ChevronDown, GripVertical } from "lucide-react";
import { Button } from "@admin/components/ui/button";
import { Mono, NativeSelect, PersonAvatar, PriorityTag, Tag, rise, useGo } from "@admin/components/admin/common";
import { checkAssign, departmentRisk, openTickets, ownedTickets, canAssign, people, recommend, resource, teamLead } from "@admin/lib/logic";
import { moveTicket } from "@admin/lib/actions";
import { openModal, useStore } from "@admin/lib/store";
import { cn } from "@admin/lib/utils";
import type { Person, Ticket } from "@admin/lib/types";

const UNASSIGNED = "__unassigned__";

export default function ResourceBoard() {
  useStore();
  const go = useGo();
  const [active, setActive] = useState<Ticket | null>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  const team = [...people].sort((a, b) => Number(b.name === teamLead) - Number(a.name === teamLead)); // 팀장이 맨 앞
  const unassigned = openTickets().filter((t) => !t.owner);
  const best = active ? recommend(active.id) : undefined;

  const verdict = (col: string): { ok: boolean; reason?: string } => {
    if (!active) return { ok: true };
    if (col === UNASSIGNED) return active.owner ? { ok: true } : { ok: false, reason: "이미 미배정입니다" };
    const p = people.find((x) => x.name === col)!;
    return p.name === active.owner ? { ok: false, reason: "현재 담당자입니다" } : checkAssign(active, p);
  };

  const onStart = (e: DragStartEvent) => setActive(openTickets().find((t) => t.id === e.active.id) || null);
  const onEnd = (e: DragEndEvent) => {
    const t = active;
    setActive(null);
    if (!t || !e.over) return;
    const col = String(e.over.id);
    if (col === UNASSIGNED ? !t.owner : col === t.owner) return;
    const v = col === UNASSIGNED ? { ok: true } : checkAssign(t, people.find((p) => p.name === col)!);
    if (!v.ok) { toast.error(`배정할 수 없습니다 · ${v.reason}`); return; }
    moveTicket(t, col === UNASSIGNED ? "" : col);
  };

  return (
    <div className="grid gap-4 px-10 pb-12">
      <div className="flex items-center justify-between gap-3 text-sm">
        <p className="text-muted-foreground">{canAssign ? "카드를 끌어서 담당자를 바꿉니다." : "현황만 볼 수 있습니다. 담당자 배정은 팀장만 할 수 있습니다."}</p>
      </div>

      <DndContext sensors={sensors} collisionDetection={pointerWithin} onDragStart={onStart} onDragEnd={onEnd} onDragCancel={() => setActive(null)}>
        <div className="grid auto-cols-[minmax(210px,1fr)] grid-flow-col gap-3 overflow-x-auto pb-2">
          <Column id={UNASSIGNED} order={0} title="미배정" tickets={unassigned} dragging={!!active} verdict={verdict(UNASSIGNED)} go={go}
            sub={<span className="text-xs text-muted-foreground">담당자 지정 대기</span>} />
          {team.map((p, i) => (
            <Column key={p.name} id={p.name} order={i + 1} title={p.name} tickets={ownedTickets(p.name)} dragging={!!active} verdict={verdict(p.name)} recommended={best?.name === p.name} person={p} go={go} />
          ))}
        </div>
        <DragOverlay dropAnimation={null}>{active && <Card t={active} overlay />}</DragOverlay>
      </DndContext>
    </div>
  );
}

function Column({ id, order, title, tickets, person, sub, dragging, verdict, recommended, go }: {
  id: string; order: number; title: string; tickets: Ticket[]; person?: Person; sub?: React.ReactNode; dragging: boolean;
  verdict: { ok: boolean; reason?: string }; recommended?: boolean; go: ReturnType<typeof useGo>;
}) {
  const { setNodeRef, isOver } = useDroppable({ id });
  const r = person ? resource(person) : null;
  return (
    <section ref={setNodeRef} aria-label={`${title} 열`} style={rise(order).style}
      className={cn("flex min-h-[calc(100dvh-300px)] flex-col gap-3 rounded-2xl bg-muted/70 p-3 transition-colors", rise(order).className,
        dragging && verdict.ok && "ring-1 ring-success/60 bg-success/5",
        dragging && !verdict.ok && "opacity-45",
        isOver && verdict.ok && "ring-2 ring-success bg-success/10",
        isOver && !verdict.ok && "ring-2 ring-destructive bg-destructive/5")}>
      <header className="grid gap-2">
        <div className="flex items-center justify-between gap-2">
          <h3 className="flex items-center gap-2 font-semibold">{person && <PersonAvatar name={person.name} size={28} />}{title}{person?.rank && <span className={cn("text-xs", person.name === teamLead ? "font-medium text-[#003377]" : "font-normal text-muted-foreground")}>{person.rank}</span>}</h3>
          <div className="flex items-center gap-1.5">
            {dragging && recommended && <Tag tone="green">추천</Tag>}
            <span className="rounded bg-card px-1.5 py-0.5 text-xs tabular-nums ring-1 ring-border">{tickets.length}</span>
          </div>
        </div>
        {person && r ? (
          <>
            <div className="flex items-baseline justify-between text-xs text-muted-foreground"><span>미완료</span><span className="tabular-nums"><b className="text-foreground">{r.count}</b>건</span></div>
            <span className="block h-1.5 overflow-hidden rounded-full bg-muted"><span className="block h-full rounded-full bg-info" style={{ width: `${(r.count / Math.max(1, ...people.map((x) => resource(x).count))) * 100}%` }} /></span>
          </>
        ) : sub}
        {dragging && !verdict.ok && verdict.reason && <p className="rounded bg-card px-2 py-1 text-xs text-destructive ring-1 ring-destructive/30">{verdict.reason}</p>}
      </header>
      <div className="grid content-start gap-2">
        {tickets.map((t) => <DraggableCard key={t.id} t={t} go={go} />)}
        {!tickets.length && <p className="rounded-xl bg-card/60 py-8 text-center text-xs text-muted-foreground">배정된 문의 없음</p>}
      </div>
    </section>
  );
}

function DraggableCard({ t, go }: { t: Ticket; go: ReturnType<typeof useGo> }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: t.id, disabled: !canAssign });
  return (
    <div ref={setNodeRef} className={cn(isDragging && "opacity-30")}>
      <Card t={t} handle={{ ...attributes, ...listeners }} onOpen={() => go.ticket(t.id)} />
    </div>
  );
}

function Card({ t, handle, onOpen, overlay }: { t: Ticket; handle?: Record<string, any>; onOpen?: () => void; overlay?: boolean }) {
  return (
    <article className={cn("group/card grid gap-2 rounded-xl bg-card p-3.5 text-sm shadow-card", overlay && "w-[248px] shadow-lg ring-1 ring-ring", departmentRisk(t) && "ring-1 ring-destructive/40")}>
      <div className="flex items-start gap-1.5">
        {canAssign && <button type="button" aria-label="끌어서 담당자 변경" className="mt-0.5 cursor-grab touch-none text-muted-foreground hover:text-foreground active:cursor-grabbing" {...handle}><GripVertical className="size-4" /></button>}
        <button type="button" onClick={onOpen} className="min-w-0 flex-1 text-left font-semibold leading-snug hover:underline">{t.title}</button>
      </div>
      <div className="grid text-xs text-muted-foreground"><Mono>{t.id}</Mono><span>{t.product}</span></div>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5"><PriorityTag p={t.priority} /><span className={cn("text-xs tabular-nums", departmentRisk(t) ? "font-semibold text-destructive" : "text-muted-foreground")}>{t.sla}</span></div>
        {!overlay && canAssign && <Button size="sm" variant="ghost" className="h-6 px-2 text-xs opacity-0 transition-opacity focus-visible:opacity-100 group-hover/card:opacity-100" onClick={() => openModal("assign", { id: t.id })}>배정<ChevronDown /></Button>}
      </div>
    </article>
  );
}
