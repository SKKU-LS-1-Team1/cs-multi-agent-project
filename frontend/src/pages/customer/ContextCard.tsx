// "상담 중인 제품" 카드 (CSA-38 · 조수빈): AI가 어떤 제품·화면을 기준으로 상담하는지 짧게 보여 준다.
// 접힌 상태가 기본이다(대화 영역을 넓게 쓰려고). 값이 바뀌면 바뀐 항목만 잠깐 연한 파랑으로 표시하고,
// 카드를 저절로 펼치거나 대화 스크롤을 옮기지 않는다.
import { useEffect, useId, useRef, useState } from "react";

type Row = { key: string; label: string; value: string; sub?: string };
type Props = { family: string | null; name: string; code: string; screen: string | null };

export default function ContextCard({ family, name, code, screen }: Props) {
  const [open, setOpen] = useState(false);
  const [flash, setFlash] = useState<Record<string, boolean>>({});
  const prev = useRef<Record<string, string> | null>(null);
  const id = useId();

  const rows: Row[] = [
    ...(family ? [{ key: "family", label: "제품군", value: family }] : []),
    { key: "model", label: "모델", value: name, sub: code },
    ...(screen ? [{ key: "screen", label: "보고 있는 화면", value: screen }] : []),
  ];
  const sig = rows.map((r) => `${r.key}:${r.value}`).join("|");
  useEffect(() => {
    const now = Object.fromEntries(rows.map((r) => [r.key, r.value]));
    const old = prev.current;
    prev.current = now;
    if (!old) return; // 처음 나타날 때는 표시하지 않는다
    const changed = Object.fromEntries(Object.keys(now).filter((k) => old[k] !== now[k]).map((k) => [k, true]));
    if (!Object.keys(changed).length) return;
    setFlash(changed);
    const t = setTimeout(() => setFlash({}), 1400);
    return () => clearTimeout(t);
  }, [sig]); // eslint-disable-line react-hooks/exhaustive-deps

  const f = (k: string) => (flash[k] ? " is-flash" : "");
  return (
    <section className="cp-ctx" aria-label="상담 중인 제품">
      <button type="button" className="cp-ctx-h" aria-expanded={open} aria-controls={id} onClick={() => setOpen((v) => !v)}>
        <span className="cp-ctx-t">
          <small>상담 중인 제품</small>
          <b className={f("model")}>{name}</b>
          {screen && <span className={`cp-ctx-sum${open ? " is-off" : ""}${f("screen")}`}>{screen}</span>}
        </span>
        <svg className="cp-ctx-chev" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
      </button>
      <div className={`cp-ctx-wrap${open ? " is-open" : ""}`} id={id} role="region" aria-label="상담 중인 내용 자세히">
        <div className="cp-ctx-in">
          <dl>
            {rows.map((r) => (
              <div key={r.key} className={f(r.key).trim()}>
                <dt>{r.label}</dt>
                <dd>{r.value}{r.sub && <small>{r.sub}</small>}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </section>
  );
}
