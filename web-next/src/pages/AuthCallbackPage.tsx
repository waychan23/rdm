import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import Spinner from "@atlaskit/spinner";
import { Box, Stack, Text } from "@atlaskit/primitives/compiled";

import { reloadSession } from "../lib/auth";
import { beginLogin, completeLogin, takePostLoginPath } from "../lib/oauth";

const styles = cssMap({
  wrap: {
    minHeight: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "var(--ds-surface-sunken)",
  },
});

export default function AuthCallbackPage() {
  const { t } = useTranslation("auth");
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = params.get("code");
    const state = params.get("state");
    const oauthError = params.get("error");
    if (oauthError) {
      setError(oauthError);
      return;
    }
    if (!code || !state) {
      setError(t("callback.errors.missingCode"));
      return;
    }
    void (async () => {
      const ok = await completeLogin(code, state);
      if (!ok) {
        setError(t("callback.errors.invalidCallback"));
        return;
      }
      await reloadSession();
      navigate(takePostLoginPath(), { replace: true });
    })();
  }, [params, navigate, t]);

  return (
    <Box xcss={styles.wrap} testId="page-auth-callback">
      <Stack space="space.200" alignInline="center">
        {error ? (
          <Stack space="space.150" alignInline="center">
            <Heading size="large" as="h1">{t("callback.title")}</Heading>
            <Text>{error}</Text>
            <Button
              appearance="primary"
              testId="auth-callback-retry"
              onClick={() => void beginLogin("/projects")}
            >
              {t("callback.retry")}
            </Button>
          </Stack>
        ) : (
          <>
            <Spinner size="large" />
            <Text color="color.text.subtlest">{t("callback.completing")}</Text>
          </>
        )}
      </Stack>
    </Box>
  );
}
