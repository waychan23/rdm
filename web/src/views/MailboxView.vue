<template>
  <div v-loading="loading">
    <div class="head">
      <h2>信箱 · {{ key }}</h2>
      <div>
        <el-checkbox v-model="unreadOnly" @change="reload">仅未读</el-checkbox>
        <el-button
          :disabled="!selected.size"
          @click="markSelected([...selected])"
        >标记已读</el-button>
      </div>
    </div>

    <el-empty v-if="!messages.length" description="没有信件" :image-size="80" />
    <el-card
      v-for="m in messages"
      :key="m.delivery_id"
      class="mail"
      :class="{ unread: !m.read_at }"
    >
      <div class="mail-head">
        <el-checkbox
          :model-value="selected.has(m.delivery_id)"
          :disabled="!!m.read_at"
          @change="toggle(m.delivery_id)"
        />
        <strong>{{ m.subject }}</strong>
        <el-tag size="small" type="info">{{ m.from.name ?? m.from.id }}</el-tag>
        <span class="muted">{{ m.created_at }}</span>
        <el-button
          v-if="!m.read_at"
          link
          type="primary"
          @click="markSelected([m.delivery_id])"
        >标已读</el-button>
      </div>
      <div class="mail-body">{{ m.body_md }}</div>
      <div v-if="m.refs.length" class="muted">
        关联：
        <router-link
          v-for="r in m.refs"
          :key="r"
          :to="`/projects/${key}/items/${r}`"
          style="margin-right: 8px"
        >{{ r }}</router-link>
      </div>
    </el-card>

    <div v-if="nextCursor" style="text-align: center; margin-top: 12px">
      <el-button @click="loadMore">加载更多</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api";
import type { MailMessage, Mailbox } from "../types";

const props = defineProps<{ key: string }>();
const key = props.key;
const loading = ref(false);
const unreadOnly = ref(true);
const messages = ref<MailMessage[]>([]);
const nextCursor = ref<string | null>(null);
const selected = ref<Set<string>>(new Set());

async function fetchPage(since?: string | null, replace = false) {
  loading.value = true;
  try {
    const params = new URLSearchParams({ limit: "20" });
    if (unreadOnly.value) params.set("unread_only", "true");
    if (since) params.set("since", since);
    const box = (await api.get<Mailbox>(`/projects/${key}/mailbox?${params}`)).data;
    messages.value = replace ? box.messages : [...messages.value, ...box.messages];
    nextCursor.value = box.next_cursor;
  } finally {
    loading.value = false;
  }
}

function reload() {
  selected.value.clear();
  fetchPage(null, true);
}

function loadMore() {
  return fetchPage(nextCursor.value);
}

function toggle(id: string) {
  if (selected.value.has(id)) selected.value.delete(id);
  else selected.value.add(id);
  selected.value = new Set(selected.value);
}

async function markSelected(ids: string[]) {
  try {
    await api.post("/messages/read", { delivery_ids: ids });
    ids.forEach((id) => selected.value.delete(id));
    selected.value = new Set(selected.value);
    await fetchPage(null, true);
  } catch (e) {
    ElMessage.error((e as Error).message);
  }
}

onMounted(() => fetchPage(null, true));
</script>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.mail {
  margin-bottom: 10px;
}
.mail.unread {
  border-left: 3px solid var(--el-color-primary);
}
.mail-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.mail-body {
  margin: 8px 0 4px 24px;
  white-space: pre-wrap;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.mail-head .el-button {
  margin-left: auto;
}
</style>
