import { useCallback, useEffect, useState, type FormEvent } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import SectionMessage from "@atlaskit/section-message";
import Spinner from "@atlaskit/spinner";
import Textfield from "@atlaskit/textfield";
import { Box, Stack, Text } from "@atlaskit/primitives/compiled";

import { checkPasswordTicket, setPasswordWithTicket } from "../api/auth-api";
import { cardBorder } from "../components/cardBorder";
import FormField from "../components/FormField";
import { errorCause } from "../lib/api";
import { useNotify } from "../lib/flags";

const styles = cssMap({
  wrap: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "var(--ds-space-300)",
    backgroundColor: "var(--ds-surface-sunken)",
  },
  card: {
    width: "380px",
    maxWidth: "100%",
    padding: "var(--ds-space-300)",
    backgroundColor: "var(--ds-surface)",
    borderRadius: "var(--ds-radius-small)",
    boxShadow: "var(--ds-shadow-raised)",
  },
});

type TicketState =
  | { phase: "checking" }
  | { phase: "valid" }
  | { phase: "invalid"; reason: string; kind: string | null }
  | { phase: "error" };

function invalidMessage(
  t: TFunction<"auth">,
  reason: string,
  kind: string | null,
): { title: string; body: string } {
  const nextStep =
    kind === "bootstrap"
      ? t("setPassword.invalid.nextStep.bootstrap")
      : t("setPassword.invalid.nextStep.fallback");
  switch (reason) {
    case "consumed":
      return {
        title: t("setPassword.invalid.consumed.title"),
        body: `${t("setPassword.invalid.consumed.body")}${nextStep}`,
      };
    case "expired":
      return {
        title: t("setPassword.invalid.expired.title"),
        body: `${t("setPassword.invalid.expired.body")}${nextStep}`,
      };
    case "user_missing":
      return {
        title: t("setPassword.invalid.userMissing.title"),
        body: `${t("setPassword.invalid.userMissing.body")}${nextStep}`,
      };
    default:
      return {
        title: t("setPassword.invalid.notFound.title"),
        body: `${t("setPassword.invalid.notFound.body")}${nextStep}`,
      };
  }
}

export default function SetPasswordPage() {
  const { t } = useTranslation("auth");
  const [params] = useSearchParams();
  const notify = useNotify();
  const ticket = params.get("ticket");
  const authKey = params.get("auth_key");
  const [status, setStatus] = useState<TicketState>({ phase: "checking" });
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const checkTicket = useCallback(async () => {
    if (!ticket) return;
    setStatus({ phase: "checking" });
    try {
      const data = await checkPasswordTicket(ticket);
      setStatus(
        data.valid
          ? { phase: "valid" }
          : { phase: "invalid", reason: data.reason ?? "not_found", kind: data.kind },
      );
    } catch {
      setStatus({ phase: "error" });
    }
  }, [ticket]);

  // Evaluate the link before rendering the form: an expired or reused ticket
  // must not accept a password that can only fail on submit.
  useEffect(() => {
    void checkTicket();
  }, [checkTicket]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ticket || loading) return;
    if (password !== confirm) {
      notify.error(t("setPassword.errors.mismatch"));
      return;
    }
    setLoading(true);
    try {
      await setPasswordWithTicket(ticket, password);
      setDone(true);
    } catch (e) {
      notify.error(t("setPassword.errors.failed"), errorCause(e)?.message);
    } finally {
      setLoading(false);
    }
  };

  const renderBody = () => {
    if (!ticket) {
      return (
        <SectionMessage appearance="error" title={t("setPassword.missingTicket.title")}>
          {t("setPassword.missingTicket.body")}
        </SectionMessage>
      );
    }
    if (status.phase === "checking") {
      return (
        <Stack space="space.200" alignInline="center">
          <Spinner size="large" />
          <Text color="color.text.subtlest">{t("setPassword.checking")}</Text>
        </Stack>
      );
    }
    if (status.phase === "error") {
      return (
        <Stack space="space.200">
          <SectionMessage appearance="warning" title={t("setPassword.checkFailed.title")}>
            {t("setPassword.checkFailed.body")}
          </SectionMessage>
          <Button testId="set-password-recheck" onClick={() => void checkTicket()}>
            {t("setPassword.retry")}
          </Button>
        </Stack>
      );
    }
    if (status.phase === "invalid") {
      const message = invalidMessage(t, status.reason, status.kind);
      return (
        <SectionMessage appearance="error" title={message.title}>
          {message.body}
        </SectionMessage>
      );
    }
    if (done) {
      return (
        <Stack space="space.200">
          <Heading size="large" as="h1">{t("setPassword.done.title")}</Heading>
          <SectionMessage appearance="success" title={t("setPassword.done.successTitle")}>
            {t("setPassword.done.successBody")}
          </SectionMessage>
          <Button
            appearance="primary"
            testId="set-password-goto-login"
            onClick={() => {
              window.location.assign(
                authKey ? `/login?auth_key=${encodeURIComponent(authKey)}` : "/login",
              );
            }}
          >
            {t("setPassword.done.gotoLogin")}
          </Button>
        </Stack>
      );
    }
    return (
      <Box as="form" onSubmit={submit} testId="set-password-form">
        <Stack space="space.200">
          <Heading size="large" as="h1">{t("setPassword.form.title")}</Heading>
          <Text color="color.text.subtlest">{t("setPassword.form.hint")}</Text>
          <FormField label={t("setPassword.form.newPassword")} htmlFor="set-password">
            <Textfield
              id="set-password"
              type="password"
              autoComplete="new-password"
              value={password}
              autoFocus
              testId="set-password-new"
              onChange={(e) => setPassword(e.currentTarget.value)}
            />
          </FormField>
          <FormField label={t("setPassword.form.confirmPassword")} htmlFor="set-password-confirm">
            <Textfield
              id="set-password-confirm"
              type="password"
              autoComplete="new-password"
              value={confirm}
              testId="set-password-confirm"
              onChange={(e) => setConfirm(e.currentTarget.value)}
            />
          </FormField>
          <Button
            type="submit"
            appearance="primary"
            isLoading={loading}
            testId="set-password-submit"
          >
            {t("setPassword.form.submit")}
          </Button>
        </Stack>
      </Box>
    );
  };

  return (
    <Box xcss={styles.wrap} testId="page-set-password">
      <Box xcss={styles.card} style={cardBorder}>
        {renderBody()}
      </Box>
    </Box>
  );
}
