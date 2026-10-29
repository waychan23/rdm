import { useEffect, useState } from "react";
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
      setError("missing_code");
      return;
    }
    void (async () => {
      const ok = await completeLogin(code, state);
      if (!ok) {
        setError("invalid_callback");
        return;
      }
      await reloadSession();
      navigate(takePostLoginPath(), { replace: true });
    })();
  }, [params, navigate]);

  return (
    <Box xcss={styles.wrap} testId="page-auth-callback">
      <Stack space="space.200" alignInline="center">
        {error ? (
          <Stack space="space.150" alignInline="center">
            <Heading size="large" as="h1">登录未完成</Heading>
            <Text>{error}</Text>
            <Button
              appearance="primary"
              testId="auth-callback-retry"
              onClick={() => void beginLogin("/projects")}
            >
              重新登录
            </Button>
          </Stack>
        ) : (
          <>
            <Spinner size="large" />
            <Text color="color.text.subtlest">正在完成登录…</Text>
          </>
        )}
      </Stack>
    </Box>
  );
}
