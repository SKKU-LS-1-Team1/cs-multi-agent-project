// 기술문서 원문(마크다운 일부 문법)을 화면용으로 변환한다. 표·제목·목록·굵게만 지원한다.
import type { ReactNode } from "react";

const inline = (v: string): ReactNode[] =>
  v.split(/(\*\*[^*]+\*\*)/g).map((p, i) => (p.startsWith("**") && p.endsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : p));

export default function DocContent({ text }: { text: string }) {
  const lines = text.replace(/^---[\s\S]*?---\s*/, "").split("\n"), out: ReactNode[] = [];
  const cols = (l: string) => l.split("|").slice(1, -1).map((v) => v.trim());
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith("|") && /^\|[\s:|-]+\|$/.test(lines[i + 1] || "")) {
      const head = cols(line), body: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].startsWith("|")) body.push(cols(lines[i++]));
      i--;
      out.push(
        <div key={i} className="overflow-x-auto rounded-xl border">
          <table className="w-full text-sm">
            <thead className="bg-secondary"><tr>{head.map((h, k) => <th key={k} className="px-3 py-2 text-left font-semibold">{inline(h)}</th>)}</tr></thead>
            <tbody>{body.map((r, k) => <tr key={k} className="border-t">{r.map((c, j) => <td key={j} className="px-3 py-2 align-top">{inline(c)}</td>)}</tr>)}</tbody>
          </table>
        </div>,
      );
      continue;
    }
    const h = line.match(/^(#{1,6})\s+(.*)/);
    if (h) out.push(<h4 key={i} className={h[1].length <= 1 ? "mt-4 text-lg font-bold" : "mt-3 font-semibold"}>{inline(h[2])}</h4>);
    else if (line.startsWith("- ")) out.push(<p key={i} className="pl-3">• {inline(line.slice(2))}</p>);
    else if (line.trim()) out.push(<p key={i} className="leading-relaxed">{inline(line)}</p>);
  }
  return <div className="grid gap-2 text-sm">{out}</div>;
}
