import { useCallback, useEffect, useRef, useState } from "react";

import Button from "@atlaskit/button/default/button";
import IconButton from "@atlaskit/button/icon/button";
import Heading from "@atlaskit/heading";
import CrossIcon from "@atlaskit/icon/core/cross";
import Link from "@atlaskit/link";
import Select from "@atlaskit/select";
import TextArea from "@atlaskit/textarea";
import SectionMessage from "@atlaskit/section-message";
import Spinner from "@atlaskit/spinner";
import { Box, Inline, Text } from "@atlaskit/primitives";
import TextButton from "../../components/TextButton";
import { token } from "@atlaskit/tokens";

import { api, errorCause } from "../../lib/api";
import { formatDate, formatSize } from "../../lib/format";
import { useNotify } from "../../lib/flags";
import MarkdownText from "../../components/MarkdownText";
import PersonCell from "../../components/PersonCell";
import PriorityMark from "../../components/PriorityMark";
import TypeKindIcon from "../../components/TypeKindIcon";
import EditWorkItemDialog from "../../workitems/EditWorkItemDialog";
import StatusLozenge from "../../workitems/status";
import type { Artifact, Attachment, Comment, OrgUser, ProjectMemberRow, WorkItem } from "../../types";
import { flattenMembers } from "../../lib/members";
import TransitionDialog from "./TransitionDialog";
import ArtifactDialog from "./ArtifactDialog";

interface Props {
  projectKey: string;
  itemId: string;
  onClose: () => void;
  onOpenItem: (id: string) => void;
}

interface DetailBundle {
  item: WorkItem;
  children: WorkItem[];
  allowed: string[];
  comments: Comment[];
  members: OrgUser[];
  attachments: Attachment[];
  artifacts: Artifact[];
}

export default function ItemPanel({ projectKey, itemId, onClose, onOpenItem }: Props) {
  const notify = useNotify();
  const [bundle, setBundle] = useState<DetailBundle | null>(null);
  const [loadError, setLoadError] = useState(false);

  const [showEdit, setShowEdit] = useState(false);
  const [transitionTarget, setTransitionTarget] = useState<string | null>(null);
  const [showArtifact, setShowArtifact] = useState(false);
  const [gateMessage, setGateMessage] = useState<string | null>(null);

  const [draft, setDraft] = useState("");
  const [savingComment, setSavingComment] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<{ name: string; id: string }[]>([]);
  const pendingIds = useRef<string[]>([]);
  const commentFileInput = useRef<HTMLInputElement>(null);
  const attachFileInput = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const load = useCallback(async () => {
    try {
      const detail = await api.get<WorkItem>(
        `/work-items/${encodeURIComponent(itemId)}`,
      );
      const [cm, mm, am, artm] = await Promise.all([
        api.get<Comment[]>(`/work-items/${itemId}/comments`),
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
        children: ((detail.meta?.children as WorkItem[]) ?? []) as WorkItem[],
        allowed: (detail.meta?.allowed_transitions as string[]) ?? [],
        comments: cm.data,
        members: flattenMembers(mm.data),
        attachments: am.data,
        artifacts: artm.data,
      });
      setLoadError(false);
    } catch {
      setLoadError(true);
    }
  }, [itemId, projectKey]);

  useEffect(() => {
    setBundle(null);
    void load();
  }, [load]);

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
      await load();
    } catch (e) {
      setTransitionTarget(null);
      reportGate(e);
    }
  };

  const assign = async (memberId: string | null) => {
    if (!memberId) return;
    try {
      await api.post(`/work-items/${itemId}/assign`, { member: memberId });
      await load();
    } catch (e) {
      notify.error("指派失败", errorCause(e)?.message);
      await load();
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

  const removeArtifact = async (id: string) => {
    try {
      await api.post(`/artifacts/${id}/delete`, {});
      setBundle((b) =>
        b ? { ...b, artifacts: b.artifacts.filter((a) => a.id !== id) } : b,
      );
    } catch (e) {
      notify.error("删除失败", errorCause(e)?.message);
    }
  };

  const postComment = async () => {
    if (!draft.trim() || savingComment) return;
    setSavingComment(true);
    try {
      await api.post(`/work-items/${itemId}/comments`, {
        body_md: draft,
        attachment_ids: pendingIds.current,
      });
      setDraft("");
      pendingIds.current = [];
      setPendingFiles([]);
      await load();
    } catch (e) {
      notify.error("评论失败", errorCause(e)?.message);
    } finally {
      setSavingComment(false);
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
            <Button
              appearance="primary"
              testId="item-panel-error-back"
              onClick={onClose}
            >
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

  const { item, children, allowed, comments, members, attachments, artifacts } = bundle;
  const memberOptions = members.map((m) => ({ label: m.name, value: m.id }));

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
              <MarkdownText source={item.description_md} />
            </div>
          ) : (
            <div
              className="rdm-item-desc rdm-item-desc-empty"
              data-testid="item-panel-description-empty"
            >
              未填写描述
            </div>
          )}

          {item.fields && Object.keys(item.fields).length > 0 && (
            <>
              <div className="rdm-item-section-label">特型字段</div>
              <pre
                style={{ font: token("font.body.small"), color: token("color.text.subtle") }}
                data-testid="item-panel-fields-json"
              >
                {JSON.stringify(item.fields, null, 2)}
              </pre>
            </>
          )}

          <div className="rdm-item-section-label">子项（{children.length}）</div>
          <div data-testid="item-panel-children">
            {children.map((c) => (
              <div key={c.id} className="rdm-item-child" onClick={() => onOpenItem(c.id)}>
                <TypeKindIcon kind={c.kind} />
                <span className="rdm-item-child-id">{c.display_id}</span>
                <span className="rdm-item-child-title">{c.title}</span>
                <StatusLozenge status={c.status} />
              </div>
            ))}
          </div>

          <div className="rdm-item-section-label">评论</div>
          <div data-testid="item-panel-comments">
            {comments.length === 0 && (
              <Text size="small" color="color.text.subtlest">
                还没有评论
              </Text>
            )}
            {comments.map((c) => (
              <div key={c.id} className="rdm-item-comment" data-testid={`item-comment-${c.id}`}>
                <div className="rdm-item-comment-head">
                  <PersonCell name={c.author.name ?? c.author.id} />
                  <Text size="small" color="color.text.subtlest">
                    {formatDate(c.created_at)}
                  </Text>
                </div>
                <MarkdownText source={c.body_md} />
                {c.attachments?.map((a) => (
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
            ))}
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
              options={allowed.map((s) => ({ label: s, value: s }))}
              placeholder="选择目标状态"
              value={null}
              onChange={(opt) => opt && setTransitionTarget((opt as { value: string }).value)}
              isDisabled={allowed.length === 0}
            />
          </div>

          <div className="rdm-item-field" data-testid="item-field-priority">
            <div className="rdm-item-section-label">优先级</div>
            <PriorityMark priority={item.priority} />
          </div>

          <div className="rdm-item-field" data-testid="item-field-assignee">
            <div className="rdm-item-section-label">负责人</div>
            <Select
              options={memberOptions}
              value={memberOptions.find((o) => o.value === item.assignee?.id) ?? null}
              placeholder="未指派"
              isClearable
              onChange={(opt) => assign((opt as { value: string } | null)?.value ?? null)}
            />
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
                <Link
                  href={art.url}
                  target="_blank"
                  testId={`item-artifact-link-${art.id}`}
                >
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
        </section>
      </div>

      <footer className="rdm-item-comment-bar" data-testid="item-comment-bar">
        <TextArea
          value={draft}
          minimumRows={2}
          placeholder="写评论；@成员名 会给对方发站内信"
          testId="item-comment-input"
          onChange={(e) => setDraft(e.currentTarget.value)}
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
          <Button
            testId="item-comment-attach"
            onClick={() => commentFileInput.current?.click()}
          >
            添加附件
          </Button>
          <Button
            appearance="primary"
            isLoading={savingComment}
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
      <ArtifactDialog open={showArtifact} onClose={() => setShowArtifact(false)} onSave={addArtifact} />
      <EditWorkItemDialog
        open={showEdit}
        item={item}
        onClose={() => setShowEdit(false)}
        onSaved={(updated) => {
          setBundle((b) => (b ? { ...b, item: updated } : b));
          void load();
        }}
      />
    </aside>
  );
}
