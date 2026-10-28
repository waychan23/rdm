// Thin wrappers around the Atlaskit FlagsProvider, replacing ElMessage.
import { useMemo } from "react";

import { useFlags } from "@atlaskit/flag/use-flags";

export interface Notify {
  success: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
}

export function useNotify(): Notify {
  const flags = useFlags();
  return useMemo<Notify>(
    () => ({
      success: (title, description) =>
        flags.showFlag({
          appearance: "success",
          title,
          description,
          isAutoDismiss: true,
        }),
      error: (title, description) =>
        flags.showFlag({ appearance: "error", title, description }),
    }),
    [flags],
  );
}
