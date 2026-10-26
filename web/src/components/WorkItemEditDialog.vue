<template>
  <el-dialog
    :model-value="modelValue"
    title="编辑工作项"
    width="560px"
    append-to-body
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <el-form v-if="form" label-position="top" @submit.prevent>
      <el-form-item label="标题">
        <el-input v-model="form.title" />
      </el-form-item>
      <el-form-item label="描述（Markdown）">
        <el-input v-model="form.description_md" type="textarea" :rows="4" />
      </el-form-item>
      <el-form-item label="优先级">
        <el-input-number v-model="form.priority" :min="0" :max="99" controls-position="right" />
      </el-form-item>

      <template v-if="item.kind === 'story'">
        <el-form-item label="验收标准（每行一条）">
          <el-input v-model="acceptance" type="textarea" :rows="3" />
        </el-form-item>
      </template>
      <template v-else-if="item.kind === 'issue'">
        <el-form-item label="严重度">
          <el-select v-model="issue.severity">
            <el-option v-for="s in ['blocker', 'critical', 'major', 'minor', 'trivial']" :key="s" :value="s" :label="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="环境"><el-input v-model="issue.environment" /></el-form-item>
      </template>
      <template v-else-if="item.kind === 'task'">
        <el-form-item label="任务类型">
          <el-select v-model="task.task_type">
            <el-option v-for="t in ['product_design', 'ux_design', 'frontend', 'backend', 'fullstack', 'qa', 'release', 'docs', 'other']" :key="t" :value="t" :label="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="工时（h）">
          <el-input-number v-model="task.est_work_hours" :min="0" :step="0.5" controls-position="right" />
        </el-form-item>
      </template>
    </el-form>
    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { api, errorCause } from "../api";
import type { WorkItem } from "../types";

const props = defineProps<{ modelValue: boolean; item: WorkItem }>();
const emit = defineEmits<{ "update:modelValue": [boolean]; saved: [WorkItem] }>();

const form = reactive({ title: "", description_md: "", priority: 0 });
const acceptance = ref("");
const issue = reactive({ severity: "major", environment: "" });
const task = reactive({ task_type: "other", est_work_hours: 0 });
const saving = ref(false);

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    form.title = props.item.title;
    form.description_md = props.item.description_md ?? "";
    form.priority = props.item.priority ?? 0;
    const f = (props.item.fields ?? {}) as Record<string, unknown>;
    acceptance.value = Array.isArray(f.acceptance_criteria)
      ? (f.acceptance_criteria as string[]).join("\n")
      : "";
    issue.severity = (f.severity as string) || "major";
    issue.environment = (f.environment as string) || "";
    task.task_type = (f.task_type as string) || "other";
    task.est_work_hours = Number(f.est_work_hours ?? 0);
  }
);

function close() {
  emit("update:modelValue", false);
}

async function save() {
  saving.value = true;
  try {
    const payload: Record<string, unknown> = { ...form };
    if (props.item.kind === "story") {
      payload.story = {
        acceptance_criteria: acceptance.value.split("\n").map((s) => s.trim()).filter(Boolean),
      };
    } else if (props.item.kind === "issue") {
      payload.issue = { severity: issue.severity, environment: issue.environment };
    } else if (props.item.kind === "task") {
      payload.task = { task_type: task.task_type, est_work_hours: task.est_work_hours };
    }
    const updated = (await api.patch<WorkItem>(`/work-items/${props.item.display_id}`, payload)).data;
    ElMessage.success("已保存");
    emit("saved", updated);
    close();
  } catch (e) {
    ElMessage.error(errorCause(e)?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}
</script>
