<template>
  <section class="monitor-metric-page">
    <header class="metric-page-header">
      <div>
        <el-button link type="primary" class="back-button" @click="emit('back')">‹ 返回库存看板</el-button>
        <h1>{{ metricLabel }}</h1>
        <p>{{ metricDescription }}</p>
      </div>
      <div class="metric-page-total">
        <span>当前结果</span>
        <strong>{{ formatNumber(total) }}</strong>
        <small>{{ needsWarehouse ? 'SKU-仓记录' : 'SKU' }}</small>
      </div>
    </header>

    <form class="metric-filter-panel" @submit.prevent="search">
      <label><span>店铺</span><el-select v-model="filters.shop_name" filterable clearable multiple collapse-tags collapse-tags-tooltip placeholder="全部店铺"><el-option v-for="shop in filterOptions.shops" :key="shop" :label="shop" :value="shop" /></el-select></label>
      <label><span>数据日期</span><el-select v-model="filters.snapshot_date" filterable clearable multiple collapse-tags collapse-tags-tooltip placeholder="默认最新数据"><el-option v-for="date in filterOptions.snapshot_dates" :key="date" :label="date" :value="date" /></el-select></label>
      <label><span>品牌</span><el-select v-model="filters.brand" filterable clearable multiple collapse-tags collapse-tags-tooltip placeholder="全部品牌"><el-option v-for="brand in filterOptions.brands" :key="brand" :label="brand" :value="brand" /></el-select></label>
      <label><span>一级类目</span><el-select v-model="filters.category_l1" filterable clearable multiple collapse-tags collapse-tags-tooltip placeholder="全部类目"><el-option v-for="category in filterOptions.categories" :key="category" :label="category" :value="category" /></el-select></label>
      <label><span>上下柜</span><el-select v-model="filters.product_status" aria-label="上下柜筛选" clearable multiple collapse-tags collapse-tags-tooltip placeholder="全部状态"><el-option label="上柜" value="上柜" /><el-option label="下柜" value="下柜" /></el-select></label>
      <label class="keyword-field"><span>商品 / SKU</span><el-input v-model="filters.keyword" clearable placeholder="输入商品名称或 SKU" /></label>
      <div class="metric-filter-actions"><el-button @click="reset">重置</el-button></div>
    </form>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="metric-page-alert" />

    <section class="metric-detail-panel">
      <div class="metric-detail-toolbar">
        <div>
          <h2>{{ metricLabel }} SKU清单</h2>
          <span v-if="metric === 'shortage'">缺货口径：近30日出库 ÷ 30 × {{ formatDays(turnoverDays) }}天 − 现货 &gt; 0</span>
          <span v-else-if="metric === 'stockout'">断货口径：对应仓库当前现货库存 = 0</span>
          <span v-else>按导入文件中的上下柜状态统计</span>
        </div>
        <el-button :loading="loading" @click="load">刷新</el-button>
      </div>

      <el-table v-loading="loading" :data="items" stripe border class="metric-detail-table" height="100%" :row-key="rowKey">
        <el-table-column prop="sku_code" label="SKU" min-width="150" fixed="left" show-overflow-tooltip />
        <el-table-column prop="product_name" label="商品名称" min-width="230" show-overflow-tooltip />
        <el-table-column prop="brand" label="品牌" min-width="130" show-overflow-tooltip />
        <el-table-column prop="category_l1" label="一级类目" min-width="110" show-overflow-tooltip />
        <el-table-column prop="shop_name" label="店铺" min-width="160" show-overflow-tooltip />
        <el-table-column prop="snapshot_date" label="数据日期" width="110" />
        <el-table-column v-if="needsWarehouse" prop="warehouse" label="仓库" width="105" />
        <el-table-column prop="product_status" label="上下柜状态" width="110" align="center" />
        <el-table-column v-if="needsWarehouse" prop="stock_qty" label="现货" width="95" align="right"><template #default="{ row }">{{ formatDecimal(row.stock_qty) }}</template></el-table-column>
        <el-table-column v-if="metric === 'stockout'" prop="sales_30d" label="近30日出库" width="115" align="right"><template #default="{ row }">{{ formatDecimal(row.sales_30d) }}</template></el-table-column>
        <template v-if="metric === 'shortage'">
          <el-table-column prop="sales_30d" label="近30日出库" width="115" align="right"><template #default="{ row }">{{ formatDecimal(row.sales_30d) }}</template></el-table-column>
          <el-table-column prop="daily_sales" label="日均" width="85" align="right"><template #default="{ row }">{{ formatDecimal(row.daily_sales) }}</template></el-table-column>
          <el-table-column prop="target_stock_qty" label="目标库存" width="100" align="right"><template #default="{ row }">{{ formatDecimal(row.target_stock_qty) }}</template></el-table-column>
          <el-table-column prop="shortage_qty" label="缺口" width="90" align="right"><template #default="{ row }"><strong class="shortage-value">{{ formatDecimal(row.shortage_qty) }}</strong></template></el-table-column>
        </template>
        <template v-if="isStatusMetric">
          <el-table-column v-for="group in warehouseGroups" :key="group.key" :label="group.label" align="center">
            <el-table-column v-for="column in warehouseMetricColumns" :key="column.key" :label="column.label" :min-width="80" align="right">
              <template #default="{ row }">{{ formatDecimal(getWarehouseMetric(row, group.key, column.key)) }}</template>
            </el-table-column>
          </el-table-column>
        </template>
        <template #empty><div class="metric-empty">暂无符合条件的明细</div></template>
      </el-table>

      <footer class="metric-pagination">
        <span>共 {{ formatNumber(total) }} 条记录</span>
        <el-pagination :current-page="page" :page-size="pageSize" :total="total" :page-sizes="[20, 50, 100, 200]" background layout="total, sizes, prev, pager, next, jumper" @update:page-size="changePageSize" @update:current-page="changePage" />
      </footer>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElAlert, ElButton, ElInput, ElOption, ElPagination, ElSelect, ElTable, ElTableColumn } from 'element-plus'
import request from '../utils/request'

type MonitorMetric = 'stockout' | 'shortage' | 'listed' | 'delisted'
type MetricFilters = { snapshot_date: string[]; keyword: string; brand: string[]; category_l1: string[]; shop_name: string[]; product_status: string[] }
type FilterOptions = { snapshot_dates: string[]; brands: string[]; categories: string[]; shops: string[] }

const props = withDefaults(defineProps<{
  metric?: MonitorMetric
  initialFilters?: MetricFilters
  options?: FilterOptions
  turnoverDays?: number
}>(), {
  metric: 'stockout',
  initialFilters: () => ({ snapshot_date: [], keyword: '', brand: [], category_l1: [], shop_name: [], product_status: ['上柜'] }),
  options: () => ({ snapshot_dates: [], brands: [], categories: [], shops: [] }),
  turnoverDays: 30,
})

const emit = defineEmits<{ (event: 'back'): void }>()

const filters = reactive<MetricFilters>({
  snapshot_date: [...props.initialFilters.snapshot_date],
  keyword: props.initialFilters.keyword,
  brand: [...props.initialFilters.brand],
  category_l1: [...props.initialFilters.category_l1],
  shop_name: [...props.initialFilters.shop_name],
  product_status: [...props.initialFilters.product_status],
})
const filterOptions = ref<FilterOptions>({
  snapshot_dates: [...props.options.snapshot_dates],
  brands: [...props.options.brands],
  categories: [...props.options.categories],
  shops: [...props.options.shops],
})
const items = ref<Record<string, any>[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const loading = ref(false)
const error = ref('')
const activeTurnoverDays = ref(Number(props.turnoverDays || 30))
let requestId = 0
let autoSearchTimer: ReturnType<typeof setTimeout> | undefined

const metricLabel = computed(() => ({
  stockout: '库存断货数据',
  shortage: '库存缺货数据',
  listed: '库存上柜数据',
  delisted: '库存下柜数据',
}[props.metric]))
const metricDescription = computed(() => {
  if (props.metric === 'stockout') return '查看当前店铺下各仓库现货为 0 的 SKU。'
  if (props.metric === 'shortage') return '查看按库存周转天数计算出的库存缺口 SKU。'
  if (props.metric === 'listed') return '查看当前导入数据中状态为上柜的 SKU。'
  return '查看当前导入数据中状态为下柜的 SKU。'
})
const needsWarehouse = computed(() => props.metric === 'stockout' || props.metric === 'shortage')
const isStatusMetric = computed(() => props.metric === 'listed' || props.metric === 'delisted')
const turnoverDays = computed(() => Number(activeTurnoverDays.value || 30))

const warehouseGroups = [
  { key: 'national', label: '全国' },
  { key: '北京', label: '北京仓' },
  { key: '上海', label: '上海仓' },
  { key: '广州', label: '广州仓' },
  { key: '成都', label: '成都仓' },
  { key: '武汉', label: '武汉仓' },
  { key: '沈阳', label: '沈阳仓' },
  { key: '西安', label: '西安仓' },
  { key: '德州', label: '德州仓' },
] as const
const warehouseMetricColumns = [
  { key: 'stock_qty', label: '现货' },
  { key: 'orderable_qty', label: '可订购' },
  { key: 'sales_1d', label: '昨出库' },
  { key: 'sales_7d', label: '近7日' },
  { key: 'sales_30d', label: '近30日' },
] as const

const getWarehouseMetric = (row: Record<string, any>, groupKey: string, metricKey: string) => {
  if (groupKey === 'national') return row[`national_${metricKey}`]
  return row.city_metrics?.[groupKey]?.[metricKey]
}

const formatNumber = (value: unknown) => {
  const number = Number(value)
  return (Number.isFinite(number) ? number : 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}
const formatDecimal = (value: unknown) => {
  const number = Number(value)
  return (Number.isFinite(number) ? number : 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
const formatDays = (value: unknown) => {
  const number = Number(value)
  return (Number.isFinite(number) ? number : 30).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}
const rowKey = (row: Record<string, any>) => `${row.sku_code}-${row.warehouse || row.product_status || 'sku'}`

const getErrorMessage = (reason: any) => reason?.response?.data?.detail || reason?.message || '指标明细加载失败'

const syncIncomingFilters = (incoming: MetricFilters) => {
  filters.snapshot_date = [...incoming.snapshot_date]
  filters.keyword = incoming.keyword || ''
  filters.brand = [...incoming.brand]
  filters.category_l1 = [...incoming.category_l1]
  filters.shop_name = [...incoming.shop_name]
  filters.product_status = [...incoming.product_status]
}

async function loadOptions() {
  try {
    const response: any = await request.get('/inventory-monitor', {
      params: { ...filters, page: 1, page_size: 1 },
      silent: true,
    } as any)
    const data = response?.data || {}
    if (data.filter_options) {
      for (const key of ['snapshot_dates', 'brands', 'categories', 'shops'] as const) {
        if (Array.isArray(data.filter_options[key])) filterOptions.value[key] = data.filter_options[key]
      }
    }
    if (data.summary?.turnover_days) activeTurnoverDays.value = Number(data.summary.turnover_days)
  } catch {
    // 明细接口仍可独立加载，筛选选项失败时保留已传入的选项。
  }
}

async function load() {
  const id = ++requestId
  loading.value = true
  error.value = ''
  try {
    const response: any = await request.get('/inventory-monitor/details', {
      params: {
        ...filters,
        metric: props.metric,
        page: page.value,
        page_size: pageSize.value,
      },
    })
    if (id !== requestId) return
    const data = response?.data || {}
    items.value = Array.isArray(data.items) ? data.items : []
    total.value = Number(data.total || 0)
    const lastPage = Math.max(1, Math.ceil(total.value / pageSize.value))
    if (page.value > lastPage) {
      page.value = lastPage
      await load()
    }
  } catch (reason: unknown) {
    if (id !== requestId) return
    error.value = getErrorMessage(reason)
    items.value = []
    total.value = 0
  } finally {
    if (id === requestId) loading.value = false
  }
}

function search() {
  if (autoSearchTimer) {
    clearTimeout(autoSearchTimer)
    autoSearchTimer = undefined
  }
  filters.keyword = filters.keyword.trim()
  page.value = 1
  void load()
}

function scheduleFilterSearch() {
  if (autoSearchTimer) clearTimeout(autoSearchTimer)
  autoSearchTimer = setTimeout(() => {
    autoSearchTimer = undefined
    search()
  }, 220)
}

function reset() {
  filters.snapshot_date = []
  filters.keyword = ''
  filters.brand = []
  filters.category_l1 = []
  filters.shop_name = []
  filters.product_status = ['上柜']
  search()
}

function changePage(next: number) {
  if (next === page.value) return
  page.value = next
  void load()
}

function changePageSize(next: number) {
  if (next === pageSize.value) return
  pageSize.value = next
  page.value = 1
  void load()
}

watch(
  () => props.initialFilters,
  (next) => {
    syncIncomingFilters(next)
  },
  { deep: true },
)

watch(
  filters,
  () => {
    scheduleFilterSearch()
  },
  { deep: true },
)

onMounted(() => {
  void loadOptions()
  void load()
})
</script>

<style scoped>
.monitor-metric-page{box-sizing:border-box;min-height:100%;padding:20px;background:var(--app-bg,#f5f7fb);color:var(--text-primary,#1e293b);--el-color-primary:light-dark(#0f766e, #2dd4bf);display:flex;flex-direction:column;gap:14px}.metric-page-header,.metric-filter-panel,.metric-detail-panel{border:1px solid var(--border-color,#e5eaf2);border-radius:12px;background:var(--app-surface,#fff);box-shadow:0 2px 6px #16325704}.metric-page-header{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:18px 22px}.back-button{padding:0;margin-bottom:8px}.metric-page-header h1{margin:0;font-size:22px;line-height:1.25}.metric-page-header p{margin:8px 0 0;color:light-dark(#64748b, var(--text-secondary));font-size:13px}.metric-page-total{min-width:130px;padding-left:20px;border-left:1px solid light-dark(#e2e8f0, var(--border-color));text-align:right}.metric-page-total span,.metric-page-total small{display:block;color:light-dark(#94a3b8, var(--text-secondary));font-size:12px}.metric-page-total strong{display:block;margin:2px 0;color:light-dark(#0f766e, var(--text-accent));font-size:28px;line-height:1.1}.metric-filter-panel{display:grid;grid-template-columns:repeat(4,minmax(130px,1fr));gap:14px;padding:16px 20px}.metric-filter-panel label{display:flex;flex-direction:column;gap:7px;min-width:0;color:light-dark(#64748b, var(--text-secondary));font-size:12px}.metric-filter-panel .keyword-field{grid-column:span 2}.metric-filter-panel :deep(.el-select),.metric-filter-panel :deep(.el-input){width:100%}.metric-filter-actions{display:flex;align-items:flex-end;justify-content:flex-end;gap:8px;grid-column:span 2}.metric-detail-panel{flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden;padding:0 20px 14px}.metric-detail-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:18px 0 14px}.metric-detail-toolbar h2{margin:0 0 6px;font-size:16px}.metric-detail-toolbar span{color:light-dark(#94a3b8, var(--text-secondary));font-size:12px}.metric-detail-table{flex:1;min-height:360px;font-size:12px;--el-table-header-bg-color:light-dark(#f8fafc, var(--table-header-bg))}.shortage-value{color:light-dark(#c2410c, #fb923c)}.metric-empty{padding:56px 0;color:light-dark(#94a3b8, var(--text-secondary));text-align:center}.metric-pagination{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding-top:14px;color:light-dark(#64748b, var(--text-secondary));font-size:12px}.metric-pagination :deep(.el-pagination){flex-wrap:wrap}
.metric-page-alert{margin:0}@media(max-width:1050px){.metric-filter-panel{grid-template-columns:repeat(2,minmax(130px,1fr))}.metric-filter-panel .keyword-field,.metric-filter-actions{grid-column:auto}.metric-filter-actions{justify-content:flex-start}}@media(max-width:640px){.monitor-metric-page{padding:14px}.metric-page-header{align-items:flex-start;flex-direction:column;padding:16px}.metric-page-total{width:100%;padding:12px 0 0;border-left:0;border-top:1px solid light-dark(#e2e8f0, var(--border-color));text-align:left}.metric-filter-panel{grid-template-columns:1fr;padding:14px}.metric-filter-panel .keyword-field{grid-column:auto}.metric-filter-actions{grid-column:auto}.metric-detail-panel{padding:0 14px 14px}.metric-detail-toolbar{align-items:flex-start;flex-direction:column}.metric-pagination{align-items:flex-start;flex-direction:column}}
.metric-filter-panel{grid-template-columns:repeat(6,minmax(120px,1fr)) auto}.metric-filter-panel .keyword-field{grid-column:auto}.metric-filter-actions{grid-column:auto;white-space:nowrap}
@media(max-width:1200px){.metric-filter-panel{grid-template-columns:repeat(3,minmax(130px,1fr))}.metric-filter-actions{grid-column:1/-1;justify-content:flex-start}}
@media(max-width:1050px){.metric-filter-panel{grid-template-columns:repeat(2,minmax(130px,1fr))}.metric-filter-actions{grid-column:1/-1;justify-content:flex-start}}
@media(max-width:640px){.metric-filter-panel{grid-template-columns:1fr}.metric-filter-actions{grid-column:auto}}
</style>
