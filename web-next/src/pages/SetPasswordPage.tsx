import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import SectionMessage from "@atlaskit/section-message";
import Textfield from "@atlaskit/textfield";
import { Box, Stack, Text } from "@atlaskit/primitives/compiled";

import { cardBorder } from "../components/cardBorder";
import FormField from "../components/FormField";
import { api, errorCause } from "../lib/api";
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
      <Box xcss={styles.wrap} testId="page-set-password">
        <Box xcss={styles.card} style={cardBorder}>
          <SectionMessage appearance="error" title="链接无效">
            缺少 ticket 参数，请向管理员重新索取设置密码链接。
          </SectionMessage>
        </Box>
      </Box>
    );
  }

  return (
    <Box xcss={styles.wrap} testId="page-set-password">
      <Box xcss={styles.card} style={cardBorder}>
        {done ? (
          <Stack space="space.200">
            <Heading size="large" as="h1">密码已设置</Heading>
            <SectionMessage appearance="success" title="完成">
              现在用新密码登录。
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
              去登录
            </Button>
          </Stack>
        ) : (
          <Box as="form" onSubmit={submit} testId="set-password-form">
            <Stack space="space.200">
              <Heading size="large" as="h1">设置密码</Heading>
              <Text color="color.text.subtlest">密码长度 8–128 位，请妥善保管。</Text>
              <FormField label="新密码" htmlFor="set-password">
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
              <FormField label="确认新密码" htmlFor="set-password-confirm">
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
                保存
              </Button>
            </Stack>
          </Box>
        )}
      </Box>
    </Box>
  );
}
