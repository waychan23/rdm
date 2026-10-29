import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import SectionMessage from "@atlaskit/section-message";
import Textfield from "@atlaskit/textfield";
import { Box, Stack, Text, xcss } from "@atlaskit/primitives";

import { api, errorCause } from "../lib/api";
import { useNotify } from "../lib/flags";

const wrapStyles = xcss({
  minHeight: "100vh",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  backgroundColor: "color.background.neutral.subtle",
});

const cardStyles = xcss({
  width: "380px",
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

export default function SetPasswordPage() {
  const [params] = useSearchParams();
  const notify = useNotify();
  const ticket = params.get("ticket");
  const authKey = params.get("auth_key");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ticket || loading) return;
    if (password !== confirm) {
      notify.error("两次输入的密码不一致");
      return;
    }
    setLoading(true);
    try {
      await api.post("/auth/set-password", { ticket, new_password: password });
      setDone(true);
    } catch (e) {
      notify.error("设置密码失败", errorCause(e)?.message);
    } finally {
      setLoading(false);
    }
  };

  if (!ticket) {
    return (
      <Box xcss={wrapStyles}>
        <Box xcss={cardStyles}>
          <SectionMessage appearance="error" title="链接无效">
            缺少 ticket 参数，请向管理员重新索取设置密码链接。
          </SectionMessage>
        </Box>
      </Box>
    );
  }

  return (
    <Box xcss={wrapStyles}>
      <Box xcss={cardStyles}>
        {done ? (
          <Stack space="space.200">
            <Heading size="large">密码已设置</Heading>
            <SectionMessage appearance="success" title="完成">
              现在用新密码登录。
            </SectionMessage>
            <Button
              appearance="primary"
              onClick={() => {
                window.location.assign(
                  authKey ? `/login?auth_key=${encodeURIComponent(authKey)}` : "/login",
                );
              }}
            >
              去登录
            </Button>
          </Stack>
        ) : (
          <Box as="form" onSubmit={submit}>
            <Stack space="space.200">
              <Heading size="large">设置密码</Heading>
              <Text color="color.text.subtlest">密码长度 8–128 位，请妥善保管。</Text>
              <Stack space="space.050">
                <Box as="label" xcss={labelStyles} htmlFor="set-password">
                  新密码
                </Box>
                <Textfield
                  id="set-password"
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  autoFocus
                  onChange={(e) => setPassword(e.currentTarget.value)}
                />
              </Stack>
              <Stack space="space.050">
                <Box as="label" xcss={labelStyles} htmlFor="set-password-confirm">
                  确认新密码
                </Box>
                <Textfield
                  id="set-password-confirm"
                  type="password"
                  autoComplete="new-password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.currentTarget.value)}
                />
              </Stack>
              <Button type="submit" appearance="primary" isLoading={loading}>
                保存
              </Button>
            </Stack>
          </Box>
        )}
      </Box>
    </Box>
  );
}
