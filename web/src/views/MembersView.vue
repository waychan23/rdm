<template>
  <div>
    <div class="head">
      <h2>成员 · {{ key }}</h2>
      <el-button type="primary" @click="dialog = true">新增成员</el-button>
    </div>
    <el-table :data="members" border>
      <el-table-column prop="name" label="名称" width="160" />
      <el-table-column prop="type" label="类型" width="100" />
      <el-table-column label="角色">
        <template #default="{ row }">
          <el-tag v-for="r in row.roles" :key="r" size="small" style="margin-right: 4px">
            {{ r }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="活跃" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
            {{ row.is_active ? "是" : "否" }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" title="新增成员" width="460px">
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
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="create">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api";
import type { Member } from "../types";

const props = defineProps<{ key: string }>();
const key = props.key;
const members = ref<Member[]>([]);
const dialog = ref(false);
const saving = ref(false);
const form = reactive({
  name: "",
  type: "human",
  rolesText: "worker",
});

async function load() {
  members.value = (await api.get<Member[]>(`/projects/${key}/members`)).data;
}

async function create() {
  saving.value = true;
  try {
    await api.post(`/projects/${key}/members`, {
      name: form.name,
      type: form.type,
      roles: form.rolesText.split(",").map((r) => r.trim()).filter(Boolean),
    });
    dialog.value = false;
    form.name = "";
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
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
