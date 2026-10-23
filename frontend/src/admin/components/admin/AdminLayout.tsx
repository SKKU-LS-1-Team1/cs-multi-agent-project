// 관리자 공통 셸: LS 남색 그라데이션 프레임 안에 둥근 본문 판이 들어가는 구조(Emerald24 레퍼런스).
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { BookOpen, Inbox, LayoutGrid, LogOut, Search, Users } from "lucide-react";
import { cn } from "@admin/lib/utils";
import { setUi, useStore } from "@admin/lib/store";
import { Toaster } from "@admin/components/ui/sonner";
import ModalHost from "./Modals";
import { PersonAvatar } from "./common";
import CommandPalette from "./CommandPalette";
import { endSession } from "@admin/lib/auth";
import { FRONTLINE, people, signedIn, teamLead } from "@admin/lib/logic";
import logo from "@admin/assets/ls-electric-logo-reverse.png"; // 어두운 배경용(흰색 LS · 하늘색 ELECTRIC · 빨간 포인트)

const MENU = [
  { to: "/", label: "업무 현황", icon: LayoutGrid, match: (p: string) => p === "/" || p === "/collab" || p === "/resources" },
  { to: "/tickets", label: "문의 관리", icon: Inbox, match: (p: string) => p.startsWith("/tickets") },
  { to: "/customers", label: "고객 관리", icon: Users, match: (p: string) => p.startsWith("/customers") },
  { to: "/knowledge", label: "지식·해결 사례", icon: BookOpen, match: (p: string) => p.startsWith("/knowledge") },
];

export default function AdminLayout() {
  useStore();
  const { pathname } = useLocation();
  const [palette, setPalette] = useState(false);
  const me = people.find((p) => p.name === signedIn);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((v) => !v); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <div className="grid min-h-dvh grid-cols-[236px_minmax(0,1fr)] bg-[linear-gradient(172deg,#04337a_0%,#0a4a98_36%,#1f77c4_72%,#7cc2ec_100%)] bg-fixed text-foreground">
      <a href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }} className="sr-only z-50 rounded-full bg-white px-4 py-2 text-sm text-[#003377] focus:not-sr-only focus:fixed focus:left-3 focus:top-3">본문으로 건너뛰기</a>
      <aside className="sticky top-0 flex h-dvh flex-col px-5 pb-5 pt-7 text-white">
        <div className="px-1">
          <img src={logo} alt="LS ELECTRIC" width={2029} height={322} style={{ display: "block", width: "100%", height: "auto" }} />
          <p className="mt-3 text-sm font-medium tracking-wide text-white/70">글로벌 고객지원</p>
        </div>
        <nav aria-label="주 메뉴" className="mt-10 grid gap-1.5">
          {MENU.map(({ to, label, icon: Icon, match }) => {
            const on = match(pathname);
            return (
              <NavLink key={to} to={to} aria-current={on ? "page" : undefined}
                onClick={() => to === "/tickets" && setUi({ listOwner: "" })}
                className={cn("flex h-12 items-center gap-3 rounded-full px-4 text-base transition-colors", on ? "bg-white/16 font-medium text-white" : "text-white/75 hover:bg-white/10 hover:text-white")}>
                <Icon className="size-[18px]" aria-hidden />
                {label}
              </NavLink>
            );
          })}
        </nav>
        <div className="mt-auto grid gap-3">
          <button onClick={() => setPalette(true)} className="flex h-12 w-full items-center gap-3 rounded-full bg-[#04337a]/65 px-4 text-base text-white shadow-[0_6px_16px_-10px_rgb(0_10_40/0.7)] transition-colors hover:bg-[#04337a]/80">
            <Search className="size-[18px]" aria-hidden />빠른 이동<kbd className="ml-auto rounded-full bg-white/20 px-2 text-[11px]">⌘K</kbd>
          </button>
          <div className="flex items-center gap-1 rounded-full bg-white py-1.5 pl-1.5 pr-1.5 text-[#0e1a2b] shadow-[0_8px_20px_-10px_rgb(0_10_40/0.6)]">
            <PersonAvatar name={signedIn} size={32} />
            <span className="grid min-w-0 flex-1 leading-tight pl-1"><strong className="truncate text-sm font-medium">{signedIn}</strong><small className={cn("truncate text-xs", signedIn === teamLead ? "font-medium text-[#003377]" : "text-[#5d6b7e]")}>{me?.rank || FRONTLINE}</small></span>
            <button type="button" aria-label="로그아웃" title="로그아웃" onClick={() => { endSession(); window.location.reload(); }} className="grid size-9 shrink-0 place-items-center rounded-full text-[#5d6b7e] transition-colors hover:bg-[#eef2f8] hover:text-[#0e1a2b]"><LogOut className="size-[18px]" aria-hidden /></button>
          </div>
        </div>
      </aside>
      <main id="main" tabIndex={-1} className="m-3 ml-0 min-h-[calc(100dvh-1.5rem)] min-w-0 overflow-clip rounded-[28px] bg-background outline-none">
        <Outlet />
      </main>
      <ModalHost />
      <CommandPalette open={palette} onOpenChange={setPalette} />
      <Toaster position="bottom-center" />
    </div>
  );
}
