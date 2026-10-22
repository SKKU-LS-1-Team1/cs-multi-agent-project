// 제품 대시보드 분류 트리: 대 3 · 중 11 · 소 23 (CSA-36 · 조수빈)
// 좌측 사이드바용 접이식 트리. 큰 화면에서 고르는 화면은 ProductPicker.tsx.
import { familyImage, familyName } from "./productFamilies";
import { useProductTree } from "./useProductTree";
import "./product-select.css";

type Props = { selected: string | null; onSelect: (code: string) => void };

export default function ProductTree({ selected, onSelect }: Props) {
  const { tree, loading, error, reload } = useProductTree();

  return (
    <aside className="ps ps-tree" aria-label="제품 분류">
      {loading && <p className="ps-note">제품 목록을 불러오는 중이에요…</p>}
      {error && (
        <div className="ps-note" role="alert">
          제품 목록을 불러오지 못했어요.
          <button type="button" className="ps-link" onClick={reload}>다시 시도</button>
        </div>
      )}
      {tree.map((d) => (
        <details key={d.division} open>
          <summary className="ps-div">{d.label}</summary>
          {d.families.map((f) => {
            const img = familyImage(f.family);
            return (
              <details key={f.family} open={f.products.some((p) => p.code === selected)} className="ps-fam">
                <summary>
                  {img && <img src={img} alt="" width={28} height={28} />}
                  <span>{familyName(f.family, f.label)}</span>
                  <em>{f.products.length}</em>
                </summary>
                {f.products.map((p) => (
                  <button
                    key={p.code}
                    type="button"
                    className={`ps-item${p.code === selected ? " is-sel" : ""}`}
                    aria-current={p.code === selected}
                    onClick={() => onSelect(p.code)}
                  >
                    <span>{p.name}</span>
                    <small>{p.code}</small>
                  </button>
                ))}
              </details>
            );
          })}
        </details>
      ))}
    </aside>
  );
}
