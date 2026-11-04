// ⌘K / Ctrl+K 문의 번호(Ticket ID) 검색: 번호로만 찾고, 새 화면 없이 기존 화면으로 바로 이동한다.
// 진행 중인 문의 → 문의 관리(상세), 완료된 문의 → 지식·해결 사례(그 사례).
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CornerDownLeft, Search } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@admin/components/ui/dialog";
import { Mono } from "./common";
import { cases, signedIn } from "@admin/lib/logic";
import { setUi, tickets } from "@admin/lib/store";
import { cn } from "@admin/lib/utils";

type Hit = { id: string; where: "ticket" | "case"; caseIndex: number; mine: boolean };
const norm = (v: string) => v.replace(/\s+/g, "").toUpperCase();
const MAX = 8;

/** 문의 번호 하나가 어디로 가는지: 완료된 문의는 해결 사례가 있으면 거기로, 아니면 문의 상세로. 진행 중이면 문의 상세. */
function locate(id: string): Hit {
  const t = tickets.find((x) => norm(x.id) === norm(id));
  const caseIndex = cases.findIndex((c) => norm(c.ticketId) === norm(id));
  const done = t ? t.stage === 5 : caseIndex >= 0;
  return { id: t?.id ?? cases[caseIndex]?.ticketId ?? id, where: done && caseIndex >= 0 ? "case" : "ticket", caseIndex, mine: !!t && t.owner === signedIn && t.stage !== 5 };
}

export default function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);

  useEffect(() => { if (open) { setQ(""); setIdx(0); } }, [open]);

  const hits = useMemo(() => {
    const k = norm(q);
    if (!k) return [];
    const ids = [...new Set([...tickets.map((t) => t.id), ...cases.map((c) => c.ticketId)])];
    return ids.filter((id) => norm(id).includes(k)).sort((a, b) => Number(norm(b).startsWith(k)) - Number(norm(a).startsWith(k)) || a.localeCompare(b)).slice(0, MAX).map(locate);
  }, [q]);

  const run = (h: Hit | undefined) => {
    if (!h) return;
    onOpenChange(false);
    if (h.where === "case") { setUi({ knowledgeTab: "해결 사례", caseGroup: "", caseFamily: "", kquery: "", knowledge: h.caseIndex }); return nav("/knowledge"); }
    setUi({ queueScope: h.mine ? "내 담당" : "전체", tab: "문의·답변" });
    nav("/tickets/" + h.id);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(hits.length - 1, i + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(0, i - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); run(hits[idx]); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="top-[20%] translate-y-0 gap-0 p-0 sm:max-w-xl" showCloseButton={false}>
        <DialogTitle className="sr-only">문의 번호 검색</DialogTitle>
        <div className="flex items-center gap-2 border-b px-4">
          <Search className="size-4 text-muted-foreground" />
          <input autoFocus value={q} onChange={(e) => { setQ(e.target.value); setIdx(0); }} onKeyDown={onKey} aria-label="문의 번호 검색"
            placeholder="문의 번호(Ticket ID) 입력 · 예: CSV1-000050" className="h-12 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground" />
          <kbd className="rounded border px-1.5 py-0.5 text-[11px] text-muted-foreground">Esc</kbd>
        </div>
        <ul role="listbox" className="max-h-[50dvh] overflow-y-auto p-2">
          {hits.map((h, i) => (
            <li key={h.id} role="option" aria-selected={i === idx}>
              <button onMouseEnter={() => setIdx(i)} onClick={() => run(h)} className={cn("flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm", i === idx && "bg-accent")}>
                <Mono className="flex-1 font-medium">{h.id}</Mono>
                <span className="text-xs text-muted-foreground">{h.where === "case" ? "해결 사례에서 보기" : "문의 관리에서 보기"}</span>
                {i === idx && <CornerDownLeft className="size-3.5 text-muted-foreground" />}
              </button>
            </li>
          ))}
          {q.trim() && !hits.length && <li className="px-3 py-8 text-center text-sm text-muted-foreground">일치하는 문의 번호가 없습니다.</li>}
          {!q.trim() && <li className="px-3 py-8 text-center text-sm text-muted-foreground">진행 중인 문의는 문의 관리로, 완료된 문의는 해결 사례로 바로 이동합니다.</li>}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
