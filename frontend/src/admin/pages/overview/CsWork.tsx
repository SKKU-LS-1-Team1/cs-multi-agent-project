import { todayTasks } from "@admin/lib/actions";
// C/S 업무 홈(2단): 위 = 오늘 내가 할 일 | SLA 안정도, 아래 = 팀 현황 | 전문부서 협업 요약. 위쪽 버튼으로 카드를 켜고 끌 수 있다.
import { ArrowRight, ArrowUpRight, CheckCheck, ChevronRight, FileCheck2, FilePenLine, MessageSquareReply, Plus, Send, TriangleAlert, type LucideIcon } from "lucide-react";
import { Button } from "@admin/components/ui/button";
import { CustomizeMenu, Ring, useWidgets } from "@admin/components/admin/charts";
import { Mono, PageHeader, PersonAvatar, SlaTag, Tag, rise, useGo } from "@admin/components/admin/common";
import { departmentRank, departmentRisk, openTickets, people, referralRows, canAssign, FRONTLINE, resource, signedIn, teamLead, slaMinutes, stats } from "@admin/lib/logic";
import { openModal, setUi, useStore } from "@admin/lib/store";
import { cn } from "@admin/lib/utils";

export const CS_WIDGETS = [["today", "오늘 내가 할 일"], ["sla", "SLA·바로가기"], ["team", "팀 현황"], ["collab", "전문부서 협업"]] as const;

/** 위험 건수에 따른 색: 0건 초록 · 1~2건 노랑 · 3건 이상 빨강. */
const riskTone = (n: number) => (n === 0 ? "success" : n < 3 ? "warning" : "destructive") as "success" | "warning" | "destructive";
const RISK_TEXT = { success: "위험 없음", warning: "주의 필요", destructive: "위험 높음" };
const RISK_TAG = { success: "green", warning: "amber", destructive: "red" } as const;
/** 할 일 카드에 보여 주는 줄 수(급한 순). 전체 건수는 제목 옆에 쓴다. */
const TASK_ROWS = 4;
const TASK_ICON: Record<string, [LucideIcon, string]> = {
  "고객 회신 확인하기": [MessageSquareReply, "bg-info/10 text-info"],
  "답변 작성 시작하기": [FilePenLine, "bg-info/10 text-info"],
  "영어 초안 검토하기": [FilePenLine, "bg-info/10 text-info"],
  "승인하고 발송하기": [Send, "bg-success/10 text-success"],
  "처리 결과 기록하고 완료하기": [CheckCheck, "bg-success/10 text-success"],
  "고객 질의서 작성하기": [FilePenLine, "bg-info/10 text-info"],
  "전문부서 요청서 작성하기": [FilePenLine, "bg-info/10 text-info"],
};
const TaskIcon = ({ label }: { label: string }) => { const [Icon, tone] = TASK_ICON[label] || [FilePenLine, "bg-muted text-foreground"]; return <span className={cn("grid size-10 place-items-center rounded-full transition-transform duration-200 group-hover:scale-105", tone)}><Icon className="size-[18px]" aria-hidden /></span>; };

/** 대시보드 카드: 제목 + 한 줄 설명(desc) + 오른쪽 링크. */
const Card = ({ title, sub, desc, aside, children, className, order = 0 }: { title: string; sub?: string; desc?: string; aside?: React.ReactNode; children: React.ReactNode; className?: string; order?: number }) => (
  <section aria-label={title} style={rise(order).style} className={cn("flex flex-col rounded-3xl bg-card p-6 shadow-card", rise(order).className, className)}>
    <div className="mb-5 flex items-start justify-between gap-3">
      <div className="grid gap-1">
        <h2 className="flex items-baseline gap-2 text-lg font-semibold tracking-tight">{title}{sub && <small className="text-sm font-normal text-muted-foreground">{sub}</small>}</h2>
        {desc && <p className="text-sm text-muted-foreground">{desc}</p>}
      </div>
      {aside}
    </div>
    {children}
  </section>
);

export default function CsWork({ tabs }: { tabs: React.ReactNode }) {
  useStore();
  const go = useGo();
  const w = useWidgets("ls-admin-widgets-cs-v2", CS_WIDGETS);
  const s = stats(), allTasks = todayTasks(), tasks = allTasks.slice(0, TASK_ROWS), open = openTickets().length;
  const safe = open ? Math.round(((open - s.risk) / open) * 100) : 100, tone = riskTone(s.risk);
  const waiting = referralRows().filter((r) => !r.response && r.ticket.stage !== 5).sort((a, b) => departmentRank(a.ticket) - departmentRank(b.ticket) || (slaMinutes(a.ticket) ?? Infinity) - (slaMinutes(b.ticket) ?? Infinity));
  const waitRisk = new Set(waiting.filter((r) => departmentRisk(r.ticket)).map((r) => r.ticket.id)).size;
  const list = (filter: string) => { setUi({ filter }); go.list({ filter }); };
  const quick: [string, number, LucideIcon, string, () => void][] = [
    ["SLA 위험", s.risk, TriangleAlert, s.risk ? (tone === "destructive" ? "bg-destructive/10 text-destructive" : "bg-warning/15 text-warning-ink") : "bg-muted text-muted-foreground", () => list("전체")],
    ["답변 검토 대기", s.review, FileCheck2, s.review ? "bg-info/10 text-info" : "bg-muted text-muted-foreground", () => list("답변 준비")],
  ];
  const row = "group grid w-full grid-cols-[auto_minmax(0,1fr)_auto_16px] items-center gap-4 px-6 py-4 text-left transition-colors duration-200 hover:bg-muted/70 active:bg-muted";
  const chev = "size-4 text-muted-foreground transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-foreground";
  const link = "text-sm font-medium text-info transition-colors hover:text-[#003377]";

  return (
    <>
      <PageHeader title="고객지원 업무 현황" actions={<><CustomizeMenu all={CS_WIDGETS} shown={w.shown} toggle={w.toggle} /><Button onClick={() => openModal("new-ticket")}><Plus aria-hidden />새 문의 등록</Button></>}>{tabs}</PageHeader>
      <div className="grid grid-cols-[minmax(0,1fr)_340px] items-stretch gap-5 px-10 pb-12">
        {w.shown("today") && (
          <Card title="오늘 내가 할 일" sub={allTasks.length ? `${allTasks.length}건` : undefined} desc="기한이 급한 순" aside={<button onClick={() => list("내 담당")} className={link}>내 문의 전체 ›</button>} className="overflow-hidden p-0 [&>div:first-child]:px-6 [&>div:first-child]:pt-6">
            <ul className="divide-y">
              {tasks.map(({ ticket: t, label }) => (
                <li key={t.id}>
                  <button onClick={() => go.ticket(t.id)} className={row}>
                    <TaskIcon label={label} />
                    <span className="grid gap-0.5"><span className="font-semibold">{label}</span><span className="truncate text-sm text-muted-foreground">{t.title} · <Mono>{t.id}</Mono></span></span>
                    <SlaTag t={t} />
                    <ChevronRight className={chev} aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
            {!tasks.length && <p className="px-6 py-12 text-center text-sm text-muted-foreground">오늘 처리할 일이 없습니다. 고객이나 전문부서 회신을 기다리는 건은 여기에 나오지 않습니다.</p>}
          </Card>
        )}
        {w.shown("sla") && (
          <Card title="SLA 안정도" desc="팀 전체 진행 중 문의 기준" order={1}>
            <div className="grid flex-1 content-center gap-6">
            <div className="grid place-items-center"><Ring size={124} value={safe} label={`${safe}%`} caption="기한 내 진행" tone={tone} /><Tag tone={RISK_TAG[tone]} className="mt-3">{RISK_TEXT[tone]}</Tag></div>
            <ul className="grid gap-2">
              {quick.map(([label, n, Icon, c, run]) => (
                <li key={label}>
                  <button onClick={run} className={cn("group flex w-full items-center gap-3 rounded-full py-2 pl-2 pr-4 text-left transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card active:translate-y-0 active:scale-[0.98]", c)}>
                    <span className="grid size-9 place-items-center rounded-full bg-card shadow-sm"><Icon className="size-4" aria-hidden /></span>
                    <span className="text-sm font-medium text-foreground">{label}</span>
                    <b className="ml-auto text-lg font-bold tabular-nums">{n}<span className="ml-0.5 text-xs font-normal text-muted-foreground">건</span></b>
                    <ArrowUpRight className="size-4 opacity-60 transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:opacity-100" aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
            </div>
          </Card>
        )}
        {w.shown("team") && (
          <Card title="팀 현황" sub={FRONTLINE} desc="담당자별 진행 중 문의" order={2} aside={<div className="flex items-center gap-3">
            {s.unassigned > 0 && <button onClick={() => go.to("/resources")} className="rounded-full bg-warning/20 px-2.5 py-0.5 text-xs font-semibold text-warning-ink transition-colors hover:bg-warning/30">미배정 {s.unassigned}건</button>}
            <button onClick={() => go.to("/resources")} className={link}>{canAssign ? "배정하기 ›" : "자세히 ›"}</button></div>}>
            <ul className="grid grid-cols-2 gap-x-4 gap-y-1">
              {[...people].sort((a, b) => Number(b.name === teamLead) - Number(a.name === teamLead)).map((p) => { // 팀장이 맨 앞
                const r = resource(p), me = p.name === signedIn;
                const width = (r.count / Math.max(1, ...people.map((x) => resource(x).count))) * 100; // 팀에서 가장 많이 맡은 사람 = 가득 찬 막대
                return (
                  <li key={p.name}>
                    <button onClick={() => go.list({ listOwner: p.name, filter: "전체", query: "", status: "", priority: "", product: "" })} className="group grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 rounded-xl px-2 py-2.5 text-left transition-colors duration-200 hover:bg-muted active:scale-[0.99]">
                      <PersonAvatar name={p.name} size={40} />
                      <span className="grid gap-1.5"><span className="truncate text-sm font-semibold">{p.name}{p.rank && <span className={cn("ml-1.5 text-xs", p.name === teamLead ? "font-medium text-[#003377]" : "font-normal text-muted-foreground")}>{p.rank}</span>}{me && <span className="ml-1.5 text-xs font-normal text-muted-foreground">나</span>}</span><span className="h-1.5 overflow-hidden rounded-full bg-muted"><span className="block h-full origin-left rounded-full bg-info transition-[width] duration-700 ease-out" style={{ width: `${width}%` }} /></span></span>
                      <span className="text-sm tabular-nums"><b className="text-base font-bold">{r.count}</b><span className="text-muted-foreground">건</span></span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </Card>
        )}
        {w.shown("collab") && (
          <Card title="전문부서 협업" desc="전문부서 회신을 기다리는 요청" order={3} aside={<button onClick={() => go.to("/collab")} className={link}>자세히 ›</button>}>
            <div className="flex items-baseline gap-2"><span className="text-4xl font-bold tracking-tight tabular-nums">{waiting.length}</span><span className="text-muted-foreground">건 회신 대기</span>{waitRisk > 0 && <Tag tone="red" className="ml-auto">SLA 위험 {waitRisk}</Tag>}</div>
            <ul className="mt-3 divide-y">
              {waiting.slice(0, 3).map((r) => (
                <li key={r.key}><button onClick={() => go.to("/collab")} className="grid w-full gap-0.5 py-3 text-left transition-colors duration-200 hover:text-info"><span className="truncate text-sm font-semibold">{r.ticket.title}</span><span className="flex items-center gap-1.5 text-xs text-muted-foreground">{r.source || "요청 부서 미기록"}<ArrowRight className="size-3" aria-hidden />{r.target || "대상 부서 미기록"}</span></button></li>
              ))}
              {!waiting.length && <li className="py-6 text-center text-sm text-muted-foreground">회신을 기다리는 요청이 없습니다.</li>}
            </ul>
          </Card>
        )}
      </div>
    </>
  );
}
