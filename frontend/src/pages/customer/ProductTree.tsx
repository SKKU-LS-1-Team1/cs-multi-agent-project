// 제품 대시보드 분류 트리: 대 3 · 중 11 · 소 23 (CSA-36 · 조수빈)
import { useEffect, useState } from "react";
import { api, type ProductTree as Tree } from "../../api/client";

type Props = { selected: string | null; onSelect: (code: string) => void };

export default function ProductTree({ selected, onSelect }: Props) {
  const [tree, setTree] = useState<Tree>([]);
  useEffect(() => { api.productTree().then(setTree).catch(console.error); }, []);

  return (
    <aside style={{ borderRight: "1px solid #ddd", padding: 12, overflow: "auto" }}>
      {tree.map((d) => (
        <details key={d.division} open>
          <summary><b>{d.label}</b></summary>
          {d.families.map((f) => (
            <details key={f.family} open={f.products.some((p) => p.code === selected)} style={{ marginLeft: 12 }}>
              <summary>{f.family}</summary>
              {f.products.map((p) => (
                <div
                  key={p.code}
                  onClick={() => onSelect(p.code)}
                  style={{ marginLeft: 12, cursor: "pointer", fontWeight: p.code === selected ? 700 : 400 }}
                >
                  {p.name}
                </div>
              ))}
            </details>
          ))}
        </details>
      ))}
    </aside>
  );
}
