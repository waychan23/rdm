import { useCallback, useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";

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
import type { MailGroup, MailMessage, Mailbox, OrgUser, ProjectMemberRow } from "../types";
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
  const { key: routeProjectKey } = useParams<{ key?: string }>();
  const location = useLocation();
  const notify = useNotify();
  const me = useCurrentUser();
  const projectKey = routeProjectKey ?? "";
  const [searchParams, setSearchParams] = useSearchParams();
  const projectFilter = searchParams.get("project") ?? projectKey;
  const folder: "inbox" | "archived" | "sent" =
    searchParams.get("folder") === "archived"
      ? "archived"
      : searchParams.get("folder") === "sent"
        ? "sent"
        : "inbox";
  const order: "desc" | "asc" = searchParams.get("order") === "asc" ? "asc" : "desc";
  const view: "flat" | "thread" = searchParams.get("view") === "thread" ? "thread" : "flat";
  const query = searchParams.get("q") ?? "";
  const identity = searchParams.get("identity");
  const unreadOnly = searchParams.get("unread") !== "false";

  const patchParams = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(patch)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    setSearchParams(next, { replace: true });
  };
  const setProjectFilter = (value: string) =>
    patchParams({ project: value && value !== projectKey ? value : null });
  const setFolder = (value: "inbox" | "archived" | "sent") =>
    patchParams({ folder: value === "inbox" ? null : value });
  const setOrder = (value: "asc" | "desc") =>
    patchParams({ order: value === "desc" ? null : value });
  const setView = (value: "flat" | "thread") =>
    patchParams({ view: value === "flat" ? null : value });
  const setQuery = (value: string) => patchParams({ q: value || null });
  const setIdentity = (value: string | null) => patchParams({ identity: value });
  const setUnreadOnly = (value: boolean) =>
    patchParams({ unread: value ? null : "false" });

  const [messages, setMessages] = useState<MailMessage[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [collapsedThreads, setCollapsedThreads] = useState<Set<string>>(new Set());
  const [searchDraft, setSearchDraft] = useState(query);
  const [agents, setAgents] = useState<OrgUser[]>([]);
  const [groups, setGroups] = useState<MailGroup[]>([]);
  const [showGroups, setShowGroups] = useState(false);
  const [groupName, setGroupName] = useState("");
  const [groupMembers, setGroupMembers] = useState<Option[]>([]);
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
    async (cursor: string | null, replace: boolean) => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({
          limit: "20",
          unread_only: String(folder === "inbox" ? unreadOnly : false),
          include_agents: "true",
          folder,
        });
        if (identity) params.set("identity", identity);
        if (query.trim()) params.set("q", query.trim());
        params.set("order", order);
        if (cursor) params.set(order === "desc" ? "before" : "since", cursor);
        const base = projectFilter ? `/projects/${projectFilter}/mailbox` : "/mailbox";
        const box = (await api.get<Mailbox>(`${base}?${params}`)).data;
        setMessages((prev) => (replace ? box.messages : [...prev, ...box.messages]));
        setNextCursor(box.next_cursor);
      } catch (e) {
        setError(e);
      } finally {
        setLoading(false);
      }
    },
    [projectFilter, identity, unreadOnly, folder, query, order],
  );

  useEffect(() => {
    setSelected(new Set());
    void fetchPage(null, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unreadOnly, projectFilter, identity, folder, query, order]);

  useEffect(() => setSearchDraft(query), [query]);

  useEffect(() => {
    if (!projectFilter) {
      setMembers([]);
      return;
    }
    api
      .get<ProjectMemberRow[]>(`/projects/${projectFilter}/members`)
      .then((r) => setMembers(flattenMembers(r.data)))
      .catch(() => {});
  }, [projectFilter]);

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
      await fetchPage(null, true);
    } catch (e) {
      notify.error("标记失败", errorCause(e)?.message);
    }
  };

  const archive = async (ids: string[], archived: boolean) => {
    try {
      await api.post("/messages/archive", { delivery_ids: ids, archived });
      setSelected(new Set());
      notify.success(archived ? "已归档" : "已移回收件箱");
      await fetchPage(null, true);
    } catch (e) {
      notify.error("归档失败", errorCause(e)?.message);
    }
  };

  const remove = async (ids: string[]) => {
    try {
      await api.post("/messages/delete", { delivery_ids: ids });
      setSelected(new Set());
      notify.success("已删除");
      await fetchPage(null, true);
    } catch (e) {
      notify.error("删除失败", errorCause(e)?.message);
    }
  };

  const loadGroups = useCallback(async () => {
    if (!projectFilter) {
      setGroups([]);
      return;
    }
    try {
      const res = await api.get<MailGroup[]>(`/projects/${projectFilter}/mailboxes`);
      setGroups(res.data);
    } catch (e) {
      notify.error("加载群信箱失败", errorCause(e)?.message);
    }
  }, [projectFilter, notify]);

  useEffect(() => {
    void loadGroups();
  }, [loadGroups]);

  const openGroups = async () => {
    if (!projectFilter) {
      notify.error("请先在顶部选择项目");
      return;
    }
    setShowGroups(true);
    setGroupName("");
    setGroupMembers([]);
    await loadGroups();
  };

  const createGroup = async () => {
    if (!projectFilter) {
      notify.error("请先在顶部选择项目");
      return;
    }
    if (!groupName.trim()) {
      notify.error("群信箱名称必填");
      return;
    }
    try {
      await api.post(`/projects/${projectKey}/mailboxes`, {
        name: groupName.trim(),
        members: groupMembers.map((m) => m.value),
      });
      notify.success("已创建群信箱");
      setGroupName("");
      setGroupMembers([]);
      await loadGroups();
    } catch (e) {
      notify.error("创建失败", errorCause(e)?.message);
    }
  };

  const send = async () => {
    if (!projectFilter) {
      notify.error("请先在顶部选择项目后再发信");
      return;
    }
    if (!compose.to.length || !compose.subject.trim() || !compose.body.trim()) {
      notify.error("收件人、主题、正文均必填");
      return;
    }
    setSending(true);
    try {
      await api.post(`/projects/${projectFilter}/messages`, {
        to: compose.to.map((o) => o.value),
        subject: compose.subject,
        body_md: compose.body,
        cc: [],
        refs: compose.refs,
        reply_to: compose.replyTo,
      });
      notify.success(compose.replyTo ? "已回复" : "已发送");
      setShowCompose(false);
      await fetchPage(null, true);
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
  const recipientOptions: Option[] = [
    ...memberOptions,
    ...groups.map((g) => ({ label: `${g.name}（群信箱）`, value: g.name })),
  ];
  const projectOptions: Option[] = (me?.projects ?? []).map((p) => ({
    label: `${p.key} · ${p.name}`,
    value: p.key,
  }));
  const sortOptions: Option[] = [
    { label: "最新在前", value: "desc" },
    { label: "最早在前", value: "asc" },
  ];
  const identityOptions: Option[] = [
    ...(me ? [{ label: `我（${me.user.name}）`, value: me.user.id }] : []),
    ...agents.map((a) => ({ label: `${a.name}（agent）`, value: a.id })),
  ];

  const threadGroups = useMemo(() => {
    const groups = new Map<string, MailMessage[]>();
    for (const message of messages) {
      const key = message.thread_id || message.message_id;
      const bucket = groups.get(key) ?? [];
      bucket.push(message);
      groups.set(key, bucket);
    }
    return [...groups.entries()]
      .map(([id, rows]) => {
        const sorted = [...rows].sort((a, b) => a.created_at.localeCompare(b.created_at));
        return {
          id,
          messages: sorted,
          root: sorted.find((row) => !row.reply_to_id) ?? sorted[0],
          latest: sorted[sorted.length - 1],
        };
      })
      .sort((a, b) =>
        order === "desc"
          ? b.latest.created_at.localeCompare(a.latest.created_at)
          : a.latest.created_at.localeCompare(b.latest.created_at),
      );
  }, [messages, order]);

  const renderMessage = (m: MailMessage) => {
    const refProject = m.project?.key ?? projectFilter;
    return (
      <Box
        key={m.delivery_id}
        xcss={styles.card}
        testId={`mailbox-item-${m.delivery_id}`}
        style={
          m.read_at
            ? cardBorder
            : {
                ...cardBorder,
                borderInlineStart: `3px solid ${token("color.border.selected")}`,
              }
        }
      >
        <Stack space="space.075">
          <Inline space="space.100" alignBlock="center" shouldWrap>
            {folder !== "sent" && (
              <Checkbox
                isChecked={selected.has(m.delivery_id)}
                testId={`mailbox-item-select-${m.delivery_id}`}
                onChange={() => toggle(m.delivery_id)}
              />
            )}
            {!projectFilter && m.project ? (
              <Lozenge appearance="default" testId={`mailbox-project-${m.delivery_id}`}>
                {m.project.name}（{m.project.key}）
              </Lozenge>
            ) : null}
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
            {folder === "sent" && m.recipients?.length ? (
              <Text size="small" color="color.text.subtlest">
                收件人：{m.recipients.map((r) => r.name ?? r.id).join("、")}
              </Text>
            ) : null}
            <Text size="small" color="color.text.subtlest">
              {formatDate(m.created_at)}
            </Text>
            {!m.read_at && folder === "inbox" && (
              <TextButton
                data-testid={`mailbox-item-mark-read-${m.delivery_id}`}
                onClick={() => void markRead([m.delivery_id])}
              >
                标已读
              </TextButton>
            )}
            {folder !== "sent" && (
              <>
                <TextButton
                  data-testid={`mailbox-item-archive-${m.delivery_id}`}
                  onClick={() => void archive([m.delivery_id], folder === "inbox")}
                >
                  {folder === "inbox" ? "归档" : "移回收件箱"}
                </TextButton>
                <TextButton
                  data-testid={`mailbox-item-delete-${m.delivery_id}`}
                  onClick={() => void remove([m.delivery_id])}
                >
                  删除
                </TextButton>
              </>
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
                  to={`/projects/${refProject}/items/${r}`}
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
    );
  };

  return (
    <Page testId="page-mailbox">
      <PageHeader
        title={projectFilter ? `信箱 · ${projectFilter}` : "信箱"}
        testId="mailbox-header"
        actions={
          <Inline space="space.100" alignBlock="center" shouldWrap>
            <Inline space="space.050">
              {(["inbox", "archived", "sent"] as const).map((f) => (
                <Button
                  key={f}
                  appearance={folder === f ? "primary" : "default"}
                  spacing="compact"
                  testId={`mailbox-folder-${f}`}
                  onClick={() => setFolder(f)}
                >
                  {f === "inbox" ? "收件箱" : f === "archived" ? "已归档" : "已发送"}
                </Button>
              ))}
            </Inline>
            <Box style={{ width: 210 }}>
              <Select<Option>
                isClearable
                spacing="compact"
                placeholder="全部项目"
                inputId="mailbox-project-filter"
                options={projectOptions}
                value={projectOptions.find((o) => o.value === projectFilter) ?? null}
                onChange={(opt) => setProjectFilter((opt as Option | null)?.value ?? "")}
                testId="mailbox-project-filter"
              />
            </Box>
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
            <Box style={{ width: 200 }}>
              <Textfield
                placeholder="搜索主题/正文"
                value={searchDraft}
                testId="mailbox-search"
                onChange={(e) => setSearchDraft(e.currentTarget.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") setQuery(searchDraft.trim());
                }}
                onBlur={() => setQuery(searchDraft.trim())}
              />
            </Box>
            <Box style={{ width: 130 }}>
              <Select<Option>
                spacing="compact"
                inputId="mailbox-sort"
                options={sortOptions}
                value={sortOptions.find((o) => o.value === order) ?? null}
                onChange={(opt) =>
                  setOrder(((opt as Option | null)?.value as "asc" | "desc") ?? "desc")
                }
                testId="mailbox-sort"
              />
            </Box>
            <Inline space="space.050">
              <Button
                appearance={view === "flat" ? "primary" : "default"}
                spacing="compact"
                testId="mailbox-view-flat"
                onClick={() => setView("flat")}
              >
                平铺
              </Button>
              <Button
                appearance={view === "thread" ? "primary" : "default"}
                spacing="compact"
                testId="mailbox-view-thread"
                onClick={() => setView("thread")}
              >
                会话
              </Button>
            </Inline>
            {folder === "inbox" && (
              <Checkbox
                label="仅未读"
                isChecked={unreadOnly}
                testId="mailbox-unread-only"
                onChange={(e) => setUnreadOnly(e.currentTarget.checked)}
              />
            )}
            <Button appearance="primary" testId="mailbox-compose-button" onClick={openCompose}>
              发信
            </Button>
            <Button testId="mailbox-groups-button" onClick={() => void openGroups()}>
              群信箱
            </Button>
            {folder !== "sent" && (
              <Button
                isDisabled={selected.size === 0}
                testId="mailbox-mark-read"
                onClick={() => void markRead([...selected])}
              >
                标记已读
              </Button>
            )}
          </Inline>
        }
      />

      {error ? (
        <ErrorState
          error={error}
          onRetry={() => void fetchPage(null, true)}
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
        <Box testId="mailbox-list">
          {view === "flat" ? (
            <Stack space="space.100">{messages.map((m) => renderMessage(m))}</Stack>
          ) : (
            <Stack space="space.150">
              {threadGroups.map((thread) => {
                const collapsed = collapsedThreads.has(thread.id);
                return (
                  <Box
                    key={thread.id}
                    style={cardBorder}
                    padding="space.100"
                    testId={`mailbox-thread-${thread.id}`}
                  >
                    <Box
                      role="button"
                      tabIndex={0}
                      onClick={() =>
                        setCollapsedThreads((prev) => {
                          const next = new Set(prev);
                          if (next.has(thread.id)) next.delete(thread.id);
                          else next.add(thread.id);
                          return next;
                        })
                      }
                      onKeyDown={(e: KeyboardEvent<HTMLElement>) => {
                        if (e.target !== e.currentTarget) return;
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setCollapsedThreads((prev) => {
                            const next = new Set(prev);
                            if (next.has(thread.id)) next.delete(thread.id);
                            else next.add(thread.id);
                            return next;
                          });
                        }
                      }}
                      testId={`mailbox-thread-toggle-${thread.id}`}
                    >
                      <Inline space="space.100" alignBlock="center" shouldWrap>
                        <Text weight="semibold">{thread.root.subject}</Text>
                        <Lozenge appearance="default">{thread.messages.length} 封</Lozenge>
                        {!projectFilter && thread.root.project ? (
                          <Lozenge appearance="default">{thread.root.project.name}</Lozenge>
                        ) : null}
                        <Text size="small" color="color.text.subtlest">
                          {formatDate(thread.latest.created_at)}
                        </Text>
                        <Text size="small" color="color.text.subtlest">
                          {collapsed ? "展开" : "折叠"}
                        </Text>
                      </Inline>
                    </Box>
                    {!collapsed && (
                      <Box paddingBlockStart="space.100">
                        <Stack space="space.100">
                          {thread.messages.map((m) => renderMessage(m))}
                        </Stack>
                      </Box>
                    )}
                  </Box>
                );
              })}
            </Stack>
          )}
        </Box>
      )}

      {nextCursor && (
        <Box paddingBlock="space.200" style={{ textAlign: "center" }}>
          <Button testId="mailbox-load-more" onClick={() => void fetchPage(nextCursor, false)}>
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
                    options={recipientOptions}
                    value={compose.to}
                    onChange={(opts) => setCompose({ ...compose, to: opts as Option[] })}
                    placeholder="选择成员或群信箱"
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
      <ModalTransition>
        {showGroups && (
          <ModalDialog
            onClose={() => setShowGroups(false)}
            width="560px"
            label="群信箱"
            testId="mailbox-groups-dialog"
          >
            <ModalHeader>
              <ModalTitle>群信箱</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.150">
                <Text size="small" color="color.text.subtlest">
                  群信箱用于一次投递给多个成员；成员仍会各自收到一份站内信。
                </Text>
                <FormField label="名称" htmlFor="group-name">
                  <Textfield
                    id="group-name"
                    value={groupName}
                    testId="mailbox-group-name"
                    onChange={(e) => setGroupName(e.currentTarget.value)}
                  />
                </FormField>
                <FormField label="成员" htmlFor="group-members">
                  <Select<Option, true> {...portalMenuProps}
                    inputId="group-members"
                    isMulti
                    options={memberOptions}
                    value={groupMembers}
                    onChange={(opts) => setGroupMembers(opts as Option[])}
                    placeholder="选择成员"
                    testId="mailbox-group-members"
                  />
                </FormField>
                <Button appearance="primary" onClick={() => void createGroup()} testId="mailbox-group-create">
                  创建群信箱
                </Button>
                <Stack space="space.050" testId="mailbox-group-list">
                  {groups.map((g) => (
                    <Box key={g.id} style={cardBorder} padding="space.100" testId={`mailbox-group-${g.id}`}>
                      <Inline space="space.100" alignBlock="center" shouldWrap>
                        <Text weight="medium">{g.name}</Text>
                        <Text size="small" color="color.text.subtlest">
                          {g.members.map((m) => m.name).join("、") || "无成员"}
                        </Text>
                      </Inline>
                    </Box>
                  ))}
                  {groups.length === 0 ? (
                    <Text size="small" color="color.text.subtlest">
                      还没有群信箱
                    </Text>
                  ) : null}
                </Stack>
              </Stack>
            </ModalBody>
            <ModalFooter>
              <Button appearance="subtle" onClick={() => setShowGroups(false)}>
                关闭
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
