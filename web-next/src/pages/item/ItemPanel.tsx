import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import Button from "@atlaskit/button/default/button";
import IconButton from "@atlaskit/button/icon/button";
import Heading from "@atlaskit/heading";
import CrossIcon from "@atlaskit/icon/core/cross";
import Link from "@atlaskit/link";
import Select from "@atlaskit/select";
import SectionMessage from "@atlaskit/section-message";
import Spinner from "@atlaskit/spinner";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";
import { token } from "@atlaskit/tokens";

import ConfirmDialog from "../../components/ConfirmDialog";
import ImagePreviewDialog from "../../components/ImagePreviewDialog";
import MarkdownEditor from "../../components/MarkdownEditor";
import MarkdownText from "../../components/MarkdownText";
import PersonCell from "../../components/PersonCell";
import PriorityMark from "../../components/PriorityMark";
import TextButton from "../../components/TextButton";
import TypeKindIcon from "../../components/TypeKindIcon";
import WorkItemPicker, { type WorkItemOption } from "../../components/WorkItemPicker";
import EditWorkItemDialog from "../../workitems/EditWorkItemDialog";
import StatusLozenge from "../../workitems/status";
import { api, errorCause } from "../../lib/api";
import { useCurrentUser } from "../../lib/auth";
import { formatDate, formatSize } from "../../lib/format";
import { useNotify } from "../../lib/flags";
import { flattenMembers } from "../../lib/members";
import { portalMenuProps } from "../../lib/portalMenu";
import type {
  Artifact,
  Attachment,
  Comment,
  OrgUser,
  ProjectMemberRow,
  WorkItem,
  WorkItemDetailMeta,
} from "../../types";
import ArtifactDialog from "./ArtifactDialog";
import ChildrenSection from "./ChildrenSection";
import HistorySection from "./HistorySection";
import TransitionDialog from "./TransitionDialog";
import WorkItemFieldsView from "./WorkItemFieldsView";

interface Props {
  projectKey: string;
  itemId: string;
  onClose: () => void;
  onOpenItem: (id: string) => void;
}

interface DetailBundle {
  item: WorkItem;
  parent: WorkItem | null;
  children: WorkItem[];
  allowed: string[];
  allowedParentKinds: string[];
  allowedChildKinds: string[];
  comments: Comment[];
  members: OrgUser[];
  attachments: Attachment[];
  artifacts: Artifact[];
}

interface PreviewImage {
  src: string;
  alt: string;
}

const PRIORITY_VALUES = [0, 1, 2, 3, 4];
const COMMENTS_PAGE = 50;

function toWorkItemOption(item: WorkItem): WorkItemOption {
  return {
    label: `${item.display_id} · ${item.title}`,
    value: item.display_id,
    id: item.id,
    display_id: item.display_id,
    title: item.title,
    kind: item.kind,
    status: item.status,
    row_version: item.row_version,
  };
}

export default function ItemPanel({ projectKey, itemId, onClose, onOpenItem }: Props) {
  const notify = useNotify();
  const me = useCurrentUser();
  const [bundle, setBundle] = useState<DetailBundle | null>(null);
  const [loadError, setLoadError] = useState(false);

  const [showEdit, setShowEdit] = useState(false);
  const [transitionTarget, setTransitionTarget] = useState<string | null>(null);
  const [showArtifact, setShowArtifact] = useState(false);
  const [gateMessage, setGateMessage] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewImage | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [parentEditing, setParentEditing] = useState(false);
  const [commentToDelete, setCommentToDelete] = useState<Comment | null>(null);

  const [draft, setDraft] = useState("");
  const [replyTo, setReplyTo] = useState<Comment | null>(null);
  const [savingComment, setSavingComment] = useState(false);
  const [uploadingDraftImage, setUploadingDraftImage] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<{ name: string; id: string }[]>([]);
  const pendingIds = useRef<string[]>([]);
  const commentFileInput = useRef<HTMLInputElement>(null);
  const attachFileInput = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [hasMoreComments, setHasMoreComments] = useState(false);
  const [loadingMoreComments, setLoadingMoreComments] = useState(false);

  const load = useCallback(async () => {
    try {
      const detail = await api.get<WorkItem>(
        `/work-items/${encodeURIComponent(itemId)}`,
      );
      const meta = (detail.meta ?? {}) as WorkItemDetailMeta;
      const [cm, mm, am, artm] = await Promise.all([
        api.get<Comment[]>(
          `/work-items/${itemId}/comments?limit=${COMMENTS_PAGE}&offset=0`,
        ),
        api.get<ProjectMemberRow[]>(`/projects/${projectKey}/members`),
        api.get<Attachment[]>(
          `/projects/${projectKey}/attachments?owner_type=work_item&owner_ref=${encodeURIComponent(itemId)}`,
        ),
        api.get<Artifact[]>(
          `/projects/${projectKey}/artifacts?owner_type=work_item&owner_ref=${encodeURIComponent(itemId)}`,
        ),
      ]);
      setBundle({
        item: detail.data,
        parent: meta.parent ?? null,
        children: meta.children ?? [],
        allowed: meta.allowed_transitions ?? [],
        allowedParentKinds: meta.allowed_parent_kinds ?? [],
        allowedChildKinds: meta.allowed_child_kinds ?? [],
        comments: cm.data,
        members: flattenMembers(mm.data),
        attachments: am.data,
        artifacts: artm.data,
      });
      setHasMoreComments(cm.data.length >= COMMENTS_PAGE);
      setLoadError(false);
    } catch {
      setLoadError(true);
    }
  }, [itemId, projectKey]);

  useEffect(() => {
    setBundle(null);
    void load();
  }, [load]);

  const refresh = useCallback(async () => {
    await load();
    setRefreshKey((value) => value + 1);
  }, [load]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      if (
        showEdit ||
        showArtifact ||
        transitionTarget ||
        preview ||
        commentToDelete ||
        parentEditing
      ) {
        return;
      }
      event.preventDefault();
      onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    commentToDelete,
    onClose,
    parentEditing,
    preview,
    showArtifact,
    showEdit,
    transitionTarget,
  ]);

  const reportGate = (e: unknown) => {
    const cause = errorCause(e);
    if (cause?.code === "WORKFLOW_GATE_BLOCKED" && cause.details?.blocking_children) {
      const ids = ((cause.details.blocking_children as unknown) as string[]).join(", ");
      setGateMessage(`${cause.message}（阻塞: ${ids}）`);
    } else {
      notify.error("流转失败", cause?.message);
    }
  };

  const doTransition = async (reason: string | null) => {
    if (!bundle || !transitionTarget) return;
    try {
      await api.post(`/work-items/${itemId}/transition`, {
        to: transitionTarget,
        row_version: bundle.item.row_version,
        reason,
      });
      notify.success(`已流转到 ${transitionTarget}`);
      setTransitionTarget(null);
      await refresh();
    } catch (e) {
      setTransitionTarget(null);
      reportGate(e);
    }
  };

  const assign = async (memberId: string | null) => {
    if (!memberId) return;
    try {
      await api.post(`/work-items/${itemId}/assign`, { member: memberId });
      await refresh();
    } catch (e) {
      notify.error("指派失败", errorCause(e)?.message);
      await refresh();
    }
  };

  const changePriority = async (priority: number) => {
    if (!bundle) return;
    try {
      await api.patch(`/work-items/${itemId}`, {
        row_version: bundle.item.row_version,
        priority,
      });
      await refresh();
    } catch (e) {
      notify.error("优先级保存失败", errorCause(e)?.message);
      await refresh();
    }
  };

  const reparent = async (option: WorkItemOption | null) => {
    if (!bundle) return;
    try {
      await api.post(`/work-items/${itemId}/reparent`, {
        parent: option?.display_id ?? null,
        row_version: bundle.item.row_version,
      });
      notify.success(option ? `已改为 ${option.display_id} 的子项` : "已移出父项");
      setParentEditing(false);
      await refresh();
    } catch (e) {
      notify.error("更改父项失败", errorCause(e)?.message);
    }
  };

  const uploadFiles = async (files: FileList | null, attachToComment: boolean) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("file", file);
        form.append("owner_type", "work_item");
        form.append("owner_ref", itemId);
        const res = await api.upload<Attachment>(`/projects/${projectKey}/attachments`, form);
        if (attachToComment) {
          pendingIds.current.push(res.data.id);
          setPendingFiles((p) => [...p, { name: file.name, id: res.data.id }]);
        } else {
          setBundle((b) => (b ? { ...b, attachments: [...b.attachments, res.data] } : b));
        }
      }
      if (attachToComment) notify.success("附件已上传，提交评论时挂载");
    } catch (e) {
      notify.error("上传失败", errorCause(e)?.message);
    } finally {
      setUploading(false);
    }
  };

  const removeAttachment = async (id: string) => {
    try {
      await api.del(`/attachments/${id}`);
      setBundle((b) =>
        b ? { ...b, attachments: b.attachments.filter((a) => a.id !== id) } : b,
      );
    } catch (e) {
      notify.error("删除失败", errorCause(e)?.message);
    }
  };

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      notify.success("链接已复制");
    } catch {
      notify.error("复制失败", "浏览器未授予剪贴板权限");
    }
  };

  const loadMoreComments = async () => {    if (!bundle || loadingMoreComments) return;
    setLoadingMoreComments(true);
    try {
      const res = await api.get<Comment[]>(
        `/work-items/${itemId}/comments?limit=${COMMENTS_PAGE}&offset=${bundle.comments.length}`,
      );
      setBundle((b) =>
        b ? { ...b, comments: [...b.comments, ...res.data] } : b,
      );
      setHasMoreComments(res.data.length >= COMMENTS_PAGE);
    } catch (e) {
      notify.error("评论加载失败", errorCause(e)?.message);
    } finally {
      setLoadingMoreComments(false);
    }
  };

  const removeArtifact = async (id: string) => {    try {
      await api.post(`/artifacts/${id}/delete`, {});
      setBundle((b) =>
        b ? { ...b, artifacts: b.artifacts.filter((a) => a.id !== id) } : b,
      );
    } catch (e) {
      notify.error("删除失败", errorCause(e)?.message);
    }
  };

  const postComment = async () => {
    if (!draft.trim() || savingComment || uploadingDraftImage) return;
    setSavingComment(true);
    try {
      const res = await api.post<Comment>(`/work-items/${itemId}/comments`, {
        body_md: draft,
        reply_to_id: replyTo?.id ?? null,
        attachment_ids: pendingIds.current,
      });
      setBundle((b) =>
        b ? { ...b, comments: [...b.comments, res.data] } : b,
      );
      setRefreshKey((value) => value + 1);
      setDraft("");
      setReplyTo(null);
      pendingIds.current = [];
      setPendingFiles([]);
    } catch (e) {
      notify.error("评论失败", errorCause(e)?.message);
    } finally {
      setSavingComment(false);
    }
  };

  const deleteComment = async () => {
    if (!commentToDelete) return;
    const target = commentToDelete;
    setCommentToDelete(null);
    try {
      await api.del(`/comments/${target.id}`);
      await refresh();
    } catch (e) {
      notify.error("删除评论失败", errorCause(e)?.message);
    }
  };

  const addArtifact = async (a: { kind: string; label: string; url: string }) => {
    if (!a.label || !a.url) {
      notify.error("标题和 URL 必填");
      return;
    }
    try {
      const res = await api.post<Artifact>(`/projects/${projectKey}/artifacts`, {
        owner_type: "work_item",
        owner_ref: itemId,
        kind: a.kind,
        label: a.label,
        url: a.url,
        description_md: "",
      });
      setBundle((b) => (b ? { ...b, artifacts: [...b.artifacts, res.data] } : b));
      setShowArtifact(false);
    } catch (e) {
      notify.error("挂载失败", errorCause(e)?.message);
    }
  };

  if (loadError) {
    return (
      <aside className="rdm-item-panel" aria-label="工作项详情" data-testid="item-panel">
        <Box padding="space.400">
          <SectionMessage appearance="error">工作项加载失败或已被删除。</SectionMessage>
          <Box paddingBlockStart="space.200">
            <Button appearance="primary" testId="item-panel-error-back" onClick={onClose}>
              返回列表
            </Button>
          </Box>
        </Box>
      </aside>
    );
  }
  if (!bundle) {
    return (
      <aside className="rdm-item-panel" aria-label="工作项详情" data-testid="item-panel">
        <Box padding="space.400" testId="item-panel-loading">
          <Spinner size="large" />
        </Box>
      </aside>
    );
  }

  const {
    item,
    parent,
    children,
    allowed,
    allowedParentKinds,
    allowedChildKinds,
    comments,
    members,
    attachments,
    artifacts,
  } = bundle;
  const memberOptions = members.map((m) => ({ label: m.name, value: m.id }));
  const priorityValues = PRIORITY_VALUES.includes(item.priority)
    ? PRIORITY_VALUES
    : [...PRIORITY_VALUES, item.priority].sort((a, b) => a - b);
  const priorityOptions = priorityValues.map((value) => ({
    label: value === 0 ? "未设置" : `P${value}`,
    value,
  }));
  const identityId = me?.identity.id ?? me?.user.id ?? null;
  const projectRoles =
    me?.projects.find((project) => project.key === projectKey)?.roles ?? [];
  const canModerate =
    Boolean(me?.org_roles.includes("org_owner")) ||
    projectRoles.includes("project_owner") ||
    projectRoles.includes("manager");
  const parentOption = useMemo(
    () => (parent ? toWorkItemOption(parent) : null),
    [parent],
  );

  return (
    <aside className="rdm-item-panel" aria-label="工作项详情" data-testid="item-panel">
      <header className="rdm-item-head" data-testid="item-panel-header">
        <IconButton
          icon={(iconProps) => <CrossIcon {...iconProps} />}
          label="关闭"
          appearance="subtle"
          testId="item-panel-close"
          onClick={onClose}
        />
        <TypeKindIcon kind={item.kind} />
        <Text weight="medium" color="color.link" testId="item-panel-display-id">
          {item.display_id}
        </Text>
        <TextButton data-testid="item-panel-edit" onClick={() => setShowEdit(true)}>
          编辑
        </TextButton>
        <TextButton data-testid="item-panel-copy-link" onClick={() => void copyLink()}>
          复制链接
        </TextButton>
      </header>

      <div className="rdm-item-body">
        <section className="rdm-item-content" data-testid="item-panel-content">
          <Box paddingBlockEnd="space.200">
            <Heading size="medium" as="h2" testId="item-panel-title">
              {item.title}
            </Heading>
          </Box>

          <div className="rdm-item-section-label">描述</div>
          {item.description_md ? (
            <div className="rdm-item-desc" data-testid="item-panel-description">
              <MarkdownText source={item.description_md} onImageClick={setPreview} />
            </div>
          ) : (
            <div
              className="rdm-item-desc rdm-item-desc-empty"
              data-testid="item-panel-description-empty"
            >
              未填写描述
            </div>
          )}

          <div className="rdm-item-section-label">特型字段</div>
          <div data-testid="item-panel-fields-json">
            <WorkItemFieldsView
              item={item}
              onOpenItem={onOpenItem}
              onImageClick={setPreview}
            />
          </div>

          <div className="rdm-item-spacer" />
          <ChildrenSection
            projectKey={projectKey}
            parent={item}
            children={children}
            allowedKinds={allowedChildKinds}
            onOpen={onOpenItem}
            onChanged={() => void refresh()}
          />

          <div className="rdm-item-section-label">评论（{comments.length}）</div>
          <div data-testid="item-panel-comments">
            {comments.length === 0 && (
              <Text size="small" color="color.text.subtlest">
                还没有评论
              </Text>
            )}
            {comments.map((c) => {
              const parentComment = c.reply_to_id
                ? comments.find((x) => x.id === c.reply_to_id)
                : null;
              const canDelete = c.author.id === identityId || canModerate;
              return (
                <div key={c.id} className="rdm-item-comment" data-testid={`item-comment-${c.id}`}>
                  <div className="rdm-item-comment-head">
                    <PersonCell name={c.author.name ?? c.author.id} />
                    <Inline space="space.100" alignBlock="center">
                      <Text size="small" color="color.text.subtlest">
                        {formatDate(c.created_at)}
                      </Text>
                      <TextButton
                        data-testid={`item-comment-reply-${c.id}`}
                        onClick={() => setReplyTo(c)}
                      >
                        回复
                      </TextButton>
                      {canDelete && (
                        <TextButton
                          danger
                          data-testid={`item-comment-delete-${c.id}`}
                          onClick={() => setCommentToDelete(c)}
                        >
                          删除
                        </TextButton>
                      )}
                    </Inline>
                  </div>
                  {parentComment && (
                    <div className="rdm-item-comment-reply">
                      回复 {parentComment.author.name ?? parentComment.author.id}：
                      {parentComment.body_md.slice(0, 80)}
                    </div>
                  )}
                  <MarkdownText source={c.body_md} onImageClick={setPreview} />
                  {c.attachments
                    ?.filter((a) => !c.body_md.includes(a.download_url))
                    .map((a) => (
                    <div
                      key={a.id}
                      className="rdm-item-att"
                      style={{ marginTop: token("space.050") }}
                    >
                      <TextButton onClick={() => api.download(a.download_url, a.filename)}>
                        📎 {a.filename}
                      </TextButton>
                    </div>
                  ))}
                </div>
              );
            })}
            {hasMoreComments && (
              <Box paddingBlockStart="space.100">
                <TextButton
                  data-testid="item-comment-more"
                  onClick={() => void loadMoreComments()}
                >
                  {loadingMoreComments ? "加载中…" : "加载更多评论"}
                </TextButton>
              </Box>
            )}
          </div>
        </section>

        <section className="rdm-item-fields" data-testid="item-panel-fields">
          {gateMessage && (
            <Box paddingBlockEnd="space.150">
              <SectionMessage appearance="warning" onDismiss={() => setGateMessage(null)}>
                {gateMessage}
              </SectionMessage>
            </Box>
          )}

          <div className="rdm-item-field" data-testid="item-field-status">
            <div className="rdm-item-section-label">状态</div>
            <StatusLozenge status={item.status} />
          </div>

          <div className="rdm-item-field" data-testid="item-field-transition">
            <div className="rdm-item-section-label">流转到</div>
            <Select
              {...portalMenuProps}
              options={allowed.map((s) => ({ label: s, value: s }))}
              placeholder="选择目标状态"
              value={null}
              onChange={(opt) => opt && setTransitionTarget((opt as { value: string }).value)}
              isDisabled={allowed.length === 0}
            />
          </div>

          <div className="rdm-item-field" data-testid="item-field-priority">
            <div className="rdm-item-section-label">优先级</div>
            <Select
              {...portalMenuProps}
              options={priorityOptions}
              value={priorityOptions.find((o) => o.value === item.priority) ?? null}
              onChange={(opt) =>
                opt && void changePriority((opt as { value: number }).value)
              }
              isClearable={false}
            />
            <Box paddingBlockStart="space.050">
              <PriorityMark priority={item.priority} />
            </Box>
          </div>

          <div className="rdm-item-field" data-testid="item-field-assignee">
            <div className="rdm-item-section-label">负责人</div>
            <Select
              {...portalMenuProps}
              options={memberOptions}
              value={memberOptions.find((o) => o.value === item.assignee?.id) ?? null}
              placeholder="未指派"
              isClearable
              onChange={(opt) => assign((opt as { value: string } | null)?.value ?? null)}
            />
          </div>

          <div className="rdm-item-field" data-testid="item-field-parent">
            <div className="rdm-item-section-label">父项</div>
            {parent && !parentEditing ? (
              <Inline space="space.100" alignBlock="center">
                <TextButton onClick={() => onOpenItem(parent.id)}>
                  {parent.display_id}
                </TextButton>
                <Text size="small" color="color.text.subtlest">
                  {parent.title}
                </Text>
              </Inline>
            ) : (
              <Text size="small" color="color.text.subtlest">
                {allowedParentKinds.length === 0 ? "该类型不支持父项" : "无父项"}
              </Text>
            )}
            {allowedParentKinds.length > 0 && (
              <Box paddingBlockStart="space.100">
                {parentEditing ? (
                  <Stack space="space.100">
                    <WorkItemPicker
                      projectKey={projectKey}
                      allowedKinds={allowedParentKinds}
                      excludeIds={[item.id, ...children.map((c) => c.id)]}
                      value={parentOption}
                      onChange={(option) => void reparent(option)}
                      placeholder="选择父项"
                      testId="item-parent-picker"
                    />
                    <TextButton onClick={() => setParentEditing(false)}>取消</TextButton>
                  </Stack>
                ) : (
                  <Inline space="space.100">
                    <TextButton
                      data-testid="item-parent-change"
                      onClick={() => setParentEditing(true)}
                    >
                      {parent ? "更改父项" : "设置父项"}
                    </TextButton>
                    {parent && (
                      <TextButton danger onClick={() => void reparent(null)}>
                        移出父项
                      </TextButton>
                    )}
                  </Inline>
                )}
              </Box>
            )}
          </div>

          <div className="rdm-item-field">
            <div className="rdm-item-section-label">类型 / 版本</div>
            <Text size="small" color="color.text.subtlest">
              {item.kind} · v{item.row_version}
            </Text>
          </div>
          <div className="rdm-item-field">
            <div className="rdm-item-section-label">创建时间</div>
            <Text size="small" color="color.text.subtlest">
              {formatDate(item.created_at)}
            </Text>
          </div>

          <div className="rdm-item-field" data-testid="item-field-attachments">
            <div className="rdm-item-section-label">附件</div>
            <input
              ref={attachFileInput}
              type="file"
              multiple
              hidden
              onChange={(e) => void uploadFiles(e.target.files, false)}
            />
            <Button
              isLoading={uploading}
              testId="item-attachment-upload"
              onClick={() => attachFileInput.current?.click()}
            >
              上传附件
            </Button>
            {attachments.map((a) => (
              <div key={a.id} className="rdm-item-att" data-testid={`item-attachment-${a.id}`}>
                <TextButton onClick={() => api.download(a.download_url, a.filename)}>
                  <span className="rdm-item-att-name">{a.filename}</span>
                </TextButton>
                <Text size="small" color="color.text.subtlest">
                  {formatSize(a.size_bytes)}
                </Text>
                <TextButton danger onClick={() => removeAttachment(a.id)}>
                  删除
                </TextButton>
              </div>
            ))}
          </div>

          <div className="rdm-item-field" data-testid="item-field-artifacts">
            <div className="rdm-item-section-label">产出物</div>
            {artifacts.map((art) => (
              <div key={art.id} className="rdm-item-att" data-testid={`item-artifact-${art.id}`}>
                <Link href={art.url} target="_blank" testId={`item-artifact-link-${art.id}`}>
                  {art.label}
                </Link>
                <Text size="small" color="color.text.subtlest">
                  {art.kind}
                </Text>
                <TextButton danger onClick={() => removeArtifact(art.id)}>
                  删除
                </TextButton>
              </div>
            ))}
            <Button testId="item-artifact-add" onClick={() => setShowArtifact(true)}>
              挂产出物
            </Button>
          </div>

          <HistorySection itemId={item.id} refreshKey={refreshKey} />
        </section>
      </div>

      <footer className="rdm-item-comment-bar" data-testid="item-comment-bar">
        {replyTo && (
          <div className="rdm-item-comment-reply-chip">
            <Text size="small" color="color.text.subtlest">
              回复 {replyTo.author.name ?? replyTo.author.id}
            </Text>
            <TextButton onClick={() => setReplyTo(null)}>取消</TextButton>
          </div>
        )}
        <MarkdownEditor
          value={draft}
          onChange={setDraft}
          projectKey={projectKey}
          minimumRows={2}
          placeholder="写评论；@成员名 会给对方发站内信"
          testId="item-comment"
          onSubmit={() => void postComment()}
          onImageClick={setPreview}
          onUploadingChange={setUploadingDraftImage}
          isDisabled={savingComment}
        />
        {pendingFiles.length > 0 && (
          <Inline space="space.100" shouldWrap>
            {pendingFiles.map((f) => (
              <Text key={f.id} size="small" color="color.text.subtlest">
                📎 {f.name}
              </Text>
            ))}
          </Inline>
        )}
        <div className="rdm-item-comment-actions">
          <input
            ref={commentFileInput}
            type="file"
            multiple
            hidden
            onChange={(e) => void uploadFiles(e.target.files, true)}
          />
          <Button testId="item-comment-attach" onClick={() => commentFileInput.current?.click()}>
            添加附件
          </Button>
          <Button
            appearance="primary"
            isLoading={savingComment}
            isDisabled={uploadingDraftImage}
            testId="item-comment-submit"
            onClick={() => void postComment()}
          >
            提交评论
          </Button>
        </div>
      </footer>

      <TransitionDialog
        to={transitionTarget}
        onCancel={() => setTransitionTarget(null)}
        onConfirm={doTransition}
      />
      <ArtifactDialog
        open={showArtifact}
        onClose={() => setShowArtifact(false)}
        onSave={addArtifact}
      />
      <EditWorkItemDialog
        open={showEdit}
        projectKey={projectKey}
        item={item}
        parentOption={parentOption}
        onClose={() => setShowEdit(false)}
        onSaved={() => {
          void refresh();
        }}
      />
      <ImagePreviewDialog
        open={preview !== null}
        src={preview?.src ?? null}
        alt={preview?.alt}
        onClose={() => setPreview(null)}
      />
      <ConfirmDialog
        open={commentToDelete !== null}
        title="删除评论"
        confirmLabel="删除"
        testId="item-comment-delete-dialog"
        onClose={() => setCommentToDelete(null)}
        onConfirm={() => void deleteComment()}
      >
        删除后不可恢复，确认删除这条评论？
      </ConfirmDialog>
    </aside>
  );
}
