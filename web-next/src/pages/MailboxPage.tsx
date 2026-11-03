import { useCallback, useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

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
import { useOpenWorkItem } from "../lib/itemOverlay";
import {
  useListProjectKey,
  useListSearchParams,
} from "../lib/originSearch";
import { userLabel } from "../lib/users";

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
  messageBody: {
    paddingInlineStart: "var(--ds-space-300)",
  },
  threadCard: {
    padding: "var(--ds-space-100)",
  },
  threadBody: {
    paddingBlockStart: "var(--ds-space-100)",
  },
  loadMore: {
    paddingBlock: "var(--ds-space-200)",
  },
  groupCard: {
    padding: "var(--ds-space-100)",
  },
});

interface Option {
  label: string;
  value: string;
}

export default function MailboxPage() {
  const { t } = useTranslation("mailbox");
  const { key: routeKey } = useParams<{ key?: string }>();
  // The origin URL owns the project while this page is a drawer backdrop.
  const routeProjectKey = useListProjectKey(routeKey ?? "");
  const notify = useNotify();
  const me = useCurrentUser();
  const projectKey = routeProjectKey ?? "";
  const openWorkItem = useOpenWorkItem();
  const [searchParams, setSearchParams] = useListSearchParams();
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
      notify.error(t("notify.markFailed"), errorCause(e)?.message);
    }
  };

  const archive = async (ids: string[], archived: boolean) => {
    try {
      await api.post("/messages/archive", { delivery_ids: ids, archived });
      setSelected(new Set());
      notify.success(archived ? t("notify.archived") : t("notify.unarchived"));
      await fetchPage(null, true);
    } catch (e) {
      notify.error(t("notify.archiveFailed"), errorCause(e)?.message);
    }
  };

  const remove = async (ids: string[]) => {
    try {
      await api.post("/messages/delete", { delivery_ids: ids });
      setSelected(new Set());
      notify.success(t("notify.deleted"));
      await fetchPage(null, true);
    } catch (e) {
      notify.error(t("notify.deleteFailed"), errorCause(e)?.message);
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
      notify.error(t("notify.loadGroupsFailed"), errorCause(e)?.message);
    }
  }, [projectFilter, notify, t]);

  useEffect(() => {
    void loadGroups();
  }, [loadGroups]);

  const openGroups = async () => {
    if (!projectFilter) {
      notify.error(t("notify.selectProject"));
      return;
    }
    setShowGroups(true);
    setGroupName("");
    setGroupMembers([]);
    await loadGroups();
  };

  const createGroup = async () => {
    if (!projectFilter) {
      notify.error(t("notify.selectProject"));
      return;
    }
    if (!groupName.trim()) {
      notify.error(t("notify.groupNameRequired"));
      return;
    }
    try {
      await api.post(`/projects/${projectKey}/mailboxes`, {
        name: groupName.trim(),
        members: groupMembers.map((m) => m.value),
      });
      notify.success(t("notify.groupCreated"));
      setGroupName("");
      setGroupMembers([]);
      await loadGroups();
    } catch (e) {
      notify.error(t("notify.createFailed"), errorCause(e)?.message);
    }
  };

  const send = async () => {
    if (!projectFilter) {
      notify.error(t("notify.selectProjectToSend"));
      return;
    }
    if (!compose.to.length || !compose.subject.trim() || !compose.body.trim()) {
      notify.error(t("notify.recipientsRequired"));
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
      notify.success(compose.replyTo ? t("notify.replied") : t("notify.sent"));
      setShowCompose(false);
      await fetchPage(null, true);
    } catch (e) {
      notify.error(t("notify.sendFailed"), errorCause(e)?.message);
    } finally {
      setSending(false);
    }
  };

  const openCompose = () => {
    setCompose({ to: [], subject: "", body: "", replyTo: null, refs: [] });
    setShowCompose(true);
  };

  const openReply = (m: MailMessage) => {
    const sender = userLabel(m.from) || m.from.id;
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

  const memberOptions: Option[] = members.map((m) => ({
    label: userLabel(m),
    value: m.id,
  }));
  const recipientOptions: Option[] = [
    ...memberOptions,
    ...groups.map((g) => ({ label: t("group.option", { name: g.name }), value: g.name })),
  ];
  const projectOptions: Option[] = (me?.projects ?? []).map((p) => ({
    label: `${p.key} · ${p.name}`,
    value: p.key,
  }));
  const sortOptions: Option[] = [
    { label: t("sort.newest"), value: "desc" },
    { label: t("sort.oldest"), value: "asc" },
  ];
  const identityOptions: Option[] = [
    ...(me
      ? [{ label: t("identity.me", { name: userLabel(me.user) }), value: me.user.id }]
      : []),
    ...agents.map((a) => ({ label: t("identity.agent", { name: userLabel(a) }), value: a.id })),
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
                  ? t("owner.mine")
                  : m.mailbox_owner.type === "agent"
                    ? t("owner.agent", {
                        name: userLabel(m.mailbox_owner) || t("owner.unknown"),
                      })
                    : userLabel(m.mailbox_owner) || t("owner.unknown")}
              </Lozenge>
            )}
            <Text weight="semibold">{m.subject}</Text>
            <Lozenge appearance="default">{userLabel(m.from) || m.from.id}</Lozenge>
            {folder === "sent" && m.recipients?.length ? (
              <Text size="small" color="color.text.subtlest">
                {t("message.recipients", {
                  names: m.recipients
                    .map((r) => userLabel(r) || r.id)
                    .join(t("listSeparator")),
                })}
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
                {t("actions.markRead")}
              </TextButton>
            )}
            {folder !== "sent" && (
              <>
                <TextButton
                  data-testid={`mailbox-item-archive-${m.delivery_id}`}
                  onClick={() => void archive([m.delivery_id], folder === "inbox")}
                >
                  {folder === "inbox" ? t("actions.archive") : t("actions.unarchive")}
                </TextButton>
                <TextButton
                  data-testid={`mailbox-item-delete-${m.delivery_id}`}
                  onClick={() => void remove([m.delivery_id])}
                >
                  {t("actions.delete")}
                </TextButton>
              </>
            )}
            <TextButton
              data-testid={`mailbox-item-reply-${m.delivery_id}`}
              onClick={() => openReply(m)}
            >
              {t("actions.reply")}
            </TextButton>
          </Inline>
          <Box xcss={styles.messageBody}>
            <MarkdownText source={m.body_md} onImageClick={setPreview} />
          </Box>
          {m.refs.length > 0 && (
            <Inline space="space.100">
              <Text size="small" color="color.text.subtlest">
                {t("message.refs")}
              </Text>
              {m.refs.map((r) => (
                <TextButton
                  key={r}
                  data-testid={`mailbox-item-ref-${r}`}
                  onClick={() => openWorkItem(refProject, r)}
                >
                  {r}
                </TextButton>
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
        title={
          projectFilter
            ? t("title.withProject", { project: projectFilter })
            : t("title.default")
        }
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
                  {f === "inbox"
                    ? t("folder.inbox")
                    : f === "archived"
                      ? t("folder.archived")
                      : t("folder.sent")}
                </Button>
              ))}
            </Inline>
            <Box style={{ width: 210 }}>
              <Select<Option>
                isClearable
                spacing="compact"
                placeholder={t("placeholders.allProjects")}
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
                placeholder={t("placeholders.allIdentities")}
                options={identityOptions}
                value={identityOptions.find((o) => o.value === identity) ?? null}
                onChange={(opt) => setIdentity((opt as Option | null)?.value ?? null)}
              />
            </Box>
            <Box style={{ width: 200 }}>
              <Textfield
                placeholder={t("placeholders.search")}
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
                {t("view.flat")}
              </Button>
              <Button
                appearance={view === "thread" ? "primary" : "default"}
                spacing="compact"
                testId="mailbox-view-thread"
                onClick={() => setView("thread")}
              >
                {t("view.thread")}
              </Button>
            </Inline>
            {folder === "inbox" && (
              <Checkbox
                label={t("filters.unreadOnly")}
                isChecked={unreadOnly}
                testId="mailbox-unread-only"
                onChange={(e) => setUnreadOnly(e.currentTarget.checked)}
              />
            )}
            <Button appearance="primary" testId="mailbox-compose-button" onClick={openCompose}>
              {t("actions.compose")}
            </Button>
            <Button testId="mailbox-groups-button" onClick={() => void openGroups()}>
              {t("actions.groups")}
            </Button>
            {folder !== "sent" && (
              <Button
                isDisabled={selected.size === 0}
                testId="mailbox-mark-read"
                onClick={() => void markRead([...selected])}
              >
                {t("actions.markSelectedRead")}
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
          <EmptyState header={t("empty.header")} description={t("empty.description")} />
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
                    xcss={styles.threadCard}
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
                        <Lozenge appearance="default">
                          {t("thread.count", { count: thread.messages.length })}
                        </Lozenge>
                        {!projectFilter && thread.root.project ? (
                          <Lozenge appearance="default">{thread.root.project.name}</Lozenge>
                        ) : null}
                        <Text size="small" color="color.text.subtlest">
                          {formatDate(thread.latest.created_at)}
                        </Text>
                        <Text size="small" color="color.text.subtlest">
                          {collapsed ? t("thread.expand") : t("thread.collapse")}
                        </Text>
                      </Inline>
                    </Box>
                    {!collapsed && (
                      <Box xcss={styles.threadBody}>
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
        <Box xcss={styles.loadMore} style={{ textAlign: "center" }}>
          <Button testId="mailbox-load-more" onClick={() => void fetchPage(nextCursor, false)}>
            {t("actions.loadMore")}
          </Button>
        </Box>
      )}

      <ModalTransition>
        {showCompose && (
          <ModalDialog
            onClose={() => setShowCompose(false)}
            width="520px"
            label={compose.replyTo ? t("compose.replyTitle") : t("compose.newTitle")}
            testId="mailbox-compose-dialog"
          >
            <ModalHeader>
              <ModalTitle>
                {compose.replyTo ? t("compose.replyTitle") : t("compose.newTitle")}
              </ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.150">
                <FormField label={t("fields.recipients")} htmlFor="mail-to">
                  <Select<Option, true> {...portalMenuProps}
                    inputId="mail-to"
                    isMulti
                    options={recipientOptions}
                    value={compose.to}
                    onChange={(opts) => setCompose({ ...compose, to: opts as Option[] })}
                    placeholder={t("placeholders.selectRecipients")}
                  />
                </FormField>
                <FormField label={t("fields.subject")} htmlFor="mail-subject">
                  <Textfield
                    id="mail-subject"
                    value={compose.subject}
                    testId="mailbox-compose-subject"
                    onChange={(e) => setCompose({ ...compose, subject: e.currentTarget.value })}
                  />
                </FormField>
                <FormField label={t("fields.body")}>
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
                {t("actions.cancel")}
              </Button>
              <Button
                appearance="primary"
                isLoading={sending}
                testId="mailbox-compose-submit"
                onClick={() => void send()}
              >
                {t("actions.send")}
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
            label={t("group.title")}
            testId="mailbox-groups-dialog"
          >
            <ModalHeader>
              <ModalTitle>{t("group.title")}</ModalTitle>
            </ModalHeader>
            <ModalBody>
              <Stack space="space.150">
                <Text size="small" color="color.text.subtlest">
                  {t("group.description")}
                </Text>
                <FormField label={t("fields.groupName")} htmlFor="group-name">
                  <Textfield
                    id="group-name"
                    value={groupName}
                    testId="mailbox-group-name"
                    onChange={(e) => setGroupName(e.currentTarget.value)}
                  />
                </FormField>
                <FormField label={t("fields.members")} htmlFor="group-members">
                  <Select<Option, true> {...portalMenuProps}
                    inputId="group-members"
                    isMulti
                    options={memberOptions}
                    value={groupMembers}
                    onChange={(opts) => setGroupMembers(opts as Option[])}
                    placeholder={t("placeholders.selectMembers")}
                    testId="mailbox-group-members"
                  />
                </FormField>
                <Button appearance="primary" onClick={() => void createGroup()} testId="mailbox-group-create">
                  {t("actions.createGroup")}
                </Button>
                <Stack space="space.050" testId="mailbox-group-list">
                  {groups.map((g) => (
                    <Box
                      key={g.id}
                      style={cardBorder}
                      xcss={styles.groupCard}
                      testId={`mailbox-group-${g.id}`}
                    >
                      <Inline space="space.100" alignBlock="center" shouldWrap>
                        <Text weight="medium">{g.name}</Text>
                        <Text size="small" color="color.text.subtlest">
                          {g.members.map((m) => userLabel(m)).join(t("listSeparator")) ||
                            t("group.noMembers")}
                        </Text>
                      </Inline>
                    </Box>
                  ))}
                  {groups.length === 0 ? (
                    <Text size="small" color="color.text.subtlest">
                      {t("group.none")}
                    </Text>
                  ) : null}
                </Stack>
              </Stack>
            </ModalBody>
            <ModalFooter>
              <Button appearance="subtle" onClick={() => setShowGroups(false)}>
                {t("actions.close")}
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
