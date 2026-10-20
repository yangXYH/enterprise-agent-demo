<template>
  <section class="purchase-page">
    <el-alert
      v-if="importStatus"
      class="purchase-alert"
      :title="importStatus"
      type="success"
      show-icon
      closable
      @close="importStatus = ''"
    />
    <el-alert v-if="error" class="purchase-alert" :title="error" type="error" show-icon :closable="false">
      <el-button link type="primary" @click="load">重新加载</el-button>
    </el-alert>

    <section class="purchase-header">
      <div>
        <span class="purchase-eyebrow">供应链部 / 采购执行</span>
        <h1>采购单看板</h1>
        <p>
          {{ batch.source_name ? `数据来源：${batch.source_name}` : '请导入采购单明细文件' }}
          <span v-if="batch.date_start"> · 数据日期：{{ batch.date_start }} 至 {{ batch.date_end }}</span>
        </p>
      </div>
      <div class="purchase-actions">
        <el-button size="small" text @click="reset">重置筛选</el-button>
        <el-button size="small" type="primary" :loading="importing" @click="fileInput?.click()">
          {{ importing ? '正在导入…' : '导入采购单' }}
        </el-button>
        <input ref="fileInput" class="file-input" type="file" accept=".xlsx,.xlsm" :disabled="importing" @change="uploadFile" />
      </div>
    </section>

    <section class="purchase-summary purchase-summary-five" aria-label="采购单汇总">
      <article class="purchase-kpi purchase-kpi-primary">
        <span>采购单数</span>
        <strong>{{ formatNumber(summary.order_count) }}</strong>
        <small>{{ formatNumber(summary.row_count) }} 条采购明细</small>
      </article>
      <article class="purchase-kpi">
        <span>采购数量</span>
        <strong>{{ formatNumber(summary.quantity) }}</strong>
        <small>{{ formatNumber(summary.product_count) }} 个商品编码</small>
      </article>
      <article class="purchase-kpi">
        <span>已入库数量</span>
        <strong>{{ formatNumber(summary.received_quantity) }}</strong>
        <small>采购数量的 {{ receivedRate }}</small>
      </article>
      <article class="purchase-kpi">
        <span>订单待发数</span>
        <strong>{{ formatNumber(summary.pending_ship_quantity) }}</strong>
        <small>当前订单待发需求</small>
      </article>
      <article class="purchase-kpi purchase-kpi-warning">
        <span>总可用数</span>
        <strong>{{ formatNumber(summary.available_quantity) }}</strong>
        <small>关联明细可用库存</small>
      </article>
      <article v-if="summary.variance_quantity !== 0" class="purchase-kpi purchase-kpi-danger">
        <span>差异数</span>
        <strong>{{ formatNumber(summary.variance_quantity) }}</strong>
        <small>{{ summary.variance_quantity === 0 ? '当前无数量差异' : '请优先核查差异明细' }}</small>
      </article>
    </section>

    <section class="purchase-filters panel" aria-label="采购单筛选">
      <div class="filter-caption">筛选条件</div>
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        size="small"
        value-format="YYYY-MM-DD"
        range-separator="至"
        start-placeholder="采购开始日期"
        end-placeholder="采购结束日期"
        clearable
        :disabled-date="disabledPurchaseDate"
        class="date-filter"
      />
      <el-input v-model="filters.keyword" size="small" clearable placeholder="采购单号 / 商品 / 供应商编码" />
      <el-select v-model="filters.status" size="small" filterable clearable placeholder="全部采购状态">
        <el-option v-for="item in options.statuses" :key="item" :label="item" :value="item" />
      </el-select>
      <el-select v-model="filters.receiving_status" size="small" filterable clearable placeholder="全部收货状态">
        <el-option v-for="item in options.receiving_statuses" :key="item" :label="item" :value="item" />
      </el-select>
      <el-select v-model="filters.warehouse_party" size="small" filterable clearable placeholder="全部仓储方">
        <el-option v-for="item in options.warehouses" :key="item" :label="item" :value="item" />
      </el-select>
      <el-select v-model="filters.purchaser" size="small" filterable clearable placeholder="全部采购员">
        <el-option v-for="item in options.purchasers" :key="item" :label="item" :value="item" />
      </el-select>
    </section>

    <section class="panel purchase-detail-panel" :aria-busy="loading">
      <header class="detail-header">
        <div>
          <h2>采购明细</h2>
          <span>保留文件中的全部采购字段，可横向滚动查看</span>
        </div>
        <span class="detail-count">{{ total ? `当前筛选 ${formatNumber(total)} 条` : '暂无明细' }}</span>
      </header>
      <div class="purchase-table-wrap">
        <div v-if="loading" class="loading-note">正在加载采购明细…</div>
        <el-table :data="items" row-key="source_row" stripe height="100%" table-layout="fixed" class="purchase-table">
          <el-table-column label="图片" width="82" align="center">
            <template #default="{ row }">
              <el-image v-if="row.image_url" :src="row.image_url" :preview-src-list="[row.image_url]" preview-teleported fit="contain" class="purchase-image" loading="lazy">
                <template #error><span class="image-error">失败</span></template>
              </el-image>
              <span v-else class="image-empty">暂无</span>
            </template>
          </el-table-column>
          <el-table-column prop="product_code" label="商品编码" min-width="142" show-overflow-tooltip class-name="code-column" />
          <el-table-column prop="order_no" label="采购单号" width="112" show-overflow-tooltip class-name="code-column" />
          <el-table-column prop="purchase_date" label="采购日期" width="154" show-overflow-tooltip />
          <el-table-column label="状态" width="92" align="center">
            <template #default="{ row }"><el-tag size="small" effect="plain" :type="statusTagType(row.status)">{{ row.status || '未填写' }}</el-tag></template>
          </el-table-column>
          <el-table-column label="收货状态" width="104" align="center">
            <template #default="{ row }"><el-tag size="small" effect="plain" :type="receivingTagType(row.receiving_status)">{{ row.receiving_status || '未填写' }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="purchase_remark" label="采购单备注" min-width="180" show-overflow-tooltip />
          <el-table-column prop="receiving_address" label="收货地址" min-width="250" show-overflow-tooltip />
          <el-table-column prop="purchase_type" label="采购单类型" min-width="130" show-overflow-tooltip />
          <el-table-column prop="warehouse_party" label="仓储方" min-width="155" show-overflow-tooltip />
          <el-table-column prop="purchaser" label="采购员" width="100" show-overflow-tooltip />
          <el-table-column prop="review_date" label="审核日期" width="154" show-overflow-tooltip />
          <el-table-column prop="last_modified_date" label="最后修改日期" width="154" show-overflow-tooltip />
          <el-table-column prop="style_code" label="款式编码" min-width="130" show-overflow-tooltip class-name="code-column" />
          <el-table-column prop="product_name" label="商品名称" min-width="230" show-overflow-tooltip />
          <el-table-column prop="color_spec" label="颜色及规格" min-width="150" show-overflow-tooltip />
          <el-table-column prop="pending_ship_quantity" label="订单待发数" width="112" align="right"><template #default="{ row }"><span class="quantity">{{ formatNumber(row.pending_ship_quantity) }}</span></template></el-table-column>
          <el-table-column prop="available_quantity" label="总可用数" width="105" align="right"><template #default="{ row }"><span class="quantity">{{ formatNumber(row.available_quantity) }}</span></template></el-table-column>
          <el-table-column prop="quantity" label="数量" width="92" align="right"><template #default="{ row }"><strong class="quantity">{{ formatNumber(row.quantity) }}</strong></template></el-table-column>
          <el-table-column prop="received_quantity" label="已入库数量" width="112" align="right"><template #default="{ row }"><span class="quantity">{{ formatNumber(row.received_quantity) }}</span></template></el-table-column>
          <el-table-column prop="variance_quantity" label="差异数" width="92" align="right"><template #default="{ row }"><span :class="['quantity', { 'quantity-danger': Number(row.variance_quantity) !== 0 }]">{{ formatNumber(row.variance_quantity) }}</span></template></el-table-column>
          <el-table-column prop="supplier_product_code" label="供应商商品编码" min-width="150" show-overflow-tooltip class-name="code-column" />
          <el-table-column prop="supplier_style_no" label="供应商款号" min-width="140" show-overflow-tooltip class-name="code-column" />
          <el-table-column prop="detail_no" label="明细单号" min-width="120" show-overflow-tooltip class-name="code-column" />
          <template #empty><div class="empty-state">{{ error ? '数据加载失败' : '暂无采购明细，请导入采购单文件或调整筛选条件' }}</div></template>
        </el-table>
      </div>
      <footer class="purchase-pagination">
        <span>{{ total ? `当前 ${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} 条，共 ${formatNumber(total)} 条` : '共 0 条记录' }}</span>
        <el-pagination :current-page="page" :page-size="pageSize" :total="total" :page-sizes="[20, 50, 100, 200]" background layout="sizes, prev, pager, next, jumper" @update:page-size="changePageSize" @update:current-page="changePage" />
      </footer>
    </section>

    <section class="purchase-chart-grid" aria-label="采购单分析图表">
      <article class="panel chart-panel chart-panel-wide">
        <header class="chart-header">
          <div><h2>采购数量与入库趋势</h2><span>按采购日期统计</span></div>
        </header>
        <VChart :option="trendOption" autoresize class="purchase-chart purchase-chart-tall" />
      </article>
      <article class="panel chart-panel">
        <header class="chart-header">
          <div><h2>采购单状态分布</h2><span>按采购明细统计</span></div>
        </header>
        <VChart :option="statusOption" autoresize class="purchase-chart" />
      </article>
      <article class="panel chart-panel">
        <header class="chart-header">
          <div><h2>收货状态分布</h2><span>按采购明细统计</span></div>
        </header>
        <VChart :option="receivingOption" autoresize class="purchase-chart" />
      </article>
    </section>

  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElAlert, ElButton, ElDatePicker, ElImage, ElInput, ElOption, ElPagination, ElSelect, ElTable, ElTableColumn, ElTag } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { CanvasRenderer } from 'echarts/renderers'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import request from '../utils/request'

use([CanvasRenderer, BarChart, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent])

type Filters = {
  keyword: string
  status: string
  receiving_status: string
  warehouse_party: string
  purchaser: string
}
type Summary = {
  row_count: number
  order_count: number
  product_count: number
  quantity: number
  received_quantity: number
  pending_ship_quantity: number
  available_quantity: number
  variance_quantity: number
}
type PurchaseRow = Record<string, any> & { source_row: number; image_url: string }
type ChartPoint = { name: string; value: number; order_count?: number; quantity?: number }
type TrendPoint = { date: string; order_count: number; row_count: number; quantity: number; received_quantity: number }

const emptyFilters = (): Filters => ({ keyword: '', status: '', receiving_status: '', warehouse_party: '', purchaser: '' })
const emptySummary = (): Summary => ({ row_count: 0, order_count: 0, product_count: 0, quantity: 0, received_quantity: 0, pending_ship_quantity: 0, available_quantity: 0, variance_quantity: 0 })
const filters = reactive<Filters>(emptyFilters())
const dateRange = ref<string[]>([])
const summary = reactive<Summary>(emptySummary())
const batch = reactive<Record<string, any>>({})
const options = reactive({ statuses: [] as string[], receiving_statuses: [] as string[], warehouses: [] as string[], purchasers: [] as string[], purchase_dates: [] as string[] })
const charts = reactive({ status: [] as ChartPoint[], receiving_status: [] as ChartPoint[], trend: [] as TrendPoint[] })
const items = ref<PurchaseRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const loading = ref(false)
const importing = ref(false)
const error = ref('')
const importStatus = ref('')
const fileInput = ref<HTMLInputElement>()
let disposed = false
let requestId = 0
let searchTimer: ReturnType<typeof setTimeout> | undefined

const formatNumber = (value: unknown) => Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
const receivedRate = computed(() => summary.quantity > 0 ? `${((summary.received_quantity / summary.quantity) * 100).toFixed(1)}%` : '0.0%')
const errorMessage = (reason: any, fallback: string) => typeof reason?.response?.data?.detail === 'string' ? reason.response.data.detail : reason?.message || fallback
const disabledPurchaseDate = (time: Date) => {
  const year = time.getFullYear()
  const month = String(time.getMonth() + 1).padStart(2, '0')
  const day = String(time.getDate()).padStart(2, '0')
  return options.purchase_dates.length === 0 || !options.purchase_dates.includes(`${year}-${month}-${day}`)
}
const chartData = (points: ChartPoint[]) => points.map((item) => ({ name: item.name, value: Number(item.value || 0) }))
const trendOption = computed(() => ({
  color: ['#0f766e', '#38bdf8'],
  tooltip: { trigger: 'axis' },
  legend: { top: 0, right: 12, textStyle: { color: '#64748b', fontSize: 11 } },
  grid: { left: 48, right: 24, top: 34, bottom: 28, containLabel: true },
  xAxis: { type: 'category', data: charts.trend.map((item) => item.date), axisLabel: { color: '#94a3b8', fontSize: 11 }, axisLine: { lineStyle: { color: '#dbe5ef' } } },
  yAxis: { type: 'value', axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: '#e8eef5' } } },
  series: [
    { name: '采购数量', type: 'bar', barMaxWidth: 24, data: charts.trend.map((item) => item.quantity), itemStyle: { color: '#0f766e', borderRadius: [4, 4, 0, 0] } },
    { name: '已入库数量', type: 'line', smooth: true, data: charts.trend.map((item) => item.received_quantity), symbolSize: 7, lineStyle: { width: 3, color: '#38bdf8' }, itemStyle: { color: '#38bdf8' } },
  ],
}))
const pieOption = (points: ChartPoint[], colors: string[]) => ({
  color: colors,
  tooltip: { trigger: 'item', formatter: '{b}<br/>{c} 条（{d}%）' },
  legend: { bottom: 0, left: 'center', type: 'scroll', textStyle: { color: '#64748b', fontSize: 11 } },
  series: [{ type: 'pie', radius: ['42%', '68%'], center: ['50%', '43%'], avoidLabelOverlap: true, itemStyle: { borderColor: '#fff', borderWidth: 2 }, label: { color: '#475569', formatter: '{b}\n{d}%', fontSize: 11 }, data: chartData(points) }],
})
const statusOption = computed(() => pieOption(charts.status, ['#0f766e', '#14b8a6', '#38bdf8', '#f59e0b', '#94a3b8', '#f97316']))
const receivingOption = computed(() => pieOption(charts.receiving_status, ['#2563eb', '#0f766e', '#f59e0b', '#f97316', '#94a3b8']))

function statusTagType(value: unknown) {
  const label = String(value || '')
  if (/完成|关闭|结案/.test(label)) return 'success'
  if (/取消|作废|拒绝/.test(label)) return 'danger'
  if (/审核|待|处理中/.test(label)) return 'warning'
  return 'info'
}
function receivingTagType(value: unknown) {
  const label = String(value || '')
  if (/全量|完成|已收|入库/.test(label)) return 'success'
  if (/部分|待|未/.test(label)) return 'warning'
  return 'info'
}
async function load() {
  const id = ++requestId
  loading.value = true
  error.value = ''
  try {
    const response: any = await request.get('/purchase-order-dashboard', {
      params: {
        ...filters,
        date_start: dateRange.value[0] || '',
        date_end: dateRange.value[1] || '',
        page: page.value,
        page_size: pageSize.value,
      },
    })
    if (disposed || id !== requestId) return
    const data = response?.data || {}
    Object.assign(batch, data.batch || {})
    Object.assign(summary, emptySummary(), data.summary || {})
    items.value = Array.isArray(data.items) ? data.items : []
    Object.assign(options, {
      statuses: Array.isArray(data.filter_options?.statuses) ? data.filter_options.statuses : [],
      receiving_statuses: Array.isArray(data.filter_options?.receiving_statuses) ? data.filter_options.receiving_statuses : [],
      warehouses: Array.isArray(data.filter_options?.warehouses) ? data.filter_options.warehouses : [],
      purchasers: Array.isArray(data.filter_options?.purchasers) ? data.filter_options.purchasers : [],
      purchase_dates: Array.isArray(data.filter_options?.purchase_dates) ? data.filter_options.purchase_dates : [],
    })
    Object.assign(charts, {
      status: Array.isArray(data.charts?.status) ? data.charts.status : [],
      receiving_status: Array.isArray(data.charts?.receiving_status) ? data.charts.receiving_status : [],
      trend: Array.isArray(data.charts?.trend) ? data.charts.trend : [],
    })
    total.value = Number(data.total || 0)
    const lastPage = Math.max(1, Math.ceil(total.value / pageSize.value))
    if (page.value > lastPage) { page.value = lastPage; await load() }
  } catch (reason: unknown) {
    if (disposed || id !== requestId) return
    error.value = errorMessage(reason, '采购单看板加载失败')
    items.value = []
    total.value = 0
  } finally {
    if (!disposed && id === requestId) loading.value = false
  }
}
function reset() { Object.assign(filters, emptyFilters()); dateRange.value = []; page.value = 1 }
function changePage(next: number) { if (next !== page.value) { page.value = next; void load() } }
function changePageSize(next: number) { if (next !== pageSize.value) { pageSize.value = next; page.value = 1; void load() } }
async function uploadFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || importing.value) return
  if (!/\.(xlsx|xlsm)$/i.test(file.name)) { error.value = '请选择 .xlsx 或 .xlsm 格式的采购单文件'; input.value = ''; return }
  importing.value = true
  importStatus.value = ''
  const form = new FormData()
  form.append('file', file)
  try {
    const response: any = await request.post('/purchase-order-dashboard/import', form)
    if (disposed) return
    const imported = response?.data || {}
    importStatus.value = `导入完成：${formatNumber(imported.order_count)} 个采购单，${formatNumber(imported.row_count)} 条明细。`
    Object.assign(filters, emptyFilters())
    dateRange.value = []
    page.value = 1
    await load()
  } catch (reason: unknown) {
    if (!disposed) error.value = errorMessage(reason, '导入失败，请检查采购单文件后重试')
  } finally {
    importing.value = false
    input.value = ''
  }
}
watch([filters, dateRange], () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { page.value = 1; void load() }, 300)
}, { deep: true })
onMounted(() => { void load() })
onBeforeUnmount(() => { disposed = true; requestId++; if (searchTimer) clearTimeout(searchTimer) })
</script>

<style scoped>
.purchase-page{min-height:100%;box-sizing:border-box;padding:20px;background:var(--app-bg,#f8fafc);color:var(--text-primary,#1f2937);--el-color-primary:light-dark(#0f766e, #2dd4bf);overflow:auto}.purchase-alert{margin-bottom:12px}.purchase-header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:16px}.purchase-eyebrow{color:light-dark(#0f766e, var(--text-accent));font-size:11px;font-weight:700;letter-spacing:.08em}.purchase-header h1{margin:5px 0 0;color:var(--text-heading,#0f172a);font-size:24px;line-height:1.2}.purchase-header p{margin:7px 0 0;max-width:680px;overflow:hidden;color:var(--text-muted,#94a3b8);font-size:12px;text-overflow:ellipsis;white-space:nowrap}.purchase-actions{display:flex;align-items:center;gap:6px;flex-shrink:0}.purchase-actions .el-button{white-space:nowrap}.file-input{display:none}.purchase-summary{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin-bottom:14px}.purchase-kpi{min-height:96px;padding:15px 16px;border:1px solid var(--border-color,#e2e8f0);border-radius:12px;background:var(--app-surface,#fff);box-shadow:var(--shadow-sm);display:flex;flex-direction:column}.purchase-kpi span{color:var(--text-secondary,#64748b);font-size:12px}.purchase-kpi strong{margin-top:10px;color:var(--text-heading,#0f172a);font-size:23px;line-height:1;font-variant-numeric:tabular-nums}.purchase-kpi small{margin-top:auto;color:var(--text-muted,#94a3b8);font-size:11px}.purchase-kpi-primary{border-top:3px solid #0f766e}.purchase-kpi-warning{border-top:3px solid #f59e0b}.purchase-kpi-danger{border-top:3px solid #dc2626}.purchase-kpi-danger strong,.quantity-danger{color:light-dark(#dc2626, #f87171)}.panel{border:1px solid var(--border-color,#e2e8f0);border-radius:12px;background:var(--app-surface,#fff);box-shadow:var(--shadow-sm)}.purchase-filters{display:grid;grid-template-columns:auto minmax(250px,1.1fr) minmax(220px,1.1fr) repeat(5,minmax(130px,1fr));align-items:center;gap:8px;padding:14px 16px;margin-bottom:14px}.filter-caption{color:var(--text-heading,#334155);font-size:12px;font-weight:700;white-space:nowrap}.purchase-filters :deep(.el-select),.purchase-filters :deep(.el-input),.date-filter{width:100%}.purchase-chart-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-bottom:14px}.chart-panel{min-width:0;padding:0 14px 10px}.chart-panel-wide{grid-column:1/-1}.chart-header{display:flex;align-items:center;justify-content:space-between;min-height:58px;border-bottom:1px solid var(--border-subtle,#edf2f7)}.chart-header h2,.detail-header h2{margin:0;color:var(--text-heading,#0f172a);font-size:14px}.chart-header span,.detail-header span{display:block;margin-top:5px;color:var(--text-muted,#94a3b8);font-size:11px}.purchase-chart{width:100%;height:270px}.purchase-chart-tall{height:310px}.purchase-chart-rank{height:300px}.purchase-detail-panel{min-width:0;overflow:hidden}.detail-header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 18px;border-bottom:1px solid var(--border-subtle,#edf2f7)}.detail-count{flex-shrink:0!important;margin-top:0!important;color:light-dark(#0f766e, var(--text-accent))!important;font-weight:700}.purchase-table-wrap{height:560px;position:relative;min-width:0}.loading-note{position:absolute;top:0;right:0;left:0;z-index:3;padding:8px 18px;background:light-dark(#ecfdf5, var(--primary-surface-2));color:light-dark(#0f766e, var(--text-accent));font-size:12px}.purchase-table{width:100%;height:100%;--el-table-header-bg-color:var(--table-header-bg,#f8fafc);--el-table-header-text-color:var(--text-secondary,#64748b);--el-table-border-color:var(--border-subtle,#edf2f7);--el-table-row-hover-bg-color:light-dark(#f0fdfa, var(--primary-surface-2));--el-table-text-color:var(--text-primary,#334155);font-size:12px}.purchase-table :deep(th.el-table__cell){padding:8px 0;font-weight:600;white-space:nowrap}.purchase-table :deep(td.el-table__cell){padding:5px 0}.purchase-table :deep(.cell){padding:0 8px}.purchase-table :deep(.code-column .cell){color:var(--text-secondary,#64748b);font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px}.purchase-image{width:48px;height:48px;border:1px solid light-dark(#eef2f7, var(--border-color));border-radius:7px;background:light-dark(#f8fafc, var(--app-surface-2));vertical-align:middle}.image-error,.image-empty{color:light-dark(#cbd5e1, var(--text-secondary));font-size:10px}.quantity{font-variant-numeric:tabular-nums}.empty-state{padding:70px 0;color:var(--text-muted,#94a3b8);text-align:center}.purchase-pagination{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:11px 18px;border-top:1px solid var(--border-subtle,#edf2f7);color:var(--text-secondary,#64748b);font-size:12px}.purchase-pagination :deep(.el-pagination){flex-shrink:0}
@media(max-width:1500px){.purchase-summary{grid-template-columns:repeat(3,minmax(0,1fr))}.purchase-filters{grid-template-columns:auto repeat(3,minmax(160px,1fr))}.purchase-filters .date-filter{grid-column:span 2}.purchase-filters .el-input{grid-column:span 2}}
@media(max-width:850px){.purchase-page{padding:14px}.purchase-header{align-items:stretch;flex-direction:column}.purchase-actions{justify-content:flex-end}.purchase-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.purchase-filters{grid-template-columns:1fr}.purchase-filters .date-filter,.purchase-filters .el-input{grid-column:auto}.purchase-chart-grid{grid-template-columns:1fr}.chart-panel-wide{grid-column:auto}.detail-header{align-items:flex-start;flex-direction:column}.purchase-pagination{align-items:flex-start;flex-direction:column}}
</style>

<style scoped>
.purchase-summary-five{grid-template-columns:repeat(5,minmax(0,1fr))}
@media(max-width:1500px){.purchase-summary-five{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:850px){.purchase-summary-five{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>

<style scoped>
/* 给日期范围保留足够空间，避免结束日期被关键词输入框视觉挤压。 */
.purchase-filters{grid-template-columns:auto 310px minmax(220px,1fr) repeat(4,minmax(120px,1fr));column-gap:16px}
.purchase-filters .date-filter{width:310px!important;min-width:0!important;max-width:310px;box-sizing:border-box;--el-date-editor-daterange-width:310px}
@media(max-width:1500px){.purchase-filters{display:flex;grid-template-columns:none;flex-wrap:wrap;column-gap:16px;row-gap:8px}.purchase-filters .date-filter{flex:0 0 310px;width:310px!important;min-width:310px;max-width:310px}.purchase-filters > :deep(.el-input){flex:1 1 220px;min-width:220px;width:auto!important}.purchase-filters > :deep(.el-select){flex:1 1 160px;min-width:160px;width:auto!important}}
@media(max-width:850px){.purchase-filters{display:grid;grid-template-columns:1fr}.purchase-filters .date-filter{flex:none;width:100%!important;min-width:0;max-width:none;--el-date-editor-daterange-width:100%}.purchase-filters > :deep(.el-input),.purchase-filters > :deep(.el-select){flex:none;min-width:0;width:100%!important}}
</style>
