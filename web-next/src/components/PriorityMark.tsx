import { token } from "@atlaskit/tokens";
import { Inline, Text } from "@atlaskit/primitives";

export default function PriorityMark({ priority }: { priority: number | null | undefined }) {
  const unset = priority == null;
  return (
    <Inline space="space.100" alignBlock="center" testId="priority-mark">
      <span
        style={{
          width: token("space.100"),
          height: token("space.100"),
          borderRadius: token("radius.full"),
          backgroundColor: unset
            ? token("color.icon.disabled")
            : token("color.icon.warning"),
          display: "inline-block",
        }}
      />
      <Text size="small" color={unset ? "color.text.subtlest" : "color.text"}>
        {unset ? "未设置" : priority}
      </Text>
    </Inline>
  );
}
