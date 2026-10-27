// 기술문서 절(Markdown 조각)을 읽기 좋게 그린다. 문서에 있는 글자만 보여 주고 고치지 않는다.
// 지원: 제목(#) · 문단 · 목록(- , 1.) · 체크박스(- [ ]) · 표 · 굵게 · 인용.
import { Fragment, type ReactNode } from "react";

export type Block =
  | { t: "h"; text: string }
  | { t: "p"; text: string }
  | { t: "quote"; text: string }
  | { t: "ul" | "ol" | "check"; items: string[] }
  | { t: "table"; head: string[]; rows: string[][] };

const cells = (line: string) => line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

export function parseBlocks(text: string): Block[] {
  const lines = text.split("\n");
  const out: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const ln = lines[i].trimEnd();
    if (!ln.trim()) { i++; continue; }
    if (ln.startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        const c = cells(lines[i]);
        if (!c.every((x) => /^[-: ]*$/.test(x))) rows.push(c);
        i++;
      }
      out.push({ t: "table", head: rows[0] ?? [], rows: rows.slice(1) });
      continue;
    }
    if (/^#{1,6}\s/.test(ln)) { out.push({ t: "h", text: ln.replace(/^#+\s*/, "") }); i++; continue; }
    if (ln.startsWith(">")) { out.push({ t: "quote", text: ln.replace(/^>\s*/, "") }); i++; continue; }
    const kind = /^- \[[ x]\] /.test(ln) ? "check" : /^- /.test(ln) ? "ul" : /^\d+\.\s/.test(ln) ? "ol" : null;
    if (kind) {
      const re = kind === "check" ? /^- \[[ x]\] (.*)/ : kind === "ul" ? /^- (.*)/ : /^\d+\.\s+(.*)/;
      const items: string[] = [];
      for (let m = re.exec(lines[i] ?? ""); m; m = re.exec(lines[i] ?? "")) { items.push(m[1].trim()); i++; }
      out.push({ t: kind, items });
      continue;
    }
    const para = [ln];
    i++;
    while (i < lines.length && lines[i].trim() && !/^(\||- |\d+\.\s|>|#)/.test(lines[i])) { para.push(lines[i].trim()); i++; }
    out.push({ t: "p", text: para.join(" ") });
  }
  return out;
}

const inline = (s: string): ReactNode[] =>
  s.split(/(\*\*[^*]+\*\*)/g).map((p, i) => (p.startsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : <Fragment key={i}>{p}</Fragment>));

export default function MarkdownText({ text }: { text: string }) {
  return (
    <div className="pd-md">
      {parseBlocks(text).map((b, i) => {
        switch (b.t) {
          case "h": return <h5 key={i}>{inline(b.text)}</h5>;
          case "p": return <p key={i}>{inline(b.text)}</p>;
          case "quote": return <blockquote key={i}>{inline(b.text)}</blockquote>;
          case "ul": return <ul key={i}>{b.items.map((x) => <li key={x}>{inline(x)}</li>)}</ul>;
          case "ol": return <ol key={i}>{b.items.map((x) => <li key={x}>{inline(x)}</li>)}</ol>;
          case "check": return <ul key={i} className="pd-check">{b.items.map((x) => <li key={x}>☐ {inline(x)}</li>)}</ul>;
          case "table": return (
            <div className="pd-tw" key={i}>
              <table>
                <thead><tr>{b.head.map((h) => <th key={h}>{h}</th>)}</tr></thead>
                <tbody>{b.rows.map((r, j) => <tr key={j}>{r.map((c, k) => <td key={k}>{inline(c)}</td>)}</tr>)}</tbody>
              </table>
            </div>
          );
        }
      })}
    </div>
  );
}
