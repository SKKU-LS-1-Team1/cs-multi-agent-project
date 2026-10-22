import { useCallback, useEffect, useState } from "react";
import { api, type ProductTree } from "../../api/client";

type State = { tree: ProductTree; loading: boolean; error: string | null };

/** 제품 분류 트리(대 3 · 중 11 · 소 23)를 API 에서 읽는다. 실패하면 error 에 이유를 담고 reload 로 다시 시도한다. */
export function useProductTree() {
  const [state, setState] = useState<State>({ tree: [], loading: true, error: null });
  const load = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    api
      .productTree()
      .then((tree) => setState({ tree, loading: false, error: null }))
      .catch((e: unknown) => setState({ tree: [], loading: false, error: e instanceof Error ? e.message : String(e) }));
  }, []);
  useEffect(load, [load]);
  return { ...state, reload: load };
}
