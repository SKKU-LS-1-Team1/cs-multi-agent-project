// 국가 · 언어 (CSA-64 · 조수빈). 고객 화면 첫 화면(온보딩)에서 정하고, 상담·문의 요청의 language · country 로 쓴다.
// 국가와 언어는 별도 상태다 — 언어를 바꿔도 감지된 국가는 바뀌지 않는다.
// 사용자가 직접 고른 언어는 자동 감지 결과보다 우선하고, 나중에 국가 감지가 끝나도 덮어쓰지 않는다.
import { useSyncExternalStore } from "react";

// 지원 국가 20개. 이름은 영어 고정 — 언어를 바꿔도 국가 표기는 그대로여야 한다.
export const COUNTRIES = ["TH", "JP", "BR", "FR", "GB", "SA", "IN", "RU", "AE", "AU", "IT", "US", "DE", "ID", "MX", "ES", "CN", "VN", "TR", "PL"] as const;
const REGION = new Intl.DisplayNames(["en"], { type: "region" });
export const countryName = (code: string): string => REGION.of(code) ?? code;

// 지원 언어 15개. 이름은 각 언어의 자국어 표기.
export const LANGUAGES: [string, string][] = [
  ["en", "English"], ["ja", "日本語"], ["zh", "中文"], ["es", "Español"], ["pt", "Português"],
  ["fr", "Français"], ["de", "Deutsch"], ["it", "Italiano"], ["ar", "العربية"], ["ru", "Русский"],
  ["th", "ไทย"], ["id", "Bahasa Indonesia"], ["vi", "Tiếng Việt"], ["tr", "Türkçe"], ["pl", "Polski"],
];
const LANG_CODES = LANGUAGES.map(([c]) => c);
export const RTL = new Set(["ar"]);

// 국가별 기본 언어 (이 저장소에 기존 매핑이 없어 요청 명세의 매핑을 쓴다)
export const COUNTRY_LANG: Record<string, string> = {
  TH: "th", JP: "ja", BR: "pt", FR: "fr", GB: "en", IN: "en", AU: "en", US: "en", SA: "ar", AE: "ar", RU: "ru",
  IT: "it", DE: "de", ID: "id", MX: "es", ES: "es", CN: "zh", VN: "vi", TR: "tr", PL: "pl",
};

export type CountryState = { status: "loading" | "ok" | "unsupported" | "failed"; code: string | null };

// 접속 IP 기준 국가 감지. 브라우저가 외부 서비스를 직접 부르므로 접속 IP가 그 서비스로 나간다.
// 주소는 VITE_GEO_URL 로 바꿀 수 있다 (응답에 { country: "JP" } 가 있으면 된다).
const GEO_URL = (import.meta.env.VITE_GEO_URL as string | undefined) || "https://api.country.is/";
export async function detectCountry(timeoutMs = 4000): Promise<CountryState> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(GEO_URL, { signal: ctl.signal });
    if (!res.ok) throw new Error(String(res.status));
    const code = String(((await res.json()) as { country?: string }).country ?? "").toUpperCase();
    if (!/^[A-Z]{2}$/.test(code)) throw new Error("bad country");
    return (COUNTRIES as readonly string[]).includes(code) ? { status: "ok", code } : { status: "unsupported", code };
  } catch {
    return { status: "failed", code: null };
  } finally {
    clearTimeout(timer);
  }
}

// 저장 (브라우저 저장소를 못 쓰면 이번 방문 동안만 메모리에 둔다)
const CHOICE = "ls-lang-choice"; // 직접 고른 언어 — 재방문 때도 유지
const SESSION_LANG = "ls-lang"; // 이번 방문에서 쓰는 언어
const ONBOARDED = "ls-onboarded";
const COUNTRY = "ls-country"; // 감지에 성공한 지원 국가 코드
const read = (s: Storage, k: string): string | null => { try { return s.getItem(k); } catch { return null; } };
const write = (s: Storage, k: string, v: string | null) => { try { if (v === null) s.removeItem(k); else s.setItem(k, v); } catch { /* 저장 못 해도 화면은 동작한다 */ } };

export function browserLang(): string | null {
  for (const l of navigator.languages?.length ? navigator.languages : [navigator.language]) {
    const base = String(l || "").toLowerCase().split("-")[0];
    if (LANG_CODES.includes(base)) return base;
  }
  return null;
}
export const savedChoice = (): string | null => { const v = read(localStorage, CHOICE); return v && LANG_CODES.includes(v) ? v : null; };

/** 초기 언어: 직접 고른 값 → (국가 감지 성공 시) 국가 기본 언어 → 브라우저 언어 → 영어. */
export function initialLang(choice: string | null, country: string | null): { lang: string; source: "user" | "country" | "browser" | "default" } {
  if (choice) return { lang: choice, source: "user" };
  if (country && COUNTRY_LANG[country]) return { lang: COUNTRY_LANG[country], source: "country" };
  const b = browserLang();
  return b ? { lang: b, source: "browser" } : { lang: "en", source: "default" };
}

// ── 앱 전체가 같이 보는 상태 (온보딩 · 헤더 언어 메뉴 · 상담/문의 요청)
type State = { onboarded: boolean; lang: string };
let state: State = {
  onboarded: read(sessionStorage, ONBOARDED) === "1",
  lang: read(sessionStorage, SESSION_LANG) ?? savedChoice() ?? initialLang(null, null).lang,
};
const listeners = new Set<() => void>();
const set = (next: Partial<State>) => { state = { ...state, ...next }; listeners.forEach((l) => l()); };

export const langStore = {
  subscribe(l: () => void) { listeners.add(l); return () => { listeners.delete(l); }; },
  snapshot: () => state,
  /** 온보딩에서 [계속하기]. country 는 감지에 성공한 지원 국가만 넘긴다. */
  complete(lang: string, country: string | null) {
    write(sessionStorage, ONBOARDED, "1"); write(sessionStorage, SESSION_LANG, lang); write(sessionStorage, COUNTRY, country);
    set({ onboarded: true, lang });
  },
  /** 헤더에서 언어 변경 — 직접 고른 값이라 저장해서 다음 방문에도 쓴다. */
  choose(lang: string) { write(localStorage, CHOICE, lang); write(sessionStorage, SESSION_LANG, lang); set({ lang }); },
  reopen() { write(sessionStorage, ONBOARDED, null); set({ onboarded: false }); },
};
export const useLangState = (): State => useSyncExternalStore(langStore.subscribe, langStore.snapshot);

/** API 요청에 실을 값 */
export const getLang = (): string => state.lang;
export const getCountry = (): string | undefined => read(sessionStorage, COUNTRY) ?? undefined;
