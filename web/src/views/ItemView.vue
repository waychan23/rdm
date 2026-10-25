<template>
  <div v-if="item">
    <el-page-header :content="`${item.display_id} · ${item.title}`" style="margin-bottom: 16px">
      <template #content>
        <el-link :href="`/projects/${key}/backlog`" :underline="false">
          ← {{ item.display_id }}
        </el-link>
        <span style="margin-left: 12px">{{ item.title }}</span>
      </template>
    </el-page-header>

    <el-descriptions :column="2" border>
      <el-descriptions-item label="类型">{{ item.kind }}</el-descriptions-item>
      <el-descriptions-item label="状态">{{ item.status }}</el-descriptions-item>
      <el-descriptions-item label="优先级">{{ item.priority }}</el-descriptions-item>
      <el-descriptions-item label="负责人">{{ item.assignee?.name ?? "—" }}</el-descriptions-item>
      <el-descriptions-item label="版本">{{ item.row_version }}</el-descriptions-item>
      <el-descriptions-item label="可流转">
        <el-tag v-for="s in allowed" :key="s" size="small" style="margin-right: 4px">{{ s }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="描述" :span="2">
        {{ item.description_md || "—" }}
      </el-descriptions-item>
      <el-descriptions-item v-if="fieldsText" label="特型字段" :span="2">
        <pre class="fields">{{ fieldsText }}</pre>
      </el-descriptions-item>
    </el-descriptions>

    <el-divider content-position="left">子项</el-divider>
    <el-table :data="children" border size="small">
      <el-table-column label="ID" width="110">
        <template #default="{ row }">
          <el-link :href="`/projects/${key}/items/${row.display_id}`" :underline="false">
            {{ row.display_id }}
          </el-link>
        </template>
      </el-table-column>
      <el-table-column prop="kind" label="类型" width="90" />
      <el-table-column prop="title" label="标题" />
      <el-table-column prop="status" label="状态" width="140" />
    </el-table>

    <el-divider content-position="left">评论</el-divider>
    <div v-for="c in comments" :key="c.id" class="comment">
      <div class="comment-head">
        <strong>{{ c.author.name ?? c.author.id }}</strong>
        <span class="muted">{{ c.created_at }}</span>
      </div>
      <div class="comment-body">{{ c.body_md }}</div>
    </div>
    <el-empty v-if="!comments.length" description="还没有评论" :image-size="60" />

    <el-input
      v-model="draft"
      type="textarea"
      :rows="3"
      placeholder="写评论；@成员名 会给对方发站内信"
      style="margin-top: 12px"
    />
    <div style="margin-top: 8px; text-align: right">
      <el-button type="primary" :loading="saving" @click="postComment">提交评论</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { api } from "../api";
import type { Comment, WorkItem } from "../types";

const route = useRoute();
const key = String(route.params.key);

const item = ref<WorkItem | null>(null);
const children = ref<WorkItem[]>([]);
const allowed = ref<string[]>([]);
const comments = ref<Comment[]>([]);
const draft = ref("");
const saving = ref(false);

const fieldsText = computed(() => {
  const f = item.value?.fields;
  if (!f || Object.keys(f).length === 0) return "";
  return JSON.stringify(f, null, 2);
});

async function load() {
  const detail = await api.get<WorkItem>(
    `/work-items/${encodeURIComponent(String(route.params.id))}`
  );
  item.value = detail.data;
  children.value = ((detail.meta?.children as WorkItem[]) ?? []);
  allowed.value = (detail.meta?.allowed_transitions as string[]) ?? [];
  comments.value = (await api.get<Comment[]>(`/work-items/${route.params.id}/comments`)).data;
}

async function postComment() {
  if (!draft.value.trim()) return;
  saving.value = true;
  try {
    await api.post(`/work-items/${route.params.id}/comments`, { body_md: draft.value });
    draft.value = "";
    await load();
  } catch (e) {
    ElMessage.error((e as Error).message);
  } finally {
    saving.value = false;
  }
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
  white-space: pre-wrap;
}
.fields {
  margin: 0;
  font-size: 12px;
}
</style>
