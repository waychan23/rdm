import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useSearchParams, type SetURLSearchParams } from "react-router-dom";

// The item drawer is a route, so opening it replaces the list URL. The list
// keeps rendering behind the drawer, but its route params would read from
// `/items/<id>` and the filters would silently reset. The overlay therefore
// re-hydrates the backdrop from the URL the drawer was opened from and keeps
// later filter edits in memory (the address bar belongs to the drawer).

interface OriginState {
  /** Path of the list page behind the drawer, e.g. `/projects/RDM/backlog`. */
  path: string;
  /** Current list query string, without the leading `?`. */
  search: string;
  /**
   * Project named by the origin route (`:key`), or "" for a global page such
   * as `/inbox` or `/mailbox`. `null` means the origin has no project notion.
   */
  projectKey: string | null;
  setSearch: (next: string) => void;
}

const OriginSearchContext = createContext<OriginState | null>(null);

function splitOrigin(origin: string): { path: string; search: string } {
  const index = origin.indexOf("?");
  return index < 0
    ? { path: origin, search: "" }
    : { path: origin.slice(0, index), search: origin.slice(index + 1) };
}

export function OriginSearchProvider({
  origin,
  projectKey = null,
  onOriginChange,
  children,
}: {
  /** Full list URL (`path?query`) the drawer was opened from. */
  origin: string;
  /** Project named by the origin route; "" for a global page. */
  projectKey?: string | null;
  /** Reports the live origin URL so the drawer closes to the current state. */
  onOriginChange?: (origin: string) => void;
  children: ReactNode;
}) {
  const [initial] = useState(() => splitOrigin(origin));
  const [path] = useState(initial.path);
  const [search, setSearchState] = useState(initial.search);
  const setSearch = useCallback(
    (next: string) => {
      setSearchState(next);
      onOriginChange?.(next ? `${path}?${next}` : path);
    },
    [path, onOriginChange],
  );
  const state = useMemo<OriginState>(
    () => ({ path, search, projectKey, setSearch }),
    [path, search, projectKey, setSearch],
  );
  return (
    <OriginSearchContext.Provider value={state}>
      {children}
    </OriginSearchContext.Provider>
  );
}

/**
 * Like `useSearchParams`, but while the page is the drawer's backdrop it reads
 * (and writes) the origin URL instead of the item route's URL.
 */
export function useListSearchParams(): [URLSearchParams, SetURLSearchParams] {
  const [urlParams, setUrlParams] = useSearchParams();
  const origin = useContext(OriginSearchContext);
  const params = useMemo(
    () => (origin ? new URLSearchParams(origin.search) : urlParams),
    [origin, urlParams],
  );
  const setParams = useCallback<SetURLSearchParams>(
    (next, options) => {
      if (origin) {
        const resolved =
          typeof next === "function" ? next(new URLSearchParams(origin.search)) : next;
        if (resolved !== undefined) origin.setSearch(resolved.toString());
        return;
      }
      setUrlParams(next, options);
    },
    [origin, setUrlParams],
  );
  return [params, setParams];
}

/** The URL a backdrop row should return to when its drawer closes. */
export function useListOrigin(): string | null {
  const origin = useContext(OriginSearchContext);
  if (!origin) return null;
  return origin.search ? `${origin.path}?${origin.search}` : origin.path;
}

/**
 * Project key for a page rendered as a drawer backdrop: the origin route's
 * `:key` (or "" for a global page). Falls back to the page's own route param
 * when it is the real page. Backdrop pages are not mounted under their own
 * route, so `useParams()` cannot be trusted there.
 */
export function useListProjectKey(fallback: string): string {
  const origin = useContext(OriginSearchContext);
  return origin?.projectKey ?? fallback;
}
