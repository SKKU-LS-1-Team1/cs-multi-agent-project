// C/S 업무 홈: ① 바로가기 타일 4개 → ② 급한 티켓 → ③ 팀 현황. (Emerald24 홈의 순서)
import { AlarmClock, Inbox, Plus, UserPlus } from "lucide-react";
import { Progress } from "@admin/components/ui/progress";
import { ActionTile, TicketRow, useGo } from "@admin/components/admin/common";
import { departmentRisk, ownedTickets, people, priorityTickets, resource, signedIn, stats } from "@admin/lib/logic";
import { openModal, setUi, useStore } from "@admin/lib/store";
import { cn } from "@admin/lib/utils";

const SectionHead = ({ title, link, onLink }: { title: string; link: string; onLink: () => void }) => (
  <div className="mb-3 flex items-baseline justify-between px-1"><h2 className="text-lg font-medium">{title}</h2><button onClick={onLink} className="text-sm text-info hover:underline">{link} ›</button></div>
);

export default function CsWork() {
  useStore();
  const go = useGo();
  const s = stats(), mine = ownedTickets(), urgent = priorityTickets().slice(0, 4);
  const urgentMine = mine.filter((t) => ["P1", "P2"].includes(t.priority)).length;
  const list = (filter: string) => { setUi({ filter }); go.list({ filter }); };

  return (
    <div className="grid gap-9 px-10 pb-12">
      <section aria-label="바로가기" className="grid grid-cols-4 gap-4">
        <ActionTile icon={Plus} label="새 티켓 등록" sub="접수하고 자동 배정" onClick={() => openModal("new-ticket")} />
        <ActionTile icon={UserPlus} label="미배정 배정하기" sub={s.unassigned ? `${s.unassigned}건 대기 중` : "대기 중인 건 없음"} tone={s.unassigned ? "amber" : ""} onClick={() => go.to("/resources")} />
        <ActionTile icon={AlarmClock} label="SLA 위험 확인" sub={s.risk ? `${s.risk}건 확인 필요` : "위험 티켓 없음"} tone={s.risk ? "red" : ""} onClick={() => list("SLA 위험")} />
        <ActionTile icon={Inbox} label="내 티켓" sub={`${mine.length}건${urgentMine ? ` · 긴급 ${urgentMine}건` : ""}`} onClick={() => list("내 담당")} />
      </section>

      <section aria-label="급한 티켓">
        <SectionHead title="급한 티켓" link="전체 보기" onLink={() => list("전체")} />
        <div className="divide-y overflow-hidden rounded-2xl bg-card shadow-card">
          {urgent.map((t) => <TicketRow key={t.id} t={t} onOpen={() => go.ticket(t.id)} />)}
          {!urgent.length && <p className="px-6 py-12 text-center text-sm text-muted-foreground">처리할 티켓이 없습니다.</p>}
        </div>
      </section>

      <section aria-label="팀 현황">
        <SectionHead title="팀 현황" link="리소스 배정" onLink={() => go.to("/resources")} />
        <div className="grid grid-cols-4 gap-4">
          {people.map((p) => {
            const r = resource(p), risk = ownedTickets(p.name).filter(departmentRisk).length, me = p.name === signedIn;
            return (
              <button key={p.name} onClick={() => go.list({ listDepartment: p.department, listOwner: p.name, filter: "전체", query: "", status: "", priority: "", product: "" })}
                className="group grid gap-4 rounded-2xl bg-card p-5 text-left shadow-card transition-all hover:-translate-y-0.5 hover:shadow-float">
                <span className="flex items-center gap-2.5">
                  <span className={cn("grid size-9 place-items-center rounded-full text-xs font-semibold", me ? "bg-[#003377] text-white" : "bg-accent text-accent-foreground")}>{p.name.split(" ").map((x) => x[0]).join("")}</span>
                  <span className="grid leading-tight"><span className="text-sm font-medium">{p.name}{me && <span className="ml-1.5 text-xs font-normal text-muted-foreground">나</span>}</span><span className="text-xs text-muted-foreground">{p.department}</span></span>
                </span>
                <span className="rounded-xl bg-background px-4 py-3">
                  <span className="flex items-baseline justify-between"><span><span className="text-3xl font-normal tabular-nums">{r.count}</span><span className="text-sm text-muted-foreground"> / {r.capacity}건</span></span>{risk > 0 && <span className="text-xs font-medium text-destructive">위험 {risk}</span>}</span>
                  <Progress value={Math.min(100, r.ratio * 100)} className={cn("mt-2 h-1.5", r.free === 0 && "[&>div]:bg-destructive")} />
                </span>
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}
