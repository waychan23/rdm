<template>
  <div>
    <div class="head">
      <h2>Backlog · {{ key }}</h2>
    </div>
    <el-form :inline="true">
      <el-form-item label="类型">
        <el-select v-model="filters.kind" clearable placeholder="全部" style="width: 130px">
          <el-option v-for="k in KINDS" :key="k" :label="k" :value="k" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态">
        <el-input v-model="filters.status" placeholder="如 TODO" clearable style="width: 140px" />
      </el-form-item>
      <el-form-item label="关键词">
        <el-input v-model="filters.q" clearable style="width: 180px" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="load">查询</el-button>
      </el-form-item>
    </el-form>

    <el-table :data="items" border>
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
      <el-table-column prop="priority" label="优先级" width="90" />
      <el-table-column label="负责人" width="140">
        <template #default="{ row }">{{ row.assignee?.name ?? "—" }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import { api } from "../api";
import type { WorkItem } from "../types";

const KINDS = ["epic", "story", "issue", "task"];
const key = String(useRoute().params.key);
const items = ref<WorkItem[]>([]);
const filters = reactive({ kind: "", status: "", q: "" });

async function load() {
  const params = new URLSearchParams();
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.status) params.set("status", filters.status);
  if (filters.q) params.set("q", filters.q);
  items.value = (await api.get<WorkItem[]>(`/projects/${key}/work-items?${params}`)).data;
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
