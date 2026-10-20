<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  ElAlert, ElButton, ElCard, ElCollapse, ElCollapseItem, ElDialog, ElDrawer,
  ElEmpty, ElIcon, ElInput, ElLoading, ElMessage, ElOption, ElPagination, ElSelect, ElTable,
  ElTableColumn, ElTabPane, ElTabs, ElTag, ElTooltip,
} from 'element-plus'
import {
  ArrowRight, Box, Calendar, CircleCheck, Clock, DataAnalysis, Document,
  Download, Filter, Grid, InfoFilled, Refresh, RefreshLeft, Search, Setting,
  ShoppingCart, TrendCharts, Warning,
} from '@element-plus/icons-vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'

use([CanvasRenderer, LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent])

type View = 'sku' | 'detail'
type SortDirection = 'asc' | 'desc'
type FilterKey = 'period' | 'entity' | 'category' | 'brand' | 'supplier'
type Filters = Record<FilterKey, string[]> & { sku_keyword: string }
type Decimal = string | number | null

interface Metadata {
  run_id: number | string | null
  imported_at?: string | null
  manifest_sha256?: string | null
  rule_version?: number | string | null
  periods: string[]
  entities: string[]
  categories: string[]
  brands: string[]
  coverage?: unknown[]
  quality?: Record<string, unknown>
}
interface FilterOptions {
  period: string[]
  entity: string[]
  category: string[]
  brand: string[]
}
interface Summary {
  run_id: number | string
  sales_quantity: Decimal
  return_in_quantity: Decimal
  after_sales_quantity: Decimal
  return_quantity: Decimal
  return_rate: string | null
  sku_count: number | string
  no_sales_sku_count: number | string
}
interface Item {
  sku_code: string
  sku_name: string
  brand: string
  period?: string
  entity?: string
  category?: string
  supplier_name?: string
  sales_quantity: Decimal
  return_in_quantity: Decimal
  after_sales_quantity: Decimal
  return_quantity: Decimal
  return_rate: string | null
  entity_count?: number
  supplier_count?: number
}
interface ItemsResponse {
  run_id: number | string
  total: number
  items: Item[]
}
interface MonthlyPoint {
  period: string
  sales_quantity: Decimal
  return_in_quantity: Decimal
  after_sales_quantity: Decimal
  return_quantity: Decimal
  return_rate: string | null
}
interface MonthlyTrendResponse {
  run_id: number | string
  items: MonthlyPoint[]
}
interface Source {
  relative_path: string
  sheet_name: string
  row_number: number
  document_type: string
  raw_quantity: Decimal
  included: boolean
}
interface ApiError extends Error { status?: number }
interface BrandRule {
  id?: number
  match_type: 'exact' | 'prefix'
  pattern: string
  canonical_brand: string
  priority: number
  enabled: boolean
}

const API = '/api/sku-returns'
const vLoading = ElLoading.directive
const emptyFilters = (): Filters => ({ period: [], entity: [], category: [], brand: [], supplier: [], sku_keyword: '' })
const cloneFilters = (filters: Filters): Filters => ({
  period: [...filters.period], entity: [...filters.entity], category: [...filters.category],
  brand: [...filters.brand], supplier: [...filters.supplier], sku_keyword: filters.sku_keyword.trim(),
})
const metadata = ref<Metadata | null>(null)
const filterOptions = ref<FilterOptions>({ period: [], entity: [], category: [], brand: [] })
const metadataLoading = ref(false)
const metadataError = ref('')
const draft = ref<Filters>(emptyFilters())
const applied = ref<Filters>(emptyFilters())
const summary = ref<Summary | null>(null)
const monthlyTrend = ref<MonthlyPoint[]>([])
const pageTab = ref<'dashboard' | 'data'>('dashboard')
const compactTable = ref(false)
const narrowViewport = window.matchMedia('(max-width: 580px)')
const narrowTable = ref(narrowViewport.matches)
const updateTableViewport = (event: MediaQueryListEvent) => { narrowTable.value = event.matches }
const items = ref<Item[]>([])
const total = ref(0)
const view = ref<View>('sku')
const page = ref(1)
const pageSize = ref(20)
const sortBy = ref('return_quantity')
const sortDir = ref<SortDirection>('desc')
const summaryLoading = ref(false)
const trendLoading = ref(false)
const itemsLoading = ref(false)
const exporting = ref(false)
const dataError = ref('')
const supplierOptions = ref<string[]>([])
const suppliersLoading = ref(false)
const sourceVisible = ref(false)
const sourceLoading = ref(false)
const sourceError = ref('')
const sourceTitle = ref('')
const sourceItems = ref<Source[]>([])
const brandDrawerVisible = ref(false)
const brandLoading = ref(false)
const brandSaving = ref(false)
const brandRules = ref<BrandRule[]>([])
const brandVersion = ref<number | string | null>(null)
const brandPreview = ref<Record<string, unknown> | null>(null)
let summarySequence = 0
let trendSequence = 0
let itemsSequence = 0
let supplierSequence = 0
let supplierFailureNotified = false
let sourceSequence = 0
let filterOptionsSequence = 0
let filtersReady = false
let filterTimer: ReturnType<typeof setTimeout> | undefined

const hasRun = computed(() => metadata.value?.run_id !== null && metadata.value?.run_id !== undefined)
const activeRunId = computed(() => metadata.value?.run_id)
const filtersPending = computed(() => JSON.stringify(cloneFilters(draft.value)) !== JSON.stringify(applied.value))
const queryLoading = computed(() => filtersPending.value || summaryLoading.value || trendLoading.value || itemsLoading.value)
const availablePeriods = computed(() => [...(metadata.value?.periods || [])].sort())
const periodRange = computed(() => {
  const periods = availablePeriods.value
  if (!periods.length) return '暂无覆盖月份'
  return periods.length === 1 ? periods[0] : `${periods[0]} — ${periods.at(-1)}`
})
const importedAt = computed(() => metadata.value?.imported_at?.replace('T', ' ').slice(0, 16) || '暂无更新时间')
const filterLabels: Record<FilterKey, string> = { period: '月份', entity: '主体', category: '类目', brand: '品牌', supplier: '供应商' }
const activeFilters = computed(() => {
  const tags: { key: FilterKey | 'sku_keyword'; value: string; label: string }[] = []
  for (const key of Object.keys(filterLabels) as FilterKey[]) {
    if (key === 'period' && isPeriodPreset('all')) continue
    if (draft.value[key].length) tags.push({ key, value: draft.value[key].join('、'), label: filterLabels[key] })
  }
  if (draft.value.sku_keyword.trim()) tags.push({ key: 'sku_keyword', value: draft.value.sku_keyword.trim(), label: 'SKU' })
  return tags
})
const canManageBrands = computed(() => ['admin', '管理员', 'operator'].includes((localStorage.getItem('auth_role') || '').trim().toLowerCase()))
const scopeText = computed(() => {
  const f = applied.value
  const allPeriods = metadata.value?.periods || []
  const everyPeriodSelected = f.period.length === allPeriods.length && allPeriods.every(period => f.period.includes(period))
  const parts = [
    f.period.length && !everyPeriodSelected ? `月份 ${f.period.join('、')}` : '全部月份',
    f.entity.length ? `主体 ${f.entity.join('、')}` : '全部主体',
    f.category.length ? `类目 ${f.category.join('、')}` : '全部类目',
    f.brand.length ? `品牌 ${f.brand.join('、')}` : '全部品牌',
  ]
  if (f.supplier.length) parts.push(`供应商 ${f.supplier.join('、')}`)
  if (f.sku_keyword) parts.push(`SKU 包含“${f.sku_keyword}”`)
  return parts.join(' · ')
})
const coverageText = computed(() => {
  const periods = metadata.value?.periods || []
  return periods.length ? periods.join('、') : '暂无'
})
const qualityLabels: Record<string, string> = {
  scanned_rows: '扫描行', target_rows: '目标单据行', included_rows: '计入行',
  isolated_rows: '隔离行', invalid_rows: '异常隔离行', duplicate_rows: '重复排除行',
  excluded_duplicates: '重复排除行', missing_quantity_rows: '数量缺失行',
  invalid_quantity: '数量异常行', missing_technical_key: '缺技术单据键行',
  unknown_category_rows: '未分类行', unknown_category_files: '未分类来源文件',
  new_category_combinations: '新主体类目组合', unknown_brand_rows: '待识别品牌行',
  empty_sku_name_rows: 'SKU 名称为空行', empty_sku_name: 'SKU 名称为空行',
  empty_supplier_rows: '供应商为空行', empty_supplier: '供应商为空行',
  empty_sku_code: 'SKU 编码为空行', oversized_text: '文本超长行',
  negative_sales_rows: '负销售行', negative_sales: '负销售行',
  duplicate_category_mismatch: '重复行类目不一致',
  numeric_precision_risk: '编码数字精度风险', numeric_fractional_identifier: '非整数编码',
  excel_zero_format: '编码按 Excel 格式补零',
  file_count: '工作簿数', source_unit_count: '数据表数',
}
const qualityEntries = computed(() => Object.entries(metadata.value?.quality || {})
  .filter(([, value]) => ['number', 'string'].includes(typeof value) && value !== '')
  .map(([key, value]) => ({ key, label: qualityLabels[key] || key.replaceAll('_', ' '), value: String(value) })))

const monthlyPoints = computed<MonthlyPoint[]>(() => {
  const periods = (applied.value.period.length ? applied.value.period : metadata.value?.periods || []).slice().sort()
  const byPeriod = new Map(monthlyTrend.value.map(row => [row.period, row]))
  return periods.map(period => byPeriod.get(period) || {
    period, sales_quantity: null, return_in_quantity: null,
    after_sales_quantity: null, return_quantity: null, return_rate: null,
  })
})
const ratePoints = computed(() => monthlyPoints.value.filter(row => row.return_rate !== null))
const firstRatePointIndex = computed(() => monthlyPoints.value.findIndex(row => row.return_rate !== null))
const latestPoint = computed(() => ratePoints.value.at(-1))
const highestPoint = computed(() => ratePoints.value.length
  ? ratePoints.value.reduce((best, row) => Number(row.return_rate) > Number(best.return_rate) ? row : best)
  : null)
const rateTrendOption = computed(() => ({
  animationDuration: 450,
  grid: { top: 38, right: 24, bottom: 28, left: 12, containLabel: true },
  tooltip: {
    trigger: 'axis', backgroundColor: '#233b4d', borderWidth: 0, textStyle: { color: '#fff' },
    formatter: (params: any) => {
      const point = monthlyPoints.value[params?.[0]?.dataIndex]
      if (!point) return ''
      return `${point.period}<br/>退货率：${percent(point.return_rate)}<br/>销售数量：${quantity(point.sales_quantity)}<br/>退货数量：${quantity(point.return_quantity)}`
    },
  },
  xAxis: { type: 'category', boundaryGap: false, data: monthlyPoints.value.map(row => row.period), axisLine: { lineStyle: { color: '#dce5ee' } }, axisTick: { show: false }, axisLabel: { color: '#718197', margin: 16, formatter: monthLabel } },
  yAxis: { type: 'value', min: 0, axisLabel: { color: '#718197', formatter: (value: number) => `${value}%` }, splitLine: { lineStyle: { color: '#edf1f6', type: 'dashed' } } },
  series: [{ name: '退货率', type: 'line', smooth: 0.22, connectNulls: false, symbol: 'circle', symbolSize: 9,
    data: monthlyPoints.value.map((row, index) => {
      if (row.return_rate === null) return null
      const value = Number((Number(row.return_rate) * 100).toFixed(4))
      return index === firstRatePointIndex.value
        ? { value, label: { position: 'right' } }
        : value
    }),
    lineStyle: { color: '#4276ed', width: 3 }, itemStyle: { color: '#4276ed', borderColor: '#fff', borderWidth: 3 },
    areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(66,118,237,.22)' }, { offset: 1, color: 'rgba(66,118,237,.015)' }] } },
    label: { show: monthlyPoints.value.length <= 12, position: 'top', color: '#5271a4', fontSize: 11, formatter: (params: any) => params.value === null ? '' : `${Number(params.value).toFixed(2)}%` },
    labelLayout: { hideOverlap: true },
  }],
}))
const returnMixOption = computed(() => ({
  animationDuration: 450,
  color: ['#7199f5', '#a8d8cd'],
  grid: { top: 38, right: 10, bottom: 28, left: 8, containLabel: true },
  legend: { show: false },
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (value: number) => quantity(value) },
  xAxis: { type: 'category', data: monthlyPoints.value.map(row => row.period), axisLine: { lineStyle: { color: '#dce5ee' } }, axisTick: { show: false }, axisLabel: { color: '#718197', formatter: monthLabel } },
  yAxis: { type: 'value', axisLabel: { color: '#718197', formatter: (value: number) => Math.abs(value) >= 10000 ? `${Number((value / 10000).toFixed(1))}万` : quantity(value) }, splitLine: { lineStyle: { color: '#edf1f6', type: 'dashed' } } },
  series: [
    { name: '退货入库', type: 'bar', stack: 'returns', barMaxWidth: 28, data: monthlyPoints.value.map(row => row.return_in_quantity === null ? null : Number(row.return_in_quantity)) },
    { name: '售后退货', type: 'bar', stack: 'returns', barMaxWidth: 28, itemStyle: { borderRadius: [4, 4, 0, 0] }, data: monthlyPoints.value.map(row => row.after_sales_quantity === null ? null : Number(row.after_sales_quantity)) },
  ],
}))

function quantity(value: Decimal): string {
  if (value === null || value === undefined || value === '') return '-'
  const text = String(value).trim()
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(text)
  if (!match) return text
  const decimal = (match[3] || '').replace(/0+$/, '')
  return `${match[1]}${match[2]!.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}${decimal ? `.${decimal}` : ''}`
}
function monthLabel(period: string): string {
  const multipleYears = new Set(monthlyPoints.value.map(row => row.period.slice(0, 4))).size > 1
  return multipleYears ? period : `${Number(period.slice(5))}月`
}
function isPeriodPreset(preset: 'all' | 'latest' | 'recent'): boolean {
  const selected = draft.value.period
  const expected = preset === 'all' ? availablePeriods.value : availablePeriods.value.slice(preset === 'latest' ? -1 : -3)
  return (preset === 'all' && !selected.length) || (expected.length > 0 && selected.length === expected.length && expected.every(period => selected.includes(period)))
}
function selectPeriodPreset(preset: 'all' | 'latest' | 'recent'): void {
  draft.value.period = preset === 'all' ? [...availablePeriods.value] : availablePeriods.value.slice(preset === 'latest' ? -1 : -3)
  applyFilters()
}
function removeFilter(key: FilterKey | 'sku_keyword'): void {
  if (key === 'sku_keyword') draft.value.sku_keyword = ''
  else draft.value[key] = []
  applyFilters()
}
function percent(value: string | null): string {
  if (value === null || value === undefined || value === '') return '-'
  const number = Number(value)
  return Number.isFinite(number) ? `${(number * 100).toFixed(2)}%` : '-'
}
function queryFor(filters: Filters = applied.value): URLSearchParams {
  const query = new URLSearchParams()
  if (activeRunId.value !== null && activeRunId.value !== undefined) query.set('run_id', String(activeRunId.value))
  for (const key of ['period', 'entity', 'category', 'brand', 'supplier'] as FilterKey[]) {
    for (const value of filters[key]) query.append(key, value)
  }
  if (filters.sku_keyword.trim()) query.set('sku_keyword', filters.sku_keyword.trim())
  return query
}
async function apiGet<T>(path: string, params?: URLSearchParams): Promise<T> {
  const url = `${API}${path}${params ? `?${params.toString()}` : ''}`
  const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store' })
  if (!response.ok) {
    let message = `请求失败（HTTP ${response.status}）`
    try {
      const body = await response.json()
      const detail = body.detail || body.message || body.error
      if (typeof detail === 'string') message = detail
      else if (Array.isArray(detail)) message = detail.map((item) => item.msg || String(item)).join('；')
    } catch { /* 保留 HTTP 状态提示 */ }
    const error = new Error(message) as ApiError
    error.status = response.status
    throw error
  }
  return response.json() as Promise<T>
}
async function loadMetadata(preserveFilters = false): Promise<void> {
  metadataLoading.value = true
  metadataError.value = ''
  try {
    const result = await apiGet<Metadata>('/metadata')
    metadata.value = result
    if (!preserveFilters) {
      filtersReady = false
      draft.value = { ...emptyFilters(), period: [...(result.periods || [])] }
      applied.value = cloneFilters(draft.value)
    }
    filtersReady = true
    if (hasRun.value) {
      await Promise.all([loadData(), loadFilterOptions(applied.value), searchSuppliers('')])
    } else {
      filterOptions.value = { period: [], entity: [], category: [], brand: [] }
      summary.value = null
      monthlyTrend.value = []
      items.value = []
      total.value = 0
    }
  } catch (error) {
    metadataError.value = (error as Error).message
  } finally {
    metadataLoading.value = false
  }
}
async function loadFilterOptions(filters: Filters = applied.value): Promise<void> {
  if (!hasRun.value) return
  const sequence = ++filterOptionsSequence
  const query = queryFor(filters)
  try {
    const result = await apiGet<FilterOptions & { run_id: number | string }>('/options', query)
    if (sequence !== filterOptionsSequence || String(result.run_id) !== String(activeRunId.value)) return
    filterOptions.value = {
      period: result.period || [],
      entity: result.entity || [],
      category: result.category || [],
      brand: result.brand || [],
    }
  } catch (error) {
    if (sequence === filterOptionsSequence) ElMessage.warning(`筛选选项加载失败：${(error as Error).message}`)
  }
}
async function loadData(): Promise<void> {
  if (!hasRun.value) return
  const currentSummary = ++summarySequence
  const currentTrend = ++trendSequence
  const currentItems = ++itemsSequence
  dataError.value = ''
  summaryLoading.value = true
  trendLoading.value = true
  itemsLoading.value = true
  const summaryQuery = queryFor()
  const trendQuery = queryFor()
  const itemQuery = queryFor()
  itemQuery.set('view', view.value)
  itemQuery.set('page', String(page.value))
  itemQuery.set('page_size', String(pageSize.value))
  itemQuery.set('sort_by', sortBy.value)
  itemQuery.set('sort_dir', sortDir.value)
  const [summaryResult, trendResult, itemResult] = await Promise.allSettled([
    apiGet<Summary>('/summary', summaryQuery), apiGet<MonthlyTrendResponse>('/monthly-trend', trendQuery), apiGet<ItemsResponse>('/items', itemQuery),
  ])
  if (currentSummary === summarySequence) {
    summary.value = summaryResult.status === 'fulfilled' ? summaryResult.value : null
    summaryLoading.value = false
  }
  if (currentTrend === trendSequence) {
    monthlyTrend.value = trendResult.status === 'fulfilled' ? trendResult.value.items || [] : []
    trendLoading.value = false
  }
  if (currentItems === itemsSequence) {
    if (itemResult.status === 'fulfilled') {
      items.value = itemResult.value.items || []
      total.value = itemResult.value.total || 0
    } else {
      items.value = []
      total.value = 0
    }
    itemsLoading.value = false
  }
  const failure = summaryResult.status === 'rejected' && currentSummary === summarySequence ? summaryResult.reason
    : trendResult.status === 'rejected' && currentTrend === trendSequence ? trendResult.reason
    : itemResult.status === 'rejected' && currentItems === itemsSequence ? itemResult.reason : null
  if (failure) await handleDataError(failure)
}
async function loadItems(): Promise<void> {
  if (!hasRun.value) return
  const sequence = ++itemsSequence
  itemsLoading.value = true
  dataError.value = ''
  const query = queryFor()
  query.set('view', view.value)
  query.set('page', String(page.value))
  query.set('page_size', String(pageSize.value))
  query.set('sort_by', sortBy.value)
  query.set('sort_dir', sortDir.value)
  try {
    const result = await apiGet<ItemsResponse>('/items', query)
    if (sequence !== itemsSequence) return
    items.value = result.items || []
    total.value = result.total || 0
  } catch (error) {
    if (sequence !== itemsSequence) return
    items.value = []
    total.value = 0
    await handleDataError(error)
  } finally {
    if (sequence === itemsSequence) itemsLoading.value = false
  }
}
async function handleDataError(error: unknown): Promise<void> {
  if ((error as ApiError).status === 409) {
    ElMessage.warning('数据版本已更新，正在刷新查询')
    await loadMetadata(true)
  } else {
    dataError.value = (error as Error).message || '数据加载失败'
  }
}
function applyFilters(): void {
  if (filterTimer) clearTimeout(filterTimer)
  filterTimer = undefined
  const next = cloneFilters(draft.value)
  void loadFilterOptions(next)
  void searchSuppliers('')
  if (JSON.stringify(next) === JSON.stringify(applied.value)) return
  applied.value = next
  page.value = 1
  void loadData()
}
function scheduleFilters(): void {
  if (!filtersReady || !hasRun.value) return
  if (filterTimer) clearTimeout(filterTimer)
  filterTimer = setTimeout(applyFilters, 180)
}
watch(draft, scheduleFilters, { deep: true, flush: 'sync' })
function resetFilters(): void {
  draft.value = { ...emptyFilters(), period: [...(metadata.value?.periods || [])] }
  applyFilters()
}
function inspectMonth(period: string): void {
  draft.value.period = [period]
  pageTab.value = 'data'
  applyFilters()
}
function switchView(next: View): void {
  if (view.value === next) return
  view.value = next
  page.value = 1
  sortBy.value = 'return_quantity'
  sortDir.value = 'desc'
  void loadItems()
}
function sortTable(event: { prop?: string | null; order?: 'ascending' | 'descending' | null }): void {
  sortBy.value = event.prop && event.order ? event.prop : 'return_quantity'
  sortDir.value = event.order === 'ascending' ? 'asc' : 'desc'
  page.value = 1
  void loadItems()
}
function changePage(next: number): void { page.value = next; void loadItems() }
function changePageSize(next: number): void { pageSize.value = next; page.value = 1; void loadItems() }
async function searchSuppliers(keyword: string): Promise<void> {
  if (!hasRun.value) return
  const sequence = ++supplierSequence
  suppliersLoading.value = true
  const query = queryFor(draft.value)
  query.delete('supplier')
  query.set('keyword', keyword)
  query.set('limit', '50')
  try {
    const result = await apiGet<{ items: string[] }>('/options/suppliers', query)
    if (sequence !== supplierSequence) return
    supplierFailureNotified = false
    supplierOptions.value = Array.from(new Set([...(result.items || []), ...draft.value.supplier]))
  } catch {
    if (sequence !== supplierSequence) return
    supplierOptions.value = [...draft.value.supplier]
    if (!supplierFailureNotified) {
      ElMessage.warning('供应商选项加载失败，请稍后重试')
      supplierFailureNotified = true
    }
  } finally {
    if (sequence === supplierSequence) suppliersLoading.value = false
  }
}
async function openSources(row: Record<string, unknown>): Promise<void> {
  if (!hasRun.value) return
  const sequence = ++sourceSequence
  sourceVisible.value = true
  sourceLoading.value = true
  sourceError.value = ''
  sourceItems.value = []
  sourceTitle.value = `${row.sku_code || ''} · ${row.sku_name || ''}`
  const query = queryFor()
  query.set('view', view.value)
  query.set('sku_code', String(row.sku_code ?? ''))
  query.set('sku_name', String(row.sku_name ?? ''))
  if (view.value === 'detail') {
    query.set('detail_period', String(row.period ?? ''))
    query.set('detail_entity', String(row.entity ?? ''))
    query.set('detail_category', String(row.category ?? ''))
    query.set('detail_supplier_name', String(row.supplier_name ?? ''))
  }
  try {
    const result = await apiGet<{ items: Source[] }>('/sources', query)
    if (sequence !== sourceSequence) return
    sourceItems.value = result.items || []
  } catch (error) {
    if (sequence !== sourceSequence) return
    sourceError.value = (error as Error).message
  } finally {
    if (sequence === sourceSequence) sourceLoading.value = false
  }
}
async function exportData(): Promise<void> {
  if (!hasRun.value || exporting.value) return
  applyFilters()
  exporting.value = true
  const query = queryFor()
  query.set('view', view.value)
  query.set('sort_by', sortBy.value)
  query.set('sort_dir', sortDir.value)
  try {
    const response = await fetch(`${API}/export?${query.toString()}`, { credentials: 'same-origin', cache: 'no-store' })
    if (!response.ok) {
      let message = `导出失败（HTTP ${response.status}）`
      try { const body = await response.json(); message = body.detail || body.message || message } catch { /* 使用默认提示 */ }
      const error = new Error(message) as ApiError
      error.status = response.status
      throw error
    }
    const blob = await response.blob()
    const downloadUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    const disposition = response.headers.get('content-disposition') || ''
    const encodedName = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1]
    link.download = encodedName ? decodeURIComponent(encodedName) : `SKU退货数据_${view.value}_${Date.now()}.xlsx`
    link.href = downloadUrl
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000)
  } catch (error) {
    if ((error as ApiError).status === 409) await handleDataError(error)
    else ElMessage.error((error as Error).message)
  } finally {
    exporting.value = false
  }
}
async function openBrandRules(): Promise<void> {
  brandDrawerVisible.value = true
  brandLoading.value = true
  brandPreview.value = null
  brandVersion.value = null
  brandRules.value = []
  try {
    const result = await apiGet<{ version: number | string; items: BrandRule[] }>('/brand-rules')
    brandVersion.value = result.version
    brandRules.value = (result.items || []).map((rule) => ({ ...rule }))
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    brandLoading.value = false
  }
}
function editableRules(): BrandRule[] {
  return brandRules.value.map(({ match_type, pattern, canonical_brand, priority, enabled }) => ({
    match_type, pattern: pattern.trim(), canonical_brand: canonical_brand.trim(), priority: Number(priority) || 0, enabled,
  }))
}
async function brandRequest(path: string, body: Record<string, unknown>, method: 'POST' | 'PUT'): Promise<Record<string, unknown>> {
  const response = await fetch(`${API}${path}`, {
    method, credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  const result = await response.json().catch(() => ({})) as Record<string, unknown>
  if (!response.ok) throw new Error(String(result.detail || result.message || `请求失败（HTTP ${response.status}）`))
  return result
}
async function previewBrandRules(): Promise<void> {
  brandLoading.value = true
  try { brandPreview.value = await brandRequest('/brand-rules/preview', { rules: editableRules() }, 'POST') }
  catch (error) { ElMessage.error((error as Error).message) }
  finally { brandLoading.value = false }
}
async function saveBrandRules(): Promise<void> {
  if (brandVersion.value === null) return
  brandSaving.value = true
  try {
    await brandRequest('/brand-rules', { rules: editableRules(), expected_version: brandVersion.value }, 'PUT')
    ElMessage.success('品牌规则已保存，数据版本正在更新')
    brandDrawerVisible.value = false
    await loadMetadata(true)
  } catch (error) { ElMessage.error((error as Error).message) }
  finally { brandSaving.value = false }
}

onMounted(() => {
  narrowViewport.addEventListener('change', updateTableViewport)
  void loadMetadata()
})
onBeforeUnmount(() => {
  if (filterTimer) clearTimeout(filterTimer)
  narrowViewport.removeEventListener('change', updateTableViewport)
})
</script>

<template>
  <section class="sku-return-page">
    <header class="page-header">
      <div class="page-identity">
        <div class="page-symbol"><el-icon><DataAnalysis /></el-icon></div>
        <div>
          <p class="eyebrow">运营部 <el-icon><ArrowRight /></el-icon> 退货分析</p>
          <div class="page-title"><h1>SKU 退货数据</h1><span class="title-badge">结算分析</span></div>
          <p class="subtitle">按结算月份分析退货表现，快速查看 SKU 与数据来源</p>
        </div>
      </div>
      <div class="header-tools">
        <div class="header-actions">
          <el-button v-if="canManageBrands" :icon="Setting" @click="openBrandRules">品牌规则</el-button>
          <el-tooltip content="重新获取最新数据版本" placement="bottom"><el-button :icon="Refresh" :loading="metadataLoading" @click="loadMetadata(true)">刷新</el-button></el-tooltip>
          <el-button type="primary" :icon="Download" :disabled="!hasRun || queryLoading || metadataLoading" :loading="exporting" @click="exportData">导出数据</el-button>
        </div>
        <span v-if="hasRun" class="update-time"><el-icon><Clock /></el-icon> 数据更新于 {{ importedAt }}</span>
      </div>
    </header>

    <el-card v-if="metadataLoading && !hasRun" v-loading="metadataLoading" shadow="never" class="empty-card" aria-label="正在加载 SKU 退货数据" />
    <el-alert v-if="metadataError" type="error" :closable="false" :title="metadataError" class="status-alert" />
    <el-card v-if="!metadataLoading && !metadataError && !hasRun" shadow="never" class="empty-card">
      <el-empty description="尚无已发布的 SKU 退货数据，请先执行数据导入" />
    </el-card>

    <template v-if="hasRun">
      <el-card shadow="never" class="filter-card">
        <div class="filter-heading">
          <div class="section-title"><el-icon><Filter /></el-icon><h2>筛选条件</h2><span class="auto-query">选择后自动更新</span></div>
          <div class="filter-actions">
            <el-button text :icon="RefreshLeft" @click="resetFilters">重置</el-button>
          </div>
        </div>
        <div class="filter-grid">
          <label class="filter-field"><span>结算月份</span><el-select v-model="draft.period" aria-label="结算月份" multiple collapse-tags collapse-tags-tooltip clearable filterable placeholder="全部月份"><el-option v-for="item in filterOptions.period" :key="item" :label="item" :value="item" /></el-select></label>
          <label class="filter-field"><span>搜索 SKU</span><el-input v-model="draft.sku_keyword" aria-label="搜索 SKU" :prefix-icon="Search" :maxlength="191" clearable placeholder="输入 SKU 编码或商品名称" @keyup.enter="applyFilters" /></label>
          <label class="filter-field"><span>商品品牌</span><el-select v-model="draft.brand" aria-label="商品品牌" multiple collapse-tags collapse-tags-tooltip clearable filterable placeholder="全部品牌"><el-option v-for="item in filterOptions.brand" :key="item" :label="item" :value="item" /></el-select></label>
          <label class="filter-field"><span>经营主体</span><el-select v-model="draft.entity" aria-label="经营主体" multiple collapse-tags collapse-tags-tooltip clearable filterable placeholder="全部主体"><el-option v-for="item in filterOptions.entity" :key="item" :label="item" :value="item" /></el-select></label>
          <label class="filter-field"><span>商品类目</span><el-select v-model="draft.category" aria-label="商品类目" multiple collapse-tags collapse-tags-tooltip clearable filterable placeholder="全部类目"><el-option v-for="item in filterOptions.category" :key="item" :label="item" :value="item" /></el-select></label>
          <label class="filter-field"><span>供应商</span><el-select v-model="draft.supplier" aria-label="供应商" multiple filterable remote reserve-keyword collapse-tags collapse-tags-tooltip clearable :remote-method="searchSuppliers" :loading="suppliersLoading" placeholder="输入供应商名称搜索"><el-option v-for="item in supplierOptions" :key="item" :label="item" :value="item" /></el-select></label>
        </div>
        <div class="filter-footer">
          <div class="period-presets" aria-label="月份快捷筛选">
            <span>快捷月份</span>
            <button type="button" :class="{ active: isPeriodPreset('all') }" :aria-pressed="isPeriodPreset('all')" @click="selectPeriodPreset('all')">全部</button>
            <button type="button" :class="{ active: isPeriodPreset('latest') }" :aria-pressed="isPeriodPreset('latest')" @click="selectPeriodPreset('latest')">最近一期</button>
            <button type="button" :class="{ active: isPeriodPreset('recent') }" :aria-pressed="isPeriodPreset('recent')" @click="selectPeriodPreset('recent')">最近三期</button>
          </div>
          <span class="query-status" role="status"><span class="status-dot" :class="{ pending: queryLoading, error: dataError }" />{{ queryLoading ? '数据更新中' : dataError ? '更新失败，请重试' : '已同步当前筛选' }}</span>
        </div>
        <div v-if="activeFilters.length" class="active-filters" aria-label="已选筛选条件">
          <span>已选条件</span><el-tag v-for="tag in activeFilters" :key="tag.key" closable effect="plain" :title="`${tag.label}：${tag.value}`" @close="removeFilter(tag.key)">{{ tag.label }}：{{ tag.value }}</el-tag>
          <el-button link @click="resetFilters">清除全部</el-button>
        </div>
      </el-card>

      <el-alert v-if="dataError" type="error" show-icon :closable="false" :title="dataError" class="status-alert"><el-button link type="danger" @click="loadData">重新加载</el-button></el-alert>
      <div class="overview-heading"><h2>核心指标 <span>当前筛选范围</span></h2><el-tooltip :content="`数据覆盖月份：${coverageText}`" placement="top"><span class="coverage-label"><el-icon><Calendar /></el-icon>数据覆盖 {{ periodRange }}</span></el-tooltip></div>
      <div class="kpi-grid" v-loading="summaryLoading" :aria-busy="summaryLoading">
        <article class="kpi sales-kpi"><div class="kpi-label"><span>销售数量</span><el-icon class="kpi-icon"><ShoppingCart /></el-icon></div><div class="kpi-value"><strong>{{ quantity(summary?.sales_quantity ?? null) }}</strong></div><small>结算销售单数量，含负数冲减</small></article>
        <article class="kpi returns-kpi"><div class="kpi-label"><span>退货数量</span><el-icon class="kpi-icon"><RefreshLeft /></el-icon></div><div class="kpi-value"><strong>{{ quantity(summary?.return_quantity ?? null) }}</strong></div><small>退货入库 {{ quantity(summary?.return_in_quantity ?? null) }} <span class="text-divider">/</span> 售后 {{ quantity(summary?.after_sales_quantity ?? null) }}</small></article>
        <article class="kpi rate-kpi"><div class="kpi-label"><span>总体退货率</span><el-icon class="kpi-icon"><TrendCharts /></el-icon></div><div class="kpi-value"><strong>{{ percent(summary?.return_rate ?? null) }}</strong></div><small>退货数量 ÷ 销售数量</small></article>
        <article class="kpi sku-kpi"><div class="kpi-label"><span>SKU 组合数</span><el-icon class="kpi-icon"><Box /></el-icon></div><div class="kpi-value"><strong>{{ quantity(summary?.sku_count ?? null) }}</strong></div><small>按 SKU 编码 + 商品名称区分</small></article>
        <article class="kpi warning-kpi"><div class="kpi-label"><span>无有效销售基数</span><el-tooltip content="销售数量小于等于 0 的 SKU 组合，其退货率不参与计算" placement="top"><el-icon class="kpi-icon" tabindex="0" aria-label="无有效销售基数说明"><Warning /></el-icon></el-tooltip></div><div class="kpi-value"><strong>{{ quantity(summary?.no_sales_sku_count ?? null) }}</strong><span class="kpi-unit">组</span></div><small>销售数量 ≤ 0，退货率显示「-」</small></article>
      </div>

      <div class="analysis-nav">
        <el-tabs v-model="pageTab" class="page-tabs">
          <el-tab-pane name="dashboard"><template #label><span class="tab-label"><el-icon><TrendCharts /></el-icon>趋势概览</span></template></el-tab-pane>
          <el-tab-pane name="data"><template #label><span class="tab-label"><el-icon><Document /></el-icon>数据明细<span class="tab-count">{{ quantity(total) }}</span></span></template></el-tab-pane>
        </el-tabs>
        <span class="calculation-note"><el-icon><InfoFilled /></el-icon> 按结算归属月统计</span>
      </div>
      <div v-if="pageTab === 'dashboard'" class="dashboard" v-loading="trendLoading">
        <div class="analytics-grid">
          <el-card shadow="never" class="chart-card trend-panel">
            <div class="chart-heading"><div><h3><span class="heading-marker" />月度退货率趋势</h3><p>观察各结算月的退货变化</p></div><span class="chart-key"><i class="rate-dot" />退货率</span></div>
            <div class="trend-highlights"><span>最近可计算月 <strong>{{ latestPoint ? percent(latestPoint.return_rate) : '-' }}</strong><small>{{ latestPoint?.period || '暂无' }}</small></span><span>最高月份 <strong>{{ highestPoint ? percent(highestPoint.return_rate) : '-' }}</strong><small>{{ highestPoint?.period || '暂无' }}</small></span><span class="computable-months">可计算 <b>{{ ratePoints.length }}</b> / {{ monthlyPoints.length }} 月</span></div>
            <VChart v-if="ratePoints.length" :option="rateTrendOption" autoresize class="rate-chart" aria-label="月度退货率折线图" />
            <el-empty v-else-if="!trendLoading" description="当前条件下没有可计算的月度退货率" :image-size="90" />
            <p class="chart-note"><el-icon><InfoFilled /></el-icon> 悬停查看数量；无有效销售基数或无数据的月份留空。</p>
          </el-card>
          <el-card shadow="never" class="chart-card mix-panel">
            <div class="chart-heading"><div><h3><span class="heading-marker mint" />退货数量构成</h3><p>按月查看两类退货数量分布</p></div></div>
            <div class="mix-legend"><span><i class="legend-dot return-in" />退货入库</span><span><i class="legend-dot after-sales" />售后退货</span><small>单位：数量</small></div>
            <VChart v-if="monthlyTrend.length" :option="returnMixOption" autoresize class="mix-chart" aria-label="月度退货构成柱状图" />
            <el-empty v-else-if="!trendLoading" description="当前条件下暂无退货数据" :image-size="90" />
            <p class="chart-note">退货总量 = 退货入库 + 售后退货</p>
          </el-card>
        </div>
        <el-card shadow="never" class="chart-card month-panel">
          <div class="chart-heading"><div><h3><el-icon><Calendar /></el-icon>月度数据一览</h3><p>逐月核对销售与退货，点击明细进一步查看 SKU</p></div><span class="subtle-badge">{{ monthlyPoints.length }} 个结算月</span></div>
          <div class="month-table-wrap"><table class="month-table"><caption class="sr-only">当前筛选范围的月度销售与退货数据</caption><thead><tr><th scope="col">结算月份</th><th scope="col">销售数量</th><th scope="col">退货入库</th><th scope="col">售后退货</th><th scope="col">退货合计</th><th scope="col">退货率</th><th scope="col">操作</th></tr></thead><tbody>
            <tr v-for="row in monthlyPoints" :key="row.period"><td><span class="month-cell"><el-icon><Calendar /></el-icon>{{ row.period }}</span></td><td>{{ quantity(row.sales_quantity) }}</td><td>{{ quantity(row.return_in_quantity) }}</td><td>{{ quantity(row.after_sales_quantity) }}</td><td><strong>{{ quantity(row.return_quantity) }}</strong></td><td><span class="rate-pill" :class="{ muted: row.return_rate === null }">{{ percent(row.return_rate) }}</span></td><td><el-button link type="primary" :aria-label="`查看 ${row.period} 的 SKU 明细`" @click="inspectMonth(row.period)">查看明细<el-icon><ArrowRight /></el-icon></el-button></td></tr>
          </tbody></table></div>
          <div class="month-table-footer"><el-icon><InfoFilled /></el-icon> 总体退货率按数量合计计算，不等于各月退货率的平均值。</div>
        </el-card>
      </div>

      <el-card v-else shadow="never" class="table-card">
        <div class="table-header"><div><h2>退货数据明细 <span class="subtle-badge">{{ quantity(total) }} 条</span></h2><p>{{ scopeText }}</p></div><div class="table-tools"><div class="view-switch" aria-label="明细维度"><button type="button" :class="{ active: view === 'sku' }" :aria-pressed="view === 'sku'" @click="switchView('sku')"><el-icon><Box /></el-icon>SKU 聚合</button><button type="button" :class="{ active: view === 'detail' }" :aria-pressed="view === 'detail'" @click="switchView('detail')"><el-icon><Grid /></el-icon>维度明细</button></div><el-tooltip :content="compactTable ? '切换为舒适行距' : '切换为紧凑行距'" placement="top"><el-button class="density-toggle" :icon="Setting" :aria-pressed="compactTable" aria-label="切换表格行距" @click="compactTable = !compactTable" /></el-tooltip></div></div>
        <p class="table-hint"><el-icon><InfoFilled /></el-icon> 点击列标题排序 · 无有效销售基数的退货率始终排在末尾 · 导出包含全部匹配结果</p>
        <el-table :key="view" :data="items" v-loading="itemsLoading" :size="compactTable ? 'small' : 'default'" :default-sort="{ prop: sortBy, order: sortDir === 'asc' ? 'ascending' : 'descending' }" :max-height="620" class="result-table" @sort-change="sortTable">
          <el-table-column v-if="view === 'detail'" prop="period" label="结算月" width="108" sortable="custom" :sort-orders="['ascending', 'descending']" />
          <el-table-column v-if="view === 'detail'" prop="entity" label="主体" width="95" />
          <el-table-column v-if="view === 'detail'" prop="category" label="类目" width="105" />
          <el-table-column v-if="view === 'detail'" prop="supplier_name" label="供应商" min-width="155" show-overflow-tooltip />
          <el-table-column prop="sku_code" label="SKU 编码" min-width="150" show-overflow-tooltip sortable="custom" :sort-orders="['ascending', 'descending']"><template #default="{ row }"><span class="sku-code">{{ row.sku_code }}</span></template></el-table-column>
          <el-table-column prop="sku_name" label="SKU 名称" min-width="245" show-overflow-tooltip sortable="custom" :sort-orders="['ascending', 'descending']" />
          <el-table-column prop="brand" label="品牌" min-width="115" show-overflow-tooltip><template #default="{ row }"><span class="brand-label" :class="{ unknown: row.brand === '待识别' }">{{ row.brand }}</span></template></el-table-column>
          <el-table-column prop="sales_quantity" label="销售数量" min-width="112" align="right" sortable="custom" :sort-orders="['ascending', 'descending']"><template #default="{ row }">{{ quantity(row.sales_quantity) }}</template></el-table-column>
          <el-table-column prop="return_in_quantity" label="退货入库" min-width="112" align="right" sortable="custom" :sort-orders="['ascending', 'descending']"><template #default="{ row }">{{ quantity(row.return_in_quantity) }}</template></el-table-column>
          <el-table-column prop="after_sales_quantity" label="售后退货" min-width="112" align="right" sortable="custom" :sort-orders="['ascending', 'descending']"><template #default="{ row }">{{ quantity(row.after_sales_quantity) }}</template></el-table-column>
          <el-table-column prop="return_quantity" label="退货合计" min-width="112" align="right" sortable="custom" :sort-orders="['ascending', 'descending']"><template #default="{ row }"><strong>{{ quantity(row.return_quantity) }}</strong></template></el-table-column>
          <el-table-column prop="return_rate" label="退货率" width="108" align="right" sortable="custom" :sort-orders="['ascending', 'descending']" :fixed="narrowTable ? false : 'right'"><template #default="{ row }"><span class="rate-pill" :class="{ muted: row.return_rate === null }">{{ percent(row.return_rate) }}</span></template></el-table-column>
          <el-table-column v-if="view === 'sku'" prop="entity_count" label="主体数" width="82" align="right" />
          <el-table-column v-if="view === 'sku'" prop="supplier_count" label="供应商数" width="94" align="right" />
          <el-table-column label="来源" width="86" fixed="right"><template #default="{ row }"><el-button link type="primary" :icon="Document" @click="openSources(row)">查看</el-button></template></el-table-column>
          <template #empty><el-empty :image-size="90" :description="dataError ? '数据暂时未能加载' : '没有找到符合条件的 SKU'"><el-button v-if="dataError" @click="loadData">重新加载</el-button><el-button v-else @click="resetFilters">重置筛选</el-button></el-empty></template>
        </el-table>
        <div class="table-footer"><span>共 <strong>{{ quantity(total) }}</strong> 条匹配结果</span><el-pagination :current-page="page" :page-size="pageSize" :page-sizes="[20, 50, 100, 200]" :total="total" :pager-count="5" background layout="sizes, prev, pager, next, jumper" class="pagination" @current-change="changePage" @size-change="changePageSize" /></div>
      </el-card>

      <el-card shadow="never" class="quality-card">
        <el-collapse><el-collapse-item name="quality"><template #title><div class="quality-title"><el-icon><CircleCheck /></el-icon><strong>数据来源与统计口径</strong><span>结算单数据 · 可追溯来源</span></div></template>
          <p>数据来自结算单 Excel。主目录按文件夹确定结算月与主体、按文件名识别类目；示例户外按月工作表确定结算月。两类退货按数量绝对值计入，销售单保留带符号数量；跨月重复归首次出现月份。</p>
          <p>覆盖月份：{{ coverageText }}。未分类与待识别品牌仍计入统计，可通过筛选核查。销售数量小于等于 0 时退货率显示“-”。</p>
          <p class="manifest">数据版本：{{ activeRunId }} <span class="text-divider">·</span> 品牌规则版本：{{ metadata?.rule_version ?? '-' }} <span class="text-divider">·</span> 更新时间：{{ importedAt }}</p>
          <div v-if="qualityEntries.length" class="quality-list"><span v-for="item in qualityEntries" :key="item.key"><b>{{ item.label }}</b> {{ quantity(item.value) }}</span></div>
        </el-collapse-item></el-collapse>
      </el-card>
    </template>

    <el-dialog v-model="sourceVisible" :title="`来源记录 · ${sourceTitle}`" width="min(1000px, 92vw)">
      <el-alert v-if="sourceError" type="error" :closable="false" :title="sourceError" />
      <el-table :data="sourceItems" v-loading="sourceLoading" stripe max-height="520"><el-table-column prop="relative_path" label="相对路径" min-width="310" show-overflow-tooltip /><el-table-column prop="sheet_name" label="工作表" width="110" /><el-table-column prop="row_number" label="行号" width="75" /><el-table-column prop="document_type" label="单据类型" min-width="155" /><el-table-column prop="raw_quantity" label="原始数量" width="105" align="right"><template #default="{ row }">{{ quantity(row.raw_quantity) }}</template></el-table-column><el-table-column label="状态" width="78"><template #default="{ row }"><el-tag :type="row.included ? 'success' : 'info'" size="small">{{ row.included ? '计入' : '排除' }}</el-tag></template></el-table-column></el-table>
      <p class="dialog-note">最多显示前 100 条来源记录，可根据文件路径、工作表和行号核对原始结算单。</p>
    </el-dialog>

    <el-drawer v-model="brandDrawerVisible" title="品牌识别规则" size="min(940px, 95vw)">
      <p class="drawer-note">先按 SKU 名称的完整名称或前缀识别品牌；示例户外主体的“测试旅行”单独归为“测试旅行企业购”。保存规则会重算数据版本；未命中的 SKU 保持“待识别”。</p>
      <div class="brand-actions"><el-button @click="brandRules.push({ match_type: 'prefix', pattern: '', canonical_brand: '', priority: 0, enabled: true })">新增规则</el-button><el-button :loading="brandLoading" @click="previewBrandRules">预览影响</el-button><el-button type="primary" :loading="brandSaving" @click="saveBrandRules">保存规则</el-button></div>
      <el-table :data="brandRules" v-loading="brandLoading" max-height="480" border><el-table-column label="匹配方式" width="130"><template #default="{ row }"><el-select v-model="row.match_type"><el-option label="名称完整匹配" value="exact" /><el-option label="名称前缀" value="prefix" /></el-select></template></el-table-column><el-table-column label="匹配文本" min-width="170"><template #default="{ row }"><el-input v-model="row.pattern" /></template></el-table-column><el-table-column label="标准品牌" min-width="150"><template #default="{ row }"><el-input v-model="row.canonical_brand" /></template></el-table-column><el-table-column label="优先级" width="100"><template #default="{ row }"><el-input v-model.number="row.priority" type="number" /></template></el-table-column><el-table-column label="启用" width="90"><template #default="{ row }"><input v-model="row.enabled" type="checkbox" aria-label="启用规则" /></template></el-table-column><el-table-column label="操作" width="76"><template #default="{ $index }"><el-button link type="danger" @click="brandRules.splice($index, 1)">删除</el-button></template></el-table-column></el-table>
      <div v-if="brandPreview" class="preview"><strong>规则预览</strong><pre>{{ JSON.stringify(brandPreview, null, 2) }}</pre></div>
    </el-drawer>
  </section>
</template>

<style scoped src="./sku-return-data.css"></style>
