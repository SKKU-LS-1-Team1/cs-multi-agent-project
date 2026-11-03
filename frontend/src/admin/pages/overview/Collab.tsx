// 전문부서 협업 = 문의 목록 "3/6 전문부서" 단계를 문의 전체에 걸쳐 본 화면. 하위 상태는 expertPhase 와 같다.
// 왼쪽 위 = 회신 도착·검토 필요(공이 우리에게 있다: 담당자가 확인해야 4단계로 넘어간다), 왼쪽 아래 = 회신 대기(회신 대기 시간·회신 등록)
// 오른쪽 = 부서별 대기(건수 막대를 기다린 시간 구간으로 나눠 어느 부서가 오래 묵었는지 보인다).
// 요청서 작성 중(writing)은 부서와 오가는 일이 아니라 담당자 본인의 작업이라 "할 일"에 둔다. 검토가 끝난 뒤의 답변 작성도 "할 일"과 문의 상세가 안내한다.
import { useState } from "react";
import { ArrowRight, ChevronDown } from "lucide-react";
import { Button } from "@admin/components/ui/button";
import { PageHeader, SlaTag, Tag, rise, useGo } from "@admin/components/admin/common";
import { departmentRisk, departmentReviewRows, expertPhase, referralDepartments, referralRows } from "@admin/lib/logic";
import { openModal, setUi, ui, useStore } from "@admin/lib/store";
import { cn } from "@admin/lib/utils";

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

  const waitingAll = referralRows().filter((r) => (!r.response || r.ticket.specialistFollowup?.status === "in_progress") && r.ticket.stage !== 5);
  const names = referralDepartments();
  const inReview = (r: Row) => !!r.response && !r.response.reviewed && r.ticket.stage !== 5 && expertPhase(r.ticket) === "review";
  const reviewAll = referralRows().filter(inReview);
  const selected = ui.department !== "전체 부서" && !names.includes(ui.department) ? "전체 부서" : ui.department;
  const pending = (selected === "전체 부서" ? waitingAll : departmentReviewRows(selected).filter((r) => (!r.response || r.ticket.specialistFollowup?.status === "in_progress") && r.ticket.stage !== 5)).sort(byUrgency);
  const toReview = (selected === "전체 부서" ? reviewAll : reviewAll.filter((r) => (r.target || "대상 부서 미기록") === selected)).sort((a, b) => Number(departmentRisk(b.ticket)) - Number(departmentRisk(a.ticket)) || (Date.parse(a.response.createdAt || "") || 0) - (Date.parse(b.response.createdAt || "") || 0));
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
        <div className="grid gap-8">
        {toReview.length > 0 && (
          <section aria-label="회신 도착" className="grid gap-4">
            <h2 className="px-1 text-lg font-medium">회신 도착 · 검토 필요 <span className="tabular-nums text-muted-foreground">{toReview.length}</span></h2>
            <div className="grid grid-cols-2 gap-4">
              {toReview.map((r, i) => <ReviewCard key={r.key} r={r} order={i + 1} />)}
            </div>
          </section>
        )}
        <section aria-label="회신 대기" className="grid gap-4">
          <h2 className="px-1 text-lg font-medium">회신 대기·사내 분석 <span className="tabular-nums text-muted-foreground">{pending.length}</span></h2>
          <div className="grid grid-cols-2 gap-4">
            {pending.map((r, i) => <Card key={r.key} r={r} order={i + 1} onOpen={() => (r.event ? openModal("department-review", { key: r.key }) : go.ticket(r.ticket.id))} />)}
          </div>
          {!pending.length && <p style={rise(1).style} className={cn("rounded-2xl bg-card py-12 text-center text-sm text-muted-foreground shadow-card", rise(1).className)}>진행 중인 전문부서 요청이 없습니다.</p>}
        </section>
        </div>

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
                      <span className={cn("shrink-0 tabular-nums", on ? "text-white/80" : "text-muted-foreground")}><b className={cn("font-medium", !on && "text-foreground")}>{rows.length}</b> 진행</span>
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

/** 회신이 도착해 담당자 확인을 기다리는 요청. 누르면 요청·회신 비교 화면(반영/추가 질의/고객 자료 요청)이 열린다. */
function ReviewCard({ r, order }: { r: Row; order: number }) {
  const got = r.response?.createdAt ? Date.parse(r.response.createdAt) : NaN;
  const h = Number.isFinite(got) ? Math.max(0, (Date.now() - got) / 3600e3) : null;
  return (
    <article onClick={() => openModal("department-review", { key: r.key })} style={rise(order).style} className={cn("grid cursor-pointer gap-3 rounded-2xl bg-card p-5 shadow-card transition-shadow hover:shadow-float", rise(order).className, departmentRisk(r.ticket) && "ring-1 ring-destructive/40")}>
      <div className="grid gap-1">
        <h3 className="font-semibold leading-snug">{r.ticket.title}</h3>
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground"><span className="truncate font-medium text-foreground">{r.target || "부서 미기록"}</span><span className="shrink-0">회신</span></p>
        <p className="line-clamp-2 text-sm text-muted-foreground">{r.response.text}</p>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <Tag tone="blue">{h === null ? "회신 시각 미기록" : `도착 ${fmtWait(h)} 전`}</Tag>
        <SlaTag t={r.ticket} prefix="SLA " />
      </div>
      <div className="flex justify-end" onClick={(e) => e.stopPropagation()}>
        <Button size="sm" onClick={() => openModal("department-review", { key: r.key })}>회신 검토</Button>
      </div>
    </article>
  );
}

function Card({ r, onOpen, order }: { r: Row; onOpen: () => void; order: number }) {
  const go = useGo();
  const goToInquiry = (id: string) => go.ticket(id);
  const h = waitedHours(r);
  return (
    <article onClick={onOpen} style={rise(order).style} className={cn("grid cursor-pointer gap-3 rounded-2xl bg-card p-5 shadow-card transition-shadow hover:shadow-float", rise(order).className, departmentRisk(r.ticket) && "ring-1 ring-destructive/40")}>
      <div className="grid gap-1">
        <h3 className="font-semibold leading-snug">{r.ticket.title}</h3>
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground"><span className="truncate">{r.source || "부서 미기록"}</span><ArrowRight className="size-3.5 shrink-0" aria-hidden /><span className="truncate font-medium text-foreground">{r.target || "부서 미기록"}</span></p>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <Tag>{h === null ? "요청 시각 미기록" : `회신 대기 ${fmtWait(h)}`}</Tag>
        <SlaTag t={r.ticket} prefix="SLA " />
      </div>
      <div className="flex justify-end gap-2" onClick={(e) => e.stopPropagation()}>
        <Button size="sm" onClick={() => r.response ? goToInquiry(r.ticket.id) : openModal("expert-receive", { id: r.ticket.id, requestId: r.requestId || undefined })}>{r.response ? "사내 분석 확인" : "회신 등록"}</Button>
      </div>
    </article>
  );
}
