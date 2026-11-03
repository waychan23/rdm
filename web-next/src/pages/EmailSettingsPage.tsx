import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import Checkbox from "@atlaskit/checkbox";
import Heading from "@atlaskit/heading";
import SectionMessage from "@atlaskit/section-message";
import Select from "@atlaskit/select";
import Spinner from "@atlaskit/spinner";
import Textfield from "@atlaskit/textfield";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";

import ErrorState from "../components/ErrorState";
import FormField from "../components/FormField";
import { Page, PageHeader } from "../components/Page";
import { useAsync } from "../hooks/useAsync";
import { api, errorCause } from "../lib/api";
import { useCurrentUser } from "../lib/auth";
import { useNotify } from "../lib/flags";
import type { EmailSecurity, EmailSettings } from "../types";

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

interface FormState {
  enabled: boolean;
  smtpHost: string;
  smtpPort: string;
  smtpSecurity: EmailSecurity;
  smtpUsername: string;
  fromAddress: string;
  fromName: string;
  password: string;
  clearPassword: boolean;
}

const EMPTY_FORM: FormState = {
  enabled: false,
  smtpHost: "",
  smtpPort: "587",
  smtpSecurity: "starttls",
  smtpUsername: "",
  fromAddress: "",
  fromName: "",
  password: "",
  clearPassword: false,
};

function fromSettings(settings: EmailSettings): FormState {
  return {
    enabled: settings.enabled,
    smtpHost: settings.smtp_host ?? "",
    smtpPort: String(settings.smtp_port),
    smtpSecurity: settings.smtp_security,
    smtpUsername: settings.smtp_username ?? "",
    fromAddress: settings.from_address ?? "",
    fromName: settings.from_name ?? "",
    password: "",
    clearPassword: false,
  };
}

export default function EmailSettingsPage() {
  const { t } = useTranslation("emailSettings");
  const notify = useNotify();
  const me = useCurrentUser();
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [testTo, setTestTo] = useState("");
  const [testing, setTesting] = useState(false);

  const { data, loading, error, reload } = useAsync(
    async () => (await api.get<EmailSettings>("/email-settings")).data,
    [],
  );

  useEffect(() => {
    if (data) setForm(fromSettings(data));
  }, [data]);

  useEffect(() => {
    if (!testTo && me?.user.email) setTestTo(me.user.email);
  }, [me?.user.email, testTo]);

  const patch = (values: Partial<FormState>) => setForm((prev) => ({ ...prev, ...values }));

  const save = async () => {
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        enabled: form.enabled,
        smtp_host: form.smtpHost.trim() || null,
        smtp_port: Number(form.smtpPort),
        smtp_security: form.smtpSecurity,
        smtp_username: form.smtpUsername.trim() || null,
        from_address: form.fromAddress.trim() || null,
        from_name: form.fromName.trim() || null,
      };
      if (form.clearPassword) payload.password = "";
      else if (form.password) payload.password = form.password;
      await api.patch("/email-settings", payload);
      notify.success(t("notify.saved"));
      reload();
    } catch (e) {
      notify.error(t("notify.saveFailed"), errorCause(e)?.message);
    } finally {
      setSaving(false);
    }
  };

  const sendTest = async () => {
    setTesting(true);
    try {
      const res = await api.post<{ sent: boolean; to: string }>("/email-settings/test", {
        to: testTo.trim() || null,
      });
      notify.success(t("notify.testSent", { to: res.data.to }));
    } catch (e) {
      notify.error(t("notify.testFailed"), errorCause(e)?.message);
    } finally {
      setTesting(false);
    }
  };

  const securityOptions = [
    { label: t("security.none"), value: "none" },
    { label: t("security.starttls"), value: "starttls" },
    { label: t("security.ssl"), value: "ssl" },
  ];

  return (
    <Page testId="page-email-settings">
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        testId="email-settings-header"
        actions={
          data ? (
            <Button
              appearance="primary"
              isLoading={saving}
              testId="email-settings-save"
              onClick={() => void save()}
            >
              {saving ? t("actions.saving") : t("actions.save")}
            </Button>
          ) : undefined
        }
      />

      {error ? (
        <ErrorState error={error} onRetry={reload} testId="email-settings-error" />
      ) : loading || !data ? (
        <Box xcss={styles.loading} testId="email-settings-loading">
          <Spinner size="large" />
        </Box>
      ) : (
        <Stack space="space.300" xcss={styles.section}>
          <SectionMessage appearance="information">{t("hint")}</SectionMessage>

          <Stack space="space.150">
            <Heading size="small">{t("sections.server")}</Heading>
            <Checkbox
              label={t("fields.enabled")}
              isChecked={form.enabled}
              testId="email-settings-enabled"
              onChange={(event) => patch({ enabled: event.currentTarget.checked })}
            />
            <FormField label={t("fields.smtpHost")} htmlFor="email-smtp-host">
              <Textfield
                id="email-smtp-host"
                value={form.smtpHost}
                testId="email-settings-host"
                onChange={(event) => patch({ smtpHost: event.currentTarget.value })}
              />
            </FormField>
            <Inline space="space.150" alignBlock="end">
              <FormField label={t("fields.smtpPort")} htmlFor="email-smtp-port">
                <Textfield
                  id="email-smtp-port"
                  type="number"
                  width="small"
                  value={form.smtpPort}
                  testId="email-settings-port"
                  onChange={(event) => patch({ smtpPort: event.currentTarget.value })}
                />
              </FormField>
              <FormField label={t("fields.security")} htmlFor="email-smtp-security">
                <Select
                  inputId="email-smtp-security"
                  options={securityOptions}
                  value={
                    securityOptions.find((option) => option.value === form.smtpSecurity) ??
                    securityOptions[1]
                  }
                  onChange={(option) =>
                    patch({
                      smtpSecurity: (option?.value ?? "starttls") as EmailSecurity,
                    })
                  }
                  spacing="compact"
                  testId="email-settings-security"
                />
              </FormField>
            </Inline>
            <FormField label={t("fields.username")} htmlFor="email-smtp-username">
              <Textfield
                id="email-smtp-username"
                value={form.smtpUsername}
                testId="email-settings-username"
                onChange={(event) => patch({ smtpUsername: event.currentTarget.value })}
              />
            </FormField>
            <FormField
              label={t("fields.password")}
              htmlFor="email-smtp-password"
              hint={data.has_password ? t("password.saved") : t("password.empty")}
            >
              <Textfield
                id="email-smtp-password"
                type="password"
                value={form.password}
                isDisabled={form.clearPassword}
                placeholder={data.has_password ? "" : t("password.set")}
                testId="email-settings-password"
                onChange={(event) => patch({ password: event.currentTarget.value })}
              />
            </FormField>
            {data.has_password ? (
              <Checkbox
                label={t("password.clear")}
                isChecked={form.clearPassword}
                testId="email-settings-clear-password"
                onChange={(event) =>
                  patch({
                    clearPassword: event.currentTarget.checked,
                    password: event.currentTarget.checked ? "" : form.password,
                  })
                }
              />
            ) : null}
          </Stack>

          <Stack space="space.150">
            <Heading size="small">{t("sections.sender")}</Heading>
            <FormField label={t("fields.fromAddress")} htmlFor="email-from-address">
              <Textfield
                id="email-from-address"
                value={form.fromAddress}
                testId="email-settings-from-address"
                onChange={(event) => patch({ fromAddress: event.currentTarget.value })}
              />
            </FormField>
            <FormField label={t("fields.fromName")} htmlFor="email-from-name">
              <Textfield
                id="email-from-name"
                value={form.fromName}
                testId="email-settings-from-name"
                onChange={(event) => patch({ fromName: event.currentTarget.value })}
              />
            </FormField>
          </Stack>

          <Stack space="space.150">
            <Heading size="small">{t("sections.test")}</Heading>
            <Inline space="space.100" alignBlock="end">
              <FormField label={t("fields.testTo")} htmlFor="email-test-to">
                <Textfield
                  id="email-test-to"
                  value={testTo}
                  testId="email-settings-test-to"
                  onChange={(event) => setTestTo(event.currentTarget.value)}
                />
              </FormField>
              <Button
                isLoading={testing}
                testId="email-settings-test"
                onClick={() => void sendTest()}
              >
                {testing ? t("actions.testing") : t("actions.test")}
              </Button>
            </Inline>
            <Text size="small" color="color.text.subtlest">
              {t("hint")}
            </Text>
          </Stack>
        </Stack>
      )}
    </Page>
  );
}
