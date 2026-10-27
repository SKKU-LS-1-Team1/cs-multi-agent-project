// 헤더 언어 변경: 지구본 + 현재 언어 코드(EN). 누르면 15개 언어 목록이 열린다. (CSA-64 · 조수빈)
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { LANGUAGES, langStore, useLangState } from "../../lib/lang";

export default function LangMenu() {
  const { lang } = useLangState();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const cur = LANGUAGES.find(([c]) => c === lang) ?? LANGUAGES[0];

  useEffect(() => {
    if (!open) return;
    const out = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", out);
    root.current?.querySelector<HTMLElement>("[aria-selected=true]")?.focus();
    return () => document.removeEventListener("mousedown", out);
  }, [open]);

  const pick = (code: string) => { langStore.choose(code); setOpen(false); btn.current?.focus(); };
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") { setOpen(false); btn.current?.focus(); return; }
    const items = [...(root.current?.querySelectorAll<HTMLElement>("[role=option]") ?? [])];
    const i = items.indexOf(document.activeElement as HTMLElement);
    const go = (j: number) => { e.preventDefault(); items[(j + items.length) % items.length]?.focus(); };
    if (e.key === "ArrowDown") go(i + 1);
    else if (e.key === "ArrowUp") go(i - 1);
    else if (e.key === "Home") go(0);
    else if (e.key === "End") go(items.length - 1);
  };

  return (
    <div className="lm" ref={root} onKeyDown={open ? onKey : undefined}>
      <button ref={btn} type="button" className="lm-btn" aria-haspopup="listbox" aria-expanded={open} aria-label={`언어 변경 (현재: ${cur[1]})`} onClick={() => setOpen((v) => !v)}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3.2 3 14.8 0 18M12 3c-3 3.2-3 14.8 0 18" />
        </svg>
        <b>{lang.toUpperCase()}</b>
      </button>
      {open && (
        <div className="lm-pop">
          <ul className="lm-list" role="listbox" aria-label="언어">
            {LANGUAGES.map(([code, name]) => (
              <li key={code} role="option" aria-selected={code === lang} tabIndex={-1} lang={code} className={code === lang ? "is-on" : ""} onClick={() => pick(code)}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(code); } }}>
                <span className="lm-ck" aria-hidden="true">{code === lang ? "✓" : ""}</span>
                <span>{name}</span>
                <small>{code.toUpperCase()}</small>
              </li>
            ))}
          </ul>
          <button type="button" className="lm-again" onClick={() => { setOpen(false); langStore.reopen(); }}>국가·언어 다시 고르기</button>
        </div>
      )}
    </div>
  );
}
