// 제품 고르기 화면 (CSA-36 · 조수빈): 중분류 11개를 3D 회전 캐러셀로 고르고, 소분류(모델)를 고른다.
// 대분류(전력·자동화·에너지)는 칩과 이름 아래에 표시한다. 자동 회전 없음 — 사용자가 조작할 때만 움직인다.
// 캐러셀은 위치(pos)를 소수로 들고 있다가 매 프레임 스프링으로 가까운 정수에 맞춘다: 끌 때는 손을 따라 연속으로 움직이고,
// 놓으면 놓은 속도만큼 미끄러지다 가장 가까운 제품군이 정중앙에 감속하며 멈춘다. 처음과 끝은 이어져 있다.
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { familyImage, familyName } from "./productFamilies";
import { useProductTree } from "./useProductTree";
import "./product-select.css";

// focus: 왼쪽 제품 목록에서 누른 제품군. 바뀔 때마다(같은 제품군을 다시 눌러도 n 이 바뀐다) 그쪽으로 돌린다.
type Props = { selected: string | null; onSelect: (code: string) => void; focus?: { family: string; n: number } | null };
type Item = { family: string; name: string; division: string; products: { code: string; name: string }[] };

const RX = 430; // 궤도 가로 반지름
const RZ = 340; // 궤도 앞뒤 깊이
const TILT = 0.55; // 중심을 향해 기울이는 정도 (궤도 각도 대비)
const MAX_TILT = 38; // 이 이상 돌리면 납작해지므로 각도 상한(deg)
const DRAG_PX = 120; // 이만큼 끌면 한 칸
const K = 80; // 정렬 스프링 세기 (임계 감쇠라 튕기지 않는다)
const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));
const reduced = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

export default function ProductPicker({ selected, onSelect, focus }: Props) {
  const { tree, loading, error, reload } = useProductTree();
  const items = useMemo<Item[]>(
    () => tree.flatMap((d) => d.families.map((f) => ({ family: f.family, name: familyName(f.family, f.label), division: d.label, products: f.products }))),
    [tree],
  );
  const [chosen, setChosen] = useState<string | null>(null); // 모델 목록을 연 제품군
  const [pos, setPos] = useState(0); // 연속 위치(소수). 정수면 그 제품군이 정중앙. 한 바퀴 넘어도 끊기지 않게 누적한다.
  const [dragging, setDragging] = useState(false);
  const m = useRef({ pos: 0, vel: 0, target: 0, raf: 0, last: 0, drag: null as null | { x: number; p: number; id: number; lx: number; lt: number; v: number } });
  const moved = useRef(false);
  const n = items.length;
  const mod = (x: number) => ((x % n) + n) % n;
  const wrap = (x: number) => ((((x + n / 2) % n) + n) % n) - n / 2;

  const step = (t: number) => {
    const s = m.current;
    const dt = Math.min(0.032, (t - s.last) / 1000 || 0.016);
    s.last = t;
    s.vel += (K * (s.target - s.pos) - 2 * Math.sqrt(K) * s.vel) * dt; // 임계 감쇠 스프링: 놓은 속도가 관성이 된다
    s.pos += s.vel * dt;
    if (Math.abs(s.target - s.pos) < 0.0006 && Math.abs(s.vel) < 0.002) { s.pos = s.target; s.vel = 0; s.raf = 0; }
    else s.raf = requestAnimationFrame(step);
    setPos(s.pos);
  };
  const goTo = (target: number) => {
    const s = m.current;
    s.target = target;
    if (reduced()) { s.pos = target; s.vel = 0; setPos(target); return; }
    if (!s.raf) { s.last = performance.now(); s.raf = requestAnimationFrame(step); }
  };
  useEffect(() => () => cancelAnimationFrame(m.current.raf), []);

  useEffect(() => {
    if (!focus || n === 0) return;
    const at = items.findIndex((i) => i.family === focus.family);
    if (at < 0) return;
    const base = Math.round(m.current.target);
    goTo(base + wrap(at - base)); // 가까운 쪽으로 돌린다
    setChosen(null); // 모델 목록을 보고 있었으면 캐러셀로 돌아간다
  }, [focus, items]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <p className="ps-note">제품 목록을 불러오는 중이에요…</p>;
  if (error || n === 0) {
    return (
      <div className="ps-note" role="alert">
        제품 목록을 불러오지 못했어요.
        <button type="button" className="ps-link" onClick={reload}>다시 시도</button>
      </div>
    );
  }

  const go = (k: number) => goTo(Math.round(m.current.target) + k);
  const index = mod(Math.round(pos));
  const cur = items[index];
  const chosenItem = items.find((i) => i.family === chosen) ?? null;

  const onDown = (e: PointerEvent<HTMLDivElement>) => {
    const s = m.current;
    cancelAnimationFrame(s.raf); s.raf = 0; s.vel = 0;
    s.drag = { x: e.clientX, p: s.pos, id: e.pointerId, lx: e.clientX, lt: performance.now(), v: 0 };
    moved.current = false;
  };
  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    const s = m.current;
    if (!s.drag) return;
    const dx = e.clientX - s.drag.x;
    if (!moved.current && Math.abs(dx) > 6) { moved.current = true; setDragging(true); e.currentTarget.setPointerCapture(s.drag.id); }
    if (!moved.current) return;
    const now = performance.now();
    const v = (-(e.clientX - s.drag.lx) / DRAG_PX) / Math.max(0.001, (now - s.drag.lt) / 1000);
    s.drag.v = s.drag.v * 0.6 + v * 0.4;
    s.drag.lx = e.clientX; s.drag.lt = now;
    s.pos = s.drag.p - dx / DRAG_PX;
    setPos(s.pos);
  };
  const onUp = () => {
    const s = m.current;
    if (!s.drag) return;
    const v = clamp(s.drag.v, -8, 8);
    s.drag = null; setDragging(false);
    if (!moved.current) return;
    s.vel = v; // 놓은 속도만큼 더 미끄러진 뒤 가장 가까운 제품군에 정렬
    goTo(Math.round(s.pos + v * 0.16));
  };
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowLeft") { e.preventDefault(); go(-1); }
    if (e.key === "ArrowRight") { e.preventDefault(); go(1); }
  };

  if (chosenItem) {
    return (
      <section className="ps ps-models" aria-label={`${chosenItem.name} 모델`}>
        <button type="button" className="ps-back" onClick={() => setChosen(null)}>← 제품군 다시 고르기</button>
        <h2>어떤 모델인가요?</h2>
        <p className="ps-sub">{chosenItem.division} · {chosenItem.name}</p>
        <div className="ps-optlist">
          {chosenItem.products.map((p) => (
            <button key={p.code} type="button" className={`ps-opt${p.code === selected ? " is-sel" : ""}`} onClick={() => onSelect(p.code)}>
              <b>{p.name}</b>
            </button>
          ))}
        </div>
      </section>
    );
  }

  const step_ = (2 * Math.PI) / n;
  return (
    <section className="ps ps-picker" aria-label="제품군 고르기" onKeyDown={onKey}>
      <h2>어떤 제품에 대해 알고 싶으세요?</h2>
      <div className="ps-car" role="group" aria-roledescription="carousel" aria-label="제품군">
        <div className="ps-jump" role="group" aria-label="제품군 바로 보기">
          {tree.map((d) => (
            <div key={d.division} className="ps-jgroup">
              <span>{d.label}</span>
              {d.families.map((f) => {
                const i = items.findIndex((x) => x.family === f.family);
                return (
                  <button key={f.family} type="button" className={i === index ? "is-sel" : ""} aria-pressed={i === index}
                    onClick={() => goTo(Math.round(m.current.target) + wrap(i - Math.round(m.current.target)))}>
                    {familyName(f.family, f.label)}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
        <div className="ps-view">
          <div className="ps-fade">
            <div
              className={`ps-stage${dragging ? " is-dragging" : ""}`}
              onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}
            >
              {items.map((it, i) => {
                const d = wrap(i - pos); // 중앙에서 떨어진 칸 수 (오른쪽 +)
                const a = Math.abs(d);
                const th = d * step_;
                const x = Math.sin(th) * RX;
                const z = (Math.cos(th) - 1) * RZ;
                const tilt = -clamp(th * TILT * (180 / Math.PI), -MAX_TILT, MAX_TILT); // 바깥쪽 제품이 중심을 바라본다
                const scale = 1 - 0.07 * Math.min(a, 3);
                const opacity = clamp(1 - 0.3 * a - 0.04 * a * a, 0, 1); // 옆 제품은 알아볼 만큼, 바깥은 점점 희미하게
                const blur = Math.min(a, 3.5) * 1.3;
                const center = Math.round(d) === 0;
                const src = familyImage(it.family);
                return (
                  <button
                    key={it.family}
                    type="button"
                    tabIndex={center ? 0 : -1}
                    className={`ps-card${center ? " is-center" : ""}`}
                    aria-label={center ? `${it.name} (현재 선택 중)` : `${it.name} 보기`}
                    aria-current={center}
                    style={{
                      transform: `translate3d(${x.toFixed(1)}px,0,${z.toFixed(1)}px) rotateY(${tilt.toFixed(2)}deg) scale(${scale.toFixed(3)})`,
                      opacity: Number(opacity.toFixed(3)),
                      filter: blur > 0.05 ? `blur(${blur.toFixed(2)}px)` : "none",
                      zIndex: Math.round(100 - a * 10),
                      pointerEvents: a > 3 ? "none" : "auto",
                    }}
                    onClick={() => { if (!moved.current && !center) goTo(Math.round(m.current.target + d)); }}
                  >
                    {src && <img src={src} alt="" draggable={false} />}
                  </button>
                );
              })}
            </div>
          </div>
          <button type="button" className="ps-arrow ps-l" aria-label="이전 제품군" onClick={() => go(-1)}>‹</button>
          <button type="button" className="ps-arrow ps-r" aria-label="다음 제품군" onClick={() => go(1)}>›</button>
        </div>
        <div className="ps-info" aria-live="polite">
          <small>{cur.division}</small>
          <h3>{cur.name}</h3>
          <p>{index + 1} / {n}</p>
          <button type="button" className="ps-primary" onClick={() => setChosen(cur.family)}>이 제품군 선택하기</button>
        </div>
      </div>
    </section>
  );
}
