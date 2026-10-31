import Button from "@atlaskit/button/default/button";
import SectionMessage from "@atlaskit/section-message";
import { Box, Inline } from "@atlaskit/primitives/compiled";
import { useTranslation } from "react-i18next";

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
  title,
  testId = "error-state",
}: Props) {
  const { t } = useTranslation("common");
  const cause = errorCause(error);
  return (
    <Box padding="space.400" testId={testId}>
      <SectionMessage
        appearance="error"
        title={title ?? t("error.loadFailed")}
        actions={
          onRetry ? (
            <Inline>
              <Button appearance="subtle" onClick={onRetry}>
                {t("actions.retry")}
              </Button>
            </Inline>
          ) : undefined
        }
      >
        {cause?.message ?? (error instanceof Error ? error.message : t("error.requestFailed"))}
      </SectionMessage>
    </Box>
  );
}
