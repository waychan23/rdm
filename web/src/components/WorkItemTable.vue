<template>
  <div class="wi-table">
    <el-table
      :data="items"
      size="default"
      height="100%"
      @row-click="(row: WorkItem) => emit('open', row)"
    >
      <el-table-column label="标题" min-width="280">
        <template #default="{ row }">
          <div class="title-cell">
            <TypeIcon :kind="row.kind" />
            <span class="display-id rdm-num">{{ row.display_id }}</span>
            <span class="title-text">{{ row.title }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="状态" :width="140">
        <template #default="{ row }">
          <StatusPill :status="row.status" />
        </template>
      </el-table-column>
      <el-table-column label="优先级" :width="110">
        <template #default="{ row }">
          <PriorityRank :priority="row.priority" />
        </template>
      </el-table-column>
      <el-table-column label="负责人" :width="180">
        <template #default="{ row }">
          <PersonCell :name="row.assignee?.name" />
        </template>
      </el-table-column>
      <el-table-column label="创建时间" :width="160">
        <template #default="{ row }">
          <span class="meta">{{ formatDate(row.created_at) }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="pager">
      <span class="total rdm-num">共 {{ total }} 条</span>
      <el-pagination
        layout="prev, pager, next"
        :total="total"
        :page-size="pageSize"
        :current-page="page"
        small
        @current-change="(p: number) => emit('update:page', p)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import StatusPill from "./StatusPill.vue";
import PriorityRank from "./PriorityRank.vue";
import PersonCell from "./PersonCell.vue";
import TypeIcon from "./TypeIcon.vue";
import type { WorkItem } from "../types";

defineProps<{
  items: WorkItem[];
  total: number;
  page: number;
  pageSize: number;
}>();
const emit = defineEmits<{ open: [WorkItem]; "update:page": [number] }>();

function formatDate(iso: string) {
  return iso ? iso.slice(0, 10) : "";
}
</script>

<style scoped>
.wi-table {
  display: flex;
  flex-direction: column;
  height: 100%;
}
:deep(.el-table) {
  --el-table-header-height: var(--rdm-thead-h);
  cursor: pointer;
}
:deep(.el-table th.el-table__cell) {
  height: var(--rdm-thead-h);
  background: var(--rdm-surface-subtle);
  color: var(--rdm-text-3);
  font: var(--rdm-type-meta);
}
:deep(.el-table .el-table__cell) {
  padding: 0 var(--rdm-space-4);
}
.title-cell {
  display: flex;
  align-items: center;
  gap: var(--rdm-space-2);
  height: var(--rdm-row-h);
  font: var(--rdm-type-cell);
}
.display-id {
  color: var(--rdm-accent-strong);
}
.title-text {
  color: var(--rdm-text-1);
}
.meta {
  font: var(--rdm-type-meta);
  color: var(--rdm-text-3);
}
.pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--rdm-space-2) var(--rdm-space-4);
  border-top: 1px solid var(--rdm-border);
}
.total {
  font: var(--rdm-type-meta);
  color: var(--rdm-text-3);
}
</style>
