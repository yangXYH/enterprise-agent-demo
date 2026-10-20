<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElAlert, ElButton, ElDatePicker, ElEmpty, ElOption, ElSelect, ElTag } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart, PieChart, ScatterChart, TreemapChart } from 'echarts/charts'
import { DataZoomComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { compactNumber } from './operatingCharts'

use([CanvasRenderer, BarChart, LineChart, PieChart, ScatterChart, TreemapChart, DataZoomComponent, GridComponent, LegendComponent, TooltipComponent])

type Row = Record<string, any>
type View = 'overview' | 'trend' | 'category' | 'brand'
const props = defineProps<{ view: View }>()
const names: Record<View, string> = { overview: '经营驾驶舱', trend: '经营脉搏', category: '品类增长地图', brand: '品牌与商品矩阵' }
const subtitles: Record<View, string> = {
  overview: '先看经营结果，再定位增长来源和异常信号。',
  trend: '把每天的成交、流量和数据完整度放在同一时间轴上。',
  category: '看清哪些品类撑起规模，哪些正在拉动或拖累变化。',
  brand: '识别品牌集中度，以及高流量、低成交的商品机会。',
}
const meta = ref<Row>({ dates: [], brands: [], categories: [] })
const board = ref<Row | null>(null)
const range = ref<string[]>([])
const brand = ref('')
const category = ref('')
const granularity = ref<'day' | 'month'>('day')
const loading = ref(false)
const error = ref('')
let requestId = 0

const yuan = (n: any) => n == null ? '—' : Number(n).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const count = (n: any) => n == null ? '—' : Number(n).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
const rate = (n: any) => n == null ? '不可比' : `${n > 0 ? '+' : ''}${(n * 100).toFixed(1)}%`
const moneyShort = (n: number) => Math.abs(n) >= 100000000 ? `${(n / 100000000).toFixed(2)}亿` : Math.abs(n) >= 10000 ? `${(n / 10000).toFixed(1)}万` : yuan(n)
const escapeHtml = (value: unknown) => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char] || char)
const ratio = (part: number, total: number) => total > 0 && part > 0 ? part / total : null
const sharePercent = (part: number, total: number) => ratio(part, total) == null ? '—' : `${(ratio(part, total)! * 100).toFixed(1)}%`
const latest = computed(() => meta.value.dates.at(-1) || '')
const summary = computed<Row>(() => board.value?.summary || {})
const coverage = computed<Row>(() => board.value?.coverage || {})
const monthComparable = computed(() => !!board.value?.comparisons.mom.comparable)
const positiveCategories = computed<Row[]>(() => (board.value?.categories || []).filter((r: Row) => r.revenue > 0))
const positiveBrands = computed<Row[]>(() => (board.value?.brands || []).filter((r: Row) => r.revenue > 0))
const topCategories = computed<Row[]>(() => (board.value?.categories || []).slice(0, 7))
const topBrands = computed<Row[]>(() => (board.value?.brands || []).slice(0, 8))
const oldCategoryMap = computed(() => new Map<string, Row>((board.value?.previous_dimensions.categories || []).map((r: Row) => [r.label, r])))
const categoryDelta = computed<Row[]>(() => {
  if (!monthComparable.value) return []
  const combined = new Map<string, Row>()
  for (const row of board.value?.categories || []) combined.set(row.label, { label: row.label, current: row.revenue, previous: 0 })
  for (const row of board.value?.previous_dimensions.categories || []) {
    const item = combined.get(row.label) || { label: row.label, current: 0, previous: 0 }
    item.previous = row.revenue
    combined.set(row.label, item)
  }
  return [...combined.values()].map(row => ({ ...row, delta: row.current - row.previous }))
    .filter(row => row.delta !== 0).sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
})
const categoryGrowth = computed<Row[]>(() => monthComparable.value
  ? (board.value?.categories || []).map((row: Row) => ({ ...row, previous: oldCategoryMap.value.get(row.label)?.revenue || 0 }))
    .filter((row: Row) => row.revenue > 0 && row.previous > 0)
    .map((row: Row) => ({ ...row, growth: (row.revenue - row.previous) / Math.abs(row.previous) }))
  : [])

async function read(path: string) {
  const response = await fetch(`/api/operating-analysis${path}`, { credentials: 'same-origin' })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    if (response.status === 404 && path.startsWith('/insights')) throw new Error('经营驾驶舱接口未加载，请重启后端服务后刷新页面。')
    throw new Error(payload.detail || payload.message || `数据读取失败（${response.status}）`)
  }
  return payload
}
async function load() {
  if (range.value.length !== 2) return
  const id = ++requestId
  loading.value = true; error.value = ''; board.value = null
  try {
    const query = new URLSearchParams({ start: range.value[0], end: range.value[1], brand: brand.value, category: category.value })
    const result = await read(`/insights?${query}`)
    if (id === requestId) board.value = result
  } catch (e: any) { if (id === requestId) error.value = e.message }
  finally { if (id === requestId) loading.value = false }
}
function reset() {
  brand.value = ''; category.value = ''
  if (latest.value) range.value = [`${latest.value.slice(0, 7)}-01`, latest.value]
}
function chooseCategory(event: Row) {
  const label = String(event?.name || '')
  if (label && label !== '其他品类' && meta.value.categories.includes(label)) category.value = label
}
onMounted(async () => {
  try { meta.value = await read('/metadata'); reset() }
  catch (e: any) { error.value = e.message }
})
watch([range, brand, category], () => { void load() }, { deep: true })

const days = computed<Row[]>(() => {
  if (!board.value) return []
  const actual = new Map<string, Row>(board.value.trend.map((r: Row) => [r.day, r]))
  const loaded = new Set<string>(meta.value.dates)
  const result: Row[] = []
  const start = Date.parse(`${board.value.filters.start}T00:00:00Z`)
  const end = Date.parse(`${board.value.filters.end}T00:00:00Z`)
  for (let date = start; date <= end; date += 86400000) {
    const day = new Date(date).toISOString().slice(0, 10)
    result.push(actual.get(day) || (loaded.has(day) ? { day, revenue: 0, visitors: 0, quantity: 0, customers: 0 } : { day, missing: true }))
  }
  return result
})
const timeline = computed<Row[]>(() => {
  if (granularity.value === 'day') return days.value
  const monthly = new Map<string, Row>()
  for (const row of days.value) {
    const key = row.day.slice(0, 7)
    const item = monthly.get(key) || { day: key, revenue: 0, visitors: 0, quantity: 0, customers: 0, hasData: false }
    if (!row.missing) {
      item.hasData = true
      for (const metric of ['revenue', 'visitors', 'quantity', 'customers']) item[metric] += row[metric] || 0
    }
    monthly.set(key, item)
  }
  return [...monthly.values()].map(row => ({ ...row, missing: !row.hasData }))
})
const heatDays = computed(() => days.value.slice(-42))
const heatOffset = computed(() => heatDays.value.length ? (new Date(`${heatDays.value[0].day}T00:00:00Z`).getUTCDay() + 6) % 7 : 0)
const heatValues = computed(() => heatDays.value.filter(r => !r.missing && r.revenue > 0).map(r => r.revenue).sort((a, b) => a - b))
const heatColor = (row: Row) => {
  if (row.missing) return '#d5dfe3'
  if (row.revenue <= 0) return '#eef4f3'
  // Rank colors distinguish close daily values better than a zero-based opacity scale.
  const values = heatValues.value
  const rank = values.findIndex(value => value >= row.revenue)
  return ['#d6eee7', '#99d5c5', '#5bbca9', '#198e7d', '#075f59'][Math.min(4, Math.floor(rank / Math.max(1, values.length) * 5))]
}
const heatSummary = computed(() => {
  const valid = heatDays.value.filter(row => !row.missing)
  const peak = valid.reduce<Row | null>((best, row) => !best || row.revenue > best.revenue ? row : best, null)
  const low = valid.reduce<Row | null>((best, row) => !best || row.revenue < best.revenue ? row : best, null)
  return { peak, low, average: valid.length ? valid.reduce((total, row) => total + row.revenue, 0) / valid.length : null }
})

const categoryColors = ['#0c7e76', '#118f82', '#23a096', '#3aafa1', '#5bb9aa', '#177f91', '#468da3', '#78a6ad', '#85b7b7', '#9acac0', '#b8d3d0']
const treeItems = computed(() => {
  const items = positiveCategories.value
  const nodes = items.slice(0, 10).map((row, index) => ({ name: row.label || '未分类', value: row.revenue, itemStyle: { color: categoryColors[index] } }))
  const rest = items.slice(10).reduce((sum, row) => sum + row.revenue, 0)
  if (rest > 0) nodes.push({ name: '其他品类', value: rest, itemStyle: { color: categoryColors[10] } })
  return nodes
})

const commonGrid = { left: 68, right: 60, top: 42, bottom: 68 }
const trendOption = computed(() => ({
  color: ['#0d8978', '#e6aa50'],
  tooltip: { trigger: 'axis', renderMode: 'richText' },
  legend: { show: false },
  grid: { ...commonGrid, top: 20, right: 76 },
  xAxis: { type: 'category', data: timeline.value.map(r => r.day), axisLabel: { color: '#718796', hideOverlap: true }, axisLine: { lineStyle: { color: '#dbe7e8' } } },
  yAxis: [
    { type: 'value', name: '元', axisLabel: { formatter: compactNumber }, splitLine: { lineStyle: { type: 'dashed', color: '#e7eeee' } } },
    { type: 'value', axisLabel: { formatter: compactNumber }, splitLine: { show: false } },
  ],
  dataZoom: timeline.value.length > 32 ? [{ type: 'inside' }, { type: 'slider', height: 16, bottom: 12 }] : [],
  series: [
    { name: '成交金额', type: 'bar', barMaxWidth: 26, itemStyle: { borderRadius: [4, 4, 0, 0] }, data: timeline.value.map(r => r.missing ? null : r.revenue) },
    { name: '商品访客合计', type: 'line', yAxisIndex: 1, smooth: .22, connectNulls: false, showSymbol: timeline.value.length < 24,
      lineStyle: { width: 3 }, data: timeline.value.map(r => r.missing ? null : r.visitors) },
  ],
}))
const categoryTreeOption = computed(() => {
  const total = treeItems.value.reduce((sum, row) => sum + row.value, 0)
  return { tooltip: { confine: true, formatter: (p: Row) => `${escapeHtml(p.name)}<br/>成交金额 ¥${yuan(p.value)}` },
    series: [{ type: 'treemap', left: 0, top: 0, right: 0, bottom: 0, roam: false, nodeClick: false, breadcrumb: { show: false }, visibleMin: 1,
      label: { show: true, formatter: (p: Row) => {
        const share = Number(p.value || 0) / total
        const name = String(p.name || '未分类')
        if (share >= .02) return `${name.length > 6 ? `${name.slice(0, 6)}…` : name}\n¥${moneyShort(Number(p.value || 0))}`
        return name.length > (share >= .01 ? 4 : 2) ? `${name.slice(0, share >= .01 ? 4 : 2)}…` : name
      }, color: '#fff', fontSize: 12, lineHeight: 18, overflow: 'truncate' },
      upperLabel: { show: false }, itemStyle: { borderColor: '#fff', borderWidth: 4, gapWidth: 2, borderRadius: 5 }, data: treeItems.value }] }
})
const comparisonOption = computed(() => {
  const rows = [
    { label: '上年同期', value: board.value?.comparisons.yoy.summary.revenue || 0, color: '#b7c8cc' },
    { label: '上月同期', value: board.value?.comparisons.mom.summary.revenue || 0, color: '#8db8b1' },
    { label: '本期', value: summary.value.revenue || 0, color: '#0d8978' },
  ]
  return { tooltip: { trigger: 'axis', formatter: (params: Row[]) => params.map(p => `${p.name} ¥${yuan(p.value)}`).join('<br/>') },
    grid: { left: 82, right: 60, top: 12, bottom: 35 }, xAxis: { type: 'value', axisLabel: { formatter: compactNumber } },
    yAxis: { type: 'category', data: rows.map(r => r.label), axisTick: { show: false }, axisLine: { show: false } },
    series: [{ type: 'bar', barWidth: 24, data: rows.map(r => ({ value: r.value, itemStyle: { color: r.color, borderRadius: [0, 6, 6, 0] } })) }] }
})
const deltaOption = computed(() => {
  const rows = categoryDelta.value.slice(0, 10).reverse()
  return { tooltip: { trigger: 'axis', formatter: (params: Row[]) => params.map(p => `${p.name} ${p.value > 0 ? '+' : ''}¥${yuan(p.value)}`).join('<br/>') },
    grid: { left: 132, right: 68, top: 18, bottom: 40 },
    xAxis: { type: 'value', axisLabel: { formatter: compactNumber }, splitLine: { lineStyle: { type: 'dashed', color: '#e7eeee' } } },
    yAxis: { type: 'category', data: rows.map(r => r.label || '未分类'), axisLabel: { width: 114, overflow: 'truncate' } },
    series: [{ type: 'bar', barMaxWidth: 22, data: rows.map(r => ({ value: r.delta,
      itemStyle: { color: r.delta >= 0 ? '#0d8978' : '#dd806c', borderRadius: r.delta >= 0 ? [0, 5, 5, 0] : [5, 0, 0, 5] } })) }] }
})
const growthOption = computed(() => ({
  tooltip: { trigger: 'item', confine: true, extraCssText: 'max-width:320px;white-space:normal;overflow-wrap:anywhere;', formatter: (p: Row) => {
    const [growth, revenue, skuCount] = p.value || p.data?.value || []
    return `${escapeHtml(p.name)}<br/>成交金额 ¥${yuan(revenue)}<br/>环比 ${rate(growth)}<br/>SKU 数 ${count(skuCount)}`
  } },
  grid: { left: 64, right: 35, top: 35, bottom: 52 },
  xAxis: { type: 'value', name: '环比增长', axisLabel: { formatter: (n: number) => `${(n * 100).toFixed(0)}%` }, splitLine: { lineStyle: { type: 'dashed' } } },
  yAxis: { type: 'value', name: '成交金额', axisLabel: { formatter: compactNumber }, splitLine: { lineStyle: { type: 'dashed' } } },
  series: [{ type: 'scatter', data: categoryGrowth.value.map((r: Row) => ({ name: r.label || '未分类', value: [r.growth, r.revenue, r.sku_count],
    itemStyle: { color: r.growth >= 0 ? '#0d8978' : '#dd806c', opacity: .78 } })),
    symbolSize: (value: number[]) => Math.max(13, Math.min(47, 12 + Math.sqrt(value[2] || 0) * 2.5)) }],
}))
const brandDonutOption = computed(() => {
  const rows = positiveBrands.value
  const rest = rows.slice(6).reduce((sum, row) => sum + row.revenue, 0)
  const values = rows.slice(0, 6).map(row => ({ name: row.label || '待识别', value: row.revenue }))
  if (rest > 0) values.push({ name: '其他品牌', value: rest })
  return { color: ['#0d8978', '#2ba99a', '#e4b35f', '#537e9b', '#8eb9b4', '#d78577', '#cedbd9'],
    tooltip: { trigger: 'item', formatter: (p: Row) => `${p.name}<br/>¥${yuan(p.value)}（${p.percent}%）` },
    legend: { bottom: 0, type: 'scroll' },
    series: [{ type: 'pie', radius: ['54%', '76%'], center: ['50%', '42%'], label: { show: false }, itemStyle: { borderColor: '#fff', borderWidth: 3 }, data: values }] }
})
const productScatterOption = computed(() => ({
  tooltip: { trigger: 'item', confine: true, extraCssText: 'max-width:320px;white-space:normal;overflow-wrap:anywhere;', formatter: (p: Row) => {
    const [visitors, revenue, quantity] = p.value || p.data?.value || []
    return `${escapeHtml(p.name)}<br/>商品访客合计 ${count(visitors)}<br/>成交金额 ¥${yuan(revenue)}<br/>成交件数 ${count(quantity)}`
  } },
  grid: { left: 76, right: 30, top: 28, bottom: 55 },
  xAxis: { type: 'value', name: '商品访客合计', nameLocation: 'middle', nameGap: 33, axisLabel: { formatter: compactNumber }, splitLine: { lineStyle: { type: 'dashed' } } },
  yAxis: { type: 'value', name: '成交金额', axisLabel: { formatter: compactNumber }, splitLine: { lineStyle: { type: 'dashed' } } },
  series: [{ type: 'scatter', data: (board.value?.products || []).map((row: Row) => ({ name: row.name || row.label,
    value: [row.visitors, row.revenue, row.quantity], itemStyle: { color: row.revenue < 0 ? '#dd806c' : '#0d8978', opacity: .7 } })),
    symbolSize: (value: number[]) => Math.max(11, Math.min(45, 10 + Math.sqrt(Math.max(0, value[2] || 0)) * 1.7)) }],
}))
const productRankOption = computed(() => {
  const rows = (board.value?.products || []).slice(0, 10).reverse()
  return { tooltip: { trigger: 'axis', formatter: (params: Row[]) => params.map(p => `${p.name}<br/>¥${yuan(p.value)}`).join('<br/>') },
    grid: { left: 158, right: 75, top: 12, bottom: 36 },
    xAxis: { type: 'value', axisLabel: { formatter: compactNumber }, splitLine: { lineStyle: { type: 'dashed' } } },
    yAxis: { type: 'category', data: rows.map((r: Row) => r.name || r.label), axisLabel: { width: 140, overflow: 'truncate' } },
    series: [{ type: 'bar', barMaxWidth: 22, data: rows.map((r: Row, index: number) => ({ value: r.revenue,
      itemStyle: { color: index === rows.length - 1 ? '#0d8978' : '#8ac8bd', borderRadius: [0, 5, 5, 0] } })) }] }
})
const signals = computed<Row[]>(() => {
  if (!board.value) return []
  const messages: Row[] = []
  if (!coverage.value.complete) messages.push({ tone: 'warn', title: '数据覆盖未完成', detail: `当前区间缺少 ${coverage.value.missing_dates.length} 天，增长率暂停比较。` })
  const top = positiveCategories.value[0]
  if (top && summary.value.revenue > 0) messages.push({ tone: 'normal', title: '最大收入来源', detail: `${top.label || '未分类'}贡献 ¥${moneyShort(top.revenue)}，占净成交额 ${sharePercent(top.revenue, summary.value.revenue)}。` })
  const biggestLoss = [...categoryDelta.value].filter(r => r.delta < 0).sort((a, b) => a.delta - b.delta)[0]
  if (biggestLoss) messages.push({ tone: 'warn', title: '主要下滑品类', detail: `${biggestLoss.label || '未分类'}较上月同期少 ¥${moneyShort(Math.abs(biggestLoss.delta))}。` })
  const biggestGain = [...categoryDelta.value].filter(r => r.delta > 0).sort((a, b) => b.delta - a.delta)[0]
  if (biggestGain) messages.push({ tone: 'good', title: '主要增长品类', detail: `${biggestGain.label || '未分类'}较上月同期多 ¥${moneyShort(biggestGain.delta)}。` })
  if (!messages.length) messages.push({ tone: 'normal', title: '等待可比数据', detail: '继续积累完整日期后可呈现增长贡献。' })
  return messages.slice(0, 3)
})
</script>

<template>
  <section class="board" :aria-busy="loading">
    <header class="masthead">
      <div><span class="eyebrow">DATA INTELLIGENCE / 运营部商品日明细</span><h1>{{ names[props.view] }}</h1><p>{{ subtitles[props.view] }}</p></div>
      <div class="masthead-side"><span>数据截止 {{ latest || '—' }}</span></div>
    </header>

    <div class="filterbar"><label>统计日期<el-date-picker v-model="range" type="daterange" value-format="YYYY-MM-DD" :clearable="false" start-placeholder="开始日期" end-placeholder="结束日期" /></label><label>品牌<el-select v-model="brand" filterable clearable placeholder="全部品牌"><el-option v-for="item in meta.brands" :key="item" :label="item" :value="item" /></el-select></label><label>三级类目<el-select v-model="category" filterable clearable placeholder="全部类目"><el-option v-for="item in meta.categories" :key="item" :label="item || '未分类'" :value="item" /></el-select></label><el-button @click="reset">重置</el-button><el-button :loading="loading" @click="load">刷新</el-button></div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" class="error" />
    <div v-if="loading" class="loading">正在构建经营视图…</div>
    <el-empty v-else-if="!meta.dates.length && !error" description="暂无经营数据，请先在运营部导入月报" />

    <template v-if="board && summary.row_count">
      <div class="scope"><span>{{ board.filters.start }} 至 {{ board.filters.end }}</span><span>{{ coverage.available_days }}/{{ coverage.expected_days }} 个日期有源记录</span><span>{{ count(summary.row_count) }} 条商品日明细</span><span>{{ brand || '全部品牌' }} / {{ category || '全部类目' }}</span></div>
      <el-alert v-if="!coverage.complete" type="warning" :closable="false" class="error" :title="`有 ${coverage.missing_dates.length} 天缺少源报表，趋势保留空档，同比环比不输出增长率。`" />

      <template v-if="props.view === 'overview'">
        <div class="hero-grid"><section class="revenue-hero"><div class="hero-top"><span>本期成交金额</span><span class="hero-accent">核心结果</span></div><div class="hero-number"><small>¥</small>{{ moneyShort(summary.revenue) }}</div><div class="hero-exact">精确金额 ¥{{ yuan(summary.revenue) }}</div><div class="hero-comparison"><span>同比 <strong>{{ rate(board.comparisons.yoy.rates.revenue) }}</strong></span><span>环比 <strong>{{ rate(board.comparisons.mom.rates.revenue) }}</strong></span></div><div class="hero-bottom">{{ count(summary.sku_count) }} 个 SKU · {{ count(summary.quantity) }} 件成交商品</div></section>
          <section class="metric-stack"><div><span>商品访客合计</span><strong>{{ count(summary.visitors) }}</strong><small>商品日求和，非独立访客</small></div><div><span>成交客户合计</span><strong>{{ count(summary.customers) }}</strong><small>商品日求和，非独立客户</small></div><div><span>访客转化代理值</span><strong>{{ summary.conversion == null ? '—' : `${(summary.conversion * 100).toFixed(2)}%` }}</strong><small>成交客户合计 / 商品访客合计</small></div></section></div>
        <div class="overview-main"><section class="panel"><div class="panel-title"><div><span class="index">01 / TIME</span><h2>成交与流量同屏</h2><p>柱形为成交金额，曲线为商品访客合计；原始报表缺日不会补零。</p></div></div><div class="chart-legend"><span><i class="legend-bar" />成交金额</span><span><i class="legend-line" />商品访客合计</span></div><VChart :option="trendOption" autoresize class="chart-large" /></section><section class="panel signals"><span class="index">02 / SIGNALS</span><h2>特别关注</h2><article v-for="item in signals" :key="item.title" :class="item.tone"><i></i><div><strong>{{ item.title }}</strong><p>{{ item.detail }}</p></div></article></section></div>
        <section class="panel overview-tree"><span class="index">03 / STRUCTURE</span><h2>收入落在哪些品类</h2><p>矩形面积映射正值成交金额；下方完整列出头部品类名称，余项合并展示。负值仍计入净额和增长贡献。</p><VChart v-if="positiveCategories.length" :option="categoryTreeOption" autoresize class="chart-tree-overview" @click="chooseCategory" /><el-empty v-else description="本期暂无正值品类" /><div class="tree-legend"><div v-for="item in treeItems" :key="item.name"><i :style="{ background: item.itemStyle.color }" /><span>{{ item.name }}</span><strong>¥{{ moneyShort(item.value) }}</strong></div></div></section>
      </template>

      <template v-else-if="props.view === 'trend'"><div class="trend-head"><section class="brief"><span class="index">PERIOD PULSE</span><strong>¥{{ moneyShort(summary.revenue) }}</strong><span>本期成交金额</span></section><section class="brief"><span class="index">DAILY AVERAGE</span><strong>¥{{ moneyShort(coverage.available_days ? summary.revenue / coverage.available_days : 0) }}</strong><span>每个有数据日期的平均成交金额</span></section><section class="brief"><span class="index">DATA COVERAGE</span><strong>{{ coverage.expected_days ? `${Math.round(coverage.available_days / coverage.expected_days * 100)}%` : '—' }}</strong><span>{{ coverage.available_days }} / {{ coverage.expected_days }} 天</span></section></div>
        <section class="panel"><div class="panel-title"><div><span class="index">01 / PULSE</span><h2>成交金额 × 商品访客</h2><p>用流量和成交的背离定位需要进一步核查的日期。</p></div><el-select v-model="granularity" class="grain"><el-option label="按日" value="day" /><el-option label="按月" value="month" /></el-select></div><div class="chart-legend"><span><i class="legend-bar" />成交金额</span><span><i class="legend-line" />商品访客合计</span></div><VChart :option="trendOption" autoresize class="chart-large" /></section>
        <div class="split"><section class="panel daily-map"><span class="index">02 / DAILY MAP</span><h2>最近 {{ heatDays.length }} 天成交热力</h2><p>按区间内有数据日期的金额高低分五档；灰色缺报表，浅灰为筛选后零成交。</p><div class="weekdays"><span v-for="day in ['一','二','三','四','五','六','日']" :key="day">{{ day }}</span></div><div class="heat-grid"><span v-for="i in heatOffset" :key="`blank-${i}`" class="heat-blank" /><span v-for="day in heatDays" :key="day.day" class="heat-cell" :style="{ background: heatColor(day), color: day.revenue > 0 && heatValues.length && day.revenue >= heatValues[Math.floor(heatValues.length * .6)] ? '#fff' : '#31535a' }" :title="`${day.day} · ${day.missing ? '缺少源报表' : `¥${yuan(day.revenue)}`}`">{{ Number(day.day.slice(-2)) }}</span></div><div class="heat-scale"><span>低</span><i v-for="color in ['#d6eee7','#99d5c5','#5bbca9','#198e7d','#075f59']" :key="color" :style="{ background: color }" /><span>高</span><i class="missing-swatch" /><span>缺日</span></div><div class="heat-stats"><div><span>峰值日 {{ heatSummary.peak?.day || '—' }}</span><strong>{{ heatSummary.peak ? `¥${moneyShort(heatSummary.peak.revenue)}` : '—' }}</strong></div><div><span>低谷日 {{ heatSummary.low?.day || '—' }}</span><strong>{{ heatSummary.low ? `¥${moneyShort(heatSummary.low.revenue)}` : '—' }}</strong></div><div><span>有数据日均</span><strong>{{ heatSummary.average == null ? '—' : `¥${moneyShort(heatSummary.average)}` }}</strong></div></div></section><section class="panel"><span class="index">03 / PERIODS</span><h2>期间规模对照</h2><p>金额可查看，但仅在天数相等且日期完整时计算增长率。</p><VChart :option="comparisonOption" autoresize class="chart-mid" /><div class="compare-foot"><span>同比 {{ rate(board.comparisons.yoy.rates.revenue) }}</span><span>环比 {{ rate(board.comparisons.mom.rates.revenue) }}</span></div></section></div>
      </template>

      <template v-else-if="props.view === 'category'"><div class="category-header"><div><span class="index">CATEGORY ATLAS</span><strong>{{ count(board.categories.length) }}</strong><span>个三级类目参与本期统计</span></div><div><span class="index">TOP CATEGORY</span><strong>{{ topCategories[0]?.label || '—' }}</strong><span>成交金额最高的类目</span></div><div><span class="index">TOP SHARE</span><strong>{{ ratio(topCategories[0]?.revenue || 0, summary.revenue) == null ? '—' : `${(ratio(topCategories[0]?.revenue || 0, summary.revenue)! * 100).toFixed(1)}%` }}</strong><span>第一类目占本期净成交额</span></div></div>
        <div class="split wide-left"><section class="panel"><span class="index">01 / SCALE</span><h2>品类收入版图</h2><p>面积对应正值成交金额，点击区域可聚焦品类；下方列出头部品类完整名称和金额。</p><VChart v-if="positiveCategories.length" :option="categoryTreeOption" autoresize class="chart-tall" @click="chooseCategory" /><el-empty v-else description="本期暂无正值品类" /><div class="tree-legend"><div v-for="item in treeItems" :key="item.name"><i :style="{ background: item.itemStyle.color }" /><span>{{ item.name }}</span><strong>¥{{ moneyShort(item.value) }}</strong></div></div></section><section class="panel"><span class="index">02 / LEADERS</span><h2>头部品类</h2><div v-for="(row, i) in topCategories" :key="row.label" class="rank-row"><div><b>{{ String(i + 1).padStart(2, '0') }}</b><span>{{ row.label || '未分类' }}</span><strong>¥{{ moneyShort(row.revenue) }}</strong></div><div class="rank-track"><i :style="{ width: `${Math.max(0, topCategories[0]?.revenue ? row.revenue / topCategories[0].revenue * 100 : 0)}%` }" /></div></div></section></div>
        <div class="split"><section class="panel"><span class="index">03 / CONTRIBUTION</span><h2>环比增长贡献</h2><p>横条显示本期与上月同期的成交金额差额，包含本期退出的品类。</p><VChart v-if="categoryDelta.length" :option="deltaOption" autoresize class="chart-mid" /><el-empty v-else description="比较期不完整或没有可比变化" /></section><section class="panel"><span class="index">04 / POSITION</span><h2>规模 × 增长定位</h2><p>横轴环比、纵轴成交额、气泡大小代表 SKU 数；仅展示上月有基数的品类。</p><VChart v-if="categoryGrowth.length" :option="growthOption" autoresize class="chart-mid" /><el-empty v-else description="没有可比的品类增长数据" /></section></div>
      </template>

      <template v-else><div class="brand-summary"><div><span>本期第一品牌</span><strong>{{ topBrands[0]?.label || '—' }}</strong></div><div><span>品牌数</span><strong>{{ count(board.brands.length) }}</strong></div><div><span>商品 SKU</span><strong>{{ count(summary.sku_count) }}</strong></div><div><span>头部 10 SKU 成交贡献</span><strong>{{ sharePercent(board.products.slice(0, 10).reduce((sum: number, r: Row) => sum + r.revenue, 0), summary.revenue) }}</strong></div></div>
        <div class="split"><section class="panel"><span class="index">01 / BRAND MIX</span><h2>品牌收入结构</h2><p>环图仅用于正值品牌贡献，负值仍计入净额。</p><VChart v-if="positiveBrands.length" :option="brandDonutOption" autoresize class="chart-mid" /><el-empty v-else description="本期暂无正值品牌" /></section><section class="panel"><span class="index">02 / BRAND RANK</span><h2>品牌经营梯队</h2><div v-for="(row, i) in topBrands" :key="row.label" class="rank-row clickable" @click="brand = row.label"><div><b>{{ String(i + 1).padStart(2, '0') }}</b><span>{{ row.label || '待识别' }}</span><strong>¥{{ moneyShort(row.revenue) }}</strong></div><div class="rank-track"><i :style="{ width: `${Math.max(0, topBrands[0]?.revenue ? row.revenue / topBrands[0].revenue * 100 : 0)}%` }" /></div></div></section></div>
        <div class="split"><section class="panel"><span class="index">03 / PRODUCT MAP</span><h2>头部商品流量—成交分布</h2><p>每个点是一个 SKU；横轴商品访客合计，纵轴成交金额，点大小代表成交件数。</p><VChart :option="productScatterOption" autoresize class="chart-mid" /></section><section class="panel"><span class="index">04 / TOP SKU</span><h2>商品成交金额前十</h2><VChart :option="productRankOption" autoresize class="chart-mid" /></section></div>
      </template>

      <footer class="source-note"><strong>口径与来源</strong><p>{{ board.note }}</p><p>数据来自运营部“经营数据分析”的 {{ board.sources.length }} 个已导入月报。同比/环比沿用相同日期及源报表完整性判定；无成本、退款、投放、渠道数据，不能据此计算利润或复购率。</p><details><summary>查看来源文件与行号</summary><ul><li v-for="file in board.sources" :key="file.filename">{{ file.filename }} · {{ count(file.rows) }} 行 · 源文件第 {{ file.first_row }}–{{ file.last_row }} 行</li></ul></details></footer>
    </template>
    <el-empty v-else-if="board && !summary.row_count" description="当前筛选条件没有商品日记录" />
  </section>
</template>

<style scoped>
.board{min-height:100%;padding:28px;background:light-dark(#f2f7f7, var(--app-bg));color:light-dark(#133039, var(--text-primary));font-family:"Microsoft YaHei","Segoe UI",sans-serif}.masthead{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;margin-bottom:22px}.eyebrow,.index{font-size:10px;font-weight:800;letter-spacing:.16em;color:light-dark(#0d8978, var(--text-accent))}.masthead h1{font-size:31px;letter-spacing:.02em;margin:8px 0}.masthead p{font-size:14px;color:light-dark(#647985, var(--text-secondary));margin:0}.masthead-side{display:flex;flex-direction:column;align-items:flex-end;gap:10px;font-size:12px;color:light-dark(#718895, var(--text-secondary))}.filterbar{display:flex;gap:12px;align-items:end;padding:16px 18px;background:light-dark(#fff, var(--app-surface));border:1px solid light-dark(#dce9e9, var(--border-color));border-radius:14px;margin-bottom:18px;box-shadow:0 7px 20px #1b4c5408}.filterbar label{display:flex;flex-direction:column;gap:7px;flex:1;min-width:140px;color:light-dark(#647985, var(--text-secondary));font-size:12px}.filterbar label:first-child{flex:1.6;min-width:300px}.filterbar :deep(.el-date-editor){width:100%}.error{margin:14px 0}.loading{padding:90px;text-align:center;color:light-dark(#64808a, var(--text-secondary))}.scope{display:flex;gap:9px;flex-wrap:wrap;margin:0 0 18px}.scope span{border:1px solid light-dark(#dce9e9, var(--border-color));background:light-dark(#fff, var(--app-surface));border-radius:30px;padding:6px 11px;color:light-dark(#607985, var(--text-secondary));font-size:11px}.panel{background:light-dark(#fff, var(--app-surface));border:1px solid light-dark(#dce9e9, var(--border-color));border-radius:16px;padding:22px;box-shadow:0 7px 20px #1b4c5408;min-width:0}.panel h2{font-size:18px;margin:9px 0 4px}.panel p{font-size:12px;color:light-dark(#78909b, var(--text-secondary));line-height:1.6;margin:5px 0 14px}.panel-title{display:flex;justify-content:space-between;gap:14px}.chart-large{height:390px}.chart-mid{height:340px}.chart-tall{height:455px}.hero-grid{display:grid;grid-template-columns:1.55fr 1fr;gap:16px;margin-bottom:16px}.revenue-hero{border-radius:18px;background:linear-gradient(135deg,#103942 0%,#0c5e59 66%,#087e6f 100%);color:#fff;padding:30px 34px;min-height:220px;position:relative;overflow:hidden}.revenue-hero:after{content:"";position:absolute;width:300px;height:300px;border:1px solid #ffffff24;border-radius:50%;right:-90px;top:-90px;box-shadow:0 0 0 48px #ffffff08,0 0 0 95px #ffffff06}.hero-top{display:flex;justify-content:space-between;color:light-dark(#c7e5df, var(--text-secondary));font-size:13px;position:relative;z-index:1}.hero-accent{border:1px solid #ffffff55;border-radius:20px;padding:4px 9px;font-size:11px}.hero-number{font-size:55px;font-weight:800;letter-spacing:-.05em;line-height:1.2;margin-top:12px;position:relative;z-index:1}.hero-number small{font-size:23px;margin-right:5px}.hero-exact{color:light-dark(#c9e4e0, var(--text-secondary));font-size:12px}.hero-comparison{display:flex;gap:20px;margin-top:19px;font-size:13px;color:light-dark(#c9e4e0, var(--text-secondary))}.hero-comparison strong{font-size:17px;color:#fff}.hero-bottom{margin-top:18px;border-top:1px solid #ffffff37;padding-top:14px;color:light-dark(#c9e4e0, var(--text-secondary));font-size:12px}.metric-stack{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.metric-stack>div,.brief,.category-header>div,.brand-summary>div{background:light-dark(#fff, var(--app-surface));border:1px solid light-dark(#dce9e9, var(--border-color));border-radius:15px;padding:19px;display:flex;flex-direction:column;justify-content:space-between;gap:9px;box-shadow:0 7px 20px #1b4c5408}.metric-stack span,.brief>span:last-child,.category-header span:last-child,.brand-summary span{font-size:12px;color:light-dark(#6d8490, var(--text-secondary))}.metric-stack strong{font-size:25px;color:light-dark(#123942, var(--text-primary));overflow-wrap:anywhere}.metric-stack small{font-size:10px;color:light-dark(#8ba0a7, var(--text-secondary));line-height:1.5}.overview-main{display:grid;grid-template-columns:1.7fr 1fr;gap:16px;margin-bottom:16px}.signals article{display:flex;gap:12px;padding:15px 0;border-bottom:1px solid light-dark(#e7eeee, var(--border-color))}.signals article:last-child{border:0}.signals i{width:8px;height:8px;flex:none;border-radius:50%;background:#688d9a;margin-top:5px}.signals article.good i{background:#0d8978}.signals article.warn i{background:#df9076}.signals strong{font-size:14px}.signals p{margin:5px 0 0}.overview-bottom,.split{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-bottom:16px}.flow-row{margin-top:24px}.flow-row>div:first-child{display:flex;justify-content:space-between;font-size:13px}.flow-row strong{font-size:18px}.flow-track,.rank-track{height:9px;background:light-dark(#e8f0ef, var(--app-surface-2));border-radius:20px;overflow:hidden;margin-top:9px}.flow-track i,.rank-track i{display:block;height:100%;border-radius:20px;background:linear-gradient(90deg,#0d8978,#66c7b5)}.flow-row:nth-of-type(3) .flow-track i{background:#e2ae5a}.flow-row:nth-of-type(4) .flow-track i{background:#6a9bac}.trend-head,.category-header,.brand-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:15px;margin-bottom:16px}.brand-summary{grid-template-columns:repeat(4,1fr)}.brief strong,.category-header strong,.brand-summary strong{font-size:28px;overflow-wrap:anywhere}.trend-head+.panel{margin-bottom:16px}.grain{width:120px}.weekdays,.heat-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:5px}.weekdays span{text-align:center;color:light-dark(#8a9fa7, var(--text-secondary));font-size:11px;padding-bottom:8px}.heat-cell,.heat-blank{height:23px;border-radius:4px}.heat-cell{cursor:help}.compare-foot{display:flex;justify-content:space-around;color:light-dark(#0d8978, var(--text-accent));font-weight:700;font-size:13px}.wide-left{grid-template-columns:1.5fr 1fr}.rank-row{padding:11px 0;border-bottom:1px solid light-dark(#edf2f2, var(--border-color))}.rank-row:last-child{border:0}.rank-row>div:first-child{display:flex;align-items:center;gap:11px;font-size:12px}.rank-row b{color:light-dark(#0d8978, var(--text-accent))}.rank-row span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.rank-row strong{white-space:nowrap}.rank-track{height:6px}.clickable{cursor:pointer}.clickable:hover{background:light-dark(#f4faf8, var(--app-surface-2))}.source-note{border-top:1px solid light-dark(#dce8e8, var(--border-color));margin-top:22px;padding:17px 5px;font-size:12px;color:light-dark(#758a94, var(--text-secondary));line-height:1.7}.source-note strong{color:light-dark(#335862, var(--text-primary))}.source-note p{margin:5px 0}.source-note ul{padding-left:20px}@media(max-width:1200px){.hero-grid,.overview-main,.overview-bottom,.split,.wide-left{grid-template-columns:1fr}.metric-stack{grid-template-columns:repeat(3,1fr)}}@media(max-width:740px){.board{padding:14px}.masthead{flex-wrap:wrap}.masthead-side{align-items:flex-start}.filterbar{flex-wrap:wrap}.filterbar label:first-child{min-width:100%}.metric-stack,.trend-head,.category-header,.brand-summary{grid-template-columns:1fr}.hero-number{font-size:42px}}
.chart-legend{display:flex;justify-content:flex-end;align-items:center;gap:20px;margin:2px 14px 0;color:light-dark(#607785, var(--text-secondary));font-size:12px;line-height:22px}
.chart-legend span{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
.legend-bar{width:18px;height:10px;border-radius:2px;background:#0d8978}
.legend-line{width:19px;height:2px;background:#e6aa50;position:relative}
.legend-line:after{content:"";width:6px;height:6px;border:2px solid #e6aa50;border-radius:50%;background:light-dark(white, var(--app-surface));position:absolute;left:6px;top:-4px}
.overview-tree{margin-bottom:16px}.chart-tree-overview{height:470px}
.tree-legend{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px 20px;margin-top:14px;padding-top:14px;border-top:1px solid light-dark(#e7eeee, var(--border-color))}
.tree-legend>div{display:flex;align-items:center;gap:8px;min-width:0;font-size:12px;color:light-dark(#335862, var(--text-primary))}
.tree-legend i{flex:none;width:10px;height:10px;border-radius:2px}.tree-legend span{min-width:0;overflow-wrap:anywhere}.tree-legend strong{margin-left:auto;flex:none;font-weight:600;white-space:nowrap}
.daily-map{display:flex;flex-direction:column}.daily-map .weekdays{margin-top:8px}.daily-map .heat-grid{align-content:start}
.daily-map .heat-cell,.daily-map .heat-blank{height:39px;border-radius:6px}.daily-map .heat-cell{display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700}
.heat-scale{display:flex;align-items:center;gap:5px;margin-top:15px;color:light-dark(#7c929b, var(--text-secondary));font-size:11px}.heat-scale i{width:20px;height:12px;border-radius:3px}.heat-scale .missing-swatch{margin-left:14px;background:light-dark(#d5dfe3, rgba(96, 165, 250, .12))}
.heat-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;border-top:1px solid light-dark(#e7eeee, var(--border-color));margin-top:auto;padding-top:15px}
.heat-stats>div{display:flex;flex-direction:column;gap:6px}.heat-stats span{color:light-dark(#7b929a, var(--text-secondary));font-size:11px}.heat-stats strong{font-size:14px;color:light-dark(#214851, var(--text-primary))}
@media(max-width:1100px){.tree-legend{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:650px){.tree-legend{grid-template-columns:1fr}.heat-stats{grid-template-columns:1fr}.chart-legend{justify-content:flex-start}}
</style>
