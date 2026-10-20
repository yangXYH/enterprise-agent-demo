<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  ElAlert,
  ElButton,
  ElDialog,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElLoading,
  ElMessage,
  ElOption,
  ElPagination,
  ElSelect,
  ElTable,
  ElTableColumn,
  ElTag,
  ElTooltip,
} from 'element-plus'
import { Document, Download, Search, Upload, Refresh, View } from '@element-plus/icons-vue'

const vLoading = ElLoading.directive

type Report = {
  id: string; filename: string; models: string[]; categories: string[]; sources: string[]
  report_number: string; report_date: string; page_count: number; file_size: number; created_at: string
}
type Catalog = {
  reports: Report[]; total: number; categories: string[]; can_upload: boolean
  summary: { reports: number; models: number; categories: number }
}
const baseUrl = '/api/product-quality-reports'
const keyword = ref('')
const category = ref('')
const page = ref(1)
const pageSize = 12
const loading = ref(false)
const error = ref('')
const catalog = ref<Catalog>({ reports: [], total: 0, categories: [], can_upload: false, summary: { reports: 0, models: 0, categories: 0 } })
let requestNumber = 0
let searchTimer: ReturnType<typeof setTimeout> | undefined
const selected = ref<Report | null>(null)
const previewOpen = ref(false)
const previewUrl = ref('')
const previewLoading = ref(false)
const previewError = ref('')
let previewRequest = 0
const downloading = ref(new Set<string>())
const uploadOpen = ref(false)
const uploadCategory = ref('常规检测')
const uploadFiles = ref<File[]>([])
const uploading = ref(false)
const uploadProgress = ref('')
const uploadErrors = ref<string[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const hasFilters = computed(() => Boolean(keyword.value || category.value))
const fileUrl = (report: Report, download = false) => `${baseUrl}/${report.id}/file${download ? '?download=true' : ''}`
const formatSize = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(1)} MB`

async function responseError(response: Response): Promise<string> {
  const data = await response.json().catch(() => ({}))
  return typeof data.detail === 'string' ? data.detail : `请求失败（${response.status}）`
}

async function loadReports() {
  const current = ++requestNumber
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ keyword: keyword.value.trim(), category: category.value, page: String(page.value), page_size: String(pageSize) })
    const response = await fetch(`${baseUrl}?${params}`, { credentials: 'same-origin', cache: 'no-store' })
    if (!response.ok) throw new Error(await responseError(response))
    const data = await response.json() as Catalog
    if (current === requestNumber) catalog.value = data
  } catch (cause) {
    if (current === requestNumber) error.value = cause instanceof Error ? cause.message : '报告读取失败'
  } finally {
    if (current === requestNumber) loading.value = false
  }
}

watch([keyword, category], () => {
  page.value = 1
  clearTimeout(searchTimer)
  // Invalidate an older response immediately, before the next request starts.
  ++requestNumber
  searchTimer = setTimeout(() => void loadReports(), 220)
})
function resetFilters() { keyword.value = ''; category.value = '' }
function changePage(value: number) { page.value = value; void loadReports() }

async function fetchPdf(report: Report, download = false): Promise<Blob> {
  const response = await fetch(fileUrl(report, download), { credentials: 'same-origin' })
  if (!response.ok) throw new Error(await responseError(response))
  return response.blob()
}

function clearPreview() {
  ++previewRequest
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
}
async function preview(report: Report) {
  clearPreview()
  const current = previewRequest
  selected.value = report
  previewOpen.value = true
  previewLoading.value = true
  previewError.value = ''
  try {
    const blob = await fetchPdf(report)
    if (current === previewRequest && previewOpen.value) previewUrl.value = URL.createObjectURL(blob)
  } catch (cause) {
    if (current === previewRequest) previewError.value = cause instanceof Error ? cause.message : '预览失败'
  } finally {
    if (current === previewRequest) previewLoading.value = false
  }
}

async function download(report: Report) {
  if (downloading.value.has(report.id)) return
  downloading.value.add(report.id)
  try {
    const url = URL.createObjectURL(await fetchPdf(report, true))
    const link = document.createElement('a')
    link.href = url
    link.download = report.filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (cause) {
    ElMessage.error(cause instanceof Error ? cause.message : '下载失败')
  } finally {
    downloading.value.delete(report.id)
  }
}

function selectFiles(event: Event) {
  uploadFiles.value = Array.from((event.target as HTMLInputElement).files || [])
  uploadErrors.value = []
}
function openUpload() {
  uploadFiles.value = []
  uploadErrors.value = []
  uploadProgress.value = ''
  uploadCategory.value = '常规检测'
  uploadOpen.value = true
  if (fileInput.value) fileInput.value.value = ''
}
async function upload() {
  if (!uploadFiles.value.length || uploading.value) return
  uploading.value = true
  uploadErrors.value = []
  let added = 0
  let duplicates = 0
  const failed: File[] = []
  const files = [...uploadFiles.value]
  for (const [index, file] of files.entries()) {
    uploadProgress.value = `正在上传 ${index + 1} / ${files.length}`
    try {
      if (!file.name.toLowerCase().endsWith('.pdf') || file.size > 30 * 1024 * 1024) throw new Error('仅支持 30 MB 以内的 PDF')
      const form = new FormData()
      form.append('file', file)
      form.append('category', uploadCategory.value.trim() || '常规检测')
      const response = await fetch(`${baseUrl}/upload`, { method: 'POST', body: form, credentials: 'same-origin' })
      if (!response.ok) throw new Error(await responseError(response))
      const result = await response.json()
      if (result.duplicate) ++duplicates
      else ++added
    } catch (cause) {
      failed.push(file)
      uploadErrors.value.push(`${file.name}：${cause instanceof Error ? cause.message : '上传失败'}`)
    }
  }
  uploading.value = false
  uploadProgress.value = `新增 ${added} 份，已存在 ${duplicates} 份${failed.length ? `，失败 ${failed.length} 份` : ''}`
  uploadFiles.value = failed
  if (added || duplicates) {
    ElMessage.success(uploadProgress.value)
    page.value = 1
    await loadReports()
  }
  if (!failed.length) uploadOpen.value = false
}

onMounted(() => void loadReports())
onBeforeUnmount(() => { clearTimeout(searchTimer); ++requestNumber; clearPreview() })
</script>

<template>
  <section class="quality-library">
    <header class="library-header">
      <div class="header-copy">
        <span class="eyebrow">客服部 · 共享资料库</span>
        <h1>产品质检报告</h1>
        <p>查找产品型号，预览报告，下载原件发给客户。</p>
      </div>
      <div class="header-stats">
        <div><strong>{{ catalog.summary.reports }}</strong><span>报告</span></div>
        <div><strong>{{ catalog.summary.models }}</strong><span>产品型号</span></div>
        <div><strong>{{ catalog.summary.categories }}</strong><span>资料分类</span></div>
      </div>
    </header>

    <div class="library-panel">
      <div class="search-toolbar">
        <el-input v-model="keyword" class="keyword-input" :prefix-icon="Search" placeholder="搜索型号、报告编号或文件名，如 TX5 / BY409003" clearable aria-label="搜索质检报告" />
        <el-select v-model="category" placeholder="全部分类" clearable aria-label="资料分类" class="category-select">
          <el-option v-for="name in catalog.categories" :key="name" :label="name" :value="name" />
        </el-select>
        <el-button :icon="Refresh" :loading="loading" @click="loadReports">刷新</el-button>
        <el-button v-if="catalog.can_upload" type="primary" :icon="Upload" @click="openUpload">上传报告</el-button>
      </div>
      <div class="quick-search">
        <span>快捷查找</span>
        <button v-for="model in ['TX5', 'BP4', 'BY4', '儿童书包']" :key="model" type="button" :class="{ active: keyword === model }" @click="keyword = model">{{ model }}</button>
        <span class="search-hint">支持型号中的空格、横线和下划线</span>
      </div>
      <div class="results-heading">
        <h2>{{ hasFilters ? '查询结果' : '全部报告' }} <span>{{ catalog.total }} 份</span></h2>
        <el-button v-if="hasFilters" link type="primary" @click="resetFilters">清除筛选</el-button>
        <span v-else class="shared-note">全员共享 · 原始 PDF</span>
      </div>

      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="error-alert">
        <el-button link type="primary" @click="loadReports">重新加载</el-button>
      </el-alert>
      <div v-else v-loading="loading" class="reports-table">
        <el-table :data="catalog.reports" row-key="id" stripe empty-text="暂无匹配报告，请尝试其他型号或清除筛选" style="width: 100%">
          <!-- @vue-generic {Report} -->
          <el-table-column label="报告文件" min-width="330">
            <template #default="{ row }: { row: Report }">
              <div class="report-title">
                <div class="pdf-icon"><el-icon><Document /></el-icon><small>PDF</small></div>
                <div class="report-copy">
                  <button type="button" class="filename" @click="preview(row)">{{ row.filename }}</button>
                  <span class="report-meta">{{ row.page_count }} 页 · {{ formatSize(row.file_size) }}<template v-if="row.report_number"> · {{ row.report_number }}</template></span>
                </div>
              </div>
            </template>
          </el-table-column>
          <!-- @vue-generic {Report} -->
          <el-table-column label="产品型号" min-width="175">
            <template #default="{ row }: { row: Report }">
              <div v-if="row.models.length" class="model-tags">
                <button v-for="model in row.models.slice(0, 3)" :key="model" type="button" @click="keyword = model">{{ model }}</button>
                <el-tooltip v-if="row.models.length > 3" :content="row.models.join('、')" placement="top"><span class="more-models">+{{ row.models.length - 3 }}</span></el-tooltip>
              </div>
              <span v-else class="muted">见报告原文</span>
            </template>
          </el-table-column>
          <!-- @vue-generic {Report} -->
          <el-table-column label="分类" min-width="145">
            <template #default="{ row }: { row: Report }">
              <div class="category-tags"><el-tag v-for="name in row.categories" :key="name" type="info" size="small" effect="plain">{{ name }}</el-tag></div>
            </template>
          </el-table-column>
          <!-- @vue-generic {Report} -->
          <el-table-column label="报告日期" width="115">
            <template #default="{ row }: { row: Report }"><span class="date-text">{{ row.report_date || '见报告原文' }}</span></template>
          </el-table-column>
          <!-- @vue-generic {Report} -->
          <el-table-column label="操作" width="165" fixed="right">
            <template #default="{ row }: { row: Report }">
              <el-button type="primary" link :icon="View" @click="preview(row)">预览</el-button>
              <el-button type="primary" link :icon="Download" :loading="downloading.has(row.id)" @click="download(row)">下载</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <footer v-if="!error" class="library-footer">
        <span>报告内容与适用型号以原件为准</span>
        <el-pagination v-if="catalog.total > pageSize" :current-page="page" :page-size="pageSize" :total="catalog.total" layout="prev, pager, next" background @current-change="changePage" />
      </footer>
    </div>

    <el-dialog v-model="previewOpen" title="报告预览" width="min(1100px, 94vw)" top="4vh" destroy-on-close @closed="clearPreview">
      <div v-if="selected" class="preview-heading">
        <div><strong>{{ selected.filename }}</strong><span>{{ selected.models.join(' · ') || '产品型号见原文' }} · {{ selected.page_count }} 页</span></div>
        <el-button type="primary" :icon="Download" :loading="downloading.has(selected.id)" @click="download(selected)">下载原件</el-button>
      </div>
      <div v-loading="previewLoading" class="pdf-preview">
        <el-alert v-if="previewError" :title="previewError" type="error" :closable="false" show-icon />
        <iframe v-else-if="previewUrl" :src="previewUrl" :title="selected?.filename || 'PDF 报告预览'" />
      </div>
      <template #footer><span class="preview-tip">无法显示时，可下载原件或</span> <a v-if="selected" :href="fileUrl(selected)" target="_blank" rel="noopener">在新窗口打开</a></template>
    </el-dialog>

    <el-dialog v-model="uploadOpen" title="上传质检报告" width="560px" :close-on-click-modal="!uploading" :close-on-press-escape="!uploading" :show-close="!uploading">
      <el-form label-position="top">
        <el-form-item label="资料分类">
          <el-select v-model="uploadCategory" filterable allow-create default-first-option :disabled="uploading" class="upload-category" aria-label="上传分类">
            <el-option v-for="name in catalog.categories" :key="name" :label="name" :value="name" />
          </el-select>
        </el-form-item>
        <el-form-item label="报告文件">
          <div class="upload-picker">
            <input ref="fileInput" type="file" multiple accept=".pdf,application/pdf" :disabled="uploading" aria-label="选择 PDF 报告" @change="selectFiles" />
            <p>支持批量选择 PDF，每份不超过 30 MB。重复报告会自动识别。</p>
          </div>
        </el-form-item>
        <ul v-if="uploadFiles.length" class="selected-files"><li v-for="(file, index) in uploadFiles" :key="index">{{ file.name }} <span>{{ formatSize(file.size) }}</span></li></ul>
        <p v-if="uploadProgress" class="upload-progress">{{ uploadProgress }}</p>
        <el-alert v-for="message in uploadErrors" :key="message" :title="message" type="error" :closable="false" class="upload-error" />
      </el-form>
      <template #footer><el-button :disabled="uploading" @click="uploadOpen = false">取消</el-button><el-button type="primary" :loading="uploading" :disabled="!uploadFiles.length" @click="upload">{{ uploading ? '上传中' : '确认上传' }}</el-button></template>
    </el-dialog>
  </section>
</template>

<style scoped>
.quality-library { padding: 26px; color: var(--text-primary); max-width: 1680px; margin: 0 auto; }
.library-header { display: flex; align-items: center; justify-content: space-between; gap: 32px; padding: 28px 32px; margin-bottom: 22px; border: 1px solid var(--border-color); border-radius: 16px; background: linear-gradient(115deg, var(--primary-surface-2), var(--app-surface)); }
.eyebrow { color: var(--text-accent); font-size: 12px; font-weight: 600; letter-spacing: 1px; }
h1 { margin: 10px 0; color: var(--text-heading); font-size: 27px; }
.header-copy p { margin: 0; font-size: 14px; color: var(--text-secondary); }
.header-stats { display: flex; flex-shrink: 0; }
.header-stats > div { min-width: 100px; display: flex; flex-direction: column; align-items: center; gap: 7px; padding: 0 20px; }
.header-stats > div + div { border-left: 1px solid var(--border-color); }
.header-stats strong { color: var(--text-accent); font-size: 30px; line-height: 1; font-variant-numeric: tabular-nums; }
.header-stats span { color: var(--text-secondary); font-size: 12px; }
.library-panel { background: var(--app-surface); border: 1px solid var(--border-color); border-radius: 14px; padding: 22px; box-shadow: var(--shadow-sm); }
.search-toolbar { display: flex; align-items: center; gap: 12px; }
.keyword-input { flex: 1; min-width: 230px; }
.category-select { width: 180px; flex-shrink: 0; }
.search-toolbar :deep(.el-button + .el-button) { margin-left: 0; }
.quick-search { display: flex; gap: 9px; align-items: center; flex-wrap: wrap; padding: 14px 0 20px; color: var(--text-secondary); font-size: 12px; }
.quick-search button, .model-tags button { font: inherit; color: var(--text-accent); background: var(--primary-surface); border: 1px solid var(--border-color); border-radius: 5px; padding: 3px 9px; cursor: pointer; }
.quick-search button:hover, .quick-search button.active, .model-tags button:hover { border-color: var(--primary); background: var(--primary-surface-2); }
.search-hint { margin-left: auto; color: var(--text-muted); }
.results-heading { display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--border-subtle); padding: 18px 0 14px; }
h2 { margin: 0; font-size: 15px; color: var(--text-heading); }
h2 span { margin-left: 10px; font-size: 12px; color: var(--text-secondary); font-weight: 400; }
.shared-note, .muted, .date-text { font-size: 12px; color: var(--text-secondary); }
.reports-table { min-height: 220px; }
.report-title { display: flex; gap: 12px; align-items: center; padding: 8px 0; }
.pdf-icon { flex-shrink: 0; width: 38px; height: 46px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1px; color: #dc5555; background: rgba(220, 85, 85, .08); border-radius: 7px; }
.pdf-icon .el-icon { font-size: 20px; }
.pdf-icon small { font-size: 8px; font-weight: 800; }
.report-copy { min-width: 0; }
.filename { display: block; font: inherit; font-size: 13px; font-weight: 500; color: var(--text-heading); border: 0; padding: 0; background: transparent; text-align: left; cursor: pointer; overflow-wrap: anywhere; line-height: 1.6; }
.filename:hover { color: var(--text-accent); }
.report-meta { display: block; margin-top: 4px; color: var(--text-muted); font-size: 11px; overflow-wrap: anywhere; }
.model-tags, .category-tags { display: flex; gap: 5px; flex-wrap: wrap; align-items: center; }
.model-tags button { font-size: 11px; padding: 2px 6px; font-family: ui-monospace, monospace; }
.more-models { color: var(--text-secondary); font-size: 11px; }
.library-footer { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding-top: 18px; font-size: 12px; color: var(--text-muted); }
.error-alert { margin: 8px 0 20px; }
.preview-heading { display: flex; justify-content: space-between; align-items: center; gap: 20px; margin-bottom: 18px; }
.preview-heading > div { min-width: 0; }
.preview-heading strong { display: block; overflow-wrap: anywhere; color: var(--text-heading); font-size: 14px; }
.preview-heading span { display: block; margin-top: 5px; color: var(--text-secondary); font-size: 12px; }
.pdf-preview { height: 68vh; min-height: 300px; background: var(--app-surface-2); border: 1px solid var(--border-color); border-radius: 7px; overflow: hidden; }
.pdf-preview iframe { height: 100%; width: 100%; border: 0; }
.preview-tip { font-size: 12px; color: var(--text-secondary); }
a { color: var(--text-accent); font-size: 12px; }
.upload-category, .upload-picker { width: 100%; }
.upload-picker { padding: 18px; border: 1px dashed var(--border-color); border-radius: 8px; background: var(--app-surface-2); }
.upload-picker p { margin: 10px 0 0; color: var(--text-secondary); font-size: 12px; }
.upload-picker input { max-width: 100%; }
.selected-files { list-style: none; padding: 0; max-height: 180px; overflow: auto; }
.selected-files li { padding: 8px 0; border-bottom: 1px solid var(--border-subtle); font-size: 12px; overflow-wrap: anywhere; }
.selected-files span { color: var(--text-muted); margin-left: 8px; }
.upload-progress { font-size: 12px; color: var(--text-accent); }
.upload-error { margin-top: 8px; }
@media (max-width: 1050px) { .quality-library { padding: 18px; } .library-header { padding: 24px; gap: 20px; } .header-stats > div { min-width: 70px; padding: 0 12px; } .search-hint { display: none; } }
@media (max-width: 720px) { .quality-library { padding: 12px; } .library-header { flex-direction: column; align-items: flex-start; } .header-stats { width: 100%; justify-content: space-around; } .header-stats > div { flex: 1; } .library-panel { padding: 14px; } .search-toolbar { flex-wrap: wrap; } .keyword-input { flex-basis: 100%; } .category-select { flex: 1; width: auto; } .library-footer { align-items: flex-start; flex-direction: column; } .preview-heading { align-items: flex-start; } }
</style>
