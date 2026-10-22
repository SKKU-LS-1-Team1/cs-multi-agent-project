import { Button } from "@admin/components/ui/button";
import { PageHeader, useGo } from "@admin/components/admin/common";

export default function NotFound() {
  const go = useGo();
  return (
    <>
      <PageHeader title="페이지를 찾을 수 없습니다" />
      <div className="grid max-w-lg gap-4 px-8">
        <p className="text-muted-foreground">주소가 바뀌었거나 삭제된 화면입니다. 아래에서 다시 이동해 주세요.</p>
        <div className="flex gap-2">
          <Button onClick={() => go.to("/")}>업무 현황으로</Button>
          <Button variant="outline" onClick={() => go.list({ filter: "전체" })}>문의 목록으로</Button>
        </div>
      </div>
    </>
  );
}
