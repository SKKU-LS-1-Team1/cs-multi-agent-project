// 전문부서 협업: 전문부서에 맡겨 놓고 "회신을 기다리는 요청"만 관리한다.
// 왼쪽 = 회신 대기 카드(요청 후 경과 시간·회신 등록), 오른쪽 = 부서별 대기(건수 막대를 기다린 시간 구간으로 나눠 어느 부서가 오래 묵었는지 보인다).
// 회신이 온 뒤의 일(답변 작성)은 "오늘 내가 할 일"과 문의 상세가 안내하므로 여기에는 두지 않는다.
import { useState } from "react";
import { ArrowRight, ChevronDown } from "lucide-react";
import { Button } from "@admin/components/ui/button";
import { PageHeader, SlaTag, rise, useGo } from "@admin/components/admin/common";
import { departmentRisk, departmentReviewRows, referralDepartments, referralRows } from "@admin/lib/logic";
import { openModal, setUi, ui, useStore } from "@admin/lib/store";
import { cn } from "@admin/lib/utils";

type Row = ReturnType<typeof referralRows>[number];
/** 요청한 뒤 지난 시간(시간 단위). 없거나 해석할 수 없는 시각은 미기록으로 둔다. */
const waitedHours = (r: Row): number | null => {
  const timestamp = r.when ? Date.parse(r.when) : NaN;
  return Number.isFinite(timestamp) ? Math.max(0, (Date.now() - timestamp) / 3600e3) : null;
};
const fmtWait = (h: number) => (h < 1 ? "1시간 미만" : h < 24 ? `${Math.floor(h)}시간` : `${Math.floor(h / 24)}일 ${Math.floor(h % 24)}시간`);
/** SLA 위험인 요청을 먼저, 그다음 오래 기다린 순. */
const byUrgency = (a: Row, b: Row) => Number(departmentRisk(b.ticket)) - Number(departmentRisk(a.ticket)) || (waitedHours(b) ?? -1) - (waitedHours(a) ?? -1);
/** 이만큼 기다리면 경과 시간을 강조한다. */
const NUDGE_HOURS = 24;

/** 기다린 시간 구간: 막대 색. 시각이 없는 요청은 회색으로 둔다. */
const WAIT_BANDS = [
  { key: "day", label: "24시간 이내", tone: "bg-info/45" },
  { key: "days", label: "1~3일", tone: "bg-warning" },
  { key: "long", label: "3일 이상", tone: "bg-destructive" },
  { key: "none", label: "시각 미기록", tone: "bg-muted-foreground/30" },
] as const;
const waitBand = (r: Row) => { const h = waitedHours(r); return h === null ? "none" : h < 24 ? "day" : h < 72 ? "days" : "long"; };

// BACKEND: 전문부서 재요청(독촉)은 아직 없다. 생기면 POST /tickets/{id}/specialist-requests/{request_id}/remind 로 카드에 버튼을 붙인다.

export default function Collab({ tabs }: { tabs: React.ReactNode }) {
  useStore();
  const go = useGo();
  const [showIdle, setShowIdle] = useState(false);

  const waitingAll = referralRows().filter((r) => !r.response && r.ticket.stage !== 5);
  const names = referralDepartments();
  const selected = ui.department !== "전체 부서" && !names.includes(ui.department) ? "전체 부서" : ui.department;
  const pending = (selected === "전체 부서" ? waitingAll : departmentReviewRows(selected).filter((r) => !r.response && r.ticket.stage !== 5)).sort(byUrgency);
  // 부서별 현황: 대기가 있는 부서만 먼저(많은 순), 대기 없는 부서는 접어 둔다. 부서 목록 자체는 그대로다.
  const waitOf = (n: string) => (n === "전체 부서" ? waitingAll : waitingAll.filter((r) => (r.target || "대상 부서 미기록") === n)).length;
  const busy = names.filter((n) => waitOf(n) > 0).sort((a, b) => waitOf(b) - waitOf(a));
  const idle = names.filter((n) => !busy.includes(n));
  const idleOpen = showIdle || idle.includes(selected);
  const rowsOf = (n: string) => (n === "전체 부서" ? waitingAll : waitingAll.filter((r) => (r.target || "대상 부서 미기록") === n));
  const widest = Math.max(1, ...busy.map(waitOf));


  return (
    <>
      <PageHeader title="전문부서 협업 현황">{tabs}</PageHeader>
      <div className="grid grid-cols-[minmax(0,1fr)_340px] items-start gap-5 px-10 pb-12">
        <section aria-label="회신 대기" className="grid gap-4">
          <h2 className="px-1 text-lg font-medium">회신 대기 <span className="tabular-nums text-muted-foreground">{pending.length}</span></h2>
          <div className="grid grid-cols-2 gap-4">
            {pending.map((r, i) => <Card key={r.key} r={r} order={i + 1} onOpen={() => (r.event ? openModal("department-review", { key: r.key }) : go.ticket(r.ticket.id))} />)}
          </div>
          {!pending.length && <p style={rise(1).style} className={cn("rounded-2xl bg-card py-12 text-center text-sm text-muted-foreground shadow-card", rise(1).className)}>회신을 기다리는 요청이 없습니다.</p>}
        </section>

        <section aria-label="부서별 현황" style={rise(0).style} className={cn("rounded-2xl bg-card p-6 shadow-card", rise(0).className)}>
          <h2 className="text-lg font-medium">부서별 현황</h2>
          <ul className="mb-3 mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground" aria-label="기다린 시간">
            {WAIT_BANDS.filter((b) => b.key !== "none" || waitingAll.some((r) => waitBand(r) === "none")).map((b) => <li key={b.key} className="flex items-center gap-1.5"><span aria-hidden className={cn("size-2 rounded-full", b.tone)} />{b.label}</li>)}
          </ul>
          <ul className="grid gap-1">
            {["전체 부서", ...busy, ...(idleOpen ? idle : [])].map((n) => {
              const rows = rowsOf(n), on = selected === n;
              return (
                <li key={n}>
                  <button onClick={() => setUi({ department: n })} aria-pressed={on} className={cn("grid w-full gap-1.5 rounded-xl px-3 py-2.5 text-left text-sm transition-colors", on ? "bg-[#003377] text-white" : "hover:bg-muted")}>
                    <span className="flex items-center justify-between gap-3">
                      <span className="truncate font-medium">{n}</span>
                      <span className={cn("shrink-0 tabular-nums", on ? "text-white/80" : "text-muted-foreground")}><b className={cn("font-medium", !on && "text-foreground")}>{rows.length}</b> 대기</span>
                    </span>
                    {n !== "전체 부서" && rows.length > 0 && (
                      // 막대 길이 = 대기 건수(가장 많은 부서 기준), 색 = 기다린 시간 구간
                      <span className={cn("flex h-2 overflow-hidden rounded-full", on ? "bg-white/20" : "bg-muted")} style={{ width: `${(rows.length / widest) * 100}%` }}
                        role="img" aria-label={WAIT_BANDS.map((b) => `${b.label} ${rows.filter((r) => waitBand(r) === b.key).length}건`).join(", ")}>
                        {WAIT_BANDS.map((b) => { const k = rows.filter((r) => waitBand(r) === b.key).length; return k > 0 && <span key={b.key} className={cn("h-full", b.tone)} style={{ width: `${(k / rows.length) * 100}%` }} />; })}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
            {idle.length > 0 && !idle.includes(selected) && (
              <li><button onClick={() => setShowIdle((v) => !v)} aria-expanded={idleOpen} className="flex w-full items-center gap-1.5 rounded-xl px-3 py-2.5 text-left text-sm text-muted-foreground transition-colors hover:bg-muted">{idleOpen ? "접기" : `대기 없는 부서 ${idle.length}개`}<ChevronDown className={cn("size-4 transition-transform", idleOpen && "rotate-180")} aria-hidden /></button></li>
            )}
          </ul>
        </section>
      </div>
    </>
  );
}

function Card({ r, onOpen, order }: { r: Row; onOpen: () => void; order: number }) {
  const h = waitedHours(r), late = h !== null && h >= NUDGE_HOURS;
  return (
    <article onClick={onOpen} style={rise(order).style} className={cn("grid cursor-pointer gap-3 rounded-2xl bg-card p-5 shadow-card transition-shadow hover:shadow-float", rise(order).className, departmentRisk(r.ticket) && "ring-1 ring-destructive/40")}>
      <div className="grid gap-1">
        <h3 className="font-semibold leading-snug">{r.ticket.title}</h3>
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground"><span className="truncate">{r.source || "부서 미기록"}</span><ArrowRight className="size-3.5 shrink-0" aria-hidden /><span className="truncate font-medium text-foreground">{r.target || "부서 미기록"}</span></p>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <span className={cn(late ? "font-medium text-warning-ink" : "text-muted-foreground")}>{h === null ? "요청 시각 미기록" : `요청 후 ${fmtWait(h)}`}</span>
        <SlaTag t={r.ticket} />
      </div>
      <div className="flex justify-end gap-2" onClick={(e) => e.stopPropagation()}>
        <Button size="sm" onClick={() => openModal("expert-receive", { id: r.ticket.id, requestId: r.requestId || undefined })}>회신 등록</Button>
      </div>
    </article>
  );
}
