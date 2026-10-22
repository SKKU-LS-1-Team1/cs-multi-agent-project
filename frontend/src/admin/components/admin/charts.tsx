// 업무 현황용 부품: 링 게이지, 카드 켜고 끄기 메뉴. (차트 라이브러리 없이 SVG로 그린다)
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Settings2 } from "lucide-react";
import { Button } from "@admin/components/ui/button";
import { Checkbox } from "@admin/components/ui/checkbox";
import { cn } from "@admin/lib/utils";

/** 링 게이지: 가운데에 큰 숫자, 아래에 한 줄 설명. */
export function Ring({ value, label, caption, tone = "info", size = 148 }: { value: number; label: ReactNode; caption?: ReactNode; tone?: "info" | "success" | "warning" | "destructive"; size?: number }) {
  const r = 52, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, value));
  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }} role="img" aria-label={`${typeof label === "string" ? label : ""} ${Math.round(v)}%`}>
      <svg viewBox="0 0 120 120" className="size-full -rotate-90" aria-hidden>
        <circle cx="60" cy="60" r={r} fill="none" strokeWidth="11" className="stroke-muted" />
        {v > 0 && <circle cx="60" cy="60" r={r} fill="none" strokeWidth="11" strokeLinecap="round" strokeDasharray={`${(c * v) / 100} ${c}`} className={cn("transition-[stroke-dasharray] duration-500", tone === "success" ? "stroke-success" : tone === "warning" ? "stroke-warning" : tone === "destructive" ? "stroke-destructive" : "stroke-info")} />}
      </svg>
      <div className="absolute grid text-center leading-tight"><span className="text-3xl font-medium tabular-nums">{label}</span>{caption && <span className="text-xs text-muted-foreground">{caption}</span>}</div>
    </div>
  );
}

/** 화면 맞춤 설정: 카드를 켜고 끈다. 선택은 이 브라우저에 기억한다. */
export function useWidgets(key: string, all: readonly (readonly [string, string])[]) {
  const read = () => { try { const v = JSON.parse(localStorage.getItem(key) || "null"); if (Array.isArray(v)) return v as string[]; } catch { /* 저장소를 못 읽어도 기본값으로 보인다 */ } return all.map(([k]) => k); };
  const [on, setOn] = useState<string[]>(read);
  const toggle = (k: string) => setOn((cur) => { const next = cur.includes(k) ? cur.filter((x) => x !== k) : [...cur, k]; try { localStorage.setItem(key, JSON.stringify(next)); } catch { /* 저장 실패는 무시 */ } return next; });
  return { shown: (k: string) => on.includes(k), toggle };
}

export function CustomizeMenu({ all, shown, toggle }: { all: readonly (readonly [string, string])[]; shown: (k: string) => boolean; toggle: (k: string) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div ref={ref} className="relative">
      <Button variant="outline" onClick={() => setOpen(!open)} aria-expanded={open} aria-haspopup="true"><Settings2 aria-hidden />화면 설정</Button>
      {open && (
        <div role="group" aria-label="보일 카드" className="absolute right-0 top-full z-20 mt-2 grid w-56 gap-1 rounded-2xl bg-card p-2 shadow-float">
          <p className="px-3 pb-1 pt-2 text-xs text-muted-foreground">보일 카드를 고르세요</p>
          {all.map(([k, label]) => <label key={k} className="flex cursor-pointer items-center gap-2.5 rounded-xl px-3 py-2 text-sm hover:bg-muted"><Checkbox checked={shown(k)} onCheckedChange={() => toggle(k)} />{label}</label>)}
        </div>
      )}
    </div>
  );
}
