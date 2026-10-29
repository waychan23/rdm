import type { ReactNode } from "react";

import { Box, Stack, Text } from "@atlaskit/primitives/compiled";

interface Props {
  label: ReactNode;
  htmlFor?: string;
  hint?: ReactNode;
  children: ReactNode;
  testId?: string;
}

/**
 * ADS form rhythm: 12px medium label, 4px gap to the control, optional 12px
 * helper text below. Kept as a thin wrapper (rather than @atlaskit/form) so
 * dialogs stay controlled by local state.
 */
export default function FormField({ label, htmlFor, hint, children, testId }: Props) {
  return (
    <Stack space="space.050" testId={testId}>
      <Box as="label" htmlFor={htmlFor}>
        <Text size="small" weight="medium" color="color.text.subtle">
          {label}
        </Text>
      </Box>
      {children}
      {hint ? (
        <Text size="small" color="color.text.subtlest">
          {hint}
        </Text>
      ) : null}
    </Stack>
  );
}
