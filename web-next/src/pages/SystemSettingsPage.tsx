import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import SectionMessage from "@atlaskit/section-message";
import Spinner from "@atlaskit/spinner";
import Textfield from "@atlaskit/textfield";
import { Box, Stack, Text } from "@atlaskit/primitives/compiled";

import ErrorState from "../components/ErrorState";
import FormField from "../components/FormField";
import { Page, PageHeader } from "../components/Page";
import { useAsync } from "../hooks/useAsync";
import { getOrgSettings, updateOrgSettings } from "../api/system-api";
import { errorCause } from "../lib/api";
import { useNotify } from "../lib/flags";

const styles = cssMap({
  loading: {
    display: "flex",
    justifyContent: "center",
    padding: "var(--ds-space-400)",
  },
  section: {
    maxWidth: "640px",
  },
});

export default function SystemSettingsPage() {
  const { t } = useTranslation("systemSettings");
  const notify = useNotify();
  const [webOrigin, setWebOrigin] = useState("");
  const [saving, setSaving] = useState(false);

  const { data, loading, error, reload } = useAsync(getOrgSettings, []);

  useEffect(() => {
    if (data) setWebOrigin(data.web_origin ?? "");
  }, [data]);

  const save = async () => {
    setSaving(true);
    try {
      await updateOrgSettings(webOrigin.trim() || null);
      notify.success(t("notify.saved"));
      reload();
    } catch (e) {
      notify.error(t("notify.saveFailed"), errorCause(e)?.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Page testId="page-system-settings">
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        testId="system-settings-header"
        actions={
          data ? (
            <Button
              appearance="primary"
              isLoading={saving}
              testId="system-settings-save"
              onClick={() => void save()}
            >
              {saving ? t("actions.saving") : t("actions.save")}
            </Button>
          ) : undefined
        }
      />

      {error ? (
        <ErrorState error={error} onRetry={reload} testId="system-settings-error" />
      ) : loading || !data ? (
        <Box xcss={styles.loading} testId="system-settings-loading">
          <Spinner size="large" />
        </Box>
      ) : (
        <Stack space="space.300" xcss={styles.section}>
          <SectionMessage appearance="information">{t("hint")}</SectionMessage>

          <Stack space="space.150">
            <Heading size="small">{t("sections.webOrigin")}</Heading>
            <FormField
              label={t("fields.webOrigin")}
              htmlFor="system-web-origin"
              hint={t("fields.webOriginHint")}
            >
              <Textfield
                id="system-web-origin"
                value={webOrigin}
                testId="system-settings-web-origin"
                placeholder={t("fields.webOriginPlaceholder")}
                onChange={(event) => setWebOrigin(event.currentTarget.value)}
              />
            </FormField>
            <Box>
              <Button
                appearance="subtle"
                testId="system-settings-use-current-origin"
                onClick={() => setWebOrigin(window.location.origin)}
              >
                {t("actions.useCurrentOrigin")}
              </Button>
            </Box>
            <Text size="small" color="color.text.subtlest">
              {t("fields.fallback", { origin: data.default_web_origin })}
            </Text>
          </Stack>
        </Stack>
      )}
    </Page>
  );
}
