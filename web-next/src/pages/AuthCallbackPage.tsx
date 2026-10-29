import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import Heading from "@atlaskit/heading";
import Spinner from "@atlaskit/spinner";
import { Box, Stack, Text, xcss } from "@atlaskit/primitives";

import { reloadSession } from "../lib/auth";
import { beginLogin, completeLogin, takePostLoginPath } from "../lib/oauth";

const wrapStyles = xcss({
  minHeight: "100vh",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
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
    <Box xcss={wrapStyles}>
      <Stack space="space.200" alignInline="center">
        {error ? (
          <>
            <Heading size="large">登录未完成</Heading>
            <Text>{error}</Text>
            <Text>
              <a
                href="/login"
                onClick={(e) => {
                  e.preventDefault();
                  void beginLogin("/projects");
                }}
              >
                重新登录
              </a>
            </Text>
          </>
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
