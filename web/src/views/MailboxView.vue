<template>
  <div v-loading="loading">
    <div class="head">
      <h2>信箱 · {{ key }}</h2>
      <div>
        <el-checkbox v-model="unreadOnly" @change="reload">仅未读</el-checkbox>
        <el-button type="primary" @click="openCompose">发信</el-button>
        <el-button
          :disabled="!selected.size"
          @click="markSelected([...selected])"
        >标记已读</el-button>
      </div>
    </div>

    <el-dialog v-model="showCompose" title="发站内信" width="520px">
      <el-form label-position="top">
        <el-form-item label="收件人">
          <el-select v-model="compose.to" multiple filterable placeholder="选择成员" style="width: 100%">
            <el-option v-for="m in members" :key="m.id" :value="m.name" :label="m.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="主题"><el-input v-model="compose.subject" /></el-form-item>
        <el-form-item label="正文（Markdown）">
          <el-input v-model="compose.body_md" type="textarea" :rows="5" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCompose = false">取消</el-button>
        <el-button type="primary" :loading="sending" @click="send">发送</el-button>
      </template>
    </el-dialog>

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
import { onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { api, errorCause } from "../api";
import type { MailMessage, Mailbox, Member } from "../types";

const key = String(useRoute().params.key);
const loading = ref(false);
const unreadOnly = ref(true);
const messages = ref<MailMessage[]>([]);
const nextCursor = ref<string | null>(null);
const selected = ref<Set<string>>(new Set());
const members = ref<Member[]>([]);
const showCompose = ref(false);
const sending = ref(false);
const compose = reactive({ to: [] as string[], subject: "", body_md: "" });

function openCompose() {
  compose.to = [];
  compose.subject = "";
  compose.body_md = "";
  showCompose.value = true;
}

async function send() {
  if (!compose.to.length || !compose.subject.trim() || !compose.body_md.trim()) {
    ElMessage.warning("收件人、主题、正文均必填");
    return;
  }
  sending.value = true;
  try {
    await api.post(`/projects/${key}/messages`, { ...compose, cc: [], refs: [] });
    ElMessage.success("已发送");
    showCompose.value = false;
    reload();
  } catch (e) {
    ElMessage.error(errorCause(e)?.message || "发送失败");
  } finally {
    sending.value = false;
  }
}

async function fetchPage(since?: string | null, replace = false) {
  loading.value = true;
  try {
    const params = new URLSearchParams({
      limit: "20",
      unread_only: unreadOnly.value ? "true" : "false",
    });
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

onMounted(async () => {
  members.value = (await api.get<Member[]>(`/projects/${key}/members`)).data;
  fetchPage(null, true);
});
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
