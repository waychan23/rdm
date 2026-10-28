import { useCallback, useEffect, useState } from "react";

export interface AsyncState<T> {
  data: T | undefined;
  error: unknown;
  loading: boolean;
  reload: () => void;
}

/**
 * Run an async fetcher (typically an api.get call) and expose {data, error,
 * loading, reload}. `reload` bumps a nonce; deps re-run the fetch.
 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [nonce, setNonce] = useState(0);
  const [state, setState] = useState<{ data?: T; error?: unknown; loading: boolean }>(
    { loading: true },
  );

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    let alive = true;
    setState({ loading: true });
    fn()
      .then((data) => alive && setState({ data, loading: false }))
      .catch((error) => alive && setState({ error, loading: false }));
    return () => {
      alive = false;
    };
    // fn is recreated each render; callers pass the real dependencies explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce, ...deps]);

  return { data: state.data, error: state.error, loading: state.loading, reload };
}
