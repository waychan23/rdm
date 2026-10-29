import type { ReactNode } from "react";

import Heading from "@atlaskit/heading";
import { Box, Inline, Stack, Text, xcss } from "@atlaskit/primitives";

// Shared page frame. ADS page rhythm: 24px inset, 24px between the header
// block and the page content. `fill` is for list/board pages that must keep
// their own vertical scroll area inside the shell.
const pageStyles = xcss({
  display: "flex",
  flexDirection: "column",
  gap: "space.300",
  padding: "space.300",
  minWidth: "0",
});

const fillPageStyles = xcss({
  display: "flex",
  flexDirection: "column",
  gap: "space.300",
  padding: "space.300",
  minWidth: "0",
  flex: "1",
  minHeight: "0",
  height: "100%",
});

export function Page({
  children,
  testId,
  fill = false,
}: {
  children: ReactNode;
  testId?: string;
  fill?: boolean;
}) {
  return (
    <Box xcss={fill ? fillPageStyles : pageStyles} testId={testId}>
      {children}
    </Box>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  testId,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  testId?: string;
}) {
  return (
    <Inline
      spread="space-between"
      alignBlock="center"
      space="space.200"
      shouldWrap
      testId={testId}
    >
      <Stack space="space.050">
        <Heading size="large" as="h1">
          {title}
        </Heading>
        {description ? (
          <Text size="small" color="color.text.subtlest">
            {description}
          </Text>
        ) : null}
      </Stack>
      {actions ? (
        <Inline space="space.100" alignBlock="center">
          {actions}
        </Inline>
      ) : null}
    </Inline>
  );
}
