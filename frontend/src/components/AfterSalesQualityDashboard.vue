<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  ElButton,
  ElDatePicker,
  ElIcon,
  ElInput,
  ElLoading,
  ElMessage,
  ElOption,
  ElPagination,
  ElRadioButton,
  ElRadioGroup,
  ElSelect,
  ElTable,
  ElTableColumn,
  ElTag,
} from 'element-plus'
import { Download, Refresh, Search } from '@element-plus/icons-vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components'
import * as XLSX from 'xlsx'
import request from '../utils/request'

use([
  CanvasRenderer,
  BarChart,
  LineChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
])

interface BrandMetric {
  brand: string
  after_sales: number
  quality: number
  quality_rate: number
  refund_amount: number
  avg_duration_hours: number
}

interface StoreMetric {
  store_name: string
  after_sales: number
  quality: number
  quality_rate: number
  refund_amount: number
  avg_duration_hours: number
}

interface TrendPoint {
  date: string
  brands: Record<string, number>
  total: number
}

interface CategoryPoint {
  category: string
  brands: Record<string, number>
  total: number
}

interface ProductMetric {
  product_name: string
  after_sales: number
  quality: number
  quality_count: number
  non_quality_count: number
  quality_rate: number
}

interface DetailRow {
  service_no: string
  order_no: string
  apply_time: string
  brand: string
  store_name: string
  product_no: string
  product_name: string
  category: string
  is_quality: boolean
  reason1: string
  reason2: string
  customer_desc: string
  customer1: string
  customer2: string
  audit_opinion: string
  handle_result: string
  refund_amount: number
  duration_hours: number
}

interface DashboardMeta {
  source_name: string
  date_min: string
  date_max: string
  data_date_min: string
  data_date_max: string
  after_sales_total: number
  quality_total: number
  non_quality_total: number
  problem_total: number
  problem_scope: string
  quality_rate: number
  refund_amount: number
  avg_duration_hours: number
}

interface DashboardPayload {
  meta: DashboardMeta
  brand_options: string[]
  brands: BrandMetric[]
  stores: StoreMetric[]
  trend: TrendPoint[]
  categories: CategoryPoint[]
  top_products: ProductMetric[]
  details: DetailRow[]
}

const vLoading = ElLoading.directive

const EMPTY_META: DashboardMeta = {
  source_name: '',
  date_min: '',
  date_max: '',
  data_date_min: '',
  data_date_max: '',
  after_sales_total: 0,
  quality_total: 0,
  non_quality_total: 0,
  problem_total: 0,
  problem_scope: 'all',
  quality_rate: 0,
  refund_amount: 0,
  avg_duration_hours: 0,
}

const payload = ref<DashboardPayload | null>(null)
const loading = ref(false)
const brandFilter = ref<string[]>([])
const storeFilter = ref('')
const categoryFilter = ref('')
const dateRange = ref<string[]>([])
const searchText = ref('')
const appliedSearchText = ref('')
const problemScope = ref<'all' | 'quality' | 'non_quality'>('all')
const detailPage = ref(1)
const detailPageSize = ref(20)

const meta = computed(() => payload.value?.meta ?? EMPTY_META)

const disabledDate = (date: Date) => {
  if (!meta.value.data_date_min || !meta.value.data_date_max) return true
  const min = new Date(`${meta.value.data_date_min}T00:00:00`).getTime()
  const max = new Date(`${meta.value.data_date_max}T00:00:00`).getTime()
  return date.getTime() < min || date.getTime() > max
}

const storeOptions = computed(() =>
  payload.value ? payload.value.stores.map((store) => store.store_name) : [],
)

const categoryOptions = computed(() =>
  payload.value ? payload.value.categories.map((item) => item.category) : [],
)

const brandOptions = computed(() => payload.value?.brand_options ?? [])

const topProducts = computed(() => payload.value?.top_products ?? [])

const BRAND_COLORS = [
  '#0f766e',
  '#d97706',
  '#7c3aed',
  '#0e7490',
  '#b91c1c',
  '#4d7c0f',
  '#be185d',
  '#1d4ed8',
  '#64748b',
]

const visibleChartBrands = computed(() => {
  if (brandFilter.value.length) return brandFilter.value.slice(0, 8)
  return brandOptions.value.slice(0, 8)
})

const kpiItems = computed(() => [
  {
    label: '售后单总量',
    value: meta.value.after_sales_total.toLocaleString('zh-CN'),
    unit: '单',
    sub: `${meta.value.date_min} 至 ${meta.value.date_max}`,
    tone: 'neutral',
  },
  {
    label: '当前问题单量',
    value: meta.value.problem_total.toLocaleString('zh-CN'),
    unit: '单',
    sub: problemScope.value === 'quality'
      ? `质量问题率 ${meta.value.quality_rate.toFixed(2)}%`
      : problemScope.value === 'non_quality'
        ? `非质量 ${meta.value.non_quality_total.toLocaleString('zh-CN')} 单`
        : `质量 ${meta.value.quality_total} / 非质量 ${meta.value.non_quality_total}`,
    tone: 'danger',
  },
  {
    label: '当前问题退款',
    value: formatMoney(meta.value.refund_amount),
    unit: '',
    sub: `平均 ${meta.value.avg_duration_hours.toFixed(1)} 小时完结`,
    tone: 'warning',
  },
  {
    label: '问题最集中品牌',
    value: worstBrand.value,
    unit: '',
    sub: worstRate.value,
    tone: 'accent',
  },
])

const worstBrand = computed(() => {
  const metrics = payload.value?.brands ?? []
  const worst = metrics.reduce(
    (current, item) => (item.quality > current.quality ? item : current),
    metrics[0] ?? { brand: '-', quality: 0, quality_rate: 0 },
  )
  return worst.brand
})

const worstRate = computed(() => {
  const metrics = payload.value?.brands ?? []
  const worst = metrics.reduce(
    (current, item) => (item.quality > current.quality ? item : current),
    metrics[0] ?? { quality: 0, quality_rate: 0 },
  )
  return `当前问题 ${worst.quality} 条`
})

const brandOption = computed<Record<string, unknown>>(() => {
  const brands = payload.value?.brands ?? []
  const barWidth = Math.max(18, Math.min(42, Math.floor(560 / Math.max(brands.length, 1))))
  return {
    tooltip: { trigger: 'axis' },
    legend: { top: 0, data: ['当前问题单量', '质量占比'] },
    grid: { left: 44, right: 58, top: 42, bottom: 28 },
    xAxis: {
      type: 'category',
      data: brands.map((item) => item.brand),
      axisLabel: {
        color: '#64748b',
        interval: 0,
        rotate: brands.length > 5 ? 25 : 0,
      },
      axisLine: { lineStyle: { color: '#cbd5e1' } },
    },
    yAxis: [
      {
        type: 'value',
        name: '单量',
        axisLabel: { color: '#94a3b8' },
        splitLine: { lineStyle: { color: 'rgba(148,163,184,0.18)' } },
      },
      {
        type: 'value',
        name: '质量占比 %',
        max: (value: { max: number }) => Math.max(30, Math.ceil(value.max * 1.2)),
        axisLabel: { color: '#94a3b8' },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '当前问题单量',
        type: 'bar',
        barWidth,
        data: brands.map((item) => item.quality),
        itemStyle: { color: '#0f766e', borderRadius: [6, 6, 0, 0] },
      },
      {
        name: '质量占比',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        symbolSize: 8,
        data: brands.map((item) => item.quality_rate),
        lineStyle: { color: '#d97706', width: 3 },
        itemStyle: { color: '#d97706' },
      },
    ],
  }
})

const categoryOption = computed<Record<string, unknown>>(() => {
  const categories = payload.value?.categories ?? []
  const chartBrands = visibleChartBrands.value
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { top: 0, type: 'scroll', data: chartBrands },
    grid: { left: 12, right: 24, top: 42, bottom: 24, containLabel: true },
    xAxis: {
      type: 'value',
      axisLabel: { color: '#94a3b8' },
      splitLine: { lineStyle: { color: 'rgba(148,163,184,0.18)' } },
    },
    yAxis: {
      type: 'category',
      inverse: true,
      data: categories.map((item) => item.category),
      axisLabel: { color: '#475569', width: 100, overflow: 'truncate' },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: chartBrands.map((brand, index) => ({
      name: brand,
      type: 'bar',
      stack: 'total',
      barWidth: 18,
      data: categories.map((item) => item.brands[brand] ?? 0),
      itemStyle: {
        color: BRAND_COLORS[index % BRAND_COLORS.length],
        borderRadius: [0, 0, 0, 0],
      },
    })),
  }
})

const trendOption = computed<Record<string, unknown>>(() => {
  const trend = payload.value?.trend ?? []
  const dates = trend.map((item) => item.date.slice(5))
  const chartBrands = visibleChartBrands.value
  return {
    tooltip: { trigger: 'axis' },
    legend: { top: 0, type: 'scroll', data: [...chartBrands, '合计'] },
    grid: { left: 44, right: 24, top: 42, bottom: 30 },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: dates,
      axisLabel: { color: '#94a3b8' },
      axisLine: { lineStyle: { color: '#cbd5e1' } },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: '#94a3b8' },
      splitLine: { lineStyle: { color: 'rgba(148,163,184,0.18)' } },
    },
    series: [
      ...chartBrands.map((brand, index) => {
        const color = BRAND_COLORS[index % BRAND_COLORS.length]
        return {
          name: brand,
          type: 'line',
          smooth: true,
          symbolSize: 6,
          data: trend.map((item) => item.brands[brand] ?? 0),
          lineStyle: { color, width: 3 },
          itemStyle: { color },
          areaStyle: { color, opacity: 0.08 },
        }
      }),
      {
        name: '合计',
        type: 'line',
        smooth: true,
        symbolSize: 5,
        data: trend.map((item) => item.total),
        lineStyle: { color: '#64748b', width: 2, type: 'dashed' },
        itemStyle: { color: '#64748b' },
      },
    ],
  }
})

const scopeDetails = computed(() => {
  const details = payload.value?.details ?? []
  if (problemScope.value === 'quality') return details.filter((row) => row.is_quality)
  if (problemScope.value === 'non_quality') return details.filter((row) => !row.is_quality)
  return details
})

const filteredDetails = computed(() => {
  const details = scopeDetails.value
  const tokens = appliedSearchText.value
    .split(/[\s,，;；]+/)
    .map((token) => token.trim())
    .filter(Boolean)
  if (!tokens.length) return details
  return details.filter((row) =>
    tokens.some((token) =>
      [
        row.service_no,
        row.order_no,
        row.product_name,
        row.customer_desc,
        row.reason1,
        row.reason2,
      ].some((value) => String(value).includes(token)),
    ),
  )
})

const detailPanelTitle = computed(() => {
  if (problemScope.value === 'quality') return '质量问题明细'
  if (problemScope.value === 'non_quality') return '非质量问题明细'
  return '售后问题明细'
})

const tableCountText = computed(() => {
  const current = filteredDetails.value.length
  if (problemScope.value === 'quality') {
    return `质量问题 ${current} 条 / 全部售后 ${meta.value.after_sales_total} 条`
  }
  if (problemScope.value === 'non_quality') {
    return `非质量问题 ${current} 条 / 全部售后 ${meta.value.after_sales_total} 条`
  }
  if (appliedSearchText.value.trim()) {
    return `全部问题 ${current} 条 / 全部售后 ${meta.value.after_sales_total} 条`
  }
  return `全部问题 ${current} 条（质量 ${meta.value.quality_total} / 非质量 ${meta.value.non_quality_total}）`
})

const pagedDetails = computed(() => {
  const start = (detailPage.value - 1) * detailPageSize.value
  return filteredDetails.value.slice(start, start + detailPageSize.value)
})

watch(searchText, () => {
  appliedSearchText.value = searchText.value.trim()
  detailPage.value = 1
})

watch(problemScope, () => {
  detailPage.value = 1
})

watch(brandFilter, () => {
  storeFilter.value = ''
  categoryFilter.value = ''
})

watch(
  [brandFilter, storeFilter, categoryFilter, dateRange, problemScope],
  () => {
    void fetchData()
  },
)

const fetchData = async () => {
  loading.value = true
  try {
    const params: Record<string, unknown> = {}
    if (brandFilter.value.length) params.brand = brandFilter.value.join(',')
    if (storeFilter.value) params.store = storeFilter.value
    if (categoryFilter.value) params.category = categoryFilter.value
    params.problem_scope = problemScope.value
    if (dateRange.value.length === 2) {
      params.start_date = dateRange.value[0]
      params.end_date = dateRange.value[1]
    }
    const data = await request.get('/after-sales/quality-dashboard', {
      params,
    }) as DashboardPayload
    payload.value = data
    detailPage.value = 1
  } finally {
    loading.value = false
  }
}

const formatMoney = (value: number) =>
  `¥${Number(value || 0).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`

const categoryTone = (category: string) => {
  if (['拉链/拉头', '拉杆/轮子', '肩带/配件'].includes(category)) return 'part'
  if (category === '做工/缝制/材质') return 'craft'
  if (category === '破损/物流') return 'damage'
  if (category === '功能/使用故障') return 'function'
  if (category === '描述/预期不符') return 'desc'
  return 'other'
}

const brandTagType = (brand: string) => {
  if (brand === '测试旅行') return 'success'
  if (brand === '测试箱包') return 'warning'
  return 'info'
}

const riskTone = (rate: number) => {
  if (rate >= 15) return 'danger'
  if (rate >= 8) return 'warning'
  return 'success'
}

const exportExcel = () => {
  const rows = filteredDetails.value
  if (!rows.length) {
    ElMessage.warning('当前筛选下没有可导出的明细')
    return
  }
  const sheetRows = rows.map((row) => ({
    服务单号: row.service_no,
    订单号: row.order_no,
    申请时间: row.apply_time,
    品牌: row.brand,
    店铺收货主体: row.store_name,
    商品编号: row.product_no,
    商品名称: row.product_name,
    类型: row.is_quality ? '质量问题' : '非质量问题',
    问题类型: row.category,
    一级申请原因: row.reason1,
    二级申请原因: row.reason2,
    客户问题描述: row.customer_desc,
    一级客户问题: row.customer1,
    二级客户问题: row.customer2,
    审核意见: row.audit_opinion,
    处理结果: row.handle_result,
    退款金额: row.refund_amount,
    售后时长小时: row.duration_hours,
  }))
  const worksheet = XLSX.utils.json_to_sheet(sheetRows)
  const workbook = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(workbook, worksheet, '问题明细')
  XLSX.writeFile(
    workbook,
    `售后问题分析_${brandFilter.value.join('_') || '全部'}_${new Date().toISOString().slice(0, 10)}.xlsx`,
  )
}

const handleSearch = () => {
  appliedSearchText.value = searchText.value.trim()
  detailPage.value = 1
}

onMounted(() => {
  void fetchData()
})
</script>

<template>
  <div v-loading="loading" class="quality-dashboard">
    <section class="dashboard-head">
      <div class="dashboard-title">
        <h1>售后质量分析</h1>
        <p class="dashboard-meta">
          {{ meta.date_min }} 至 {{ meta.date_max }} · {{ meta.source_name }}
        </p>
      </div>
      <div class="head-actions">
        <el-button :icon="Refresh" circle title="刷新数据" @click="fetchData" />
      </div>
    </section>

    <section class="filter-bar">
      <el-select
        v-model="brandFilter"
        multiple
        collapse-tags
        collapse-tags-tooltip
        clearable
        filterable
        placeholder="全部品牌"
        class="filter-control"
      >
        <el-option
          v-for="brand in brandOptions"
          :key="brand"
          :label="brand"
          :value="brand"
        />
      </el-select>

      <el-select
        v-model="storeFilter"
        placeholder="全部店铺 / 收货主体"
        clearable
        class="filter-control"
      >
        <el-option
          v-for="store in storeOptions"
          :key="store"
          :label="store"
          :value="store"
        />
      </el-select>

      <el-select
        v-model="categoryFilter"
        placeholder="全部问题类型"
        clearable
        class="filter-control"
      >
        <el-option
          v-for="category in categoryOptions"
          :key="category"
          :label="category"
          :value="category"
        />
      </el-select>

      <el-radio-group v-model="problemScope" size="large" class="scope-switch">
        <el-radio-button value="all">全部问题</el-radio-button>
        <el-radio-button value="quality">质量问题</el-radio-button>
        <el-radio-button value="non_quality">非质量问题</el-radio-button>
      </el-radio-group>

      <el-date-picker
        v-model="dateRange"
        type="daterange"
        value-format="YYYY-MM-DD"
        :disabled-date="disabledDate"
        clearable
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        class="filter-control date-filter"
      />

    </section>

    <section class="kpi-grid">
      <div
        v-for="item in kpiItems"
        :key="item.label"
        class="kpi-cell"
        :class="`kpi-${item.tone}`"
      >
        <span class="kpi-label">{{ item.label }}</span>
        <strong class="kpi-value">
          {{ item.value }}<small v-if="item.unit">{{ item.unit }}</small>
        </strong>
        <span class="kpi-sub">{{ item.sub }}</span>
      </div>
    </section>

    <section class="chart-grid">
      <div class="chart-panel">
        <div class="panel-title">品牌问题对比</div>
        <VChart :option="brandOption" autoresize class="chart" />
      </div>
      <div class="chart-panel">
        <div class="panel-title">问题类型</div>
        <VChart :option="categoryOption" autoresize class="chart" />
      </div>
      <div class="chart-panel chart-panel-full">
        <div class="panel-title">问题趋势</div>
        <VChart :option="trendOption" autoresize class="chart chart-tall" />
      </div>
    </section>

    <section class="panel">
      <div class="table-head">
        <div class="panel-title">问题集中商品</div>
        <span class="table-count">{{ topProducts.length }} 款</span>
      </div>
      <el-table :data="topProducts" class="quality-table">
        <el-table-column
          prop="product_name"
          label="商品"
          min-width="320"
          show-overflow-tooltip
        />
        <el-table-column prop="after_sales" label="售后单量" width="110" align="right" />
        <el-table-column
          v-if="problemScope === 'all'"
          prop="quality_count"
          label="质量问题单"
          width="110"
          align="right"
        />
        <el-table-column
          v-if="problemScope === 'all'"
          prop="non_quality_count"
          label="非质量问题单"
          width="120"
          align="right"
        />
        <el-table-column
          v-else-if="problemScope === 'quality'"
          prop="quality"
          label="质量问题单"
          width="110"
          align="right"
        />
        <el-table-column
          v-else
          prop="quality"
          label="非质量问题单"
          width="120"
          align="right"
        />
        <el-table-column prop="quality_rate" label="质量占比" width="110" align="right">
          <template #default="{ row }">
            <el-tag :type="riskTone(row.quality_rate)" effect="light">
              {{ row.quality_rate.toFixed(2) }}%
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section class="panel">
      <div class="table-head">
        <div class="table-title-group">
          <div class="panel-title">{{ detailPanelTitle }}</div>
          <span class="table-count">{{ tableCountText }}</span>
        </div>
        <div class="detail-search">
          <el-input
            v-model="searchText"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            placeholder="粘贴多个服务单号，空格 / 换行分隔"
            clearable
            class="detail-search-input"
            @keydown.enter.exact.prevent="handleSearch"
            @clear="handleSearch"
          />
          <el-button type="primary" :icon="Search" @click="handleSearch">
            搜索
          </el-button>
          <el-button type="primary" :icon="Download" @click="exportExcel">
            导出明细
          </el-button>
        </div>
      </div>
      <el-table :data="pagedDetails" class="quality-table">
        <el-table-column type="index" label="#" width="52" />
        <el-table-column prop="apply_time" label="申请时间" width="156" />
        <el-table-column prop="service_no" label="服务单号" width="126" />
        <el-table-column prop="brand" label="品牌" width="88">
          <template #default="{ row }">
            <el-tag :type="brandTagType(row.brand)">{{ row.brand }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_quality" label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_quality ? 'danger' : 'info'" effect="light">
              {{ row.is_quality ? '质量问题' : '非质量问题' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="store_name"
          label="店铺 / 收货主体"
          width="190"
          show-overflow-tooltip
        />
        <el-table-column
          prop="product_name"
          label="商品"
          min-width="280"
          show-overflow-tooltip
        />
        <el-table-column prop="category" label="问题类型" width="140">
          <template #default="{ row }">
            <el-tag
              class="category-tag"
              :class="`category-${categoryTone(row.category)}`"
              effect="plain"
            >
              {{ row.category }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="reason1" label="一级申请原因" width="150" />
        <el-table-column prop="reason2" label="二级申请原因" width="130" />
        <el-table-column
          prop="customer_desc"
          label="问题描述"
          min-width="240"
          show-overflow-tooltip
        />
        <el-table-column prop="refund_amount" label="退款金额" width="120" align="right">
          <template #default="{ row }">{{ formatMoney(row.refund_amount) }}</template>
        </el-table-column>
        <el-table-column prop="duration_hours" label="时长(H)" width="96" align="right" />
      </el-table>
      <div class="pagination-row">
        <el-pagination
          v-model:current-page="detailPage"
          v-model:page-size="detailPageSize"
          background
          layout="total, sizes, prev, pager, next"
          :total="filteredDetails.length"
          :page-sizes="[10, 20, 50, 100]"
        />
      </div>
    </section>
  </div>
</template>

<style scoped>
.quality-dashboard {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 16px;
  padding: 18px;
}

.dashboard-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.dashboard-title h1 {
  margin: 0;
  color: var(--text-heading);
  font-size: 22px;
  line-height: 1.3;
  letter-spacing: 0;
}

.dashboard-meta {
  margin: 6px 0 0;
  color: var(--text-muted);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.head-actions {
  display: flex;
  gap: 10px;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.filter-control {
  width: 220px;
}

.date-filter {
  width: 280px;
}

.search-filter {
  width: 280px;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.kpi-cell {
  display: flex;
  min-height: 96px;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  padding: 14px 16px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--app-surface);
}

.kpi-label {
  color: var(--text-secondary);
  font-size: 13px;
}

.kpi-value {
  color: var(--text-heading);
  font-size: 22px;
  line-height: 1.2;
  letter-spacing: 0;
}

.kpi-value small {
  margin-left: 4px;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 400;
}

.kpi-sub {
  color: var(--text-muted);
  font-size: 12px;
}

.kpi-danger .kpi-value {
  color: light-dark(#b91c1c, #fca5a5);
}

.kpi-warning .kpi-value {
  color: light-dark(#b45309, #fbbf24);
}

.kpi-accent .kpi-value {
  color: var(--primary);
}

.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.chart-panel,
.panel {
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--app-surface);
}

.chart-panel-full {
  grid-column: 1 / -1;
}

.panel-title {
  margin-bottom: 12px;
  color: var(--text-heading);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0;
}

.chart {
  width: 100%;
  height: 280px;
}

.chart-tall {
  height: 300px;
}

.table-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.table-head .panel-title {
  margin: 0;
}

.table-title-group {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.table-count {
  color: var(--text-muted);
  font-size: 12px;
}

.detail-search {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 560px;
}

.detail-search-input {
  flex: 1;
}

.quality-table {
  width: 100%;
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
  padding-top: 14px;
}

.category-tag {
  border: 0;
}

.category-part {
  color: light-dark(#0f766e, var(--text-accent));
  background: rgba(15, 118, 110, 0.1);
}

.category-craft {
  color: light-dark(#6d28d9, #c4b5fd);
  background: rgba(109, 40, 217, 0.1);
}

.category-damage {
  color: light-dark(#b91c1c, #fca5a5);
  background: rgba(185, 28, 28, 0.1);
}

.category-function {
  color: light-dark(#0e7490, var(--text-accent));
  background: rgba(14, 116, 144, 0.1);
}

.category-desc {
  color: light-dark(#b45309, #fbbf24);
  background: rgba(180, 83, 9, 0.1);
}

.category-other {
  color: light-dark(#475569, var(--text-secondary));
  background: rgba(71, 85, 105, 0.1);
}

@media (max-width: 1100px) {
  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .chart-grid {
    grid-template-columns: 1fr;
  }

  .chart-panel-full {
    grid-column: auto;
  }

  .table-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .detail-search {
    width: 100%;
  }
}

@media (max-width: 640px) {
  .quality-dashboard {
    padding: 12px;
  }

  .kpi-grid {
    grid-template-columns: 1fr;
  }

  .filter-control,
  .date-filter {
    width: 100%;
  }

  .detail-search {
    min-width: 0;
    flex-direction: column;
  }

  .detail-search .el-button {
    width: 100%;
  }
}
</style>
