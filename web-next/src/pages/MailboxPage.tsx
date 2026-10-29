import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

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
import TextArea from "@atlaskit/textarea";
import Textfield from "@atlaskit/textfield";
import { Box, Inline, Stack, Text, xcss } from "@atlaskit/primitives";
import { token } from "@atlaskit/tokens";

import FormField from "../components/FormField";
import { Page, PageHeader } from "../components/Page";
import TextButton from "../components/TextButton";
import { api, errorCause } from "../lib/api";
import { formatDate } from "../lib/format";
import { useNotify } from "../lib/flags";
import type { MailMessage, Mailbox, OrgUser, ProjectMemberRow } from "../types";
import { flattenMembers } from "../lib/members";

const card = xcss({
  border: "1px solid",
  borderColor: "color.border",
  borderRadius: "radius.small",
  padding: "space.150",
  backgroundColor: "elevation.surface",
});

const centeredStyles = xcss({
  display: "flex",
  justifyContent: "center",
  padding: "space.400",
});

interface Option {
  label: string;
  value: string;
}

export default function MailboxPage() {
  const { key: projectKey = "" } = useParams();
  const notify = useNotify();

  const [messages, setMessages] = useState<MailMessage[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [unreadOnly, setUnreadOnly] = useState(true);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [members, setMembers] = useState<OrgUser[]>([]);
  const [showCompose, setShowCompose] = useState(false);
  const [sending, setSending] = useState(false);
  const [compose, setCompose] = useState<{
    to: Option[];
    subject: string;
    body: string;
  }>({ to: [], subject: "", body: "" });

  const fetchPage = useCallback(
    async (cursor: string | null, replace: boolean, onlyUnread: boolean) => {
      setLoading(true);
      try {
        const params = new URLSearchParams({
          limit: "20",
          unread_only: String(onlyUnread),
        });
        if (cursor) params.set("since", cursor);
        const box = (await api.get<Mailbox>(`/projects/${projectKey}/mailbox?${params}`)).data;
        setMessages((prev) => (replace ? box.messages : [...prev, ...box.messages]));
        setNextCursor(box.next_cursor);
      } finally {
        setLoading(false);
      }
    },
    [projectKey],
  );

  useEffect(() => {
    setSelected(new Set());
    void fetchPage(null, true, unreadOnly);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unreadOnly, projectKey]);

  useEffect(() => {
    api
      .get<ProjectMemberRow[]>(`/projects/${projectKey}/members`)
      .then((r) => setMembers(flattenMembers(r.data)))
      .catch(() => {});
  }, [projectKey]);

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
        refs: [],
      });
      notify.success("已发送");
      setShowCompose(false);
      await fetchPage(null, true, unreadOnly);
    } catch (e) {
      notify.error("发送失败", errorCause(e)?.message);
    } finally {
      setSending(false);
    }
  };

  const memberOptions: Option[] = members.map((m) => ({ label: m.name, value: m.name }));

  return (
    <Page testId="page-mailbox">
      <PageHeader
        title={`信箱 · ${projectKey}`}
        testId="mailbox-header"
        actions={
          <Inline space="space.100" alignBlock="center">
            <Checkbox
              label="仅未读"
              isChecked={unreadOnly}
              testId="mailbox-unread-only"
              onChange={(e) => setUnreadOnly(e.currentTarget.checked)}
            />
            <Button
              appearance="primary"
              testId="mailbox-compose-button"
              onClick={() => setShowCompose(true)}
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

      {loading ? (
        <Box xcss={centeredStyles} testId="mailbox-loading">
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
              xcss={card}
              testId={`mailbox-item-${m.delivery_id}`}
              style={
                m.read_at
                  ? undefined
                  : { borderInlineStart: `3px solid ${token("color.border.selected")}` }
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
                </Inline>
                <Box as="div" style={{ whiteSpace: "pre-wrap" }} paddingInlineStart="space.300">
                  {m.body_md}
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
            testId="mailbox-compose-dialog"
          >
            <ModalHeader>
              <ModalTitle>发站内信</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.150">
                <FormField label="收件人" htmlFor="mail-to">
                  <Select<Option, true>
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
                <FormField label="正文（Markdown）" htmlFor="mail-body">
                  <TextArea
                    id="mail-body"
                    value={compose.body}
                    minimumRows={5}
                    testId="mailbox-compose-body"
                    onChange={(e) => setCompose({ ...compose, body: e.currentTarget.value })}
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
    </Page>
  );
}
