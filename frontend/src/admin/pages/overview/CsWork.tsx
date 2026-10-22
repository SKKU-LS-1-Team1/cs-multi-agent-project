// C/S 업무 홈(2단): 위 = 오늘 내가 할 일 | SLA 안정도, 아래 = 팀 현황 | 전문부서 협업 요약. 위쪽 버튼으로 카드를 켜고 끌 수 있다.
import { ArrowRight, CheckCheck, ChevronRight, FilePenLine, MessageSquareReply, Plus, Send, UserPlus, type LucideIcon } from "lucide-react";
import { Button } from "@admin/components/ui/button";
import { CustomizeMenu, Ring, useWidgets } from "@admin/components/admin/charts";
import { Mono, PageHeader, PersonAvatar, SlaTag, Tag, useGo } from "@admin/components/admin/common";
import { departmentRank, departmentRisk, openTickets, ownedTickets, people, referralRows, canAssign, FRONTLINE, resource, signedIn, teamLead, slaMinutes, stats, todayTasks } from "@admin/lib/logic";
import { openModal, setUi, useStore } from "@admin/lib/store";
import { cn } from "@admin/lib/utils";

export const CS_WIDGETS = [["today", "오늘 내가 할 일"], ["sla", "SLA·바로가기"], ["team", "팀 현황"], ["collab", "전문부서 협업"]] as const;

/** 위험 건수에 따른 색: 0건 초록 · 1~2건 노랑 · 3건 이상 빨강. */
const riskTone = (n: number) => (n === 0 ? "success" : n < 3 ? "warning" : "destructive") as "success" | "warning" | "destructive";
const RISK_TEXT = { success: "위험 없음", warning: "주의 필요", destructive: "위험 높음" };
const RISK_TAG = { success: "green", warning: "amber", destructive: "red" } as const;
const TASK_ICON: Record<string, [LucideIcon, string]> = {
  "고객 회신 확인하기": [MessageSquareReply, "bg-info/10 text-info"],
  "답변 작성 시작하기": [FilePenLine, "bg-info/10 text-info"],
  "영어 초안 검토하기": [FilePenLine, "bg-info/10 text-info"],
  "승인하고 발송하기": [Send, "bg-success/10 text-success"],
  "처리 결과 기록하고 완료하기": [CheckCheck, "bg-success/10 text-success"],
  "고객 질의서 작성하기": [FilePenLine, "bg-info/10 text-info"],
  "전문부서 요청서 작성하기": [FilePenLine, "bg-info/10 text-info"],
  "미배정 문의 배정하기": [UserPlus, "bg-warning/20 text-warning-ink"],
};
const TaskIcon = ({ label }: { label: string }) => { const [Icon, tone] = TASK_ICON[label] || [FilePenLine, "bg-muted text-foreground"]; return <span className={cn("grid size-10 place-items-center rounded-full", tone)}><Icon className="size-[18px]" aria-hidden /></span>; };

const Card = ({ title, sub, aside, children, className }: { title: string; sub?: string; aside?: React.ReactNode; children: React.ReactNode; className?: string }) => (
  <section aria-label={title} className={cn("flex flex-col rounded-2xl bg-card p-6 shadow-card", className)}>
    <div className="mb-4 flex items-center justify-between gap-3"><h2 className="flex items-baseline gap-2 text-lg font-medium">{title}{sub && <small className="text-sm font-normal text-muted-foreground">{sub}</small>}</h2>{aside}</div>
    {children}
  </section>
);

export default function CsWork({ tabs }: { tabs: React.ReactNode }) {
  useStore();
  const go = useGo();
  const w = useWidgets("ls-admin-widgets-cs-v2", CS_WIDGETS);
  const s = stats(), mine = ownedTickets(), tasks = todayTasks().slice(0, 5), open = openTickets().length;
  const safe = open ? Math.round(((open - s.risk) / open) * 100) : 100, tone = riskTone(s.risk);
  const waiting = referralRows().filter((r) => !r.response).sort((a, b) => departmentRank(a.ticket) - departmentRank(b.ticket) || (slaMinutes(a.ticket) ?? Infinity) - (slaMinutes(b.ticket) ?? Infinity));
  const waitRisk = new Set(waiting.filter((r) => departmentRisk(r.ticket)).map((r) => r.ticket.id)).size;
  const list = (filter: string) => { setUi({ filter }); go.list({ filter }); };
  const quick: [string, number, string, () => void][] = [
    ["미배정", s.unassigned, s.unassigned ? "text-warning-ink" : "", () => go.to("/resources")],
    ["SLA 위험", s.risk, s.risk ? (tone === "destructive" ? "text-destructive" : "text-warning-ink") : "", () => list("전체")],
    ["답변 검토 대기", s.review, "", () => list("답변 준비")],
    ["내 문의", mine.length, "", () => list("내 담당")],
  ];
  const row = "grid w-full grid-cols-[auto_minmax(0,1fr)_auto_16px] items-center gap-4 px-6 py-4 text-left transition-colors hover:bg-muted/70";

  return (
    <>
      <PageHeader title="고객지원 업무 현황" actions={<><CustomizeMenu all={CS_WIDGETS} shown={w.shown} toggle={w.toggle} /><Button onClick={() => openModal("new-ticket")}><Plus aria-hidden />새 문의 등록</Button></>}>{tabs}</PageHeader>
      <div className="grid grid-cols-[minmax(0,1fr)_340px] items-stretch gap-5 px-10 pb-12">
        {w.shown("today") && (
          <Card title="오늘 내가 할 일" aside={<button onClick={() => list("내 담당")} className="text-sm text-info hover:underline">내 문의 전체 ›</button>} className="overflow-hidden p-0 [&>div:first-child]:px-6 [&>div:first-child]:pt-6">
            <ul className="divide-y">
              {tasks.map(({ ticket: t, label }) => (
                <li key={t.id}>
                  <button onClick={() => go.ticket(t.id)} className={row}>
                    <TaskIcon label={label} />
                    <span className="grid gap-0.5"><span className="font-medium">{label}</span><span className="truncate text-sm text-muted-foreground">{t.title} · <Mono>{t.id}</Mono></span></span>
                    <SlaTag t={t} />
                    <ChevronRight className="size-4 text-muted-foreground" aria-hidden />
                  </button>
                </li>
              ))}
              {s.unassigned > 0 && canAssign && (
                <li><button onClick={() => go.to("/resources")} className={row}><TaskIcon label="미배정 문의 배정하기" /><span className="grid gap-0.5"><span className="font-medium">미배정 문의 배정하기</span><span className="text-sm text-muted-foreground">담당자가 없는 문의 {s.unassigned}건</span></span><Tag tone="amber">{s.unassigned}건</Tag><ChevronRight className="size-4 text-muted-foreground" aria-hidden /></button></li>
              )}
            </ul>
            {!tasks.length && !(s.unassigned > 0 && canAssign) && <p className="px-6 py-12 text-center text-sm text-muted-foreground">오늘 처리할 일이 없습니다. 고객이나 전문부서 회신을 기다리는 건은 여기에 나오지 않습니다.</p>}
          </Card>
        )}
        {w.shown("sla") && (
          <Card title="SLA 안정도">
            <div className="grid place-items-center"><Ring size={124} value={safe} label={`${safe}%`} caption="기한 내 진행" tone={tone} /><Tag tone={RISK_TAG[tone]} className="mt-3">{RISK_TEXT[tone]}{s.risk ? ` · SLA 위험 ${s.risk}건` : ""}</Tag></div>
            <ul className="mt-4 grid grid-cols-2 gap-2">
              {quick.map(([label, n, c, run]) => (
                <li key={label}><button onClick={run} className="grid w-full gap-0.5 rounded-xl bg-background px-3.5 py-2.5 text-left transition-colors hover:bg-muted"><span className="text-xs text-muted-foreground">{label}</span><span className={cn("text-xl font-medium tabular-nums", c)}>{n}<span className="text-sm font-normal text-muted-foreground"> 건</span></span></button></li>
              ))}
            </ul>
          </Card>
        )}
        {w.shown("team") && (
          <Card title="팀 현황" sub={FRONTLINE} aside={<button onClick={() => go.to("/resources")} className="text-sm text-info hover:underline">{canAssign ? "배정하기 ›" : "자세히 ›"}</button>}>
            <ul className="grid grid-cols-2 gap-x-4 gap-y-1">
              {[...people].sort((a, b) => Number(b.name === teamLead) - Number(a.name === teamLead)).map((p) => { // 팀장이 맨 앞
                const r = resource(p), me = p.name === signedIn;
                return (
                  <li key={p.name}>
                    <button onClick={() => go.list({ listOwner: p.name, filter: "전체", query: "", status: "", priority: "", product: "" })} className="grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 rounded-xl px-2 py-2.5 text-left transition-colors hover:bg-muted">
                      <PersonAvatar name={p.name} size={40} />
                      <span className="grid gap-1.5"><span className="truncate text-sm font-medium">{p.name}{p.rank && <span className={cn("ml-1.5 text-xs", p.name === teamLead ? "font-medium text-[#003377]" : "font-normal text-muted-foreground")}>{p.rank}</span>}{me && <span className="ml-1.5 text-xs font-normal text-muted-foreground">나</span>}</span><span className="h-1.5 overflow-hidden rounded-full bg-muted"><span className={cn("block h-full rounded-full", r.free === 0 ? "bg-destructive" : r.ratio >= 0.8 ? "bg-warning" : "bg-info")} style={{ width: `${Math.min(100, r.ratio * 100)}%` }} /></span></span>
                      <span className="text-sm tabular-nums"><b className="font-medium">{r.count}</b><span className="text-muted-foreground"> / {r.capacity}</span></span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </Card>
        )}
        {w.shown("collab") && (
          <Card title="전문부서 협업" aside={<button onClick={() => go.to("/collab")} className="text-sm text-info hover:underline">자세히 ›</button>}>
            <div className="flex items-baseline gap-2"><span className="text-4xl font-medium tabular-nums">{waiting.length}</span><span className="text-muted-foreground">건 회신 대기</span>{waitRisk > 0 && <Tag tone="red" className="ml-auto">SLA 위험 {waitRisk}</Tag>}</div>
            <ul className="mt-3 divide-y">
              {waiting.slice(0, 3).map((r) => (
                <li key={r.key}><button onClick={() => go.to("/collab")} className="grid w-full gap-0.5 py-3 text-left hover:text-info"><span className="truncate text-sm font-medium">{r.ticket.title}</span><span className="flex items-center gap-1.5 text-xs text-muted-foreground">{r.source || "요청 부서 미기록"}<ArrowRight className="size-3" aria-hidden />{r.target || "대상 부서 미기록"}</span></button></li>
              ))}
              {!waiting.length && <li className="py-6 text-center text-sm text-muted-foreground">회신을 기다리는 요청이 없습니다.</li>}
            </ul>
          </Card>
        )}
      </div>
    </>
  );
}
