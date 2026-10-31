import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

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
  const { i18n } = useTranslation();
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
    // The language is an implicit dependency: backend text (workflow names,
    // notifications) must be refetched after a switch (§17.115).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce, i18n.language, ...deps]);

  return { data: state.data, error: state.error, loading: state.loading, reload };
}
