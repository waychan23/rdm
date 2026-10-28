import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
import Textfield from "@atlaskit/textfield";
import Heading from "@atlaskit/heading";
import { Box, Inline, Stack, Text, xcss } from "@atlaskit/primitives";

import { errorCause } from "../lib/api";
import { login, rememberedProjectKey, rememberProjectKey } from "../lib/auth";
import { useNotify } from "../lib/flags";

// Server-side (non-SPA) paths the OAuth flow may ask us to return to after
// login: /authorize must be re-requested as a full page (with the new session
// cookie) so the authorization server can continue and redirect to consent.
const SERVER_PATHS = new Set(["/authorize", "/token", "/register", "/revoke"]);

function isSafeInternalPath(target: unknown): target is string {
  return (
    typeof target === "string" &&
    target.startsWith("/") &&
    !target.startsWith("//") &&
    !target.startsWith("/\\")
  );
}

function isServerPath(target: string): boolean {
  const path = target.split("?")[0].split("#")[0];
  return SERVER_PATHS.has(path) || path.startsWith("/.well-known/");
}

const wrapStyles = xcss({
  minHeight: "100vh",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  backgroundColor: "color.background.neutral.subtle",
});

const cardStyles = xcss({
  width: "360px",
  padding: "space.300",
  backgroundColor: "elevation.surface",
  border: "1px solid",
  borderColor: "color.border",
  borderRadius: "radius.small",
});

const labelStyles = xcss({
  fontWeight: "font.weight.medium",
  marginBlockEnd: "space.050",
});

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const notify = useNotify();
  const [projectKey, setProjectKey] = useState(rememberedProjectKey());
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    try {
      const key = projectKey.trim() || "RDM";
      rememberProjectKey(key);
      await login(key, name.trim(), password);
      // OAuth provider redirects to /login?next=/authorize?...; the router
      // guard uses ?redirect= for SPA pages. Honor both.
      const params = new URLSearchParams(location.search);
      const target = params.get("next") ?? params.get("redirect");
      if (isSafeInternalPath(target)) {
        if (isServerPath(target)) {
          window.location.assign(target);
          return;
        }
        navigate(target);
      } else {
        navigate("/projects");
      }
    } catch (e) {
      notify.error("登录失败", errorCause(e)?.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box xcss={wrapStyles}>
      <Box xcss={cardStyles}>
        <Box as="form" onSubmit={submit}>
          <Stack space="space.200">
            <Heading size="large">rd-manager 登录</Heading>
          <Stack space="space.050">
            <Box as="label" xcss={labelStyles} htmlFor="login-project">
              项目 Key
            </Box>
            <Textfield
              id="login-project"
              value={projectKey}
              placeholder="RDM"
              autoComplete="organization"
              onChange={(e) => setProjectKey(e.currentTarget.value)}
            />
          </Stack>
          <Stack space="space.050">
            <Box as="label" xcss={labelStyles} htmlFor="login-name">
              用户名
            </Box>
            <Textfield
              id="login-name"
              value={name}
              placeholder="owner"
              autoComplete="username"
              onChange={(e) => setName(e.currentTarget.value)}
            />
          </Stack>
          <Stack space="space.050">
            <Box as="label" xcss={labelStyles} htmlFor="login-password">
              密码
            </Box>
            <Textfield
              id="login-password"
              type="password"
              value={password}
              autoComplete="current-password"
              onChange={(e) => setPassword(e.currentTarget.value)}
            />
          </Stack>
          <Button type="submit" appearance="primary" isLoading={loading}>
            登录
          </Button>
            <Text size="small" color="color.text.subtlest">
              初始 owner 密码见 data-dir 下的 bootstrap-password（首次启动生成，0600）。
            </Text>
          </Stack>
        </Box>
      </Box>
    </Box>
  );
}
