// ⌘K / Ctrl+K 빠른 이동: 티켓 번호·제목·고객·제품으로 티켓을 찾거나 화면으로 바로 이동한다.
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CornerDownLeft, Search } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@admin/components/ui/dialog";
import { PriorityTag, SlaTag } from "./common";
import { signedIn } from "@admin/lib/logic";
import { findTicket, setUi, tickets } from "@admin/lib/store";
import { cn } from "@admin/lib/utils";

const PAGES = [
  { label: "업무 현황 · C/S 업무", to: "/" },
  { label: "업무 현황 · 전문부서 협업", to: "/collab" },
  { label: "업무 현황 · 리소스 배정", to: "/resources" },
  { label: "티켓 관리", to: "/tickets" },
  { label: "지식·해결 사례", to: "/knowledge" },
];

export default function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);

  useEffect(() => { if (open) { setQ(""); setIdx(0); } }, [open]);

  const items = useMemo(() => {
    const k = q.trim().toLowerCase();
    const ts = tickets.filter((t) => !k || [t.id, t.title, t.company, t.product, t.owner].join(" ").toLowerCase().includes(k)).slice(0, 8)
      .map((t) => ({ kind: "ticket" as const, id: t.id }));
    const ps = PAGES.filter((p) => !k || p.label.toLowerCase().includes(k)).map((p) => ({ kind: "page" as const, ...p }));
    return [...ts, ...ps];
  }, [q]);

  const run = (it: (typeof items)[number] | undefined) => {
    if (!it) return;
    onOpenChange(false);
    if (it.kind === "page") return nav(it.to);
    const t = findTicket(it.id);
    setUi({ queueScope: t && t.owner === signedIn && t.stage !== 5 ? "내 담당" : "전체", tab: "문의·답변" });
    nav("/tickets/" + it.id);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(items.length - 1, i + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(0, i - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); run(items[idx]); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="top-[20%] translate-y-0 gap-0 p-0 sm:max-w-xl" showCloseButton={false}>
        <DialogTitle className="sr-only">빠른 이동</DialogTitle>
        <div className="flex items-center gap-2 border-b px-4">
          <Search className="size-4 text-muted-foreground" />
          <input autoFocus value={q} onChange={(e) => { setQ(e.target.value); setIdx(0); }} onKeyDown={onKey} aria-label="빠른 이동 검색"
            placeholder="티켓 번호·제목·고객·제품, 또는 화면 이름" className="h-12 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground" />
          <kbd className="rounded border px-1.5 py-0.5 text-[11px] text-muted-foreground">Esc</kbd>
        </div>
        <ul role="listbox" className="max-h-[50dvh] overflow-y-auto p-2">
          {items.map((it, i) => {
            const t = it.kind === "ticket" ? findTicket(it.id) : undefined;
            return (
              <li key={it.kind + (it.kind === "ticket" ? it.id : it.to)} role="option" aria-selected={i === idx}>
                <button onMouseEnter={() => setIdx(i)} onClick={() => run(it)} className={cn("flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm", i === idx && "bg-accent")}>
                  {t ? (
                    <>
                      <PriorityTag p={t.priority} />
                      <span className="min-w-0 flex-1"><span className="block truncate font-medium">{t.title}</span><span className="block truncate text-xs text-muted-foreground">{t.id} · {t.product} · {t.owner || "미배정"}</span></span>
                      <SlaTag t={t} />
                    </>
                  ) : <span className="flex-1">{it.kind === "page" ? it.label : ""}<span className="ml-2 text-xs text-muted-foreground">화면</span></span>}
                  {i === idx && <CornerDownLeft className="size-3.5 text-muted-foreground" />}
                </button>
              </li>
            );
          })}
          {!items.length && <li className="px-3 py-8 text-center text-sm text-muted-foreground">일치하는 항목이 없습니다.</li>}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
