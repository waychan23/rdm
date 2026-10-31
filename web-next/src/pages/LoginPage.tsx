import { useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import Checkbox from "@atlaskit/checkbox";
import Heading from "@atlaskit/heading";
import Spinner from "@atlaskit/spinner";
import Textfield from "@atlaskit/textfield";
import { Box, Stack, Text } from "@atlaskit/primitives/compiled";

import { cardBorder } from "../components/cardBorder";
import FormField from "../components/FormField";
import { errorCause } from "../lib/api";
import { submitLogin } from "../lib/auth";
import { useNotify } from "../lib/flags";
import { beginLogin, getAccessToken, safePostLoginPath } from "../lib/oauth";

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
    width: "360px",
    maxWidth: "100%",
    padding: "var(--ds-space-300)",
    backgroundColor: "var(--ds-surface)",
    borderRadius: "var(--ds-radius-small)",
    boxShadow: "var(--ds-shadow-raised)",
  },
});

export default function LoginPage() {
  const { t } = useTranslation("auth");
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const notify = useNotify();
  const authKey = params.get("auth_key");
  const redirectTarget = safePostLoginPath(params.get("redirect"));
  // React StrictMode mounts effects twice in dev; one full-page redirect is enough.
  const startedRef = useRef(false);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [loading, setLoading] = useState(false);

  // Direct visits (bookmarks, a 401 bounce) start a fresh authorization
  // request instead of pretending to be a login form without context.
  useEffect(() => {
    if (authKey) return;
    // Already authenticated (e.g. a bookmark or a stale /login link): do not
    // restart the OAuth flow, just continue to the app.
    if (getAccessToken()) {
      navigate(redirectTarget, { replace: true });
      return;
    }
    if (startedRef.current) return;
    startedRef.current = true;
    void beginLogin(redirectTarget);
  }, [authKey, redirectTarget, navigate]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (loading || !authKey) return;
    setLoading(true);
    try {
      const result = await submitLogin(authKey, name.trim(), password, remember);
      if (result.must_reset && result.set_password_url) {
        window.location.assign(result.set_password_url);
        return;
      }
      if (result.redirect_to) {
        window.location.assign(result.redirect_to);
        return;
      }
      await beginLogin("/projects");
    } catch (e) {
      notify.error(t("login.failed"), errorCause(e)?.message);
    } finally {
      setLoading(false);
    }
  };

  if (!authKey) {
    return (
      <Box xcss={styles.wrap} testId="login-redirecting">
        <Stack space="space.200" alignInline="center">
          <Spinner size="large" />
          <Text color="color.text.subtlest">{t("login.redirecting")}</Text>
        </Stack>
      </Box>
    );
  }

  return (
    <Box xcss={styles.wrap} testId="page-login">
      <Box xcss={styles.card} style={cardBorder}>
        <Box as="form" onSubmit={submit} testId="login-form">
          <Stack space="space.200">
            <Heading size="large" as="h1">{t("login.title")}</Heading>
            <FormField label={t("login.username")} htmlFor="login-name">
              <Textfield
                id="login-name"
                value={name}
                placeholder={t("login.usernamePlaceholder")}
                autoComplete="username"
                autoFocus
                testId="login-username"
                onChange={(e) => setName(e.currentTarget.value)}
              />
            </FormField>
            <FormField label={t("login.password")} htmlFor="login-password">
              <Textfield
                id="login-password"
                type="password"
                value={password}
                autoComplete="current-password"
                testId="login-password"
                onChange={(e) => setPassword(e.currentTarget.value)}
              />
            </FormField>
            <Checkbox
              label={t("login.remember")}
              isChecked={remember}
              testId="login-remember"
              onChange={(e) => setRemember(e.currentTarget.checked)}
            />
            <Button
              type="submit"
              appearance="primary"
              isLoading={loading}
              testId="login-submit"
            >
              {t("login.submit")}
            </Button>
            <Text size="small" color="color.text.subtlest">
              {t("login.bootstrapHint")}
            </Text>
          </Stack>
        </Box>
      </Box>
    </Box>
  );
}
