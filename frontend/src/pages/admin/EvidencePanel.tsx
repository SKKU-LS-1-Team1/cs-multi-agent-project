// 근거 문서 · 자동 점검 결과 표시 (CSA-42 · 김도연)
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
          <pre style={{ whiteSpace: "pre-wrap" }}>{e.text}</pre>
        </details>
      ))}
    </aside>
  );
}
