import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import Button from "@atlaskit/button/default/button";
import IconButton from "@atlaskit/button/icon/button";
import { DatePicker } from "@atlaskit/datetime-picker";
import Heading from "@atlaskit/heading";
import CrossIcon from "@atlaskit/icon/core/cross";
import Link from "@atlaskit/link";
import Lozenge from "@atlaskit/lozenge";
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
import TextButton from "../../components/TextButton";
import TypeKindIcon from "../../components/TypeKindIcon";
import WorkItemPicker, {
  toWorkItemOption,
  type WorkItemOption,
} from "../../components/WorkItemPicker";
import EditWorkItemDialog from "../../workitems/EditWorkItemDialog";
import { TASK_TYPE_OPTIONS } from "../../workitems/constants";
import { PRIORITY_OPTIONS, priorityColor, priorityOption } from "../../workitems/priority";
import StatusLozenge from "../../workitems/status";
import { api, errorCause } from "../../lib/api";
import { artifactKindLabel, kindLabel } from "../../lib/labels";
import { useCurrentUser } from "../../lib/auth";
import { formatDate, formatSize } from "../../lib/format";
import { useNotify } from "../../lib/flags";
import { flattenMembers } from "../../lib/members";
import { portalMenuProps } from "../../lib/portalMenu";
import type {
  ActiveStep,
  Artifact,
  Attachment,
  Comment,
  OrgUser,
  ProjectMemberRow,
  WorkItem,
  WorkItemDetailMeta,
  WorkItemPermissions,
  WorkflowDto,
  WorkflowFields,
  WorkflowStepDef,
} from "../../types";
import ActiveStepCard from "./ActiveStepCard";
import ArtifactDialog from "./ArtifactDialog";
import ChildrenSection from "./ChildrenSection";
import HistorySection from "./HistorySection";
import StepExecuteDialog from "./StepExecuteDialog";
import StepRejectDialog from "./StepRejectDialog";
import StepStartDialog from "./StepStartDialog";
import {
  InlineMarkdownField,
  InlineMemberField,
  InlineTextField,
  type MemberOption,
} from "./InlineFields";
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
  steps: WorkflowStepDef[];
  activeStep: ActiveStep | null;
  permissions: WorkItemPermissions;
  workflowFields: WorkflowFields;
  comments: Comment[];
  members: OrgUser[];
  attachments: Attachment[];
  artifacts: Artifact[];
}

interface PreviewImage {
  src: string;
  alt: string;
}

interface StepExecuteTarget {
  active?: ActiveStep;
  step?: WorkflowStepDef;
  name: string;
  noteRequired: boolean;
}

interface StepReassignTarget {
  active: ActiveStep;
  step: WorkflowStepDef;
}

const COMMENTS_PAGE = 50;
const EMPTY_FIELDS: WorkflowFields = {
  reviewer: false,
  review_content: false,
  custom: [],
};

function effectiveFields(workflow: WorkflowDto, item: WorkItem): WorkflowFields {
  const kind = workflow.kinds[item.kind];
  if (!kind) return EMPTY_FIELDS;
  const effective =
    item.kind === "task" && item.task_type
      ? kind.subtypes?.[item.task_type] ?? kind
      : kind;
  return effective.fields ?? EMPTY_FIELDS;
}

export default function ItemPanel({ projectKey, itemId, onClose, onOpenItem }: Props) {
  const notify = useNotify();
  const me = useCurrentUser();
  const [bundle, setBundle] = useState<DetailBundle | null>(null);
  const [loadError, setLoadError] = useState(false);

  const [showEdit, setShowEdit] = useState(false);
  const [stepStart, setStepStart] = useState<WorkflowStepDef | null>(null);
  const [stepExecute, setStepExecute] = useState<StepExecuteTarget | null>(null);
  const [stepReassign, setStepReassign] = useState<StepReassignTarget | null>(null);
  const [stepCancel, setStepCancel] = useState<ActiveStep | null>(null);
  const [stepReject, setStepReject] = useState<ActiveStep | null>(null);
  const [showArtifact, setShowArtifact] = useState(false);
  const [gateMessage, setGateMessage] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewImage | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [parentEditing, setParentEditing] = useState(false);
  const [commentToDelete, setCommentToDelete] = useState<Comment | null>(null);

  const [commenting, setCommenting] = useState(false);
  const [commentCancelConfirm, setCommentCancelConfirm] = useState(false);
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
  // Latest known row_version: inline edits can be saved back to back while a
  // refresh is still in flight, so read it from a ref instead of render state.
  const versionRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const detail = await api.get<WorkItem>(
        `/work-items/${encodeURIComponent(itemId)}`,
      );
      const meta = (detail.meta ?? {}) as WorkItemDetailMeta;
      const [cm, mm, am, artm, wf] = await Promise.all([
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
        api.get<WorkflowDto>("/workflow"),
      ]);
      setBundle({
        item: detail.data,
        parent: meta.parent ?? null,
        children: meta.children ?? [],
        allowed: meta.allowed_transitions ?? [],
        allowedParentKinds: meta.allowed_parent_kinds ?? [],
        allowedChildKinds: meta.allowed_child_kinds ?? [],
        steps: meta.available_steps ?? [],
        activeStep: meta.active_step ?? null,
        permissions: meta.permissions ?? {},
        workflowFields: effectiveFields(wf.data, detail.data),
        comments: cm.data,
        members: flattenMembers(mm.data),
        attachments: am.data,
        artifacts: artm.data,
      });
      versionRef.current = detail.data.row_version;
      setHasMoreComments(cm.data.length >= COMMENTS_PAGE);
      setLoadError(false);
    } catch {
      setLoadError(true);
    }
  }, [itemId, projectKey]);

  useEffect(() => {
    // Switching items reuses this panel; clear all per-item transient state so
    // a previous item's gate/step error or open dialog cannot leak across.
    versionRef.current = null;
    setBundle(null);
    setGateMessage(null);
    setStepStart(null);
    setStepExecute(null);
    setStepReassign(null);
    setStepCancel(null);
    setParentEditing(false);
    setShowEdit(false);
    setShowArtifact(false);
    setCommentToDelete(null);
    setPreview(null);
    setCommenting(false);
    setCommentCancelConfirm(false);
    setDraft("");
    setReplyTo(null);
    pendingIds.current = [];
    setPendingFiles([]);
    void load();
  }, [load]);

  const refresh = useCallback(async () => {
    await load();
    setRefreshKey((value) => value + 1);
  }, [load]);

  /**
   * Save one field at a time. Inline editors stay open when this returns
   * false, so a conflict/validation error never discards the user's draft.
   */
  const patchItem = useCallback(
    async (payload: Record<string, unknown>): Promise<boolean> => {
      const rowVersion = versionRef.current;
      if (rowVersion === null) return false;
      try {
        const res = await api.patch<WorkItem>(`/work-items/${itemId}`, {
          row_version: rowVersion,
          ...payload,
        });
        versionRef.current = res.data.row_version;
        await refresh();
        notify.success("保存成功");
        return true;
      } catch (e) {
        notify.error("保存失败", errorCause(e)?.message);
        await refresh();
        return false;
      }
    },
    [itemId, notify, refresh],
  );

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      if (
        showEdit ||
        showArtifact ||
        stepStart ||
        stepExecute ||
        stepReassign ||
        stepCancel ||
        stepReject ||
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
    stepCancel,
    stepExecute,
    stepReassign,
    stepReject,
    stepStart,
  ]);

  const reportGate = (e: unknown) => {
    const cause = errorCause(e);
    if (cause?.code === "WORKFLOW_GATE_BLOCKED") {
      const ids = ((cause.details?.blocking_children as unknown) as string[] | undefined)
        ?.filter(Boolean)
        .join(", ");
      const missing = (
        (cause.details?.missing_fields as unknown) as
          | { label?: string }[]
          | undefined
      )
        ?.map((field) => field.label)
        .filter(Boolean)
        .join("、");
      const extra = [ids && `阻塞: ${ids}`, missing && `缺少字段: ${missing}`]
        .filter(Boolean)
        .join("；");
      setGateMessage(extra ? `${cause.message}（${extra}）` : cause.message);
    } else {
      notify.error("操作失败", cause?.message);
    }
  };

  const openStep = (step: WorkflowStepDef) => {
    if (step.mode === "direct") {
      setStepExecute({ step, name: step.name, noteRequired: step.note === "required" });
    } else {
      setStepStart(step);
    }
  };

  const executeStep = async (noteMd: string, attachmentIds: string[]) => {
    if (!bundle || !stepExecute) return;
    try {
      if (stepExecute.active) {
        await api.post(`/work-item-steps/${stepExecute.active.id}/execute`, {
          note_md: noteMd,
          attachment_ids: attachmentIds,
        });
      } else if (stepExecute.step) {
        await api.post(`/work-items/${itemId}/steps/${stepExecute.step.key}`, {
          row_version: versionRef.current ?? bundle.item.row_version,
          note_md: noteMd,
          attachment_ids: attachmentIds,
        });
      }
      notify.success("步骤已执行");
      setGateMessage(null);
      setStepExecute(null);
      await refresh();
    } catch (e) {
      setStepExecute(null);
      reportGate(e);
    }
  };

  const startStep = async (executors: string[]) => {
    if (!bundle || !stepStart) return;
    try {
      await api.post(`/work-items/${itemId}/steps/${stepStart.key}`, {
        row_version: versionRef.current ?? bundle.item.row_version,
        executors,
      });
      notify.success(`已发起步骤「${stepStart.name}」`);
      setGateMessage(null);
      setStepStart(null);
      await refresh();
    } catch (e) {
      setStepStart(null);
      reportGate(e);
    }
  };

  const reassignStep = async (executors: string[]) => {
    if (!stepReassign) return;
    try {
      await api.post(`/work-item-steps/${stepReassign.active.id}/reassign`, {
        row_version: stepReassign.active.row_version,
        executors,
      });
      notify.success("执行人已更新");
      setGateMessage(null);
      setStepReassign(null);
      await refresh();
    } catch (e) {
      setStepReassign(null);
      reportGate(e);
    }
  };

  const cancelStep = async () => {
    if (!stepCancel) return;
    const target = stepCancel;
    setStepCancel(null);
    try {
      await api.post(`/work-item-steps/${target.id}/cancel`, {
        row_version: target.row_version,
      });
      notify.success("步骤已取消");
      setGateMessage(null);
      await refresh();
    } catch (e) {
      reportGate(e);
    }
  };

  const rejectStep = async (reason: string) => {
    if (!stepReject) return;
    try {
      await api.post(`/work-item-steps/${stepReject.id}/reject`, {
        row_version: stepReject.row_version,
        reason,
      });
      notify.success("步骤已拒绝");
      setGateMessage(null);
      setStepReject(null);
      await refresh();
    } catch (e) {
      reportGate(e);
    }
  };

  const retryStep = async (active: ActiveStep) => {    try {
      await api.post(`/work-item-steps/${active.id}/retry`, {
        row_version: active.row_version,
      });
      setGateMessage(null);
      await refresh();
    } catch (e) {
      reportGate(e);
    }
  };

  const assignMember = async (ids: string[]): Promise<boolean> => {
    const memberId = ids[0];
    if (!memberId) return false;
    if (bundle?.item.assignee?.id === memberId) return true;
    try {
      await api.post(`/work-items/${itemId}/assign`, { member: memberId });
      await refresh();
      notify.success("保存成功");
      return true;
    } catch (e) {
      notify.error("指派失败", errorCause(e)?.message);
      await refresh();
      return false;
    }
  };

  const changePriority = async (priority: number) => {
    if (!bundle) return;
    try {
      await api.patch(`/work-items/${itemId}`, {
        row_version: versionRef.current ?? bundle.item.row_version,
        priority,
      });
      await refresh();
      notify.success("保存成功");
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
        row_version: versionRef.current ?? bundle.item.row_version,
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

  const discardComment = () => {
    setDraft("");
    setReplyTo(null);
    pendingIds.current = [];
    setPendingFiles([]);
    setCommenting(false);
    setCommentCancelConfirm(false);
  };

  const requestCancelComment = () => {
    if (draft.trim() || pendingIds.current.length > 0) {
      setCommentCancelConfirm(true);
      return;
    }
    discardComment();
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
      setCommenting(false);
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

  // Hooks must run unconditionally: compute this before the loading/error
  // early returns below, otherwise React sees a different hook count once
  // the detail bundle arrives (error #310).
  const parentOption = useMemo(
    () => (bundle?.parent ? toWorkItemOption(bundle.parent) : null),
    [bundle?.parent],
  );

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
    steps,
    activeStep,
    permissions,
    workflowFields,
    comments,
    members,
    attachments,
    artifacts,
  } = bundle;
  const memberOptions: MemberOption[] = members.map((m) => ({
    label: `${m.name}${m.type === "agent" ? "（agent）" : ""}`,
    value: m.id,
    name: m.name,
  }));
  const currentPriority = priorityOption(item.priority).value;
  const identityId = me?.identity.id ?? me?.user.id ?? null;
  const projectRoles =
    me?.projects.find((project) => project.key === projectKey)?.roles ?? [];
  const canModerate =
    Boolean(me?.org_roles.includes("org_owner")) ||
    projectRoles.includes("project_owner") ||
    projectRoles.includes("manager");
  const canEdit = Boolean(permissions.can_edit);
  const canAssign = Boolean(permissions.can_assign);
  // Epic has no kind extension table; empty field maps render no editor either.
  const hasKindFields =
    item.kind !== "epic" && Object.keys(item.fields ?? {}).length > 0;
  const taskTypeLabel =
    TASK_TYPE_OPTIONS.find((option) => option.value === (item.task_type ?? "other"))?.label ??
    item.task_type ??
    "其他";
  // Gate-required fields for the steps reachable from this status (and the
  // active step) drive the red asterisk next to field labels. Plain compute:
  // this sits after the early returns, so it must not be a hook.
  const requiredFieldKeys = new Set<string>();
  {
    const collect = (gates: Record<string, unknown> | undefined) => {
      const required = gates?.required_fields;
      if (Array.isArray(required)) {
        for (const key of required) requiredFieldKeys.add(String(key));
      }
    };
    for (const step of steps) collect(step.gates);
    collect(
      (activeStep?.config as { gates?: Record<string, unknown> } | undefined)?.gates,
    );
  }

  // The composer belongs to the left column's bottom edge, not the drawer
  // footer (which would span the fields column too).
  const commentBar = (
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
        autoFocus
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
        <TextButton
          data-testid="item-comment-cancel"
          onClick={requestCancelComment}
        >
          取消
        </TextButton>
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
        {canEdit && (
          <TextButton data-testid="item-panel-edit" onClick={() => setShowEdit(true)}>
            完整编辑
          </TextButton>
        )}
        <TextButton data-testid="item-panel-copy-link" onClick={() => void copyLink()}>
          复制链接
        </TextButton>
      </header>

      <div className="rdm-item-body">
        <section className="rdm-item-content" data-testid="item-panel-content">
          <div className="rdm-item-content-scroll">
            <div className="rdm-item-title-row">
              {item.kind === "task" && (
                <span className="rdm-item-task-type" data-testid="item-task-type">
                  <Lozenge appearance="default">{taskTypeLabel}</Lozenge>
                </span>
              )}
              <div className="rdm-item-title-main">
                <InlineTextField
                  testId="item-panel-title-field"
                  value={item.title}
                  canEdit={canEdit}
                  editLabel="编辑标题"
                  validate={(next) => (next.trim() ? undefined : "标题不能为空")}
                  readClassName="rdm-inline-title"
                  renderView={(value) => (
                    <Heading size="medium" as="h2" testId="item-panel-title">
                      {value}
                    </Heading>
                  )}
                  onSave={(next) => patchItem({ title: next.trim() })}
                />
              </div>
            </div>

            <section className="rdm-item-section" data-testid="item-section-base">
              <InlineMarkdownField
                testId="item-panel-description"
                label="描述"
                required={requiredFieldKeys.has("description_md")}
                value={item.description_md}
                canEdit={canEdit}
                projectKey={projectKey}
                emptyText="未填写描述"
                placeholder="写点什么（支持 Markdown，可直接粘贴图片）"
                minimumRows={6}
                editLabel="编辑描述"
                readClassName="rdm-inline-read-desc"
                onImageClick={setPreview}
                onSave={(next) => patchItem({ description_md: next.trim() ? next : null })}
              />

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
                  <div
                    key={a.id}
                    className="rdm-item-att"
                    data-testid={`item-attachment-${a.id}`}
                  >
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
                  <div
                    key={art.id}
                    className="rdm-item-att"
                    data-testid={`item-artifact-${art.id}`}
                  >
                    <Link href={art.url} target="_blank" testId={`item-artifact-link-${art.id}`}>
                      {art.label}
                    </Link>
                    <Text size="small" color="color.text.subtlest">
                      {artifactKindLabel(art.kind)}
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
            </section>

            <hr className="rdm-item-divider" />

            {hasKindFields && (
              <>
                <section className="rdm-item-section" data-testid="item-section-kind">
                  <div data-testid="item-panel-fields-json">
                    <WorkItemFieldsView
                      item={item}
                      projectKey={projectKey}
                      canEdit={canEdit}
                      requiredFields={requiredFieldKeys}
                      onPatch={patchItem}
                      onOpenItem={onOpenItem}
                      onImageClick={setPreview}
                    />
                  </div>
                </section>
                <hr className="rdm-item-divider" />
              </>
            )}

            <section className="rdm-item-section" data-testid="item-section-children">
              <ChildrenSection
                projectKey={projectKey}
                parent={item}
                children={children}
                allowedKinds={allowedChildKinds}
                onOpen={onOpenItem}
                onChanged={() => void refresh()}
              />
            </section>

            <hr className="rdm-item-divider" />

            <section className="rdm-item-section" data-testid="item-section-comments">
              <div className="rdm-item-section-head">
                <div className="rdm-item-section-label">评论（{comments.length}）</div>
                {!commenting && (
                  <TextButton
                    data-testid="item-comment-add"
                    onClick={() => setCommenting(true)}
                  >
                    添加评论
                  </TextButton>
                )}
              </div>
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
                        onClick={() => {
                          setReplyTo(c);
                          setCommenting(true);
                        }}
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
          </div>
          {commenting && commentBar}
        </section>

        <section className="rdm-item-fields" data-testid="item-panel-fields">
          {gateMessage && (
            <Box paddingBlockEnd="space.150">
              <SectionMessage appearance="warning" onDismiss={() => setGateMessage(null)}>
                {gateMessage}
              </SectionMessage>
            </Box>
          )}

          {allowedParentKinds.length > 0 && (
            <>
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
                    无父项
                  </Text>
                )}
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
                  ) : permissions.can_edit ? (
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
                  ) : null}
                </Box>
              </div>
              <hr className="rdm-item-divider" />
            </>
          )}

          <div className="rdm-item-field" data-testid="item-field-priority">
            <div className="rdm-item-section-label">优先级</div>
            <div className="rdm-priority-row">
              <div className="rdm-priority-select" data-testid="priority-select">
                <Select
                  {...portalMenuProps}
                  options={PRIORITY_OPTIONS}
                  value={
                    PRIORITY_OPTIONS.find((o) => o.value === currentPriority) ?? null
                  }
                  isDisabled={!permissions.can_edit}
                  onChange={(opt) =>
                    opt && void changePriority((opt as { value: number }).value)
                  }
                  isClearable={false}
                />
              </div>
              <span
                className="rdm-priority-swatch"
                data-testid="priority-swatch"
                data-priority={item.priority}
                style={{ backgroundColor: priorityColor(item.priority) }}
              />
            </div>
          </div>
          <hr className="rdm-item-divider" />

          <div className="rdm-item-field" data-testid="item-field-planned-dates">
            <div className="rdm-item-section-label">计划日期</div>
            <Stack space="space.100">
              <div className="rdm-planned-date-row">
                <span className="rdm-planned-date-label">开始</span>
                <div className="rdm-planned-date-input">
                  <DatePicker
                    value={item.planned_start_date ?? ""}
                    placeholder="未设置"
                    isDisabled={!canEdit}
                    testId="item-planned-start"
                    onChange={(value) =>
                      void patchItem({ planned_start_date: value || null })
                    }
                  />
                </div>
              </div>
              <div className="rdm-planned-date-row">
                <span className="rdm-planned-date-label">完成</span>
                <div className="rdm-planned-date-input">
                  <DatePicker
                    value={item.planned_end_date ?? ""}
                    placeholder="未设置"
                    isDisabled={!canEdit}
                    testId="item-planned-end"
                    onChange={(value) =>
                      void patchItem({ planned_end_date: value || null })
                    }
                  />
                </div>
              </div>
            </Stack>
          </div>
          <hr className="rdm-item-divider" />

          <div className="rdm-item-field" data-testid="item-field-status">
            <div className="rdm-item-section-label">状态</div>
            <StatusLozenge status={item.status} />
          </div>

          <div className="rdm-item-field" data-testid="item-field-steps">
            <div className="rdm-item-section-label">可执行步骤</div>
            {activeStep && (
              <Box paddingBlockEnd="space.100">
                <ActiveStepCard
                  step={activeStep}
                  onExecute={() =>
                    setStepExecute({
                      active: activeStep,
                      name: activeStep.name,
                      noteRequired: activeStep.config.note === "required",
                    })
                  }
                  onCancel={() => setStepCancel(activeStep)}
                  onReject={() => setStepReject(activeStep)}
                  onRetry={() => void retryStep(activeStep)}
                  onReassign={() => {
                    const definition = steps.find((step) => step.key === activeStep.key);
                    if (definition) {
                      setStepReassign({ active: activeStep, step: definition });
                    }
                  }}
                  onOpenItem={onOpenItem}
                />
              </Box>
            )}
            {steps.length === 0 && !activeStep && (
              <Text size="small" color="color.text.subtlest">
                当前状态没有可执行步骤
              </Text>
            )}
            <Stack space="space.100">
              {steps
                .filter((step) => step.key !== activeStep?.key)
                .map((step) => {
                  const enabled = step.can_start || step.can_execute;
                  return (
                    <Button
                      key={step.key}
                      spacing="compact"
                      isDisabled={!enabled}
                      testId={`item-step-${step.key}`}
                      onClick={() => openStep(step)}
                    >
                      {step.name}
                      {step.mode === "task"
                        ? "（子任务）"
                        : step.mode === "approval"
                          ? "（多人）"
                          : ""}
                    </Button>
                  );
                })}
            </Stack>
            {steps.some(
              (step) => !step.can_start && !step.can_execute && step.blocked_reasons.length > 0,
            ) && (
              <Box paddingBlockStart="space.050">
                <Text size="small" color="color.text.subtlest">
                  {steps
                    .filter((step) => !step.can_start && !step.can_execute)
                    .flatMap((step) => step.blocked_reasons)
                    .join("；")}
                </Text>
              </Box>
            )}
          </div>
          <hr className="rdm-item-divider" />

          <div className="rdm-item-field" data-testid="item-field-assignee">
            <InlineMemberField
              testId="item-assignee"
              label="负责人"
              canEdit={canAssign}
              multiple={false}
              ids={item.assignee ? [item.assignee.id] : []}
              options={memberOptions}
              emptyText="未指派"
              placeholder="选择负责人"
              editLabel="编辑负责人"
              onSave={assignMember}
            />
          </div>

          <div className="rdm-item-field" data-testid="item-field-participants">
            <InlineMemberField
              testId="item-participants"
              label="参与人"
              canEdit={canEdit}
              multiple
              ids={(item.participants ?? []).map((participant) => participant.id)}
              options={memberOptions}
              emptyText="未设置"
              placeholder="选择参与人"
              editLabel="编辑参与人"
              onSave={(next) => patchItem({ participants: next })}
            />
          </div>
          <hr className="rdm-item-divider" />

          {workflowFields.reviewer && (
            <div className="rdm-item-field" data-testid="item-field-reviewer">
              <InlineMemberField
                testId="item-reviewer"
                label="评审人"
                required={requiredFieldKeys.has("reviewer")}
                canEdit={canEdit}
                multiple
                ids={(item.reviewer ?? []).map((reviewer) => reviewer.id)}
                options={memberOptions}
                emptyText="未设置"
                placeholder="选择评审人"
                editLabel="编辑评审人"
                onSave={(next) => patchItem({ reviewer: next })}
              />
            </div>
          )}

          {workflowFields.review_content && (
            <div className="rdm-item-field" data-testid="item-field-review-content">
              <InlineMarkdownField
                testId="item-review-content"
                label="评审意见"
                required={requiredFieldKeys.has("review_content")}
                value={item.review_content_md}
                canEdit={canEdit}
                projectKey={projectKey}
                emptyText="未填写"
                placeholder="填写评审意见（支持 Markdown）"
                minimumRows={3}
                editLabel="编辑评审意见"
                onImageClick={setPreview}
                onSave={(next) =>
                  patchItem({ review_content_md: next.trim() ? next : null })
                }
              />
            </div>
          )}

          {workflowFields.custom.length > 0 && (
            <div data-testid="item-field-custom">
              {workflowFields.custom.map((field) => {
                const raw = item.custom_fields?.[field.key];
                // Send every declared key (never stale ones): the backend
                // rejects custom_fields keys the current workflow no longer
                // declares, and PATCH replaces the whole map.
                const save = (value: unknown) => {
                  const next: Record<string, unknown> = {};
                  for (const def of workflowFields.custom) {
                    next[def.key] =
                      def.key === field.key ? value : item.custom_fields?.[def.key] ?? null;
                  }
                  return patchItem({ custom_fields: next });
                };
                if (field.type === "text") {
                  return (
                    <div className="rdm-item-field" key={field.key}>
                      <InlineMarkdownField
                        testId={`item-custom-${field.key}`}
                        label={field.label}
                        required={requiredFieldKeys.has(field.key)}
                        value={typeof raw === "string" ? raw : ""}
                        canEdit={canEdit}
                        projectKey={projectKey}
                        minimumRows={2}
                        editLabel={`编辑${field.label}`}
                        onImageClick={setPreview}
                        onSave={(next) => save(next.trim() ? next : null)}
                      />
                    </div>
                  );
                }
                if (field.type === "number") {
                  return (
                    <div className="rdm-item-field" key={field.key}>
                      <InlineTextField
                        testId={`item-custom-${field.key}`}
                        label={field.label}
                        required={requiredFieldKeys.has(field.key)}
                        value={raw === null || raw === undefined ? "" : String(raw)}
                        canEdit={canEdit}
                        inputType="number"
                        editLabel={`编辑${field.label}`}
                        onSave={(next) => save(next.trim() === "" ? null : Number(next))}
                      />
                    </div>
                  );
                }
                const ids = Array.isArray(raw)
                  ? raw.map(String)
                  : raw
                    ? [String(raw)]
                    : [];
                return (
                  <div className="rdm-item-field" key={field.key}>
                    <InlineMemberField
                      testId={`item-custom-${field.key}`}
                      label={field.label}
                      required={requiredFieldKeys.has(field.key)}
                      canEdit={canEdit}
                      multiple={field.multiple}
                      ids={ids}
                      options={memberOptions}
                      emptyText="未选择"
                      placeholder="选择成员"
                      editLabel={`编辑${field.label}`}
                      onSave={(next) => save(next)}
                    />
                  </div>
                );
              })}
            </div>
          )}

          {(workflowFields.reviewer ||
            workflowFields.review_content ||
            workflowFields.custom.length > 0) && <hr className="rdm-item-divider" />}

          <div data-testid="item-section-metadata">
            <div className="rdm-item-field">
              <div className="rdm-item-section-label">类型 / 版本</div>
              <Text size="small" color="color.text.subtlest">
                {kindLabel(item.kind)} · v{item.row_version}
              </Text>
            </div>
            <div className="rdm-item-field">
              <div className="rdm-item-section-label">创建时间</div>
              <Text size="small" color="color.text.subtlest">
                {formatDate(item.created_at)}
              </Text>
            </div>

            <HistorySection itemId={item.id} refreshKey={refreshKey} />
          </div>
        </section>
      </div>

      <StepStartDialog
        open={stepStart !== null}
        step={stepStart}
        mode="start"
        onClose={() => setStepStart(null)}
        onConfirm={startStep}
      />
      <StepStartDialog
        open={stepReassign !== null}
        step={stepReassign?.step ?? null}
        mode="reassign"
        onClose={() => setStepReassign(null)}
        onConfirm={reassignStep}
      />
      <StepExecuteDialog
        open={stepExecute !== null}
        projectKey={projectKey}
        itemId={itemId}
        stepName={stepExecute?.name ?? ""}
        noteRequired={stepExecute?.noteRequired ?? false}
        onClose={() => setStepExecute(null)}
        onConfirm={executeStep}
        onImageClick={setPreview}
      />
      <StepRejectDialog
        open={stepReject !== null}
        stepName={stepReject?.name ?? ""}
        onClose={() => setStepReject(null)}
        onConfirm={rejectStep}
      />
      <ConfirmDialog
        open={stepCancel !== null}
        title="取消步骤"
        confirmLabel="取消步骤"
        testId="step-cancel-dialog"
        onClose={() => setStepCancel(null)}
        onConfirm={() => void cancelStep()}
      >
        取消后已完成的执行记录会保留，未执行的执行人不再需要提交。确认取消？
      </ConfirmDialog>
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
      <ConfirmDialog
        open={commentCancelConfirm}
        title="放弃评论"
        confirmLabel="放弃"
        testId="comment-cancel-dialog"
        danger
        onClose={() => setCommentCancelConfirm(false)}
        onConfirm={discardComment}
      >
        当前评论内容尚未提交，确认放弃？
      </ConfirmDialog>
    </aside>
  );
}
