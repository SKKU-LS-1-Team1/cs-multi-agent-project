#!/usr/bin/env python3
"""설치·사용 방법 안내의 원문을 PDF로 만든다 (frontend/public/downloads/pdf/, 모델마다 2개 → 46개).
제공 자료에는 Markdown 원문만 있어서, docs.json 에 나뉜 원문을 그대로 HTML로 옮기고 Chrome 으로 인쇄한다.
문장·표는 원문 그대로이고, 내용을 더하거나 바꾸지 않는다.
  - IG-{모델}.pdf     : 설치 가이드 (설치 방법 안내, 자료 탭의 "설치 가이드")
  - {모델}-usage.pdf  : 사용 방법 가이드. 사용 방법 안내가 쓰는 문서(데이터시트, 설치 가이드, 유지보수, 릴리스 노트)를 한 파일로 묶는다.
나머지 문서(데이터시트·유지보수·릴리스 노트·문제 해결)는 PDF 없이 기존 Markdown 원본을 내려받는다.
"""
import html, json, os, re, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = json.loads((HERE.parent / "src/home/data/docs.json").read_text())
OUT = HERE.parent / "public/downloads/pdf"
# Chrome 실행 파일: 환경변수 CHROME 으로 지정하거나, 흔한 설치 위치에서 찾는다
CHROME = os.environ.get("CHROME") or next((p for p in (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser",
) if os.path.exists(p)), None)
USAGE = ["DS", "IG", "MG", "RN"]  # 화면 lib/guide.js 의 사용 방법 안내가 근거로 쓰는 문서

CSS = """
@page { size: A4; margin: 18mm 16mm; }
body { font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif; font-size: 10.5pt; line-height: 1.55; color: #111; }
h1 { font-size: 17pt; margin: 0 0 6px; } h2 { font-size: 12.5pt; margin: 18px 0 6px; } h3 { font-size: 11pt; margin: 12px 0 4px; }
.meta { color: #666; font-size: 9pt; margin-bottom: 10px; }
blockquote { margin: 0 0 12px; padding: 6px 10px; background: #f3f4f6; color: #444; font-size: 9pt; }
table { border-collapse: collapse; width: 100%; margin: 6px 0; font-size: 9.5pt; } th, td { border: 1px solid #bbb; padding: 4px 6px; text-align: left; vertical-align: top; } th { background: #eef1f5; }
ul, ol { margin: 4px 0; padding-left: 20px; } .check { list-style: none; padding-left: 4px; }
.doc + .doc { page-break-before: always; }
"""


def inline(t):
    t = html.escape(t)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)


def block(b):
    t = b["t"]
    if t == "p":
        return f"<p>{inline(b['text'])}</p>"
    if t == "quote":
        return f"<blockquote>{inline(b['text'])}</blockquote>"
    if t in ("ul", "ol"):
        return f"<{t}>" + "".join(f"<li>{inline(x)}</li>" for x in b["items"]) + f"</{t}>"
    if t == "check":
        return '<ul class="check">' + "".join(f"<li>☐ {inline(re.sub(r'^\[[ xX]?\]\s*', '', x))}</li>" for x in b["items"]) + "</ul>"
    if t == "table":
        head = "".join(f"<th>{inline(c)}</th>" for c in b.get("head", []))
        rows = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in b["rows"])
        return f"<table>{f'<tr>{head}</tr>' if head else ''}{rows}</table>"
    raise ValueError(f"모르는 블록: {t}")


def doc_html(d):
    out = [f'<section class="doc"><div class="meta">{html.escape(d["id"])} · Rev. {html.escape(str(d["revision"]))}</div>']
    for s in d["sections"]:
        if s["title"]:
            lv = min(max(s["level"], 1), 3)
            num = f'{s["num"]}. ' if s["num"] != "0" else ""
            out.append(f"<h{lv}>{num}{inline(s['title'])}</h{lv}>")
        out += [block(b) for b in s["blocks"]]
    return "".join(out) + "</section>"


def to_pdf(docs, path, tmp):
    page = tmp / (path.stem + ".html")
    page.write_text(f"<!doctype html><meta charset=utf-8><style>{CSS}</style>" + "".join(doc_html(d) for d in docs))
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={path}", page.as_uri()],
                   check=True, capture_output=True, timeout=60)


def main():
    if not CHROME:
        sys.exit("Chrome 을 찾지 못했어요. CHROME=/경로/chrome 으로 지정해 주세요.")
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.pdf"):
        old.unlink()
    n = 0
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        for model, docs in DOCS.items():
            if "IG" not in docs:
                continue  # 정책 문서 묶음
            to_pdf([docs["IG"]], OUT / f"{docs['IG']['id']}.pdf", tmp)
            n += 1
            to_pdf([docs[k] for k in USAGE if k in docs], OUT / f"{model}-usage.pdf", tmp)
            n += 1
    print(f"{n}개 PDF → {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
