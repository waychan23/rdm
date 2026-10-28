import Heading from "@atlaskit/heading";
import { Box, Stack, Text, xcss } from "@atlaskit/primitives";

// Temporary route target for pages later batches will implement.
export default function PlaceholderPage({ title }: { title: string }) {
  return (
    <Box xcss={wrapStyles} padding="space.400">
      <Stack space="space.100" alignInline="center" alignBlock="center">
        <Heading size="large">{title}</Heading>
        <Text color="color.text.subtlest">该页面将在后续批次由 React+ADS 实现。</Text>
      </Stack>
    </Box>
  );
}

const wrapStyles = xcss({
  minHeight: "60vh",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
});
