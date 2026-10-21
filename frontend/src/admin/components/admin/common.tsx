import type { ComponentProps, ReactNode } from "react";
import { AlarmClock, Check, ChevronRight, Clock, UserRound, type LucideIcon } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Badge } from "@admin/components/ui/badge";
import { cn } from "@admin/lib/utils";
import { findTicket, setUi } from "@admin/lib/store";
import { departmentRisk, overdue, signedIn, ticketProgress, unreadReplies } from "@admin/lib/logic";
import type { Ticket } from "@admin/lib/types";

const TONES = {
  red: "bg-destructive/10 text-destructive",
  green: "bg-success/10 text-success",
  blue: "bg-info/10 text-info",
  amber: "bg-warning/20 text-warning-ink",
} as const;
/** 각진 채움 태그. 테두리·알약 모양 없이 색 면과 글자 색으로만 구분한다. */
export function Tag({ tone, children, className }: { tone?: keyof typeof TONES | ""; children: ReactNode; className?: string }) {
  return <Badge variant="secondary" className={cn("h-5 rounded-[3px] px-1.5 font-medium", tone ? TONES[tone] : "bg-muted text-foreground/80", className)}>{children}</Badge>;
}
export const PriorityTag = ({ p, urgent }: { p: string; urgent?: boolean }) => <Tag tone={urgent ?? p === "P2" ? "red" : ""} className="font-semibold tabular-nums">{p}</Tag>;
const DOT = { green: "bg-success", blue: "bg-info", muted: "bg-muted-foreground/50" };
/** 진행 상태는 점 + 글자로 가볍게. */
export const StatusTag = ({ t }: { t: Ticket }) => {
  const tone = t.stage === 5 ? "green" : !t.owner ? "blue" : "muted";
  return <span className="inline-flex items-center gap-1.5 text-sm"><span aria-hidden className={cn("size-1.5 rounded-full", DOT[tone])} />{ticketProgress(t)}</span>;
};

/** SLA 상태를 한눈에: 초과(빨강) / 임박(노랑) / 완료(초록) / 정상(글자). */
export function SlaTag({ t }: { t: Ticket }) {
  if (t.stage === 5) return <Tag tone="green">{t.sla}</Tag>;
  if (overdue(t)) return <Tag tone="red">{t.sla}</Tag>;
  if (t.risk) return <Tag tone="amber">임박 {t.sla}</Tag>;
  return <span className="text-sm tabular-nums text-muted-foreground">{t.sla}</span>;
}

export function PageHeader({ title, actions, children }: { title: string; actions?: ReactNode; children?: ReactNode }) {
  return (
    <div className="grid gap-5 px-10 pb-6 pt-10">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-[32px] font-normal tracking-tight">{title}</h1>
        {actions}
      </div>
      {children}
    </div>
  );
}

/** 밑줄 탭: 선택한 탭만 진하게, 나머지는 흐리게. */
export function UnderlineTabs<T extends string>({ tabs, value, onChange, className }: { tabs: readonly (readonly [T, string])[]; value: T; onChange: (v: T) => void; className?: string }) {
  return (
    <div role="tablist" className={cn("flex gap-7 border-b", className)}>
      {tabs.map(([key, label]) => (
        <button key={key} role="tab" aria-selected={value === key} onClick={() => onChange(key)}
          className={cn("-mb-px border-b-2 pb-3 text-[15px] transition-colors", value === key ? "border-foreground font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
          {label}
        </button>
      ))}
    </div>
  );
}

/** 홈 화면의 행동 타일: 원형 아이콘 + 이름 + 한 줄 현황. */
export function ActionTile({ icon: Icon, label, sub, tone, onClick }: { icon: LucideIcon; label: string; sub?: ReactNode; tone?: "red" | "amber" | ""; onClick: () => void }) {
  return (
    <button onClick={onClick} className="group grid h-full content-between gap-5 rounded-2xl bg-card p-5 text-left shadow-card transition-all hover:-translate-y-0.5 hover:shadow-float">
      <span className={cn("grid size-10 place-items-center rounded-full text-white", tone === "red" ? "bg-destructive" : tone === "amber" ? "bg-[#c98f00]" : "bg-[#003377]")}><Icon className="size-[18px]" aria-hidden /></span>
      <span className="grid gap-0.5"><span className="font-semibold">{label}</span>{sub && <span className="text-sm text-muted-foreground">{sub}</span>}</span>
    </button>
  );
}
export function NativeSelect({ className, ...p }: ComponentProps<"select">) {
  return <select {...p} className={cn("h-9 rounded-lg border border-input bg-card px-3 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/40", className)} />;
}
export function Field({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return <label className={cn("grid gap-1.5 text-sm", className)}><span className="text-muted-foreground">{label}</span>{children}</label>;
}
export function Facts({ rows, className }: { rows: [string, ReactNode][]; className?: string }) {
  return (
    <dl className={cn("grid grid-cols-[104px_minmax(0,1fr)] gap-x-4 gap-y-2.5 text-sm", className)}>
      {rows.map(([k, v]) => (
        <div key={k} className="contents"><dt className="text-muted-foreground">{k}</dt><dd className="min-w-0 break-words">{v}</dd></div>
      ))}
    </dl>
  );
}
export const Empty = ({ children }: { children: ReactNode }) => <div className="px-6 py-12 text-center text-sm text-muted-foreground">{children}</div>;

/** 페이지 이동 헬퍼: 레거시 go() 의 화면 상태 초기화 규칙을 따른다. */
export function useGo() {
  const nav = useNavigate();
  return {
    ticket(id: string) {
      const t = findTicket(id);
      setUi({ queueScope: t && t.owner === signedIn && t.stage !== 5 ? "내 담당" : "전체", tab: "문의·답변" });
      nav("/tickets/" + id);
    },
    list(patch: Record<string, any> = {}) {
      setUi({ listDepartment: "", listOwner: "", ...patch });
      nav("/tickets");
    },
    to: nav,
  };
}

/** 티켓 상태를 원형 아이콘 하나로: 완료(초록) / 위험(빨강) / 미배정(노랑) / 진행(회색). */
export function StatusIcon({ t }: { t: Ticket }) {
  const [Icon, cls] = t.stage === 5 ? [Check, "bg-success/12 text-success"] : departmentRisk(t) ? [AlarmClock, "bg-destructive/12 text-destructive"] : !t.owner ? [UserRound, "bg-[#f2b705]/20 text-[#8a6500]"] : [Clock, "bg-muted text-muted-foreground"];
  return <span className={cn("grid size-10 shrink-0 place-items-center rounded-full", cls)}><Icon className="size-[18px]" aria-hidden /></span>;
}

/** 목록 한 줄: 아이콘 · 제목과 메타 · 오른쪽에 SLA와 담당자. 한 줄에 정보는 두세 개만. */
export function TicketRow({ t, onOpen, lead }: { t: Ticket; onOpen: () => void; lead?: ReactNode }) {
  return (
    <div role="button" tabIndex={0} aria-label={`${t.title} 상세 열기`} onClick={onOpen} onKeyDown={(e) => e.target === e.currentTarget && e.key === "Enter" && onOpen()}
      className="group grid cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto_16px] items-center gap-4 px-5 py-3.5 transition-colors hover:bg-muted/70">
      {lead ?? <StatusIcon t={t} />}
      <div className="min-w-0"><div className="flex items-center gap-2"><span className="truncate font-medium">{t.title}</span>{unreadReplies(t) > 0 && <Tag tone="blue" className="shrink-0">새 회신</Tag>}</div><div className="truncate text-xs text-muted-foreground">{t.id} · {t.product} · {t.country}</div></div>
      <div className="grid justify-items-end gap-0.5 text-right"><SlaTag t={t} /><span className={cn("text-xs", t.owner ? "text-muted-foreground" : "font-medium text-[#8a6500]")}>{t.owner || "미배정"}</span></div>
      <ChevronRight className="size-4 text-muted-foreground/40 transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" aria-hidden />
    </div>
  );
}
