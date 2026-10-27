// 고객 관리: 표 하나로 보는 두 가지 — 중점 관리(매일 먼저 보는 곳) · 전체(찾아보기). 검색·필터는 탭마다 따로.
// 줄 하나 = 고객 하나(이름·업종·국가 / 등급 / 사실 / 상태 / 버튼). 국기는 표에서 쓰지 않고, 지난 대응 이력은 고객 상세에서 본다.
import { useMemo, useState } from "react";
import { ChevronDown, ChevronLeft, ChevronRight, Search, SlidersHorizontal } from "lucide-react";
import { Button } from "@admin/components/ui/button";
import { Input } from "@admin/components/ui/input";
import { CareButtons } from "@admin/components/admin/CareButtons";
import { CareTag, PageHeader, Tag, TierTag, UnderlineTabs, useGo } from "@admin/components/admin/common";
import { careStatus, recordOf, useCare } from "@admin/lib/care";
import { factParts, flag, focusOf, maxLate, monthsSince, primaryReason, score, SEGMENT_KO, useCustomers, type Customer } from "@admin/lib/customers";
import { cn } from "@admin/lib/utils";

type Tab = "focus" | "all";
type Flt = { tier: string; country: string; seg: string; quiet: string; sort: string };
const NO_FLT: Flt = { tier: "", country: "", seg: "", quiet: "", sort: "default" };
const RANK = { issue: 0, pinned: 1 } as const;
/** 중점 관리 카드의 순서: 결과 확인할 때(0) → 아직 대응 전(1) → 대응 중(2). */
const STATUS_RANK = { due: 0, none: 1, acted: 2, resolved: 3 } as const;
const md = (iso: string) => iso.slice(5, 10).replace("-", ".");
const SIZE = 15;
const SORTS: [string, string][] = [["default", "중요도순"], ["recent", "최근 문의순"], ["oldest", "오래된 문의순"], ["most", "문의 많은 순"]];
const TIER_RANK = { PLATINUM: 0, GOLD: 1, STANDARD: 2 } as const;

/** 페이지 번호: 현재 페이지 앞뒤와 처음·끝만 보이고 나머지는 … 로 줄인다. */
function Pager({ page, size, total, onChange }: { page: number; size: number; total: number; onChange: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / size));
  if (pages <= 1) return null;
  const nums = [...new Set([1, pages, page - 1, page, page + 1].filter((n) => n >= 1 && n <= pages))].sort((a, b) => a - b);
  const items: (number | "…")[] = [];
  nums.forEach((n, i) => { if (i && n - nums[i - 1] > 1) items.push("…"); items.push(n); });
  const go = (p: number) => { onChange(p); window.scrollTo({ top: 0, behavior: "smooth" }); };
  return (
    <nav aria-label="페이지" className="flex items-center justify-between gap-4 pt-2">
      <span className="text-sm tabular-nums text-muted-foreground">{(page - 1) * size + 1}–{Math.min(page * size, total)} / {total}곳</span>
      <div className="flex items-center gap-1">
        <button aria-label="이전 페이지" disabled={page === 1} onClick={() => go(page - 1)} className="grid size-9 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-muted disabled:opacity-30"><ChevronLeft className="size-4" /></button>
        {items.map((n, i) => n === "…" ? <span key={"g" + i} className="px-1 text-muted-foreground">…</span> : <button key={n} aria-current={n === page ? "page" : undefined} onClick={() => go(n)} className={cn("h-9 min-w-9 rounded-full px-3 text-sm tabular-nums transition-colors", n === page ? "bg-[#003377] font-medium text-white" : "text-muted-foreground hover:bg-muted")}>{n}</button>)}
        <button aria-label="다음 페이지" disabled={page === pages} onClick={() => go(page + 1)} className="grid size-9 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-muted disabled:opacity-30"><ChevronRight className="size-4" /></button>
      </div>
    </nav>
  );
}

/** 필터 선택: 보이는 글자에 맞춰 너비가 정해져 화살표가 글자 바로 옆에 붙는다. 값이 걸려 있으면 남색으로 보인다. 실제 선택은 투명한 select 가 받는다. */
function FilterSelect({ label, value, options, onChange }: { label: string; value: string; options: [string, string][]; onChange: (v: string) => void }) {
  const on = value !== "", shown = options.find(([v]) => v === value)?.[1] ?? label;
  return (
    <label className={cn("relative inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-full pl-4 pr-3 text-sm transition-colors focus-within:ring-3 focus-within:ring-ring/40", on ? "bg-[#003377] text-white" : "bg-card text-foreground shadow-card hover:bg-muted")}>
      <span>{shown}</span><ChevronDown className="size-3.5 opacity-70" aria-hidden />
      <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} className="absolute inset-0 size-full cursor-pointer opacity-0">
        <option value="">{label}</option>{options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  );
}

const Num = ({ n }: { n?: number }) => <span className="ml-1.5 text-sm font-normal tabular-nums text-muted-foreground">{n ?? ""}</span>;
/** 표: 머리글 한 줄 + 고객당 한 줄. 줄 전체를 누르면 고객 상세. */
const FOCUS_COLS = "grid-cols-[minmax(0,2.4fr)_96px_minmax(0,1.4fr)_minmax(0,1.3fr)_104px_156px]";
const ALL_COLS = "grid-cols-[minmax(0,2.4fr)_96px_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_104px]";
function Table({ cols, heads, children }: { cols: string; heads: string[]; children: React.ReactNode }) {
  return (
    <div className="overflow-hidden rounded-2xl bg-card shadow-card">
      <div className={cn("grid items-center gap-4 px-7 pb-3 pt-5 text-sm text-muted-foreground", cols)}>{heads.map((h, i) => <span key={i}>{h}</span>)}</div>
      <div className="divide-y border-t">{children}</div>
    </div>
  );
}
function Row({ c, cols, onOpen, children }: { c: Customer; cols: string; onOpen: () => void; children: React.ReactNode }) {
  return (
    <div role="link" tabIndex={0} aria-label={`${c.name} 상세`} onClick={onOpen} onKeyDown={(e) => e.target === e.currentTarget && e.key === "Enter" && onOpen()}
      className={cn("grid cursor-pointer items-center gap-4 px-7 py-[18px] transition-colors hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:outline-none", cols)}>
      {children}
    </div>
  );
}
/** 작은 게이지: 값이 얼마나 큰지 한눈에. 칸 너비를 꽉 채우지 않고 가늘게 그린다. */
const Gauge = ({ value, max, tone }: { value: number; max: number; tone: string }) => (
  <span aria-hidden className="block h-1.5 w-full max-w-[140px] overflow-hidden rounded-full bg-muted"><span className={cn("block h-full rounded-full", tone)} style={{ width: `${Math.max(6, Math.min(100, (value / max) * 100))}%` }} /></span>
);
const LATE_MAX = 30; // 지연 게이지는 30일을 가득 찬 값으로 본다
/** 고객 칸: 이름 + 업종·국가 한 줄(국기 없이 글자로). */
const Who = ({ c }: { c: Customer }) => (
  <span className="grid min-w-0 gap-0.5"><span className="truncate font-semibold">{c.name}</span><span className="truncate text-sm text-muted-foreground">{SEGMENT_KO[c.seg] || c.seg} · {c.cn}</span></span>
);
/** 사실 표시는 면을 칠하지 않고 점 + 글자색만 쓴다. 7일 이상 지연은 값 글자만 빨강. */
const DOT: Record<"severe" | "red" | "amber" | "blue", string> = { severe: "bg-destructive", red: "bg-destructive/70", amber: "bg-warning", blue: "bg-info" };

export default function Customers() {
  const go = useGo();
  const { rows, error } = useCustomers();
  const care = useCare();
  const [tab, setTab] = useState<Tab>("focus");
  const [page, setPage] = useState(1), [showFilters, setShowFilters] = useState(false);
  // 검색어·필터는 탭마다 따로 가진다(한 탭에서 걸어도 다른 탭엔 영향 없음).
  const [flts, setFlts] = useState<Record<Tab, Flt>>({ focus: NO_FLT, all: NO_FLT });
  const [qs, setQs] = useState<Record<Tab, string>>({ focus: "", all: "" });
  const flt = flts[tab], q = qs[tab];
  const open = (c: Customer) => go.to("/customers/" + c.id);
  const reset = () => setPage(1);
  const setF = (p: Partial<Flt>) => { setFlts((x) => ({ ...x, [tab]: { ...x[tab], ...p } })); setPage(1); };
  const active = [flt.tier, flt.country, flt.seg].filter(Boolean).length + (flt.sort !== "default" ? 1 : 0);
  const countries = useMemo(() => { const m = new Map<string, { c: string; cn: string; n: number }>(); for (const c of rows || []) m.set(c.c, { c: c.c, cn: c.cn, n: (m.get(c.c)?.n || 0) + 1 }); return [...m.values()].sort((a, b) => b.n - a.n); }, [rows]);

  const st = (c: Customer) => careStatus(care[c.id]);
  const passes = (c: Customer, t: Tab) => {
    const f = flts[t], k = qs[t].trim().toLowerCase();
    return (!k || [c.name, c.cn, SEGMENT_KO[c.seg] || c.seg].join(" ").toLowerCase().includes(k)) && (!f.tier || c.tier === f.tier) && (!f.country || c.c === f.country) && (!f.seg || c.seg === f.seg);
  };

  // 중점 관리: 가장 오래 지연된 순. 결과 확인할 때 → 대응 전 → 대응 중 순으로 먼저 보인다.
  const focusRows = useMemo(() => (rows || []).map((c) => ({ c, f: focusOf(c, care[c.id]) })).filter((x) => x.f && passes(x.c, "focus"))
    .sort((a, b) => RANK[a.f!] - RANK[b.f!] || STATUS_RANK[st(a.c)] - STATUS_RANK[st(b.c)] || maxLate(b.c) - maxLate(a.c) || score(b.c) - score(a.c)), [rows, care, flts, qs]); // eslint-disable-line react-hooks/exhaustive-deps
  const allRows = useMemo(() => {
    const by: Record<string, (a: Customer, b: Customer) => number> = {
      default: (a, b) => TIER_RANK[a.tier] - TIER_RANK[b.tier] || score(b) - score(a),
      recent: (a, b) => b.last.localeCompare(a.last), oldest: (a, b) => a.last.localeCompare(b.last), most: (a, b) => b.n - a.n,
    };
    return (rows || []).filter((c) => passes(c, "all")).sort(by[flts.all.sort]);
  }, [rows, flts, qs]); // eslint-disable-line react-hooks/exhaustive-deps
  const nFocus = (rows || []).filter((c) => focusOf(c, care[c.id])).length;

  const maxN = Math.max(1, ...(rows || []).map((c) => c.n)), maxBreach = Math.max(1, ...(rows || []).map((c) => c.breach));
  const Empty = ({ children }: { children: React.ReactNode }) => <p className="rounded-2xl bg-card px-6 py-14 text-center text-sm text-muted-foreground shadow-card">{children}</p>;

  return (
    <>
      <PageHeader title="고객 관리">
        <UnderlineTabs tabs={[["focus" as Tab, <>중점 관리<Num n={rows ? nFocus : undefined} /></>], ["all" as Tab, <>전체<Num n={rows?.length} /></>]] as const} value={tab} onChange={(v) => { setTab(v); reset(); }} />
      </PageHeader>
      {rows && error && <p role="alert" className="px-10 py-3 text-destructive">{error} 마지막 조회 정보를 표시합니다.</p>}
      {!rows ? <p className="px-10 py-16 text-center text-sm text-muted-foreground">{error || "불러오는 중입니다."}</p> : (
        <div className="grid gap-6 px-10 pb-14">
          <div className="grid gap-3">
            <div className="flex items-center gap-2">
              <Button variant={showFilters || active > 0 ? "secondary" : "ghost"} aria-expanded={showFilters} onClick={() => setShowFilters((v) => !v)}><SlidersHorizontal />필터{active > 0 && <span className="tabular-nums text-info"> {active}</span>}</Button>
              {active > 0 && <Button size="sm" variant="ghost" onClick={() => { setFlts((x) => ({ ...x, [tab]: NO_FLT })); setPage(1); }}>초기화</Button>}
              <div className="relative ml-auto"><Search className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden /><Input aria-label="고객 검색" className="h-10 w-64 rounded-full bg-card pl-10 shadow-card" placeholder="회사·업종 검색" value={q} onChange={(e) => { setQs((x) => ({ ...x, [tab]: e.target.value })); reset(); }} /></div>
            </div>
            {showFilters && (
              <div className="flex flex-wrap items-center gap-2">
                <FilterSelect label="전체 등급" value={flt.tier} options={["PLATINUM", "GOLD", "STANDARD"].map((t) => [t, t] as [string, string])} onChange={(v) => setF({ tier: v })} />
                <FilterSelect label="전체 국가" value={flt.country} options={countries.map((x) => [x.c, `${flag(x.c)} ${x.cn}`] as [string, string])} onChange={(v) => setF({ country: v })} />
                <FilterSelect label="전체 업종" value={flt.seg} options={Object.entries(SEGMENT_KO)} onChange={(v) => setF({ seg: v })} />
                {tab === "all" && <FilterSelect label="중요도순" value={flt.sort === "default" ? "" : flt.sort} options={SORTS.filter(([v]) => v !== "default")} onChange={(v) => setF({ sort: v || "default" })} />}
              </div>
            )}
          </div>

          {tab === "focus" && (focusRows.length === 0 ? <Empty>해당하는 고객이 없습니다.</Empty> : (
            <>
              <Table cols={FOCUS_COLS} heads={["고객", "등급", "사유", "지연", "대응 상태", ""]}>
                {focusRows.slice((page - 1) * SIZE, page * SIZE).map(({ c }) => {
                  const r = primaryReason(c), x = r ? factParts(c, r) : null;
                  return (
                    <Row key={c.id} c={c} cols={FOCUS_COLS} onOpen={() => open(c)}>
                      <Who c={c} />
                      <span><TierTag tier={c.tier} /></span>
                      {x ? <span className="flex items-center gap-2 text-[15px]"><span className={cn("size-2 shrink-0 rounded-full", DOT[x.tone])} aria-hidden />{x.title}</span> : <span className="text-[15px] text-muted-foreground">직접 지정</span>}
                      <span className="grid gap-1.5">
                        <span className={cn("text-[15px]", x?.tone === "severe" ? "font-medium text-destructive" : "text-muted-foreground")}>{x?.value ?? "—"}</span>
                        {r === "urgent" && x && (x.tone === "severe" || x.tone === "red") && <Gauge value={maxLate(c)} max={LATE_MAX} tone={x.tone === "severe" ? "bg-destructive/80" : "bg-destructive/45"} />}
                      </span>
                      <span><CareTag status={st(c)} /></span>
                      <div className="flex justify-end" onClick={(e) => e.stopPropagation()}>{r && <CareButtons c={c} />}</div>
                    </Row>
                  );
                })}
              </Table>
              <Pager page={page} size={SIZE} total={focusRows.length} onChange={setPage} />
            </>
          ))}

          {tab === "all" && (allRows.length === 0 ? <Empty>해당하는 고객이 없습니다.</Empty> : (
            <>
              <Table cols={ALL_COLS} heads={["고객", "등급", "12개월 문의", "기한 넘긴 횟수", "최근 문의", ""]}>
                {allRows.slice((page - 1) * SIZE, page * SIZE).map((c) => (
                  <Row key={c.id} c={c} cols={ALL_COLS} onOpen={() => open(c)}>
                    <Who c={c} />
                    <span><TierTag tier={c.tier} /></span>
                    <span className="grid gap-1.5"><span className="text-[15px] tabular-nums">{c.n}건</span><Gauge value={c.n} max={maxN} tone="bg-info/70" /></span>
                    <span className="grid gap-1.5"><span className={cn("text-[15px] tabular-nums", c.breach >= 4 ? "font-medium" : "text-muted-foreground")}>{c.breach}회</span><Gauge value={c.breach} max={maxBreach} tone={c.breach >= 4 ? "bg-warning" : "bg-muted-foreground/30"} /></span>
                    <span className="text-[15px] tabular-nums text-muted-foreground">{md(c.last)}</span>
                    <span className="flex justify-end">{focusOf(c, care[c.id]) && <Tag tone="blue">중점 관리</Tag>}</span>
                  </Row>
                ))}
              </Table>
              <Pager page={page} size={SIZE} total={allRows.length} onChange={setPage} />
            </>
          ))}
        </div>
      )}
    </>
  );
}
