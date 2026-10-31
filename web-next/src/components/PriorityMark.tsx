import { token } from "@atlaskit/tokens";
import { Inline, Text } from "@atlaskit/primitives/compiled";
import { useTranslation } from "react-i18next";

import { priorityColor, priorityLabel } from "../workitems/priority";

export default function PriorityMark({ priority }: { priority: number | null | undefined }) {
  // Subscribe to language changes so the label re-renders.
  useTranslation("labels");
  return (
    <Inline space="space.100" alignBlock="center" testId="priority-mark">
      <span
        style={{
          width: token("space.100"),
          height: token("space.100"),
          borderRadius: token("radius.full"),
          backgroundColor: priorityColor(priority),
          display: "inline-block",
        }}
      />
      <Text size="small" color="color.text">
        {priorityLabel(priority)}
      </Text>
    </Inline>
  );
}
