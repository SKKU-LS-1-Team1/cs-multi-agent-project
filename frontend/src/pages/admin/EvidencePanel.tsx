// 근거 문서 · 자동 점검 결과 표시 (CSA-42 · 김도연)
// 지식 그래프 사례(CSA-73)는 따라간 경로(제품 → 에러코드 → 고장 → 사례 → 문서 절)를 한 줄로 보여 준다.
import type { CheckResult, Evidence } from "../../api/client";

export default function EvidencePanel({ evidence, checks }: { evidence: Evidence[]; checks: CheckResult[] }) {
  return (
    <aside>
      <h3>자동 점검</h3>
      <ul>
        {checks.map((c) => (
          <li key={c.name}>{c.passed ? "✅" : "❌"} {c.name} {c.reason}</li>
        ))}
      </ul>
      <h3>근거</h3>
      {evidence.map((e, i) => (
        <details key={`${e.doc_id}-${i}`}>
          <summary>[{i + 1}] {e.doc_id} {e.section} ({e.source})</summary>
          {e.metadata?.graph_path && <p>근거 경로: {e.metadata.graph_path}</p>}
          <pre style={{ whiteSpace: "pre-wrap" }}>{e.text}</pre>
        </details>
      ))}
    </aside>
  );
}
