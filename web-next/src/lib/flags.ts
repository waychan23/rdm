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
      error: (title, description) => {
        // Non-normal appearances hide Atlaskit's built-in dismiss button, and
        // error flags are persistent. Add an explicit close action.
        let dismiss: () => void = () => {};
        dismiss = flags.showFlag({
          appearance: "error",
          title,
          description,
          actions: [{ content: "关闭", onClick: () => dismiss() }],
        });
      },
    }),
    [flags],
  );
}
