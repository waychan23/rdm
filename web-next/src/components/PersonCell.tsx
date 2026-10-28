import Avatar from "@atlaskit/avatar";
import { Inline, Text } from "@atlaskit/primitives";

export default function PersonCell({ name }: { name?: string | null }) {
  return (
    <Inline space="space.100" alignBlock="center">
      <Avatar
        appearance="circle"
        size="small"
        name={name ?? "未指派"}
        src={undefined}
      />
      <Text size="small" color={name ? "color.text.subtle" : "color.text.subtlest"}>
        {name || "未指派"}
      </Text>
    </Inline>
  );
}
