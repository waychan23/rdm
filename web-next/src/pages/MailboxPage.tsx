import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import Checkbox from "@atlaskit/checkbox";
import EmptyState from "@atlaskit/empty-state";
import Lozenge from "@atlaskit/lozenge";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import Select from "@atlaskit/select";
import Spinner from "@atlaskit/spinner";
import Textfield from "@atlaskit/textfield";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";
import { token } from "@atlaskit/tokens";
import { portalMenuProps } from "../lib/portalMenu";

import { cardBorder } from "../components/cardBorder";
import ErrorState from "../components/ErrorState";
import FormField from "../components/FormField";
import ImagePreviewDialog from "../components/ImagePreviewDialog";
import MarkdownEditor from "../components/MarkdownEditor";
import MarkdownText from "../components/MarkdownText";
import { Page, PageHeader } from "../components/Page";
import TextButton from "../components/TextButton";
import { api, errorCause } from "../lib/api";
import { formatDate } from "../lib/format";
import { useNotify } from "../lib/flags";
import { useCurrentUser } from "../lib/auth";
import type { MailMessage, Mailbox, OrgUser, ProjectMemberRow } from "../types";
import { flattenMembers } from "../lib/members";

const styles = cssMap({
  card: {
    borderRadius: "var(--ds-radius-small)",
    padding: "var(--ds-space-150)",
    backgroundColor: "var(--ds-surface)",
  },
  centered: {
    display: "flex",
    justifyContent: "center",
    padding: "var(--ds-space-400)",
  },
});

interface Option {
  label: string;
  value: string;
}

export default function MailboxPage() {
  const { key: projectKey = "" } = useParams();
  const location = useLocation();
  const notify = useNotify();
  const me = useCurrentUser();

  const [messages, setMessages] = useState<MailMessage[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [unreadOnly, setUnreadOnly] = useState(true);
  const [identity, setIdentity] = useState<string | null>(null);
  const [agents, setAgents] = useState<OrgUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [members, setMembers] = useState<OrgUser[]>([]);
  const [showCompose, setShowCompose] = useState(false);
  const [sending, setSending] = useState(false);
  const [preview, setPreview] = useState<{ src: string; alt: string } | null>(null);
  const [compose, setCompose] = useState<{
    to: Option[];
    subject: string;
    body: string;
    replyTo: string | null;
    refs: string[];
  }>({ to: [], subject: "", body: "", replyTo: null, refs: [] });

  const fetchPage = useCallback(
    async (cursor: string | null, replace: boolean, onlyUnread: boolean) => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({
          limit: "20",
          unread_only: String(onlyUnread),
          include_agents: "true",
        });
        if (identity) params.set("identity", identity);
        if (cursor) params.set("since", cursor);
        const box = (await api.get<Mailbox>(`/projects/${projectKey}/mailbox?${params}`)).data;
        setMessages((prev) => (replace ? box.messages : [...prev, ...box.messages]));
        setNextCursor(box.next_cursor);
      } catch (e) {
        setError(e);
      } finally {
        setLoading(false);
      }
    },
    [projectKey, identity],
  );

  useEffect(() => {
    setSelected(new Set());
    void fetchPage(null, true, unreadOnly);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unreadOnly, projectKey, identity]);

  useEffect(() => {
    api
      .get<ProjectMemberRow[]>(`/projects/${projectKey}/members`)
      .then((r) => setMembers(flattenMembers(r.data)))
      .catch(() => {});
  }, [projectKey]);

  useEffect(() => {
    api
      .get<OrgUser[]>("/me/agents")
      .then((r) => setAgents(r.data))
      .catch(() => {});
  }, []);

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const markRead = async (ids: string[]) => {
    try {
      await api.post("/messages/read", { delivery_ids: ids });
      const remaining = new Set(
        [...selected].filter((id) => !ids.includes(id)),
      );
      setSelected(remaining);
      await fetchPage(null, true, unreadOnly);
    } catch (e) {
      notify.error("标记失败", errorCause(e)?.message);
    }
  };

  const send = async () => {
    if (!compose.to.length || !compose.subject.trim() || !compose.body.trim()) {
      notify.error("收件人、主题、正文均必填");
      return;
    }
    setSending(true);
    try {
      await api.post(`/projects/${projectKey}/messages`, {
        to: compose.to.map((o) => o.value),
        subject: compose.subject,
        body_md: compose.body,
        cc: [],
        refs: compose.refs,
        reply_to: compose.replyTo,
      });
      notify.success(compose.replyTo ? "已回复" : "已发送");
      setShowCompose(false);
      await fetchPage(null, true, unreadOnly);
    } catch (e) {
      notify.error("发送失败", errorCause(e)?.message);
    } finally {
      setSending(false);
    }
  };

  const openCompose = () => {
    setCompose({ to: [], subject: "", body: "", replyTo: null, refs: [] });
    setShowCompose(true);
  };

  const openReply = (m: MailMessage) => {
    const sender = m.from.name ?? m.from.id;
    const subject = m.subject.replace(/^Re:\s*/i, "");
    setCompose({
      to: [{ label: sender, value: m.from.id ?? sender }],
      subject: `Re: ${subject}`,
      body: "",
      replyTo: m.message_id,
      refs: m.refs,
    });
    setShowCompose(true);
  };

  const memberOptions: Option[] = members.map((m) => ({ label: m.name, value: m.id }));
  const identityOptions: Option[] = [
    ...(me ? [{ label: `我（${me.user.name}）`, value: me.user.id }] : []),
    ...agents.map((a) => ({ label: `${a.name}（agent）`, value: a.id })),
  ];

  return (
    <Page testId="page-mailbox">
      <PageHeader
        title={`信箱 · ${projectKey}`}
        testId="mailbox-header"
        actions={
          <Inline space="space.100" alignBlock="center">
            <Box style={{ width: 190 }}>
              <Select<Option>
                isClearable
                spacing="compact"
                placeholder="全部身份"
                options={identityOptions}
                value={identityOptions.find((o) => o.value === identity) ?? null}
                onChange={(opt) => setIdentity((opt as Option | null)?.value ?? null)}
              />
            </Box>
            <Checkbox
              label="仅未读"
              isChecked={unreadOnly}
              testId="mailbox-unread-only"
              onChange={(e) => setUnreadOnly(e.currentTarget.checked)}
            />
            <Button
              appearance="primary"
              testId="mailbox-compose-button"
              onClick={openCompose}
            >
              发信
            </Button>
            <Button
              isDisabled={selected.size === 0}
              testId="mailbox-mark-read"
              onClick={() => void markRead([...selected])}
            >
              标记已读
            </Button>
          </Inline>
        }
      />

      {error ? (
        <ErrorState
          error={error}
          onRetry={() => void fetchPage(null, true, unreadOnly)}
          testId="mailbox-error"
        />
      ) : loading ? (
        <Box xcss={styles.centered} testId="mailbox-loading">
          <Spinner size="large" />
        </Box>
      ) : messages.length === 0 ? (
        <Box testId="mailbox-empty">
          <EmptyState header="没有信件" description="有新站内信时会出现在这里。" />
        </Box>
      ) : (
        <Stack space="space.100" testId="mailbox-list">
          {messages.map((m) => (
            <Box
              key={m.delivery_id}
              xcss={styles.card}
              testId={`mailbox-item-${m.delivery_id}`}
              style={
                m.read_at
                  ? cardBorder
                  : { ...cardBorder, borderInlineStart: `3px solid ${token("color.border.selected")}` }
              }
            >
              <Stack space="space.075">
                <Inline space="space.100" alignBlock="center">
                  {!m.read_at && (
                    <Checkbox
                      isChecked={selected.has(m.delivery_id)}
                      testId={`mailbox-item-select-${m.delivery_id}`}
                      onChange={() => toggle(m.delivery_id)}
                    />
                  )}
                  {m.mailbox_owner && (
                    <Lozenge
                      appearance={m.mailbox_owner.type === "agent" ? "warning" : "new"}
                      testId={`mailbox-owner-${m.delivery_id}`}
                    >
                      {m.mailbox_owner.id === me?.user.id
                        ? "我的信箱"
                        : `${m.mailbox_owner.name ?? "未知身份"}${
                            m.mailbox_owner.type === "agent" ? "（agent）" : ""
                          }`}
                    </Lozenge>
                  )}
                  <Text weight="semibold">{m.subject}</Text>
                  <Lozenge appearance="default">{m.from.name ?? m.from.id}</Lozenge>
                  <Text size="small" color="color.text.subtlest">
                    {formatDate(m.created_at)}
                  </Text>
                  {!m.read_at && (
                    <TextButton
                      data-testid={`mailbox-item-mark-read-${m.delivery_id}`}
                      onClick={() => void markRead([m.delivery_id])}
                    >
                      标已读
                    </TextButton>
                  )}
                  <TextButton
                    data-testid={`mailbox-item-reply-${m.delivery_id}`}
                    onClick={() => openReply(m)}
                  >
                    回复
                  </TextButton>
                </Inline>
                <Box paddingInlineStart="space.300">
                  <MarkdownText source={m.body_md} onImageClick={setPreview} />
                </Box>
                {m.refs.length > 0 && (
                  <Inline space="space.100">
                    <Text size="small" color="color.text.subtlest">
                      关联：
                    </Text>
                    {m.refs.map((r) => (
                      <Link
                        key={r}
                        className="rdm-link"
                        to={`/projects/${projectKey}/items/${r}`}
                        state={{ from: location.pathname + location.search }}
                        data-testid={`mailbox-item-ref-${r}`}
                      >
                        {r}
                      </Link>
                    ))}
                  </Inline>
                )}
              </Stack>
            </Box>
          ))}
        </Stack>
      )}

      {nextCursor && (
        <Box paddingBlock="space.200" style={{ textAlign: "center" }}>
          <Button testId="mailbox-load-more" onClick={() => void fetchPage(nextCursor, false, unreadOnly)}>
            加载更多
          </Button>
        </Box>
      )}

      <ModalTransition>
        {showCompose && (
          <ModalDialog
            onClose={() => setShowCompose(false)}
            width="520px"
            label={compose.replyTo ? "回复信件" : "发站内信"}
            testId="mailbox-compose-dialog"
          >
            <ModalHeader>
              <ModalTitle>{compose.replyTo ? "回复信件" : "发站内信"}</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.150">
                <FormField label="收件人" htmlFor="mail-to">
                  <Select<Option, true> {...portalMenuProps}
                    inputId="mail-to"
                    isMulti
                    options={memberOptions}
                    value={compose.to}
                    onChange={(opts) => setCompose({ ...compose, to: opts as Option[] })}
                    placeholder="选择成员"
                  />
                </FormField>
                <FormField label="主题" htmlFor="mail-subject">
                  <Textfield
                    id="mail-subject"
                    value={compose.subject}
                    testId="mailbox-compose-subject"
                    onChange={(e) => setCompose({ ...compose, subject: e.currentTarget.value })}
                  />
                </FormField>
                <FormField label="正文（Markdown）">
                  <MarkdownEditor
                    value={compose.body}
                    onChange={(body) => setCompose({ ...compose, body })}
                    projectKey={projectKey}
                    minimumRows={6}
                    testId="mailbox-compose-body"
                    onSubmit={() => void send()}
                  />
                </FormField>
              </Stack>
            </ModalBody>
            <ModalFooter>
              <Button
                appearance="subtle"
                testId="mailbox-compose-cancel"
                onClick={() => setShowCompose(false)}
              >
                取消
              </Button>
              <Button
                appearance="primary"
                isLoading={sending}
                testId="mailbox-compose-submit"
                onClick={() => void send()}
              >
                发送
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>
      <ImagePreviewDialog
        open={preview !== null}
        src={preview?.src ?? null}
        alt={preview?.alt}
        onClose={() => setPreview(null)}
      />
    </Page>
  );
}
