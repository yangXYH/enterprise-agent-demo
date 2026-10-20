<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import {
  ElAlert,
  ElButton,
  ElDrawer,
  ElEmpty,
  ElIcon,
  ElInput,
  ElMessage,
  ElOption,
  ElPagination,
  ElPopover,
  ElSelect,
  ElSkeleton,
  ElTable,
  ElTableColumn,
  ElTag,
  ElTooltip,
  ElUpload,
  type UploadFile,
  type UploadInstance,
  type UploadRawFile,
} from 'element-plus'
import {
  ChatDotRound,
  DataAnalysis,
  DocumentChecked,
  Download,
  Refresh,
  Search,
  TrendCharts,
  Upload,
} from '@element-plus/icons-vue'
import request from '../utils/request'

const props = withDefaults(defineProps<{
  mode?: 'forecast' | 'purchase'
  purchaseFormula?: 'system' | 'excel'
}>(), {
  mode: 'forecast',
  purchaseFormula: 'system',
})
const emit = defineEmits<{ (e: 'data-updated'): void }>()

interface ForecastOptions {
  forecast_dates: string[]
  business_dates: string[]
  latest_snapshot_date?: string | null
  brands: string[]
  categories: string[]
  trend_levels: string[]
  confidence_levels: string[]
  sku_link_statuses: string[]
}

interface ForecastSummary {
  forecast_date?: string | null
  latest_business_date?: string | null
  forecast_sku_count?: number
  linked_sku_count?: number
  pending_link_count?: number
  up_high_count?: number
  affected_warehouse_count?: number
  suggestion_count?: number
  backtest_hit_rate?: number | null
  backtest_wape?: number | null
}

interface ForecastRow {
  id?: number
  forecast_date: string
  target_start_date?: string
  target_end_date?: string
  sku_code: string
  product_name?: string
  brand?: string
  category?: string
  category_l1?: string
  category_l2?: string
  category_l3?: string
  sku_link_status: string
  days_covered?: number
  total_30d_units?: number
  recent_3d_avg?: number
  recent_7d_avg?: number
  recent_14d_avg?: number
  recent_30d_avg?: number
  base_pred_7d?: number
  adjusted_pred_7d?: number
  unit_momentum?: number
  visitor_momentum?: number
  cart_momentum?: number
  conversion_momentum?: number
  adjustment_factor?: number
  trend_level: string
  confidence_level: string
  affected_warehouse_count?: number
  suggestion_count?: number
  pending_city_split?: number | boolean
  reason_json?: string | Record<string, unknown>
  actual_7d?: number | null
  forecast_error?: number | null
}

interface CityForecastRow {
  id?: number
  warehouse_code: string
  city_sales_30d?: number
  city_share?: number
  predicted_city_7d?: number
  daily_city_forecast?: number
  target_days?: number
  stock_qty?: number
  inbound_qty?: number
  available_qty?: number
  days_of_supply?: number
  risk_level?: string
  shortage_qty?: number
  suggested_qty?: number
  suggested_source?: string
  eta_days?: number
  route_path?: string
  status?: string
  reason?: string
}

interface ListResponse {
  items: ForecastRow[]
  total: number
  page: number
  page_size: number
}

interface DetailResponse {
  forecast: ForecastRow | null
  cities: CityForecastRow[]
}

interface PurchaseRow {
  sku_code: string
  product_name?: string
  brand?: string
  category?: string
  category_l1?: string
  category_l2?: string
  category_l3?: string
  purchase_reason?: string
  purchase_reason_summary?: string
  purchase_reason_details?: PurchaseReasonDetail[]
  huadong_available_qty?: number
  北京?: number
  上海?: number
  广州?: number
  成都?: number
  武汉?: number
  沈阳?: number
  西安?: number
  德州?: number
}

interface PurchaseReasonDetail {
  city: string
  suggested_qty?: number
  predicted_city_7d?: number
  stock_qty?: number
  inbound_qty?: number
  huadong_available_qty?: number
  days_of_supply?: number
  target_days?: number
  route_path?: string
  eta_days?: number
}

interface PurchaseRowsResponse {
  items: PurchaseRow[]
  total: number
  page: number
  page_size: number
  total_qty?: number
  brands?: string[]
  categories?: string[]
}

interface ForecastExplainResponse {
  answer: string
}

interface ForecastAgentMessage {
  role: 'user' | 'assistant'
  content: string
}

type SignalKey = 'sales' | 'traffic' | 'interest' | 'conversion' | 'quality'

interface BusinessSignalRow {
  key: SignalKey
  label: string
  score: number | null
  weight: string
  metrics: string
  reason: string
}

const emptyOptions = (): ForecastOptions => ({
  forecast_dates: [],
  business_dates: [],
  latest_snapshot_date: null,
  brands: [],
  categories: [],
  trend_levels: ['UP', 'STABLE', 'DOWN'],
  confidence_levels: ['HIGH', 'MID', 'LOW'],
  sku_link_statuses: ['LINKED', 'PENDING_LINK'],
})

const options = reactive<ForecastOptions>(emptyOptions())
const summary = reactive<ForecastSummary>({})
const filters = reactive({
  forecastDate: '',
  businessDate: '',
  skuCode: '',
  productName: '',
  brand: '',
  category: '',
  trendLevel: '',
  confidenceLevel: '',
  linkStatus: '',
})

const rows = ref<ForecastRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const purchaseRows = ref<PurchaseRow[]>([])
const purchaseTotal = ref(0)
const purchaseTotalQty = ref(0)
const purchaseFilterBrands = ref<string[]>([])
const purchaseFilterCategories = ref<string[]>([])
const purchasePage = ref(1)
const purchasePageSize = ref(20)
const loading = ref(true)
const tableLoading = ref(false)
const purchaseLoading = ref(false)
const actionLoading = ref(false)
const exportLoading = ref(false)
const detailLoading = ref(false)
const errorMessage = ref('')
const detailError = ref('')
const detailVisible = ref(false)
const selectedForecast = ref<ForecastRow | null>(null)
const cityRows = ref<CityForecastRow[]>([])
const explainVisible = ref(false)
const explainLoading = ref(false)
const explainLoadingKey = ref('')
const selectedExplainForecast = ref<ForecastRow | null>(null)
const explainInput = ref('')
const explainMessagesBySku = reactive<Record<string, ForecastAgentMessage[]>>({})
const explainBodyRef = ref<HTMLElement>()
const uploadRef = ref<UploadInstance>()
const uploadFile = ref<UploadRawFile | null>(null)

const explainStarterPrompts = [
  { label: '分析趋势', message: '请用运营能看懂的话，分析这个SKU未来7天为什么需要重点关注。' },
  { label: '为什么变化', message: '为什么这个SKU的未来需求和原判断不一样？' },
  { label: '看八仓风险', message: '八大仓里我应该优先看哪些风险，怎么处理？' },
  { label: '补货建议', message: '这个SKU现在适合怎么观察补货？请说得直接一点。' },
  { label: '生成汇报话术', message: '帮我生成一段给运营负责人看的简短汇报话术。' },
]

const targetWindow = computed(() => {
  const row = selectedForecast.value || rows.value[0]
  if (!row?.target_start_date || !row?.target_end_date) return '暂无预测批次'
  return `${row.target_start_date} 至 ${row.target_end_date}`
})

const businessDataRange = computed(() => {
  const endDate = summary.latest_business_date || summary.forecast_date || filters.forecastDate
  if (!endDate) return '-'
  const parsed = new Date(`${endDate}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return endDate
  parsed.setDate(parsed.getDate() - 29)
  return `${parsed.toISOString().slice(0, 10)} ~ ${endDate}`
})

const activeForecastDate = computed(() => {
  if (props.mode === 'purchase') {
    return options.forecast_dates[0] || filters.forecastDate || ''
  }
  return filters.forecastDate || ''
})

// 补货导出明细的“最新批次”以库存表导入批次（inv_stock_snapshot 最新 snapshot_date）为准；
// 仅改变显示日期来源，不影响补货明细数据按经营预测批次查询。
const latestInventoryBatchDate = computed(() => options.latest_snapshot_date || '')
const purchaseLatestBatchText = computed(() => (
  latestInventoryBatchDate.value || activeForecastDate.value || '自动同步'
))

const hasData = computed(() => rows.value.length > 0)

const activeExplainMessages = computed(() => (
  selectedExplainForecast.value ? explainMessagesBySku[explainRowKey(selectedExplainForecast.value)] || [] : []
))

const trendLabels: Record<string, string> = {
  UP: '上涨',
  STABLE: '稳定',
  DOWN: '下降',
}

const confidenceLabels: Record<string, string> = {
  HIGH: '高置信',
  MID: '中置信',
  LOW: '低置信',
}

const linkLabels: Record<string, string> = {
  LINKED: '已关联',
  PENDING_LINK: '待关联',
}

const purchaseCities = ['北京', '上海', '广州', '成都', '武汉', '沈阳', '西安', '德州'] as const

const riskLabels: Record<string, string> = {
  HIGH: '高风险',
  MID: '中风险',
  LOW: '低风险',
}

const trendTagType = (value?: string) => {
  if (value === 'UP') return 'danger'
  if (value === 'DOWN') return 'success'
  return 'info'
}

const confidenceTagType = (value?: string) => {
  if (value === 'HIGH') return 'success'
  if (value === 'LOW') return 'warning'
  return 'info'
}

const riskTagType = (value?: string) => {
  if (value === 'HIGH') return 'danger'
  if (value === 'MID') return 'warning'
  return 'success'
}

const numberValue = (value?: number | null, digits = 0) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

const percentValue = (value?: number | null, digits = 1) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return `${(Number(value) * 100).toFixed(digits)}%`
}

const signedPercent = (value?: number | null) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  const percent = Number(value) * 100
  return `${percent > 0 ? '+' : ''}${percent.toFixed(1)}%`
}

const forecastDelta = (rawRow: unknown) => {
  const row = rawRow as ForecastRow
  return Number(row.adjusted_pred_7d || 0) - Number(row.base_pred_7d || 0)
}

const forecastDeltaClass = (row: unknown) => {
  const delta = forecastDelta(row)
  return delta > 0 ? 'delta-up' : delta < 0 ? 'delta-down' : 'delta-flat'
}

const categoryText = (rawRow: unknown) => {
  const row = rawRow as ForecastRow
  return row.category || row.category_l3 || row.category_l2 || row.category_l1 || '-'
}

const asNumber = (value?: number | null) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return null
  return Number(value)
}

const toChartNumber = (value?: number | null) => {
  const current = asNumber(value)
  return current === null ? 0 : current
}

const detailPredicted7dTotal = computed(() => (
  toChartNumber(selectedForecast.value?.adjusted_pred_7d ?? selectedForecast.value?.base_pred_7d)
))

const detailSuggestedQtyTotal = computed(() => (
  cityRows.value.reduce((total, row) => total + toChartNumber(row.suggested_qty), 0)
))

const detailShortageQtyTotal = computed(() => (
  cityRows.value.reduce((total, row) => total + toChartNumber(row.shortage_qty), 0)
))

const detailSalesTrendRows = computed(() => {
  const forecast = selectedForecast.value
  if (!forecast) return []

  const predictedDaily = detailPredicted7dTotal.value / 7
  return [
    { name: '近30日', value: toChartNumber(forecast.recent_30d_avg), forecast: false },
    { name: '近14日', value: toChartNumber(forecast.recent_14d_avg), forecast: false },
    { name: '近7日', value: toChartNumber(forecast.recent_7d_avg), forecast: false },
    { name: '近3日', value: toChartNumber(forecast.recent_3d_avg), forecast: false },
    { name: '未来7日', value: predictedDaily, forecast: true },
  ].filter((row) => row.value > 0)
})

const hasDetailObservationChart = computed(() => (
  selectedForecast.value?.sku_link_status !== 'PENDING_LINK'
  && detailSalesTrendRows.value.length > 0
))

const detailSalesTrendMax = computed(() => (
  Math.max(1, ...detailSalesTrendRows.value.map((row) => row.value)) * 1.12
))

const detailSalesTrendPoints = computed(() => {
  const rows = detailSalesTrendRows.value
  const max = detailSalesTrendMax.value
  const left = 34
  const top = 16
  const width = 336
  const height = 132
  const divisor = Math.max(rows.length - 1, 1)
  return rows.map((row, index) => ({
    ...row,
    x: left + (width * index) / divisor,
    y: top + height - (row.value / max) * height,
  }))
})

const detailSalesHistoryPolyline = computed(() => (
  detailSalesTrendPoints.value
    .filter((point) => !point.forecast)
    .map((point) => `${point.x},${point.y}`)
    .join(' ')
))

const detailSalesForecastSegment = computed(() => {
  const points = detailSalesTrendPoints.value
  const forecastPoint = points.find((point) => point.forecast)
  const lastHistoryPoint = [...points].reverse().find((point) => !point.forecast)
  if (!forecastPoint || !lastHistoryPoint) return ''
  return `${lastHistoryPoint.x},${lastHistoryPoint.y} ${forecastPoint.x},${forecastPoint.y}`
})

const detailKeyDriverRows = computed(() => {
  const forecast = selectedForecast.value
  if (!forecast) return []
  return primarySignalRows(forecast).slice(0, 3)
})

const detailForecastConclusion = computed(() => {
  const forecast = selectedForecast.value
  if (!forecast) return ''
  const futureDaily = detailPredicted7dTotal.value / 7
  const recent30 = toChartNumber(forecast.recent_30d_avg)
  const recent3 = toChartNumber(forecast.recent_3d_avg)
  const compare30 = futureDaily >= recent30 ? '高于' : '低于'
  const compare3 = futureDaily >= recent3 ? '高于' : '低于'
  return `未来7日预计日均 ${numberValue(futureDaily, 1)} 件，${compare30}近30日 ${numberValue(recent30, 1)} 件，${compare3}近3日 ${numberValue(recent3, 1)} 件。`
})

const detailForecastWhy = computed(() => {
  const forecast = selectedForecast.value
  if (!forecast) return ''
  const futureDaily = detailPredicted7dTotal.value / 7
  const recent3 = toChartNumber(forecast.recent_3d_avg)
  const recent7 = toChartNumber(forecast.recent_7d_avg)
  const drivers = detailKeyDriverRows.value.map((item) => `${item.label}${signalToneText(item.score)}`)
  const driverText = drivers.length ? `主要驱动是${drivers.join('、')}。` : '经营信号整体比较平稳。'
  if (recent3 < recent7 && futureDaily > recent3) {
    return `近3日比近7日回落，但综合信号仍支撑未来预测上修，${driverText}`
  }
  return driverText
})

const plainMomentum = (value?: number | null, upText = '变多', downText = '变少') => {
  const current = asNumber(value)
  if (current === null) return ''
  if (current >= 0.2) return `${upText}很明显`
  if (current >= 0.08) return upText
  if (current <= -0.2) return `${downText}很明显`
  if (current <= -0.08) return downText
  return ''
}

const signalLabels: Record<SignalKey, string> = {
  sales: '销量趋势',
  traffic: '流量热度',
  interest: '加购兴趣',
  conversion: '成交转化',
  quality: '成交质量',
}

const signalMetrics: Record<SignalKey, string> = {
  sales: '成交商品件数',
  traffic: '浏览量、访客数、人均浏览量、平均停留时长',
  interest: '加购人数、加购转化率、加购商品件数',
  conversion: '成交人数、成交转化率、成交单量',
  quality: '成交金额、成交客单价',
}

const fallbackSignalWeights: Record<SignalKey, number> = {
  sales: 0.35,
  traffic: 0.2,
  interest: 0.2,
  conversion: 0.15,
  quality: 0.1,
}

const parseReasonJson = (rawRow: unknown): Record<string, any> => {
  const row = rawRow as ForecastRow
  const value = row.reason_json
  if (!value) return {}
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value)
      return parsed && typeof parsed === 'object' ? parsed : {}
    } catch {
      return {}
    }
  }
  return value && typeof value === 'object' ? value as Record<string, any> : {}
}

const signalScoreFallback = (row: ForecastRow, key: SignalKey) => {
  if (key === 'sales') return asNumber(row.unit_momentum)
  if (key === 'traffic') return asNumber(row.visitor_momentum)
  if (key === 'interest') return asNumber(row.cart_momentum)
  if (key === 'conversion') return asNumber(row.conversion_momentum)
  return null
}

const signalScore = (rawRow: unknown, key: SignalKey) => {
  const row = rawRow as ForecastRow
  const reason = parseReasonJson(row)
  const scores = reason.signal_scores && typeof reason.signal_scores === 'object'
    ? reason.signal_scores as Record<string, unknown>
    : {}
  return asNumber(scores[key] as number | null) ?? signalScoreFallback(row, key)
}

const signalWeightText = (rawRow: unknown, key: SignalKey) => {
  const reason = parseReasonJson(rawRow)
  const weights = reason.signal_weights && typeof reason.signal_weights === 'object'
    ? reason.signal_weights as Record<string, unknown>
    : {}
  const weight = asNumber(weights[key] as number | null) ?? fallbackSignalWeights[key]
  return `${Math.round(weight * 100)}%`
}

const signalTone = (score: number | null) => {
  if (score === null || Math.abs(score) < 0.04) return 'neutral'
  return score > 0 ? 'up' : 'down'
}

const signalToneText = (score: number | null) => {
  if (score === null) return '暂无'
  if (score >= 0.2) return '明显推高'
  if (score >= 0.04) return '轻微推高'
  if (score <= -0.2) return '明显压低'
  if (score <= -0.04) return '轻微压低'
  return '基本稳定'
}

const signalReasonText = (key: SignalKey, score: number | null) => {
  const tone = signalToneText(score)
  if (key === 'sales') return `${tone}：看近3/7/14/30日成交件数变化。`
  if (key === 'traffic') return `${tone}：看浏览、访客、访问深度和停留时长。`
  if (key === 'interest') return `${tone}：看用户是否更愿意加购和加购件数。`
  if (key === 'conversion') return `${tone}：看成交人数、成交率和订单数是否跟上。`
  return `${tone}：看成交金额和客单价是否支撑需求质量。`
}

const businessSignalRows = (rawRow: unknown): BusinessSignalRow[] => (
  (['sales', 'traffic', 'interest', 'conversion', 'quality'] as SignalKey[]).map((key) => {
    const score = signalScore(rawRow, key)
    return {
      key,
      label: signalLabels[key],
      score,
      weight: signalWeightText(rawRow, key),
      metrics: signalMetrics[key],
      reason: signalReasonText(key, score),
    }
  })
)

const mainBusinessSignalRows = (rawRow: unknown) => (
  businessSignalRows(rawRow).filter((item) => item.key !== 'quality')
)

const supportBusinessSignalRows = (rawRow: unknown) => (
  businessSignalRows(rawRow).filter((item) => item.key === 'quality' && item.score !== null && Math.abs(item.score) >= 0.08)
)

const primarySignalRows = (rawRow: unknown) => (
  mainBusinessSignalRows(rawRow)
    .filter((item) => item.score !== null && Math.abs(item.score) >= 0.04)
    .sort((a, b) => Math.abs(b.score || 0) - Math.abs(a.score || 0))
)

const signalImpactText = (rawRow: unknown) => {
  const rows = primarySignalRows(rawRow)
  if (!rows.length) return '各经营信号整体稳定'
  return rows.slice(0, 4).map((item) => `${item.label}${signalToneText(item.score)}`).join('、')
}

const businessBasisSummary = (rawRow: unknown) => {
  const row = rawRow as ForecastRow
  if (row.trend_level === 'UP') {
    return row.confidence_level === 'HIGH'
      ? '这个 SKU 最近卖得更快，先当重点款盯库存。'
      : '这个 SKU 有变热的苗头，先看看八大仓库存够不够。'
  }
  if (row.trend_level === 'DOWN') return '这个 SKU 最近热度在降，补货先稳一点。'
  return '这个 SKU 最近变化不大，按正常节奏看库存就行。'
}

const businessDemandText = (rawRow: unknown) => {
  const row = rawRow as ForecastRow
  const adjusted = numberValue(row.adjusted_pred_7d, 1)
  const base = numberValue(row.base_pred_7d, 1)
  const delta = forecastDelta(row)
  if (Math.abs(delta) < 0.05) return `未来7天大概卖 ${adjusted} 件，和原来判断差不多。`
  return `未来7天大概卖 ${adjusted} 件，原来估 ${base} 件，现在看要${delta > 0 ? '多备' : '少备'}约 ${numberValue(Math.abs(delta), 1)} 件。`
}

const businessReasonText = (rawRow: unknown) => {
  const row = rawRow as ForecastRow
  const signals = primarySignalRows(row)
  if (signals.length) return `综合看${signals.slice(0, 3).map((item) => `${item.label}${signalToneText(item.score)}`).join('、')}，所以系统把未来需求重新估了一下。`
  const reasons = [
    plainMomentum(row.unit_momentum, '卖得更快', '卖得变慢'),
    plainMomentum(row.visitor_momentum, '看的人变多', '看的人变少'),
    plainMomentum(row.cart_momentum, '加购变多', '加购变少'),
    plainMomentum(row.conversion_momentum, '下单意愿变强', '下单意愿变弱'),
  ].filter(Boolean)
  if (reasons.length) return `主要是${reasons.slice(0, 3).join('、')}，所以系统把未来需求重新估了一下。`
  return '最近卖货、访客、加购都没明显变化，所以预测基本没动。'
}

const businessActionText = (rawRow: unknown) => {
  const row = rawRow as ForecastRow
  if (row.sku_link_status === 'PENDING_LINK') return '先把这个商品和库存 SKU 对上号；没对上前，只看全国趋势，不生成城市补货。'
  const warehouses = numberValue(row.affected_warehouse_count)
  const suggestions = numberValue(row.suggestion_count)
  if (row.trend_level === 'UP') return `先看八大仓里库存紧的仓；目前 ${warehouses} 个仓要留意，系统给了 ${suggestions} 条观察建议。`
  if (row.trend_level === 'DOWN') return '先不要因为这条趋势加码补货，等销量回暖后再提高优先级。'
  return `正常看八大仓即可；目前 ${warehouses} 个仓要留意，系统给了 ${suggestions} 条观察建议。`
}

const businessConfidenceText = (rawRow: unknown) => {
  const row = rawRow as ForecastRow
  const confidence = confidenceLabels[row.confidence_level] || '-'
  return `系统参考了最近 ${numberValue(row.days_covered)} 天数据，近30天成交 ${numberValue(row.total_30d_units, 1)} 件；数据越多越稳，当前把握：${confidence}。`
}

const basisText = (rawRow: unknown) => {
  return [
    businessBasisSummary(rawRow),
    businessDemandText(rawRow),
    businessReasonText(rawRow),
    businessActionText(rawRow),
  ].join(' ')
}

const explainRowKey = (row: ForecastRow) => `${row.sku_code}-${row.forecast_date || filters.forecastDate}`

const getExplainMessages = (row: ForecastRow) => {
  const key = explainRowKey(row)
  if (!explainMessagesBySku[key]) {
    explainMessagesBySku[key] = []
  }
  return explainMessagesBySku[key]
}

const isExplainLoading = (rawRow: unknown) => {
  const row = rawRow as ForecastRow
  return explainLoading.value && explainLoadingKey.value === explainRowKey(row)
}

const scrollExplainToBottom = async () => {
  await nextTick()
  if (explainBodyRef.value) {
    explainBodyRef.value.scrollTop = explainBodyRef.value.scrollHeight
  }
}

const splitMarkdownTableRow = (line: string) => {
  const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '')
  return trimmed.split('|').map((cell) => cell.trim())
}

const parseMarkdownTables = (raw: string) => {
  const lines = raw.split('\n')
  const output: string[] = []
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]
    const next = lines[index + 1] || ''
    const isTableStart = line.trim().startsWith('|') && /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(next)
    if (!isTableStart) {
      output.push(line)
      continue
    }

    const header = splitMarkdownTableRow(line)
    index += 2
    const bodyRows: string[][] = []
    while (index < lines.length && lines[index].trim().startsWith('|')) {
      bodyRows.push(splitMarkdownTableRow(lines[index]))
      index += 1
    }
    index -= 1

    const thead = `<thead><tr>${header.map((cell) => `<th>${cell}</th>`).join('')}</tr></thead>`
    const tbody = bodyRows.length
      ? `<tbody>${bodyRows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join('')}</tr>`).join('')}</tbody>`
      : ''
    output.push(`<table>${thead}${tbody}</table>`)
  }
  return output.join('\n')
}

const parseMarkdown = (raw: string): string => {
  if (!raw) return ''

  let html = raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_match, _language, code) => `<pre><code>${code}</code></pre>`)
  html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>')
  html = html.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/^#### ([^\n]+)\s*$/gm, '<h4>$1</h4>')
  html = html.replace(/^### ([^\n]+)\s*$/gm, '<h3>$1</h3>')
  html = html.replace(/^## ([^\n]+)\s*$/gm, '<h2>$1</h2>')
  html = html.replace(/^# ([^\n]+)\s*$/gm, '<h1>$1</h1>')
  html = parseMarkdownTables(html)
  html = html.replace(/^[\s]*[-*] ([^\n]+)\s*$/gm, '<li>$1</li>')
  html = html.replace(/(<li>.*<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`)

  const blockTags = ['<h1', '<h2', '<h3', '<h4', '<ul', '<pre', '<p', '<table']
  return html
    .split('\n')
    .map((line) => {
      const trimmed = line.trim()
      if (!trimmed) return ''
      if (blockTags.some((tag) => trimmed.startsWith(tag))) return line
      return `<p>${line}</p>`
    })
    .filter(Boolean)
    .join('')
}

const getErrorMessage = (error: unknown, fallback: string) => {
  if (!error || typeof error !== 'object') return fallback
  const candidate = error as {
    message?: string
    response?: { data?: { detail?: string; message?: string } }
  }
  return candidate.response?.data?.detail || candidate.response?.data?.message || candidate.message || fallback
}

const loadOptions = async () => {
  const response = await request.get('/inventory/business-forecast/options') as { data: ForecastOptions }
  Object.assign(options, emptyOptions(), response.data || {})
  if (!filters.forecastDate && options.forecast_dates.length) {
    filters.forecastDate = options.forecast_dates[0]
  }
  if (!filters.businessDate && options.business_dates.length) {
    filters.businessDate = options.business_dates[0]
  }
}

const applyLatestForecastDate = () => {
  if (options.forecast_dates.length) {
    filters.forecastDate = options.forecast_dates[0]
  }
  if (options.business_dates.length) {
    filters.businessDate = options.business_dates[0]
  }
}

const loadSummary = async () => {
  const response = await request.get('/inventory/business-forecast/summary', {
    params: { forecast_date: activeForecastDate.value || undefined },
  }) as { data: ForecastSummary }
  Object.assign(summary, response.data || {})
}

const currentForecastParams = () => ({
  forecast_date: activeForecastDate.value || undefined,
  sku_code: filters.skuCode.trim() || undefined,
  product_name: filters.productName.trim() || undefined,
  brand: filters.brand || undefined,
  category: filters.category || undefined,
  trend_level: filters.trendLevel || undefined,
  confidence_level: filters.confidenceLevel || undefined,
  sku_link_status: filters.linkStatus || undefined,
})

const loadForecasts = async () => {
  tableLoading.value = true
  try {
    const response = await request.get('/inventory/business-forecast/forecasts', {
      params: {
        ...currentForecastParams(),
        page: page.value,
        page_size: pageSize.value,
      },
    }) as ListResponse
    rows.value = response.items || []
    total.value = response.total || 0
  } finally {
    tableLoading.value = false
  }
}

const loadPurchaseRows = async () => {
  purchaseLoading.value = true
  try {
    const response = await request.get('/inventory/business-forecast/purchase-rows', {
      params: {
        ...currentForecastParams(),
        page: purchasePage.value,
        page_size: purchasePageSize.value,
      },
    }) as PurchaseRowsResponse
    purchaseRows.value = response.items || []
    purchaseTotal.value = response.total || 0
    purchaseTotalQty.value = response.total_qty || 0
    purchaseFilterBrands.value = response.brands || []
    purchaseFilterCategories.value = response.categories || []
  } finally {
    purchaseLoading.value = false
  }
}

const refreshData = async (settings: { useLatest?: boolean } = {}) => {
  errorMessage.value = ''
  try {
    if (settings.useLatest) {
      await loadOptions()
      applyLatestForecastDate()
      page.value = 1
      purchasePage.value = 1
    }
    await Promise.all([loadSummary(), loadForecasts(), loadPurchaseRows()])
  } catch (error) {
    errorMessage.value = getErrorMessage(error, '经营趋势预测数据加载失败')
  }
}

const refreshLatestData = async () => {
  await refreshData({ useLatest: true })
}

defineExpose({ refreshData, refreshLatestData })

const initialize = async () => {
  loading.value = true
  errorMessage.value = ''
  try {
    await loadOptions()
    await Promise.all([loadSummary(), loadForecasts(), loadPurchaseRows()])
  } catch (error) {
    errorMessage.value = getErrorMessage(error, '经营趋势预测页面初始化失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  page.value = 1
  purchasePage.value = 1
  void refreshData()
}

const resetFilters = () => {
  filters.skuCode = ''
  filters.productName = ''
  filters.brand = ''
  filters.category = ''
  filters.trendLevel = ''
  filters.confidenceLevel = ''
  filters.linkStatus = ''
  page.value = 1
  purchasePage.value = 1
  void refreshData()
}

const handleForecastDateChange = () => {
  page.value = 1
  purchasePage.value = 1
  void refreshData()
}

const handleBusinessDateChange = () => {
  if (options.forecast_dates.includes(filters.businessDate)) {
    filters.forecastDate = filters.businessDate
    page.value = 1
    purchasePage.value = 1
    void refreshData()
  }
}

const handlePageChange = (nextPage: number) => {
  page.value = nextPage
  void loadForecasts().catch((error) => {
    errorMessage.value = getErrorMessage(error, '预测列表加载失败')
  })
}

const handlePageSizeChange = (nextSize: number) => {
  pageSize.value = nextSize
  page.value = 1
  void loadForecasts().catch((error) => {
    errorMessage.value = getErrorMessage(error, '预测列表加载失败')
  })
}

const handlePurchasePageChange = (nextPage: number) => {
  purchasePage.value = nextPage
  void loadPurchaseRows().catch((error) => {
    errorMessage.value = getErrorMessage(error, '补货导出明细加载失败')
  })
}

const handlePurchasePageSizeChange = (nextSize: number) => {
  purchasePageSize.value = nextSize
  purchasePage.value = 1
  void loadPurchaseRows().catch((error) => {
    errorMessage.value = getErrorMessage(error, '补货导出明细加载失败')
  })
}

const handleUploadChange = (file: UploadFile) => {
  uploadFile.value = file.raw || null
}

const handleUploadRemove = () => {
  uploadFile.value = null
}

const importExcel = async () => {
  if (!uploadFile.value) {
    ElMessage.warning('请先选择经营报表 Excel 文件')
    return
  }

  actionLoading.value = true
  errorMessage.value = ''
  try {
    const formData = new FormData()
    formData.append('file', uploadFile.value)
    formData.append('auto_calculate', 'true')
    const response = await request.post('/inventory/business-forecast/import', formData) as {
      message?: string
      data?: {
        import?: { max_biz_date?: string }
        forecast?: { forecast_date?: string }
      }
    }
    const forecastDate = response.data?.forecast?.forecast_date || response.data?.import?.max_biz_date || ''
    filters.businessDate = response.data?.import?.max_biz_date || filters.businessDate
    filters.forecastDate = forecastDate || filters.forecastDate
    uploadFile.value = null
    uploadRef.value?.clearFiles()
    await loadOptions()
    page.value = 1
    purchasePage.value = 1
    await Promise.all([loadSummary(), loadForecasts(), loadPurchaseRows()])
    emit('data-updated')
    ElMessage.success(response.message || '经营报表导入并预测完成')
  } catch (error) {
    errorMessage.value = getErrorMessage(error, '经营报表导入失败')
  } finally {
    actionLoading.value = false
  }
}

const recalculate = async () => {
  actionLoading.value = true
  errorMessage.value = ''
  try {
    const response = await request.post('/inventory/business-forecast/recalculate', {
      forecast_date: filters.businessDate || filters.forecastDate || null,
      sku_codes: [],
    }) as { message?: string; data?: { forecast_date?: string } }
    filters.forecastDate = response.data?.forecast_date || filters.businessDate || filters.forecastDate
    await loadOptions()
    page.value = 1
    purchasePage.value = 1
    await Promise.all([loadSummary(), loadForecasts(), loadPurchaseRows()])
    emit('data-updated')
    ElMessage.success(response.message || '经营趋势预测重算完成')
  } catch (error) {
    errorMessage.value = getErrorMessage(error, '经营趋势预测重算失败')
  } finally {
    actionLoading.value = false
  }
}

const exportFileName = () => {
  const brand = filters.brand.trim()
  if (!brand) return '全部导出.xlsx'
  return `${brand.replace(/[\\/:*?"<>|]/g, '').trim() || brand}补货.xlsx`
}

const exportPurchaseExcel = async () => {
  if (purchaseTotal.value <= 0) {
    ElMessage.warning('当前筛选下没有可导出的补货明细')
    return
  }

  exportLoading.value = true
  errorMessage.value = ''
  try {
    const response = await request.get('/inventory/business-forecast/export-purchase', {
      params: currentForecastParams(),
      responseType: 'blob',
    } as any) as Blob
    const blob = response instanceof Blob
      ? response
      : new Blob([response as BlobPart], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    const filename = exportFileName()
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success(`已导出：${filename}`)
  } catch (error) {
    errorMessage.value = getErrorMessage(error, '经营趋势补货表导出失败')
  } finally {
    exportLoading.value = false
  }
}

const purchaseCityQty = (rawRow: unknown, city: typeof purchaseCities[number]) => {
  const row = rawRow as Partial<PurchaseRow>
  return Number(row[city] || 0)
}

const purchaseReasonDetails = (rawRow: unknown) => {
  const row = rawRow as PurchaseRow
  return Array.isArray(row.purchase_reason_details) ? row.purchase_reason_details : []
}

const purchaseReasonSummary = (rawRow: unknown) => {
  const row = rawRow as PurchaseRow
  return row.purchase_reason_summary || row.purchase_reason || '暂无原因'
}

const purchaseRowBrand = (rawRow: unknown) => {
  const row = rawRow as PurchaseRow
  return row.brand || '-'
}

const purchaseRowCategory = (rawRow: unknown) => {
  const row = rawRow as PurchaseRow
  return row.category || row.category_l1 || row.category_l2 || row.category_l3 || '-'
}

const uniqueFilterValues = (values: string[], currentValue = '') => {
  const unique = Array.from(new Set(values.map((item) => item.trim()).filter(Boolean))).sort((a, b) => a.localeCompare(b, 'zh-CN'))
  const current = currentValue.trim()
  if (current && !unique.includes(current)) {
    return [current, ...unique]
  }
  return unique
}

const brandFilterOptions = computed(() => {
  if (props.mode !== 'purchase') return options.brands
  return uniqueFilterValues(
    purchaseFilterBrands.value,
    filters.brand,
  )
})

const categoryFilterOptions = computed(() => {
  if (props.mode !== 'purchase') return options.categories
  return uniqueFilterValues(
    purchaseFilterCategories.value,
    filters.category,
  )
})

const openDetail = async (rawRow: unknown) => {
  const row = rawRow as ForecastRow
  selectedForecast.value = row
  cityRows.value = []
  detailError.value = ''
  detailVisible.value = true
  detailLoading.value = true
  try {
    const response = await request.get('/inventory/business-forecast/detail', {
      params: {
        sku_code: row.sku_code,
        forecast_date: row.forecast_date || filters.forecastDate || undefined,
      },
    }) as DetailResponse
    selectedForecast.value = response.forecast || row
    cityRows.value = response.cities || []
  } catch (error) {
    detailError.value = getErrorMessage(error, '城市预测明细加载失败')
  } finally {
    detailLoading.value = false
  }
}

const openForecastExplain = (rawRow: unknown) => {
  const row = rawRow as ForecastRow
  selectedExplainForecast.value = row
  explainVisible.value = true
  getExplainMessages(row)
  void scrollExplainToBottom()
}

const sendForecastExplainMessage = async (presetMessage?: string) => {
  const row = selectedExplainForecast.value
  if (!row || explainLoading.value) return

  const content = (presetMessage ?? explainInput.value).trim()
  if (!content) {
    ElMessage.warning('请输入要问AI助手的问题')
    return
  }

  const messages = getExplainMessages(row)
  const history = messages.slice(-8)
  const userIndex = messages.length
  messages.push({ role: 'user', content })
  const assistantIndex = messages.length
  messages.push({ role: 'assistant', content: '' })
  explainInput.value = ''
  explainLoading.value = true
  explainLoadingKey.value = explainRowKey(row)
  void scrollExplainToBottom()

  try {
    const response = await request.post('/ai/business_forecast/explain', {
      sku_code: row.sku_code,
      forecast_date: row.forecast_date || filters.forecastDate || null,
      message: content,
      messages: history,
    }, { silent: true } as any) as ForecastExplainResponse
    const answer = (response.answer || '').trim()
    if (!answer) {
      throw new Error('AI 未返回有效解释')
    }
    messages[assistantIndex].content = answer
  } catch (error) {
    messages.splice(userIndex)
    ElMessage.error(getErrorMessage(error, '经营趋势 AI 解释生成失败'))
  } finally {
    explainLoading.value = false
    explainLoadingKey.value = ''
    void scrollExplainToBottom()
  }
}

onMounted(() => {
  void initialize()
})
</script>

<template>
  <div class="forecast-workbench">
    <header v-if="props.mode === 'forecast'" class="page-heading">
      <div class="heading-copy">
        <div class="title-line">
          <el-icon><TrendCharts /></el-icon>
          <h1>经营趋势预测</h1>
          <el-tag type="warning" effect="plain" size="small">观察模式</el-tag>
        </div>
        <p>未来 7 天趋势预警 · 不写入今日调拨建议</p>
      </div>
      <div class="heading-meta">
        <span>预测窗口</span>
        <strong>{{ targetWindow }}</strong>
      </div>
    </header>

    <section v-if="props.mode === 'forecast'" class="action-band" aria-label="经营报表操作">
      <el-upload
        ref="uploadRef"
        class="excel-upload"
        accept=".xlsx"
        :auto-upload="false"
        :limit="1"
        :on-change="handleUploadChange"
        :on-remove="handleUploadRemove"
      >
        <el-button :icon="Upload" :disabled="actionLoading">选择 Excel</el-button>
      </el-upload>
      <el-button
        type="primary"
        :icon="DocumentChecked"
        :loading="actionLoading"
        :disabled="!uploadFile"
        @click="importExcel"
      >
        导入并预测
      </el-button>
      <span class="action-divider" />
      <el-select
        v-model="filters.businessDate"
        class="date-select"
        placeholder="经营日期"
        clearable
        filterable
        @change="handleBusinessDateChange"
      >
        <el-option v-for="item in options.business_dates" :key="item" :label="item" :value="item" />
      </el-select>
      <el-tooltip content="以所选经营日期为基准重算未来 7 天预测" placement="bottom">
        <el-button :icon="Refresh" :loading="actionLoading" @click="recalculate">重算预测</el-button>
      </el-tooltip>
    </section>

    <el-alert
      v-if="errorMessage"
      class="page-alert"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
    >
      <template #default>
        <el-button size="small" @click="initialize">重新加载</el-button>
      </template>
    </el-alert>

    <el-skeleton v-if="loading" class="loading-shell" :rows="10" animated />

    <template v-else>
      <section v-if="props.mode === 'forecast'" class="kpi-grid" aria-label="预测概览">
        <article class="kpi-item kpi-neutral">
          <span>预测 SKU</span>
          <strong>{{ numberValue(summary.forecast_sku_count) }}</strong>
          <small>经营数据 {{ businessDataRange }}</small>
        </article>
        <article class="kpi-item kpi-good">
          <span>已关联库存</span>
          <strong>{{ numberValue(summary.linked_sku_count) }}</strong>
          <small>可生成城市风险拆分</small>
        </article>
        <article class="kpi-item kpi-warning">
          <span>待关联 SKU</span>
          <strong>{{ numberValue(summary.pending_link_count) }}</strong>
          <small>保留全国预测，不生成城市补货</small>
        </article>
        <article class="kpi-item kpi-danger">
          <span>高置信上涨</span>
          <strong>{{ numberValue(summary.up_high_count) }}</strong>
          <small>优先观察需求抬升</small>
        </article>
        <article class="kpi-item kpi-blue">
          <span>风险城市仓</span>
          <strong>{{ numberValue(summary.affected_warehouse_count) }}</strong>
          <small>{{ numberValue(summary.suggestion_count) }} 个观察补货建议</small>
        </article>
      </section>

      <section class="filter-band" aria-label="预测筛选">
        <template v-if="props.mode === 'forecast'">
          <el-select
            v-model="filters.forecastDate"
            class="filter-control date-select"
            placeholder="预测批次"
            clearable
            filterable
            @change="handleForecastDateChange"
          >
            <el-option v-for="item in options.forecast_dates" :key="item" :label="item" :value="item" />
          </el-select>
        </template>
        <template v-else>
          <div class="purchase-latest-batch">最新批次：{{ purchaseLatestBatchText }}</div>
        </template>
        <el-input v-model="filters.skuCode" class="filter-control keyword-input" placeholder="SKU" clearable @keyup.enter="handleSearch" />
        <el-input v-model="filters.productName" class="filter-control name-input" placeholder="商品名称" clearable @keyup.enter="handleSearch" />
        <el-select v-model="filters.brand" class="filter-control" placeholder="品牌" clearable filterable>
          <el-option v-for="item in brandFilterOptions" :key="item" :label="item" :value="item" />
        </el-select>
        <el-select v-model="filters.category" class="filter-control" placeholder="类目" clearable filterable>
          <el-option v-for="item in categoryFilterOptions" :key="item" :label="item" :value="item" />
        </el-select>
        <el-select v-if="props.mode === 'forecast'" v-model="filters.trendLevel" class="filter-control" placeholder="趋势" clearable>
          <el-option v-for="item in options.trend_levels" :key="item" :label="trendLabels[item] || item" :value="item" />
        </el-select>
        <el-select v-if="props.mode === 'forecast'" v-model="filters.confidenceLevel" class="filter-control" placeholder="置信度" clearable>
          <el-option v-for="item in options.confidence_levels" :key="item" :label="confidenceLabels[item] || item" :value="item" />
        </el-select>
        <el-select v-if="props.mode === 'forecast'" v-model="filters.linkStatus" class="filter-control" placeholder="关联状态" clearable>
          <el-option v-for="item in options.sku_link_statuses" :key="item" :label="linkLabels[item] || item" :value="item" />
        </el-select>
        <div class="filter-actions">
          <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </div>
      </section>

      <section v-if="props.mode === 'purchase'" class="purchase-panel">
        <div class="purchase-toolbar">
          <div>
            <h2>补货导出明细</h2>
            <span>导出前确认 · 只展示八大仓当天需要补货的 SKU · 共 {{ numberValue(purchaseTotal) }} 个 SKU · 合计补货 {{ numberValue(purchaseTotalQty) }} 件</span>
            <em
              class="purchase-formula-badge"
              :class="props.purchaseFormula === 'excel' ? 'is-excel' : 'is-system'"
            >
              {{ props.purchaseFormula === 'excel' ? '运营表算法' : '现行算法' }}
            </em>
          </div>
          <div class="purchase-export-action">
            <el-button
              type="success"
              :icon="Download"
              :loading="exportLoading"
              :disabled="loading || purchaseLoading || actionLoading || purchaseTotal <= 0"
              @click="exportPurchaseExcel"
            >
              导出补货表
            </el-button>
            <span>可先选择品牌后导出；不选品牌则导出当前全部明细</span>
          </div>
        </div>
        <el-table
          v-loading="purchaseLoading"
          :data="purchaseRows"
          stripe
          table-layout="fixed"
          class="purchase-table"
        >
          <el-table-column label="商品编号" prop="sku_code" width="135" fixed="left" />
          <el-table-column label="商品名称" min-width="260" fixed="left">
            <template #default="{ row }">
              <el-tooltip :content="row.product_name || '-'" placement="top">
                <span class="purchase-product-name">{{ row.product_name || '-' }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="品牌" width="150" show-overflow-tooltip>
            <template #default="{ row }">{{ purchaseRowBrand(row) }}</template>
          </el-table-column>
          <el-table-column label="类目" width="92" show-overflow-tooltip>
            <template #default="{ row }">{{ purchaseRowCategory(row) }}</template>
          </el-table-column>
          <el-table-column label="采购原因" min-width="70">
            <template #default="{ row }">
              <el-popover
                placement="left-start"
                trigger="hover"
                width="760"
                popper-class="purchase-reason-popover"
                :show-after="120"
                :hide-after="80"
              >
                <template #reference>
                  <span class="purchase-reason-detail">查看</span>
                </template>
                <div class="purchase-reason-card">
                  <div class="purchase-reason-card-head">
                    <strong>采购原因</strong>
                    <span>{{ row.sku_code }}</span>
                  </div>
                  <div class="purchase-reason-summary">
                    <span>补货结论</span>
                    <p>{{ purchaseReasonSummary(row) }}</p>
                  </div>
                  <div v-if="purchaseReasonDetails(row).length" class="purchase-reason-detail-table">
                    <div class="purchase-reason-table-head">
                      <span>仓库</span>
                      <span>补货</span>
                      <span>未来7天</span>
                      <span>库存</span>
                      <span>在途</span>
                      <span>花东仓数量</span>
                      <span>含在途可售 / 安全线</span>
                      <span>参考路径</span>
                    </div>
                    <div
                      v-for="detail in purchaseReasonDetails(row)"
                      :key="`${row.sku_code}-${detail.city}`"
                      class="purchase-reason-table-row"
                    >
                      <strong>{{ detail.city }}</strong>
                      <b>{{ numberValue(detail.suggested_qty) }} 件</b>
                      <span>{{ numberValue(detail.predicted_city_7d, 1) }} 件</span>
                      <span>{{ numberValue(detail.stock_qty, 0) }} 件</span>
                      <span>{{ numberValue(detail.inbound_qty, 0) }} 件</span>
                      <span>{{ numberValue(detail.huadong_available_qty, 0) }} 件</span>
                      <span>{{ numberValue(detail.days_of_supply, 1) }} / {{ numberValue(detail.target_days, 0) }} 天</span>
                      <span class="purchase-reason-route">
                        {{ detail.route_path || '暂未匹配路径' }}
                        <em v-if="detail.eta_days">约{{ detail.eta_days }}天</em>
                      </span>
                    </div>
                  </div>
                </div>
              </el-popover>
            </template>
          </el-table-column>
          <el-table-column
            v-for="city in purchaseCities"
            :key="city"
            :label="city"
            width="74"
            align="right"
          >
            <template #default="{ row }">
              <strong
                :class="{
                  'qty-positive': purchaseCityQty(row, city) > 0,
                  'qty-negative': purchaseCityQty(row, city) < 0,
                }"
              >
                {{ numberValue(purchaseCityQty(row, city)) }}
              </strong>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty description="当前筛选下暂无八大仓补货数量，可换个品牌/SKU或部署到有聚水潭库存数据的环境后再看" :image-size="82" />
          </template>
        </el-table>
        <div v-if="purchaseTotal > 0" class="pagination-row compact-pagination">
          <el-pagination
            v-model:current-page="purchasePage"
            v-model:page-size="purchasePageSize"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next"
            :total="purchaseTotal"
            @current-change="handlePurchasePageChange"
            @size-change="handlePurchasePageSizeChange"
          />
        </div>
      </section>

      <section v-if="props.mode === 'forecast'" class="table-panel">
        <div class="table-toolbar">
          <div>
            <h2>SKU 预测清单</h2>
            <span>共 {{ numberValue(total) }} 条</span>
          </div>
          <div class="table-legend">
            <span><i class="legend-dot dot-danger" />上涨</span>
            <span><i class="legend-dot dot-neutral" />稳定</span>
            <span><i class="legend-dot dot-success" />下降</span>
          </div>
        </div>

        <el-table
          v-loading="tableLoading"
          :data="rows"
          stripe
          table-layout="fixed"
          class="forecast-table"
        >
          <el-table-column label="SKU / 商品" min-width="220" fixed="left">
            <template #default="{ row }">
              <div class="sku-cell">
                <strong>{{ row.sku_code }}</strong>
                <el-tooltip :content="row.product_name || '-'" placement="top">
                  <span>{{ row.product_name || '-' }}</span>
                </el-tooltip>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="品牌 / 类目" min-width="150">
            <template #default="{ row }">
              <div class="stacked-cell">
                <span>{{ row.brand || '-' }}</span>
                <small>{{ categoryText(row) }}</small>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="趋势" width="92" align="center">
            <template #default="{ row }">
              <el-tag :type="trendTagType(row.trend_level)" size="small" effect="light">
                {{ trendLabels[row.trend_level] || row.trend_level }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="置信度" width="96" align="center">
            <template #default="{ row }">
              <el-tag :type="confidenceTagType(row.confidence_level)" size="small" effect="plain">
                {{ confidenceLabels[row.confidence_level] || row.confidence_level }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="原始7天预测" width="120" align="right">
            <template #default="{ row }"><strong>{{ numberValue(row.base_pred_7d, 1) }}</strong></template>
          </el-table-column>
          <el-table-column label="经营修正后" width="120" align="right">
            <template #default="{ row }"><strong class="adjusted-value">{{ numberValue(row.adjusted_pred_7d, 1) }}</strong></template>
          </el-table-column>
          <el-table-column label="需求变化" width="105" align="right">
            <template #default="{ row }">
              <span :class="forecastDeltaClass(row)">
                {{ forecastDelta(row) > 0 ? '+' : '' }}{{ numberValue(forecastDelta(row), 1) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="关联状态" width="102" align="center">
            <template #default="{ row }">
              <el-tag :type="row.sku_link_status === 'LINKED' ? 'success' : 'warning'" size="small" effect="plain">
                {{ linkLabels[row.sku_link_status] || row.sku_link_status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column width="112" align="center">
            <template #header>
              <el-tooltip content="点击下方数字可打开八大仓城市补货观察" placement="top">
                <span class="column-help">城市观察</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <button class="city-counts city-counts-action" type="button" @click.stop="openDetail(row)">
                <strong>{{ numberValue(row.affected_warehouse_count) }}</strong>
                <small>{{ numberValue(row.suggestion_count) }} 条建议</small>
              </button>
            </template>
          </el-table-column>
          <el-table-column label="预测依据" width="92" align="center">
            <template #default="{ row }">
              <el-popover
                placement="left-start"
                trigger="hover"
                width="620"
                popper-class="forecast-basis-popover"
                :show-after="120"
                :hide-after="80"
              >
                <template #reference>
                  <span class="basis-detail-btn" @click.stop @mousedown.stop>查看</span>
                </template>
                <div class="basis-card">
                  <div class="basis-card-head">
                    <strong>预测依据</strong>
                    <span>{{ row.sku_code }}</span>
                  </div>
                  <div class="basis-card-body">
                    <p class="basis-main">{{ businessBasisSummary(row) }}</p>
                    <p><span>预计变化</span><strong>{{ businessDemandText(row) }}</strong></p>
                    <p><span>为什么</span><strong>{{ businessReasonText(row) }}</strong></p>
                    <p><span>综合信号</span><strong>{{ signalImpactText(row) }}</strong></p>
                    <p><span>怎么处理</span><strong>{{ businessActionText(row) }}</strong></p>
                    <p><span>靠不靠谱</span><strong>{{ businessConfidenceText(row) }}</strong></p>
                  </div>
                  <div class="basis-signal-table">
                    <div class="basis-signal-row basis-signal-head">
                      <span>主要依据</span>
                      <span>影响</span>
                      <span>权重</span>
                      <span>包含指标</span>
                    </div>
                    <div
                      v-for="signal in mainBusinessSignalRows(row)"
                      :key="signal.key"
                      class="basis-signal-row"
                    >
                      <strong>{{ signal.label }}</strong>
                      <em :class="`signal-tone-${signalTone(signal.score)}`">{{ signalToneText(signal.score) }}</em>
                      <span>{{ signal.weight }}</span>
                      <small>{{ signal.metrics }}</small>
                    </div>
                  </div>
                  <div v-if="supportBusinessSignalRows(row).length" class="basis-support-row">
                    <span>辅助参考</span>
                    <strong
                      v-for="signal in supportBusinessSignalRows(row)"
                      :key="signal.key"
                      :class="`signal-tone-${signalTone(signal.score)}`"
                    >
                      {{ signal.label }}{{ signalToneText(signal.score) }}：{{ signal.metrics }}
                    </strong>
                  </div>
                </div>
              </el-popover>
            </template>
          </el-table-column>
          <el-table-column label="AI解释" width="108" align="center" fixed="right">
            <template #default="{ row }">
              <el-button
                text
                type="primary"
                :icon="ChatDotRound"
                :loading="isExplainLoading(row)"
                :disabled="explainLoading && !isExplainLoading(row)"
                @click.stop="openForecastExplain(row)"
              >
                AI解释
              </el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty description="当前筛选条件下暂无预测数据" :image-size="88" />
          </template>
        </el-table>

        <div v-if="hasData || total > 0" class="pagination-row">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            background
            layout="total, sizes, prev, pager, next, jumper"
            :page-sizes="[20, 50, 100, 200]"
            :total="total"
            @current-change="handlePageChange"
            @size-change="handlePageSizeChange"
          />
        </div>
      </section>
    </template>

    <el-drawer v-model="detailVisible" size="min(920px, 94vw)" class="detail-drawer">
      <template #header>
        <div class="drawer-heading">
          <div>
            <span>城市补货观察</span>
            <strong>{{ selectedForecast?.sku_code || '-' }}</strong>
          </div>
          <el-tag type="warning" effect="plain">仅观察</el-tag>
        </div>
      </template>

      <el-alert v-if="detailError" :title="detailError" type="error" show-icon :closable="false" />
      <el-skeleton v-if="detailLoading" :rows="8" animated />

      <template v-else-if="selectedForecast">
        <section class="detail-summary">
          <div class="detail-product">
            <strong>{{ selectedForecast.product_name || '-' }}</strong>
            <span>{{ selectedForecast.brand || '-' }} · {{ categoryText(selectedForecast) }}</span>
          </div>
          <div>
            <span>未来 7 天</span>
            <strong>{{ numberValue(selectedForecast.adjusted_pred_7d, 1) }}</strong>
          </div>
          <div>
            <span>修正系数</span>
            <strong>{{ numberValue(selectedForecast.adjustment_factor, 3) }}</strong>
          </div>
          <div>
            <span>趋势 / 置信度</span>
            <strong>{{ trendLabels[selectedForecast.trend_level] || '-' }} · {{ confidenceLabels[selectedForecast.confidence_level] || '-' }}</strong>
          </div>
        </section>

        <div class="basis-strip">
          <el-icon><DataAnalysis /></el-icon>
          <span>{{ basisText(selectedForecast) }}</span>
        </div>

        <el-alert
          v-if="selectedForecast.sku_link_status === 'PENDING_LINK'"
          title="该 SKU 待关联库存，仅保留全国趋势预测，不生成城市补货观察。"
          type="warning"
          show-icon
          :closable="false"
        />

        <el-table v-else :data="cityRows" stripe class="city-table" table-layout="fixed">
          <el-table-column prop="warehouse_code" label="城市仓" min-width="90" fixed="left" />
          <el-table-column label="未来7天需求" width="118" align="right">
            <template #default="{ row }">{{ numberValue(row.predicted_city_7d, 1) }}</template>
          </el-table-column>
          <el-table-column label="库存" width="80" align="right">
            <template #default="{ row }">{{ numberValue(row.stock_qty, 0) }}</template>
          </el-table-column>
          <el-table-column label="在途" width="80" align="right">
            <template #default="{ row }">{{ numberValue(row.inbound_qty, 0) }}</template>
          </el-table-column>
          <el-table-column label="可售天数" width="100" align="right">
            <template #default="{ row }">{{ numberValue(row.days_of_supply, 1) }}</template>
          </el-table-column>
          <el-table-column label="风险" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="riskTagType(row.risk_level)" size="small" effect="light">
                {{ riskLabels[row.risk_level] || row.risk_level || '-' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="观察补货" width="90" align="right">
            <template #default="{ row }"><strong>{{ numberValue(row.suggested_qty, 0) }}</strong></template>
          </el-table-column>
          <el-table-column prop="route_path" label="参考路径" min-width="150" show-overflow-tooltip />
          <el-table-column label="时效" width="76" align="center">
            <template #default="{ row }">{{ row.eta_days ? `${row.eta_days}天` : '-' }}</template>
          </el-table-column>
          <template #empty>
            <el-empty description="没有符合经营条件的城市仓" :image-size="80" />
          </template>
        </el-table>

        <div v-if="hasDetailObservationChart" class="detail-chart-card">
          <div class="detail-chart-head">
            <div>
              <strong>SKU 销量变化</strong>
              <span>按近30日、近14日、近7日、近3日和未来7日预测日均销量看变化</span>
            </div>
            <div class="detail-chart-kpis">
              <span>未来7天 {{ numberValue(detailPredicted7dTotal, 1) }} 件</span>
              <span>观察补货 {{ numberValue(detailSuggestedQtyTotal) }} 件</span>
              <span>缺口 {{ numberValue(detailShortageQtyTotal) }} 件</span>
            </div>
          </div>
          <div class="detail-forecast-explain">
            <div class="detail-forecast-main">
              <span>预测结论</span>
              <strong>{{ detailForecastConclusion }}</strong>
              <p>{{ detailForecastWhy }}</p>
            </div>
            <div class="detail-forecast-drivers">
              <span>关键驱动</span>
              <div>
                <em
                  v-for="driver in detailKeyDriverRows"
                  :key="driver.key"
                  :class="`signal-tone-${signalTone(driver.score)}`"
                >
                  {{ driver.label }} · {{ signalToneText(driver.score) }}
                </em>
                <em v-if="!detailKeyDriverRows.length" class="signal-tone-neutral">经营信号稳定</em>
              </div>
            </div>
          </div>
          <div class="detail-chart-panel detail-chart-panel-wide">
            <div class="detail-chart-label-row">
              <span class="detail-chart-label">SKU 销量变化（日均件数）</span>
              <div class="detail-chart-legend">
                <span><i class="legend-history"></i>历史真实</span>
                <span><i class="legend-forecast"></i>未来预测</span>
              </div>
            </div>
            <svg class="detail-sales-svg" viewBox="0 0 400 190" role="img" aria-label="SKU 销量变化图">
                <line x1="34" y1="148" x2="378" y2="148" class="chart-axis" />
                <line x1="34" y1="16" x2="34" y2="148" class="chart-axis" />
                <line
                  v-for="tick in [0, 1, 2, 3]"
                  :key="`sales-grid-${tick}`"
                  x1="34"
                  :y1="16 + tick * 44"
                  x2="378"
                  :y2="16 + tick * 44"
                  class="chart-grid-line"
                />
                <polyline :points="detailSalesHistoryPolyline" class="sales-trend-line" />
                <polyline v-if="detailSalesForecastSegment" :points="detailSalesForecastSegment" class="sales-forecast-line" />
                <g v-for="point in detailSalesTrendPoints" :key="point.name">
                  <circle
                    :cx="point.x"
                    :cy="point.y"
                    r="4.5"
                    :class="point.forecast ? 'sales-forecast-dot' : 'sales-trend-dot'"
                  />
                  <text :x="point.x" :y="Math.max(12, point.y - 9)" text-anchor="middle" class="sales-trend-value">
                    {{ numberValue(point.value, 1) }}
                  </text>
                  <text :x="point.x" y="174" text-anchor="middle" class="sales-trend-label">
                    {{ point.name }}
                  </text>
                </g>
            </svg>
          </div>
        </div>
      </template>
    </el-drawer>

    <el-drawer v-model="explainVisible" direction="rtl" size="90vw" class="explain-drawer">
      <template #header>
        <div class="explain-agent-header">
          <div class="explain-agent-title">
            <strong>经营趋势 AI 助手</strong>
            <span v-if="selectedExplainForecast">
              {{ selectedExplainForecast.sku_code }} · {{ selectedExplainForecast.brand || '-' }}
            </span>
          </div>
          <el-tag type="warning" effect="plain">观察信号</el-tag>
        </div>
      </template>

      <template v-if="selectedExplainForecast">
        <div class="explain-agent-shell">
          <aside class="explain-agent-data">
            <section class="explain-agent-summary">
              <div>
                <span>SKU</span>
                <strong>{{ selectedExplainForecast.sku_code }}</strong>
              </div>
              <div>
                <span>品牌 / 类目</span>
                <strong>{{ selectedExplainForecast.brand || '-' }} · {{ categoryText(selectedExplainForecast) }}</strong>
              </div>
              <div class="wide">
                <span>商品名称</span>
                <strong :title="selectedExplainForecast.product_name">{{ selectedExplainForecast.product_name || '-' }}</strong>
              </div>
              <div>
                <span>趋势 / 置信度</span>
                <strong>
                  {{ trendLabels[selectedExplainForecast.trend_level] || '-' }} ·
                  {{ confidenceLabels[selectedExplainForecast.confidence_level] || '-' }}
                </strong>
              </div>
              <div>
                <span>未来 7 天</span>
                <strong class="adjusted-value">{{ numberValue(selectedExplainForecast.adjusted_pred_7d, 1) }} 件</strong>
              </div>
              <div>
                <span>需求变化</span>
                <strong :class="forecastDeltaClass(selectedExplainForecast)">
                  {{ forecastDelta(selectedExplainForecast) > 0 ? '+' : '' }}{{ numberValue(forecastDelta(selectedExplainForecast), 1) }} 件
                </strong>
              </div>
              <div>
                <span>八仓风险</span>
                <strong>{{ numberValue(selectedExplainForecast.affected_warehouse_count) }} 个</strong>
              </div>
              <div>
                <span>观察建议</span>
                <strong>{{ numberValue(selectedExplainForecast.suggestion_count) }} 条</strong>
              </div>
            </section>

            <section class="explain-agent-basis">
              <div class="explain-agent-section-title">
                <strong>预测依据</strong>
                <span>已带入右侧 AI 助手</span>
              </div>
              <div class="explain-agent-basis-list">
                <p class="basis-main">{{ businessBasisSummary(selectedExplainForecast) }}</p>
                <p><span>预计变化</span><strong>{{ businessDemandText(selectedExplainForecast) }}</strong></p>
                <p><span>为什么</span><strong>{{ businessReasonText(selectedExplainForecast) }}</strong></p>
                <p><span>综合信号</span><strong>{{ signalImpactText(selectedExplainForecast) }}</strong></p>
                <p><span>怎么处理</span><strong>{{ businessActionText(selectedExplainForecast) }}</strong></p>
                <p><span>靠不靠谱</span><strong>{{ businessConfidenceText(selectedExplainForecast) }}</strong></p>
              </div>
              <div class="explain-signal-list">
                <div
                  v-for="signal in mainBusinessSignalRows(selectedExplainForecast)"
                  :key="signal.key"
                  :class="`signal-tone-${signalTone(signal.score)}`"
                >
                  <span>{{ signal.label }}</span>
                  <strong>{{ signalToneText(signal.score) }}</strong>
                  <em>{{ signal.weight }}</em>
                </div>
              </div>
              <div v-if="supportBusinessSignalRows(selectedExplainForecast).length" class="explain-support-list">
                <span>辅助参考</span>
                <strong
                  v-for="signal in supportBusinessSignalRows(selectedExplainForecast)"
                  :key="signal.key"
                  :class="`signal-tone-${signalTone(signal.score)}`"
                >
                  {{ signal.label }}{{ signalToneText(signal.score) }}
                </strong>
              </div>
            </section>

            <div class="explain-observation-note">
              经营趋势只用于观察和复盘，不修改今日调拨建议，最终补货数量仍以库存主引擎为准。
            </div>
          </aside>

          <section class="explain-agent-chat">
            <div ref="explainBodyRef" class="explain-agent-messages">
              <div v-if="!activeExplainMessages.length" class="explain-empty-choice">
                <strong>你想先了解哪一块？</strong>
                <span>AI 已带入当前 SKU、趋势、预测、八仓风险和观察建议，选择一个问题后再开始分析。</span>
                <div class="explain-choice-grid">
                  <el-button
                    v-for="item in explainStarterPrompts"
                    :key="item.label"
                    :disabled="explainLoading"
                    plain
                    type="primary"
                    @click="sendForecastExplainMessage(item.message)"
                  >
                    {{ item.label }}
                  </el-button>
                </div>
              </div>

              <div
                v-for="(message, index) in activeExplainMessages"
                :key="`${message.role}-${index}`"
                class="explain-message"
                :class="message.role"
              >
                <div
                  v-if="message.role === 'assistant' && message.content"
                  class="explain-bubble markdown-body"
                  v-html="parseMarkdown(message.content)"
                />
                <div v-else-if="message.role === 'assistant'" class="explain-bubble muted">AI助手正在分析...</div>
                <div v-else class="explain-bubble">{{ message.content }}</div>
              </div>
            </div>

            <div class="explain-quick-actions">
              <el-button :disabled="explainLoading" size="small" @click="sendForecastExplainMessage('为什么这个SKU值得关注？')">
                为什么关注
              </el-button>
              <el-button :disabled="explainLoading" size="small" @click="sendForecastExplainMessage('运营今天应该先看什么？')">
                今天看什么
              </el-button>
              <el-button :disabled="explainLoading" size="small" @click="sendForecastExplainMessage('帮我写成一句运营汇报。')">
                生成汇报
              </el-button>
            </div>

            <div class="explain-input-row">
              <el-input
                v-model="explainInput"
                :autosize="{ minRows: 2, maxRows: 4 }"
                :disabled="explainLoading"
                placeholder="继续问这个 SKU 的经营趋势..."
                type="textarea"
                @keydown.enter.exact.prevent="sendForecastExplainMessage()"
              />
              <el-button :disabled="explainLoading" :loading="explainLoading" type="primary" @click="sendForecastExplainMessage()">
                发送
              </el-button>
            </div>
          </section>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.forecast-workbench {
  width: 100%;
  min-width: 0;
  padding: 22px 24px 36px;
  color: var(--text-primary);
}

.page-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 18px;
}

.heading-copy,
.heading-meta,
.sku-cell,
.stacked-cell,
.city-counts,
.stacked-number,
.detail-product {
  min-width: 0;
}

.title-line {
  display: flex;
  align-items: center;
  gap: 9px;
}

.title-line > .el-icon {
  color: var(--primary);
  font-size: 23px;
}

.title-line h1 {
  margin: 0;
  color: var(--text-heading);
  font-size: 22px;
  font-weight: 750;
  letter-spacing: 0;
}

.heading-copy p {
  margin: 7px 0 0 32px;
  color: var(--text-secondary);
  font-size: 13px;
}

.heading-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 3px;
  font-size: 12px;
  white-space: nowrap;
}

.heading-meta span {
  color: var(--text-muted);
}

.heading-meta strong {
  color: var(--text-secondary);
  font-size: 13px;
}

.action-band,
.filter-band {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--border-color);
  background: var(--app-surface);
}

.action-band {
  border-radius: 6px 6px 0 0;
}

.excel-upload {
  min-width: 0;
}

.excel-upload :deep(.el-upload-list) {
  display: inline-block;
  max-width: 240px;
  margin: 0 0 0 10px;
  vertical-align: middle;
}

.excel-upload :deep(.el-upload-list__item) {
  margin: 0;
}

.action-divider {
  width: 1px;
  height: 24px;
  margin: 0 2px;
  background: var(--border-color);
}

.date-select {
  width: 155px;
}

.purchase-latest-batch {
  display: inline-flex;
  align-items: center;
  min-height: 36px;
  padding: 0 12px;
  border: 1px solid light-dark(#dbe4f2, var(--border-color));
  border-radius: 6px;
  background: light-dark(#f8fbff, var(--app-surface-2));
  color: light-dark(#64748b, var(--text-secondary));
  font-size: 13px;
  white-space: nowrap;
}

.page-alert {
  margin-top: 12px;
}

.loading-shell {
  margin-top: 16px;
  padding: 18px;
  border: 1px solid var(--border-color);
  background: var(--app-surface);
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(130px, 1fr));
  border-right: 1px solid var(--border-color);
  border-bottom: 1px solid var(--border-color);
  border-left: 1px solid var(--border-color);
  background: var(--app-surface);
}

.kpi-item {
  position: relative;
  display: flex;
  min-width: 0;
  min-height: 112px;
  flex-direction: column;
  justify-content: center;
  padding: 15px 16px 14px;
  border-right: 1px solid var(--border-subtle);
  overflow: hidden;
}

.kpi-item:last-child {
  border-right: 0;
}

.kpi-item::before {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  height: 3px;
  background: #64748b;
  content: '';
}

.kpi-good::before { background: #0f766e; }
.kpi-warning::before { background: #d97706; }
.kpi-danger::before { background: #dc2626; }
.kpi-blue::before { background: #2563eb; }

.kpi-item span {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 650;
}

.kpi-item strong {
  margin-top: 6px;
  color: var(--text-heading);
  font-size: 25px;
  line-height: 1.1;
}

.kpi-item small {
  margin-top: 7px;
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.35;
}

.filter-band {
  flex-wrap: wrap;
  margin-top: 14px;
  border-radius: 6px;
}

.filter-control {
  width: 128px;
}

.keyword-input {
  width: 138px;
}

.name-input {
  width: 170px;
}

.filter-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.purchase-panel {
  min-width: 0;
  margin-top: 14px;
  border: 1px solid light-dark(#bfdbfe, var(--border-color));
  border-radius: 6px;
  background: light-dark(#f8fbff, var(--app-surface-2));
  overflow: hidden;
}

.purchase-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 58px;
  padding: 11px 14px;
  border-bottom: 1px solid light-dark(#dbeafe, var(--border-color));
  background: light-dark(#eff6ff, rgba(96, 165, 250, .12));
}

.purchase-toolbar > div:first-child {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.purchase-toolbar h2 {
  margin: 0;
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 16px;
}

.purchase-toolbar span {
  color: light-dark(#475569, var(--text-secondary));
  font-size: 12px;
}

.purchase-formula-badge {
  display: inline-flex;
  align-self: flex-start;
  margin-top: 2px;
  padding: 1px 8px;
  border-radius: 10px;
  font-style: normal;
  font-size: 11px;
  line-height: 18px;
  border: 1px solid transparent;
}

.purchase-formula-badge.is-system {
  color: light-dark(#475569, var(--text-secondary));
  background: light-dark(#e2e8f0, rgba(96, 165, 250, .12));
  border-color: light-dark(#cbd5e1, var(--border-color));
}

.purchase-formula-badge.is-excel {
  color: light-dark(#b45309, #fbbf24);
  background: light-dark(#fef3c7, rgba(251, 191, 36, .12));
  border-color: light-dark(#fcd34d, var(--border-color));
}

.purchase-export-action {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 5px;
  flex-shrink: 0;
}

.purchase-export-action span {
  color: light-dark(#64748b, var(--text-secondary));
  font-size: 12px;
  line-height: 1.2;
  white-space: nowrap;
}

.purchase-table {
  width: 100%;
  overflow: visible;
}

.purchase-table :deep(.el-table__inner-wrapper),
.purchase-table :deep(.el-table__body-wrapper),
.purchase-table :deep(.el-scrollbar),
.purchase-table :deep(.el-scrollbar__wrap),
.purchase-table :deep(.el-scrollbar__view) {
  overflow: visible;
}

.purchase-table :deep(.el-table__header-wrapper) {
  position: sticky;
  top: 56px;
  z-index: 12;
  background: light-dark(#f8fbff, var(--app-surface-2));
  box-shadow: 0 1px 0 #dbeafe;
}

.purchase-table :deep(.el-table__header-wrapper th),
.purchase-table :deep(.el-table__header-wrapper tr) {
  background: light-dark(#f8fbff, var(--app-surface-2));
}

.purchase-table :deep(.el-table__cell) {
  padding: 8px 0;
}

.purchase-product-name {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  color: light-dark(#334155, var(--text-primary));
  text-overflow: ellipsis;
  white-space: nowrap;
}

.purchase-reason-detail {
  display: inline-flex;
  align-items: center;
  height: 26px;
  padding: 0 10px;
  border-radius: 6px;
  background: light-dark(#eff6ff, rgba(96, 165, 250, .12));
  color: light-dark(#2563eb, #93c5fd);
  cursor: help;
  font-size: 13px;
  font-weight: 700;
}

:global(.purchase-reason-popover.el-popper) {
  padding: 0;
  border: 1px solid light-dark(#cbd5e1, var(--border-color));
  border-radius: 8px;
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.16);
}

.purchase-reason-card {
  overflow: hidden;
  border-radius: 8px;
  background: light-dark(#fff, var(--app-surface));
}

.purchase-reason-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  background: light-dark(#f8fafc, var(--app-surface-2));
  border-bottom: 1px solid light-dark(#e2e8f0, var(--border-color));
}

.purchase-reason-card-head strong {
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 14px;
}

.purchase-reason-card-head span {
  color: light-dark(#64748b, var(--text-secondary));
  font-size: 12px;
  white-space: nowrap;
}

.purchase-reason-summary {
  padding: 12px 14px 10px;
  border-bottom: 1px solid light-dark(#e2e8f0, var(--border-color));
}

.purchase-reason-summary span {
  display: inline-flex;
  margin-bottom: 6px;
  padding: 2px 7px;
  border-radius: 999px;
  background: light-dark(#eff6ff, rgba(96, 165, 250, .12));
  color: light-dark(#2563eb, #93c5fd);
  font-size: 12px;
  font-weight: 700;
}

.purchase-reason-summary p {
  margin: 0;
  color: light-dark(#1e293b, var(--text-primary));
  font-size: 13px;
  line-height: 1.65;
  white-space: normal;
  word-break: break-word;
}

.purchase-reason-detail-table {
  max-height: 310px;
  overflow: auto;
}

.purchase-reason-table-head,
.purchase-reason-table-row {
  display: grid;
  grid-template-columns: 58px 58px 76px 58px 58px 84px 132px minmax(150px, 1fr);
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid light-dark(#edf2f7, var(--border-color));
  color: light-dark(#475569, var(--text-secondary));
  font-size: 12px;
}

.purchase-reason-table-head {
  position: sticky;
  top: 0;
  z-index: 1;
  background: light-dark(#f8fafc, var(--app-surface-2));
  color: light-dark(#64748b, var(--text-secondary));
  font-weight: 700;
}

.purchase-reason-table-row strong {
  color: light-dark(#0f172a, var(--text-primary));
}

.purchase-reason-table-row b {
  color: light-dark(#dc2626, #f87171);
}

.purchase-reason-route {
  overflow: hidden;
  color: light-dark(#334155, var(--text-primary));
  text-overflow: ellipsis;
  white-space: nowrap;
}

.purchase-reason-route em {
  margin-left: 6px;
  color: light-dark(#64748b, var(--text-secondary));
  font-style: normal;
}

.qty-positive {
  color: light-dark(#dc2626, #f87171);
}

.qty-negative {
  color: light-dark(#16a34a, #6ee7b7);
  font-weight: 500;
}

.compact-pagination {
  padding: 8px 12px 10px;
  background: light-dark(#fff, var(--app-surface));
}

.table-panel {
  min-width: 0;
  margin-top: 14px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--app-surface);
  overflow: hidden;
}

.table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 54px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-subtle);
}

.table-toolbar > div:first-child {
  display: flex;
  align-items: baseline;
  gap: 9px;
}

.table-toolbar h2 {
  margin: 0;
  color: var(--text-heading);
  font-size: 15px;
}

.table-toolbar span {
  color: var(--text-secondary);
  font-size: 12px;
}

.table-legend {
  display: flex;
  align-items: center;
  gap: 13px;
}

.table-legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.column-help {
  display: inline-flex;
  align-items: center;
  border-bottom: 1px dotted currentColor;
  cursor: help;
}

.legend-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.dot-danger { background: #dc2626; }
.dot-neutral { background: #64748b; }
.dot-success { background: #059669; }

.forecast-table {
  width: 100%;
}

.forecast-table :deep(.el-table__cell) {
  padding: 9px 0;
}

.sku-cell,
.stacked-cell,
.city-counts,
.stacked-number {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.city-counts-action {
  width: 100%;
  margin: 0;
  padding: 4px 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
}

.city-counts-action:hover {
  background: light-dark(#eff6ff, rgba(96, 165, 250, .12));
}

.city-counts-action strong {
  color: light-dark(#334155, var(--text-primary));
}

.sku-cell strong {
  color: var(--text-heading);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
}

.sku-cell span,
.stacked-cell small,
.city-counts small,
.stacked-number small {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.basis-detail-btn {
  display: inline-flex;
  min-height: 24px;
  align-items: center;
  justify-content: center;
  padding: 0 10px;
  border-radius: 6px;
  background: light-dark(#eff6ff, rgba(96, 165, 250, .12));
  color: light-dark(#2563eb, #93c5fd);
  cursor: default;
  font-size: 13px;
  font-weight: 700;
  line-height: 24px;
}

:global(.forecast-basis-popover.el-popper) {
  padding: 0;
  border: 1px solid light-dark(#cbd5e1, var(--border-color));
  border-radius: 8px;
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.16);
}

.basis-card {
  overflow: hidden;
  border-radius: 8px;
  background: light-dark(#fff, var(--app-surface));
}

.basis-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid light-dark(#e2e8f0, var(--border-color));
  background: light-dark(#f8fafc, var(--app-surface-2));
}

.basis-card-head strong {
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 14px;
}

.basis-card-head span {
  color: light-dark(#64748b, var(--text-secondary));
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
  white-space: nowrap;
}

.basis-card-body {
  display: flex;
  flex-direction: column;
  padding: 10px 14px 12px;
}

.basis-card-body p {
  display: grid;
  grid-template-columns: 74px minmax(0, 1fr);
  align-items: start;
  gap: 12px;
  margin: 0;
  padding: 6px 0;
  color: light-dark(#475569, var(--text-secondary));
  font-size: 13px;
  line-height: 1.6;
}

.basis-card-body p + p {
  border-top: 1px dashed light-dark(#e2e8f0, var(--border-color));
}

.basis-card-body .basis-main {
  display: block;
  padding-top: 2px;
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 14px;
  font-weight: 700;
}

.basis-card-body p > span {
  color: light-dark(#64748b, var(--text-secondary));
  white-space: nowrap;
}

.basis-card-body p > strong {
  color: light-dark(#0f172a, var(--text-primary));
  font-weight: 500;
  overflow-wrap: anywhere;
}

.basis-signal-table {
  margin: 0 14px 14px;
  border: 1px solid light-dark(#e2e8f0, var(--border-color));
  border-radius: 6px;
  overflow: hidden;
}

.basis-signal-row {
  display: grid;
  grid-template-columns: 78px 82px 54px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-top: 1px solid light-dark(#edf2f7, var(--border-color));
  color: light-dark(#334155, var(--text-primary));
  font-size: 12px;
}

.basis-signal-row:first-child {
  border-top: 0;
}

.basis-signal-head {
  background: light-dark(#f8fafc, var(--app-surface-2));
  color: light-dark(#64748b, var(--text-secondary));
  font-weight: 800;
}

.basis-signal-row strong {
  color: light-dark(#0f172a, var(--text-primary));
}

.basis-signal-row em {
  font-style: normal;
  font-weight: 800;
}

.basis-signal-row small {
  color: light-dark(#64748b, var(--text-secondary));
  line-height: 1.45;
}

.basis-support-row {
  display: grid;
  grid-template-columns: 74px minmax(0, 1fr);
  gap: 10px;
  margin: -4px 14px 14px;
  padding: 8px 10px;
  border: 1px dashed light-dark(#dbe3ee, var(--border-color));
  border-radius: 6px;
  background: light-dark(#f8fafc, var(--app-surface-2));
  color: light-dark(#64748b, var(--text-secondary));
  font-size: 12px;
  line-height: 1.5;
}

.basis-support-row span {
  font-weight: 800;
  white-space: nowrap;
}

.basis-support-row strong {
  color: var(--signal-color, #475569);
  font-weight: 700;
  overflow-wrap: anywhere;
}

.signal-tone-up {
  color: light-dark(#dc2626, #f87171);
  --signal-color: #dc2626;
}

.signal-tone-down {
  color: light-dark(#059669, #6ee7b7);
  --signal-color: #059669;
}

.signal-tone-neutral {
  color: light-dark(#64748b, var(--text-secondary));
  --signal-color: #64748b;
}

.stacked-cell > span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.adjusted-value {
  color: light-dark(#0f766e, var(--text-accent));
}

.delta-up { color: light-dark(#dc2626, #f87171); font-weight: 700; }
.delta-down { color: light-dark(#059669, #6ee7b7); font-weight: 700; }
.delta-flat { color: var(--text-muted); }

.pagination-row {
  display: flex;
  justify-content: flex-end;
  padding: 12px 14px;
  border-top: 1px solid var(--border-subtle);
  overflow-x: auto;
}

.drawer-heading {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.drawer-heading > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}

.drawer-heading span {
  color: var(--text-secondary);
  font-size: 12px;
}

.drawer-heading strong {
  overflow: hidden;
  color: var(--text-heading);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 17px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-summary {
  display: grid;
  grid-template-columns: minmax(220px, 1.8fr) repeat(3, minmax(120px, 1fr));
  margin-bottom: 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--app-surface-2);
}

.detail-summary > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  justify-content: center;
  gap: 5px;
  min-height: 76px;
  padding: 11px 13px;
  border-right: 1px solid var(--border-subtle);
}

.detail-summary > div:last-child {
  border-right: 0;
}

.detail-summary span {
  color: var(--text-muted);
  font-size: 11px;
}

.detail-summary strong {
  overflow: hidden;
  color: var(--text-heading);
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-product > strong {
  font-size: 13px;
}

.basis-strip {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 12px;
  padding: 10px 12px;
  border-left: 3px solid #2563eb;
  background: rgba(37, 99, 235, 0.06);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.basis-strip .el-icon {
  flex: 0 0 auto;
  margin-top: 2px;
  color: light-dark(#2563eb, #93c5fd);
}

.city-table {
  margin-top: 12px;
  border: 1px solid var(--border-color);
}

.detail-chart-card {
  margin-top: 12px;
  padding: 12px 14px 10px;
  border: 1px solid light-dark(#dbe5f0, var(--border-color));
  border-radius: 8px;
  background: linear-gradient(180deg, light-dark(#ffffff, var(--app-surface)) 0%, light-dark(#f8fafc, var(--app-surface-2)) 100%);
}

.detail-chart-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 8px;
}

.detail-chart-head strong {
  display: block;
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 15px;
  font-weight: 850;
}

.detail-chart-head span {
  display: block;
  margin-top: 3px;
  color: light-dark(#64748b, var(--text-secondary));
  font-size: 12px;
}

.detail-chart-kpis {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
  min-width: 260px;
}

.detail-chart-kpis span {
  margin-top: 0;
  padding: 4px 8px;
  border: 1px solid light-dark(#dbeafe, var(--border-color));
  border-radius: 6px;
  background: light-dark(#eff6ff, rgba(96, 165, 250, .12));
  color: light-dark(#1d4ed8, #93c5fd);
  font-size: 12px;
  font-weight: 800;
}

.detail-forecast-explain {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(220px, 0.9fr);
  gap: 10px;
  margin-bottom: 10px;
}

.detail-forecast-main,
.detail-forecast-drivers {
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid light-dark(#dbeafe, var(--border-color));
  border-radius: 8px;
  background: light-dark(#eff6ff, rgba(96, 165, 250, .12));
}

.detail-forecast-main span,
.detail-forecast-drivers > span {
  display: block;
  margin-bottom: 5px;
  color: light-dark(#1d4ed8, #93c5fd);
  font-size: 12px;
  font-weight: 850;
}

.detail-forecast-main strong {
  display: block;
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 14px;
  line-height: 1.55;
}

.detail-forecast-main p {
  margin: 5px 0 0;
  color: light-dark(#334155, var(--text-primary));
  font-size: 12px;
  line-height: 1.6;
}

.detail-forecast-drivers > div {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.detail-forecast-drivers em {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(100, 116, 139, 0.12);
  color: var(--signal-color, #64748b);
  font-size: 12px;
  font-style: normal;
  font-weight: 850;
}

.detail-chart-panel {
  min-width: 0;
  padding: 10px 10px 4px;
  border: 1px solid light-dark(#e2e8f0, var(--border-color));
  border-radius: 8px;
  background: light-dark(#fff, var(--app-surface));
}

.detail-chart-panel-wide {
  width: 100%;
}

.detail-chart-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 4px;
}

.detail-chart-label {
  display: block;
  margin: 0;
  color: light-dark(#334155, var(--text-primary));
  font-size: 12px;
  font-weight: 850;
}

.detail-chart-legend {
  display: flex;
  align-items: center;
  gap: 10px;
  color: light-dark(#64748b, var(--text-secondary));
  font-size: 12px;
}

.detail-chart-legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.detail-chart-legend i {
  display: inline-block;
  width: 18px;
  height: 0;
  border-top: 3px solid currentColor;
}

.legend-history {
  color: light-dark(#2563eb, #93c5fd);
}

.legend-forecast {
  color: #f97316;
  border-top-style: dashed !important;
}

.detail-sales-svg {
  width: 100%;
  height: 280px;
  overflow: visible;
}

.chart-axis {
  stroke: #cbd5e1;
  stroke-width: 1;
}

.chart-grid-line {
  stroke: #eef2f7;
  stroke-width: 1;
}

.sales-trend-line {
  fill: none;
  stroke: #2563eb;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 3;
}

.sales-forecast-line {
  fill: none;
  stroke: #f97316;
  stroke-dasharray: 8 6;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 3;
}

.sales-trend-dot {
  fill: #ffffff;
  stroke: #2563eb;
  stroke-width: 3;
}

.sales-forecast-dot {
  fill: #fff7ed;
  stroke: #f97316;
  stroke-width: 3;
}

.sales-trend-value {
  fill: #0f172a;
  font-size: 11px;
  font-weight: 800;
}

.sales-trend-label {
  fill: #64748b;
  font-size: 11px;
  font-weight: 750;
}

.explain-agent-header {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.explain-agent-title {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.explain-agent-title strong {
  color: var(--text-heading);
  font-size: 16px;
}

.explain-agent-title span {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.explain-agent-shell {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  height: calc(100vh - 96px);
  min-height: 520px;
}

.explain-agent-data,
.explain-agent-chat {
  min-width: 0;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--app-surface);
}

.explain-agent-data {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px;
  overflow: auto;
}

.explain-agent-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: var(--app-surface-2);
  overflow: hidden;
}

.explain-agent-summary > div {
  display: flex;
  min-width: 0;
  min-height: 84px;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
  padding: 14px 16px;
  border-right: 1px solid var(--border-subtle);
  border-bottom: 1px solid var(--border-subtle);
}

.explain-agent-summary > div:nth-child(even),
.explain-agent-summary > div:last-child {
  border-right: 0;
}

.explain-agent-summary > div:nth-last-child(-n + 2) {
  border-bottom: 0;
}

.explain-agent-summary .wide {
  grid-column: 1 / -1;
}

.explain-agent-summary span {
  color: var(--text-muted);
  font-size: 12px;
}

.explain-agent-summary strong {
  overflow: hidden;
  color: var(--text-heading);
  font-size: 15px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.explain-agent-section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.explain-agent-section-title strong {
  color: var(--text-heading);
  font-size: 15px;
}

.explain-agent-section-title span {
  color: var(--text-muted);
  font-size: 12px;
}

.explain-agent-basis {
  padding: 14px 16px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: var(--app-surface-2);
}

.explain-agent-basis-list {
  display: flex;
  flex-direction: column;
}

.explain-agent-basis-list p {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr);
  gap: 14px;
  margin: 0;
  padding: 9px 0;
  color: light-dark(#475569, var(--text-secondary));
  font-size: 13px;
  line-height: 1.65;
}

.explain-agent-basis-list p + p {
  border-top: 1px dashed light-dark(#dbe3ee, var(--border-color));
}

.explain-agent-basis-list .basis-main {
  display: block;
  padding-top: 0;
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 15px;
  font-weight: 700;
}

.explain-agent-basis-list span {
  color: var(--text-muted);
  white-space: nowrap;
}

.explain-agent-basis-list strong {
  color: var(--text-heading);
  font-weight: 500;
  overflow-wrap: anywhere;
}

.explain-signal-list {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
  margin-top: 10px;
}

.explain-signal-list > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
  padding: 8px;
  border: 1px solid light-dark(#e2e8f0, var(--border-color));
  border-radius: 6px;
  background: light-dark(#fff, var(--app-surface));
}

.explain-signal-list span {
  color: light-dark(#64748b, var(--text-secondary));
  font-size: 11px;
}

.explain-signal-list strong {
  color: currentColor;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.explain-signal-list em {
  color: light-dark(#94a3b8, var(--text-secondary));
  font-size: 11px;
  font-style: normal;
}

.explain-support-list {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  padding: 8px 10px;
  border: 1px dashed light-dark(#cbd5e1, var(--border-color));
  border-radius: 6px;
  background: light-dark(#f8fafc, var(--app-surface-2));
  color: light-dark(#64748b, var(--text-secondary));
  font-size: 12px;
}

.explain-support-list span {
  font-weight: 800;
}

.explain-support-list strong {
  color: var(--signal-color, #334155);
  font-weight: 850;
}

.explain-observation-note {
  padding: 12px 14px;
  border-left: 3px solid #d97706;
  background: rgba(217, 119, 6, 0.07);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.65;
}

.explain-agent-chat {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.explain-agent-messages {
  flex: 1;
  min-height: 0;
  padding: 18px;
  overflow-y: auto;
}

.explain-empty-choice {
  display: flex;
  min-height: 100%;
  flex-direction: column;
  justify-content: center;
  gap: 12px;
  color: var(--text-secondary);
  text-align: center;
}

.explain-empty-choice strong {
  color: var(--text-heading);
  font-size: 18px;
}

.explain-empty-choice span {
  color: var(--text-muted);
  font-size: 13px;
}

.explain-choice-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 180px));
  justify-content: center;
  gap: 10px;
  margin-top: 8px;
}

.explain-choice-grid .el-button {
  margin: 0;
}

.explain-message {
  display: flex;
  margin-bottom: 12px;
}

.explain-message.user {
  justify-content: flex-end;
}

.explain-bubble {
  max-width: min(720px, 82%);
  padding: 10px 12px;
  border-radius: 8px;
  background: light-dark(#f1f5f9, var(--app-surface-2));
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.explain-message.user .explain-bubble {
  background: #2563eb;
  color: #fff;
}

.explain-bubble.muted {
  color: var(--text-muted);
}

.explain-quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 14px 0;
  border-top: 1px solid var(--border-subtle);
}

.explain-quick-actions .el-button {
  margin: 0;
}

.explain-input-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 78px;
  gap: 10px;
  padding: 12px 14px 14px;
}

.markdown-body :deep(p) {
  margin: 0 0 10px;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin: 14px 0 8px;
  color: var(--text-heading);
  font-size: 15px;
}

.markdown-body :deep(h1:first-child),
.markdown-body :deep(h2:first-child),
.markdown-body :deep(h3:first-child),
.markdown-body :deep(h4:first-child) {
  margin-top: 0;
}

.markdown-body :deep(ul) {
  margin: 8px 0 12px;
  padding-left: 20px;
}

.markdown-body :deep(code) {
  padding: 2px 5px;
  border-radius: 4px;
  background: var(--app-surface-2);
}

.markdown-body :deep(pre) {
  padding: 12px;
  border-radius: 6px;
  background: var(--app-surface-2);
  overflow-x: auto;
}

.markdown-body :deep(table) {
  width: 100%;
  margin: 10px 0 12px;
  border-collapse: collapse;
  border: 1px solid light-dark(#cbd5e1, var(--border-color));
  background: light-dark(#fff, var(--app-surface));
  font-size: 12px;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 7px 8px;
  border: 1px solid light-dark(#dbe3ee, var(--border-color));
  text-align: left;
  vertical-align: top;
}

.markdown-body :deep(th) {
  background: light-dark(#f8fafc, var(--app-surface-2));
  color: light-dark(#0f172a, var(--text-primary));
  font-weight: 800;
}

@media (max-width: 1280px) {
  .kpi-grid {
    grid-template-columns: repeat(5, minmax(110px, 1fr));
  }
}

@media (max-width: 760px) {
  .forecast-workbench {
    padding: 16px 12px 28px;
  }

  .page-heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }

  .heading-meta {
    align-items: flex-start;
    white-space: normal;
  }

  .title-line {
    flex-wrap: wrap;
  }

  .title-line h1 {
    font-size: 19px;
  }

  .heading-copy p {
    margin-left: 0;
  }

  .action-band {
    align-items: stretch;
    flex-direction: column;
  }

  .action-divider {
    width: 100%;
    height: 1px;
    margin: 2px 0;
  }

  .date-select,
  .filter-control,
  .keyword-input,
  .name-input {
    width: 100%;
  }

  .excel-upload :deep(.el-upload-list) {
    display: block;
    max-width: 100%;
    margin: 8px 0 0;
  }

  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .kpi-item,
  .kpi-item:nth-child(3) {
    min-height: 104px;
    border-right: 1px solid var(--border-subtle);
    border-bottom: 1px solid var(--border-subtle);
  }

  .kpi-item:nth-child(even) {
    border-right: 0;
  }

  .kpi-item:nth-last-child(-n + 2) {
    border-bottom: 1px solid var(--border-subtle);
  }

  .kpi-item:last-child {
    grid-column: 1 / -1;
    border-right: 0;
    border-bottom: 0;
  }

  .filter-actions {
    width: 100%;
    margin-left: 0;
  }

  .filter-actions .el-button {
    flex: 1;
  }

  .table-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .table-legend {
    flex-wrap: wrap;
  }

  .pagination-row {
    justify-content: flex-start;
  }

  .detail-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .detail-summary > div:nth-child(2) {
    border-right: 0;
  }

  .detail-summary > div:nth-child(-n + 2) {
    border-bottom: 1px solid var(--border-subtle);
  }

  .detail-summary strong {
    white-space: normal;
  }

  .explain-agent-shell {
    grid-template-columns: 1fr;
    height: auto;
  }

  .explain-agent-chat {
    min-height: 520px;
  }

  .explain-choice-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 430px) {
  .kpi-grid {
    grid-template-columns: 1fr;
  }

  .kpi-item,
  .kpi-item:nth-child(even),
  .kpi-item:nth-child(3) {
    border-right: 0;
    border-bottom: 1px solid var(--border-subtle);
  }

  .kpi-item:last-child {
    grid-column: auto;
    border-bottom: 0;
  }

  .detail-summary {
    grid-template-columns: 1fr;
  }

  .detail-summary > div,
  .detail-summary > div:nth-child(2) {
    border-right: 0;
    border-bottom: 1px solid var(--border-subtle);
  }

  .detail-summary > div:last-child {
    border-bottom: 0;
  }

  .explain-agent-summary {
    grid-template-columns: 1fr;
  }

  .explain-agent-summary > div,
  .explain-agent-summary > div:nth-child(even),
  .explain-agent-summary > div:nth-last-child(-n + 2) {
    border-right: 0;
    border-bottom: 1px solid var(--border-subtle);
  }

  .explain-agent-summary > div:last-child {
    border-bottom: 0;
  }

  .explain-input-row {
    grid-template-columns: 1fr;
  }
}
</style>
