// 상담원 작업 목록: SLA 순 정렬, 75% 경고 (CSA-40 · 김도연)
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type WorkItem } from "../../api/client";

export default function WorkList() {
  const [rows, setRows] = useState<WorkItem[]>([]);
  useEffect(() => { api.workList().then(setRows).catch(console.error); }, []);

  return (
    <section style={{ padding: 16 }}>
      <h2>상담원 작업 목록</h2>
      <table>
        <thead>
          <tr><th>티켓</th><th>유형</th><th>우선순위</th><th>부서</th><th>상태</th><th>SLA 경과</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.ticket_id} style={{ background: r.at_risk ? "#fee" : undefined }}>
              <td><Link to={`/admin/tickets/${r.ticket_id}`}>{r.ticket_id}</Link></td>
              <td>{r.category}</td>
              <td>{r.priority}</td>
              <td>{r.assigned_dept}</td>
              <td>{r.status}</td>
              <td>{Math.round(r.sla_ratio * 100)}%{r.at_risk ? " ⚠" : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
