<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  ElButton,
  ElCol,
  ElDatePicker,
  ElInput,
  ElInputNumber,
  ElMessage,
  ElMessageBox,
  ElRow,
  ElTable,
  ElTableColumn,
  ElTag,
  ElTabs,
  ElTabPane,
  ElUpload,
  ElPagination,
  ElForm,
  ElFormItem,
  ElSelect,
  ElOption,
  type UploadFile,
  type UploadRawFile,
  type UploadUserFile,
} from 'element-plus'
import { Delete, Plus, Search, UploadFilled, Download, Clock, RefreshRight } from '@element-plus/icons-vue'
import * as XLSX from 'xlsx'
import request from '../utils/request'

interface ResumeRow {
  name: string
  education: string
  skills: string[]
  experience: string
  match_score: number | string
  ai_review: string
}

interface HistoryRow {
  id: number
  job_title: string
  jd_text: string
  filename: string
  name: string
  education: string
  skills: string[]
  experience: string
  match_score: number
  ai_review: string
  created_at: string
}

interface HistoryResponse {
  items: HistoryRow[]
  total: number
  page: number
  page_size: number
}

interface ApiResponse<T = unknown> {
  code?: number
  data?: T
  message?: string
}

// ── Tab state ─────────────────────────────────────────────────────────────────
const activeTab = ref('filter')

// ── Filter tab state ──────────────────────────────────────────────────────────
const jobTitle = ref('')
const jdText = ref('')
const fileList = ref<UploadUserFile[]>([])
const selectedFiles = ref<UploadRawFile[]>([])
const tableRows = ref<ResumeRow[]>([])
const filtering = ref(false)

interface HrJobTemplate {
  id: number
  job_name: string
  job_info: string
  created_at: string
  updated_at: string
}

const jobTemplates = ref<HrJobTemplate[]>([])
const selectedTemplateId = ref<number | null>(null)

const fetchJobTemplates = async (): Promise<void> => {
  try {
    const response = await request.get('/hr/job-templates') as unknown as { items: HrJobTemplate[] }
    const items = Array.isArray(response?.items) ? response.items : []
    jobTemplates.value = items.map((t: HrJobTemplate) => ({
      ...t,
      id: typeof t.id === 'number' ? t.id : Number(t.id ?? 0),
    }))
  } catch {
    jobTemplates.value = []
  }
}

const onSaveTemplate = async () => {
  const name = jobTitle.value.trim()
  if (!name) {
    ElMessage.warning('请先填写岗位名称')
    return
  }
  try {
    const payload = await request.post('/hr/job-templates', {
      job_name: name,
      job_info: jdText.value,
    }) as ApiResponse<HrJobTemplate>
    ElMessage.success((payload as { message?: string }).message || '已保存为常用模板')
    await fetchJobTemplates()
    selectedTemplateId.value = payload?.data?.id ?? null
  } catch {
    // Error shown by request interceptor
  }
}

const onClearInputs = () => {
  jobTitle.value = ''
  jdText.value = ''
  selectedTemplateId.value = null
  ElMessage.info('已清空')
}

const onDeleteTemplate = async (template: HrJobTemplate, event: Event) => {
  event.stopPropagation()
  try {
    await ElMessageBox.confirm('确认删除该模板？', '提示', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await request.delete(`/hr/job-templates/${template.id}`)
    ElMessage.success('模板已删除')
    await fetchJobTemplates()
    if (jobTitle.value === template.job_name) {
      jobTitle.value = ''
      jdText.value = ''
    }
  } catch {
    // Error shown by request interceptor
  }
}

const onTemplateSelect = (id: number | null) => {
  if (id === null) return
  const template = jobTemplates.value.find((t) => t.id === id)
  if (template) {
    jobTitle.value = template.job_name
    jdText.value = template.job_info
    ElMessage.success(`已套用模板：${template.job_name}`)
  }
}

const canFilter = computed(
  () => Boolean(jobTitle.value.trim() && jdText.value.trim() && selectedFiles.value.length) && !filtering.value,
)
const canExport = computed(() => tableRows.value.length > 0 && !filtering.value)

// ── History tab state ─────────────────────────────────────────────────────────
const historyRows = ref<HistoryRow[]>([])
const historyTotal = ref(0)
const historyPage = ref(1)
const historyPageSize = ref(20)
const historyLoading = ref(false)
const jobTitleOptions = ref<string[]>([])

// ── Multi-condition filter form ────────────────────────────────────────────────
const searchForm = ref({
  jobTitle: '',
  education: '',
  minScore: null as number | null,
})

// dateRange: [startDate, endDate] — bound to a single daterange picker
const dateRange = ref<[string, string] | null>(null)

const EDUCATION_OPTIONS = [
  { label: '全部', value: '' },
  { label: '本科', value: '本科' },
  { label: '硕士', value: '硕士' },
  { label: '大专', value: '大专' },
  { label: '博士', value: '博士' },
  { label: '高中', value: '高中' },
  { label: '其他', value: '其他' },
]

const DATE_SHORTCUTS = [
  { text: '今天', value: () => [new Date(), new Date()] },
  { text: '近7天', value: () => { const d = new Date(); d.setDate(d.getDate() - 6); return [d, new Date()]; } },
  { text: '近30天', value: () => { const d = new Date(); d.setDate(d.getDate() - 29); return [d, new Date()]; } },
  { text: '本月', value: () => { const d = new Date(); d.setDate(1); return [d, new Date()]; } },
]

// ── Normalization ──────────────────────────────────────────────────────────────
const normalizeResumeRow = (payload: unknown, fallbackName: string): ResumeRow => {
  const response = payload as ApiResponse<ResumeRow>
  const data = response?.data ?? payload
  const row = data && typeof data === 'object' ? (data as Partial<ResumeRow>) : {}

  return {
    name: String(row.name ?? fallbackName),
    education: String(row.education ?? ''),
    skills: Array.isArray(row.skills)
      ? row.skills.map((skill) => String(skill)).filter(Boolean)
      : String(row.skills ?? '')
        .split(/[,，、]/)
        .map((s) => s.trim())
        .filter(Boolean),
    experience: String(row.experience ?? ''),
    match_score: row.match_score ?? '',
    ai_review: String(row.ai_review ?? ''),
  }
}

// ── File handling ─────────────────────────────────────────────────────────────
const beforeUpload = () => false

const syncSelectedFiles = (files: UploadUserFile[]) => {
  selectedFiles.value = files
    .map((f) => f.raw)
    .filter((f): f is UploadRawFile => Boolean(f))
}

const handleFileChange = (_uploadFile: UploadFile, files: UploadUserFile[]) => {
  fileList.value = files
  syncSelectedFiles(files)
}

const handleFileRemove = (_uploadFile: UploadFile, files: UploadUserFile[]) => {
  fileList.value = files
  syncSelectedFiles(files)
}

const clearFiles = () => {
  jobTitle.value = ''
  jdText.value = ''
  fileList.value = []
  selectedFiles.value = []
  tableRows.value = []
}

// ── Submit filter ──────────────────────────────────────────────────────────────
const submitFilter = async () => {
  if (!jobTitle.value.trim()) {
    ElMessage.warning('请先填写岗位名称')
    return
  }
  if (!jdText.value.trim()) {
    ElMessage.warning('请先粘贴岗位 JD')
    return
  }
  if (!selectedFiles.value.length) {
    ElMessage.warning('请先上传简历')
    return
  }

  filtering.value = true
  tableRows.value = []

  try {
    const results: ResumeRow[] = []
    let failedCount = 0

    // 公司 AI 接入点默认按单通道稳定处理。逐份提交可避免批量上传时
    // 同时挤压模型连接，并且一份失败不会影响其他简历的结果。
    for (const file of selectedFiles.value) {
      const formData = new FormData()
      formData.append('job_title', jobTitle.value.trim())
      formData.append('jd', jdText.value.trim())
      formData.append('file', file)

      try {
        const response = await request.post('/resume/filter', formData)
        const raw = (response as ApiResponse<ResumeRow>)?.data ?? response
        results.push(normalizeResumeRow(raw, file.name))
        tableRows.value = [...results]
      } catch {
        failedCount++
      }
    }

    tableRows.value = results

    if (results.length) {
      ElMessage.success(`解析完成 ${results.length} 份简历，已自动存入历史记录`)
    }
    if (failedCount) {
      ElMessage.warning(`${failedCount} 份简历解析失败，请检查格式后重试`)
    }
  } catch {
    // Error shown by request interceptor
  } finally {
    filtering.value = false
  }
}

// ── Excel export (current tab results) ────────────────────────────────────────
const exportExcel = () => {
  if (!tableRows.value.length) return

  const rows = tableRows.value.map((r) => ({
    姓名: r.name,
    最高学历: r.education,
    核心技术栈: Array.isArray(r.skills) ? r.skills.join('、') : String(r.skills),
    前东家_学校: r.experience,
    AI匹配度得分: r.match_score,
    AI深度诊断报告: r.ai_review,
  }))

  const ws = XLSX.utils.json_to_sheet(rows)
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, '筛选结果')
  ws['!cols'] = [
    { wch: 12 }, { wch: 22 }, { wch: 30 }, { wch: 35 }, { wch: 10 }, { wch: 60 },
  ]

  const dateStr = new Date().toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).replace(/\//g, '-')
  XLSX.writeFile(wb, `AI简历筛选结果_${dateStr}.xlsx`)
  ElMessage.success(`导出成功：AI简历筛选结果_${dateStr}.xlsx`)
}

// ── History API ────────────────────────────────────────────────────────────────
const fetchJobTitles = async () => {
  try {
    const response = await request.get('/resume/history/job-titles')
    const raw = (response as ApiResponse<string[]>)?.data ?? response
    jobTitleOptions.value = Array.isArray(raw) ? raw : []
  } catch {
    jobTitleOptions.value = []
  }
}

const fetchHistory = async (page = 1) => {
  console.log('[DEBUG] fetchHistory called, page:', page, 'filters:', searchForm.value)
  historyLoading.value = true
  try {
    const params: Record<string, unknown> = { page, page_size: historyPageSize.value }

    // Job title — only send if non-empty
    if (searchForm.value.jobTitle && searchForm.value.jobTitle.trim()) {
      params.job_title = searchForm.value.jobTitle.trim()
    }

    // Education — only send if not blank (not "全部")
    if (searchForm.value.education) {
      params.education = searchForm.value.education
    }

    // Min score — only send if set and positive
    if (searchForm.value.minScore !== null && searchForm.value.minScore > 0) {
      params.min_score = searchForm.value.minScore
    }

    // Date range — single daterange array: [start, end]
    if (dateRange.value && dateRange.value.length === 2) {
      params.start_date = dateRange.value[0]
      params.end_date = dateRange.value[1]
    }

    console.log('[DEBUG] fetchHistory params:', params)
    const response = await request.get('/resume/history', { params })
    console.log('[DEBUG] fetchHistory response:', response)
    const raw = ((response as ApiResponse<HistoryResponse>)?.data ?? response) as HistoryResponse
    const newRows = Array.isArray(raw.items) ? raw.items : []
    historyRows.value = [...newRows]
    historyTotal.value = typeof raw.total === 'number' ? raw.total : 0
    historyPage.value = typeof raw.page === 'number' ? raw.page : 1
  } catch (err) {
    console.error('[DEBUG] fetchHistory error:', err)
    historyRows.value = []
    historyTotal.value = 0
  } finally {
    historyLoading.value = false
  }
}

const onHistoryPageChange = (page: number) => fetchHistory(page)

const onHistoryPageSizeChange = (size: number) => {
  historyPageSize.value = size
  historyPage.value = 1
  fetchHistory(1)
}

// Trigger search from any filter control (Enter key or select change)
const onHistorySearch = () => {
  console.log('[DEBUG] trigger search, filters:', searchForm.value)
  historyPage.value = 1
  fetchHistory(1)
}

// Reset all filters and reload full history
const onResetFilters = () => {
  searchForm.value = {
    jobTitle: '',
    education: '',
    minScore: null,
  }
  dateRange.value = null
  historyPage.value = 1
  fetchHistory(1)
}

const exportHistoryExcel = () => {
  if (!historyRows.value.length) return

  const rows = historyRows.value.map((r) => ({
    ID: r.id,
    招聘岗位: r.job_title,
    姓名: r.name,
    最高学历: r.education,
    核心技术栈: Array.isArray(r.skills) ? r.skills.join('、') : String(r.skills),
    前东家_学校: r.experience,
    AI匹配度得分: r.match_score,
    AI深度诊断报告: r.ai_review,
    解析时间: r.created_at,
  }))

  const ws = XLSX.utils.json_to_sheet(rows)
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, '历史记录')
  ws['!cols'] = [
    { wch: 8 }, { wch: 18 }, { wch: 12 }, { wch: 22 }, { wch: 30 }, { wch: 35 },
    { wch: 10 }, { wch: 60 }, { wch: 22 },
  ]

  const dateStr = new Date().toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).replace(/\//g, '-')
  XLSX.writeFile(wb, `AI简历筛选历史记录_${dateStr}.xlsx`)
  ElMessage.success('历史记录已导出')
}

// ── Tab switch ────────────────────────────────────────────────────────────────
const onTabChange = (tabName: string | number) => {
  if (tabName === 'history') {
    fetchJobTitles()
    if (!historyRows.value.length) {
      fetchHistory(1)
    }
  }
}

// ── Form state persistence across page switches ────────────────────────────────
const _SESSION_KEY = 'hr_filter_form_state'

const _restoreFormState = (): void => {
  try {
    const raw = sessionStorage.getItem(_SESSION_KEY)
    if (!raw) return
    const saved = JSON.parse(raw) as { jobTitle?: string; jdText?: string }
    if (saved.jobTitle) jobTitle.value = saved.jobTitle
    if (saved.jdText) jdText.value = saved.jdText
  } catch { /* ignore */ }
}

watch(
  [jobTitle, jdText],
  ([title, jd]) => {
    try {
      sessionStorage.setItem(_SESSION_KEY, JSON.stringify({ jobTitle: title, jdText: jd }))
    } catch { /* ignore quota errors */ }
  },
  { deep: true },
)

// ── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(() => {
  _restoreFormState()
  fetchJobTemplates()
  fetchHistory(1)
})
</script>

<template>
  <section class="resume-filter-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">HR Resume Screening</p>
        <h1>简历筛选</h1>
        <p class="subtitle">批量上传简历，AI 深度解析并自动存入数据库，支持多岗位管理。</p>
      </div>
    </header>

    <el-tabs v-model="activeTab" class="resume-tabs" @tab-change="onTabChange">
      <!-- ── Tab 1: 简历智能初筛 ─────────────────────────────────────────── -->
      <el-tab-pane label="简历智能初筛" name="filter">
        <div class="tab-filter">

          <!-- Template toolbar -->
          <div class="template-toolbar">
            <span class="template-toolbar-label">常用岗位模板：</span>
            <el-select
              v-model="selectedTemplateId"
              class="template-toolbar-select"
              clearable
              filterable
              placeholder="选择模板自动填充"
              @change="onTemplateSelect"
            >
              <el-option
                v-for="tpl in jobTemplates"
                :key="tpl.id"
                :label="tpl.job_name"
                :value="tpl.id"
              >
                <div class="template-option-row">
                  <span class="template-option-label">{{ tpl.job_name }}</span>
                  <span
                    class="template-option-delete"
                    :title="'删除该模板'"
                    @click="onDeleteTemplate(tpl, $event)"
                  >
                    <el-icon><Delete /></el-icon>
                    <span>删除</span>
                  </span>
                </div>
              </el-option>
            </el-select>
            <el-button type="primary" plain @click="onSaveTemplate">
              <el-icon><Plus /></el-icon>
              保存为常用模板
            </el-button>
            <el-button plain @click="onClearInputs">清空当前输入</el-button>
            <span class="template-toolbar-counter">共 {{ jobTemplates.length }} 个模板</span>
          </div>

          <el-row :gutter="20">
            <!-- 岗位信息卡片：岗位名称 + JD -->
            <el-col :span="12">
            <section class="input-panel input-panel--job">
              <div class="panel-header">
                <span class="panel-title">岗位信息</span>
                <div class="panel-actions">
                  <el-button :icon="Download" :disabled="!canExport" size="large" type="success" @click="exportExcel">
                    导出 Excel
                  </el-button>
                  <el-button :icon="Delete" :disabled="filtering || (!fileList.length && !tableRows.length)" size="large" @click="clearFiles">
                    清空
                  </el-button>
                  <el-button :icon="Search" :disabled="!canFilter" :loading="filtering" size="large" type="primary" @click="submitFilter">
                    开始筛选
                  </el-button>
                </div>
              </div>
              <div class="jd-block">
                <el-input
                  v-model="jobTitle"
                  class="job-title-input"
                  :disabled="filtering"
                  maxlength="100"
                  placeholder="请输入岗位名称（如：数据分析师）"
                />
                <el-input
                  v-model="jdText"
                  class="jd-textarea"
                  :disabled="filtering"
                  :rows="12"
                  maxlength="8000"
                  placeholder="粘贴岗位职责、任职要求、加分项等内容"
                  resize="none"
                  show-word-limit
                  type="textarea"
                />
              </div>
            </section>
            </el-col>

            <!-- 简历上传卡片 -->
            <el-col :span="12">
            <section class="input-panel input-panel--upload">
              <div class="panel-header">
                <span class="panel-title">批量简历</span>
                <span class="jd-char-count">{{ selectedFiles.length }} 份</span>
              </div>
              <el-upload
                v-model:file-list="fileList"
                accept=".pdf,.docx"
                action="#"
                :auto-upload="false"
                :before-upload="beforeUpload"
                drag
                :disabled="filtering"
                multiple
                :on-change="handleFileChange"
                :on-remove="handleFileRemove"
              >
                <el-icon class="upload-icon"><UploadFilled /></el-icon>
                <div class="upload-title">拖拽简历到此处，或点击选择文件</div>
                <div class="upload-hint">支持批量上传 PDF、DOCX 简历</div>
              </el-upload>
            </section>
            </el-col>
          </el-row>

          <!-- 结果表格 -->
          <main class="table-panel">
            <el-table
              v-loading="filtering"
              :data="tableRows"
              border
              class="resume-table"
              :default-sort="{ prop: 'match_score', order: 'descending' }"
              empty-text="暂无筛选结果"
              stripe
            >
              <el-table-column label="姓名" min-width="120" prop="name" show-overflow-tooltip />
              <el-table-column label="最高学历" min-width="150" prop="education" show-overflow-tooltip />
              <el-table-column label="核心技术栈" min-width="260">
                <template #default="{ row }">
                  <span class="skill-tags">
                    <el-tag
                      v-for="tag in (Array.isArray(row.skills) ? row.skills : [])"
                      :key="tag"
                      class="skill-tag"
                      size="small"
                      type="info"
                    >
                      {{ tag }}
                    </el-tag>
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="前东家/学校" min-width="220">
                <template #default="{ row }">
                  <span class="experience-cell" style="white-space: pre-line;">{{ row.experience }}</span>
                </template>
              </el-table-column>
              <el-table-column align="right" label="AI匹配度得分" min-width="140" prop="match_score" sortable />
              <el-table-column label="AI深度诊断报告" min-width="380">
                <template #default="{ row }">
                  <span style="white-space: pre-line;">{{ row.ai_review }}</span>
                </template>
              </el-table-column>
            </el-table>
          </main>
        </div>
      </el-tab-pane>

      <!-- ── Tab 2: 历史筛选记录 ─────────────────────────────────────────── -->
      <el-tab-pane name="history">
        <template #label>
          <span class="tab-label">
            <el-icon><Clock /></el-icon>
            历史筛选记录
          </span>
        </template>

        <div class="tab-history">
          <div class="history-toolbar">
            <el-form :inline="true" size="default" class="filter-form" @submit.prevent="onHistorySearch">
              <!-- 岗位筛选 -->
              <el-form-item label="岗位名称" class="filter-form-item filter-form-item--job">
                <el-select
                  v-model="searchForm.jobTitle"
                  class="filter-select filter-select--job"
                  clearable
                  placeholder="全部岗位"
                >
                  <el-option
                    v-for="title in jobTitleOptions"
                    :key="title"
                    :label="title"
                    :value="title"
                  />
                </el-select>
              </el-form-item>

              <!-- 学历筛选 -->
              <el-form-item label="最高学历" class="filter-form-item">
                <el-select
                  v-model="searchForm.education"
                  class="filter-select"
                  clearable
                  placeholder="全部"
                >
                  <el-option
                    v-for="opt in EDUCATION_OPTIONS"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
              </el-form-item>

              <!-- 最低分数 -->
              <el-form-item label="最低分" class="filter-form-item">
                <el-input-number
                  v-model="searchForm.minScore"
                  class="filter-number"
                  :max="100"
                  :min="0"
                  :controls="false"
                  placeholder="0~100"
                />
              </el-form-item>

              <!-- 时间范围 -->
              <el-form-item label="解析时间" class="filter-form-item filter-form-item--date">
                <el-date-picker
                  v-model="dateRange"
                  class="filter-date-range"
                  type="daterange"
                  range-separator="至"
                  start-placeholder="开始日期"
                  end-placeholder="结束日期"
                  format="YYYY-MM-DD"
                  value-format="YYYY-MM-DD"
                  :shortcuts="DATE_SHORTCUTS"
                />
              </el-form-item>

              <!-- 查询 + 重置 -->
              <el-form-item class="filter-form-item filter-form-item--actions">
                <el-button class="btn-search" type="primary" @click="onHistorySearch">
                  <el-icon><Search /></el-icon>
                  查询
                </el-button>
                <el-button class="btn-reset" @click="onResetFilters">
                  <el-icon><RefreshRight /></el-icon>
                  重置
                </el-button>
              </el-form-item>
            </el-form>

            <div class="toolbar-right">
              <span class="history-count">
                共 <strong>{{ historyTotal }}</strong> 条记录
              </span>
              <el-button :icon="Download" :disabled="!historyRows.length" type="success" @click="exportHistoryExcel">
                导出 Excel
              </el-button>
            </div>
          </div>

          <el-table
            v-loading="historyLoading"
            :data="historyRows"
            border
            class="resume-table"
            :default-sort="{ prop: 'match_score', order: 'descending' }"
            empty-text="暂无历史记录"
            stripe
          >
            <!-- <el-table-column label="ID" min-width="65" prop="id" /> -->
            <el-table-column label="招聘岗位" min-width="130" prop="job_title" show-overflow-tooltip>
              <template #default="{ row }">
                <el-tag type="warning" size="small">{{ row.job_title }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="姓名" min-width="110" prop="name" show-overflow-tooltip />
            <el-table-column label="最高学历" min-width="150" prop="education" show-overflow-tooltip />
            <el-table-column label="核心技术栈" min-width="220">
              <template #default="{ row }">
                <span class="skill-tags">
                  <el-tag
                    v-for="tag in (Array.isArray(row.skills) ? row.skills : [])"
                    :key="tag"
                    class="skill-tag"
                    size="small"
                    type="info"
                  >
                    {{ tag }}
                  </el-tag>
                </span>
              </template>
            </el-table-column>
            <el-table-column label="前东家/学校" min-width="200">
              <template #default="{ row }">
                <span class="experience-cell" style="white-space: pre-line; font-size: 13px;">{{ row.experience }}</span>
              </template>
            </el-table-column>
            <el-table-column align="right" label="AI匹配分" min-width="110" prop="match_score" sortable>
              <template #default="{ row }">
                <el-tag
                  :type="Number(row.match_score) >= 70 ? 'success' : Number(row.match_score) >= 50 ? 'warning' : 'danger'"
                  size="small"
                >
                  {{ row.match_score }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="AI深度诊断报告" min-width="340">
              <template #default="{ row }">
                <span style="white-space: pre-line; font-size: 13px;">{{ row.ai_review }}</span>
              </template>
            </el-table-column>
            <el-table-column label="解析时间" min-width="165" prop="created_at" />
          </el-table>

          <div class="history-pagination">
            <el-pagination
              v-model:current-page="historyPage"
              v-model:page-size="historyPageSize"
              :page-sizes="[10, 20, 50, 100]"
              :total="historyTotal"
              background
              layout="total, sizes, prev, pager, next"
              @current-change="onHistoryPageChange"
              @size-change="onHistoryPageSizeChange"
            />
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </section>
</template>

<style scoped>
/* ── Page shell ──────────────────────────────────────────────────────────── */
.resume-filter-page {
  min-height: 100vh;
  padding: 28px 28px 36px;
  color: var(--text-primary);
  background: var(--app-bg);
  transition: background 0.3s ease, color 0.3s ease;
}

/* ── Page header ─────────────────────────────────────────────────────────── */
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 22px;
}

.eyebrow {
  margin: 0 0 6px;
  color: var(--primary);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  color: var(--text-heading);
  font-size: 28px;
  line-height: 1.2;
  font-weight: 700;
}

.subtitle {
  margin: 6px 0 0;
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.5;
}

/* ── Tabs ─────────────────────────────────────────────────────────────────── */
.resume-tabs :deep(.el-tabs__header) {
  margin-bottom: 20px;
}

.resume-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background: var(--border-color);
}

.resume-tabs :deep(.el-tabs__item) {
  font-size: 14px;
  font-weight: 600;
  padding: 0 20px;
  height: 40px;
  line-height: 40px;
  color: var(--text-secondary);
}

.resume-tabs :deep(.el-tabs__item.is-active) {
  color: var(--primary);
  font-weight: 700;
}

.resume-tabs :deep(.el-tabs__active-bar) {
  background-color: var(--primary);
  height: 3px;
  border-radius: 2px;
}

.tab-label {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* ── Filter tab layout ────────────────────────────────────────────────────── */
.tab-filter {
  display: flex;
  flex-direction: column;
  gap: 0;
}

/* ── Input panels (both cards) ────────────────────────────────────────────── */
.input-panel {
  height: 100%;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: var(--app-surface);
  box-shadow: var(--shadow-sm);
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  transition: background 0.3s ease, border-color 0.3s ease;
}

.input-panel--job {
  padding: 18px 20px 20px;
}

.input-panel--upload {
  padding: 18px 20px 18px;
}

/* ── Panel header: title + actions row ─────────────────────────────────────── */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  flex-shrink: 0;
}

.panel-title {
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.01em;
}

.input-panel--job .panel-title {
  font-size: 16px;
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-actions :deep(.el-button) {
  min-height: 44px;
  padding: 0 16px;
  font-size: 14px;
}

.jd-char-count {
  color: var(--text-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

/* ── JD block: title input + textarea stacked ─────────────────────────────── */
.jd-block {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
}

.job-title-input :deep(.el-input__wrapper) {
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  box-shadow: 0 0 0 1px var(--input-border) inset;
  transition: box-shadow 0.2s;
}

.job-title-input :deep(.el-input__wrapper:hover),
.job-title-input :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 2px var(--primary) inset !important;
}

.jd-textarea :deep(.el-textarea__inner) {
  flex: 1;
  font-size: 13.5px;
  line-height: 1.8;
  color: var(--text-primary);
  border-radius: 8px;
  padding: 12px 14px;
  box-shadow: 0 0 0 1px var(--input-border) inset;
  resize: none;
  transition: box-shadow 0.2s;
  min-height: unset !important;
}

.jd-textarea :deep(.el-textarea__inner:hover),
.jd-textarea :deep(.el-textarea__inner:focus) {
  box-shadow: 0 0 0 2px var(--primary) inset !important;
}

/* ── Upload drag area ──────────────────────────────────────────────────────── */
.input-panel--upload :deep(.el-upload),
.input-panel--upload :deep(.el-upload-dragger) {
  width: 100%;
  flex: 1;
  border-radius: 10px;
  border: 1.5px dashed var(--border-color);
  background: var(--app-surface-2);
  transition: border-color 0.2s, background 0.2s;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: unset;
  height: 100%;
}

.input-panel--upload :deep(.el-upload-dragger:hover),
.input-panel--upload :deep(.el-upload-dragger.is-dragover) {
  border-color: var(--primary);
  background: light-dark(#f0fdf9, var(--primary-surface-2));
}

.upload-icon {
  color: var(--text-muted);
  font-size: 52px;
  line-height: 1;
  margin-bottom: 10px;
  transition: color 0.2s;
}

.el-upload-dragger:hover .upload-icon,
.el-upload-dragger.is-dragover .upload-icon {
  color: var(--primary);
}

.upload-title {
  margin-top: 4px;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 600;
  text-align: center;
  line-height: 1.4;
}

.upload-hint {
  margin-top: 5px;
  color: var(--text-muted);
  font-size: 12px;
  text-align: center;
}

/* ── Results table panel ─────────────────────────────────────────────────── */
.table-panel {
  margin-top: 18px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: var(--app-surface);
  padding: 18px 20px;
  box-shadow: var(--shadow-sm);
  transition: background 0.3s ease, border-color 0.3s ease;
}

/* ── History tab ──────────────────────────────────────────────────────────── */
.tab-history {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.history-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 18px;
  background: var(--app-surface);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  box-shadow: var(--shadow-sm);
  flex-wrap: wrap;
  transition: background 0.3s ease, border-color 0.3s ease;
}

/* ── Inline filter form ───────────────────────────────────────────────────── */
.filter-form {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 4px 12px;
  flex: 1;
}

.filter-form-item {
  margin-bottom: 0;
}

.filter-form-item :deep(.el-form-item__label) {
  font-size: 13px;
  font-weight: 600;
  color: var(--table-header-text);
  padding: 0 6px 0 0;
  line-height: 36px;
}

.filter-form-item--job :deep(.el-form-item__label) {
  min-width: 70px;
}

.filter-select--job {
  min-width: 180px;
}

/* Shared input/select/number control base */
.filter-input,
.filter-select,
.filter-number,
.filter-date-start,
.filter-date-end {
  min-width: 140px;
  flex: 1;
}

.filter-input :deep(.el-input__wrapper),
.filter-select :deep(.el-select__wrapper),
.filter-number :deep(.el-input__wrapper) {
  border-radius: 8px;
  box-shadow: 0 0 0 1px var(--input-border) inset;
  min-height: 36px;
  font-size: 13px;
  transition: box-shadow 0.2s;
}

.filter-input :deep(.el-input__wrapper:hover),
.filter-input :deep(.el-input__wrapper.is-focus),
.filter-select :deep(.el-select__wrapper:hover),
.filter-select :deep(.el-select__wrapper.is-focused),
.filter-number :deep(.el-input__wrapper:hover),
.filter-number :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 2px var(--primary) inset !important;
}

.filter-number {
  min-width: 90px;
}

.filter-number :deep(.el-input__inner) {
  text-align: left;
  font-size: 13px;
}

/* Date range — single unified daterange picker */
.filter-date-range {
  min-width: 260px;
}

.filter-date-range :deep(.el-range-editor.el-input__wrapper) {
  border-radius: 8px;
  box-shadow: 0 0 0 1px var(--input-border) inset;
  min-height: 36px;
  font-size: 13px;
  transition: box-shadow 0.2s;
}

.filter-date-range :deep(.el-range-editor:hover .el-input__wrapper),
.filter-date-range :deep(.el-range-editor.is-focus .el-input__wrapper) {
  box-shadow: 0 0 0 2px var(--primary) inset !important;
}

.filter-date-range :deep(.el-range__icon) {
  color: var(--text-muted);
}

.filter-date-range :deep(.el-range__close-icon) {
  color: var(--text-muted);
}

/* Query + Reset buttons */
.filter-form-item--actions {
  margin-left: 4px;
}

.filter-form-item--actions :deep(.el-form-item__content) {
  display: flex;
  gap: 8px;
}

.btn-search {
  min-width: 88px;
  height: 36px;
  background: var(--primary);
  border-color: var(--primary);
  font-size: 13px;
  font-weight: 600;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 5px;
  transition: background 0.2s, border-color 0.2s;
}

.btn-search:hover {
  background: var(--primary-hover);
  border-color: var(--primary-hover);
}

.btn-reset {
  min-width: 80px;
  height: 36px;
  font-size: 13px;
  font-weight: 600;
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 5px;
}

/* Right side of toolbar: count badge + export */
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-shrink: 0;
}

.history-search {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  max-width: 100%;
  flex-wrap: wrap;
}

.search-input :deep(.el-input__wrapper) {
  border-radius: 8px;
  box-shadow: 0 0 0 1px var(--input-border) inset;
}

.history-search-input,
.history-date-picker,
.search-input {
  min-width: 160px;
  flex: 1;
}

.history-date-picker {
  min-width: 240px;
}

.history-search-button {
  min-width: 90px;
  height: 40px;
}

.history-count {
  color: var(--text-secondary);
  font-size: 13px;
  white-space: nowrap;
}

.history-count strong {
  color: var(--primary);
  font-size: 16px;
  font-weight: 700;
}

.history-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 6px 0;
}

/* ── Shared table styles ─────────────────────────────────────────────────── */
.resume-table {
  border-radius: 10px;
  overflow: hidden;
}

.resume-table :deep(.el-table__header th) {
  color: var(--table-header-text);
  background: var(--table-header-bg);
  font-weight: 700;
  font-size: 13px;
  letter-spacing: 0.01em;
  padding: 12px 8px;
}

.resume-table :deep(.el-table__cell) {
  padding: 10px 8px;
  font-size: 13px;
  color: var(--text-primary);
}

.resume-table :deep(.el-table__row:hover > td) {
  background: var(--app-surface-2) !important;
}

.skill-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.skill-tag {
  margin: 1px 0;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.01em;
  border-color: var(--input-border);
  color: var(--table-header-text);
}

.experience-cell {
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--table-header-text);
}

/* ── Responsive ───────────────────────────────────────────────────────────── */
@media (max-width: 980px) {
  .resume-filter-page {
    padding: 16px;
  }

  .page-header {
    flex-direction: column;
    gap: 12px;
  }

  .el-col {
    width: 100% !important;
  }

  .panel-header {
    flex-wrap: wrap;
    gap: 8px;
  }

  .panel-actions {
    flex-wrap: wrap;
  }

  .history-toolbar {
    flex-wrap: wrap;
  }

  .history-search {
    max-width: 100%;
    width: 100%;
  }
}

/* ── Template toolbar ───────────────────────────────────────────────────────── */
.template-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  margin-bottom: 14px;
  background: var(--app-surface);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  box-shadow: var(--shadow-sm);
}

.template-toolbar-label {
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

.template-toolbar-select {
  min-width: 220px;
  max-width: 300px;
}

.template-toolbar-select :deep(.el-select__wrapper) {
  border-radius: 8px;
  box-shadow: 0 0 0 1px var(--input-border) inset;
  min-height: 36px;
  font-size: 13px;
  transition: box-shadow 0.2s;
}

.template-toolbar-select :deep(.el-select__wrapper:hover),
.template-toolbar-select :deep(.el-select__wrapper.is-focused) {
  box-shadow: 0 0 0 2px var(--primary) inset !important;
}

.template-option-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 12px;
}

.template-option-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.template-option-delete {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  color: #ffffff;
  background-color: #f56c6c;
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  margin-left: 8px;
  padding: 3px 8px;
  border-radius: 10px;
  cursor: pointer;
  transition: background-color 0.2s, transform 0.15s, box-shadow 0.2s;
  flex-shrink: 0;
  box-shadow: 0 1px 2px rgba(245, 108, 108, 0.4);
}

.template-option-delete .el-icon {
  font-size: 12px;
}

.template-option-delete:hover {
  background-color: #d83a3a;
  transform: scale(1.08);
  box-shadow: 0 2px 6px rgba(216, 58, 58, 0.5);
}

.template-option-row:hover .template-option-delete {
  background-color: #e64545;
}

.template-toolbar-counter {
  color: var(--text-muted);
  font-size: 12px;
  white-space: nowrap;
  margin-left: auto;
}
</style>
