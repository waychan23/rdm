<template>
  <div v-loading="loading">
    <div class="head">
      <h2>工作区 · {{ key }}</h2>
      <el-button type="primary" @click="openCreate">登记工作区</el-button>
    </div>

    <el-table :data="workspaces" border>
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="kind" label="类型" width="120" />
      <el-table-column label="URL">
        <template #default="{ row }">
          <el-link :href="row.url" target="_blank" :underline="false">{{ row.url }}</el-link>
        </template>
      </el-table-column>
      <el-table-column prop="default_branch" label="默认分支" width="110" />
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" :title="form.id ? '编辑工作区' : '登记工作区'" width="460px">
      <el-form label-width="88px">
        <el-form-item label="名称" required><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.kind" style="width: 100%">
            <el-option v-for="k in KINDS" :key="k" :label="k" :value="k" />
          </el-select>
        </el-form-item>
        <el-form-item label="URL" required><el-input v-model="form.url" /></el-form-item>
        <el-form-item label="默认分支"><el-input v-model="form.default_branch" /></el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description_md" type="textarea" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api";
import type { Workspace } from "../types";

const KINDS = ["git_repo", "doc_repo", "design", "other"];
const props = defineProps<{ key: string }>();
const key = props.key;
const loading = ref(false);
const saving = ref(false);
const dialog = ref(false);
const workspaces = ref<Workspace[]>([]);
const form = reactive({
  id: "",
  name: "",
  kind: "git_repo",
  url: "",
  default_branch: "",
  description_md: "",
});

async function load() {
  loading.value = true;
  try {
    workspaces.value = (await api.get<Workspace[]>(`/projects/${key}/workspaces`)).data;
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  Object.assign(form, {
    id: "",
    name: "",
    kind: "git_repo",
    url: "",
    default_branch: "",
    description_md: "",
  });
  dialog.value = true;
}

function openEdit(row: Workspace) {
  Object.assign(form, {
    id: row.id,
    name: row.name,
    kind: row.kind,
    url: row.url,
    default_branch: row.default_branch ?? "",
    description_md: row.description_md ?? "",
  });
  dialog.value = true;
}

async function save() {
  saving.value = true;
  try {
    const payload = {
      name: form.name,
      kind: form.kind,
      url: form.url,
      default_branch: form.default_branch || null,
      description_md: form.description_md || null,
    };
    if (form.id) await api.patch(`/workspaces/${form.id}`, payload);
    else await api.post(`/projects/${key}/workspaces`, payload);
    dialog.value = false;
    await load();
  } catch (e) {
    ElMessage.error((e as Error).message);
  } finally {
    saving.value = false;
  }
}

async function remove(row: Workspace) {
  try {
    await ElMessageBox.confirm(`删除工作区「${row.name}」？软删可恢复。`, "确认");
    await api.del(`/workspaces/${row.id}`);
    await load();
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
</style>
