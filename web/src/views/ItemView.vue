<template>
  <div v-if="item">
    <el-page-header style="margin-bottom: 16px">
      <template #content>
        <router-link :to="`/projects/${key}/backlog`">← {{ item.display_id }}</router-link>
        <span style="margin-left: 12px">{{ item.title }}</span>
        <el-button size="small" style="margin-left: 12px" @click="showEdit = true">编辑</el-button>
      </template>
    </el-page-header>

    <WorkItemEditDialog v-model="showEdit" :item="item" @saved="onSaved" />

    <el-descriptions :column="2" border>
      <el-descriptions-item label="类型">{{ item.kind }}</el-descriptions-item>
      <el-descriptions-item label="状态">{{ item.status }}</el-descriptions-item>
      <el-descriptions-item label="优先级">{{ item.priority }}</el-descriptions-item>
      <el-descriptions-item label="负责人">
        <el-select
          :model-value="item.assignee?.id ?? ''"
          size="small"
          filterable
          placeholder="未指派"
          style="width: 180px"
          @change="assign"
        >
          <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
        </el-select>
      </el-descriptions-item>
      <el-descriptions-item label="版本">{{ item.row_version }}</el-descriptions-item>
      <el-descriptions-item label="可流转">
        <el-button
          v-for="s in allowed"
          :key="s"
          size="small"
          :loading="transitioning === s"
          style="margin: 2px"
          @click="transitionTo(s)"
        >{{ s }}</el-button>
      </el-descriptions-item>
      <el-descriptions-item label="描述" :span="2">
        <div v-if="item.description_md" class="md" v-html="renderMarkdown(item.description_md)" />
        <span v-else class="muted">—</span>
      </el-descriptions-item>
      <el-descriptions-item v-if="fieldsText" label="特型字段" :span="2">
        <pre class="fields">{{ fieldsText }}</pre>
      </el-descriptions-item>
    </el-descriptions>

    <el-divider content-position="left">子项</el-divider>
    <el-table :data="children" border size="small">
      <el-table-column label="ID" width="110">
        <template #default="{ row }">
          <router-link :to="`/projects/${key}/items/${row.display_id}`">{{ row.display_id }}</router-link>
        </template>
      </el-table-column>
      <el-table-column prop="kind" label="类型" width="90" />
      <el-table-column prop="title" label="标题" />
      <el-table-column prop="status" label="状态" width="140" />
    </el-table>

    <el-divider content-position="left">产出物</el-divider>
    <el-table :data="artifacts" size="small" border>
      <el-table-column prop="kind" label="类型" width="100" />
      <el-table-column label="链接">
        <template #default="{ row }">
          <el-link :href="row.url" target="_blank" :underline="false">{{ row.label }}</el-link>
        </template>
      </el-table-column>
    </el-table>
    <el-button size="small" style="margin-top: 8px" @click="artifactDialog = true">挂产出物</el-button>

    <el-divider content-position="left">附件</el-divider>
    <el-upload
      :show-file-list="false"
      :before-upload="uploadAttachment"
      multiple
    >
      <el-button size="small" :loading="uploading">上传附件</el-button>
    </el-upload>
    <el-table :data="attachments" size="small" border style="margin-top: 8px">
      <el-table-column prop="filename" label="文件" />
      <el-table-column label="大小" width="100">
        <template #default="{ row }">{{ formatSize(row.size_bytes) }}</template>
      </el-table-column>
      <el-table-column label="上传者" width="120">
        <template #default="{ row }">{{ row.uploader.name ?? row.uploader.id }}</template>
      </el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button link type="primary" @click="api.download(row.download_url, row.filename)">下载</el-button>
          <el-button link type="danger" @click="removeAttachment(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-divider content-position="left">评论</el-divider>
    <div v-for="c in comments" :key="c.id" class="comment">
      <div class="comment-head">
        <strong>{{ c.author.name ?? c.author.id }}</strong>
        <span class="muted">{{ c.created_at }}</span>
      </div>
      <div class="md comment-body" v-html="renderMarkdown(c.body_md)" />
      <div v-for="a in c.attachments" :key="a.id" class="comment-att">
        📎
        <el-link :underline="false" @click="api.download(a.download_url, a.filename)">
          {{ a.filename }}
        </el-link>
      </div>
    </div>
    <el-empty v-if="!comments.length" description="还没有评论" :image-size="60" />

    <el-input
      v-model="draft"
      type="textarea"
      :rows="3"
      placeholder="写评论；@成员名 会给对方发站内信"
      style="margin-top: 12px"
    />
    <div class="comment-actions">
      <el-upload :show-file-list="true" :file-list="pendingFiles" :before-upload="queueAttachment" multiple>
        <el-button size="small">添加附件</el-button>
      </el-upload>
      <el-button type="primary" :loading="saving" @click="postComment">提交评论</el-button>
    </div>

    <el-dialog v-model="artifactDialog" title="挂载产出物" width="440px">
      <el-form label-width="72px">
        <el-form-item label="类型">
          <el-select v-model="artifact.kind">
            <el-option v-for="k in ARTIFACT_KINDS" :key="k" :label="k" :value="k" />
          </el-select>
        </el-form-item>
        <el-form-item label="标题"><el-input v-model="artifact.label" /></el-form-item>
        <el-form-item label="URL"><el-input v-model="artifact.url" placeholder="https://…" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="artifactDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="addArtifact">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
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

const route = useRoute();
const key = String(route.params.key);
const refId = String(route.params.id);

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
  if (!f || Object.keys(f).length === 0) return "";
  return JSON.stringify(f, null, 2);
});

function formatSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

async function load() {
  const detail = await api.get<WorkItem>(`/work-items/${encodeURIComponent(refId)}`);
  item.value = detail.data;
  children.value = ((detail.meta?.children as WorkItem[]) ?? []);
  allowed.value = (detail.meta?.allowed_transitions as string[]) ?? [];
  const [cm, mm, am, artm] = await Promise.all([
    api.get<Comment[]>(`/work-items/${refId}/comments`),
    api.get<Member[]>(`/projects/${key}/members`),
    api.get<Attachment[]>(
      `/projects/${key}/attachments?owner_type=work_item&owner_ref=${encodeURIComponent(refId)}`
    ),
    api.get<Artifact[]>(
      `/projects/${key}/artifacts?owner_type=work_item&owner_ref=${encodeURIComponent(refId)}`
    ),
  ]);
  comments.value = cm.data;
  members.value = mm.data;
  attachments.value = am.data;
  artifacts.value = artm.data;
}

async function transitionTo(to: string) {
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
    await api.post(`/work-items/${refId}/transition`, {
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

async function assign(memberId: string) {
  if (!memberId) return;
  try {
    await api.post(`/work-items/${refId}/assign`, { member: memberId });
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
    form.append("owner_ref", refId);
    const res = await api.upload<Attachment>(`/projects/${key}/attachments`, form);
    attachments.value = [...attachments.value, res.data];
  } catch (e) {
    ElMessage.error((e as Error).message);
  } finally {
    uploading.value = false;
  }
  return false; // keep el-upload from posting itself
}

async function queueAttachment(file: UploadRawFile) {
  try {
    const form = new FormData();
    form.append("file", file);
    form.append("owner_type", "work_item");
    form.append("owner_ref", refId);
    const res = await api.upload<Attachment>(`/projects/${key}/attachments`, form);
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

async function postComment() {
  if (!draft.value.trim()) return;
  saving.value = true;
  try {
    await api.post(`/work-items/${refId}/comments`, {
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
    await api.post(`/projects/${key}/artifacts`, {
      owner_type: "work_item",
      owner_ref: refId,
      kind: artifact.kind,
      label: artifact.label,
      url: artifact.url,
    });
    artifactDialog.value = false;
    artifact.label = "";
    artifact.url = "";
    await load();
  } catch (e) {
    ElMessage.error((e as Error).message);
  } finally {
    saving.value = false;
  }
}

function reportGate(e: unknown) {
  const cause = errorCause(e);
  const blocking = (cause?.details?.blocking_children ?? []) as string[];
  ElMessage({
    type: "error",
    message: h("div", [
      h("p", (e as Error).message),
      blocking.length ? h("p", `阻塞子项：${blocking.join(", ")}`) : null,
    ]),
  });
}

onMounted(load);
</script>

<style scoped>
.comment {
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 8px 0;
}
.comment-head {
  display: flex;
  gap: 10px;
  align-items: baseline;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.comment-body {
  margin-top: 4px;
}
.comment-att {
  font-size: 12px;
  margin: 2px 0;
}
.comment-actions {
  margin-top: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.fields {
  margin: 0;
  font-size: 12px;
}
</style>
