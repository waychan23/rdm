// Notification surface. Atlaskit's "bold" flags (anything but normal, i.e. every
// success/error flag) mount their description and actions inside a disclosure
// that starts collapsed and exposes no API to open it, so an error flag hid the
// failure reason behind an extra click. Notifications are rendered here as
// always-expanded SectionMessages in a fixed stack instead.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { cssMap } from "@atlaskit/css";
import SectionMessage from "@atlaskit/section-message";
import { Box } from "@atlaskit/primitives/compiled";

export interface Notify {
  success: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
}

interface Notice {
  id: number;
  appearance: "success" | "error";
  title: string;
  description?: string;
}

// Same dwell time as Atlaskit's AutoDismissFlag.
const SUCCESS_DISMISS_MS = 8_000;

const styles = cssMap({
  // Anchored where Atlaskit flags render (bottom start, space.600 inset) and as
  // wide as them (25pc), so the shift is not noticeable.
  region: {
    position: "fixed",
    insetBlockEnd: "var(--ds-space-600)",
    insetInlineStart: "var(--ds-space-600)",
    display: "flex",
    flexDirection: "column",
    gap: "var(--ds-space-200)",
    width: "400px",
    // @atlaskit/theme layers.flag().
    zIndex: 800,
  },
});

const NotifyContext = createContext<Notify | null>(null);

export function NotifyProvider({ children }: { children: ReactNode }) {
  const [notices, setNotices] = useState<Notice[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setNotices((current) => current.filter((notice) => notice.id !== id));
  }, []);

  const show = useCallback(
    (appearance: Notice["appearance"], title: string, description?: string) => {
      const id = nextId.current++;
      setNotices((current) => {
        // Rapid inline saves all report the same result; keep one success card
        // (new id restarts its dismiss timer) instead of stacking duplicates.
        const kept =
          appearance === "success"
            ? current.filter(
                (notice) =>
                  !(
                    notice.appearance === "success" &&
                    notice.title === title &&
                    notice.description === description
                  ),
              )
            : current;
        return [...kept, { id, appearance, title, description }];
      });
    },
    [],
  );

  const api = useMemo<Notify>(
    () => ({
      success: (title, description) => show("success", title, description),
      error: (title, description) => show("error", title, description),
    }),
    [show],
  );

  return (
    <NotifyContext.Provider value={api}>
      {children}
      <Box
        xcss={styles.region}
        // cssMap's width type rejects calc(), so the mobile clamp is inline.
        style={{ maxWidth: "calc(100vw - 2 * var(--ds-space-600))" }}
        testId="notification-region"
      >
        {notices.map((notice) => (
          <NoticeCard key={notice.id} notice={notice} onDismiss={dismiss} />
        ))}
      </Box>
    </NotifyContext.Provider>
  );
}

export function useNotify(): Notify {
  const api = useContext(NotifyContext);
  if (!api) throw new Error("useNotify must be used inside <NotifyProvider>");
  return api;
}

function NoticeCard({
  notice,
  onDismiss,
}: {
  notice: Notice;
  onDismiss: (id: number) => void;
}) {
  const { id, appearance, title, description } = notice;

  useEffect(() => {
    if (appearance !== "success") return;
    const timer = window.setTimeout(() => onDismiss(id), SUCCESS_DISMISS_MS);
    return () => window.clearTimeout(timer);
  }, [appearance, id, onDismiss]);

  return (
    <Box role={appearance === "error" ? "alert" : "status"} testId={`notice-${appearance}`}>
      <SectionMessage
        appearance={appearance}
        title={title}
        isDismissible
        onDismiss={() => onDismiss(id)}
      >
        {description ?? null}
      </SectionMessage>
    </Box>
  );
}
