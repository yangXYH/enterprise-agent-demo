<template>
  <section class="inventory-product-page">
    <el-alert v-if="importStatus" class="inventory-alert" :title="importStatus" type="success" show-icon closable @close="importStatus = ''" />
    <el-alert v-if="error" class="inventory-alert" :title="error" type="error" show-icon :closable="false">
      <el-button link type="primary" @click="load">重新加载</el-button>
    </el-alert>

    <Teleport to="body">
      <div v-if="previewImage" class="inventory-image-overlay" role="dialog" aria-modal="true" aria-label="商品大图预览" @click="closeImagePreview">
        <button class="inventory-image-close" type="button" aria-label="关闭大图预览" @click.stop="closeImagePreview">×</button>
        <img class="inventory-image-large" :src="previewImage" alt="商品大图" :style="{ transform: `scale(${previewScale})` }" @click="closeImagePreview" @wheel.prevent.stop="handlePreviewWheel" />
      </div>
    </Teleport>

    <section class="inventory-summary" aria-label="进销商品汇总">
      <article class="inventory-kpi inventory-kpi-primary"><span>商品条目</span><strong>{{ formatNumber(summary.row_count) }}</strong><small>{{ formatNumber(summary.sku_count) }} 个商品编码</small></article>
      <article class="inventory-kpi"><span>期初数量</span><strong>{{ formatNumber(summary.opening_quantity) }}</strong><small>本期快照期初库存</small></article>
      <article class="inventory-kpi"><span>期末数量</span><strong>{{ formatNumber(summary.closing_quantity) }}</strong><small>本期快照期末库存</small></article>
      <article class="inventory-kpi"><span>滞销商品</span><strong>{{ formatNumber(summary.stagnant_count) }}</strong><small>期初数量 = 期末数量</small></article>
      <article class="inventory-kpi inventory-kpi-warning"><span>滞销率</span><strong>{{ stagnantRate }}</strong><small>{{ formatNumber(summary.image_count) }} 条含图片</small></article>
    </section>

    <section class="panel inventory-panel" :aria-busy="loading">
      <div class="inventory-toolbar">
        <div class="inventory-title">
          <h1>进销商品看板</h1>
          <p>{{ batch.period_label ? `数据范围：${compactPeriodLabel(batch.period_label)}` : '请导入进销存按商品数据' }}</p>
        </div>
        <form class="inventory-filters" @submit.prevent="search">
          <el-select v-model="selectedReportDate" filterable clearable placeholder="选择数据周" aria-label="数据周">
            <el-option v-for="period in periods" :key="period.report_date" :label="periodOptionLabel(period)" :value="period.report_date" />
          </el-select>
          <el-input v-model="filters.keyword" clearable placeholder="编码 / 商品名称" aria-label="商品搜索" />
          <el-select v-model="filters.brand" filterable clearable multiple collapse-tags collapse-tags-tooltip placeholder="全部品牌" aria-label="商品品牌">
            <el-option v-for="brand in options.brands" :key="brand" :label="brand" :value="brand" />
          </el-select>
          <el-select v-model="filters.category" filterable clearable multiple collapse-tags collapse-tags-tooltip placeholder="全部分类" aria-label="商品分类">
            <el-option v-for="category in options.categories" :key="category" :label="category" :value="category" />
          </el-select>
          <el-select v-model="filters.stagnant" clearable placeholder="全部滞销状态" aria-label="滞销状态">
            <el-option label="滞销：是" value="yes" />
            <el-option label="滞销：否" value="no" />
          </el-select>
        </form>
        <div class="inventory-actions">
          <el-button text @click="reset">重置</el-button>
          <el-button type="primary" :loading="importing" @click="fileInput?.click()">{{ importing ? '正在导入…' : '导入周报数据' }}</el-button>
          <input ref="fileInput" class="file-input" type="file" accept=".xlsx" :disabled="importing" @change="uploadFile" />
        </div>
      </div>

      <div class="inventory-table-wrap">
        <div v-if="loading" class="loading-note">正在加载进销商品数据…</div>
        <el-table :data="items" row-key="id" stripe height="100%" table-layout="fixed" class="inventory-table">
          <el-table-column label="图片" width="82" align="center">
            <template #default="{ row }">
              <div v-if="row.image_url" class="inventory-image inventory-image-clickable" role="button" tabindex="0" @click="openImagePreview(row.image_url)" @keydown.enter.prevent="openImagePreview(row.image_url)" @keydown.space.prevent="openImagePreview(row.image_url)">
                <el-image :src="row.image_url" :alt="row.product_name" fit="contain" loading="lazy" class="inventory-image-thumb">
                  <template #error><span>加载失败</span></template>
                </el-image>
              </div>
              <div v-else class="inventory-image"><span>暂无图</span></div>
            </template>
          </el-table-column>
          <el-table-column prop="category" label="分类" min-width="110" show-overflow-tooltip />
          <el-table-column prop="style_code" label="款式编码" min-width="138" show-overflow-tooltip class-name="code-column" />
          <el-table-column prop="product_code" label="商品编码" min-width="150" show-overflow-tooltip class-name="code-column" />
          <el-table-column prop="product_name" label="商品名称" min-width="320" show-overflow-tooltip />
          <el-table-column prop="color_spec" label="颜色规格" min-width="150" show-overflow-tooltip />
          <el-table-column prop="brand" label="品牌" min-width="140" show-overflow-tooltip />
          <el-table-column prop="opening_quantity" label="期初数量" width="112" align="right"><template #default="{ row }"><span class="quantity">{{ formatNumber(row.opening_quantity) }}</span></template></el-table-column>
          <el-table-column prop="closing_quantity" label="期末数量" width="112" align="right"><template #default="{ row }"><strong class="quantity">{{ formatNumber(row.closing_quantity) }}</strong></template></el-table-column>
          <el-table-column label="是否滞销" width="105" align="center"><template #default="{ row }"><span :class="['stagnant-label', row.is_stagnant ? 'stagnant-yes' : 'stagnant-no']">{{ row.is_stagnant ? '是' : '否' }}</span></template></el-table-column>
          <template #empty><div class="empty-state">{{ error ? '数据加载失败' : '暂无匹配商品，请导入周报或调整筛选条件' }}</div></template>
        </el-table>
      </div>

      <footer class="inventory-pagination">
        <span>{{ total ? `当前 ${rangeStart}–${rangeEnd} 条，共 ${formatNumber(total)} 条` : '共 0 条记录' }}</span>
        <el-pagination :current-page="page" :page-size="pageSize" :total="total" :page-sizes="[20, 50, 100, 200]" background layout="sizes, prev, pager, next, jumper" @update:page-size="changePageSize" @update:current-page="changePage" />
      </footer>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElAlert, ElButton, ElImage, ElInput, ElOption, ElPagination, ElSelect, ElTable, ElTableColumn } from 'element-plus'
import request from '../utils/request'

type Filters = { keyword: string; brand: string[]; category: string[]; stagnant: string }
type Period = { report_date: string; period_start: string; period_end: string; period_label: string; source_name: string; row_count: number; image_count: number; imported_at: string }
type Summary = { row_count: number; sku_count: number; category_count: number; brand_count: number; opening_quantity: number; closing_quantity: number; stagnant_count: number; image_count: number }
type ProductRow = Record<string, any> & { id: number; source_row: number; product_name: string; image_url: string; is_stagnant: boolean }

const emptyFilters = (): Filters => ({ keyword: '', brand: [], category: [], stagnant: '' })
const emptySummary = (): Summary => ({ row_count: 0, sku_count: 0, category_count: 0, brand_count: 0, opening_quantity: 0, closing_quantity: 0, stagnant_count: 0, image_count: 0 })
const filters = reactive<Filters>(emptyFilters())
const summary = reactive<Summary>(emptySummary())
const options = reactive({ brands: [] as string[], categories: [] as string[] })
const batch = reactive<Record<string, any>>({})
const periods = ref<Period[]>([])
const selectedReportDate = ref('')
const items = ref<ProductRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const loading = ref(false)
const importing = ref(false)
const error = ref('')
const importStatus = ref('')
const previewImage = ref('')
const previewScale = ref(1)
const fileInput = ref<HTMLInputElement>()
let disposed = false
let requestId = 0
let searchTimer: ReturnType<typeof setTimeout> | undefined

const formatNumber = (value: unknown) => Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
const rangeStart = computed(() => total.value ? (page.value - 1) * pageSize.value + 1 : 0)
const rangeEnd = computed(() => Math.min(page.value * pageSize.value, total.value))
const stagnantRate = computed(() => summary.row_count > 0 ? `${((summary.stagnant_count / summary.row_count) * 100).toFixed(2)}%` : '0.00%')
const compactPeriodLabel = (value: unknown) => String(value || '').replace(/\s*~\s*/g, '~')
const periodOptionLabel = (period: Period) => compactPeriodLabel(period.period_label)
const errorMessage = (reason: any, fallback: string) => typeof reason?.response?.data?.detail === 'string' ? reason.response.data.detail : reason?.message || fallback

function openImagePreview(url: unknown) { if (typeof url === 'string' && url) { previewImage.value = url; previewScale.value = 1 } }
function closeImagePreview() { previewImage.value = ''; previewScale.value = 1 }
function handlePreviewWheel(event: WheelEvent) { previewScale.value = Math.min(4, Math.max(0.5, Number((previewScale.value + (event.deltaY < 0 ? 0.15 : -0.15)).toFixed(2)))) }

async function load() {
  const id = ++requestId
  loading.value = true
  error.value = ''
  try {
    const response: any = await request.get('/inventory-product-dashboard', { params: { report_date: selectedReportDate.value, keyword: filters.keyword.trim(), brand: filters.brand, category: filters.category, stagnant: filters.stagnant, page: page.value, page_size: pageSize.value } })
    if (disposed || id !== requestId) return
    const data = response?.data || {}
    periods.value = Array.isArray(data.periods) ? data.periods : []
    if (!selectedReportDate.value && data.batch?.report_date) selectedReportDate.value = data.batch.report_date
    Object.assign(batch, data.batch || {})
    Object.assign(summary, emptySummary(), data.summary || {})
    items.value = Array.isArray(data.items) ? data.items : []
    options.brands = Array.isArray(data.filter_options?.brands) ? data.filter_options.brands : []
    options.categories = Array.isArray(data.filter_options?.categories) ? data.filter_options.categories : []
    total.value = Number(data.total || 0)
    const lastPage = Math.max(1, Math.ceil(total.value / pageSize.value))
    if (page.value > lastPage) { page.value = lastPage; await load() }
  } catch (reason: unknown) {
    if (disposed || id !== requestId) return
    error.value = errorMessage(reason, '进销商品看板加载失败')
    items.value = []
    total.value = 0
  } finally { if (!disposed && id === requestId) loading.value = false }
}
function search() { page.value = 1; void load() }
function reset() { Object.assign(filters, emptyFilters()); page.value = 1; void load() }
function changePage(next: number) { if (next !== page.value) { page.value = next; void load() } }
function changePageSize(next: number) { if (next !== pageSize.value) { pageSize.value = next; page.value = 1; void load() } }
async function uploadFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || importing.value) return
  if (!file.name.toLowerCase().endsWith('.xlsx')) { error.value = '请选择 .xlsx 格式的进销存按商品文件'; input.value = ''; return }
  importing.value = true
  importStatus.value = ''
  const form = new FormData()
  form.append('file', file)
  try {
    const response: any = await request.post('/inventory-product-dashboard/import', form)
    if (disposed) return
    const imported = response?.data || {}
    selectedReportDate.value = imported.report_date || ''
    importStatus.value = `导入完成：${formatNumber(imported.row_count)} 条商品数据，数据范围 ${compactPeriodLabel(imported.period_label)}。`
    Object.assign(filters, emptyFilters())
    page.value = 1
    await load()
  } catch (reason: unknown) { if (!disposed) error.value = errorMessage(reason, '导入失败，请检查进销存文件后重试') }
  finally { importing.value = false; input.value = '' }
}
watch(filters, () => { if (searchTimer) clearTimeout(searchTimer); searchTimer = setTimeout(search, 300) }, { deep: true })
watch(selectedReportDate, (next, previous) => { if (next !== previous) { page.value = 1; void load() } })
onMounted(() => { void load() })
onBeforeUnmount(() => { disposed = true; requestId++; if (searchTimer) clearTimeout(searchTimer) })
</script>

<style scoped>
.inventory-product-page{min-height:100%;box-sizing:border-box;padding:18px;background:var(--app-bg,#f8fafc);color:var(--text-primary,#1f2937);--el-color-primary:light-dark(#0f766e, #2dd4bf);display:flex;flex-direction:column;overflow:hidden}.inventory-alert{flex-shrink:0;margin-bottom:12px}.inventory-summary{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;flex-shrink:0;margin-bottom:12px}.inventory-kpi{min-height:88px;padding:14px 16px;border:1px solid var(--border-color,#e2e8f0);border-radius:12px;background:var(--app-surface,#fff);box-shadow:var(--shadow-sm);display:flex;flex-direction:column}.inventory-kpi span{color:var(--text-secondary,#64748b);font-size:12px}.inventory-kpi strong{margin-top:9px;color:var(--text-heading,#0f172a);font-size:23px;line-height:1;font-variant-numeric:tabular-nums}.inventory-kpi small{margin-top:auto;color:var(--text-muted,#94a3b8);font-size:11px}.inventory-kpi-primary{border-top:3px solid #0f766e}.inventory-kpi-warning{border-top:3px solid #f97316}.panel{border:1px solid var(--border-color,#e2e8f0);border-radius:12px;background:var(--app-surface,#fff);box-shadow:var(--shadow-sm)}.inventory-panel{min-height:0;flex:1;display:flex;flex-direction:column;overflow:hidden}.inventory-toolbar{display:flex;align-items:center;gap:12px;padding:14px 18px;border-bottom:1px solid var(--border-subtle,#edf2f7);flex-shrink:0}.inventory-title{min-width:155px;flex:0 0 auto}.inventory-title h1{margin:0;color:var(--text-heading,#0f172a);font-size:17px;line-height:1.2}.inventory-title p{margin:5px 0 0;max-width:240px;overflow:hidden;color:var(--text-muted,#94a3b8);font-size:11px;text-overflow:ellipsis;white-space:nowrap}.inventory-filters{display:grid;grid-template-columns:minmax(150px,1fr) minmax(170px,1.15fr) minmax(145px,1fr) minmax(145px,1fr) minmax(125px,.8fr);gap:8px;min-width:0;flex:1}.inventory-filters :deep(.el-select){width:100%}.inventory-actions{display:flex;align-items:center;gap:4px;flex:0 0 auto}.inventory-actions .el-button{white-space:nowrap}.file-input{display:none}.inventory-table-wrap{position:relative;min-height:0;flex:1}.loading-note{position:absolute;top:0;right:0;left:0;z-index:3;padding:8px 18px;background:light-dark(#ecfdf5, var(--primary-surface-2));color:light-dark(#0f766e, var(--text-accent));font-size:12px}.inventory-table{width:100%;height:100%;--el-table-header-bg-color:var(--table-header-bg,#f8fafc);--el-table-header-text-color:var(--text-secondary,#64748b);--el-table-border-color:var(--border-subtle,#edf2f7);--el-table-row-hover-bg-color:light-dark(#f0fdfa, var(--primary-surface-2));--el-table-text-color:var(--text-primary,#334155);font-size:12px}.inventory-table :deep(th.el-table__cell){padding:8px 0;font-weight:600}.inventory-table :deep(td.el-table__cell){padding:5px 0}.inventory-table :deep(.cell){padding:0 8px}.inventory-table :deep(.code-column .cell){color:var(--text-secondary,#64748b);font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px}.inventory-image{width:52px;height:52px;border:1px solid light-dark(#eef2f7, var(--border-color));border-radius:8px;background:light-dark(#f8fafc, var(--app-surface-2));display:flex;align-items:center;justify-content:center;overflow:hidden;margin:0 auto}.inventory-image span{color:light-dark(#cbd5e1, var(--text-secondary));font-size:9px}.inventory-image-clickable{cursor:zoom-in;transition:border-color .2s ease,box-shadow .2s ease}.inventory-image-clickable:hover{border-color:light-dark(#5eead4, var(--border-color));box-shadow:0 0 0 3px rgba(20,184,166,.12)}.inventory-image-thumb{width:100%;height:100%;cursor:zoom-in}.inventory-image-thumb :deep(.el-image__inner){width:100%;height:100%;object-fit:contain}.inventory-image-thumb :deep(.el-image__error){display:flex;align-items:center;justify-content:center;color:light-dark(#cbd5e1, var(--text-secondary));font-size:9px}.quantity{font-variant-numeric:tabular-nums}.stagnant-label{font-weight:700}.stagnant-yes{color:light-dark(#dc2626, #f87171)}.stagnant-no{color:light-dark(#111827, var(--text-primary))}.empty-state{padding:70px 0;color:var(--text-muted,#94a3b8);text-align:center}.inventory-pagination{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:11px 18px;border-top:1px solid var(--border-subtle,#edf2f7);color:var(--text-secondary,#64748b);font-size:12px;flex-shrink:0}.inventory-image-overlay{position:fixed;inset:0;z-index:3000;display:flex;align-items:center;justify-content:center;padding:56px;background:light-dark(rgba(255,255,255,.9), rgba(15,23,42,.94));cursor:zoom-out}.inventory-image-large{display:block;max-width:100%;max-height:100%;object-fit:contain;cursor:zoom-out;user-select:none;transition:transform .16s ease;transform-origin:center center}.inventory-image-close{position:absolute;top:18px;right:24px;width:40px;height:40px;padding:0;border:0;border-radius:50%;background:light-dark(rgba(15,23,42,.08), rgba(255,255,255,.12));color:light-dark(#64748b, var(--text-secondary));font-size:30px;line-height:1;cursor:pointer}.inventory-image-close:hover{background:light-dark(rgba(15,23,42,.14), rgba(255,255,255,.2))}
@media(max-width:1450px){.inventory-summary{grid-template-columns:repeat(3,minmax(0,1fr))}.inventory-toolbar{align-items:stretch;flex-wrap:wrap}.inventory-title{width:100%}.inventory-filters{flex:1 1 760px}.inventory-actions{margin-left:auto}}
@media(max-width:760px){.inventory-product-page{padding:14px}.inventory-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.inventory-toolbar{padding:14px}.inventory-filters{grid-template-columns:1fr;flex-basis:100%}.inventory-actions{width:100%;justify-content:space-between;margin-left:0}.inventory-pagination{align-items:flex-start;flex-direction:column;padding:12px 14px}}
</style>
