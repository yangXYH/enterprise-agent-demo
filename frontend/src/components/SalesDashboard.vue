<template>
  <section class="sales-page">
    <el-alert v-if="importStatus" class="sales-alert" :title="importStatus" type="success" show-icon closable @close="importStatus = ''" />
    <el-alert v-if="error" class="sales-alert" :title="error" type="error" show-icon :closable="false">
      <el-button link type="primary" @click="load">重新加载</el-button>
    </el-alert>

    <Teleport to="body">
      <div v-if="previewImage" class="sales-image-preview-overlay" role="dialog" aria-modal="true" aria-label="商品大图预览" @click="closeImagePreview">
        <button class="sales-image-preview-close" type="button" aria-label="关闭大图预览" @click.stop="closeImagePreview">×</button>
        <img class="sales-image-preview-large" :src="previewImage" alt="商品大图" :style="{ transform: `scale(${previewScale})` }" @click="closeImagePreview" @wheel.prevent.stop="handlePreviewWheel" />
      </div>
    </Teleport>

    <section class="sales-summary" aria-label="销售数据汇总">
      <article class="sales-kpi sales-kpi-primary"><span>商品条目</span><strong>{{ formatNumber(summary.row_count) }}</strong><small>{{ formatNumber(summary.sku_count) }} 个编码</small></article>
      <article class="sales-kpi"><span>销售数量</span><strong>{{ formatNumber(summary.sales_quantity) }}</strong><small>销售主题分析数据</small></article>
      <article class="sales-kpi"><span>实发数量</span><strong>{{ formatNumber(summary.shipped_quantity) }}</strong><small>实际发货数量</small></article>
      <article class="sales-kpi"><span>实退数量</span><strong>{{ formatNumber(summary.returned_quantity) }}</strong><small>实际退货数量</small></article>
      <article class="sales-kpi sales-kpi-warning"><span>退货率</span><strong>{{ returnRate }}</strong><small>实退数量 ÷ 实发数量</small></article>
    </section>

    <section class="panel sales-panel" :aria-busy="loading">
      <div class="sales-toolbar">
        <div class="sales-title"><h1>销售数据看板</h1><p>导入时间：{{ batch.imported_at || '暂无' }}</p></div>
        <form class="sales-filters" @submit.prevent="search">
          <el-input v-model="filters.keyword" clearable placeholder="编码 / 商品名称" aria-label="编码或商品名称搜索" />
          <el-select v-model="filters.brand" filterable clearable multiple collapse-tags collapse-tags-tooltip placeholder="全部品牌" aria-label="商品品牌">
            <el-option v-for="brand in options.brands" :key="brand" :label="brand" :value="brand" />
          </el-select>
          <el-select v-model="filters.category" filterable clearable multiple collapse-tags collapse-tags-tooltip placeholder="全部分类" aria-label="产品分类">
            <el-option v-for="category in options.categories" :key="category" :label="category" :value="category" />
          </el-select>
        </form>
        <div class="sales-actions">
          <el-button text @click="reset">重置</el-button>
          <el-button type="primary" :loading="importing" @click="fileInput?.click()">{{ importing ? '正在导入…' : '更新销售数据' }}</el-button>
          <input ref="fileInput" class="file-input" type="file" accept=".xlsx" :disabled="importing" @change="uploadFile" />
        </div>
      </div>

      <div class="sales-table-wrap">
        <div v-if="loading" class="loading-note">正在加载销售数据…</div>
        <el-table :data="items" row-key="source_row" stripe height="100%" table-layout="fixed" class="sales-table">
          <el-table-column label="图片" width="88" align="center">
            <template #default="{ row }">
              <div v-if="row.image_url" class="sales-image sales-image-clickable" role="button" tabindex="0" @click="openImagePreview(row.image_url)" @keydown.enter.prevent="openImagePreview(row.image_url)" @keydown.space.prevent="openImagePreview(row.image_url)">
                <el-image :src="row.image_url" :alt="row.product_name" fit="contain" loading="lazy" class="sales-image-thumb">
                  <template #error><span>加载失败</span></template>
                </el-image>
              </div>
              <div v-else class="sales-image"><span>暂无图</span></div>
            </template>
          </el-table-column>
          <el-table-column prop="product_code" label="款式编码/商品编码" min-width="180" show-overflow-tooltip class-name="code-column" />
          <el-table-column prop="product_name" label="款式名称/商品名称" min-width="320" show-overflow-tooltip />
          <el-table-column prop="category" label="产品分类" min-width="140" show-overflow-tooltip />
          <el-table-column prop="brand" label="商品品牌" min-width="160" show-overflow-tooltip />
          <el-table-column prop="sales_quantity" label="销售数量" width="110" align="center"><template #default="{ row }"><strong class="quantity">{{ formatNumber(row.sales_quantity) }}</strong></template></el-table-column>
          <el-table-column prop="shipped_quantity" label="实发数量" width="110" align="center"><template #default="{ row }"><span class="quantity">{{ formatNumber(row.shipped_quantity) }}</span></template></el-table-column>
          <el-table-column prop="returned_quantity" label="实退数量" width="110" align="center"><template #default="{ row }"><span class="quantity returned">{{ formatNumber(row.returned_quantity) }}</span></template></el-table-column>
          <template #empty><div class="empty-state">{{ error ? '数据加载失败' : '暂无匹配的销售数据，请调整筛选条件或导入销售分析文件' }}</div></template>
        </el-table>
      </div>

      <footer class="sales-pagination">
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

type Filters = { keyword: string; brand: string[]; category: string[] }
type SalesRow = Record<string, any> & {
  source_row: number
  product_code: string
  product_name: string
  image_url: string
}
type Summary = {
  row_count: number
  sku_count: number
  category_count: number
  brand_count: number
  sales_quantity: number
  shipped_quantity: number
  returned_quantity: number
}

const emptyFilters = (): Filters => ({ keyword: '', brand: [], category: [] })
const emptySummary = (): Summary => ({ row_count: 0, sku_count: 0, category_count: 0, brand_count: 0, sales_quantity: 0, shipped_quantity: 0, returned_quantity: 0 })
const filters = reactive<Filters>(emptyFilters())
const appliedFilters = ref<Filters>(emptyFilters())
const summary = reactive<Summary>(emptySummary())
const options = reactive({ brands: [] as string[], categories: [] as string[] })
const batch = reactive<Record<string, any>>({})
const items = ref<SalesRow[]>([])
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
const returnRate = computed(() => {
  const shippedQuantity = Number(summary.shipped_quantity || 0)
  if (shippedQuantity <= 0) return '0.00%'
  return `${((Number(summary.returned_quantity || 0) / shippedQuantity) * 100).toFixed(2)}%`
})
const errorMessage = (reason: any, fallback: string) => typeof reason?.response?.data?.detail === 'string' ? reason.response.data.detail : reason?.message || fallback

function openImagePreview(url: unknown) {
  if (typeof url !== 'string' || !url) return
  previewImage.value = url
  previewScale.value = 1
}
function closeImagePreview() {
  previewImage.value = ''
  previewScale.value = 1
}
function handlePreviewWheel(event: WheelEvent) {
  const step = event.deltaY < 0 ? 0.15 : -0.15
  previewScale.value = Math.min(4, Math.max(0.5, Number((previewScale.value + step).toFixed(2))))
}
async function load() {
  const id = ++requestId
  loading.value = true
  error.value = ''
  try {
    const response: any = await request.get('/sales-dashboard', { params: { ...appliedFilters.value, page: page.value, page_size: pageSize.value } })
    if (disposed || id !== requestId) return
    const data = response?.data || {}
    Object.assign(summary, emptySummary(), data.summary || {})
    Object.assign(batch, data.batch || {})
    items.value = Array.isArray(data.items) ? data.items : []
    options.brands = Array.isArray(data.filter_options?.brands) ? data.filter_options.brands : []
    options.categories = Array.isArray(data.filter_options?.categories) ? data.filter_options.categories : []
    total.value = Number(data.total || 0)
    const lastPage = Math.max(1, Math.ceil(total.value / pageSize.value))
    if (page.value > lastPage) { page.value = lastPage; await load() }
  } catch (reason: unknown) {
    if (disposed || id !== requestId) return
    error.value = errorMessage(reason, '销售数据看板加载失败')
    items.value = []
    total.value = 0
  } finally {
    if (!disposed && id === requestId) loading.value = false
  }
}
function search() {
  appliedFilters.value = { keyword: filters.keyword.trim(), brand: [...filters.brand], category: [...filters.category] }
  page.value = 1
  void load()
}
function reset() { Object.assign(filters, emptyFilters()) }
function changePage(next: number) { if (next !== page.value) { page.value = next; void load() } }
function changePageSize(next: number) { if (next !== pageSize.value) { pageSize.value = next; page.value = 1; void load() } }
async function uploadFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || importing.value) return
  if (!file.name.toLowerCase().endsWith('.xlsx')) { error.value = '请选择 .xlsx 格式的销售分析文件'; input.value = ''; return }
  importing.value = true
  importStatus.value = ''
  const form = new FormData()
  form.append('file', file)
  try {
    const response: any = await request.post('/sales-dashboard/import', form)
    if (disposed) return
    importStatus.value = `导入完成：${formatNumber(response?.data?.row_count)} 条销售数据。`
    Object.assign(filters, emptyFilters())
    appliedFilters.value = emptyFilters()
    page.value = 1
    await load()
  } catch (reason: unknown) {
    if (!disposed) error.value = errorMessage(reason, '导入失败，请检查销售分析文件后重试')
  } finally {
    importing.value = false
    input.value = ''
  }
}
watch(filters, () => { if (searchTimer) clearTimeout(searchTimer); searchTimer = setTimeout(search, 300) })
onMounted(() => { void load() })
onBeforeUnmount(() => { disposed = true; requestId++; if (searchTimer) clearTimeout(searchTimer) })
</script>

<style scoped>
.sales-page{min-height:100%;box-sizing:border-box;padding:18px;background:var(--app-bg,#f8fafc);color:var(--text-primary,#1f2937);--el-color-primary:light-dark(#0f766e, #2dd4bf);display:flex;flex-direction:column;overflow:hidden}.sales-alert{flex-shrink:0;margin-bottom:12px}.sales-summary{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;flex-shrink:0;margin-bottom:12px}.sales-kpi{min-height:88px;padding:14px 16px;border:1px solid var(--border-color,#e2e8f0);border-radius:12px;background:var(--app-surface,#fff);box-shadow:var(--shadow-sm);display:flex;flex-direction:column}.sales-kpi span{color:var(--text-secondary,#64748b);font-size:12px}.sales-kpi strong{margin-top:9px;color:var(--text-heading,#0f172a);font-size:23px;line-height:1;font-variant-numeric:tabular-nums}.sales-kpi small{margin-top:auto;color:var(--text-muted,#94a3b8);font-size:11px}.sales-kpi-primary{border-top:3px solid #0f766e}.sales-kpi-warning{border-top:3px solid #f97316}.panel{border:1px solid var(--border-color,#e2e8f0);border-radius:12px;background:var(--app-surface,#fff);box-shadow:var(--shadow-sm)}.sales-panel{min-height:0;flex:1;display:flex;flex-direction:column;overflow:hidden}.sales-toolbar{display:flex;align-items:center;gap:14px;padding:14px 18px;border-bottom:1px solid var(--border-subtle,#edf2f7);flex-shrink:0}.sales-title{min-width:170px;flex:0 0 auto}.sales-title h1{margin:0;color:var(--text-heading,#0f172a);font-size:17px;line-height:1.2}.sales-title p{margin:5px 0 0;max-width:240px;overflow:hidden;color:var(--text-muted,#94a3b8);font-size:11px;text-overflow:ellipsis;white-space:nowrap}.sales-filters{display:grid;grid-template-columns:minmax(190px,1.25fr) minmax(145px,1fr) minmax(145px,1fr);gap:8px;min-width:0;flex:1}.sales-filters :deep(.el-select){width:100%}.sales-actions{display:flex;align-items:center;gap:4px;flex:0 0 auto}.sales-actions .el-button{white-space:nowrap}.file-input{display:none}.sales-table-wrap{position:relative;min-height:0;flex:1}.loading-note{position:absolute;top:0;right:0;left:0;z-index:3;padding:8px 18px;background:light-dark(#ecfdf5, var(--primary-surface-2));color:light-dark(#0f766e, var(--text-accent));font-size:12px}.sales-table{width:100%;height:100%;--el-table-header-bg-color:var(--table-header-bg,#f8fafc);--el-table-header-text-color:var(--text-secondary,#64748b);--el-table-border-color:var(--border-subtle,#edf2f7);--el-table-row-hover-bg-color:light-dark(#f0fdfa, var(--primary-surface-2));--el-table-text-color:var(--text-primary,#334155);font-size:12px}.sales-table :deep(th.el-table__cell){padding:8px 0;font-weight:600}.sales-table :deep(td.el-table__cell){padding:5px 0}.sales-table :deep(.cell){padding:0 9px}.sales-table :deep(.code-column .cell){color:var(--text-secondary,#64748b);font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px}.sales-image{width:52px;height:52px;border:1px solid light-dark(#eef2f7, var(--border-color));border-radius:8px;background:light-dark(#f8fafc, var(--app-surface-2));display:flex;align-items:center;justify-content:center;overflow:hidden;margin:0 auto}.sales-image span{color:light-dark(#cbd5e1, var(--text-secondary));font-size:9px}.sales-image-clickable{cursor:zoom-in;transition:border-color .2s ease,box-shadow .2s ease}.sales-image-clickable:hover{border-color:light-dark(#5eead4, var(--border-color));box-shadow:0 0 0 3px rgba(20,184,166,.12)}.sales-image-thumb{width:100%;height:100%;cursor:zoom-in}.sales-image-thumb :deep(.el-image__inner){width:100%;height:100%;object-fit:contain}.sales-image-thumb :deep(.el-image__error){display:flex;align-items:center;justify-content:center;color:light-dark(#cbd5e1, var(--text-secondary));font-size:9px}.quantity{font-variant-numeric:tabular-nums}.returned{color:light-dark(#c2410c, #fb923c)}.empty-state{padding:70px 0;color:var(--text-muted,#94a3b8);text-align:center}.sales-pagination{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:11px 18px;border-top:1px solid var(--border-subtle,#edf2f7);color:var(--text-secondary,#64748b);font-size:12px;flex-shrink:0}.sales-image-preview-overlay{position:fixed;inset:0;z-index:3000;display:flex;align-items:center;justify-content:center;padding:56px;background:light-dark(rgba(255,255,255,.9), rgba(15,23,42,.94));cursor:zoom-out}.sales-image-preview-large{display:block;max-width:100%;max-height:100%;object-fit:contain;cursor:zoom-out;user-select:none;transition:transform .16s ease;transform-origin:center center}.sales-image-preview-close{position:absolute;top:18px;right:24px;width:40px;height:40px;padding:0;border:0;border-radius:50%;background:light-dark(rgba(15,23,42,.08), rgba(255,255,255,.12));color:light-dark(#64748b, var(--text-secondary));font-size:30px;line-height:1;cursor:pointer}.sales-image-preview-close:hover{background:light-dark(rgba(15,23,42,.14), rgba(255,255,255,.2))}
@media(max-width:1250px){.sales-summary{grid-template-columns:repeat(3,minmax(0,1fr))}.sales-toolbar{align-items:stretch;flex-wrap:wrap}.sales-title{width:100%}.sales-filters{flex:1 1 600px}.sales-actions{margin-left:auto}}
@media(max-width:760px){.sales-page{padding:14px}.sales-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.sales-toolbar{padding:14px}.sales-filters{grid-template-columns:1fr;flex-basis:100%}.sales-actions{width:100%;justify-content:space-between;margin-left:0}.sales-pagination{align-items:flex-start;flex-direction:column;padding:12px 14px}}
</style>
