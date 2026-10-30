import Button from "@atlaskit/button/default/button";
import SectionMessage from "@atlaskit/section-message";
import { Box, Inline } from "@atlaskit/primitives/compiled";

import { errorCause } from "../lib/api";

interface Props {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  testId?: string;
}

/** Shared load-failure surface: message from the API envelope + a retry. */
export default function ErrorState({
  error,
  onRetry,
  title = "加载失败",
  testId = "error-state",
}: Props) {
  const cause = errorCause(error);
  return (
    <Box padding="space.400" testId={testId}>
      <SectionMessage
        appearance="error"
        title={title}
        actions={
          onRetry ? (
            <Inline>
              <Button appearance="subtle" onClick={onRetry}>
                重试
              </Button>
            </Inline>
          ) : undefined
        }
      >
        {cause?.message ?? (error instanceof Error ? error.message : "请求失败，请重试。")}
      </SectionMessage>
    </Box>
  );
}
