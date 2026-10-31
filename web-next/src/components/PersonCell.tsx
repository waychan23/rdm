import Avatar from "@atlaskit/avatar";
import { Inline, Text } from "@atlaskit/primitives/compiled";
import { useTranslation } from "react-i18next";

export default function PersonCell({ name }: { name?: string | null }) {
  const { t } = useTranslation("common");
  const unassigned = t("state.unassigned");
  return (
    <Inline
      space="space.100"
      alignBlock="center"
      testId={name ? "person-cell" : "person-cell-unassigned"}
    >
      <Avatar
        appearance="circle"
        size="small"
        name={name ?? unassigned}
        src={undefined}
      />
      <Text size="small" color={name ? "color.text.subtle" : "color.text.subtlest"}>
        {name || unassigned}
      </Text>
    </Inline>
  );
}
