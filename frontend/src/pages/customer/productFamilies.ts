// 제품군(중분류) 11개의 화면용 한글 이름과 대표 이미지.
// 이름은 API(/api/products/tree)의 family 코드로 찾는다. 없는 코드는 API가 준 label 을 그대로 쓴다.
const images = import.meta.glob<string>("../../assets/products/*.webp", {
  eager: true,
  query: "?url",
  import: "default",
});

export const FAMILY_KO: Record<string, string> = {
  LV_BREAKER: "저압차단기",
  MV_EQUIP: "고압전력기기",
  TRANSFORMER: "변압기",
  DRIVE: "인버터",
  UPS: "무정전전원장치(UPS)",
  ESS: "에너지저장장치(ESS)",
  PV: "태양광",
  METER: "전력계측기",
  CONTROL: "제어기",
  PLC: "PLC",
  HMI: "HMI",
};

export const familyName = (family: string, fallback: string): string => FAMILY_KO[family] ?? fallback;

/** 제품군 대표 이미지 URL (모델별 이미지는 없다). 없으면 undefined. */
export const familyImage = (family: string): string | undefined =>
  images[`../../assets/products/${family}.webp`];
