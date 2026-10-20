<template>
  <section class="jst-page">
    <el-alert v-if="importStatus" class="page-alert" :title="importStatus" type="success" show-icon closable @close="importStatus = ''" />
    <el-alert v-if="error" class="page-alert" :title="error" type="error" show-icon :closable="false">
      <el-button link type="primary" @click="load">重新加载</el-button>
    </el-alert>

    <Teleport to="body">
      <div v-if="previewImage" class="jst-image-preview-overlay" role="dialog" aria-modal="true" aria-label="商品大图预览" @click="closeImagePreview">
        <button class="jst-image-preview-close" type="button" aria-label="关闭大图预览" @click.stop="closeImagePreview">×</button>
        <img class="jst-image-preview-large" :src="previewImage" alt="商品大图" :style="{ transform: `scale(${previewScale})` }" @click="closeImagePreview" @wheel.prevent.stop="handlePreviewWheel" />
      </div>
    </Teleport>

    <section class="kpi-grid" aria-label="库存关键指标">
      <article class="kpi-card kpi-primary"><span>商品 SKU</span><strong>{{ formatNumber(summary.sku_count) }}</strong><small>{{ formatNumber(summary.brand_count) }} 个品牌</small></article>
      <article class="kpi-card"><span>实际库存</span><strong>{{ formatNumber(summary.actual_stock) }}</strong><small>当前在库商品</small></article>
      <article class="kpi-card"><span>订单占有</span><strong>{{ formatNumber(summary.order_occupied) }}</strong><small>已被订单占用</small></article>
      <article class="kpi-card"><span>可用库存</span><strong>{{ formatNumber(summary.available_stock) }}</strong><small>实际库存减订单占有</small></article>
      <article class="kpi-card kpi-warning"><span>缺货 / 负库存</span><strong>{{ formatNumber(summary.zero_count + summary.negative_count) }}</strong><small>{{ formatNumber(summary.low_count) }} 个 SKU 仅余 1–5 件</small></article>
    </section>

    <section class="chart-grid">
      <article class="panel chart-panel">
        <div class="panel-head"><div><h2>品牌库存排行</h2><p>按实际库存量排序，展示前 12 个品牌</p></div></div>
        <VChart :option="brandOption" autoresize class="chart" />
      </article>
      <article class="panel chart-panel">
        <div class="panel-head"><div><h2>SKU 库存健康度</h2><p>按可用库存件数分层</p></div></div>
        <VChart :option="stockOption" autoresize class="chart" />
      </article>
    </section>

    <section class="panel detail-panel">
      <div class="panel-head detail-head">
        <form class="filters" @submit.prevent="search">
          <el-input v-model="filters.keyword" clearable placeholder="商品名称 / 商品编码 / 款式编码" aria-label="商品搜索" />
          <el-select v-model="filters.brand" filterable clearable multiple collapse-tags collapse-tags-tooltip placeholder="全部品牌" aria-label="品牌">
            <el-option v-for="brand in options.brands" :key="brand" :label="brand" :value="brand" />
          </el-select>
          <el-select v-model="filters.stock_status" clearable placeholder="全部库存状态" aria-label="库存状态">
            <el-option label="负库存" value="negative" />
            <el-option label="零库存" value="zero" />
            <el-option label="低库存（1–5）" value="low" />
            <el-option label="库存充足（>5）" value="healthy" />
            <el-option label="存在订单占用" value="occupied" />
          </el-select>
        </form>
        <div class="detail-heading"><h2>商品库存明细</h2><p>共 {{ formatNumber(total) }} 条，库存更新时间 {{ updateRange }}</p></div>
        <div class="detail-actions">
          <div v-if="batch.source_name" class="source-meta">
            <span>{{ batch.source_name }}</span>
            <small>{{ batch.imported_at || '已导入' }} · {{ formatNumber(batch.image_count) }} 张商品图</small>
          </div>
          <el-button type="primary" :loading="importing" @click="fileInput?.click()">
            {{ importing ? '正在导入…' : '更新商品资料' }}
          </el-button>
          <input ref="fileInput" class="file-input" type="file" accept=".xlsx" @change="uploadFile" />
        </div>
      </div>

      <div class="table-wrap" :aria-busy="loading">
        <div v-if="loading" class="loading-note">正在加载聚水潭商品资料…</div>
        <el-table :data="items" row-key="product_code" stripe height="100%" table-layout="fixed" class="product-table">
          <el-table-column label="商品" min-width="245" fixed="left">
            <template #default="{ row }">
              <div class="product-cell">
                <div v-if="row.image_url" class="product-image product-image-clickable" role="button" tabindex="0" @click="openImagePreview(row.image_url)" @keydown.enter.prevent="openImagePreview(row.image_url)" @keydown.space.prevent="openImagePreview(row.image_url)">
                  <el-image
                    :src="row.image_url"
                    :alt="row.product_name"
                    fit="contain"
                    loading="lazy"
                    class="product-image-preview"
                  >
                    <template #error><span>加载失败</span></template>
                  </el-image>
                </div>
                <div v-else class="product-image">
                  <span>暂无图</span>
                </div>
                <div class="product-copy">
                  <strong :title="row.product_name">{{ row.product_name || '未命名商品' }}</strong>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="product_code" label="商品编码" min-width="150" show-overflow-tooltip class-name="code-column" />
          <el-table-column prop="style_code" label="款式编码" min-width="138" show-overflow-tooltip class-name="code-column">
            <template #default="{ row }">{{ row.style_code || '-' }}</template>
          </el-table-column>
          <el-table-column prop="brand" label="品牌" min-width="120" show-overflow-tooltip />
          <el-table-column label="颜色 / 规格" min-width="175" show-overflow-tooltip>
            <template #default="{ row }">{{ row.color_spec || [row.color, row.spec].filter(Boolean).join(' / ') || '-' }}</template>
          </el-table-column>
          <el-table-column prop="actual_stock" label="实际库存" min-width="112" align="right"><template #default="{ row }"><strong class="number">{{ formatNumber(row.actual_stock) }}</strong></template></el-table-column>
          <el-table-column prop="order_occupied" label="订单占有" min-width="112" align="right"><template #default="{ row }"><span class="number occupied">{{ formatNumber(row.order_occupied) }}</span></template></el-table-column>
          <el-table-column prop="available_stock" label="可用数" min-width="112" align="right">
            <template #default="{ row }"><span :class="['stock-pill', stockClass(row.available_stock)]">{{ formatNumber(row.available_stock) }}</span></template>
          </el-table-column>
          <el-table-column prop="stock_updated_at" label="库存更新时间" min-width="168" />
          <template #empty><div class="empty-state">{{ error ? '数据加载失败' : '暂无匹配商品，请调整筛选条件或导入商品资料' }}</div></template>
        </el-table>
      </div>
      <footer class="pagination-bar">
        <span>{{ total ? `当前 ${rangeStart}–${rangeEnd} 条，共 ${formatNumber(total)} 条` : '共 0 条记录' }}</span>
        <el-pagination :current-page="page" :page-size="pageSize" :total="total" :page-sizes="[20, 50, 100, 200]" background layout="sizes, prev, pager, next, jumper" @update:page-size="changePageSize" @update:current-page="changePage" />
      </footer>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { ElAlert, ElButton, ElImage, ElInput, ElOption, ElPagination, ElSelect, ElTable, ElTableColumn } from 'element-plus'
import request from '../utils/request'

use([CanvasRenderer, BarChart, PieChart, GridComponent, LegendComponent, TooltipComponent])

type Summary = {
  sku_count: number; brand_count: number; actual_stock: number; order_occupied: number; available_stock: number
  negative_count: number; zero_count: number; low_count: number; healthy_count: number
  stock_updated_min: string; stock_updated_max: string
}
type Filters = { keyword: string; brand: string[]; stock_status: string }
type ProductRow = Record<string, any> & { product_code: string; available_stock: number }
const emptySummary = (): Summary => ({ sku_count: 0, brand_count: 0, actual_stock: 0, order_occupied: 0, available_stock: 0, negative_count: 0, zero_count: 0, low_count: 0, healthy_count: 0, stock_updated_min: '', stock_updated_max: '' })
const emptyFilters = (): Filters => ({ keyword: '', brand: [], stock_status: '' })

const summary = reactive<Summary>(emptySummary())
const filters = reactive<Filters>(emptyFilters())
const appliedFilters = ref<Filters>(emptyFilters())
const options = reactive({ brands: [] as string[] })
const items = ref<ProductRow[]>([])
const brandRanking = ref<any[]>([])
const batch = reactive<Record<string, any>>({})
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
const updateRange = computed(() => {
  const first = String(summary.stock_updated_min || '').slice(0, 10)
  const last = String(summary.stock_updated_max || '').slice(0, 10)
  if (!first && !last) return '暂无'
  return first === last ? first : `${first || '-'} 至 ${last || '-'}`
})
const brandOption = computed(() => ({
  animationDuration: 500,
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (value: unknown) => `${formatNumber(value)} 件` },
  grid: { left: 18, right: 24, top: 8, bottom: 10, containLabel: true },
  xAxis: { type: 'value', axisLabel: { color: '#94a3b8', formatter: (value: number) => formatNumber(value) }, splitLine: { lineStyle: { color: '#eef2f7' } } },
  yAxis: { type: 'category', inverse: true, data: brandRanking.value.map(item => item.brand), axisLabel: { color: '#475569', width: 92, overflow: 'truncate' }, axisTick: { show: false }, axisLine: { show: false } },
  series: [{ type: 'bar', data: brandRanking.value.map(item => item.actual_stock), barMaxWidth: 16, itemStyle: { color: '#0f766e', borderRadius: [0, 4, 4, 0] } }],
}))
const stockOption = computed(() => ({
  tooltip: { trigger: 'item', formatter: '{b}<br/>{c} 个 SKU（{d}%）' },
  legend: { bottom: 0, itemWidth: 10, itemHeight: 10, textStyle: { color: '#64748b', fontSize: 11 } },
  series: [{ type: 'pie', radius: ['48%', '72%'], center: ['50%', '44%'], avoidLabelOverlap: true, label: { formatter: '{b}\n{c}', color: '#475569', fontSize: 11 }, data: [
    { name: '负库存', value: summary.negative_count, itemStyle: { color: '#dc2626' } },
    { name: '零库存', value: summary.zero_count, itemStyle: { color: '#f97316' } },
    { name: '低库存 1–5', value: summary.low_count, itemStyle: { color: '#fbbf24' } },
    { name: '库存充足', value: summary.healthy_count, itemStyle: { color: '#0f766e' } },
  ] }],
}))

const errorMessage = (reason: any, fallback: string) => typeof reason?.response?.data?.detail === 'string' ? reason.response.data.detail : reason?.message || fallback
function stockClass(value: unknown) { const n = Number(value || 0); return n < 0 ? 'danger' : n === 0 ? 'zero' : n <= 5 ? 'low' : 'healthy' }
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
    const response: any = await request.get('/jushuitan-dashboard', { params: { ...appliedFilters.value, page: page.value, page_size: pageSize.value } })
    if (disposed || id !== requestId) return
    const data = response?.data || {}
    Object.assign(summary, emptySummary(), data.summary || {})
    Object.assign(batch, data.batch || {})
    items.value = Array.isArray(data.items) ? data.items : []
    brandRanking.value = Array.isArray(data.brand_ranking) ? data.brand_ranking : []
    options.brands = Array.isArray(data.filter_options?.brands) ? data.filter_options.brands : []
    total.value = Number(data.total || 0)
    const lastPage = Math.max(1, Math.ceil(total.value / pageSize.value))
    if (page.value > lastPage) { page.value = lastPage; await load() }
  } catch (reason: unknown) {
    if (disposed || id !== requestId) return
    error.value = errorMessage(reason, '商品库存看板加载失败')
    items.value = []
    total.value = 0
  } finally { if (!disposed && id === requestId) loading.value = false }
}
function search() { appliedFilters.value = { keyword: filters.keyword.trim(), brand: [...filters.brand], stock_status: filters.stock_status }; page.value = 1; void load() }
watch(filters, () => { if (searchTimer) clearTimeout(searchTimer); searchTimer = setTimeout(search, 300) })
function changePage(next: number) { page.value = next; void load() }
function changePageSize(next: number) { pageSize.value = next; page.value = 1; void load() }
async function uploadFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || importing.value) return
  if (!file.name.toLowerCase().endsWith('.xlsx')) { error.value = '请选择 .xlsx 格式的聚水潭商品资料'; input.value = ''; return }
  importing.value = true
  importStatus.value = ''
  const form = new FormData()
  form.append('file', file)
  try {
    const response: any = await request.post('/jushuitan-dashboard/import', form)
    if (disposed) return
    importStatus.value = `导入完成：${formatNumber(response?.data?.row_count)} 个 SKU，${formatNumber(response?.data?.image_count)} 张商品图。`
    Object.assign(filters, emptyFilters())
    appliedFilters.value = emptyFilters()
    page.value = 1
    await load()
  } catch (reason: unknown) { if (!disposed) error.value = errorMessage(reason, '导入失败，请检查文件后重试') }
  finally { importing.value = false; input.value = '' }
}
onMounted(() => { void load() })
onBeforeUnmount(() => { disposed = true; requestId++; if (searchTimer) clearTimeout(searchTimer) })
</script>

<style scoped>
.jst-page{min-height:100%;padding:22px;background:var(--app-bg,#f8fafc);color:var(--text-primary,#1f2937);--el-color-primary:light-dark(#0f766e, #2dd4bf)}.page-head{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;margin-bottom:18px}.eyebrow{margin:0 0 7px;color:light-dark(#0f766e, var(--text-accent));font-size:12px;font-weight:700;letter-spacing:.12em}.page-head h1{margin:0;color:var(--text-heading,#0f172a);font-size:26px;line-height:1.2}.subtitle{margin:7px 0 0;color:var(--text-secondary,#64748b);font-size:13px}.head-actions{display:flex;align-items:center;gap:14px}.source-meta{display:flex;min-width:0;max-width:350px;flex-direction:column;text-align:right}.source-meta span{overflow:hidden;color:var(--text-primary);font-size:12px;text-overflow:ellipsis;white-space:nowrap}.source-meta small{margin-top:4px;color:var(--text-muted);font-size:11px}.file-input{display:none}.page-alert{margin-bottom:14px}.kpi-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px;margin-bottom:14px}.kpi-card{position:relative;overflow:hidden;min-height:112px;padding:18px;border:1px solid var(--border-color,#e2e8f0);border-radius:14px;background:var(--app-surface,#fff);box-shadow:var(--shadow-sm);display:flex;flex-direction:column}.kpi-card span{color:var(--text-secondary);font-size:12px}.kpi-card strong{margin-top:11px;color:var(--text-heading);font-size:26px;font-variant-numeric:tabular-nums;line-height:1}.kpi-card small{margin-top:auto;color:var(--text-muted);font-size:11px}.kpi-primary{border-top:3px solid #0f766e}.kpi-warning{border-top:3px solid #f97316}.chart-grid{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(320px,.85fr);gap:14px;margin-bottom:14px}.panel{border:1px solid var(--border-color,#e2e8f0);border-radius:14px;background:var(--app-surface,#fff);box-shadow:var(--shadow-sm)}.chart-panel{min-height:330px;display:flex;flex-direction:column}.panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding:17px 20px 4px}.panel-head h2{margin:0;color:var(--text-heading);font-size:15px}.panel-head p{margin:6px 0 0;color:var(--text-muted);font-size:11px}.chart{width:100%;height:275px}.detail-panel{min-height:520px;display:flex;flex-direction:column;overflow:hidden}.detail-head{align-items:flex-end;padding-bottom:14px}.filters{display:grid;grid-template-columns:minmax(240px,1.4fr) minmax(170px,1fr) minmax(170px,1fr);gap:10px;width:min(720px,62%)}.filters :deep(.el-select){width:100%}.table-wrap{position:relative;height:520px;min-height:360px;border-top:1px solid var(--border-subtle,#edf2f7)}.loading-note{position:absolute;top:0;right:0;left:0;z-index:3;padding:8px 20px;background:light-dark(#ecfdf5, var(--primary-surface-2));color:light-dark(#0f766e, var(--text-accent));font-size:12px}.product-table{width:100%;--el-table-header-bg-color:var(--table-header-bg,#f8fafc);--el-table-header-text-color:var(--text-secondary,#64748b);--el-table-border-color:var(--border-subtle,#edf2f7);--el-table-row-hover-bg-color:light-dark(#f0fdfa, var(--primary-surface-2));font-size:12px}.product-table :deep(th.el-table__cell){padding:9px 0}.product-table :deep(td.el-table__cell){padding:6px 0}.product-cell{display:flex;align-items:center;gap:11px;min-width:0}.product-image{width:48px;height:48px;border:1px solid light-dark(#eef2f7, var(--border-color));border-radius:8px;background:light-dark(#f8fafc, var(--app-surface-2));display:flex;flex:0 0 auto;align-items:center;justify-content:center;overflow:hidden}.product-image img{width:100%;height:100%;object-fit:contain}.product-image span{color:light-dark(#cbd5e1, var(--text-secondary));font-size:9px}.product-copy{display:flex;min-width:0;flex-direction:column;gap:3px}.product-copy strong{overflow:hidden;color:var(--text-primary);font-size:12px;text-overflow:ellipsis;white-space:nowrap}.product-copy span{color:var(--text-muted);font-size:10px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.number{font-variant-numeric:tabular-nums}.occupied{color:light-dark(#c2410c, #fb923c)}.stock-pill{display:inline-flex;min-width:46px;justify-content:flex-end;border-radius:999px;padding:3px 8px;font-weight:700;font-variant-numeric:tabular-nums}.stock-pill.healthy{background:light-dark(#ecfdf5, var(--primary-surface-2));color:light-dark(#047857, #6ee7b7)}.stock-pill.low{background:light-dark(#fffbeb, rgba(251, 191, 36, .12));color:light-dark(#b45309, #fbbf24)}.stock-pill.zero{background:light-dark(#fff7ed, rgba(251, 191, 36, .12));color:light-dark(#c2410c, #fb923c)}.stock-pill.danger{background:light-dark(#fef2f2, rgba(248, 113, 113, .12));color:light-dark(#b91c1c, #fca5a5)}.empty-state{padding:80px 0;color:var(--text-muted)}.pagination-bar{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:13px 20px;border-top:1px solid var(--border-subtle,#edf2f7);color:var(--text-secondary);font-size:12px}
.product-cell{gap:9px}
.product-table :deep(.code-column .cell){color:inherit;font-family:inherit;font-size:inherit}

@media(max-width:1250px){.kpi-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.chart-grid{grid-template-columns:1fr}.filters{width:100%}.detail-head{align-items:flex-start;flex-direction:column}}
@media(max-width:760px){.jst-page{padding:14px}.page-head{align-items:flex-start;flex-direction:column}.head-actions{width:100%;justify-content:space-between}.source-meta{text-align:left}.kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.filters{grid-template-columns:1fr}.pagination-bar{align-items:flex-start;flex-direction:column}.chart-panel{min-height:300px}}
.product-image-clickable{position:relative;cursor:zoom-in;transition:border-color .2s ease,box-shadow .2s ease}.product-image-clickable:hover{border-color:light-dark(#5eead4, var(--border-color));box-shadow:0 0 0 3px rgba(20,184,166,.12)}.product-image-preview{width:100%;height:100%;cursor:zoom-in}.product-image-preview :deep(.el-image__inner){width:100%;height:100%;object-fit:contain}.product-image-preview :deep(.el-image__error){display:flex;align-items:center;justify-content:center;color:light-dark(#cbd5e1, var(--text-secondary));font-size:9px}.jst-image-preview-overlay{position:fixed;inset:0;z-index:3000;display:flex;align-items:center;justify-content:center;padding:56px;background:rgba(15,23,42,.86);cursor:zoom-out}.jst-image-preview-large{display:block;max-width:100%;max-height:100%;object-fit:contain;cursor:zoom-out;user-select:none}.jst-image-preview-close{position:absolute;top:18px;right:24px;width:40px;height:40px;padding:0;border:0;border-radius:50%;background:rgba(255,255,255,.16);color:#fff;font-size:30px;line-height:1;cursor:pointer}.jst-image-preview-close:hover{background:rgba(255,255,255,.28)}
.jst-image-preview-overlay{background:light-dark(rgba(255,255,255,.9), rgba(15,23,42,.94))}.jst-image-preview-large{transition:transform .16s ease;transform-origin:center center}.jst-image-preview-close{background:light-dark(rgba(15,23,42,.08), rgba(255,255,255,.12));color:light-dark(#64748b, var(--text-secondary))}.jst-image-preview-close:hover{background:light-dark(rgba(15,23,42,.14), rgba(255,255,255,.2))}
.detail-head{align-items:center;flex-direction:row;gap:20px;padding:14px 20px}.detail-head .filters{order:2;width:auto;min-width:0;flex:1 1 auto;grid-template-columns:minmax(180px,1.4fr) minmax(135px,1fr) minmax(135px,1fr)}.detail-heading{order:1;flex:0 0 auto;min-width:140px;text-align:left}.detail-heading h2{margin:0;color:var(--text-heading);font-size:15px}.detail-heading p{margin:6px 0 0;color:var(--text-muted);font-size:11px;white-space:nowrap}.detail-actions{display:flex;align-items:center;justify-content:flex-end;order:3;flex:0 0 auto;gap:14px;min-width:0;margin-left:auto}.detail-actions .source-meta{max-width:200px}.detail-actions .el-button{flex:0 0 auto}
@media(max-width:1100px){.detail-head{align-items:stretch;flex-direction:column}.detail-heading{order:1;margin-left:0;text-align:left}.detail-head .filters{order:2;width:100%;flex:0 0 auto}.detail-actions{order:3;justify-content:flex-end;margin-left:0}}
@media(max-width:760px){.detail-head .filters{grid-template-columns:1fr}.detail-actions{align-items:flex-start;justify-content:space-between;flex-wrap:wrap}.detail-heading p{white-space:normal}}
</style>
