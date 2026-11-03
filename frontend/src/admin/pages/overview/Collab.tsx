// 전문부서 협업 = 문의 목록 "3/6 전문부서" 단계를 문의 전체에 걸쳐 본 화면. 하위 상태는 expertPhase 와 같다.
// 왼쪽 위 = 회신 도착·검토 필요(공이 우리에게 있다: 담당자가 확인해야 4단계로 넘어간다), 왼쪽 아래 = 회신 대기(회신 대기 시간·회신 등록)
// 오른쪽 = 부서별 대기(건수 막대를 기다린 시간 구간으로 나눠 어느 부서가 오래 묵었는지 보인다).
// 요청서 작성 중(writing)은 부서와 오가는 일이 아니라 담당자 본인의 작업이라 "할 일"에 둔다. 검토가 끝난 뒤의 답변 작성도 "할 일"과 문의 상세가 안내한다.
import { useState } from "react";
import { ArrowRight, ChevronDown, ChevronRight } from "lucide-react";
import { Mono, PageHeader, Pager, PersonAvatar, SlaTag, Tag, rise, useGo } from "@admin/components/admin/common";
import { openExpertReview } from "@admin/lib/actions";
import { departmentRisk, departmentReviewRows, expertPhase, referralDepartments, referralRows } from "@admin/lib/logic";
import { openModal, setUi, ui, useStore } from "@admin/lib/store";
import { cn } from "@admin/lib/utils";

const SIZE = 10; // 한 페이지에 보이는 요청 수
const STATUS_TABS = [["all", "전체"], ["review", "회신 도착"], ["waiting", "회신 대기"]] as const;
type Row = ReturnType<typeof referralRows>[number];
/** 요청한 뒤 지난 시간(시간 단위). 없거나 해석할 수 없는 시각은 미기록으로 둔다. */
const waitedHours = (r: Row): number | null => {
  const timestamp = r.when ? Date.parse(r.when) : NaN;
  return Number.isFinite(timestamp) ? Math.max(0, (Date.now() - timestamp) / 3600e3) : null;
};
/** SLA 태그(초과 2h 10m)와 같은 표기: 1시간 이상이면 "30h 5m"(분이 0이면 "30h"), 1시간 미만이면 "45m". */
const fmtWait = (h: number) => { const total = Math.floor(h * 60), hh = Math.floor(total / 60), mm = total % 60; return hh ? (mm ? `${hh}h ${mm}m` : `${hh}h`) : `${mm}m`; };
/** SLA 위험인 요청을 먼저, 그다음 오래 기다린 순. */
const byUrgency = (a: Row, b: Row) => Number(departmentRisk(b.ticket)) - Number(departmentRisk(a.ticket)) || (waitedHours(b) ?? -1) - (waitedHours(a) ?? -1);

/** 부서별 현황 막대 색(진행 중 요청). */
const BARS = [{ tone: "bg-info/45" }] as const;

// BACKEND: 전문부서 재요청(독촉)은 아직 없다. 생기면 POST /tickets/{id}/specialist-requests/{request_id}/remind 로 카드에 버튼을 붙인다.

export default function Collab({ tabs }: { tabs: React.ReactNode }) {
  useStore();
  const go = useGo();
  const [showIdle, setShowIdle] = useState(false);
  const [status, setStatus] = useState<"all" | "review" | "waiting">("all");
  const [page, setPage] = useState(1);

  const waitingAll = referralRows().filter((r) => (!r.response || r.ticket.specialistFollowup?.status === "in_progress") && r.ticket.stage !== 5);
  const names = referralDepartments();
  const inReview = (r: Row) => !!r.response && !r.response.reviewed && r.ticket.stage !== 5 && expertPhase(r.ticket) === "review";
  const reviewAll = referralRows().filter(inReview);
  const selected = ui.department !== "전체 부서" && !names.includes(ui.department) ? "전체 부서" : ui.department;
  const pending = (selected === "전체 부서" ? waitingAll : departmentReviewRows(selected).filter((r) => (!r.response || r.ticket.specialistFollowup?.status === "in_progress") && r.ticket.stage !== 5)).sort(byUrgency);
  const toReview = (selected === "전체 부서" ? reviewAll : reviewAll.filter((r) => (r.target || "대상 부서 미기록") === selected)).sort((a, b) => Number(departmentRisk(b.ticket)) - Number(departmentRisk(a.ticket)) || (Date.parse(a.response.createdAt || "") || 0) - (Date.parse(b.response.createdAt || "") || 0));
  const count = { all: toReview.length + pending.length, review: toReview.length, waiting: pending.length };
  // 부서별 현황: 진행 중 요청이 있는 부서를 먼저(많은 순), 없는 부서는 접어 둔다. 진행 중 요청(회신 대기 + 회신 검토)만 센다.
  const doingAll = [...new Map([...waitingAll, ...reviewAll].map((r) => [r.key, r])).values()];
  const dept = (r: Row) => r.target || "대상 부서 미기록";
  const rowsOf = (list: Row[], n: string) => (n === "전체 부서" ? list : list.filter((r) => dept(r) === n));
  const doingOf = (n: string) => rowsOf(doingAll, n).length;
  const countOf = doingOf;
  const busy = names.filter((n) => countOf(n) > 0).sort((a, b) => countOf(b) - countOf(a));
  const idle = names.filter((n) => !busy.includes(n));
  const idleOpen = showIdle || idle.includes(selected);
  const widest = Math.max(1, ...names.map(countOf));
  const shown = [...(status === "waiting" ? [] : toReview.map((r) => ({ r, phase: "review" as const }))), ...(status === "review" ? [] : pending.map((r) => ({ r, phase: "waiting" as const })))];
  const curPage = Math.min(page, Math.max(1, Math.ceil(shown.length / SIZE))); // 건수가 줄어 마지막 페이지가 사라져도 범위 안에 둔다
  return (
    <>
      <PageHeader title="전문부서 협업 현황">{tabs}</PageHeader>
      <div className="grid grid-cols-[minmax(0,1fr)_340px] items-start gap-5 px-10 pb-12">
        <section aria-label="전문부서 요청" className="grid content-start gap-4">
          <div className="overflow-hidden rounded-2xl bg-card shadow-card">
            <div className="flex flex-wrap gap-2 px-6 pt-6" role="group" aria-label="요청 상태 필터">
              {STATUS_TABS.map(([k, label]) => (
                <button key={k} type="button" aria-pressed={status === k} onClick={() => { setStatus(k); setPage(1); }}
                  className={cn("inline-flex h-9 items-center gap-2 rounded-full px-4 text-sm transition-colors", status === k ? "bg-[#003377] text-white" : "bg-muted text-muted-foreground hover:text-foreground")}>
                  {label}<span className={cn("tabular-nums", status === k ? "text-white/80" : "text-foreground")}>{count[k]}</span>
                </button>
              ))}
            </div>
            <div className={cn("grid items-center gap-4 px-6 pb-3 text-sm text-muted-foreground", "pt-6", COLS)}>
              <span>문의</span><span className="text-center">경과</span><span className="text-center">SLA</span><span>담당자</span><span />
            </div>
            <div className="divide-y border-t">
              {shown.slice((curPage - 1) * SIZE, curPage * SIZE).map(({ r, phase }) => <CollabRow key={r.key + phase} r={r} phase={phase} onOpen={() => { if (phase === "review") { go.ticket(r.ticket.id); openExpertReview(r.ticket); } else if (r.event) openModal("department-review", { key: r.key }); else go.ticket(r.ticket.id); }} />)}
            </div>
            {!shown.length && <p className="py-12 text-center text-sm text-muted-foreground">{status === "review" ? "검토할 전문부서 회신이 없습니다." : "진행 중인 전문부서 요청이 없습니다."}</p>}
          </div>
          <Pager page={curPage} size={SIZE} total={shown.length} onChange={setPage} />
        </section>

        <section aria-label="부서별 현황" style={rise(0).style} className={cn("rounded-2xl bg-card p-6 shadow-card", rise(0).className)}>
          <h2 className="text-lg font-medium">부서별 현황</h2>
          <div className="mb-3" />
          <ul className="grid gap-1">
            {["전체 부서", ...busy, ...(idleOpen ? idle : [])].map((n) => {
              const total = n === "전체 부서" ? doingAll.length : countOf(n), on = selected === n;
              return (
                <li key={n}>
                  <button onClick={() => { setUi({ department: n }); setPage(1); }} aria-pressed={on} className={cn("grid w-full gap-1.5 rounded-xl px-3 py-2.5 text-left text-sm transition-colors", on ? "bg-[#003377] text-white" : "hover:bg-muted")}>
                    <span className="flex items-center justify-between gap-3">
                      <span className="truncate font-medium">{n}</span>
                      <span className={cn("shrink-0 tabular-nums", on ? "text-white/80" : "text-muted-foreground")}><b className={cn("font-medium", !on && "text-foreground")}>{total}</b>건</span>
                    </span>
                    {n !== "전체 부서" && total > 0 && (
                      // 막대 길이 = 요청 건수(가장 많은 부서 기준)
                      <span className={cn("flex h-2 overflow-hidden rounded-full", on ? "bg-white/20" : "bg-muted")} style={{ width: `${(total / widest) * 100}%` }} role="img" aria-label={`진행 중 ${total}건`}>
                        <span className={cn("h-full w-full", BARS[0].tone)} />
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
            {idle.length > 0 && !idle.includes(selected) && (
              <li><button onClick={() => setShowIdle((v) => !v)} aria-expanded={idleOpen} className="flex w-full items-center gap-1.5 rounded-xl px-3 py-2.5 text-left text-sm text-muted-foreground transition-colors hover:bg-muted">{idleOpen ? "접기" : `요청 없는 부서 ${idle.length}개`}<ChevronDown className={cn("size-4 transition-transform", idleOpen && "rotate-180")} aria-hidden /></button></li>
            )}
          </ul>
        </section>
      </div>
    </>
  );
}

const COLS = "grid-cols-[minmax(0,1fr)_84px_112px_120px_16px]";
/** 표 한 줄: 문의(제목 + 번호·요청 부서 → 대상 부서) · 상태 태그 · 경과(도착/요청 후) · SLA · 담당자. 누르면 요청·회신 화면이 열린다. */
function CollabRow({ r, phase, onOpen }: { r: Row; phase: "review" | "waiting"; onOpen: () => void }) {
  const since = phase === "review" ? (r.response?.createdAt ? Date.parse(r.response.createdAt) : NaN) : (r.when ? Date.parse(r.when) : NaN);
  const h = Number.isFinite(since) ? Math.max(0, (Date.now() - since) / 3600e3) : null;
  return (
    <div role="link" tabIndex={0} aria-label={`${r.ticket.title} 요청·회신 열기`} onClick={onOpen} onKeyDown={(e) => e.target === e.currentTarget && e.key === "Enter" && onOpen()}
      className={cn("group grid cursor-pointer items-center gap-4 px-6 py-[18px] transition-colors hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:outline-none", COLS)}>
      <div className="grid min-w-0 gap-1">
        <span className="truncate font-medium">{r.ticket.title}</span>
        <span className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground"><Mono>{r.ticket.id}</Mono><span aria-hidden>·</span><span className="truncate">{r.source || "부서 미기록"}</span><ArrowRight className="size-3 shrink-0" aria-hidden /><span className="truncate font-medium text-foreground">{r.target || "부서 미기록"}</span></span>
      </div>
      <span className="text-center text-sm tabular-nums text-muted-foreground">{h === null ? "미기록" : fmtWait(h)}</span>
      <span className="justify-self-center"><SlaTag t={r.ticket} /></span>
      <span className="flex min-w-0 items-center gap-2 text-sm text-muted-foreground">{r.ticket.owner ? <><PersonAvatar name={r.ticket.owner} size={20} /><span className="truncate">{r.ticket.owner}</span></> : "미배정"}</span>
      <ChevronRight className="size-4 text-muted-foreground/40 transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" aria-hidden />
    </div>
  );
}
