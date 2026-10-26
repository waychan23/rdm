<template>
  <div class="consent-wrap">
    <el-card v-if="info" class="consent-card" shadow="never">
      <div class="consent-title">授权访问 rdm</div>
      <p class="consent-client">
        应用 <strong>{{ info.client.client_name || info.client.client_id }}</strong>
        请求访问你的 rdm 工作区（scope: {{ info.scopes.join(" ") }}）。
      </p>

      <template v-if="info.selectable_members.length">
        <div class="field-label">以哪个身份授权</div>
        <el-radio-group v-model="memberId" class="member-group">
          <el-radio
            v-for="m in info.selectable_members"
            :key="m.id"
            :value="m.id"
            class="member-radio"
          >
            <span>{{ m.name }}</span>
            <el-tag size="small" :type="m.type === 'agent' ? 'warning' : 'info'">
              {{ m.type }}
            </el-tag>
            <span v-if="m.project_key" class="member-project">{{ m.project_key }}</span>
          </el-radio>
        </el-radio-group>
      </template>

      <div class="actions">
        <el-button :loading="loading" @click="decide(false)">拒绝</el-button>
        <el-button type="primary" :loading="loading" @click="decide(true)">允许</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { api, errorCause } from "../api";

interface ConsentInfo {
  client: { client_id: string; client_name: string | null };
  scopes: string[];
  selectable_members: {
    id: string;
    name: string;
    type: string;
    project_key: string | null;
  }[];
}

const route = useRoute();
const info = ref<ConsentInfo | null>(null);
const memberId = ref("");
const loading = ref(false);

onMounted(async () => {
  const id = String(route.params.id);
  try {
    info.value = (await api.get<ConsentInfo>(`/oauth/consent/${id}`)).data;
    memberId.value = info.value.selectable_members[0]?.id ?? "";
  } catch (e) {
    ElMessage.error(errorCause(e)?.message || "无法加载授权请求");
  }
});

async function decide(allow: boolean) {
  if (loading.value) return;
  loading.value = true;
  try {
    const id = String(route.params.id);
    const body: { decision: "allow" | "deny"; member_id?: string } = {
      decision: allow ? "allow" : "deny",
    };
    if (allow) body.member_id = memberId.value;
    const redirect = (
      await api.post<{ redirect_to: string }>(`/oauth/consent/${id}/decision`, body)
    ).data.redirect_to;
    window.location.assign(redirect);
  } catch (e) {
    ElMessage.error(errorCause(e)?.message || "授权失败");
    loading.value = false;
  }
}
</script>

<style scoped>
.consent-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-light);
}
.consent-card {
  width: 440px;
  border-radius: 4px;
}
.consent-title {
  font-size: 18px;
  font-weight: 500;
  margin-bottom: 12px;
}
.consent-client {
  color: var(--el-text-color-regular);
  margin-bottom: 16px;
}
.field-label {
  font: var(--rdm-type-meta);
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}
.member-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 20px;
}
.member-radio {
  display: flex;
  align-items: center;
  gap: 8px;
  height: auto;
}
.member-project {
  color: var(--el-text-color-secondary);
  font: var(--rdm-type-meta);
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
