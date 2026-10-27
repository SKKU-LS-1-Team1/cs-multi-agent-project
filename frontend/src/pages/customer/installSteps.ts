// 설치 가이드(IG) 문서의 절을 사용자용 단계로 바꾼다 (CSA-37 · 조수빈). 원문의 순서와 값은 그대로 두고, 한국어 제목과 짧은 설명만 붙인다.
// 원문에 없는 절차·수치는 만들지 않는다. 문장은 "문서에 있는 정해진 문장"과 맞을 때만 한국어로 옮기고, 아니면 원문을 그대로 보여 준다.
// 절 번호는 화면 번호가 아니라 출처로만 쓴다 (단계 번호는 1, 2, 3 …).
import type { DocSection } from "../../api/client";
import { parseBlocks, type Block } from "./MarkdownText";

export type GuideStep = {
  section: string; // 출처가 되는 문서 절 번호
  group?: string;
  title: string;
  lead?: string | null;
  checks?: string[];
  bullets?: string[];
  ordered?: string[];
  checklist?: string[];
  table?: { head: string[]; rows: string[][] };
  cautions?: string[];
  notes?: string[]; // 자료에 없거나 불명확한 값
  raw?: string[]; // "자세히 보기" — 한국어로 옮긴 문장의 원문
};

const sentences = (t: string) => t.split(/(?<=\.)\s+(?=[A-Z(])/).map((x) => x.trim()).filter(Boolean);
const itemsOf = (blocks: Block[]): string[] =>
  blocks.flatMap((b) => (b.t === "p" ? sentences(b.text) : b.t === "ul" || b.t === "ol" || b.t === "check" ? b.items : []));

const CHECK_KO: Record<string, string> = {
  "Product rating matches the drawing": "제품 정격이 도면과 일치해요",
  "All terminals tightened to specified torque": "모든 단자를 지정한 토크로 조였어요",
  "Protective earth connected": "보호 접지를 연결했어요",
  "Insulation resistance measured and recorded": "절연 저항을 측정하고 기록했어요",
  "Settings / parameters recorded": "설정·파라미터를 기록했어요",
};

function safety(blocks: Block[]): GuideStep {
  const raw = itemsOf(blocks);
  const std = /qualified personnel/i.test(raw[0] ?? "") && /lock out/i.test(raw[1] ?? "") && /absence of voltage/i.test(raw[2] ?? "");
  return {
    section: "1", group: "준비하기", title: "안전부터 확인해요",
    lead: std ? "작업 전에 먼저 전원을 안전하게 막아 두세요." : null,
    checks: std ? ["모든 전원을 차단하고 잠가요", "전압이 없는지 확인해요"] : [],
    cautions: std ? ["설치·배선·시운전은 자격을 갖춘 담당자가 해야 해요."] : raw,
    raw: std ? raw : [],
  };
}

function receiving(blocks: Block[]): GuideStep {
  const raw = itemsOf(blocks);
  const m = raw.join(" ").match(/within (\d+) days \(see ([A-Z-]+)\)\. Store indoors in a dry place between (-?\d+) and \+?(\d+) °C, relative humidity below (\d+)%/);
  return {
    section: "2", group: "준비하기", title: "받은 제품을 확인하고 보관해요",
    lead: m ? "도착하면 포장부터 살펴보고, 설치 전까지는 아래 조건으로 보관해요." : null,
    checks: m ? [`포장이 파손됐다면 ${m[1]}일 이내에 알려요 (${m[2]} 참고)`, `실내 건조한 곳, ${m[3]} ~ +${m[4]} °C`, `상대습도 ${m[5]}% 미만, 결로 없이`] : [],
    bullets: m ? [] : raw, raw: m ? raw : [],
  };
}

function mounting(blocks: Block[]): GuideStep {
  const raw = itemsOf(blocks);
  const bullets = raw.map((t) => {
    let m: RegExpMatchArray | null;
    if ((m = t.match(/^Required clearances:\s*(.*)$/))) return `필요한 간격: ${m[1]}`;
    if ((m = t.match(/^Operating temperature:\s*(.*)$/))) return `사용 온도: ${m[1]}`;
    if ((m = t.match(/^Degree of protection:\s*(.*)$/))) return `보호 등급: ${m[1]}`;
    if ((m = t.match(/^Above ([\d,]+) m altitude, apply derating per the datasheet\.?$/))) return `고도 ${m[1]} m 이상에서는 데이터시트에 따라 용량을 낮춰 써요 (디레이팅)`;
    return t;
  });
  return { section: "3", group: "설치하기", title: "설치할 자리를 정해요", lead: "필요한 간격과 사용 환경을 확인하고 자리를 잡아요.", bullets, raw };
}

function wiring(blocks: Block[]): GuideStep {
  const raw = itemsOf(blocks);
  const bullets: string[] = [], notes: string[] = [];
  for (const t of raw) {
    let m: RegExpMatchArray | null;
    if ((m = t.match(/^Terminal tightening torque:\s*(.*)$/))) {
      // 조임 토크는 N·m 값이 있을 때만 수치로 보여 준다. 그 밖의 글(예: "see dimension drawing")은 값이 없는 것으로 알린다.
      if (/N\s*·\s*m/i.test(m[1])) bullets.push(`단자 조임 토크: ${m[1]}`);
      else notes.push(`조임 토크 수치가 자료에 없거나 불명확해요 (원문: "${m[1]}"). 치수 도면을 확인해 주세요.`);
    } else if ((m = t.match(/^Use copper conductors rated for at least (\d+) °C\.?$/))) bullets.push(`${m[1]} °C 이상 등급의 구리 도체를 써요`);
    else if ((m = t.match(/^Separate power and signal cables by at least (\d+) mm\.?$/))) bullets.push(`전력선과 신호선은 ${m[1]} mm 이상 떨어뜨려요`);
    else bullets.push(t);
  }
  return { section: "4", group: "설치하기", title: "배선하고 조여요", lead: "자료에 적힌 배선 조건대로 연결해요.", bullets, notes, raw };
}

const commissioning = (blocks: Block[]): GuideStep => ({
  section: "5", group: "설치 후 확인하기", title: "시운전해요", lead: "아래 순서대로 하나씩 진행해요. 문장은 원문 그대로예요.", ordered: itemsOf(blocks),
});
const preCheck = (blocks: Block[]): GuideStep => ({
  section: "6", group: "설치 후 확인하기", title: "전원을 넣기 전에 점검해요", lead: "모두 확인한 뒤에 전원을 넣어요.", checklist: itemsOf(blocks).map((t) => CHECK_KO[t] ?? t),
});
function issues(blocks: Block[]): GuideStep {
  const table = blocks.find((b): b is Extract<Block, { t: "table" }> => b.t === "table");
  const tail = blocks.find((b) => b.t === "p");
  return {
    section: "7", title: "막히면 이렇게 확인해요", lead: "설치 중 자주 생기는 문제예요. 표의 마지막 칸 문서에 자세한 방법이 있어요.",
    table: table && { head: table.head, rows: table.rows }, raw: tail && tail.t === "p" ? [tail.text] : [],
  };
}

const BUILDERS: Record<string, (b: Block[]) => GuideStep> = { "1": safety, "2": receiving, "3": mounting, "4": wiring, "5": commissioning, "6": preCheck, "7": issues };

/** 설치 가이드 절 → 단계. 알려진 절이 하나도 없으면 null(기존 목록으로 보여 준다). */
export function buildInstallSteps(sections: DocSection[]): GuideStep[] | null {
  const steps = sections
    .filter((s) => BUILDERS[s.section])
    .map((s) => BUILDERS[s.section](parseBlocks(s.text)));
  return steps.length ? steps : null;
}
