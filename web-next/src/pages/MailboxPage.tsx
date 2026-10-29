import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
import Checkbox from "@atlaskit/checkbox";
import Heading from "@atlaskit/heading";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import Select from "@atlaskit/select";
import Textfield from "@atlaskit/textfield";
import TextArea from "@atlaskit/textarea";
import EmptyState from "@atlaskit/empty-state";
import Spinner from "@atlaskit/spinner";
import Lozenge from "@atlaskit/lozenge";
import { Box, Inline, Stack, Text, xcss } from "@atlaskit/primitives";
import { token } from "@atlaskit/tokens";

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

const mailListStyles = xcss({
  marginTop: "space.200",
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
    <Box padding="space.300">
      <Inline spread="space-between" alignBlock="center">
        <Heading size="large">信箱 · {projectKey}</Heading>
        <Inline space="space.100" alignBlock="center">
          <Checkbox
            label="仅未读"
            isChecked={unreadOnly}
            onChange={(e) => setUnreadOnly(e.currentTarget.checked)}
          />
          <Button appearance="primary" onClick={() => setShowCompose(true)}>
            发信
          </Button>
          <Button
            isDisabled={selected.size === 0}
            onClick={() => void markRead([...selected])}
          >
            标记已读
          </Button>
        </Inline>
      </Inline>

      <Stack space="space.100" xcss={mailListStyles}>
        {loading ? (
          <Spinner size="large" />
        ) : messages.length === 0 ? (
          <EmptyState header="没有信件" />
        ) : (
          messages.map((m) => (
            <Box
              key={m.delivery_id}
              xcss={card}
              style={
                m.read_at
                  ? undefined
                  : { borderLeft: `3px solid ${token("color.border.selected")}` }
              }
            >
              <Stack space="space.075">
                <Inline space="space.100" alignBlock="center">
                  {!m.read_at && (
                    <Checkbox
                      isChecked={selected.has(m.delivery_id)}
                      onChange={() => toggle(m.delivery_id)}
                    />
                  )}
                  <Text weight="semibold">{m.subject}</Text>
                  <Lozenge appearance="default">{m.from.name ?? m.from.id}</Lozenge>
                  <Text size="small" color="color.text.subtlest">
                    {formatDate(m.created_at)}
                  </Text>
                  {!m.read_at && (
                    <TextButton onClick={() => void markRead([m.delivery_id])}>标已读</TextButton>
                  )}
                </Inline>
                <div style={{ whiteSpace: "pre-wrap", paddingLeft: 24 }}>{m.body_md}</div>
                {m.refs.length > 0 && (
                  <Inline space="space.100">
                    <Text size="small" color="color.text.subtlest">
                      关联：
                    </Text>
                    {m.refs.map((r) => (
                      <Link key={r} to={`/projects/${projectKey}/items/${r}`}>
                        {r}
                      </Link>
                    ))}
                  </Inline>
                )}
              </Stack>
            </Box>
          ))
        )}
      </Stack>

      {nextCursor && (
        <Box paddingBlock="space.200" style={{ textAlign: "center" }}>
          <Button onClick={() => void fetchPage(nextCursor, false, unreadOnly)}>加载更多</Button>
        </Box>
      )}

      <ModalTransition>
        {showCompose && (
          <ModalDialog onClose={() => setShowCompose(false)} width="520px">
            <ModalHeader>
              <ModalTitle>发站内信</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.150">
                <Stack space="space.050">
                  <label htmlFor="mail-to">收件人</label>
                  <Select<Option, true>
                    inputId="mail-to"
                    isMulti
                    options={memberOptions}
                    value={compose.to}
                    onChange={(opts) => setCompose({ ...compose, to: opts as Option[] })}
                    placeholder="选择成员"
                  />
                </Stack>
                <Stack space="space.050">
                  <label htmlFor="mail-subject">主题</label>
                  <Textfield
                    id="mail-subject"
                    value={compose.subject}
                    onChange={(e) => setCompose({ ...compose, subject: e.currentTarget.value })}
                  />
                </Stack>
                <Stack space="space.050">
                  <label htmlFor="mail-body">正文（Markdown）</label>
                  <TextArea
                    id="mail-body"
                    value={compose.body}
                    minimumRows={5}
                    onChange={(e) => setCompose({ ...compose, body: e.currentTarget.value })}
                  />
                </Stack>
              </Stack>
            </ModalBody>
            <ModalFooter>
              <Button appearance="subtle" onClick={() => setShowCompose(false)}>
                取消
              </Button>
              <Button appearance="primary" isLoading={sending} onClick={() => void send()}>
                发送
              </Button>
            </ModalFooter>
          </ModalDialog>
        )}
      </ModalTransition>
    </Box>
  );
}

function TextButton({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        marginLeft: "auto",
        background: "none",
        border: "none",
        color: token("color.link"),
        cursor: "pointer",
        padding: 0,
        font: "inherit",
      }}
    >
      {children}
    </button>
  );
}
