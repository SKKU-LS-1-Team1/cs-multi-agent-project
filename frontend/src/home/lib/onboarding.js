// 온보딩: 국가 감지 · 언어 선택에 쓰는 상수와 로직. 국가와 언어는 별도 상태로 다룬다.

// 지원 국가 21개 (KR 포함). 이름은 영어 고정 — 언어를 바꿔도 국가 표기는 그대로여야 한다.
export const COUNTRIES = ['KR', 'TH', 'JP', 'BR', 'FR', 'GB', 'SA', 'IN', 'RU', 'AE', 'AU', 'IT', 'US', 'DE', 'ID', 'MX', 'ES', 'CN', 'VN', 'TR', 'PL']
const COUNTRY_NAME = new Intl.DisplayNames(['en'], { type: 'region' })
export const countryName = (code) => COUNTRY_NAME.of(code)

// 국기 이모지: 국가 코드를 지역 표시 문자(🇦~🇿)로 바꾼다.
export const flag = (code) => String.fromCodePoint(...[...code].map((c) => 0x1f1a5 + c.charCodeAt(0)))

// 16개 언어 (서버 drafting._CUSTOMER_LANGUAGES 와 같다). 이름은 각 언어의 자국어 표기.
// 한국어가 빠지면 한국어 브라우저가 영어로 정해져, 고른 언어를 항상 보내는 챗봇이 한국어 질문에도 영어로 답한다.
export const LANGUAGES = [
  ['en', 'English'], ['ko', '한국어'], ['ja', '日本語'], ['zh', '中文'], ['es', 'Español'], ['pt', 'Português'],
  ['fr', 'Français'], ['de', 'Deutsch'], ['it', 'Italiano'], ['ar', 'العربية'], ['ru', 'Русский'],
  ['th', 'ไทย'], ['id', 'Bahasa Indonesia'], ['vi', 'Tiếng Việt'], ['tr', 'Türkçe'], ['pl', 'Polski'],
]
const LANG_CODES = LANGUAGES.map(([c]) => c)
export const RTL = new Set(['ar'])

// 기존 국가→언어 매핑은 코드에 없어서 요청 명세의 매핑을 그대로 쓴다.
export const COUNTRY_LANG = {
  KR: 'ko', TH: 'th', JP: 'ja', BR: 'pt', FR: 'fr', GB: 'en', IN: 'en', AU: 'en', US: 'en', SA: 'ar', AE: 'ar', RU: 'ru',
  IT: 'it', DE: 'de', ID: 'id', MX: 'es', ES: 'es', CN: 'zh', VN: 'vi', TR: 'tr', PL: 'pl',
}

// 언어별 대표 국가 — 첫 화면 국기·국가명이 고른 언어를 따라간다 (접속 국가 언어를 고르면 접속 국가).
export const LANG_COUNTRY = {
  en: 'US', ko: 'KR', ja: 'JP', zh: 'CN', es: 'ES', pt: 'BR', fr: 'FR', de: 'DE', it: 'IT', ar: 'SA',
  ru: 'RU', th: 'TH', id: 'ID', vi: 'VN', tr: 'TR', pl: 'PL',
}
// 첫 화면에 보일 국가: 고른 언어가 접속 국가의 언어면 접속 국가, 아니면 그 언어의 대표 국가.
export const shownCountry = (lang, detected) => (detected && COUNTRY_LANG[detected] === lang ? detected : LANG_COUNTRY[lang] ?? null)

// ── 국가 감지: 접속 IP 기준(네트워크). 브라우저가 직접 외부 서비스를 호출한다.
// 주소는 VITE_GEO_URL 로 바꿀 수 있다 (응답에 { country: "JP" } 가 있으면 된다).
const GEO_URL = import.meta.env.VITE_GEO_URL || 'https://api.country.is/'
export async function detectCountry(timeoutMs = 4000) {
  const ctl = new AbortController()
  const timer = setTimeout(() => ctl.abort(), timeoutMs)
  try {
    const res = await fetch(GEO_URL, { signal: ctl.signal })
    if (!res.ok) throw new Error(String(res.status))
    const code = String((await res.json()).country || '').toUpperCase()
    if (!/^[A-Z]{2}$/.test(code)) throw new Error('bad country')
    return COUNTRIES.includes(code) ? { status: 'ok', code } : { status: 'unsupported', code }
  } catch {
    return { status: 'failed', code: null }
  } finally {
    clearTimeout(timer)
  }
}

// ── 언어 선택 저장 (사용자가 직접 고른 값만 저장한다)
const KEY = 'ls-lang-choice'
export const loadChoice = () => {
  try { const v = localStorage.getItem(KEY); return LANG_CODES.includes(v) ? v : null } catch { return null }
}
export const saveChoice = (lang) => { try { localStorage.setItem(KEY, lang) } catch { /* 저장 불가 환경 */ } }

export function browserLang() {
  for (const l of navigator.languages?.length ? navigator.languages : [navigator.language]) {
    const base = String(l || '').toLowerCase().split('-')[0]
    if (LANG_CODES.includes(base)) return base
  }
  return null
}

// 초기 언어: 직접 고른 값 > (감지 성공 시) 국가 기본 언어 > 브라우저 언어 > 영어.
// 감지 중에는 국가를 아직 모르므로 country 를 null 로 넘긴다.
export function initialLang({ choice, country }) {
  if (choice) return { lang: choice, source: 'user' }
  if (country && COUNTRY_LANG[country]) return { lang: COUNTRY_LANG[country], source: 'country' }
  const b = browserLang()
  return b ? { lang: b, source: 'browser' } : { lang: 'en', source: 'default' }
}
