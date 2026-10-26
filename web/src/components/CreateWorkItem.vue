<template>
  <el-dialog
    :model-value="modelValue"
    title="新建工作项"
    width="520px"
    append-to-body
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <el-form label-position="top" @submit.prevent>
      <el-form-item label="类型">
        <el-radio-group v-model="form.kind">
          <el-radio-button v-for="k in KINDS" :key="k.value" :value="k.value">
            {{ k.label }}
          </el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="标题" required>
        <el-input v-model="form.title" placeholder="工作项标题" @keyup.enter="submit" />
      </el-form-item>
      <el-form-item label="描述（Markdown）">
        <el-input v-model="form.description_md" type="textarea" :rows="4" />
      </el-form-item>
      <el-form-item label="优先级">
        <el-input-number v-model="form.priority" :min="0" :max="99" controls-position="right" />
      </el-form-item>
      <el-form-item v-if="form.kind !== 'epic'" label="父项（display id，可空）">
        <el-input v-model="parentRef" placeholder="如 RDM-12" />
      </el-form-item>

      <template v-if="form.kind === 'story'">
        <el-form-item label="验收标准（每行一条）">
          <el-input v-model="acceptance" type="textarea" :rows="3" />
        </el-form-item>
      </template>
      <template v-else-if="form.kind === 'issue'">
        <el-form-item label="严重度"><el-select v-model="issue.severity"><el-option v-for="s in ['blocker','critical','major','minor','trivial']" :key="s" :value="s" :label="s" /></el-select></el-form-item>
        <el-form-item label="环境"><el-input v-model="issue.environment" /></el-form-item>
        <el-form-item label="复现步骤（每行一条）"><el-input v-model="issue.repro" type="textarea" :rows="3" /></el-form-item>
      </template>
      <template v-else-if="form.kind === 'task'">
        <el-form-item label="任务类型"><el-select v-model="task.task_type"><el-option v-for="t in ['product_design','ux_design','frontend','backend','fullstack','qa','release','docs','other']" :key="t" :value="t" :label="t" /></el-select></el-form-item>
        <el-form-item label="预估工时（h）"><el-input-number v-model="task.est_work_hours" :min="0" :step="0.5" controls-position="right" /></el-form-item>
      </template>
    </el-form>
    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">创建</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { api, errorCause } from "../api";
import type { WorkItem } from "../types";

const props = defineProps<{ modelValue: boolean; projectKey: string }>();
const emit = defineEmits<{
  "update:modelValue": [boolean];
  created: [WorkItem];
}>();

const KINDS = [
  { value: "epic", label: "Epic" },
  { value: "story", label: "需求" },
  { value: "issue", label: "缺陷" },
  { value: "task", label: "任务" },
];

const form = reactive({
  kind: "task",
  title: "",
  description_md: "",
  priority: 0,
});
const parentRef = ref("");
const acceptance = ref("");
const issue = reactive({ severity: "major", environment: "", repro: "" });
const task = reactive({ task_type: "other", est_work_hours: 0 });
const saving = ref(false);

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      form.title = "";
      form.description_md = "";
      form.priority = 0;
      parentRef.value = "";
      acceptance.value = "";
    }
  }
);

function close() {
  emit("update:modelValue", false);
}

async function submit() {
  if (!form.title.trim()) {
    ElMessage.warning("请填写标题");
    return;
  }
  saving.value = true;
  try {
    const payload: Record<string, unknown> = { ...form };
    if (parentRef.value.trim()) payload.parent = parentRef.value.trim();
    if (form.kind === "story" && acceptance.value.trim())
      payload.acceptance_criteria = acceptance.value.split("\n").map((s) => s.trim()).filter(Boolean);
    if (form.kind === "issue") payload.issue = { ...issue, repro_steps: issue.repro.split("\n").filter(Boolean) };
    if (form.kind === "task") payload.task = { ...task };
    const item = (
      await api.post<WorkItem>(`/projects/${props.projectKey}/work-items`, payload)
    ).data;
    ElMessage.success(`已创建 ${item.display_id}`);
    emit("created", item);
    close();
  } catch (e) {
    ElMessage.error(errorCause(e)?.message || "创建失败");
  } finally {
    saving.value = false;
  }
}
</script>
