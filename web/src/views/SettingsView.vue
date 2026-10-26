<template>
  <div v-loading="loading">
    <h2>设置 · {{ key }}</h2>

    <el-descriptions :column="2" border style="margin-bottom: 20px">
      <el-descriptions-item label="项目 ID">{{ project?.id ?? "—" }}</el-descriptions-item>
      <el-descriptions-item label="状态">{{ project?.status ?? "—" }}</el-descriptions-item>
      <el-descriptions-item label="名称" :span="2">{{ project?.name ?? "—" }}</el-descriptions-item>
    </el-descriptions>

    <el-divider content-position="left">成员与通知</el-divider>
    <el-table :data="members" border size="small">
      <el-table-column prop="name" label="名称" width="130" />
      <el-table-column prop="type" label="类型" width="80" />
      <el-table-column label="角色" width="200">
        <template #default="{ row }">
          <el-tag v-for="r in row.roles" :key="r" size="small" style="margin: 2px">{{ r }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="Webhook" min-width="200">
        <template #default="{ row }">
          <span class="muted">{{ row.notify_webhook ?? "—" }}</span>
          <el-tag v-if="row.notify_webhook" size="small" style="margin-left: 6px">
            {{ row.notify_webhook_format }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="活跃" width="70">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
            {{ row.is_active ? "是" : "否" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="warning" @click="openTokens(row)">Token</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="editDialog" title="编辑成员" width="480px">
      <el-form label-width="110px">
        <el-form-item label="角色（逗号）">
          <el-input v-model="edit.rolesText" placeholder="manager,worker" />
        </el-form-item>
        <el-form-item label="可接 kinds">
          <el-checkbox-group v-model="edit.acceptKinds">
            <el-checkbox value="story">story</el-checkbox>
            <el-checkbox value="issue">issue</el-checkbox>
            <el-checkbox value="task">task</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="Email"><el-input v-model="edit.email" /></el-form-item>
        <el-form-item label="Webhook URL">
          <el-input v-model="edit.notifyWebhook" placeholder="https://…" />
        </el-form-item>
        <el-form-item label="Webhook 格式">
          <el-select v-model="edit.notifyFormat">
            <el-option label="generic（完整 JSON）" value="generic" />
            <el-option label="dingtalk（markdown）" value="dingtalk" />
            <el-option label="feishu（text）" value="feishu" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="edit.isActive" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveMember">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="tokenDialog" :title="`Token · ${tokenMember?.name ?? ''}`" width="560px">
      <el-button type="primary" size="small" @click="issueToken">签发新 Token</el-button>
      <el-table :data="tokens" size="small" style="margin-top: 10px">
        <el-table-column prop="label" label="标签" width="120" />
        <el-table-column prop="created_at" label="创建" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_valid ? 'success' : 'info'" size="small">
              {{ row.is_valid ? "有效" : "已吊销" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button
              v-if="row.is_valid"
              link
              type="danger"
              @click="revokeToken(row.id)"
            >吊销</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-alert
        v-if="issuedToken"
        :title="`新 Token（只显示一次）：${issuedToken}`"
        type="success"
        :closable="false"
        style="margin-top: 10px"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { api } from "../api";
import type { Member, Project, Token } from "../types";

const key = String(useRoute().params.key);
const loading = ref(false);
const saving = ref(false);
const project = ref<Project | null>(null);
const members = ref<Member[]>([]);

const editDialog = ref(false);
const edit = reactive({
  id: "",
  rolesText: "",
  acceptKinds: [] as string[],
  email: "",
  notifyWebhook: "",
  notifyFormat: "generic",
  isActive: true,
});

const tokenDialog = ref(false);
const tokenMember = ref<Member | null>(null);
const tokens = ref<Token[]>([]);
const issuedToken = ref("");

async function load() {
  loading.value = true;
  try {
    project.value = (await api.get<Project>(`/projects/${key}`)).data;
    members.value = (await api.get<Member[]>(`/projects/${key}/members`)).data;
  } finally {
    loading.value = false;
  }
}

function openEdit(row: Member) {
  Object.assign(edit, {
    id: row.id,
    rolesText: row.roles.join(","),
    acceptKinds: [...(row.accept_kinds ?? [])],
    email: row.email ?? "",
    notifyWebhook: row.notify_webhook ?? "",
    notifyFormat: row.notify_webhook_format ?? "generic",
    isActive: row.is_active,
  });
  editDialog.value = true;
}

async function saveMember() {
  saving.value = true;
  try {
    await api.patch(`/members/${edit.id}`, {
      roles: edit.rolesText.split(",").map((s) => s.trim()).filter(Boolean),
      accept_kinds: edit.acceptKinds,
      email: edit.email || null,
      notify_webhook: edit.notifyWebhook || null,
      notify_webhook_format: edit.notifyFormat,
      is_active: edit.isActive,
    });
    editDialog.value = false;
    await load();
  } catch (e) {
    ElMessage.error((e as Error).message);
  } finally {
    saving.value = false;
  }
}

async function openTokens(row: Member) {
  tokenMember.value = row;
  issuedToken.value = "";
  tokenDialog.value = true;
  await loadTokens(row.id);
}

async function loadTokens(memberId: string) {
  tokens.value = (await api.get<Token[]>(`/members/${memberId}/tokens`)).data;
}

async function issueToken() {
  if (!tokenMember.value) return;
  const res = await api.post<{ id: string; label: string; token: string }>(
    `/members/${tokenMember.value.id}/tokens`,
    { label: "web" }
  );
  issuedToken.value = res.data.token;
  await loadTokens(tokenMember.value.id);
}

async function revokeToken(tokenId: string) {
  if (!tokenMember.value) return;
  await api.del(`/tokens/${tokenId}`);
  await loadTokens(tokenMember.value.id);
}

onMounted(load);
</script>

<style scoped>
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
