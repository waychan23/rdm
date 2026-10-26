<template>
  <div>
    <div class="head">
      <h2>成员 · {{ key }}</h2>
      <el-button type="primary" @click="dialog = true">新增成员</el-button>
    </div>
    <el-table :data="members" border>
      <el-table-column prop="name" label="名称" width="140" />
      <el-table-column prop="type" label="类型" width="90" />
      <el-table-column label="角色">
        <template #default="{ row }">
          <el-tag v-for="r in row.roles" :key="r" size="small" style="margin-right: 4px">
            {{ r }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="Webhook" min-width="180">
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
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button
            v-if="row.type === 'human'"
            link
            type="warning"
            @click="resetPassword(row)"
          >重置密码</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" title="新增成员" width="480px">
      <el-form label-width="96px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="form.type">
            <el-radio value="human">human</el-radio>
            <el-radio value="agent">agent</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="角色">
          <el-input v-model="form.rolesText" placeholder="owner,manager,worker（逗号分隔）" />
        </el-form-item>
        <el-form-item v-if="form.type === 'agent'" label="Manager" required>
          <el-select v-model="form.managerId" placeholder="选择同项目 human 负责人" style="width: 100%">
            <el-option v-for="m in humanManagers" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.type === 'human'" label="初始密码">
          <el-input v-model="form.password" placeholder="至少 8 位；留空则不能登录（之后可重置）" />
        </el-form-item>
        <el-form-item label="Email"><el-input v-model="form.email" /></el-form-item>
        <el-form-item label="Webhook URL">
          <el-input v-model="form.notifyWebhook" placeholder="https://…" />
        </el-form-item>
        <el-form-item label="Webhook 格式">
          <el-select v-model="form.notifyFormat">
            <el-option label="generic" value="generic" />
            <el-option label="dingtalk" value="dingtalk" />
            <el-option label="feishu" value="feishu" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="create">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editDialog" title="编辑成员" width="480px">
      <el-form label-width="110px">
        <el-form-item label="角色（逗号）">
          <el-input v-model="edit.rolesText" />
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
          <el-input v-model="edit.notifyWebhook" />
        </el-form-item>
        <el-form-item label="Webhook 格式">
          <el-select v-model="edit.notifyFormat">
            <el-option label="generic" value="generic" />
            <el-option label="dingtalk" value="dingtalk" />
            <el-option label="feishu" value="feishu" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用"><el-switch v-model="edit.isActive" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api";
import type { Member } from "../types";

const key = String(useRoute().params.key);
const members = ref<Member[]>([]);
const dialog = ref(false);
const editDialog = ref(false);
const saving = ref(false);
const form = reactive({
  name: "",
  type: "human",
  rolesText: "worker",
  managerId: "",
  email: "",
  notifyWebhook: "",
  notifyFormat: "generic",
  password: "",
});
const edit = reactive({
  id: "",
  rolesText: "",
  acceptKinds: [] as string[],
  email: "",
  notifyWebhook: "",
  notifyFormat: "generic",
  isActive: true,
});

const humanManagers = computed(() => members.value.filter((m) => m.type === "human"));

async function load() {
  members.value = (await api.get<Member[]>(`/projects/${key}/members`)).data;
}

async function create() {
  if (form.type === "agent" && !form.managerId) {
    ElMessage.warning("agent 必须指定一个同项目 human manager");
    return;
  }
  saving.value = true;
  try {
    await api.post(`/projects/${key}/members`, {
      name: form.name,
      type: form.type,
      roles: form.rolesText.split(",").map((r) => r.trim()).filter(Boolean),
      manager_member_id: form.type === "agent" ? form.managerId : null,
      email: form.email || null,
      notify_webhook: form.notifyWebhook || null,
      notify_webhook_format: form.notifyFormat,
      password: form.type === "human" && form.password ? form.password : null,
    });
    dialog.value = false;
    form.name = "";
    form.managerId = "";
    form.email = "";
    form.notifyWebhook = "";
    form.password = "";
    await load();
  } catch (e) {
    ElMessage.error((e as Error).message);
  } finally {
    saving.value = false;
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

async function saveEdit() {
  saving.value = true;
  try {
    await api.patch(`/members/${edit.id}`, {
      roles: edit.rolesText.split(",").map((r) => r.trim()).filter(Boolean),
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

async function resetPassword(row: Member) {
  try {
    const { value } = await ElMessageBox.prompt(
      `为 ${row.name} 设置新密码（留空则随机生成，至少 8 位）`,
      "重置登录密码",
      { confirmButtonText: "重置", cancelButtonText: "取消", inputPlaceholder: "新密码（可留空）" }
    );
    const res = await api.post<{ password: string }>(`/members/${row.id}/password`, {
      password: value || null,
    });
    await navigator.clipboard.writeText(res.data.password);
    ElMessage.success(`已重置，新密码已复制：${res.data.password}`);
  } catch (e) {
    if (e !== "cancel") ElMessage.error((e as Error).message);
  }
}

onMounted(load);
</script>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
