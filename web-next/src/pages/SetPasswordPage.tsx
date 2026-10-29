import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import Heading from "@atlaskit/heading";
import SectionMessage from "@atlaskit/section-message";
import Spinner from "@atlaskit/spinner";
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

interface TicketStatus {
  valid: boolean;
  reason: string | null;
  kind: string | null;
  expires_at: string | null;
}

type TicketState =
  | { phase: "checking" }
  | { phase: "valid" }
  | { phase: "invalid"; reason: string; kind: string | null }
  | { phase: "error" };

const INVALID_COPY: Record<string, { title: string; body: string }> = {
  consumed: {
    title: "该链接已失效",
    body: "链接已被使用，或已因重新生成而失效。",
  },
  expired: {
    title: "该链接已过期",
    body: "设置密码链接已失效。",
  },
  user_missing: {
    title: "链接无效",
    body: "该链接对应的用户已不可用。",
  },
  not_found: {
    title: "链接无效",
    body: "链接不存在或已被替换。",
  },
};

function invalidMessage(reason: string, kind: string | null): { title: string; body: string } {
  const copy = INVALID_COPY[reason] ?? INVALID_COPY.not_found;
  const nextStep =
    kind === "bootstrap"
      ? "请查看服务启动日志中的 bootstrap-url，或由管理员执行 rdm account recover-owner 重新生成。"
      : "请向管理员重新索取设置密码链接后再试。";
  return { title: copy.title, body: `${copy.body}${nextStep}` };
}

export default function SetPasswordPage() {
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
      const { data } = await api.post<TicketStatus>("/auth/password-ticket/check", { ticket });
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

  const renderBody = () => {
    if (!ticket) {
      return (
        <SectionMessage appearance="error" title="链接无效">
          缺少 ticket 参数，请向管理员重新索取设置密码链接。
        </SectionMessage>
      );
    }
    if (status.phase === "checking") {
      return (
        <Stack space="space.200" alignInline="center">
          <Spinner size="large" />
          <Text color="color.text.subtlest">正在校验链接…</Text>
        </Stack>
      );
    }
    if (status.phase === "error") {
      return (
        <Stack space="space.200">
          <SectionMessage appearance="warning" title="无法校验链接状态">
            网络或服务异常，请稍后重试。
          </SectionMessage>
          <Button testId="set-password-recheck" onClick={() => void checkTicket()}>
            重试
          </Button>
        </Stack>
      );
    }
    if (status.phase === "invalid") {
      const message = invalidMessage(status.reason, status.kind);
      return (
        <SectionMessage appearance="error" title={message.title}>
          {message.body}
        </SectionMessage>
      );
    }
    if (done) {
      return (
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
      );
    }
    return (
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
