// 설치 가이드 탭: 위에서 아래로 읽는 단계 흐름 (CSA-37 · 조수빈). 번호·제목·짧은 설명·확인 항목이 기본이고,
// 원문 문장은 "자세히 보기"로 접어 둔다. 출처 링크는 기존 원문 보기(DocViewer)를 연다.
import { useEffect, useRef, useState } from "react";
import type { GuideStep } from "./installSteps";

type Props = { steps: GuideStep[]; anchor: string | null; onSource: (section: string) => void };

function Step({ st, n, hit, onSource }: { st: GuideStep; n: number; hit: boolean; onSource: (s: string) => void }) {
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const ref = useRef<HTMLLIElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!("IntersectionObserver" in window)) { el.classList.add("is-in"); return; }
    const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { el.classList.add("is-in"); io.disconnect(); } }), { rootMargin: "0px 0px -8% 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  useEffect(() => { if (hit) ref.current?.scrollIntoView({ block: "center", behavior: "smooth" }); }, [hit]);
  const list = (items: string[]) => <ul className="pd-g-ul">{items.map((x) => <li key={x}>{x}</li>)}</ul>;
  return (
    <li ref={ref} className={`pd-g-step${hit ? " is-hit" : ""}`}>
      <span className="pd-g-n" aria-hidden="true">{n}</span>
      <div className="pd-g-c">
        <h3>{st.title}</h3>
        {st.lead && <p className="pd-g-lead">{st.lead}</p>}
        {!!st.checks?.length && <ul className="pd-g-chk">{st.checks.map((x) => <li key={x}>{x}</li>)}</ul>}
        {!!st.bullets?.length && list(st.bullets)}
        {!!st.ordered?.length && <ol className="pd-g-ol">{st.ordered.map((x) => <li key={x}>{x}</li>)}</ol>}
        {!!st.checklist?.length && (
          <ul className="pd-g-cl">{st.checklist.map((x) => (
            <li key={x}><label><input type="checkbox" checked={!!checked[x]} onChange={(e) => setChecked({ ...checked, [x]: e.target.checked })} /><span>{x}</span></label></li>
          ))}</ul>
        )}
        {st.table && (
          <ul className="pd-g-iss">{st.table.rows.map((r) => <li key={r[0]}><b>{r[0]}</b><span>{r[1]}</span>{r[2] && <small>{r[2]}</small>}</li>)}</ul>
        )}
        {!!st.cautions?.length && <div className="pd-g-warn"><b>주의</b>{st.cautions.map((x) => <p key={x}>{x}</p>)}</div>}
        {st.notes?.map((x) => <div className="pd-g-note" key={x}><p>{x}</p></div>)}
        {!!st.raw?.length && <details className="pd-g-det"><summary>자세히 보기</summary>{list(st.raw)}</details>}
        <button type="button" className="pd-g-src" onClick={() => onSource(st.section)}>원문에서 확인 · §{st.section}</button>
      </div>
    </li>
  );
}

export default function InstallGuide({ steps, anchor, onSource }: Props) {
  return (
    <ol className="pd-g">
      {steps.map((st, i) => (
        <span key={st.section} className="pd-g-item">
          {st.group && st.group !== steps[i - 1]?.group && <li className="pd-g-grp" aria-hidden="true">{st.group}</li>}
          <Step st={st} n={i + 1} hit={!!anchor && anchor === st.section} onSource={onSource} />
        </span>
      ))}
    </ol>
  );
}
