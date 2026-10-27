// 첫 화면: 국가 확인 + 언어 선택 (CSA-64 · 조수빈). 국가는 접속 IP로 자동 감지해 국기 배지로 보여 주고, 언어는 15개 중 직접 고른다.
// 국가와 언어는 따로 움직인다: 언어를 바꿔도 국가·국기는 그대로고, 직접 고른 언어는 나중에 끝난 국가 감지가 덮어쓰지 않는다.
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import logo from "../../admin/assets/ls-electric-logo-reverse.png";
import { LANGUAGES, RTL, countryName, detectCountry, initialLang, langStore, savedChoice, type CountryState } from "../../lib/lang";
import { t } from "../../lib/onboardingText";
import FlagIcon from "./FlagIcon";
import "./onboarding.css";

export default function Onboarding() {
  const [country, setCountry] = useState<CountryState>({ status: "loading", code: null });
  const [{ lang, source }, setLangState] = useState(() => initialLang(savedChoice(), null));
  const sourceRef = useRef(source);
  sourceRef.current = source;
  const groupRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    void detectCountry().then((r) => {
      if (!alive) return;
      setCountry(r);
      // 이미 사용자가 고른 언어(저장된 선택 포함)는 덮어쓰지 않는다
      if (sourceRef.current !== "user") setLangState(initialLang(null, r.status === "ok" ? r.code : null));
    });
    return () => { alive = false; };
  }, []);

  // 문서 언어·방향 (아랍어는 RTL). 온보딩이 끝나면 한국어 화면으로 되돌린다.
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = RTL.has(lang) ? "rtl" : "ltr";
    return () => { document.documentElement.lang = "ko"; document.documentElement.dir = "ltr"; };
  }, [lang]);

  const choose = (code: string) => { try { localStorage.setItem("ls-lang-choice", code); } catch { /* 저장 못 해도 이번 선택은 쓴다 */ } setLangState({ lang: code, source: "user" }); };

  // 라디오 그룹 키보드: 방향키 · Home/End. RTL 에서는 좌우가 반대로 움직인다.
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = LANGUAGES.findIndex(([c]) => c === lang);
    const rtl = RTL.has(lang);
    const step = ({ ArrowRight: rtl ? -1 : 1, ArrowDown: 1, ArrowLeft: rtl ? 1 : -1, ArrowUp: -1 } as Record<string, number>)[e.key];
    let j: number | null = null;
    if (step) j = (i + step + LANGUAGES.length) % LANGUAGES.length;
    else if (e.key === "Home") j = 0;
    else if (e.key === "End") j = LANGUAGES.length - 1;
    if (j === null) return;
    e.preventDefault();
    choose(LANGUAGES[j][0]);
    groupRef.current?.querySelectorAll<HTMLElement>("[role=radio]")[j]?.focus();
  };

  const ok = country.status === "ok" && country.code !== null;
  const label = country.status === "loading" ? t(lang, "detecting") : ok ? countryName(country.code as string) : t(lang, "unknown");

  return (
    <main className="ob" dir={RTL.has(lang) ? "rtl" : "ltr"} lang={lang}>
      <header className="ob-brand">
        <img src={logo} alt="LS ELECTRIC" className="ob-logo" />
        <p>{t(lang, "tagline")}</p>
      </header>

      <section className="ob-card" aria-labelledby="ob-h">
        <h1 id="ob-h">{t(lang, "title")}</h1>
        <p className="ob-sub">{t(lang, "sub")}</p>

        <div className="ob-country" role="status" aria-live="polite" aria-label={`${t(lang, "country")}: ${label}`}>
          <span className={`ob-badge${country.status === "loading" ? " is-loading" : ""}`} aria-hidden="true">
            {country.status !== "loading" && <FlagIcon code={ok ? country.code : null} size={52} />}
          </span>
          <span className="ob-cname">
            <small>{t(lang, "country")}</small>
            <b className={ok ? "" : "is-weak"}>{label}</b>
          </span>
        </div>

        <div className="ob-lh" id="ob-lang">{t(lang, "language")}</div>
        <div className="ob-langs" role="radiogroup" aria-labelledby="ob-lang" onKeyDown={onKey} ref={groupRef}>
          {LANGUAGES.map(([code, name]) => {
            const on = code === lang;
            return (
              <button key={code} type="button" role="radio" aria-checked={on} tabIndex={on ? 0 : -1} className={`ob-lang${on ? " is-on" : ""}`} lang={code} onClick={() => choose(code)}>
                <span className="ob-check" aria-hidden="true">{on ? "✓" : ""}</span>
                <span>{name}</span>
              </button>
            );
          })}
        </div>

        <button type="button" className="ob-go" onClick={() => langStore.complete(lang, ok ? country.code : null)}>{t(lang, "start")}</button>
      </section>
    </main>
  );
}
