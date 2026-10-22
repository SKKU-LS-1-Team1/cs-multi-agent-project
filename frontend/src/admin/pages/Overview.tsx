// 업무 현황 셸: 밑줄 탭으로 C/S 업무 · 전문부서 협업 · 리소스 배정을 오간다.
import { useLocation } from "react-router-dom";
import { PageHeader, UnderlineTabs, useGo } from "@admin/components/admin/common";
import CsWork from "./overview/CsWork";
import Collab from "./overview/Collab";
import ResourceBoard from "./ResourceBoard";

const TABS = [["cs", "C/S 업무"], ["collab", "전문부서 협업"], ["resources", "리소스 배정"]] as const;
const PATH = { cs: "/", collab: "/collab", resources: "/resources" };
const TITLES = { cs: "고객지원 업무 현황", collab: "전문부서 협업 현황", resources: "리소스 배정" };

export default function Overview() {
  const path = useLocation().pathname;
  const view = path === "/collab" ? "collab" : path === "/resources" ? "resources" : "cs";
  const go = useGo();
  const tabs = <UnderlineTabs tabs={TABS} value={view} onChange={(v) => go.to(PATH[v])} />;
  if (view === "collab") return <Collab tabs={tabs} />;
  if (view === "cs") return <CsWork tabs={tabs} />;
  return (
    <>
      <PageHeader title={TITLES[view]}>{tabs}</PageHeader>
      <ResourceBoard />
    </>
  );
}
