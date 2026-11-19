import { useEffect, useState } from "react";

/** `value`, delayed by `ms`. A change of `key` (a new document/tab) applies immediately. */
export function useDebounced<T>(value: T, ms: number, key: unknown = null): T {
  const [state, setState] = useState({ key, value });
  useEffect(() => {
    if (state.key !== key) {
      setState({ key, value });
      return;
    }
    const t = setTimeout(() => setState({ key, value }), ms);
    return () => clearTimeout(t);
  }, [value, key, ms, state.key]);
  return state.key === key ? state.value : value;
}
