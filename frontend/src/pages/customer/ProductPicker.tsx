// 제품 고르기 화면 (CSA-36 · 조수빈): 중분류 11개를 3D 회전 캐러셀로 고르고, 소분류(모델)를 고른다.
// 대분류(전력·자동화·에너지)는 칩과 이름 아래에 표시한다. 자동 회전 없음 — 사용자가 조작할 때만 움직인다.
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { familyImage, familyName } from "./productFamilies";
import { useProductTree } from "./useProductTree";
import "./product-select.css";

// focus: 왼쪽 제품 목록에서 누른 제품군. 바뀔 때마다(같은 제품군을 다시 눌러도 n 이 바뀐다) 그쪽으로 돌린다.
type Props = { selected: string | null; onSelect: (code: string) => void; focus?: { family: string; n: number } | null };
type Item = { family: string; name: string; division: string; products: { code: string; name: string }[] };

const RX = 400; // 궤도 가로 반지름
const RZ = 300; // 궤도 앞뒤 깊이
const DRAG_PX = 110; // 이만큼 끌면 한 칸

export default function ProductPicker({ selected, onSelect, focus }: Props) {
  const { tree, loading, error, reload } = useProductTree();
  const items = useMemo<Item[]>(
    () => tree.flatMap((d) => d.families.map((f) => ({ family: f.family, name: familyName(f.family, f.label), division: d.label, products: f.products }))),
    [tree],
  );
  const [index, setIndex] = useState(0);
  const [chosen, setChosen] = useState<string | null>(null); // 모델 목록을 연 제품군
  const [drag, setDrag] = useState(0);
  const [dragging, setDragging] = useState(false);
  const down = useRef<{ x: number; id: number } | null>(null);
  const moved = useRef(false);
  const n = items.length;

  useEffect(() => {
    if (!focus) return;
    const at = items.findIndex((i) => i.family === focus.family);
    if (at < 0) return;
    setIndex(at);
    setChosen(null); // 모델 목록을 보고 있었으면 캐러셀로 돌아간다
  }, [focus, items]);

  if (loading) return <p className="ps-note">제품 목록을 불러오는 중이에요…</p>;
  if (error || n === 0) {
    return (
      <div className="ps-note" role="alert">
        제품 목록을 불러오지 못했어요.
        <button type="button" className="ps-link" onClick={reload}>다시 시도</button>
      </div>
    );
  }

  const go = (k: number) => setIndex((i) => (((i + k) % n) + n) % n);
  const wrap = (x: number) => ((((x + n / 2) % n) + n) % n) - n / 2;
  const cur = items[index];
  const chosenItem = items.find((i) => i.family === chosen) ?? null;

  const onDown = (e: PointerEvent<HTMLDivElement>) => { down.current = { x: e.clientX, id: e.pointerId }; moved.current = false; };
  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!down.current) return;
    const dx = e.clientX - down.current.x;
    if (!dragging && Math.abs(dx) > 6) { setDragging(true); e.currentTarget.setPointerCapture(down.current.id); }
    if (Math.abs(dx) > 6) { moved.current = true; setDrag(dx); }
  };
  const onUp = () => {
    if (!down.current) return;
    const steps = Math.round(drag / DRAG_PX);
    down.current = null; setDragging(false); setDrag(0);
    if (steps) go(-steps);
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
        <p className="ps-sub">{chosenItem.name}</p>
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

  const frac = drag / DRAG_PX;
  return (
    <section className="ps ps-picker" aria-label="제품군 고르기" onKeyDown={onKey}>
      <h2>어떤 제품에 문제가 있나요?</h2>
      <div className="ps-car" role="group" aria-roledescription="carousel" aria-label="제품군">
        <div className="ps-jump is-top" role="group" aria-label="제품군 바로 보기">
          {tree.map((d) => (
            <div key={d.division} className="ps-jgroup">
              {d.families.map((f) => {
                const i = items.findIndex((x) => x.family === f.family);
                return (
                  <button key={f.family} type="button" className={i === index ? "is-sel" : ""} aria-pressed={i === index} onClick={() => setIndex(i)}>
                    {familyName(f.family, f.label)}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
        <div
          className={`ps-stage${dragging ? " is-dragging" : ""}`}
          onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}
        >
          {items.map((it, i) => {
            const d = wrap(i - index + frac);
            const a = Math.abs(d);
            const th = (d * 2 * Math.PI) / n;
            const x = Math.sin(th) * RX;
            const z = (Math.cos(th) - 1) * RZ;
            const center = a < 0.5;
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
                  transform: `translate3d(${x}px,0,${z}px) scale(${1 - 0.1 * Math.min(a, 3)})`,
                  opacity: Math.max(0, 1 - 0.4 * a),
                  filter: `blur(${Math.min(a, 3) * 1.6}px)`,
                  zIndex: Math.round(100 - a * 10),
                  pointerEvents: a > 2.6 ? "none" : "auto",
                }}
                onClick={() => { if (!moved.current && !center) setIndex(i); }}
              >
                {src && <img src={src} alt="" draggable={false} />}
              </button>
            );
          })}
          <button type="button" className="ps-arrow ps-l" aria-label="이전 제품군" onClick={() => go(-1)}>‹</button>
          <button type="button" className="ps-arrow ps-r" aria-label="다음 제품군" onClick={() => go(1)}>›</button>
        </div>
        <div className="ps-info" aria-live="polite">
          <h3>{cur.name}</h3>
          <p>{index + 1} / {n}</p>
          <button type="button" className="ps-primary" onClick={() => setChosen(cur.family)}>이 제품군 선택하기</button>
        </div>
      </div>
    </section>
  );
}
