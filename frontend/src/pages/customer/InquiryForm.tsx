// 문의하기 (자동 채움) (CSA-39 · 조수빈). 빈 필수 항목은 빨간 칸, 채우기 전에는 제출 불가.
import { useState } from "react";
import { api, type InquiryForm as FormDraft } from "../../api/client";

type Props = { draft: FormDraft; onDone: () => void };

export default function InquiryForm({ draft, onDone }: Props) {
  const [fields, setFields] = useState<Record<string, string>>(draft.fields);
  const [body, setBody] = useState(draft.body);
  const required = [...Object.keys(draft.fields), ...draft.missing_required];
  const empty = required.filter((k) => !fields[k]);

  const submit = async () => {
    await api.submitInquiry({
      channel: "WEB_FORM",
      category: draft.category,
      product_code: draft.product_code,
      subject: draft.subject,
      body,
      provided_fields: fields,
    });
    onDone();
  };

  return (
    <section>
      <h2>문의하기</h2>
      <p>유형: {draft.category} · 제품: {draft.product_code ?? "미확인"}</p>
      {required.map((k) => (
        <label key={k} style={{ display: "block", marginBottom: 6 }}>
          {k}{" "}
          <input
            value={fields[k] ?? ""}
            onChange={(e) => setFields({ ...fields, [k]: e.target.value })}
            style={{ borderColor: fields[k] ? undefined : "red" }}
          />
        </label>
      ))}
      <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={6} style={{ width: "100%" }} />
      <button onClick={submit} disabled={empty.length > 0}>제출</button>
    </section>
  );
}
