<template>
  <section class="monitor-page">
    <form class="filter-panel" @submit.prevent="search">
      <div class="filter-grid">
        <label><span>店铺</span><el-select v-model="filters.shop_name" aria-label="店铺" filterable clearable multiple collapse-tags collapse-tags-tooltip placeholder="全部店铺"><el-option v-for="shop in options.shops" :key="shop" :label="shop" :value="shop" /></el-select></label>
        <label><span>数据日期</span><el-select v-model="filters.snapshot_date" aria-label="数据日期" filterable clearable multiple collapse-tags collapse-tags-tooltip placeholder="默认最新数据"><el-option v-for="date in options.snapshot_dates" :key="date" :label="date" :value="date" /></el-select></label>
        <label><span>品牌</span><el-select v-model="filters.brand" aria-label="品牌" filterable clearable multiple collapse-tags collapse-tags-tooltip placeholder="全部品牌"><el-option v-for="brand in options.brands" :key="brand" :label="brand" :value="brand" /></el-select></label>
        <label><span>一级类目</span><el-select v-model="filters.category_l1" aria-label="一级类目" filterable clearable multiple collapse-tags collapse-tags-tooltip placeholder="全部类目"><el-option v-for="category in options.categories" :key="category" :label="category" :value="category" /></el-select></label>
        <label><span>上下柜</span><el-select v-model="filters.product_status" aria-label="上下柜筛选" clearable multiple collapse-tags collapse-tags-tooltip placeholder="全部状态"><el-option label="上柜" value="上柜" /><el-option label="下柜" value="下柜" /></el-select></label>
        <label class="keyword-filter"><span>商品 / SKU</span><el-input v-model="filters.keyword" aria-label="商品名称或 SKU" clearable placeholder="输入商品名称或 SKU" /></label>
        <div class="filter-actions">
          <el-button :loading="importing" @click="fileInput?.click()">{{ importing ? '正在导入…' : '导入库存 Excel' }}</el-button>
          <input ref="fileInput" class="file-input" type="file" accept=".xlsx" :disabled="importing" @change="uploadFile" />
          <el-button @click="reset">重置</el-button>
        </div>
      </div>
    </form>

    <el-alert v-if="importStatus" class="status-alert" :title="importStatus" type="success" show-icon closable @close="importStatus = ''" />
    <el-alert v-if="metricDataWarning" class="status-alert" :title="metricDataWarning" type="warning" show-icon :closable="false" />
    <el-alert v-if="error" class="status-alert" :title="error" type="error" show-icon :closable="false"><el-button link type="primary" @click="load">重新加载</el-button></el-alert>

    <section class="metric-summary" aria-label="库存异常与上下柜指标">
      <button v-for="metric in metricCards" :key="metric.key" type="button" :class="['metric-card', metric.className]" :aria-label="`查看${metric.label}明细`" @click="openMetric(metric.key)" @keydown.enter.prevent="openMetric(metric.key)">
        <span class="metric-card-label">{{ metric.label }}</span>
        <strong>{{ formatNumber(metric.value) }}</strong>
        <small>{{ metric.subtitle }}</small>
        <span class="metric-card-link">查看明细 ›</span>
      </button>
      <p class="metric-method">断货：仓库现货 = 0。缺货：近30日出库 ÷ 30 × {{ formatDays(turnoverDays) }}天 − 现货 &gt; 0。</p>
    </section>

    <section class="results-panel" :aria-busy="loading">
      <div class="results-toolbar">
        <div><h2>商品库存明细 <span class="count-badge">{{ formatNumber(total) }} 个 SKU</span></h2><p>数据日期：<strong>{{ snapshotDate || '暂无数据' }}</strong><span class="metric-note">库存 / 出库数量</span></p></div>
        <div class="view-controls"><label><span>查看范围</span><el-select v-model="warehouse" aria-label="查看范围" multiple collapse-tags collapse-tags-tooltip><el-option label="全国库存" value="national" /><el-option v-for="city in warehouses" :key="city" :label="`${city}仓`" :value="city" /><el-option label="全国与全部仓库" value="all" /></el-select></label><el-checkbox v-model="showMetadata">显示商品属性</el-checkbox></div>
      </div>
      <div v-if="loading" class="loading-note" role="status">正在加载库存数据…</div>
      <div class="table-wrap">
        <el-table :data="items" row-key="sku_code" stripe border class="inventory-table" height="100%" table-layout="fixed">
          <el-table-column label="商品名称 / SKU" prop="product_name" :min-width="240" fixed="left"><template #default="{ row }"><div class="product-cell"><span class="product-name" :title="row.product_name">{{ row.product_name || '未命名商品' }}</span><span class="sku-code">{{ row.sku_code }}</span></div></template></el-table-column>
          <el-table-column label="上下柜" prop="product_status" width="88" align="center"><template #default="{ row }"><el-tag v-if="row.product_status" size="small" :type="isListed(row.product_status) ? 'success' : 'info'">{{ row.product_status }}</el-tag><span v-else class="muted-value">未提供</span></template></el-table-column>
          <template v-if="showMetadata"><el-table-column v-for="field in metadataFields" :key="field.key" :prop="field.key" :label="field.label" :min-width="88" show-overflow-tooltip /></template>
          <el-table-column v-for="group in visibleGroups" :key="group.key" :label="group.label" align="center"><el-table-column v-for="metric in metrics" :key="metric.key" :label="metric.label" :min-width="80" align="right" header-align="right"><template #header><span :title="metric.full">{{ metric.label }}</span></template><template #default="{ row }"><span :class="['metric-value', { 'stock-value': metric.key === 'stock_qty' }]">{{ formatNumber(group.key === 'national' ? row['national_' + metric.key] : row.city_metrics?.[group.key]?.[metric.key]) }}</span></template></el-table-column></el-table-column>
          <template #empty><div class="empty-state"><strong>{{ loading ? '正在加载…' : error ? '数据加载失败' : '暂无匹配的库存数据' }}</strong><span v-if="!loading">{{ error ? '请重新加载后查看库存明细' : '可调整筛选条件，或导入库存 Excel 后查看' }}</span><el-button v-if="!loading && !error && hasAppliedFilters" link type="primary" @click="reset">恢复默认筛选</el-button></div></template>
        </el-table>
      </div>
      <footer class="pagination-bar"><span class="page-caption">{{ total ? `当前显示 ${rangeStart}–${rangeEnd} 条，共 ${formatNumber(total)} 条` : '共 0 条记录' }}</span><el-config-provider :locale="zhCn"><el-pagination :current-page="page" :page-size="pageSize" :total="total" :page-sizes="[20, 50, 100, 200]" :pager-count="5" :disabled="loading" background layout="sizes, prev, pager, next, jumper" @update:page-size="changePageSize" @update:current-page="changePage" /></el-config-provider></footer>
    </section>

  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElAlert, ElButton, ElCheckbox, ElConfigProvider, ElInput, ElOption, ElPagination, ElSelect, ElTable, ElTableColumn, ElTag } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import request from '../utils/request'

type MetricKey = 'stock_qty' | 'orderable_qty' | 'sales_1d' | 'sales_7d' | 'sales_30d'
type MonitorMetric = 'stockout' | 'shortage' | 'listed' | 'delisted'
type MonitorRow = Record<string, any> & { sku_code: string; city_metrics: Record<string, Record<MetricKey, number>> }
type Filters = { snapshot_date: string[]; keyword: string; brand: string[]; category_l1: string[]; shop_name: string[]; product_status: string[] }
type FilterOptions = { snapshot_dates: string[]; brands: string[]; categories: string[]; shops: string[] }
type Summary = { snapshot_date?: string; stock_qty: number; orderable_qty: number; sales_1d: number; sales_7d: number; sales_30d: number; metrics: Record<MonitorMetric, number>; turnover_days: number }

const metrics: { key: MetricKey; label: string; full: string }[] = [{ key: 'stock_qty', label: '现货', full: '现货库存' }, { key: 'orderable_qty', label: '可订购', full: '可订购库存' }, { key: 'sales_1d', label: '昨出库', full: '昨日出库' }, { key: 'sales_7d', label: '近7日', full: '近7日出库' }, { key: 'sales_30d', label: '近30日', full: '近30日出库' }]
const metadataFields = [{ key: 'brand', label: '品牌' }, { key: 'category_l1', label: '一级类目' }, { key: 'category_l2', label: '二级类目' }, { key: 'category_l3', label: '三级类目' }, { key: 'shop_name', label: '店铺名称' }, { key: 'snapshot_date', label: '数据日期' }]
const emptyFilters = (): Filters => ({ snapshot_date: [], keyword: '', brand: [], category_l1: [], shop_name: [], product_status: ['上柜'] })
const emptySummary = (): Summary => ({ snapshot_date: '', stock_qty: 0, orderable_qty: 0, sales_1d: 0, sales_7d: 0, sales_30d: 0, metrics: { stockout: 0, shortage: 0, listed: 0, delisted: 0 }, turnover_days: 30 })
const filters = reactive<Filters>(emptyFilters())
const appliedFilters = ref<Filters>(emptyFilters())
const options = ref<FilterOptions>({ snapshot_dates: [], brands: [], categories: [], shops: [] })
const summary = reactive<Summary>(emptySummary())
const warehouses = ref(['北京', '上海', '广州', '成都', '武汉', '沈阳', '西安', '德州'])
const warehouse = ref<string[]>(['all'])
const showMetadata = ref(false)
const items = ref<MonitorRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const loading = ref(false)
const error = ref('')
const metricDataWarning = ref('')
const snapshotDate = ref('')
const importing = ref(false)
const importStatus = ref('')
const fileInput = ref<HTMLInputElement>()
let requestId = 0
let disposed = false
let searchTimer: ReturnType<typeof setTimeout> | undefined

const visibleGroups = computed(() => warehouse.value.includes('all') ? [{ key: 'national', label: '全国' }, ...warehouses.value.map(city => ({ key: city, label: `${city}仓` }))] : warehouse.value.map(key => ({ key, label: key === 'national' ? '全国' : `${key}仓` })))
const hasAppliedFilters = computed(() => Object.values(appliedFilters.value).some(v => Array.isArray(v) ? v.length > 0 : Boolean(v)))
const rangeStart = computed(() => total.value ? (page.value - 1) * pageSize.value + 1 : 0)
const rangeEnd = computed(() => Math.min(page.value * pageSize.value, total.value))
const turnoverDays = computed(() => Number(summary.turnover_days || 30))
const metricCards = computed(() => [
  { key: 'stockout' as MonitorMetric, label: '断货', value: toFiniteNumber(summary.metrics?.stockout), subtitle: '个 SKU-仓，现货为 0', className: 'metric-danger' },
  { key: 'shortage' as MonitorMetric, label: '缺货', value: toFiniteNumber(summary.metrics?.shortage), subtitle: `个 SKU-仓，按${formatDays(turnoverDays.value)}天周转`, className: 'metric-warning' },
  { key: 'listed' as MonitorMetric, label: '上柜', value: toFiniteNumber(summary.metrics?.listed), subtitle: '个 SKU 已上柜', className: 'metric-success' },
  { key: 'delisted' as MonitorMetric, label: '下柜', value: toFiniteNumber(summary.metrics?.delisted), subtitle: '个 SKU 已下柜', className: 'metric-muted' },
])

function toFiniteNumber(value: unknown, fallback = 0) {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : fallback
}

const formatNumber = (value: unknown) => toFiniteNumber(value).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
const formatDays = (value: unknown) => toFiniteNumber(value, 30).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
const errorMessage = (reason: any, fallback: string) => typeof reason?.response?.data?.detail === 'string' ? reason.response.data.detail : reason?.message || fallback
const isListed = (status: unknown) => ['上柜', '可上柜', '上架', '可上架', '在售'].includes(String(status || ''))

const emit = defineEmits<{
  (event: 'open-metric-page', payload: { metric: MonitorMetric; filters: Filters }): void
}>()

function applySummary(source: any) {
  const next = emptySummary()
  if (source && typeof source === 'object') {
    Object.assign(next, source)
  }
  next.stock_qty = toFiniteNumber(source?.stock_qty)
  next.orderable_qty = toFiniteNumber(source?.orderable_qty)
  next.sales_1d = toFiniteNumber(source?.sales_1d)
  next.sales_7d = toFiniteNumber(source?.sales_7d)
  next.sales_30d = toFiniteNumber(source?.sales_30d)
  next.turnover_days = toFiniteNumber(source?.turnover_days, 30)
  next.metrics = {
    stockout: toFiniteNumber(source?.metrics?.stockout),
    shortage: toFiniteNumber(source?.metrics?.shortage),
    listed: toFiniteNumber(source?.metrics?.listed),
    delisted: toFiniteNumber(source?.metrics?.delisted),
  }
  Object.assign(summary, next)
}

async function load() {
  const id = ++requestId
  loading.value = true
  error.value = ''
  try {
    const response: any = await request.get('/inventory-monitor', { params: { ...appliedFilters.value, page: page.value, page_size: pageSize.value } })
    if (id !== requestId || disposed) return
    const data = response?.data || {}
    total.value = Number(data.total || 0)
    const lastPage = Math.max(1, Math.ceil(total.value / pageSize.value))
    if (page.value > lastPage) { page.value = lastPage; await load(); return }
    items.value = Array.isArray(data.items) ? data.items : []
    snapshotDate.value = data.summary?.snapshot_date || appliedFilters.value.snapshot_date?.join(', ') || ''
    metricDataWarning.value = data.summary?.metrics && typeof data.summary.metrics === 'object'
      ? ''
      : '当前服务未返回指标卡统计，请重启后端服务并刷新页面；明细列表仍可继续查看。'
    applySummary(data.summary)
    if (Array.isArray(data.warehouses) && data.warehouses.length) warehouses.value = data.warehouses
    if (data.filter_options) for (const key of ['snapshot_dates', 'brands', 'categories', 'shops'] as const) options.value[key] = Array.isArray(data.filter_options[key]) ? data.filter_options[key] : []
  } catch (reason: unknown) {
    if (id !== requestId || disposed) return
    error.value = errorMessage(reason, '库存看板数据加载失败')
    total.value = 0
    items.value = []
    snapshotDate.value = ''
    metricDataWarning.value = ''
  } finally { if (id === requestId && !disposed) loading.value = false }
}

function search() { appliedFilters.value = { ...filters, keyword: filters.keyword.trim() }; page.value = 1; void load() }
function reset() { Object.assign(filters, emptyFilters()) }
function openMetric(metric: MonitorMetric) {
  emit('open-metric-page', {
    metric,
    filters: {
      snapshot_date: [...filters.snapshot_date],
      keyword: filters.keyword.trim(),
      brand: [...filters.brand],
      category_l1: [...filters.category_l1],
      shop_name: [...filters.shop_name],
      product_status: [...filters.product_status],
    },
  })
}
function changePage(next: number) { if (next !== page.value) { page.value = next; void load() } }
function changePageSize(next: number) { if (next !== pageSize.value) { pageSize.value = next; page.value = 1; void load() } }
async function uploadFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || importing.value) return
  if (!file.name.toLowerCase().endsWith('.xlsx')) { error.value = '请选择 .xlsx 格式的库存文件'; input.value = ''; return }
  importing.value = true
  importStatus.value = ''
  const form = new FormData()
  form.append('file', file)
  try {
    const response: any = await request.post('/inventory-monitor/import', form)
    if (disposed) return
    const imported = response?.data || {}
    importStatus.value = imported.status_field_detected === false ? '库存文件导入成功，但文件未包含“上下柜状态”字段，上柜/下柜指标暂为 0。' : '库存文件导入成功，已刷新当前筛选结果。'
    page.value = 1
    await load()
  } catch (reason: unknown) { if (!disposed) error.value = errorMessage(reason, '导入失败，请检查文件后重试') }
  finally { importing.value = false; input.value = '' }
}

watch(filters, () => { if (searchTimer) clearTimeout(searchTimer); searchTimer = setTimeout(() => { searchTimer = undefined; search() }, 300) })
onMounted(() => { void load() })
onBeforeUnmount(() => { disposed = true; requestId++; if (searchTimer) clearTimeout(searchTimer) })
</script>

<style scoped>
.monitor-page{flex:1;min-height:0;box-sizing:border-box;padding:18px;background:var(--app-bg,#f5f7fb);color:var(--text-primary,#1e293b);--el-color-primary:light-dark(#0f766e, #2dd4bf);--el-border-radius-base:8px;display:flex;flex-direction:column;overflow:hidden}
.filter-panel,.results-panel,.metric-summary{border:1px solid var(--border-color,#e5eaf2);border-radius:12px;background:var(--app-surface,#fff);box-shadow:0 2px 6px #16325704}.filter-panel{flex-shrink:0;padding:14px 20px;margin-bottom:12px}.filter-grid{display:grid;grid-template-columns:repeat(4,minmax(125px,1fr));gap:16px}.filter-grid>label{display:flex;flex-direction:column;gap:8px;min-width:0}.filter-grid>label>span{color:var(--text-secondary,#64748b);font-size:12px}.filter-grid .keyword-filter{grid-column:span 2}.filter-grid :deep(.el-select){width:100%}.filter-actions{display:flex;align-items:flex-end;justify-content:flex-end;gap:8px;grid-column:span 2}.filter-actions .el-button{min-width:80px}.file-input{display:none}.filter-grid :deep(.el-select__wrapper),.filter-grid :deep(.el-input__wrapper){min-height:36px;box-sizing:border-box}.status-alert{flex-shrink:0;margin-bottom:12px}
.metric-summary{position:relative;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;padding:12px;margin-bottom:12px;flex-shrink:0}.metric-card{position:relative;min-height:104px;padding:14px 16px;border:1px solid var(--border-color,#e5eaf2);border-top:3px solid #94a3b8;border-radius:10px;background:light-dark(#fff, var(--app-surface));text-align:left;cursor:pointer;transition:transform .16s ease,box-shadow .16s ease,border-color .16s ease}.metric-card:hover,.metric-card:focus-visible{transform:translateY(-1px);box-shadow:0 5px 14px rgba(15,23,42,.09);outline:none}.metric-card-label{display:block;color:light-dark(#64748b, var(--text-secondary));font-size:13px}.metric-card strong{display:block;margin-top:7px;color:light-dark(#0f172a, var(--text-primary));font-size:27px;line-height:1;font-variant-numeric:tabular-nums}.metric-card small{display:block;margin-top:9px;color:light-dark(#94a3b8, var(--text-secondary));font-size:11px}.metric-card-link{position:absolute;right:14px;bottom:14px;color:light-dark(#64748b, var(--text-secondary));font-size:11px}.metric-danger{border-top-color:#dc2626}.metric-danger .metric-card-link,.metric-danger strong{color:light-dark(#b91c1c, #fca5a5)}.metric-warning{border-top-color:#f97316}.metric-warning .metric-card-link,.metric-warning strong{color:light-dark(#c2410c, #fb923c)}.metric-success{border-top-color:#0f766e}.metric-success .metric-card-link,.metric-success strong{color:light-dark(#0f766e, var(--text-accent))}.metric-muted{border-top-color:#64748b}.metric-method{grid-column:1/-1;margin:0 2px 1px;color:light-dark(#94a3b8, var(--text-secondary));font-size:11px}
.results-panel{flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden}.table-wrap{flex:1;min-height:0;position:relative}.results-toolbar{flex-shrink:0;display:flex;align-items:center;justify-content:space-between;gap:20px;padding:16px 20px}.results-toolbar h2{font-size:15px;margin:0;font-weight:600}.count-badge{display:inline-block;margin-left:8px;padding:3px 8px;border-radius:5px;background:var(--primary-surface,#ecfdf5);color:var(--text-accent,#0f766e);font-size:12px;font-weight:500}.results-toolbar p{font-size:12px;color:var(--text-muted,#94a3b8);margin:10px 0 0}.results-toolbar strong{color:var(--text-secondary,#64748b);font-weight:500}.metric-note{margin-left:14px;padding-left:14px;border-left:1px solid light-dark(#e2e8f0, var(--border-color))}.view-controls{display:flex;align-items:center;gap:18px;flex-wrap:wrap}.view-controls label{display:flex;align-items:center;gap:10px;font-size:12px;color:var(--text-secondary,#64748b)}.view-controls :deep(.el-select){width:240px}.view-controls :deep(.el-checkbox__label){font-size:12px}.loading-note{flex-shrink:0;padding:9px 22px;background:var(--primary-surface,#ecfdf5);color:var(--text-accent,#0f766e);font-size:12px}.inventory-table{width:100%;--el-table-header-bg-color:var(--table-header-bg,#f8fafc);--el-table-header-text-color:var(--text-secondary,#64748b);--el-table-border-color:var(--border-color,#e9edf4);--el-table-bg-color:var(--app-surface,#fff);--el-table-tr-bg-color:var(--app-surface,#fff);--el-table-row-hover-bg-color:var(--primary-surface,#f0fdfa);--el-table-text-color:var(--text-primary,#334155);font-size:11px}.inventory-table :deep(th.el-table__cell){font-weight:500;padding:4px 0}.inventory-table :deep(td.el-table__cell){padding:4px 0}.inventory-table :deep(.cell){padding-left:9px;padding-right:9px}.product-cell{display:flex;flex-direction:column;gap:1px;line-height:1.35}.product-name{font-size:11px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.sku-code{color:light-dark(#000, var(--text-primary));font-size:9px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.metric-value{font-variant-numeric:tabular-nums;font-size:11px}.stock-value{font-weight:600;color:var(--text-accent,#0f766e)}.muted-value{color:light-dark(#a8b0bb, var(--text-secondary));font-size:11px}.empty-state{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;min-height:220px;line-height:1.6}.empty-state strong{color:var(--text-secondary,#64748b);font-size:14px;font-weight:500}.empty-state span{color:var(--text-muted,#94a3b8);font-size:12px}.pagination-bar{flex-shrink:0;display:flex;justify-content:space-between;align-items:center;gap:16px;padding:12px 20px;flex-wrap:wrap}.page-caption{font-size:12px;color:var(--text-secondary,#64748b)}.pagination-bar :deep(.el-pagination){flex-wrap:wrap;row-gap:10px}
.analysis-dialog-context{display:flex;align-items:center;gap:20px;flex-wrap:wrap;margin:-4px 0 10px;padding:9px 12px;border:1px solid light-dark(#dbeafe, var(--border-color));border-radius:8px;background:light-dark(#eff6ff, rgba(96, 165, 250, .12));color:light-dark(#64748b, var(--text-secondary));font-size:12px}.analysis-dialog-context strong{color:light-dark(#1e3a8a, #93c5fd);font-weight:600}.analysis-dialog-tabs{min-height:580px}.analysis-dialog-tabs :deep(.el-tabs__content){overflow:visible}.analysis-dialog-tabs :deep(.el-tab-pane){padding-top:4px}.detail-intro{display:flex;justify-content:space-between;gap:12px;margin:0 0 12px;color:light-dark(#64748b, var(--text-secondary));font-size:12px}.detail-alert{margin-bottom:12px}.detail-table{width:100%;font-size:12px}.shortage-value{color:light-dark(#c2410c, #fb923c)}.detail-empty{padding:56px 0;color:light-dark(#94a3b8, var(--text-secondary));text-align:center}.detail-footer{display:flex;align-items:center;justify-content:space-between;gap:14px;padding-top:12px;color:light-dark(#64748b, var(--text-secondary));font-size:12px}.detail-footer :deep(.el-pagination){flex-wrap:wrap;justify-content:flex-end}
.analysis-dialog-tabs :deep(.forecast-workbench){min-height:0;padding:0;background:transparent}.analysis-dialog-tabs :deep(.forecast-workbench > .page-heading){display:none}.analysis-dialog-tabs :deep(.purchase-panel){border-top:0;padding-top:0}.analysis-dialog-tabs :deep(.warning-panel){padding:0}.monitor-settings-panel{display:flex;flex-direction:column;gap:14px}.settings-toolbar{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.settings-toolbar h3{margin:0;color:light-dark(#1e293b, var(--text-primary));font-size:16px}.settings-toolbar p{margin:6px 0 0;color:light-dark(#94a3b8, var(--text-secondary));font-size:12px}.settings-brand-filter{width:220px}.policy-table{width:100%;min-height:180px}.policy-editor-card{padding:16px;border:1px solid light-dark(#e5e7eb, var(--border-color));border-radius:10px;background:light-dark(#f8fafc, var(--app-surface-2))}.policy-editor-heading{display:flex;align-items:center;gap:10px;margin-bottom:14px}.policy-editor-heading strong{color:light-dark(#334155, var(--text-primary));font-size:14px}.policy-editor-heading span{color:light-dark(#94a3b8, var(--text-secondary));font-size:12px}.policy-editor-grid{display:grid;grid-template-columns:minmax(160px,1.4fr) repeat(3,minmax(130px,1fr)) minmax(140px,1fr) auto;align-items:end;gap:12px}.policy-editor-grid label{display:flex;flex-direction:column;gap:7px;color:light-dark(#64748b, var(--text-secondary));font-size:12px}.policy-editor-grid label :deep(.el-select),.policy-editor-grid label :deep(.el-input-number){width:100%}.policy-switch-field{padding-bottom:9px}.policy-editor-grid>.el-button{min-width:110px}
@media(min-width:1500px){.filter-grid{grid-template-columns:repeat(5,minmax(130px,1fr)) minmax(200px,1.4fr) auto;gap:14px}.filter-grid .keyword-filter,.filter-actions{grid-column:auto}}
@media(max-width:1050px){.metric-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.results-toolbar{align-items:flex-start;flex-direction:column}.view-controls{width:100%;justify-content:space-between}.monitor-page{padding:20px}}
@media(max-width:640px){.monitor-page{padding:14px}.filter-panel{padding:16px}.filter-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.filter-grid .keyword-filter{grid-column:span 2}.filter-actions{justify-content:flex-start;align-items:flex-start}.metric-summary{grid-template-columns:1fr;padding:10px}.metric-method{grid-column:auto}.results-toolbar{padding:16px}.view-controls{gap:8px}.metric-note{display:none}.pagination-bar{padding:16px}.detail-intro,.detail-footer{align-items:flex-start;flex-direction:column}.detail-footer :deep(.el-pagination){justify-content:flex-start}}
@media(max-width:900px){.settings-toolbar{flex-direction:column}.settings-brand-filter{width:100%}.policy-editor-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.policy-editor-grid>.el-button{width:100%}}
@media(max-width:640px){.analysis-dialog-context{gap:8px;flex-direction:column;align-items:flex-start}.analysis-dialog-tabs{min-height:0}.policy-editor-grid{grid-template-columns:1fr}}
</style>
