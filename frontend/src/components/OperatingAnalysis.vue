<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { ElAlert, ElButton, ElSelect, ElOption, ElTabs, ElTabPane, ElTable, ElTableColumn, ElPagination, ElDialog, ElTag, ElMessage, ElInput, ElEmpty, ElPopover, ElCheckbox, ElCheckboxGroup } from 'element-plus'
import * as XLSX from 'xlsx'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, GraphicComponent } from 'echarts/components'
import OperatingFilterBar from './OperatingFilters.vue'
import { trendOption, rankingOption, categoryOption, shortLabel, metricUnit, type OperatingData as Data, type OperatingFilters } from './operatingCharts'
use([CanvasRenderer, LineChart, BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, GraphicComponent])

const meta = ref<Data>({ dates: [], metrics: {}, categories: [], brands: [] })
const data = ref<Data | null>(null)
const form = ref<OperatingFilters>({ range: [], keyword: '', brand: '', metric: 'revenue' })
const tab = ref('overview'), group = ref('sku'), rankLimit = ref(10), year = ref('')
const page = ref(1), pageSize = ref(50), loading = ref(false), importing = ref(false), modelImporting = ref(false), modelExporting = ref(false), error = ref('')
const fileInput = ref<HTMLInputElement | null>(null), modelFileInput = ref<HTMLInputElement | null>(null), raw = ref<Data | null>(null)
const exportColumns = ref<string[]>([])
const fmt = (n: any, decimals = 2) => n == null ? '—' : Number(n).toLocaleString('zh-CN', { maximumFractionDigits: decimals })
const pct = (n: any) => n == null ? '不可比' : `${n > 0 ? '+' : ''}${(n * 100).toFixed(2)}%`
const share = (n: any) => n == null ? '—' : `${(n * 100).toFixed(2)}%`
const queryFilters = () => ({ start: form.value.range[0], end: form.value.range[1], keyword: form.value.keyword, brand: form.value.brand, metric: form.value.metric, group: group.value })
async function api(path: string, init?: RequestInit) {
  const response = await fetch(`/api/operating-analysis${path}`, { credentials: 'same-origin', ...init })
  const result = await response.json()
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '请求失败，请检查筛选条件')
  return result
}
async function loadMeta() {
  meta.value = await api('/metadata')
  if (!form.value.range.length && meta.value.dates.length) {
    const end = meta.value.dates.at(-1)
    form.value.range = [`${end.slice(0, 7)}-01`, end]
  }
}
let version = 0
let queryTimer: ReturnType<typeof setTimeout> | undefined
// 任何筛选条件变化后自动触发查询（输入型条件做 350ms 防抖）
watch(form, () => {
  clearTimeout(queryTimer)
  queryTimer = setTimeout(() => { void load(true) }, 350)
}, { deep: true })
async function load(reset = false) {
  if (form.value.range.length !== 2) return
  if (reset) page.value = 1
  const id = ++version
  loading.value = true; error.value = ''
  try {
    const result = await api(`?${new URLSearchParams({ ...queryFilters(), page: String(page.value), page_size: String(pageSize.value) })}`)
    if (id === version) data.value = result
  } catch (e: any) { if (id === version) { error.value = e.message; data.value = null } }
  finally { if (id === version) loading.value = false }
}
async function reset() {
  const end = meta.value.dates.at(-1)
  form.value = { range: end ? [`${end.slice(0, 7)}-01`, end] : [], keyword: '', brand: '', metric: 'revenue' }
}
async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files?.length) return
  importing.value = true
  try {
    const results: Data[] = []
    for (const file of Array.from(input.files)) {
      const body = new FormData(); body.append('file', file)
      results.push(await api('/import', { method: 'POST', body }))
    }
    await loadMeta(); await load(true)
    const updatedRows = results.reduce((total, result) => total + Number(result.updated_rows || 0), 0)
    ElMessage.success(updatedRows
      ? `数据导入完成，覆盖更新 ${updatedRows.toLocaleString('zh-CN')} 条重叠明细`
      : '数据导入完成')
  } catch (e: any) { ElMessage.error(e.message); await loadMeta(); await load(true) }
  finally { importing.value = false; input.value = '' }
}
async function downloadModelTemplate() {
  modelExporting.value = true
  try {
    const response = await fetch('/api/operating-analysis/model-mapping/template', { credentials: 'same-origin' })
    if (!response.ok) {
      const result = await response.json().catch(() => ({}))
      throw new Error(typeof result.detail === 'string' ? result.detail : '型号模板导出失败')
    }
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = '型号货号匹配模板.xlsx'
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('型号匹配模板已导出')
  } catch (e: any) { ElMessage.error(e.message || '型号模板导出失败') }
  finally { modelExporting.value = false }
}
async function importModelTemplate(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files?.length) return
  modelImporting.value = true
  try {
    const body = new FormData(); body.append('file', input.files[0])
    const result = await api('/model-mapping/import', { method: 'POST', body })
    await load(true)
    ElMessage.success({
      message: result.message || '型号模板导入完成',
      duration: 10000,
      showClose: true,
    })
  } catch (e: any) { ElMessage.error(e.message || '型号模板导入失败') }
  finally { modelImporting.value = false; input.value = '' }
}
const exportColumnOptions = computed(() => {
  const options: { key: string; label: string }[] = [{ key: 'rank', label: '排名' }]
  if (group.value === 'sku') options.push({ key: 'object', label: 'SKU' }, { key: 'name', label: '商品名称' }, { key: 'code', label: '货号' })
  else if (group.value === 'model') options.push({ key: 'object', label: '型号（货号 / SKU）' }, { key: 'name', label: '商品名称' })
  else options.push({ key: 'object', label: '类目' }, { key: 'sku_count', label: '商品数' })
  for (const [key, label] of Object.entries(meta.value.metrics || {})) options.push({ key: `metric:${key}`, label: String(label) })
  return options
})
watch([group, () => meta.value.metrics], () => { exportColumns.value = exportColumnOptions.value.map(option => option.key) }, { immediate: true })
function changeExportColumns(value: unknown[]) {
  if (value.length) return
  exportColumns.value = exportColumnOptions.value.length ? [exportColumnOptions.value[0].key] : []
  ElMessage.warning('至少保留一列导出数据')
}
function exportContribution() {
  const rows: Data[] = (data.value?.ranking || []) as Data[]
  if (!rows.length) { ElMessage.warning('暂无可导出的贡献明细'); return }
  if (!exportColumns.value.length) { ElMessage.warning('请至少选择一列导出数据'); return }
  const selected = new Set(exportColumns.value)
  const exported = rows.map(row => {
    const result: Record<string, unknown> = {}
    for (const option of exportColumnOptions.value) {
      if (!selected.has(option.key)) continue
      if (option.key === 'rank') result[option.label] = rows.indexOf(row) + 1
      else if (option.key === 'object') result[option.label] = row.label || ''
      else if (option.key === 'name') result[option.label] = row.name || ''
      else if (option.key === 'code') result[option.label] = row.code || ''
      else if (option.key === 'sku_count') result[option.label] = row.sku_count || 0
      else if (option.key.startsWith('metric:')) {
        const metricKey = option.key.slice('metric:'.length)
        result[option.label] = row[metricKey] ?? (metricKey === activeMetric.value ? row.value : '')
      }
    }
    return result
  })
  const sheet = XLSX.utils.json_to_sheet(exported)
  sheet['!cols'] = Object.keys(exported[0]).map(key => ({ wch: Math.max(12, Math.min(36, key.length + 6)) }))
  const workbook = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(workbook, sheet, '贡献明细')
  XLSX.writeFile(workbook, '经营数据分析-贡献明细.xlsx')
  ElMessage.success(`已导出 ${rows.length} 条贡献明细`)
}
function openProduct(row: Data) {
  if (data.value?.filters.group !== 'sku') return
  form.value.keyword = row.label; tab.value = 'details'
}
function openDate(day: string) { form.value.range = [day, day]; tab.value = 'details' }
async function changeGroup(value: string) { group.value = value; await load(true) }
const activeMetric = computed(() => data.value?.filters.metric || 'revenue')
const metricLabel = computed(() => meta.value.metrics[activeMetric.value] || '成交金额')
const groupLabel = computed(() => ({ sku: '商品', category: '类目', model: '型号' }[group.value] || '对象'))
const trend = computed(() => trendOption(data.value, metricLabel.value))
const ranking = computed(() => rankingOption(data.value?.ranking || [], activeMetric.value, metricLabel.value, data.value?.filters.group, rankLimit.value))
const categoryShare = computed(() => categoryOption(data.value?.category_distribution || []))
const topFiveShare = computed(() => { const total = data.value?.summary[activeMetric.value]; return total > 0 ? data.value?.ranking.slice(0, 5).reduce((s: number, r: Data) => s + r.value, 0) / total : null })
const cards = [ ['revenue', '成交金额（元）'], ['quantity', '成交件数'], ['orders', '商品成交单量合计'], ['visitors', '商品访客合计'], ['cart_amount', '加购金额（元）'] ]
const comparisons = computed(() => !data.value ? [] : ['yoy', 'mom'].map(key => ({ label: key === 'yoy' ? '同比' : '环比', ...data.value!.comparisons[key] })))
const years = computed(() => [...new Set<string>(meta.value.dates.map((d: string) => d.slice(0, 4)))].sort((a, b) => b.localeCompare(a)))
const monthGroups = computed(() => {
  const groups: Record<string, string[]> = {}
  for (const d of meta.value.dates as string[]) { if (year.value && !d.startsWith(year.value)) continue; (groups[d.slice(0, 7)] ||= []).push(d) }
  return Object.entries(groups).sort(([a], [b]) => b.localeCompare(a)).map(([month, days]) => ({ month, days }))
})
onMounted(async () => { try { await loadMeta() } catch (e: any) { error.value = e.message } })
</script>

<template>
  <section class="operating-page" :aria-busy="loading">
    <header class="page-header"><div><span class="eyebrow">运营部 / 商智商品日明细</span><h1>经营数据分析</h1></div><div class="header-actions"><el-tag>{{ meta.dates.length }} 个有数据日期</el-tag><el-button :loading="importing" @click="fileInput?.click()">导入月报</el-button><input ref="fileInput" hidden type="file" multiple accept=".xlsx" @change="upload" /></div></header>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <section v-if="!['details', 'sources'].includes(tab)" class="panel filters-panel"><OperatingFilterBar v-model="form" :meta="meta" :loading="loading" show-metric @query="load(true)" @reset="reset" /></section>
    <div v-if="data && tab !== 'sources'" class="scope"><span>{{ data.filters.start }} 至 {{ data.filters.end }}</span><el-tag size="small">{{ data.filters.brand || '全部品牌' }}</el-tag><span>{{ fmt(data.total, 0) }} 条商品日明细</span><span>{{ data.coverage.available_days }} / {{ data.coverage.expected_days }} 天有数据</span></div>
    <el-alert v-if="data && !data.coverage.complete && tab !== 'sources'" type="warning" :closable="false" :title="`区间缺少 ${data.coverage.missing_dates.length} 天数据，同比环比不输出增长率。`" />
    <el-tabs v-model="tab" class="page-tabs">
      <el-tab-pane label="经营总览" name="overview">
        <div v-if="data" class="kpis"><article v-for="[key, label] in cards" :key="key"><span>{{ label }}</span><strong>{{ fmt(data.summary[key!]) }}</strong><div><small>同比</small><b :class="{ negative: data.comparisons.yoy.rates[key!] < 0 }">{{ pct(data.comparisons.yoy.rates[key!]) }}</b></div><div><small>环比</small><b :class="{ negative: data.comparisons.mom.rates[key!] < 0 }">{{ pct(data.comparisons.mom.rates[key!]) }}</b></div></article></div>
        <div class="panel"><div class="section-heading"><div><h2>按日经营趋势</h2><p>{{ metricLabel }} · {{ metricUnit(activeMetric) }}</p></div><el-tag>{{ data?.filters.brand || '全部品牌' }}</el-tag></div><VChart :option="trend" autoresize class="trend-chart" /><p class="note">图表仅显示有明细的日期，缺失日期不补零。</p></div>
        <div v-if="data" class="panel"><h2>同比与环比核对</h2><p class="note">{{ data.comparison_note }}</p><el-table :data="comparisons"><el-table-column prop="label" label="比较" width="90" /><el-table-column label="对比期间" min-width="230"><template #default="{ row }">{{ row.coverage.start }} 至 {{ row.coverage.end }}</template></el-table-column><el-table-column label="数据天数"><template #default="{ row }">{{ row.coverage.available_days }} / {{ row.coverage.expected_days }}</template></el-table-column><el-table-column :label="metricLabel"><template #default="{ row }">{{ fmt(row.summary[activeMetric]) }}</template></el-table-column><el-table-column label="增长率"><template #default="{ row }"><span :class="{ negative: row.rates[activeMetric] < 0 }">{{ pct(row.rates[activeMetric]) }}</span></template></el-table-column></el-table></div>
        <p class="note">{{ meta.brand_note }}</p>
      </el-tab-pane>
      <el-tab-pane label="商品与类目" name="products">
        <div class="product-toolbar"><div><h2>商品、型号与类目结构</h2><p>{{ metricLabel }} · {{ data?.filters.brand || '全部品牌' }}</p></div><div class="switches"><el-button :type="group === 'sku' ? 'primary' : 'default'" @click="changeGroup('sku')">商品排行</el-button><el-button :type="group === 'model' ? 'primary' : 'default'" @click="changeGroup('model')">型号排行</el-button><el-button :type="group === 'category' ? 'primary' : 'default'" @click="changeGroup('category')">类目排行</el-button><template v-if="group === 'model'"><el-button :loading="modelExporting" @click="downloadModelTemplate">导出模板</el-button><el-button :loading="modelImporting" @click="modelFileInput?.click()">导入模板</el-button><input ref="modelFileInput" hidden type="file" accept=".xlsx" @change="importModelTemplate" /></template></div></div>
        <div v-if="data" class="product-kpis"><article><span>参与统计的商品</span><strong>{{ fmt(data.summary.sku_count, 0) }} <small>个 SKU</small></strong></article><article><span>本期{{ metricLabel }}</span><strong>{{ fmt(data.summary[activeMetric]) }} <small>{{ metricUnit(activeMetric) }}</small></strong></article><article><span>前五名占本期净值</span><strong>{{ share(topFiveShare) }}</strong></article><article><span>领先{{ groupLabel }}</span><strong class="winner">{{ group === 'sku' ? shortLabel(data.ranking[0]?.name || '暂无数据', 30) : data.ranking[0]?.label || '暂无数据' }}</strong></article></div>
        <div class="product-charts"><section class="panel rank-panel"><div class="section-heading"><div><h2>{{ groupLabel }}贡献排行</h2><p>按{{ metricLabel }}排序，{{ group === 'model' ? '货号为空时使用 SKU 作为型号' : '完整名称和 SKU 见下方明细' }}</p></div><el-select v-model="rankLimit" aria-label="排行展示数量" class="rank-limit"><el-option :value="10" label="前10名" /><el-option :value="20" label="前20名" /></el-select></div><VChart :option="ranking" autoresize :style="{ height: `${Math.max(360, Math.min(data?.ranking.length || 0, rankLimit) * 48 + 60)}px` }" /></section><section class="panel share-panel"><h2>类目贡献结构</h2><p>{{ metricLabel }} · 正值类目占比</p><VChart :option="categoryShare" autoresize class="share-chart" /><div class="category-list"><div v-for="(c, i) in (data?.category_distribution || []).slice(0, 6)" :key="c.label"><span>{{ Number(i) + 1 }} · {{ c.label || '未分类' }}</span><strong>{{ fmt(c.value) }}</strong></div></div><p class="note">环图仅展示正值贡献，其他类目合并显示；负值保留在排行和明细中。</p></section></div>
        <div class="panel"><div class="section-heading contribution-heading"><div><h2>贡献明细</h2><p>运营可选择需要导出的列，排行数据全部导出</p></div><div class="export-actions"><el-popover placement="bottom-end" :width="260" trigger="click"><template #reference><el-button>选择导出列</el-button></template><div class="export-column-picker"><strong>选择导出列</strong><el-checkbox-group v-model="exportColumns" @change="changeExportColumns"><el-checkbox v-for="option in exportColumnOptions" :key="option.key" :label="option.key">{{ option.label }}</el-checkbox></el-checkbox-group></div></el-popover><el-button type="primary" plain @click="exportContribution">导出明细</el-button></div></div><el-table :data="data?.ranking || []" stripe><el-table-column label="排名" width="70"><template #default="{ $index }"><span class="rank-number" :class="{ leading: $index < 3 }">{{ $index + 1 }}</span></template></el-table-column><el-table-column prop="label" :label="group === 'sku' ? 'SKU' : group === 'model' ? '型号（货号 / SKU）' : '类目'" min-width="150" /><el-table-column v-if="group === 'sku' || group === 'model'" prop="name" label="商品名称" min-width="300" show-overflow-tooltip /><el-table-column v-if="group === 'sku'" prop="code" label="货号" min-width="130" /><el-table-column v-if="group === 'category'" prop="sku_count" label="商品数" width="100" /><el-table-column :label="metricLabel" min-width="150" align="right"><template #default="{ row }"><strong>{{ fmt(row.value) }}</strong></template></el-table-column><el-table-column v-if="group === 'sku'" label="查询" width="100"><template #default="{ row }"><el-button link type="primary" @click="openProduct(row)">每日明细</el-button></template></el-table-column></el-table></div>
      </el-tab-pane>
      <el-tab-pane label="每日全部明细" name="details">
        <div class="panel"><div class="section-heading"><div><h2>每日商品明细筛选</h2><p>按日期、品牌及 SKU / 货号 / 名称查询全部明细</p></div><el-tag>{{ fmt(data?.total || 0, 0) }} 条结果</el-tag></div><OperatingFilterBar v-model="form" :meta="meta" :loading="loading" @query="load(true)" @reset="reset" /></div>
        <div class="panel detail-panel"><el-table :data="data?.items || []" stripe height="620"><el-table-column prop="day" label="日期" width="115" fixed /><el-table-column prop="sku" label="SKU" width="145" /><el-table-column prop="brand" label="品牌" width="145" /><el-table-column prop="code" label="货号" width="150" /><el-table-column prop="name" label="商品名称" min-width="300" show-overflow-tooltip /><el-table-column prop="category" label="类目" width="120" /><el-table-column v-for="(label, key) in meta.metrics" :key="key" :label="String(label)" width="135" align="right"><template #default="{ row }">{{ fmt(row[key]) }}</template></el-table-column><el-table-column label="原始明细" width="100" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="raw = row">原始字段</el-button></template></el-table-column></el-table><el-pagination v-model:current-page="page" v-model:page-size="pageSize" :total="data?.total || 0" :page-sizes="[20,50,100,200]" layout="total,sizes,prev,pager,next,jumper" @current-change="load()" @size-change="load(true)" /></div>
      </el-tab-pane>
      <el-tab-pane label="可查询日期" name="sources"><section class="panel dates-panel"><div class="section-heading"><div><h2>可查询的全部日期</h2><p>{{ meta.dates[0] || '暂无数据' }} 至 {{ meta.dates.at(-1) || '暂无数据' }} · 点击日期查看当天明细</p></div><el-select v-model="year" clearable placeholder="全部年份" aria-label="日期年份" class="year-select"><el-option v-for="y in years" :key="y" :value="y" :label="`${y}年`" /></el-select></div><div class="month-grid"><article v-for="month in monthGroups" :key="month.month" class="month-card"><header><h3>{{ month.month.replace('-', '年') }}月</h3><small>{{ month.days.length }} 天</small></header><div class="date-buttons"><button v-for="d in month.days" :key="d" :aria-label="`查询 ${d}`" :title="d" @click="openDate(d)">{{ Number(d.slice(-2)) }}</button></div></article></div><el-empty v-if="!monthGroups.length" description="暂无可查询日期" /></section></el-tab-pane>
    </el-tabs>
    <p v-if="tab !== 'sources'" class="footnote">{{ meta.note }}</p>
    <el-dialog :model-value="!!raw" title="原始报表字段" width="760px" @close="raw = null"><template v-if="raw"><p>{{ raw.filename }} · 第 {{ raw.source_row }} 行 · {{ raw.brand }}</p><el-table :data="Object.entries(raw.raw).map(([key, value]) => ({ key, value }))"><el-table-column prop="key" label="字段" /><el-table-column prop="value" label="原始值" /></el-table></template></el-dialog>
  </section>
</template>

<style scoped>
.operating-page{font-family:"Microsoft YaHei","Segoe UI",sans-serif}
.operating-page{padding:24px;background:light-dark(#f4f7fa, var(--app-bg));min-height:100%;color:light-dark(#172b3a, var(--text-primary))}.page-header{display:flex;justify-content:space-between;align-items:center;gap:18px;margin-bottom:22px}.eyebrow{font-size:12px;color:light-dark(#64748b, var(--text-secondary))}h1{margin:8px 0 0;font-size:27px;letter-spacing:.5px}.header-actions{display:flex;gap:12px;align-items:center}h2{font-size:17px;margin:0 0 8px}p{color:light-dark(#64748b, var(--text-secondary));font-size:13px;line-height:1.7;margin:6px 0}.panel{background:light-dark(white, var(--app-surface));border:1px solid light-dark(#e2e8f0, var(--border-color));border-radius:13px;padding:22px;margin:18px 0}.filters-panel{margin-bottom:14px}.scope{display:flex;align-items:center;flex-wrap:wrap;gap:14px;font-size:12px;color:light-dark(#64748b, var(--text-secondary));margin:16px 0}.page-tabs{margin-top:18px}.section-heading{display:flex;justify-content:space-between;align-items:center;gap:18px;margin-bottom:20px}.kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:14px;margin:18px 0}.kpis article{padding:20px;background:light-dark(white, var(--app-surface));border:1px solid light-dark(#e2e8f0, var(--border-color));border-radius:12px;display:flex;flex-direction:column;gap:10px}.kpis article>span,.kpis small{font-size:12px;color:light-dark(#64748b, var(--text-secondary))}.kpis strong{font-size:25px;color:light-dark(#0f766e, var(--text-accent));overflow-wrap:anywhere}.kpis article>div{display:flex;gap:10px;align-items:center}.kpis b{font-size:12px;color:light-dark(#0f766e, var(--text-accent));font-weight:600}.negative,.kpis b.negative{color:light-dark(#c2410c, #fb923c)}.trend-chart{height:370px}.note{font-size:12px;color:light-dark(#94a3b8, var(--text-secondary))}.product-toolbar{display:flex;justify-content:space-between;align-items:center;gap:16px;margin:20px 0}.switches{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}.switches .el-button+.el-button{margin-left:0}.product-kpis{display:grid;grid-template-columns:1fr 1.3fr 1fr 1.7fr;gap:14px}.product-kpis article{background:light-dark(#fff, var(--app-surface));border:1px solid light-dark(#e2e8f0, var(--border-color));border-radius:12px;padding:18px;display:flex;flex-direction:column;gap:12px}.product-kpis span{font-size:12px;color:light-dark(#64748b, var(--text-secondary))}.product-kpis strong{font-size:23px;color:light-dark(#0f172a, var(--text-primary))}.product-kpis small{font-size:12px;color:light-dark(#94a3b8, var(--text-secondary));font-weight:400}.product-kpis .winner{font-size:14px;line-height:1.7}.product-charts{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(0,1fr);gap:18px}.rank-limit{width:105px;flex:none}.share-chart{height:330px}.category-list>div{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid light-dark(#f1f5f9, var(--border-color));font-size:12px;color:light-dark(#64748b, var(--text-secondary))}.category-list strong{color:light-dark(#334155, var(--text-primary))}.rank-number{display:inline-flex;align-items:center;justify-content:center;width:25px;height:25px;background:light-dark(#f1f5f9, var(--app-surface-2));border-radius:7px;color:light-dark(#64748b, var(--text-secondary))}.rank-number.leading{background:light-dark(#ccfbf1, var(--primary-surface-2));color:light-dark(#0f766e, var(--text-accent))}.el-pagination{margin-top:20px}.detail-panel{padding:12px 18px 22px}.suggestions{display:flex;flex-wrap:wrap;gap:8px;margin-top:20px}.suggestions .el-button+.el-button{margin-left:0}.ai-empty{padding:40px;text-align:center;background:light-dark(#fff, var(--app-surface));border:1px dashed light-dark(#cbd5e1, var(--border-color));border-radius:12px;color:light-dark(#64748b, var(--text-secondary))}.ai-empty>span{font-size:17px;color:light-dark(#334155, var(--text-primary))}.ask{display:flex;gap:14px;align-items:flex-end}.year-select{width:150px;flex:none}.dates-panel{min-height:780px}.month-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}.month-card{padding:18px;border:1px solid light-dark(#e2e8f0, var(--border-color));border-radius:12px;background:light-dark(#fbfdff, var(--app-surface-2))}.month-card header{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.month-card h3{font-size:15px;margin:0}.month-card small{font-size:12px;color:light-dark(#64748b, var(--text-secondary))}.date-buttons{display:grid;grid-template-columns:repeat(7,1fr);gap:7px}.date-buttons button{height:36px;background:light-dark(white, var(--app-surface));border:1px solid light-dark(#e2e8f0, var(--border-color));border-radius:7px;color:light-dark(#334155, var(--text-primary));cursor:pointer;font:inherit;font-size:13px;transition:.15s}.date-buttons button:hover,.date-buttons button:focus-visible{background:#0f766e;color:white;border-color:#0f766e}.footnote{padding:12px;font-size:12px;color:light-dark(#94a3b8, var(--text-secondary));line-height:1.8}@media(max-width:1200px){.kpis{grid-template-columns:repeat(3,1fr)}.product-charts{grid-template-columns:1fr}.product-kpis{grid-template-columns:repeat(2,1fr)}.month-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:720px){.operating-page{padding:14px}.page-header,.product-toolbar{flex-wrap:wrap}.kpis{grid-template-columns:repeat(2,1fr)}.month-grid{grid-template-columns:1fr}.ask{flex-direction:column;align-items:stretch}}
.export-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.export-column-picker{display:flex;flex-direction:column;gap:12px}.export-column-picker strong{font-size:13px;color:light-dark(#334155, var(--text-primary))}.export-column-picker :deep(.el-checkbox-group){display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.export-column-picker :deep(.el-checkbox){margin-right:0;height:auto}.export-column-picker :deep(.el-checkbox__label){font-size:12px}
</style>
