<template>
  <div v-if="item" class="overlay">
    <!-- Pressed-back list context (P2: not a modal; the table stays usable) -->
    <BacklogView class="backdrop" />

    <aside class="panel">
      <header class="panel-head">
        <button class="chevron" title="关闭" @click="close">›</button>
        <TypeIcon :kind="item.kind" />
        <span class="display-id rdm-num">{{ item.display_id }}</span>
        <el-button size="small" link type="primary" @click="showEdit = true">编辑</el-button>
      </header>

      <div class="panel-body">
        <section class="content-col">
          <h1 class="title">{{ item.title }}</h1>
          <div class="section-label">描述</div>
          <div
            v-if="item.description_md"
            class="desc md"
            v-html="renderMarkdown(item.description_md)"
          />
          <div v-else class="desc desc-empty">未填写描述</div>

          <div v-if="fieldsText" class="kind-fields">
            <div class="section-label">特型字段</div>
            <pre class="fields">{{ fieldsText }}</pre>
          </div>

          <div class="section-label">子项（{{ children.length }}）</div>
          <div
            v-for="c in children"
            :key="c.id"
            class="child-row"
            @click="openChild(c)"
          >
            <TypeIcon :kind="c.kind" />
            <span class="rdm-num child-id">{{ c.display_id }}</span>
            <span class="child-title">{{ c.title }}</span>
            <StatusPill :status="c.status" />
          </div>

          <div class="comments">
            <div class="section-label">评论</div>
            <div v-for="c in comments" :key="c.id" class="comment">
              <div class="comment-head">
                <PersonCell :name="c.author.name ?? c.author.id" />
                <span class="meta">{{ formatDate(c.created_at) }}</span>
              </div>
              <div class="md comment-body" v-html="renderMarkdown(c.body_md)" />
              <div v-for="a in c.attachments" :key="a.id" class="comment-att">
                <el-link :underline="false" @click="api.download(a.download_url, a.filename)">
                  📎 {{ a.filename }}
                </el-link>
              </div>
            </div>
            <el-empty v-if="!comments.length" description="还没有评论" :image-size="60" />
          </div>
        </section>

        <section class="fields-col">
          <div class="field">
            <div class="field-label">状态</div>
            <StatusPill :status="item.status" />
          </div>
          <div class="field">
            <div class="field-label">流转到</div>
            <el-select
              :model-value="''"
              size="small"
              placeholder="选择目标状态"
              style="width: 100%"
              @change="transitionTo"
            >
              <el-option v-for="s in allowed" :key="s" :value="s" :label="s" />
            </el-select>
          </div>
          <div class="field">
            <div class="field-label">优先级</div>
            <PriorityRank :priority="item.priority" />
          </div>
          <div class="field">
            <div class="field-label">负责人</div>
            <el-select
              :model-value="item.assignee?.id ?? ''"
              size="small"
              filterable
              clearable
              placeholder="未指派"
              style="width: 100%"
              @change="assign"
            >
              <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
            </el-select>
          </div>
          <div class="field">
            <div class="field-label">类型 / 版本</div>
            <span class="meta">{{ item.kind }} · v{{ item.row_version }}</span>
          </div>
          <div class="field">
            <div class="field-label">创建时间</div>
            <span class="meta">{{ formatDate(item.created_at) }}</span>
          </div>

          <div class="field">
            <div class="field-label">附件</div>
            <el-upload :show-file-list="false" :before-upload="uploadAttachment" multiple>
              <el-button size="small" :loading="uploading">上传附件</el-button>
            </el-upload>
            <div v-for="a in attachments" :key="a.id" class="att-row">
              <el-link :underline="false" @click="api.download(a.download_url, a.filename)">
                {{ a.filename }}
              </el-link>
              <span class="meta">{{ formatSize(a.size_bytes) }}</span>
              <el-button link type="danger" size="small" @click="removeAttachment(a.id)">
                删除
              </el-button>
            </div>
          </div>

          <div class="field">
            <div class="field-label">产出物</div>
            <div v-for="art in artifacts" :key="art.id" class="att-row">
              <el-link :href="art.url" target="_blank" :underline="false">{{ art.label }}</el-link>
              <span class="meta">{{ art.kind }}</span>
              <el-button link type="danger" size="small" @click="removeArtifact(art.id)">
                删除
              </el-button>
            </div>
            <el-button size="small" @click="artifactDialog = true">挂产出物</el-button>
          </div>
        </section>
      </div>

      <footer class="comment-bar">
        <el-input v-model="draft" type="textarea" :rows="2" placeholder="写评论；@成员名 会给对方发站内信" />
        <div class="comment-bar-actions">
          <el-upload
            :show-file-list="true"
            :file-list="pendingFiles"
            :before-upload="queueAttachment"
            multiple
          >
            <el-button size="small">添加附件</el-button>
          </el-upload>
          <el-button type="primary" size="small" :loading="saving" @click="postComment">
            提交评论
          </el-button>
        </div>
      </footer>

      <WorkItemEditDialog v-model="showEdit" :item="item" @saved="onSaved" />

      <el-dialog v-model="artifactDialog" title="挂载产出物" width="440px" append-to-body>
        <el-form label-position="top">
          <el-form-item label="类型">
            <el-select v-model="artifact.kind">
              <el-option v-for="k in ARTIFACT_KINDS" :key="k" :label="k" :value="k" />
            </el-select>
          </el-form-item>
          <el-form-item label="标题"><el-input v-model="artifact.label" /></el-form-item>
          <el-form-item label="URL">
            <el-input v-model="artifact.url" placeholder="https://…" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="artifactDialog = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="addArtifact">保存</el-button>
        </template>
      </el-dialog>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import type { UploadFile, UploadRawFile } from "element-plus";
import { ElMessage, ElMessageBox } from "element-plus";
import { api, errorCause } from "../api";
import type {
  Artifact,
  Attachment,
  Comment,
  Member,
  WorkItem,
} from "../types";
import { renderMarkdown } from "../util/markdown";
import WorkItemEditDialog from "../components/WorkItemEditDialog.vue";
import StatusPill from "../components/StatusPill.vue";
import PriorityRank from "../components/PriorityRank.vue";
import PersonCell from "../components/PersonCell.vue";
import TypeIcon from "../components/TypeIcon.vue";
import BacklogView from "./BacklogView.vue";

const route = useRoute();
const router = useRouter();
const key = computed(() => String(route.params.key));
const refId = computed(() => String(route.params.id));

const item = ref<WorkItem | null>(null);
const showEdit = ref(false);
function onSaved(updated: WorkItem) {
  item.value = updated;
  load();
}
const children = ref<WorkItem[]>([]);
const allowed = ref<string[]>([]);
const comments = ref<Comment[]>([]);
const members = ref<Member[]>([]);
const attachments = ref<Attachment[]>([]);
const artifacts = ref<Artifact[]>([]);
const draft = ref("");
const saving = ref(false);
const uploading = ref(false);
const transitioning = ref<string | null>(null);
const pendingFiles = ref<UploadFile[]>([]);
const pendingAttachmentIds = ref<string[]>([]);
const artifactDialog = ref(false);
const artifact = reactive({ kind: "link", label: "", url: "" });
const ARTIFACT_KINDS = ["link", "doc", "design", "api_doc", "repo", "other"];

const fieldsText = computed(() => {
  const f = item.value?.fields;
  if (!f || !Object.keys(f).length) return "";
  return JSON.stringify(f, null, 2);
});

function formatSize(n: number) {
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
function formatDate(iso: string) {
  return iso ? iso.slice(0, 16).replace("T", " ") : "";
}
function close() {
  router.push(`/projects/${key.value}/backlog`);
}
function openChild(c: WorkItem) {
  router.push(`/projects/${key.value}/items/${c.id}`);
}

async function load() {
  const detail = await api.get<WorkItem>(`/work-items/${encodeURIComponent(refId.value)}`);
  item.value = detail.data;
  children.value = ((detail.meta?.children as WorkItem[]) ?? []) as WorkItem[];
  allowed.value = (detail.meta?.allowed_transitions as string[]) ?? [];
  const [cm, mm, am, artm] = await Promise.all([
    api.get<Comment[]>(`/work-items/${refId.value}/comments`),
    api.get<Member[]>(`/projects/${key.value}/members`),
    api.get<Attachment[]>(
      `/projects/${key.value}/attachments?owner_type=work_item&owner_ref=${encodeURIComponent(refId.value)}`
    ),
    api.get<Artifact[]>(
      `/projects/${key.value}/artifacts?owner_type=work_item&owner_ref=${encodeURIComponent(refId.value)}`
    ),
  ]);
  comments.value = cm.data;
  members.value = mm.data;
  attachments.value = am.data;
  artifacts.value = artm.data;
}

async function transitionTo(to: string) {
  if (!to) return;
  try {
    let reason: string | null = null;
    try {
      const r = await ElMessageBox.prompt(`流转到 ${to} 的原因（可留空）`, "状态流转", {
        confirmButtonText: "流转",
        cancelButtonText: "取消",
      });
      reason = r.value || null;
    } catch {
      return;
    }
    if (!item.value) return;
    transitioning.value = to;
    await api.post(`/work-items/${refId.value}/transition`, {
      to,
      row_version: item.value.row_version,
      reason,
    });
    ElMessage.success(`已流转到 ${to}`);
    await load();
  } catch (e) {
    reportGate(e);
  } finally {
    transitioning.value = null;
  }
}

function reportGate(e: unknown) {
  const cause = errorCause(e);
  if (cause?.code === "WORKFLOW_GATE_BLOCKED" && cause.details?.blocking_children) {
    const ids = (cause.details.blocking_children as { display_id?: string }[])
      .map((c) => c.display_id)
      .join(", ");
    ElMessageBox.alert(
      h("div", [
        h("p", null, cause.message),
        h("p", { style: "margin-top:8px" }, `阻塞子项: ${ids}`),
      ]),
      "子项未终态",
      { type: "warning" }
    );
  } else {
    ElMessage.error(cause?.message ?? "流转失败");
  }
}

async function assign(memberId: string) {
  if (!memberId) return;
  try {
    await api.post(`/work-items/${refId.value}/assign`, { member: memberId });
    await load();
  } catch (e) {
    ElMessage.error((e as Error).message);
    await load();
  }
}

async function uploadAttachment(file: UploadRawFile) {
  uploading.value = true;
  try {
    const form = new FormData();
    form.append("file", file);
    form.append("owner_type", "work_item");
    form.append("owner_ref", refId.value);
    const res = await api.upload<Attachment>(`/projects/${key.value}/attachments`, form);
    attachments.value = [...attachments.value, res.data];
  } catch (e) {
    ElMessage.error((e as Error).message);
  } finally {
    uploading.value = false;
  }
  return false;
}

async function queueAttachment(file: UploadRawFile) {
  try {
    const form = new FormData();
    form.append("file", file);
    form.append("owner_type", "work_item");
    form.append("owner_ref", refId.value);
    const res = await api.upload<Attachment>(`/projects/${key.value}/attachments`, form);
    pendingAttachmentIds.value.push(res.data.id);
    pendingFiles.value.push({ name: file.name } as UploadFile);
    ElMessage.success(`附件 ${file.name} 已上传，提交评论时挂载`);
  } catch (e) {
    ElMessage.error((e as Error).message);
  }
  return false;
}

async function removeAttachment(id: string) {
  try {
    await api.del(`/attachments/${id}`);
    attachments.value = attachments.value.filter((a) => a.id !== id);
  } catch (e) {
    ElMessage.error((e as Error).message);
  }
}

async function removeArtifact(id: string) {
  try {
    await api.post(`/artifacts/${id}/delete`, {});
    artifacts.value = artifacts.value.filter((a) => a.id !== id);
  } catch (e) {
    ElMessage.error((e as Error).message);
  }
}

async function postComment() {
  if (!draft.value.trim()) return;
  saving.value = true;
  try {
    await api.post(`/work-items/${refId.value}/comments`, {
      body_md: draft.value,
      attachment_ids: pendingAttachmentIds.value,
    });
    draft.value = "";
    pendingFiles.value = [];
    pendingAttachmentIds.value = [];
    await load();
  } catch (e) {
    ElMessage.error((e as Error).message);
  } finally {
    saving.value = false;
  }
}

async function addArtifact() {
  if (!artifact.label || !artifact.url) {
    ElMessage.warning("标题和 URL 必填");
    return;
  }
  saving.value = true;
  try {
    const res = await api.post<Artifact>(
      `/projects/${key.value}/artifacts`,
      {
        owner_type: "work_item",
        owner_ref: refId.value,
        kind: artifact.kind,
        label: artifact.label,
        url: artifact.url,
        description_md: "",
      }
    );
    artifacts.value = [...artifacts.value, res.data];
    artifact.label = "";
    artifact.url = "";
    artifactDialog.value = false;
  } catch (e) {
    ElMessage.error((e as Error).message);
  } finally {
    saving.value = false;
  }
}

watch(refId, () => load());
onMounted(load);
</script>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
}
.backdrop {
  position: absolute;
  inset: 0;
}
.panel {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: var(--rdm-drawer-w);
  display: flex;
  flex-direction: column;
  background: var(--rdm-surface);
  box-shadow: var(--rdm-shadow-left);
}
.panel-head {
  height: var(--rdm-topbar-h);
  display: flex;
  align-items: center;
  gap: var(--rdm-space-3);
  padding: 0 var(--rdm-space-4);
  border-bottom: 1px solid var(--rdm-border);
  flex-shrink: 0;
}
.chevron {
  border: none;
  background: none;
  font-size: 20px;
  line-height: 1;
  color: var(--rdm-text-2);
  cursor: pointer;
  width: 32px;
  height: 32px;
  border-radius: var(--rdm-radius-pill);
}
.chevron:hover {
  background: var(--rdm-surface-subtle);
}
.display-id {
  color: var(--rdm-accent-strong);
  font: var(--rdm-type-body);
}
.panel-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}
.content-col {
  flex: 1;
  min-width: 0;
  padding: var(--rdm-space-5);
  overflow-y: auto;
}
.fields-col {
  width: var(--rdm-fields-w);
  flex-shrink: 0;
  border-left: 1px solid var(--rdm-border);
  padding: var(--rdm-space-5);
  overflow-y: auto;
}
.title {
  margin: 0 0 var(--rdm-space-4);
  font: var(--rdm-type-drawer-title);
  color: var(--rdm-text-1);
}
.section-label {
  font: var(--rdm-type-section);
  color: var(--rdm-text-label);
  margin: var(--rdm-space-4) 0 var(--rdm-space-2);
}
.desc {
  border: 1px dashed var(--rdm-border-strong);
  border-radius: var(--rdm-radius-2);
  min-height: 138px;
  padding: var(--rdm-space-4);
  font: var(--rdm-type-body);
  color: var(--rdm-text-2);
}
.desc-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--rdm-text-3);
}
.fields {
  font: var(--rdm-type-meta);
  color: var(--rdm-text-2);
  white-space: pre-wrap;
}
.child-row {
  display: flex;
  align-items: center;
  gap: var(--rdm-space-2);
  height: var(--rdm-row-h);
  padding: 0 var(--rdm-space-2);
  border-radius: var(--rdm-radius-2);
  cursor: pointer;
  font: var(--rdm-type-cell);
}
.child-row:hover {
  background: var(--rdm-surface-subtle);
}
.child-id {
  color: var(--rdm-accent-strong);
}
.child-title {
  flex: 1;
  color: var(--rdm-text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.field {
  margin-bottom: var(--rdm-space-5);
}
.field-label {
  font: var(--rdm-type-meta);
  color: var(--rdm-text-label);
  margin-bottom: var(--rdm-space-2);
}
.meta {
  font: var(--rdm-type-meta);
  color: var(--rdm-text-3);
}
.att-row {
  display: flex;
  align-items: center;
  gap: var(--rdm-space-2);
  padding: var(--rdm-space-1) 0;
}
.att-row .el-link {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.comment-bar {
  border-top: 1px solid var(--rdm-border);
  box-shadow: var(--rdm-shadow-up);
  padding: var(--rdm-space-4);
  flex-shrink: 0;
}
.comment-bar-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--rdm-space-2);
  margin-top: var(--rdm-space-2);
}
.comment {
  padding: var(--rdm-space-3) 0;
  border-bottom: 1px solid var(--rdm-border);
}
.comment-head {
  display: flex;
  align-items: center;
  gap: var(--rdm-space-3);
  margin-bottom: var(--rdm-space-1);
}
.comment-body {
  color: var(--rdm-text-2);
  font: var(--rdm-type-body);
}
.comment-att {
  margin-top: var(--rdm-space-1);
}
</style>
