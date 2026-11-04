import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";

import Button from "@atlaskit/button/default/button";
import IconButton from "@atlaskit/button/icon/button";
import { cssMap } from "@atlaskit/css";
import { DatePicker } from "@atlaskit/datetime-picker";
import Heading from "@atlaskit/heading";
import ArrowLeftIcon from "@atlaskit/icon/core/arrow-left";
import CopyIcon from "@atlaskit/icon/core/copy";
import CrossIcon from "@atlaskit/icon/core/cross";
import Link from "@atlaskit/link";
import Lozenge from "@atlaskit/lozenge";
import Select from "@atlaskit/select";
import SectionMessage from "@atlaskit/section-message";
import Spinner from "@atlaskit/spinner";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";
import { token } from "@atlaskit/tokens";
import { useTranslation } from "react-i18next";

import ConfirmDialog from "../../components/ConfirmDialog";
import AttachmentPreviewDialog from "../../components/AttachmentPreviewDialog";
import ImagePreviewDialog from "../../components/ImagePreviewDialog";
import MarkdownEditor from "../../components/MarkdownEditor";
import MarkdownText from "../../components/MarkdownText";
import PersonCell from "../../components/PersonCell";
import TruncatedText from "../../components/TruncatedText";
import TextButton from "../../components/TextButton";
import TypeKindIcon from "../../components/TypeKindIcon";
import WorkItemPicker, {
  toWorkItemOption,
  type WorkItemOption,
} from "../../components/WorkItemPicker";
import EditWorkItemDialog from "../../workitems/EditWorkItemDialog";
import { SPRINT_ITEM_KINDS, taskTypeOptions } from "../../workitems/constants";
import { priorityOptions, priorityColor, priorityOption } from "../../workitems/priority";
import StatusLozenge from "../../workitems/status";
import { api, errorCause } from "../../lib/api";
import { artifactKindLabel, kindLabel, statusLabel } from "../../lib/labels";
import { i18n } from "../../i18n";
import { useCurrentUser } from "../../lib/auth";
import { CONSUMED, KEEP, drain } from "../../lib/eventBus";
import {
  WORK_ITEM_UPDATED,
  publishWorkItemUpdated,
  type WorkItemUpdatedEvent,
} from "../../lib/workItemEvents";
import { formatDate, formatSize } from "../../lib/format";
import { useNotify } from "../../lib/flags";
import { useEventInstanceId } from "../../hooks/useEventBus";
import { useWorkItemUpdatedSubscription } from "../../hooks/useWorkItemEvents";
import { flattenMembers, loadProjectMembers } from "../../lib/members";
import { portalMenuProps } from "../../lib/portalMenu";
import { userLabel } from "../../lib/users";
import type {
  ActiveStep,
  Artifact,
  Attachment,
  Comment,
  OrgUser,
  Sprint,
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

const styles = cssMap({
  padded400: { padding: "var(--ds-space-400)" },
  paddingBlockStart200: { paddingBlockStart: "var(--ds-space-200)" },
  paddingBlockStart100: { paddingBlockStart: "var(--ds-space-100)" },
  paddingBlockStart050: { paddingBlockStart: "var(--ds-space-050)" },
  paddingBlockEnd150: { paddingBlockEnd: "var(--ds-space-150)" },
  paddingBlockEnd100: { paddingBlockEnd: "var(--ds-space-100)" },
});

interface Props {
  projectKey: string;
  itemId: string;
  onClose: () => void;
  onOpenItem: (id: string) => void;
  /** Pop the top drawer layer; when set the close icon becomes a back arrow. */
  onBack?: () => void;
  /** A lower stack layer kept mounted but not visible (RDM-136). */
  covered?: boolean;
}

interface DetailBundle {
  item: WorkItem;
  parent: WorkItem | null;
  ancestors: WorkItem[];
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
  sprint: Sprint | null;
  sprints: Sprint[];
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

export default function ItemPanel({
  projectKey,
  itemId,
  onClose,
  onOpenItem,
  onBack,
  covered = false,
}: Props) {
  const { t } = useTranslation("item");
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
  const [previewAttachment, setPreviewAttachment] = useState<Attachment | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [parentEditing, setParentEditing] = useState(false);
  const [sprintEditing, setSprintEditing] = useState(false);
  const [savingSprint, setSavingSprint] = useState(false);
  const [commentToDelete, setCommentToDelete] = useState<Comment | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [editingComment, setEditingComment] = useState<{ id: string; body: string } | null>(
    null,
  );

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
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [hasMoreComments, setHasMoreComments] = useState(false);
  const [loadingMoreComments, setLoadingMoreComments] = useState(false);
  // Latest known row_version: inline edits can be saved back to back while a
  // refresh is still in flight, so read it from a ref instead of render state.
  const versionRef = useRef<number | null>(null);

  // Cross-component refresh (RDM-150): this panel is a bus subscriber like the
  // list behind it. Its queue survives while a nested layer covers it.
  const instanceId = useEventInstanceId();
  const bundleRef = useRef<DetailBundle | null>(bundle);
  bundleRef.current = bundle;
  const coveredRef = useRef(covered);
  coveredRef.current = covered;

  const load = useCallback(async () => {
    try {
      const detail = await api.get<WorkItem>(
        `/work-items/${encodeURIComponent(itemId)}`,
      );
      const meta = (detail.meta ?? {}) as WorkItemDetailMeta;
      const [cm, mm, am, artm, wf, sprintInfo, sprintList] = await Promise.all([
        api.get<Comment[]>(
          `/work-items/${itemId}/comments?limit=${COMMENTS_PAGE}&offset=0`,
        ),
        loadProjectMembers(projectKey),
        api.get<Attachment[]>(
          `/projects/${projectKey}/attachments?owner_type=work_item&owner_ref=${encodeURIComponent(itemId)}`,
        ),
        api.get<Artifact[]>(
          `/projects/${projectKey}/artifacts?owner_type=work_item&owner_ref=${encodeURIComponent(itemId)}`,
        ),
        api.get<WorkflowDto>(`/workflow?project=${encodeURIComponent(projectKey)}`),
        api.get<{ sprint: Sprint | null }>(`/work-items/${itemId}/sprint`),
        api.get<Sprint[]>(`/projects/${projectKey}/sprints`),
      ]);
      setBundle({
        item: detail.data,
        parent: meta.parent ?? null,
        ancestors: meta.ancestors ?? [],
        children: meta.children ?? [],
        allowed: meta.allowed_transitions ?? [],
        allowedParentKinds: meta.allowed_parent_kinds ?? [],
        allowedChildKinds: meta.allowed_child_kinds ?? [],
        steps: meta.available_steps ?? [],
        activeStep: meta.active_step ?? null,
        permissions: meta.permissions ?? {},
        workflowFields: effectiveFields(wf.data, detail.data),
        comments: cm.data,
        members: flattenMembers(mm),
        attachments: am.data,
        artifacts: artm.data,
        sprint: sprintInfo.data.sprint,
        sprints: sprintList.data,
      });
      versionRef.current = detail.data.row_version;
      setHasMoreComments(cm.data.length >= COMMENTS_PAGE);
      setLoadError(false);
    } catch {
      setLoadError(true);
    }
  }, [itemId, projectKey, i18n.language]);

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
    setSprintEditing(false);
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

  // Publish a change so covered drawers and the list behind the stack can
  // revalidate on demand instead of every open/close.
  const publishChange = useCallback(
    (
      action: WorkItemUpdatedEvent["action"],
      overrides: Partial<
        Pick<
          WorkItemUpdatedEvent,
          "workItemId" | "displayId" | "parentId" | "previousParentId"
        >
      > = {},
    ) => {
      publishWorkItemUpdated({
        projectKey,
        workItemId: overrides.workItemId ?? itemId,
        displayId: overrides.displayId ?? bundleRef.current?.item.display_id,
        parentId:
          "parentId" in overrides
            ? overrides.parentId
            : (bundleRef.current?.parent?.id ?? null),
        previousParentId: overrides.previousParentId,
        action,
        source: instanceId,
      });
    },
    [instanceId, itemId, projectKey],
  );

  /** Child/parent/ancestor changes are the only ones this panel renders. */
  const isRelatedEvent = useCallback(
    (event: WorkItemUpdatedEvent) => {
      const current = bundleRef.current;
      if (!current) return false;
      if (event.workItemId === itemId) return true;
      if (event.workItemId === current.parent?.id) return true;
      if (event.parentId === itemId || event.previousParentId === itemId) return true;
      return current.ancestors.some((node) => node.id === event.workItemId);
    },
    [itemId],
  );

  // Coalesce a burst of events into one reload.
  const refreshTimer = useRef<number | null>(null);
  const scheduleRefresh = useCallback(() => {
    if (refreshTimer.current !== null) return;
    refreshTimer.current = window.setTimeout(() => {
      refreshTimer.current = null;
      void refresh();
    }, 0);
  }, [refresh]);
  useEffect(
    () => () => {
      if (refreshTimer.current !== null) window.clearTimeout(refreshTimer.current);
    },
    [],
  );

  useWorkItemUpdatedSubscription(instanceId, (event) => {
    // The panel that performed the mutation already refreshed itself.
    if (event.source === instanceId) return CONSUMED;
    // Covered layers cannot render the change yet; keep the event queued.
    if (coveredRef.current) return KEEP;
    if (isRelatedEvent(event)) scheduleRefresh();
    return CONSUMED;
  });

  // A covered layer was left mounted while the user worked on top of it.
  // Batch-process whatever it kept, then revalidate only when relevant.
  const wasCovered = useRef(covered);
  useEffect(() => {
    if (wasCovered.current && !covered) {
      const queued = drain(instanceId, WORK_ITEM_UPDATED) as WorkItemUpdatedEvent[];
      if (
        queued.some(
          (event) => event.source !== instanceId && isRelatedEvent(event),
        )
      ) {
        void refresh();
      }
    }
    wasCovered.current = covered;
  }, [covered, instanceId, isRelatedEvent, refresh]);

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
        publishChange("updated");
        await refresh();
        notify.success(t("panel.saveSuccess"));
        return true;
      } catch (e) {
        notify.error(t("panel.saveFailed"), errorCause(e)?.message);
        await refresh();
        return false;
      }
    },
    [itemId, notify, publishChange, refresh],
  );

  useEffect(() => {
    // Covered layers stay mounted but must not react to Escape: the visible
    // top layer owns the key and only pops itself (RDM-136 feedback).
    if (covered) return;
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
      if (onBack) onBack();
      else onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    commentToDelete,
    covered,
    onBack,
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
        .join(t("listSeparator"));
      const extra = [
        ids && t("panel.gateBlocked", { ids }),
        missing && t("panel.gateMissing", { missing }),
      ]
        .filter(Boolean)
        .join(t("panel.gateSeparator"));
      setGateMessage(
        extra ? t("panel.gateWrap", { message: cause.message, extra }) : cause.message,
      );
    } else {
      notify.error(t("panel.actionFailed"), cause?.message);
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
      notify.success(t("panel.stepExecuted"));
      setGateMessage(null);
      setStepExecute(null);
      publishChange("updated");
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
      notify.success(t("panel.stepStarted", { name: stepStart.name }));
      setGateMessage(null);
      setStepStart(null);
      publishChange("updated");
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
      notify.success(t("panel.executorsUpdated"));
      setGateMessage(null);
      setStepReassign(null);
      publishChange("updated");
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
      notify.success(t("panel.stepCancelled"));
      setGateMessage(null);
      publishChange("updated");
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
      notify.success(t("panel.stepRejected"));
      setGateMessage(null);
      setStepReject(null);
      publishChange("updated");
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
      publishChange("updated");
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
      publishChange("updated");
      await refresh();
      notify.success(t("panel.saveSuccess"));
      return true;
    } catch (e) {
      notify.error(t("panel.assignFailed"), errorCause(e)?.message);
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
      publishChange("updated");
      await refresh();
      notify.success(t("panel.saveSuccess"));
    } catch (e) {
      notify.error(t("panel.prioritySaveFailed"), errorCause(e)?.message);
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
      // Wake both the old and the new parent drawer.
      publishChange("updated", {
        parentId: option?.id ?? null,
        previousParentId: bundle.parent?.id ?? null,
      });
      notify.success(
        option
          ? t("panel.reparented", { id: option.display_id })
          : t("panel.parentCleared"),
      );
      setParentEditing(false);
      await refresh();
    } catch (e) {
      notify.error(t("panel.reparentFailed"), errorCause(e)?.message);
    }
  };

  const uploadFiles = async (files: FileList | null, attachToComment: boolean) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    setUploadProgress(0);
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("file", file);
        form.append("owner_type", "work_item");
        form.append("owner_ref", itemId);
        const res = await api.uploadWithProgress<Attachment>(
          `/projects/${projectKey}/attachments`,
          form,
          setUploadProgress,
        );
        setUploadProgress(null);
        if (attachToComment) {
          pendingIds.current.push(res.data.id);
          setPendingFiles((p) => [...p, { name: file.name, id: res.data.id }]);
        } else {
          setBundle((b) => (b ? { ...b, attachments: [...b.attachments, res.data] } : b));
        }
      }
      if (attachToComment) notify.success(t("panel.attachmentsUploaded"));
    } catch (e) {
      notify.error(t("panel.uploadFailed"), errorCause(e)?.message);
    } finally {
      setUploading(false);
      setUploadProgress(null);
    }
  };

  const removeAttachment = async (id: string) => {
    try {
      await api.del(`/attachments/${id}`);
      setBundle((b) =>
        b ? { ...b, attachments: b.attachments.filter((a) => a.id !== id) } : b,
      );
    } catch (e) {
      notify.error(t("panel.deleteFailed"), errorCause(e)?.message);
    }
  };

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      notify.success(t("panel.linkCopied"));
    } catch {
      notify.error(t("panel.copyFailed"), t("panel.clipboardDenied"));
    }
  };

  const copyDisplayId = async (displayId: string) => {
    try {
      await navigator.clipboard.writeText(displayId);
      notify.success(t("panel.displayIdCopied", { id: displayId }));
    } catch {
      notify.error(t("panel.copyFailed"), t("panel.clipboardDenied"));
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
      notify.error(t("panel.commentsLoadFailed"), errorCause(e)?.message);
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
      notify.error(t("panel.deleteFailed"), errorCause(e)?.message);
    }
  };

  // Allocation is exclusive (§16.38): moving means leave the old one first,
  // then join the new one. A failed add leaves the item outside a sprint.
  const changeSprint = async (sprintId: string | null) => {
    if (!bundle || savingSprint || bundle.sprint?.id === sprintId) return;
    setSavingSprint(true);
    try {
      if (bundle.sprint) {
        await api.del(
          `/sprints/${bundle.sprint.id}/items/${encodeURIComponent(bundle.item.display_id)}`,
        );
      }
      if (sprintId) {
        await api.post(`/sprints/${sprintId}/items`, { items: [bundle.item.display_id] });
      }
      publishChange("updated");
      setSprintEditing(false);
      await refresh();
      notify.success(t("panel.sprintSaved"));
    } catch (e) {
      notify.error(t("panel.sprintSaveFailed"), errorCause(e)?.message);
      await refresh();
    } finally {
      setSavingSprint(false);
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
      notify.error(t("panel.commentFailed"), errorCause(e)?.message);
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
      notify.error(t("panel.commentDeleteFailed"), errorCause(e)?.message);
    }
  };

  const deleteItem = async () => {
    if (deleting) return;
    setDeleting(true);
    try {
      await api.del(`/work-items/${itemId}`);
      notify.success(t("panel.itemDeleted", { id: bundle?.item.display_id ?? itemId }));
      publishChange("deleted");
      setConfirmDelete(false);
      // Close only the deleted item's layer; lower layers stay open (RDM-136).
      if (onBack) onBack();
      else onClose();
    } catch (e) {
      notify.error(t("panel.deleteFailed"), errorCause(e)?.message);
      setDeleting(false);
    }
  };

  const saveCommentEdit = async () => {
    if (!editingComment || !editingComment.body.trim()) return;
    try {
      await api.patch(`/comments/${editingComment.id}`, {
        body_md: editingComment.body.trim(),
      });
      setEditingComment(null);
      notify.success(t("panel.commentUpdated"));
      await refresh();
    } catch (e) {
      notify.error(t("panel.commentSaveFailed"), errorCause(e)?.message);
    }
  };

  const addArtifact = async (a: { kind: string; label: string; url: string }) => {
    if (!a.label || !a.url) {
      notify.error(t("panel.artifactRequired"));
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
      notify.error(t("panel.artifactAddFailed"), errorCause(e)?.message);
    }
  };

  // Hooks must run unconditionally: compute this before the loading/error
  // early returns below, otherwise React sees a different hook count once
  // the detail bundle arrives (error #310).
  const parentOption = useMemo(
    () => (bundle?.parent ? toWorkItemOption(bundle.parent) : null),
    [bundle?.parent],
  );
  // Only PLANNED/ACTIVE sprints accept items, and the current one is pointless
  // as a "change to" target.
  const sprintOptions = useMemo(
    () =>
      (bundle?.sprints ?? [])
        .filter((s) => s.status !== "CLOSED" && s.id !== bundle?.sprint?.id)
        .map((s) => ({ label: s.name, value: s.id })),
    [bundle?.sprints, bundle?.sprint?.id],
  );

  if (loadError) {
    return (
      <aside className="rdm-item-panel" aria-label={t("panel.ariaLabel")} data-testid="item-panel">
        <Box xcss={styles.padded400}>
          <SectionMessage appearance="error">{t("panel.loadFailed")}</SectionMessage>
          <Box xcss={styles.paddingBlockStart200}>
            <Button appearance="primary" testId="item-panel-error-back" onClick={onClose}>
              {t("panel.backToList")}
            </Button>
          </Box>
        </Box>
      </aside>
    );
  }
  if (!bundle) {
    return (
      <aside className="rdm-item-panel" aria-label={t("panel.ariaLabel")} data-testid="item-panel">
        <Box xcss={styles.padded400} testId="item-panel-loading">
          <Spinner size="large" />
        </Box>
      </aside>
    );
  }

  const {
    item,
    parent,
    ancestors,
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
    sprint,
  } = bundle;
  const breadcrumb = [...ancestors, item];
  const memberOptions: MemberOption[] = members.map((m) => ({
    label: `${userLabel(m)}${m.type === "agent" ? t("panel.agentSuffix") : ""}`,
    value: m.id,
    // Read view shows the display name (§17.116); `name` stays the handle.
    name: userLabel(m),
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
  const canDelete = Boolean(permissions.can_delete ?? canModerate);
  // Epic has no kind extension table; empty field maps render no editor either.
  const hasKindFields =
    item.kind !== "epic" && Object.keys(item.fields ?? {}).length > 0;
  const taskTypeLabel =
    taskTypeOptions().find((option) => option.value === (item.task_type ?? "other"))?.label ??
    item.task_type ??
    t("panel.otherTaskType");
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
            {t("panel.replyChip", {
              name: userLabel(replyTo.author) || replyTo.author.id,
            })}
          </Text>
          <TextButton onClick={() => setReplyTo(null)}>{t("inlineField.cancel")}</TextButton>
        </div>
      )}
      <MarkdownEditor
        value={draft}
        onChange={setDraft}
        projectKey={projectKey}
        minimumRows={2}
        placeholder={t("panel.commentPlaceholder")}
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
          {t("inlineField.cancel")}
        </TextButton>
        <Button testId="item-comment-attach" onClick={() => commentFileInput.current?.click()}>
          {t("panel.addAttachment")}
        </Button>
        <Button
          appearance="primary"
          isLoading={savingComment}
          isDisabled={uploadingDraftImage}
          testId="item-comment-submit"
          onClick={() => void postComment()}
        >
          {t("panel.submitComment")}
        </Button>
      </div>
    </footer>
  );

  return (
    <aside
      className={`rdm-item-panel${covered ? " rdm-item-panel--covered" : ""}`}
      aria-label={t("panel.ariaLabel")}
      data-testid="item-panel"
    >
      <header className="rdm-item-head" data-testid="item-panel-header">
        {onBack ? (
          <IconButton
            icon={(iconProps) => <ArrowLeftIcon {...iconProps} />}
            label={t("panel.back")}
            appearance="subtle"
            testId="item-panel-back"
            onClick={onBack}
          />
        ) : (
          <IconButton
            icon={(iconProps) => <CrossIcon {...iconProps} />}
            label={t("panel.close")}
            appearance="subtle"
            testId="item-panel-close"
            onClick={onClose}
          />
        )}
        <nav
          className="rdm-item-breadcrumb"
          aria-label={t("panel.breadcrumbLabel")}
          data-testid="item-panel-breadcrumb"
        >
          {breadcrumb.map((node, index) => {
            const last = index === breadcrumb.length - 1;
            const label = (
              <>
                <TypeKindIcon kind={node.kind} />
                <span
                  className="rdm-item-breadcrumb-id"
                  {...(last ? { "data-testid": "item-panel-display-id" } : {})}
                >
                  {node.display_id}
                </span>
              </>
            );
            return (
              <Fragment key={node.id}>
                {index > 0 && (
                  <span className="rdm-item-breadcrumb-sep" aria-hidden>
                    /
                  </span>
                )}
                {last ? (
                  <span className="rdm-item-breadcrumb-current" aria-current="page">
                    {label}
                  </span>
                ) : (
                  <button
                    type="button"
                    className="rdm-item-breadcrumb-link"
                    data-testid={`item-panel-ancestor-${node.display_id}`}
                    onClick={() => onOpenItem(node.id)}
                  >
                    {label}
                  </button>
                )}
                {/* Every breadcrumb level gets its own copy affordance; the
                    icon is a sibling so ancestor navigation keeps working. */}
                <IconButton
                  icon={(iconProps) => <CopyIcon {...iconProps} />}
                  label={t("panel.copyDisplayId")}
                  appearance="subtle"
                  spacing="compact"
                  testId={`item-panel-copy-id-${node.display_id}`}
                  onClick={() => void copyDisplayId(node.display_id)}
                />
              </Fragment>
            );
          })}
        </nav>
        <div className="rdm-item-head-actions">
          {canEdit && (
            <TextButton data-testid="item-panel-edit" onClick={() => setShowEdit(true)}>
              {t("panel.editFull")}
            </TextButton>
          )}
          <TextButton data-testid="item-panel-copy-link" onClick={() => void copyLink()}>
            {t("panel.copyLink")}
          </TextButton>
          {canDelete && (
            <TextButton
              danger
              data-testid="item-panel-delete"
              onClick={() => setConfirmDelete(true)}
            >
              {t("panel.deleteItem")}
            </TextButton>
          )}
        </div>
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
                  editLabel={t("panel.editTitle")}
                  validate={(next) => (next.trim() ? undefined : t("panel.titleRequired"))}
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
                label={t("panel.description")}
                required={requiredFieldKeys.has("description_md")}
                value={item.description_md}
                canEdit={canEdit}
                projectKey={projectKey}
                emptyText={t("panel.descriptionEmpty")}
                placeholder={t("panel.descriptionPlaceholder")}
                minimumRows={6}
                editLabel={t("panel.editDescription")}
                readClassName="rdm-inline-read-desc"
                onImageClick={setPreview}
                onSave={(next) => patchItem({ description_md: next.trim() ? next : null })}
              />

              <div className="rdm-item-field" data-testid="item-field-attachments">
                <div className="rdm-item-section-label">{t("panel.attachments")}</div>
                <input
                  ref={attachFileInput}
                  type="file"
                  multiple
                  hidden
                  data-testid="item-attachment-input"
                  onChange={(e) => void uploadFiles(e.target.files, false)}
                />
                <Button
                  isLoading={uploading}
                  testId="item-attachment-upload"
                  onClick={() => attachFileInput.current?.click()}
                >
                  {uploadProgress !== null
                    ? t("panel.uploading", { percent: uploadProgress })
                    : t("panel.uploadAttachment")}
                </Button>
                {attachments.map((a) => (
                  <div
                    key={a.id}
                    className="rdm-item-att"
                    data-testid={`item-attachment-${a.id}`}
                  >
                    <TextButton onClick={() => api.download(a.download_url, a.filename)}>
                      <TruncatedText className="rdm-item-att-name" text={a.filename} />
                    </TextButton>
                    <Text size="small" color="color.text.subtlest">
                      {formatSize(a.size_bytes)}
                    </Text>
                    <TextButton
                      data-testid={`item-attachment-preview-${a.id}`}
                      onClick={() => setPreviewAttachment(a)}
                    >
                      {t("panel.preview")}
                    </TextButton>
                    <TextButton danger onClick={() => removeAttachment(a.id)}>
                      {t("panel.delete")}
                    </TextButton>
                  </div>
                ))}
              </div>

              <div className="rdm-item-field" data-testid="item-field-artifacts">
                <div className="rdm-item-section-label">{t("panel.artifacts")}</div>
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
                      {t("panel.delete")}
                    </TextButton>
                  </div>
                ))}
                <Button testId="item-artifact-add" onClick={() => setShowArtifact(true)}>
                  {t("panel.addArtifact")}
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
                onChanged={(changed) => {
                  void refresh();
                  publishChange("updated", {
                    workItemId: changed?.id,
                    displayId: changed?.display_id,
                    parentId: item.id,
                  });
                }}
              />
            </section>

            <hr className="rdm-item-divider" />

            <section className="rdm-item-section" data-testid="item-section-comments">
              <div className="rdm-item-section-head">
                <div className="rdm-item-section-label">
                  {t("panel.comments", { total: comments.length })}
                </div>
                {!commenting && (
                  <TextButton
                    data-testid="item-comment-add"
                    onClick={() => setCommenting(true)}
                  >
                    {t("panel.addComment")}
                  </TextButton>
                )}
              </div>
              <div data-testid="item-panel-comments">
            {comments.length === 0 && (
              <Text size="small" color="color.text.subtlest">
                {t("panel.commentsEmpty")}
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
                    <PersonCell name={userLabel(c.author) || c.author.id} />
                    <Inline space="space.100" alignBlock="center">
                      <Text size="small" color="color.text.subtlest">
                        {formatDate(c.created_at)}
                        {c.edited ? t("panel.edited") : ""}
                      </Text>
                      <TextButton
                        data-testid={`item-comment-reply-${c.id}`}
                        onClick={() => {
                          setReplyTo(c);
                          setCommenting(true);
                        }}
                      >
                        {t("panel.reply")}
                      </TextButton>
                      {canDelete && (
                        <TextButton
                          data-testid={`item-comment-edit-${c.id}`}
                          onClick={() => setEditingComment({ id: c.id, body: c.body_md })}
                        >
                          {t("inlineField.edit")}
                        </TextButton>
                      )}
                      {canDelete && (
                        <TextButton
                          danger
                          data-testid={`item-comment-delete-${c.id}`}
                          onClick={() => setCommentToDelete(c)}
                        >
                          {t("panel.delete")}
                        </TextButton>
                      )}
                    </Inline>
                  </div>
                  {parentComment && (
                    <div className="rdm-item-comment-reply">
                      {t("panel.replyQuote", {
                        name: userLabel(parentComment.author) || parentComment.author.id,
                      })}
                      {parentComment.body_md.slice(0, 80)}
                    </div>
                  )}
                  {editingComment?.id === c.id ? (
                    <Stack space="space.100">
                      <MarkdownEditor
                        value={editingComment.body}
                        onChange={(body) =>
                          setEditingComment((current) =>
                            current ? { ...current, body } : current,
                          )
                        }
                        projectKey={projectKey}
                        minimumRows={3}
                        testId={`item-comment-edit-input-${c.id}`}
                        onSubmit={() => void saveCommentEdit()}
                      />
                      <Inline space="space.100">
                        <Button
                          appearance="primary"
                          testId={`item-comment-edit-save-${c.id}`}
                          onClick={() => void saveCommentEdit()}
                        >
                          {t("inlineField.save")}
                        </Button>
                        <Button
                          appearance="subtle"
                          testId={`item-comment-edit-cancel-${c.id}`}
                          onClick={() => setEditingComment(null)}
                        >
                          {t("inlineField.cancel")}
                        </Button>
                      </Inline>
                    </Stack>
                  ) : (
                    <MarkdownText source={c.body_md} onImageClick={setPreview} />
                  )}
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
              <Box xcss={styles.paddingBlockStart100}>
                <TextButton
                  data-testid="item-comment-more"
                  onClick={() => void loadMoreComments()}
                >
                  {loadingMoreComments
                    ? t("panel.loadingMore")
                    : t("panel.loadMoreComments")}
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
            <Box xcss={styles.paddingBlockEnd150}>
              <SectionMessage appearance="warning" onDismiss={() => setGateMessage(null)}>
                {gateMessage}
              </SectionMessage>
            </Box>
          )}

          {allowedParentKinds.length > 0 && (
            <>
              <div className="rdm-item-field" data-testid="item-field-parent">
                <div className="rdm-item-section-label">{t("panel.parent")}</div>
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
                    {t("panel.noParent")}
                  </Text>
                )}
                <Box xcss={styles.paddingBlockStart100}>
                  {parentEditing ? (
                    <Stack space="space.100">
                      <WorkItemPicker
                        projectKey={projectKey}
                        allowedKinds={allowedParentKinds}
                        excludeIds={[item.id, ...children.map((c) => c.id)]}
                        value={parentOption}
                        onChange={(option) => void reparent(option)}
                        placeholder={t("panel.selectParent")}
                        testId="item-parent-picker"
                      />
                      <TextButton onClick={() => setParentEditing(false)}>
                        {t("inlineField.cancel")}
                      </TextButton>
                    </Stack>
                  ) : permissions.can_edit ? (
                    <Inline space="space.100">
                      <TextButton
                        data-testid="item-parent-change"
                        onClick={() => setParentEditing(true)}
                      >
                        {parent ? t("panel.changeParent") : t("panel.setParent")}
                      </TextButton>
                      {parent && (
                        <TextButton danger onClick={() => void reparent(null)}>
                          {t("panel.removeParent")}
                        </TextButton>
                      )}
                    </Inline>
                  ) : null}
                </Box>
              </div>
              <hr className="rdm-item-divider" />
            </>
          )}

          {SPRINT_ITEM_KINDS.has(item.kind) && (
            <>
              <div className="rdm-item-field" data-testid="item-field-sprint">
                <div className="rdm-item-section-label">{t("panel.sprint")}</div>
                {sprint ? (
                  <Inline space="space.100" alignBlock="center">
                    <Text>{sprint.name}</Text>
                    <Lozenge>{statusLabel(sprint.status)}</Lozenge>
                  </Inline>
                ) : (
                  <Text size="small" color="color.text.subtlest">
                    {t("panel.noSprint")}
                  </Text>
                )}
                <Box xcss={styles.paddingBlockStart100}>
                  {sprintEditing ? (
                    <Stack space="space.100">
                      <Box testId="item-sprint-picker">
                        <Select<{ label: string; value: string }>
                          {...portalMenuProps}
                          options={sprintOptions}
                          value={null}
                          placeholder={t("panel.selectSprint")}
                          isDisabled={savingSprint}
                          onChange={(opt) =>
                            void changeSprint((opt as { value: string } | null)?.value ?? null)
                          }
                        />
                      </Box>
                      <TextButton onClick={() => setSprintEditing(false)}>
                        {t("inlineField.cancel")}
                      </TextButton>
                    </Stack>
                  ) : (
                    <Inline space="space.100">
                      <TextButton
                        data-testid="item-sprint-change"
                        onClick={() => setSprintEditing(true)}
                      >
                        {sprint ? t("panel.changeSprint") : t("panel.addSprint")}
                      </TextButton>
                      {sprint && (
                        <TextButton
                          danger
                          data-testid="item-sprint-remove"
                          onClick={() => void changeSprint(null)}
                        >
                          {t("panel.removeSprint")}
                        </TextButton>
                      )}
                    </Inline>
                  )}
                </Box>
              </div>
              <hr className="rdm-item-divider" />
            </>
          )}

          <div className="rdm-item-field" data-testid="item-field-priority">
            <div className="rdm-item-section-label">{t("panel.priority")}</div>
            <div className="rdm-priority-row">
              <div className="rdm-priority-select" data-testid="priority-select">
                <Select
                  {...portalMenuProps}
                  options={priorityOptions()}
                  value={
                    priorityOptions().find((o) => o.value === currentPriority) ?? null
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
            <div className="rdm-item-section-label">{t("panel.plannedDates")}</div>
            <Stack space="space.100">
              <div className="rdm-planned-date-row">
                <span className="rdm-planned-date-label">{t("panel.start")}</span>
                <div className="rdm-planned-date-input">
                  <DatePicker
                    value={item.planned_start_date ?? ""}
                    placeholder={t("panel.notSet")}
                    isDisabled={!canEdit}
                    testId="item-planned-start"
                    onChange={(value) =>
                      void patchItem({ planned_start_date: value || null })
                    }
                  />
                </div>
              </div>
              <div className="rdm-planned-date-row">
                <span className="rdm-planned-date-label">{t("panel.end")}</span>
                <div className="rdm-planned-date-input">
                  <DatePicker
                    value={item.planned_end_date ?? ""}
                    placeholder={t("panel.notSet")}
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
            <div className="rdm-item-section-label">{t("panel.status")}</div>
            <StatusLozenge status={item.status} />
          </div>

          <div className="rdm-item-field" data-testid="item-field-steps">
            <div className="rdm-item-section-label">{t("panel.availableSteps")}</div>
            {activeStep && (
              <Box xcss={styles.paddingBlockEnd100}>
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
                {t("panel.noSteps")}
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
                        ? t("panel.taskStepSuffix")
                        : step.mode === "approval"
                          ? t("panel.approvalStepSuffix")
                          : ""}
                    </Button>
                  );
                })}
            </Stack>
            {steps.some(
              (step) => !step.can_start && !step.can_execute && step.blocked_reasons.length > 0,
            ) && (
              <Box xcss={styles.paddingBlockStart050}>
                <Text size="small" color="color.text.subtlest">
                  {steps
                    .filter((step) => !step.can_start && !step.can_execute)
                    .flatMap((step) => step.blocked_reasons)
                    .join(t("listSeparator"))}
                </Text>
              </Box>
            )}
          </div>
          <hr className="rdm-item-divider" />

          <div className="rdm-item-field" data-testid="item-field-assignee">
            <InlineMemberField
              testId="item-assignee"
              label={t("panel.assignee")}
              canEdit={canAssign}
              multiple={false}
              ids={item.assignee ? [item.assignee.id] : []}
              options={memberOptions}
              emptyText={t("panel.unassigned")}
              placeholder={t("panel.selectAssignee")}
              editLabel={t("panel.editAssignee")}
              onSave={assignMember}
            />
          </div>

          <div className="rdm-item-field" data-testid="item-field-participants">
            <InlineMemberField
              testId="item-participants"
              label={t("panel.participants")}
              canEdit={canEdit}
              multiple
              ids={(item.participants ?? []).map((participant) => participant.id)}
              options={memberOptions}
              emptyText={t("panel.notSet")}
              placeholder={t("panel.selectParticipants")}
              editLabel={t("panel.editParticipants")}
              onSave={(next) => patchItem({ participants: next })}
            />
          </div>
          <hr className="rdm-item-divider" />

          {workflowFields.reviewer && (
            <div className="rdm-item-field" data-testid="item-field-reviewer">
              <InlineMemberField
                testId="item-reviewer"
                label={t("panel.reviewer")}
                required={requiredFieldKeys.has("reviewer")}
                canEdit={canEdit}
                multiple
                ids={(item.reviewer ?? []).map((reviewer) => reviewer.id)}
                options={memberOptions}
                emptyText={t("panel.notSet")}
                placeholder={t("panel.selectReviewer")}
                editLabel={t("panel.editReviewer")}
                onSave={(next) => patchItem({ reviewer: next })}
              />
            </div>
          )}

          {workflowFields.review_content && (
            <div className="rdm-item-field" data-testid="item-field-review-content">
              <InlineMarkdownField
                testId="item-review-content"
                label={t("panel.reviewContent")}
                required={requiredFieldKeys.has("review_content")}
                value={item.review_content_md}
                canEdit={canEdit}
                projectKey={projectKey}
                emptyText={t("panel.reviewContentEmpty")}
                placeholder={t("panel.reviewContentPlaceholder")}
                minimumRows={3}
                editLabel={t("panel.editReviewContent")}
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
                        editLabel={t("panel.editField", { label: field.label })}
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
                        editLabel={t("panel.editField", { label: field.label })}
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
                      emptyText={t("panel.customEmpty")}
                      placeholder={t("panel.selectMember")}
                      editLabel={t("panel.editField", { label: field.label })}
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
              <div className="rdm-item-section-label">{t("panel.typeVersion")}</div>
              <Text size="small" color="color.text.subtlest">
                {kindLabel(item.kind)} · v{item.workflow_version ?? "—"} · v{item.row_version}
              </Text>
            </div>
            <div className="rdm-item-field">
              <div className="rdm-item-section-label">{t("panel.createdAt")}</div>
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
        title={t("panel.cancelStepTitle")}
        confirmLabel={t("panel.cancelStepTitle")}
        testId="step-cancel-dialog"
        onClose={() => setStepCancel(null)}
        onConfirm={() => void cancelStep()}
      >
        {t("panel.cancelStepBody")}
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
          publishChange("updated");
          void refresh();
        }}
      />
      <ImagePreviewDialog
        open={preview !== null}
        src={preview?.src ?? null}
        alt={preview?.alt}
        onClose={() => setPreview(null)}
      />
      <AttachmentPreviewDialog
        attachment={previewAttachment}
        onClose={() => setPreviewAttachment(null)}
      />
      <ConfirmDialog
        open={commentToDelete !== null}
        title={t("panel.deleteCommentTitle")}
        confirmLabel={t("panel.delete")}
        testId="item-comment-delete-dialog"
        onClose={() => setCommentToDelete(null)}
        onConfirm={() => void deleteComment()}
      >
        {t("panel.deleteCommentBody")}
      </ConfirmDialog>
      <ConfirmDialog
        open={confirmDelete}
        title={t("panel.deleteItemTitle")}
        confirmLabel={t("panel.deleteItem")}
        danger
        busy={deleting}
        testId="item-delete-dialog"
        onClose={() => {
          if (!deleting) setConfirmDelete(false);
        }}
        onConfirm={() => void deleteItem()}
      >
        {t("panel.deleteItemBody", { id: bundle?.item.display_id ?? itemId })}
      </ConfirmDialog>
      <ConfirmDialog
        open={commentCancelConfirm}
        title={t("panel.discardCommentTitle")}
        confirmLabel={t("panel.discardConfirm")}
        testId="comment-cancel-dialog"
        danger
        onClose={() => setCommentCancelConfirm(false)}
        onConfirm={discardComment}
      >
        {t("panel.discardCommentBody")}
      </ConfirmDialog>
    </aside>
  );
}
