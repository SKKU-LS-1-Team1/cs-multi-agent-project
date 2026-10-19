// 부서별 대시보드 (CSA-43 · 김도연). TODO: 무수정 승인율·수정률·반려율, 유형별 주간 추이
import { useEffect, useState } from "react";
import { api } from "../../api/client";

export default function DeptDashboard() {
  const [rows, setRows] = useState<{ dept: string; open: number; at_risk: number }[]>([]);
  useEffect(() => { api.departments().then(setRows).catch(console.error); }, []);

  return (
    <section style={{ padding: 16 }}>
      <h2>부서별 대시보드</h2>
      <table>
        <thead><tr><th>부서</th><th>진행 중</th><th>SLA 75% 경고</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.dept}><td>{r.dept}</td><td>{r.open}</td><td>{r.at_risk}</td></tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
