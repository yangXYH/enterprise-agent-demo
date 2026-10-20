<script setup lang="ts">
import { ref } from 'vue'
import { ElButton, ElMessage, ElUpload } from 'element-plus'
import type { UploadUserFile } from 'element-plus'
import { Download, UploadFilled } from '@element-plus/icons-vue'

const props = defineProps<{
  importApi: string
  templateApi: string
  title: string
  tip?: string
}>()
const emit = defineEmits<{ (e: 'imported', report: any): void }>()

const fileList = ref<UploadUserFile[]>([])
const importing = ref(false)
const report = ref<any>(null)

const doImport = async () => {
  const file = fileList.value[0]
  if (!file?.raw) { ElMessage.warning('请选择文件'); return }
  importing.value = true
  report.value = null
  try {
    const form = new FormData()
    form.append('file', file.raw)
    const resp = await fetch(props.importApi, { method: 'POST', body: form, credentials: 'same-origin' })
    const data = await resp.json()
    if (!resp.ok) { ElMessage.error(data.detail || '导入失败'); return }
    report.value = data
    ElMessage.success('导入完成')
    emit('imported', data)
  } catch (e: any) {
    ElMessage.error(e.message || '导入失败')
  } finally {
    importing.value = false
  }
}

const downloadTemplate = async () => {
  try {
    const resp = await fetch(props.templateApi, { credentials: 'same-origin' })
    if (!resp.ok) { ElMessage.error('模板下载失败'); return }
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = '导入模板.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  } catch { /* */ }
}
</script>

<template>
  <div class="import-block">
    <div class="import-row">
      <el-upload v-model:file-list="fileList" :auto-upload="false" :limit="1" accept=".xlsx"
        :on-change="() => { report = null }">
        <el-button :icon="UploadFilled">选择{{ title }}文件</el-button>
      </el-upload>
      <el-button type="primary" :loading="importing" :disabled="!fileList.length" @click="doImport">开始导入</el-button>
      <el-button :icon="Download" @click="downloadTemplate">下载模板</el-button>
    </div>
    <div v-if="props.tip" class="tip">{{ props.tip }}</div>
    <el-alert v-if="report?.message" :title="report.message" type="success" :closable="false" show-icon style="margin-top: 8px" />
  </div>
</template>

<style scoped>
.import-block { margin-bottom: 14px; }
.import-row { display: flex; gap: 10px; align-items: center; }
.tip { color: light-dark(#94a3b8, var(--text-secondary)); font-size: 12px; margin-top: 6px; }
</style>
