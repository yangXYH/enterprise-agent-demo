<script setup lang="ts">
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, watch } from 'vue'
import {
  ElButton,
  ElCheckbox,
  ElCheckboxGroup,
  ElDialog,
  ElDrawer,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElInputNumber,
  ElMessage,
  ElNotification,
  ElOption,
  ElPagination,
  ElPopover,
  ElSelect,
  ElSwitch,
  ElTable,
  ElTableColumn,
  ElTabs,
  ElTabPane,
  ElTag,
  ElTooltip,
  ElUpload,
  type UploadFile,
  type UploadInstance,
  type UploadRawFile,
  type UploadUserFile,
} from 'element-plus'
import { Connection, Lock, MagicStick, Refresh, Search, Upload, UploadFilled } from '@element-plus/icons-vue'
import request from '../utils/request'
import BusinessForecast from './BusinessForecast.vue'
import SkuStockWarning from './SkuStockWarning.vue'

interface SummaryData {
  snapshot_date?: string | null
  sku_count?: number
  warehouse_count?: number
  risk_high?: number
  risk_mid?: number
  risk_low?: number
  plan_count?: number
  pending_count?: number
  high_plan_count?: number
  latest_batch?: Record<string, unknown> | null
}

interface TransferPlan {
  id: number
  plan_date?: string
  sku_code: string
  product_name: string
  brand: string
  category: string
  shop_name: string
  from_warehouse: string
  to_warehouse: string
  transfer_qty: number
  eta_days: number
  priority: string
  risk_level: string
  risk_days: number
  surplus_days_after: number
  eta_late: number
  source_type?: string
  route_path?: string
  target_days?: number
  reserve_days?: number
  supplier_eta_days?: number
  hub_eta_days?: number
  score: number
  reason: string
  status: string
  from_stock_qty?: number
  from_inbound_qty?: number
  from_sales_1d?: number
  from_sales_7d?: number
  from_sales_30d?: number
  from_daily_sales?: number
  from_demand_30d?: number
  to_stock_qty?: number
  to_inbound_qty?: number
  to_sales_1d?: number
  to_sales_7d?: number
  to_sales_30d?: number
  to_daily_sales?: number
  to_demand_30d?: number
}

interface SkuWarehouseRow {
  warehouse_code: string
  warehouse_name?: string
  region?: string
  stock_qty: number
  inbound_qty: number
  sales_1d: number
  sales_7d: number
  sales_30d: number
  daily_sales?: number
  target_days?: number
  demand_30d?: number
  days_of_supply?: number
  risk_level?: string
}

interface BusinessForecastRow {
  forecast_date?: string
  target_start_date?: string
  target_end_date?: string
  sku_code?: string
  sku_link_status?: string
  days_covered?: number
  total_30d_units?: number
  recent_3d_avg?: number
  recent_7d_avg?: number
  recent_14d_avg?: number
  recent_30d_avg?: number
  base_pred_7d?: number
  adjusted_pred_7d?: number
  predicted_7d?: number
  unit_momentum?: number
  visitor_momentum?: number
  cart_momentum?: number
  conversion_momentum?: number
  adjustment_factor?: number
  trend_level?: string
  confidence_level?: string
  affected_warehouse_count?: number
  suggestion_count?: number
  pending_city_split?: number | boolean
  actual_7d?: number | null
  forecast_error?: number | null
}

interface BusinessForecastCityRow {
  warehouse_code: string
  warehouse_name?: string
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

interface BusinessForecastAttachment {
  status: 'AVAILABLE' | 'NO_DATA' | 'UNAVAILABLE' | string
  forecast: BusinessForecastRow | null
  cities: BusinessForecastCityRow[]
}

interface ReplenishmentPolicy {
  id?: number
  policy_type: string
  brand: string
  category: string
  target_days: number
  reserve_days: number
  supplier_eta_days: number
  allow_jd_transfer: boolean | number
  preferred_source_warehouse: string
  remark?: string
}

interface HuadongSyncSetting {
  enabled: boolean
  interval_minutes: number
  recalculate: boolean
  last_run_at?: string | null
  last_status?: string
  last_message?: string
  last_result?: {
    progress?: HuadongSyncProgress
    total_skus?: number
    requested_skus?: number
    requested_query_codes?: number
    skipped_without_barcode?: number
    requested_chunks?: number
    accepted?: number
    api_rows?: number
    query_error_count?: number
    query_max_workers?: number
  } | null
  updated_at?: string | null
}

interface HuadongSyncProgress {
  phase?: string
  processed?: number
  total?: number
  percent?: number
  accepted?: number
  api_rows?: number
  errors?: number
  total_skus?: number
  requested_skus?: number
  requested_query_codes?: number
  skipped_without_barcode?: number
  query_max_workers?: number
}

interface SkuDecisionData {
  snapshot_date: string
  sku: {
    sku_code?: string
    product_name?: string
    brand?: string
    category?: string
    shop_name?: string
  }
  policy: ReplenishmentPolicy
  supply_hub: {
    warehouse_code: string
    stock?: {
      stock_qty?: number
      available_qty?: number
      inbound_qty?: number
      snapshot_time?: string
      source?: string
    } | null
  }
  summary: {
    warehouse_count: number
    high_risk_count: number
    plan_count: number
    allow_jd_transfer: boolean
  }
  warehouses: SkuWarehouseRow[]
  plans: TransferPlan[]
  business_forecast?: BusinessForecastAttachment
}

interface CityHealth {
  warehouse_code: string
  warehouse_name: string
  region: string
  active_sku_count: number
  high_count: number
  mid_count: number
  low_count: number
  excess_count: number
  stock_qty: number
  inbound_qty: number
  sales_7d: number
}

interface ApiList<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

interface AgentMessage {
  role: 'user' | 'assistant'
  content: string
}

interface AgentChatResponse {
  answer: string
  reason_updated?: boolean
  reason?: string | null
}

interface AgentStreamEvent {
  type?: 'delta' | 'done' | 'error'
  content?: string
  message?: string
  reason_updated?: boolean
  reason?: string | null
}

type PlanColumnKey =
  | 'sku'
  | 'product_name'
  | 'brand'
  | 'category'
  | 'path'
  | 'transfer_qty'
  | 'eta'
  | 'eta_risk'
  | 'risk_days'
  | 'target_days'
  | 'surplus_days_after'
  | 'reason'

const planColumnOptions: Array<{ key: PlanColumnKey; label: string }> = [
  { key: 'sku', label: 'SKU' },
  { key: 'product_name', label: '商品名称' },
  { key: 'brand', label: '品牌' },
  { key: 'category', label: '类目' },
  { key: 'path', label: '路径' },
  { key: 'risk_days', label: '调入仓可售天数' },
  { key: 'eta_risk', label: '到货风险' },
  { key: 'transfer_qty', label: '建议调拨数量' },
  { key: 'surplus_days_after', label: '调出后可售天数' },
  { key: 'eta', label: '预计到达天数' },
  { key: 'reason', label: '原因' },
  { key: 'target_days', label: '目标周转' },
]
const allPlanColumnKeys = planColumnOptions.map((item) => item.key)
const defaultPlanVisibleColumns = allPlanColumnKeys.filter((key) => key !== 'target_days')
const validPlanColumnKeys = new Set<PlanColumnKey>(allPlanColumnKeys)
const PLAN_COLUMN_STORAGE_PREFIX = 'inventory_decision.plan_columns.v2'

const fileList = ref<UploadUserFile[]>([])
const selectedFile = ref<UploadRawFile | null>(null)
const uploadRef = ref<UploadInstance>()
const importDialogVisible = ref(false)
const agentDrawerVisible = ref(false)
const importing = ref(false)
const importStatus = reactive({
  visible: false,
  type: 'info' as 'info' | 'success' | 'warning' | 'error',
  title: '',
  message: '',
})
const importNotification = ref<ReturnType<typeof ElNotification> | null>(null)
const summaryLoading = ref(false)
const planLoading = ref(false)
const cityLoading = ref(false)
const recalculating = ref(false)
const agentLoading = ref(false)
const activeTab = ref('business-purchase-export')
// 库存分析决策所有页签的可见权限映射：el-tab-pane 的 name → 后端 sub_key。
// 后端 SUB_PERM_DEFS 中的每个 sub_key 在前端都对应一个 tab，管理员可独立控制。
const TAB_SUB_KEY: Record<string, string> = {
  'business-forecast': 'forecast',
  'business-purchase-export': 'purchase-export',
  'sku-stock-warning': 'sku-warning',
  'plans': 'plans',
  'sku-decision': 'sku-decision',
  'settings': 'settings',
  'cities': 'cities',
  'simulate': 'simulate',
}
// 视觉顺序：用于「当前 activeTab 不被允许时」按顺序兜底选取第一个允许的 tab
const TAB_ORDER = Object.keys(TAB_SUB_KEY)

const allowedSubTabs = ref<string[]>([])  // 后端返回的 sub_key 列表
const isTabAllowed = (tabName: string): boolean => {
  if (!tabName) return false
  const subKey = TAB_SUB_KEY[tabName]
  return subKey ? allowedSubTabs.value.includes(subKey) : true
}

// 当前允许的第一个 tab（按视觉顺序），用于默认激活与回退
const firstAllowedTab = computed<string | null>(() => {
  for (const name of TAB_ORDER) {
    if (isTabAllowed(name)) return name
  }
  return null
})

const applyTabPermission = () => {
  const fb = firstAllowedTab.value
  if (!fb) {
    // 没有任何页签可见时清空激活态，避免 el-tabs 出现无效激活
    activeTab.value = ''
    return
  }
  if (!isTabAllowed(activeTab.value)) activeTab.value = fb
}

const loadSubTabPermission = async () => {
  try {
    const resp = (await request.get('/hr/permission/my')) as { allowed_subpages?: Record<string, string[]> }
    const subMap = resp?.allowed_subpages || {}
    allowedSubTabs.value = Array.isArray(subMap['inventory-decision']) ? subMap['inventory-decision'] : []
  } catch {
    // 权限配置拉取失败时保持受限页签隐藏（安全默认）
    allowedSubTabs.value = []
  }
  applyTabPermission()
}

// 权限数据更新时同步回退激活 tab（管理员在权限后台调整后，用户下次进入页签会更准确）
watch(allowedSubTabs, () => applyTabPermission())
const planSkuKeyword = ref('')
const planProductKeyword = ref('')
const planBrandKeyword = ref('')
const planCategoryKeyword = ref('')
const planMinTransferQty = ref<number | null>(null)
const planVisibleColumns = ref<PlanColumnKey[]>([...defaultPlanVisibleColumns])
const decisionSkuKeyword = ref('')

const summary = ref<SummaryData>({})
const plans = ref<TransferPlan[]>([])
const cityHealth = ref<CityHealth[]>([])
const brandOptions = ref<string[]>([])
const planBrandOptions = ref<string[]>([])
const categoryOptions = ref<string[]>([])
const replenishmentPolicies = ref<ReplenishmentPolicy[]>([])
const skuDecision = ref<SkuDecisionData | null>(null)
const skuDecisionLoading = ref(false)
const policySaving = ref(false)
const syncSettingLoading = ref(false)
const syncSettingSaving = ref(false)
const skuWarehouseRows = ref<SkuWarehouseRow[]>([])
const skuWarehouseLoading = ref(false)
const simulation = ref<Record<string, unknown> | null>(null)
const activeAgentPlan = ref<TransferPlan | null>(null)
const agentInput = ref('')
const agentMessagesByPlan = reactive<Record<number, AgentMessage[]>>({})
const agentBodyRef = ref<HTMLElement>()
const businessForecastPanelRef = ref<InstanceType<typeof BusinessForecast> | null>(null)
const businessForecastRef = ref<InstanceType<typeof BusinessForecast> | null>(null)

const planPagination = reactive({ page: 1, pageSize: 20, total: 0 })

const simulator = reactive({
  sku_code: '',
  from_warehouse: '',
  to_warehouse: '',
  transfer_qty: 1,
})

const policyForm = reactive({
  policy_type: 'BRAND',
  brand: '',
  category: '',
  target_days: 30,
  reserve_days: 15,
  supplier_eta_days: 7,
  allow_jd_transfer: true,
})

const huadongSyncSetting = reactive<HuadongSyncSetting>({
  enabled: false,
  interval_minutes: 10,
  recalculate: true,
  last_run_at: null,
  last_status: 'IDLE',
  last_message: '',
  last_result: null,
  updated_at: null,
})

const HUADONG_SYNC_STATUS_POLL_MS = 15000
let huadongSyncStatusTimer: ReturnType<typeof window.setInterval> | null = null
let huadongSyncStatusPolling = false
let huadongSyncStatusStamp = ''

const agentStarterPrompts = [
  { label: '分析调拨方案', message: '请分析这条调拨方案。' },
  { label: '为什么这个数量', message: '为什么调这个数量？' },
  { label: '不调会怎样', message: '如果不调会怎样？' },
  { label: '看其他仓库存', message: '其他仓库库存怎么样？' },
  { label: '生成领导汇报', message: '帮我生成一段给领导看的调拨汇报。' },
]

const boxBrandNames = new Set([
  'DEMO_BAGS',
  'DEMO_BAGS 箱包',
  '测试服饰',
  '测试服饰 箱包',
  'GRANITEGEAR',
  'GRANITEGEAR 箱包',
  'Rains',
  'Rains 箱包',
  'VENQUE',
  'VENQUE 箱包',
  '京塑',
  '京塑 箱包',
  '测试旅行',
  '测试旅行 箱包',
  '联想（Lenovo）',
  '联想（Lenovo） 箱包',
  '高山（High Sierra）',
  '高山（High Sierra） 箱包',
  '魅族（meizu）',
  '魅族（meizu） 箱包',
])

const canSubmitImport = computed(() => Boolean(selectedFile.value) && !importing.value)
const currentSnapshotDate = computed(() => summary.value.snapshot_date || '')
const importStatusClass = computed(() => `import-status-strip ${importStatus.type}`)
const latestSnapshotDate = computed(() => summary.value.snapshot_date || '暂无数据')
const canManageHuadongSync = ref(false)
const trendFactorEnabled = ref(true)
const trendFactorSaving = ref(false)
// 补货导出算法：system=现行算法  excel=运营表算法（默认运营表算法；仅 admin 可调整）
const purchaseFormula = ref<'system' | 'excel'>('excel')
const purchaseFormulaSaving = ref(false)
const canManagePurchaseFormula = ref(false)
// SKU 库存预警面板实例：导入库存表等数据刷新后自动重拉最新批次
const skuWarningRef = ref<{ refresh: () => Promise<void> } | null>(null)
const activeAgentMessages = computed(() => (
  activeAgentPlan.value ? agentMessagesByPlan[activeAgentPlan.value.id] || [] : []
))
const isSelectedBrandBox = computed(() => boxBrandNames.has(policyForm.brand))
const huadongSyncProgress = computed<HuadongSyncProgress | null>(() => {
  const result = huadongSyncSetting.last_result || {}
  const progress = result.progress
  if (!progress && huadongSyncSetting.last_status !== 'RUNNING') return null

  const processed = toNumber(progress?.processed)
  const total = toNumber(progress?.total || result.requested_chunks || result.requested_skus)
  const percent = total > 0
    ? Math.min(100, Math.max(0, toNumber(progress?.percent) || (processed / total) * 100))
    : 0

  return {
    phase: progress?.phase || 'querying',
    processed,
    total,
    percent,
    accepted: toNumber(progress?.accepted ?? result.accepted),
    api_rows: toNumber(progress?.api_rows ?? result.api_rows),
    errors: toNumber(progress?.errors ?? result.query_error_count),
    total_skus: toNumber(progress?.total_skus ?? result.total_skus),
    requested_skus: toNumber(progress?.requested_skus ?? result.requested_skus),
    requested_query_codes: toNumber(progress?.requested_query_codes ?? result.requested_query_codes),
    skipped_without_barcode: toNumber(progress?.skipped_without_barcode ?? result.skipped_without_barcode),
    query_max_workers: toNumber(progress?.query_max_workers ?? result.query_max_workers),
  }
})
const huadongSyncPhaseText = computed(() => {
  const phase = huadongSyncProgress.value?.phase
  if (phase === 'saving') return '正在写入库存'
  if (phase === 'recalculating') return '正在重算补货建议'
  if (phase === 'done') return '同步完成'
  return '正在请求聚水潭'
})
const huadongSyncProgressPercent = computed(() => Number((huadongSyncProgress.value?.percent || 0).toFixed(1)))
const huadongSyncStatusText = computed(() => {
  const status = huadongSyncSetting.last_status || 'IDLE'
  if (syncSettingLoading.value) return '正在读取同步设置'
  if (status === 'RUNNING' && huadongSyncProgress.value) {
    const progress = huadongSyncProgress.value
    return `${huadongSyncPhaseText.value}：${formatNumber(progress.processed)} / ${formatNumber(progress.total)}（${formatNumber(progress.percent, 1)}%）`
  }
  if (status === 'RUNNING') return '正在自动同步花东库存'
  if (huadongSyncSetting.last_message) return huadongSyncSetting.last_message
  return huadongSyncSetting.enabled
    ? `每 ${formatNumber(huadongSyncSetting.interval_minutes)} 分钟自动拉取`
    : '未启用自动同步'
})
const huadongSyncStatusClass = computed(() => {
  const status = huadongSyncSetting.last_status || 'IDLE'
  if (status === 'FAILED') return 'danger'
  if (status === 'SUCCESS') return 'success'
  if (status === 'RUNNING') return 'running'
  return ''
})
const huadongSyncMetaText = computed(() => (
  huadongSyncSetting.last_run_at
    ? `最近同步 ${huadongSyncSetting.last_run_at}`
    : '尚未同步'
))
const huadongSyncProgressMeta = computed(() => {
  const progress = huadongSyncProgress.value
  if (!progress) return ''
  const parts = [
    `全量 SKU ${formatNumber(progress.total_skus)}`,
    `唯一条形码 ${formatNumber(progress.requested_query_codes)}`,
    `已命中 ${formatNumber(progress.accepted)} 条`,
    `API 返回 ${formatNumber(progress.api_rows)} 条`,
  ]
  if (progress.skipped_without_barcode) parts.push(`无条形码 ${formatNumber(progress.skipped_without_barcode)} 个`)
  if (progress.errors) parts.push(`失败 ${formatNumber(progress.errors)} 个`)
  if (progress.query_max_workers) parts.push(`并发 ${formatNumber(progress.query_max_workers)}`)
  return parts.join(' · ')
})

const toNumber = (value: unknown) => {
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) ? numeric : 0
}

const uniqueSortedOptions = (values: string[], currentValue = '') => {
  const unique = Array.from(new Set(values.map((item) => item.trim()).filter(Boolean))).sort((a, b) => a.localeCompare(b, 'zh-CN'))
  const current = currentValue.trim()
  if (current && !unique.includes(current)) {
    return [current, ...unique]
  }
  return unique
}

const formatNumber = (value: unknown, digits = 0) =>
  toNumber(value).toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })

const formatDays = (value: unknown) => {
  const days = toNumber(value)
  if (days >= 9999) return '近7日无出库'
  return `${formatNumber(days, 1)} 天`
}

const supplySourceLabel = (row: Record<string, unknown>) => {
  const fromWarehouse = transferPathValue(row, 'from_warehouse').trim()
  const sourceType = transferPathValue(row, 'source_type')
  if (fromWarehouse === '花东仓') return '花东仓'
  if (fromWarehouse === '南沙仓') return '南沙仓'
  if (sourceType === 'SUPPLIER_REPLENISH' || sourceType === 'SUPPLIER_DIRECT' || fromWarehouse.includes('供应商')) return '供应商'
  return ''
}

const formatSourceSafety = (row: Record<string, unknown>) => (
  supplySourceLabel(row) || formatDays(row.surplus_days_after)
)

const formatSkuCode = (value: unknown) => {
  const raw = String(value ?? '').trim()
  const match = raw.replace(/,/g, '').match(/^(\d+)(?:\.(\d+))?[eE]([+-]?\d+)$/)
  if (!match) return raw

  const integerPart = match[1]
  const fractionPart = match[2] || ''
  const exponent = Number(match[3])
  const digits = `${integerPart}${fractionPart}`
  const decimalIndex = integerPart.length + exponent

  if (decimalIndex >= digits.length) return `${digits}${'0'.repeat(decimalIndex - digits.length)}`
  if (decimalIndex <= 0) return raw

  const tail = digits.slice(decimalIndex)
  return /^0*$/.test(tail) ? digits.slice(0, decimalIndex) : raw
}

const skuBusinessForecast = computed<BusinessForecastAttachment | null>(() => (
  skuDecision.value?.business_forecast || null
))
const skuBusinessForecastRow = computed<BusinessForecastRow | null>(() => (
  skuBusinessForecast.value?.forecast || null
))
const skuBusinessForecastCities = computed<BusinessForecastCityRow[]>(() => (
  skuBusinessForecast.value?.cities || []
))
const skuBusinessForecastStatus = computed(() => (
  skuBusinessForecast.value?.status || 'NO_DATA'
))
const skuBusinessForecastPredicted7d = computed(() => {
  const forecast = skuBusinessForecastRow.value
  return toNumber(forecast?.adjusted_pred_7d ?? forecast?.predicted_7d)
})
const skuBusinessForecastSuggestionTotal = computed(() => (
  skuBusinessForecastCities.value.reduce((total, row) => total + toNumber(row.suggested_qty), 0)
))
const skuDecisionExecutableTotal = computed(() => (
  (skuDecision.value?.plans || []).reduce((total, row) => total + toNumber(row.transfer_qty), 0)
))
const skuBusinessForecastDelta = computed(() => (
  skuBusinessForecastSuggestionTotal.value - skuDecisionExecutableTotal.value
))
const skuBusinessForecastPotentialIncrement = computed(() => (
  Math.max(skuBusinessForecastDelta.value, 0)
))
const skuBusinessForecastDeltaText = computed(() => {
  const delta = skuBusinessForecastDelta.value
  if (delta > 0) return `+${formatNumber(delta)} 件`
  if (delta < 0) return `-${formatNumber(Math.abs(delta))} 件`
  return '持平'
})
const skuBusinessForecastShortageTotal = computed(() => (
  skuBusinessForecastCities.value.reduce((total, row) => total + toNumber(row.shortage_qty), 0)
))
const skuBusinessForecastWindowText = computed(() => {
  const forecast = skuBusinessForecastRow.value
  if (!forecast?.target_start_date || !forecast?.target_end_date) return '未来7天观察'
  return `${forecast.target_start_date} 至 ${forecast.target_end_date}`
})
const skuBusinessForecastEmptyText = computed(() => {
  if (skuBusinessForecastStatus.value === 'UNAVAILABLE') return '经营趋势服务暂不可用'
  if (!skuBusinessForecastRow.value) return '该SKU暂无经营趋势预测'
  if (skuBusinessForecastRow.value.sku_link_status === 'PENDING_LINK') return '该SKU待关联库存SKU，不生成城市补货观察'
  return '该SKU暂无城市经营趋势补货观察'
})

const businessForecastStatusText = (value?: string) => {
  if (value === 'AVAILABLE') return '已生成'
  if (value === 'UNAVAILABLE') return '暂不可用'
  if (value === 'NO_DATA') return '暂无数据'
  return value || '暂无数据'
}

const businessForecastStatusTagType = (value?: string) => {
  if (value === 'AVAILABLE') return 'success'
  if (value === 'UNAVAILABLE') return 'danger'
  return 'info'
}

const businessTrendText = (value?: string) => {
  if (value === 'UP') return '上涨'
  if (value === 'DOWN') return '下降'
  if (value === 'STABLE') return '稳定'
  return '未知'
}

const businessTrendTagType = (value?: string) => {
  if (value === 'UP') return 'danger'
  if (value === 'DOWN') return 'success'
  return 'info'
}

const businessConfidenceText = (value?: string) => {
  if (value === 'HIGH') return '高置信'
  if (value === 'MID') return '中置信'
  if (value === 'LOW') return '低置信'
  return '未知置信'
}

const businessConfidenceTagType = (value?: string) => {
  if (value === 'HIGH') return 'success'
  if (value === 'LOW') return 'warning'
  return 'info'
}

const businessLinkStatusText = (value?: string) => {
  if (value === 'LINKED') return '已关联库存'
  if (value === 'PENDING_LINK') return '待关联'
  return value || '未知关联状态'
}

const formatAdjustmentFactor = (value?: number | null) => {
  const factor = toNumber(value || 1)
  const percent = (factor - 1) * 100
  const sign = percent > 0 ? '+' : ''
  return `×${formatNumber(factor, 2)}（${sign}${formatNumber(percent, 1)}%）`
}

const currentColumnPreferenceUser = () => {
  try {
    return (
      localStorage.getItem('auth_username')
      || localStorage.getItem('auth_real_name')
      || 'anonymous'
    )
  } catch {
    return 'anonymous'
  }
}

const planColumnStorageKey = () =>
  `${PLAN_COLUMN_STORAGE_PREFIX}.${currentColumnPreferenceUser()}`

const sanitizePlanVisibleColumns = (columns: unknown): PlanColumnKey[] => {
  if (!Array.isArray(columns)) return [...defaultPlanVisibleColumns]
  const unique = Array.from(new Set(columns))
    .filter((key): key is PlanColumnKey => validPlanColumnKeys.has(key as PlanColumnKey))
  return unique.length ? unique : [...defaultPlanVisibleColumns]
}

const loadPlanColumnPreference = () => {
  try {
    const raw = localStorage.getItem(planColumnStorageKey())
    if (!raw) return
    planVisibleColumns.value = sanitizePlanVisibleColumns(JSON.parse(raw))
  } catch {
    planVisibleColumns.value = [...defaultPlanVisibleColumns]
  }
}

const savePlanColumnPreference = () => {
  try {
    localStorage.setItem(planColumnStorageKey(), JSON.stringify(planVisibleColumns.value))
  } catch {
    // localStorage may be unavailable; table still works with in-memory state.
  }
}

const isPlanColumnVisible = (key: PlanColumnKey) => planVisibleColumns.value.includes(key)

const resetPlanColumns = () => {
  planVisibleColumns.value = [...defaultPlanVisibleColumns]
}

const escapeHtml = (value: string) =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

const normalizeMarkdown = (value: string) => {
  const boldMarkerCount = value.match(/\*\*/g)?.length || 0
  if (boldMarkerCount % 2 === 0) return value
  const lastMarkerIndex = value.lastIndexOf('**')
  return lastMarkerIndex >= 0
    ? `${value.slice(0, lastMarkerIndex)}${value.slice(lastMarkerIndex + 2)}`
    : value
}

const stripInternalPlanId = (value: string) =>
  value
    .replace(/\s*[·\-—–]\s*Plan\s*#\s*\d+/gi, '')
    .replace(/\bPlan\s*#\s*\d+\b/gi, '')
    .replace(/(?:内部)?(?:plan_id|方案ID|调拨方案ID|计划ID)\s*[:：#]?\s*\d+/gi, '')

const renderInlineMarkdown = (value: string) =>
  value
    .replace(/`([^`\n]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/__([^_\n]+)__/g, '<strong>$1</strong>')
    .replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, '<em>$1</em>')

const cleanReasonText = (value: unknown) =>
  stripInternalPlanId(String(value ?? ''))
    .replace(/\s+/g, ' ')
    .trim()

const reasonSummary = (value: unknown) => {
  const text = cleanReasonText(value)
  if (!text) return '暂无原因'
  const firstSentence = text.split(/[。；;.!?？]/).find((item) => item.trim())?.trim() || text
  return firstSentence.length > 48 ? `${firstSentence.slice(0, 48)}...` : firstSentence
}

const reasonBullets = (value: unknown) => {
  const text = cleanReasonText(value)
  if (!text) return ['暂无原因']
  const parts = text
    .split(/(?<=[。；;.!?？])\s*/)
    .map((item) => item.replace(/[。；;]+$/g, '').trim())
    .filter(Boolean)
  return parts.length ? parts.slice(0, 5) : [text]
}

const isMarkdownTableLine = (line: string) => {
  const trimmed = line.trim()
  if (!trimmed.includes('|')) return false
  const cells = trimmed.replace(/^\|/, '').replace(/\|$/, '').split('|')
  return cells.length >= 2
}

const isMarkdownSeparatorLine = (line: string) => {
  if (!isMarkdownTableLine(line)) return false
  const cells = line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim())
  return cells.length > 0 && cells.every((cell) => /^:?\s*-{2,}\s*:?\s*$/.test(cell))
}

const tableCells = (line: string) =>
  line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => renderInlineMarkdown(cell.trim()))

const isMarkdownQuoteLine = (line: string) => /^(?:>|&gt;)\s*/.test(line.trim())

const stripMarkdownQuotePrefix = (line: string) => line.trim().replace(/^(?:>|&gt;)\s*/, '')

const isBlockStart = (line: string, nextLine = '') => {
  const trimmed = line.trim()
  return !trimmed
    || /^#{1,4}\s+/.test(trimmed)
    || /^[-*_]{3,}$/.test(trimmed)
    || /^[-*]\s+/.test(trimmed)
    || /^\d+\.\s+/.test(trimmed)
    || isMarkdownQuoteLine(trimmed)
    || trimmed.startsWith('```')
    || (isMarkdownTableLine(trimmed) && isMarkdownSeparatorLine(nextLine))
}

const parseMarkdown = (raw: string): string => {
  if (!raw) return ''

  const clean = escapeHtml(normalizeMarkdown(stripInternalPlanId(raw)).replace(/<\/?[a-z][a-z0-9]*(?:\s+[^>]*)?>/gi, ''))
  const lines = clean.split('\n')
  const blocks: string[] = []

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    const trimmed = line.trim()

    if (!trimmed) continue

    if (trimmed.startsWith('```')) {
      const codeLines: string[] = []
      i += 1
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i])
        i += 1
      }
      blocks.push(`<pre><code>${codeLines.join('\n')}</code></pre>`)
      continue
    }

    if (isMarkdownTableLine(line) && isMarkdownSeparatorLine(lines[i + 1] || '')) {
      const header = tableCells(line).map((cell) => `<th>${cell}</th>`).join('')
      const rows: string[] = []
      i += 2
      while (i < lines.length && isMarkdownTableLine(lines[i])) {
        const cells = tableCells(lines[i]).map((cell) => `<td>${cell}</td>`).join('')
        rows.push(`<tr>${cells}</tr>`)
        i += 1
      }
      i -= 1
      blocks.push(`<div class="markdown-table-wrap"><table><thead><tr>${header}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`)
      continue
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/)
    if (heading) {
      const level = heading[1].length
      blocks.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`)
      continue
    }

    if (/^[-*_]{3,}$/.test(trimmed)) {
      blocks.push('<hr>')
      continue
    }

    if (/^[-*]\s+/.test(trimmed)) {
      const items: string[] = []
      while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
        items.push(`<li>${renderInlineMarkdown(lines[i].trim().replace(/^[-*]\s+/, ''))}</li>`)
        i += 1
      }
      i -= 1
      blocks.push(`<ul>${items.join('')}</ul>`)
      continue
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const items: string[] = []
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        items.push(`<li>${renderInlineMarkdown(lines[i].trim().replace(/^\d+\.\s+/, ''))}</li>`)
        i += 1
      }
      i -= 1
      blocks.push(`<ol>${items.join('')}</ol>`)
      continue
    }

    if (isMarkdownQuoteLine(trimmed)) {
      blocks.push(`<blockquote>${renderInlineMarkdown(stripMarkdownQuotePrefix(trimmed))}</blockquote>`)
      continue
    }

    const paragraphLines = [trimmed]
    while (i + 1 < lines.length && !isBlockStart(lines[i + 1], lines[i + 2] || '')) {
      paragraphLines.push(lines[i + 1].trim())
      i += 1
    }
    blocks.push(`<p>${renderInlineMarkdown(paragraphLines.join('<br>'))}</p>`)
  }

  return blocks.join('')
}

const riskTagType = (level: string) => {
  if (level === 'HIGH') return 'danger'
  if (level === 'MID') return 'warning'
  return 'success'
}

const riskText = (level: string) => {
  if (level === 'HIGH') return '高'
  if (level === 'MID') return '中'
  if (level === 'LOW') return '低'
  return level || '-'
}

const transferPathValue = (row: Record<string, unknown>, key: keyof TransferPlan) =>
  String(row[key] ?? '')

const isSupplierReplenishmentPlan = (row: Record<string, unknown>) =>
  transferPathValue(row, 'source_type') === 'SUPPLIER_REPLENISH'

const formatTransferPath = (row: Record<string, unknown>) => {
  const routePath = transferPathValue(row, 'route_path')
  if (routePath) return routePath
  const fromWarehouse = transferPathValue(row, 'from_warehouse')
  const toWarehouse = transferPathValue(row, 'to_warehouse')
  if (isSupplierReplenishmentPlan(row)) {
    return `供应商 → 花东仓 → ${toWarehouse}`
  }
  return `${fromWarehouse} → ${toWarehouse}`
}

const transferPathNodes = (row: Record<string, unknown>) =>
  formatTransferPath(row)
    .split(/\s*→\s*/)
    .map((item) => item.trim())
    .filter(Boolean)

const handleSkuLinkClick = (skuCode: unknown) => {
  if (window.getSelection()?.toString().trim()) return
  if (!isTabAllowed('sku-decision')) {
    ElMessage.info('当前角色/人员未被授权查看 SKU补货决策，请联系管理员在权限管理中配置')
    return
  }
  activeTab.value = 'sku-decision'
  void querySkuDecision(formatSkuCode(skuCode))
}

const formatTransferEta = (row: Record<string, unknown>) => {
  const etaDays = toNumber(row.eta_days)
  return etaDays <= 0 ? '待定' : `${formatNumber(etaDays)} 天`
}

const etaRiskTagType = (row: Record<string, unknown>) => {
  if (toNumber(row.eta_days) <= 0) return 'info'
  return toNumber(row.eta_late) ? 'warning' : 'success'
}

const etaRiskText = (row: Record<string, unknown>) => {
  if (toNumber(row.eta_days) <= 0) return '待定'
  return toNumber(row.eta_late) ? '可能断货' : '可覆盖'
}

const isExcelFile = (file: File) => {
  const name = file.name.toLowerCase()
  const excelTypes = [
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  ]
  return name.endsWith('.xlsx') || excelTypes.includes(file.type)
}

const resetSelectedFile = () => {
  selectedFile.value = null
  fileList.value = []
  uploadRef.value?.clearFiles()
}

const closeImportNotification = () => {
  importNotification.value?.close()
  importNotification.value = null
}

const showImportNotification = (
  type: 'info' | 'success' | 'warning' | 'error',
  title: string,
  message: string,
  duration = 0,
  showClose = true,
) => {
  closeImportNotification()
  importNotification.value = ElNotification({
    type,
    title,
    message,
    duration,
    showClose,
    position: 'top-right',
  })
}

const updateImportStatus = (
  type: 'info' | 'success' | 'warning' | 'error',
  title: string,
  message: string,
) => {
  importStatus.visible = true
  importStatus.type = type
  importStatus.title = title
  importStatus.message = message
}

const clearImportStatus = () => {
  if (importing.value) return
  importStatus.visible = false
  importStatus.title = ''
  importStatus.message = ''
}

const getRequestErrorMessage = (error: unknown, fallback: string) => {
  if (!error || typeof error !== 'object') return fallback
  const candidate = error as {
    message?: string
    response?: { data?: { detail?: string; message?: string } }
  }
  return candidate.response?.data?.detail || candidate.response?.data?.message || candidate.message || fallback
}

const beforeUpload = (rawFile: UploadRawFile) => {
  if (!isExcelFile(rawFile)) {
    ElMessage.warning('库存RDC横版导入仅支持 xlsx 格式')
  }
  return false
}

const handleFileChange = (uploadFile: UploadFile) => {
  if (!uploadFile.raw || !isExcelFile(uploadFile.raw)) {
    resetSelectedFile()
    ElMessage.warning('库存RDC横版导入仅支持 xlsx 格式')
    return
  }
  selectedFile.value = uploadFile.raw
  fileList.value = [uploadFile]
}

const handleFileRemove = () => {
  selectedFile.value = null
  fileList.value = []
}

const fetchSummary = async () => {
  summaryLoading.value = true
  try {
    const response = await request.get('/inventory/summary') as { data: SummaryData }
    summary.value = response.data || {}
  } finally {
    summaryLoading.value = false
  }
}

const fetchPlans = async () => {
  planLoading.value = true
  try {
    const [response] = await Promise.all([
      request.get('/inventory/plans', {
        params: {
          sku_code: planSkuKeyword.value || undefined,
          product_name: planProductKeyword.value || undefined,
          brand: planBrandKeyword.value || undefined,
          category: planCategoryKeyword.value || undefined,
          min_transfer_qty: planMinTransferQty.value || undefined,
          page: planPagination.page,
          page_size: planPagination.pageSize,
        },
      }) as Promise<ApiList<TransferPlan>>,
      fetchPlanBrandOptions(),
    ])
    plans.value = response.items || []
    planPagination.total = response.total || 0
  } finally {
    planLoading.value = false
  }
}

const fetchCityHealth = async () => {
  cityLoading.value = true
  try {
    const response = await request.get('/inventory/city-health') as { items: CityHealth[] }
    cityHealth.value = response.items || []
  } finally {
    cityLoading.value = false
  }
}

const fetchBrandOptions = async () => {
  const response = await request.get('/inventory/brands', {
    params: { limit: 500 },
  }) as { items: string[] }
  brandOptions.value = response.items || []
}

const fetchPlanBrandOptions = async () => {
  const response = await request.get('/inventory/plan-brands', {
    params: {
      snapshot_date: currentSnapshotDate.value || undefined,
      sku_code: planSkuKeyword.value || undefined,
      product_name: planProductKeyword.value || undefined,
      category: planCategoryKeyword.value || undefined,
      min_transfer_qty: planMinTransferQty.value || undefined,
      limit: 1000,
    },
  }) as { items: string[] }
  planBrandOptions.value = uniqueSortedOptions(response.items || [], planBrandKeyword.value)
}

const fetchCategoryOptions = async () => {
  const response = await request.get('/inventory/categories') as { items: string[] }
  categoryOptions.value = response.items || []
}

const fetchPolicies = async () => {
  const response = await request.get('/inventory/policies') as { items: ReplenishmentPolicy[] }
  replenishmentPolicies.value = response.items || []
  if (policyForm.brand) {
    applyBrandPolicy(policyForm.brand)
  }
}

const querySkuDecision = async (sku?: string) => {
  const skuCode = (sku || decisionSkuKeyword.value).trim()
  if (!skuCode) {
    ElMessage.warning('请输入要查看的SKU')
    return
  }
  decisionSkuKeyword.value = skuCode
  skuDecisionLoading.value = true
  try {
    const response = await request.get('/inventory/sku-decision', {
      params: {
        sku_code: skuCode,
        snapshot_date: currentSnapshotDate.value || undefined,
      },
    }) as { data: SkuDecisionData }
    skuDecision.value = response.data || null
    const skuBrand = response.data?.sku?.brand
    if (skuBrand && !policyForm.brand) {
      applyBrandPolicy(skuBrand)
    }
  } finally {
    skuDecisionLoading.value = false
  }
}

const applyHuadongSyncSetting = (value?: Partial<HuadongSyncSetting> | null) => {
  const setting = value || {}
  huadongSyncSetting.enabled = Boolean(setting.enabled)
  huadongSyncSetting.interval_minutes = toNumber(setting.interval_minutes) || 10
  huadongSyncSetting.recalculate = true
  huadongSyncSetting.last_run_at = setting.last_run_at || null
  huadongSyncSetting.last_status = setting.last_status || 'IDLE'
  huadongSyncSetting.last_message = setting.last_message || ''
  huadongSyncSetting.last_result = setting.last_result || null
  huadongSyncSetting.updated_at = setting.updated_at || null
}

const getHuadongSyncStatusStamp = () => [
  huadongSyncSetting.last_status || '',
  huadongSyncSetting.last_run_at || '',
  huadongSyncSetting.updated_at || '',
  huadongSyncSetting.last_message || '',
  huadongSyncSetting.last_result?.progress?.percent ?? '',
  huadongSyncSetting.last_result?.progress?.processed ?? '',
].join('|')

const fetchHuadongSyncSetting = async (options: { background?: boolean; refreshOnSuccess?: boolean } = {}) => {
  if (!options.background) {
    syncSettingLoading.value = true
  }
  try {
    const previousStamp = huadongSyncStatusStamp
    const response = await request.get(
      '/inventory/huadong-stock/sync-setting',
      { silent: Boolean(options.background) } as any,
    ) as { data?: HuadongSyncSetting }
    applyHuadongSyncSetting(response.data)
    const nextStamp = getHuadongSyncStatusStamp()
    const statusChanged = Boolean(previousStamp) && nextStamp !== previousStamp
    huadongSyncStatusStamp = nextStamp
    if (options.refreshOnSuccess && statusChanged && huadongSyncSetting.last_status === 'SUCCESS') {
      void refreshAll()
    }
  } finally {
    if (!options.background) {
      syncSettingLoading.value = false
    }
  }
}

const fetchHuadongSyncPermission = async () => {
  const response = await request.get('/auth/session', { silent: true } as any) as {
    can_manage_huadong_sync?: boolean
    is_admin?: boolean
  }
  canManageHuadongSync.value = Boolean(response.can_manage_huadong_sync)
  canManagePurchaseFormula.value = Boolean(response.is_admin)
}

const pollHuadongSyncSetting = async () => {
  if (huadongSyncStatusPolling) return
  huadongSyncStatusPolling = true
  try {
    await fetchHuadongSyncSetting({ background: true, refreshOnSuccess: true })
  } finally {
    huadongSyncStatusPolling = false
  }
}

const startHuadongSyncStatusPolling = () => {
  if (huadongSyncStatusTimer) {
    window.clearInterval(huadongSyncStatusTimer)
  }
  huadongSyncStatusTimer = window.setInterval(() => {
    void pollHuadongSyncSetting()
  }, HUADONG_SYNC_STATUS_POLL_MS)
}

const stopHuadongSyncStatusPolling = () => {
  if (!huadongSyncStatusTimer) return
  window.clearInterval(huadongSyncStatusTimer)
  huadongSyncStatusTimer = null
}

const saveHuadongSyncSetting = async () => {
  if (!canManageHuadongSync.value) {
    ElMessage.warning('仅杨精灿可修改花东库存自动同步设置')
    return
  }
  syncSettingSaving.value = true
  try {
    const response = await request.post('/inventory/huadong-stock/sync-setting', {
      enabled: huadongSyncSetting.enabled,
      interval_minutes: huadongSyncSetting.interval_minutes,
      recalculate: true,
    }) as { data?: HuadongSyncSetting }
    applyHuadongSyncSetting(response.data)
    huadongSyncStatusStamp = getHuadongSyncStatusStamp()
    ElMessage.success(
      huadongSyncSetting.enabled
        ? '同步设置已保存，正在抓取一轮花东库存'
        : '花东库存自动同步设置已保存',
    )
  } finally {
    syncSettingSaving.value = false
  }
}

const fetchTrendFactorSetting = async () => {
  try {
    const response = await request.get('/inventory/business-forecast/settings', { silent: true } as any) as {
      data?: { apply_trend_factor?: boolean, purchase_formula?: string }
    }
    if (typeof response.data?.apply_trend_factor === 'boolean') {
      trendFactorEnabled.value = response.data.apply_trend_factor
    }
    if (response.data?.purchase_formula === 'excel') {
      purchaseFormula.value = 'excel'
    } else {
      purchaseFormula.value = 'system'
    }
  } catch {
    // 设置读取失败时保持默认开启，不阻塞页面。
  }
}

const saveTrendFactorSetting = async () => {
  trendFactorSaving.value = true
  try {
    await request.post('/inventory/business-forecast/settings', {
      apply_trend_factor: trendFactorEnabled.value,
      purchase_formula: purchaseFormula.value,
    })
    await request.post('/inventory/business-forecast/recalculate', {
      forecast_date: null,
      sku_codes: [],
    })
    ElMessage.success(trendFactorEnabled.value
      ? '已开启趋势因子并重算经营预测'
      : '已关闭趋势因子并重算经营预测')
    await refreshAll()
    await refreshBusinessForecastPanels(true)
    if (decisionSkuKeyword.value) {
      await querySkuDecision(decisionSkuKeyword.value)
    }
  } catch (error) {
    ElMessage.error(getRequestErrorMessage(error, '保存趋势因子设置失败'))
  } finally {
    trendFactorSaving.value = false
  }
}

// 切换补货导出算法（现行算法 ↔ 运营表算法），保存后立即全量重算
const switchPurchaseFormula = async (value: string | number | boolean) => {
  const next = value === 'excel' ? 'excel' : 'system'
  const previous = purchaseFormula.value
  if (next === previous) return
  if (!canManagePurchaseFormula.value) {
    ElMessage.warning('仅管理员可调整补货算法')
    return
  }
  purchaseFormulaSaving.value = true
  purchaseFormula.value = next
  try {
    await request.post('/inventory/business-forecast/settings', {
      apply_trend_factor: trendFactorEnabled.value,
      purchase_formula: next,
    })
    await request.post('/inventory/business-forecast/recalculate', {
      forecast_date: null,
      sku_codes: [],
    })
    ElMessage.success(next === 'excel'
      ? '已切换到运营表算法并重算补货导出明细'
      : '已切换回现行算法并重算补货导出明细')
    await refreshAll()
    await refreshBusinessForecastPanels(true)
    if (decisionSkuKeyword.value) {
      await querySkuDecision(decisionSkuKeyword.value)
    }
  } catch (error) {
    purchaseFormula.value = previous
    ElMessage.error(getRequestErrorMessage(error, '切换补货算法失败'))
  } finally {
    purchaseFormulaSaving.value = false
  }
}

function applyBrandPolicy(value?: string) {
  policyForm.policy_type = 'BRAND'
  policyForm.brand = value || policyForm.brand
  policyForm.category = ''

  const matched = replenishmentPolicies.value.find((item) => (
    item.policy_type === 'BRAND' && item.brand === policyForm.brand
  ))
  const fallback = replenishmentPolicies.value.find((item) => item.policy_type === 'SYSTEM')
  const policy = matched || fallback

  policyForm.target_days = toNumber(policy?.target_days) || 30
  policyForm.reserve_days = toNumber(policy?.reserve_days) || 15
  policyForm.supplier_eta_days = toNumber(policy?.supplier_eta_days) || 7
  policyForm.allow_jd_transfer = isSelectedBrandBox.value ? false : Boolean(policy?.allow_jd_transfer ?? true)
}

const savePolicy = async () => {
  if (!policyForm.brand) {
    ElMessage.warning('请选择品牌')
    return
  }
  policySaving.value = true
  try {
    await request.post('/inventory/policies', {
      policy_type: 'BRAND',
      brand: policyForm.brand,
      category: '',
      target_days: policyForm.target_days,
      reserve_days: policyForm.reserve_days || 15,
      supplier_eta_days: policyForm.supplier_eta_days,
      allow_jd_transfer: isSelectedBrandBox.value ? false : policyForm.allow_jd_transfer,
      preferred_source_warehouse: '花东仓',
      recalculate: true,
      snapshot_date: currentSnapshotDate.value || undefined,
    })
    ElMessage.success('补货策略已保存并重算')
    await Promise.all([fetchPolicies(), refreshAll()])
    await refreshBusinessForecastPanels()
    if (decisionSkuKeyword.value) {
      await querySkuDecision(decisionSkuKeyword.value)
    }
  } finally {
    policySaving.value = false
  }
}

const fetchSkuWarehouses = async (plan: TransferPlan) => {
  skuWarehouseLoading.value = true
  skuWarehouseRows.value = []
  try {
    const response = await request.get('/inventory/sku-warehouses', {
      params: {
        sku_code: plan.sku_code,
        snapshot_date: plan.plan_date || currentSnapshotDate.value || undefined,
      },
    }) as { items: SkuWarehouseRow[] }
    if (activeAgentPlan.value?.id === plan.id) {
      skuWarehouseRows.value = response.items || []
    }
  } finally {
    skuWarehouseLoading.value = false
  }
}

const refreshAll = async () => {
  await fetchSummary()
  await Promise.all([fetchPlans(), fetchCityHealth()])
}

const refreshBusinessForecastPanels = async (useLatest = false) => {
  await Promise.all([
    useLatest
      ? businessForecastPanelRef.value?.refreshLatestData()
      : businessForecastPanelRef.value?.refreshData(),
    useLatest
      ? businessForecastRef.value?.refreshLatestData()
      : businessForecastRef.value?.refreshData(),
  ])
}

const refreshBusinessPurchasePanel = async () => {
  await businessForecastRef.value?.refreshLatestData()
}

const submitImport = async () => {
  if (!selectedFile.value) {
    ElMessage.warning('请选择库存 Excel 文件')
    return
  }
  const formData = new FormData()
  formData.append('file', selectedFile.value)
  formData.append('auto_calculate', 'true')
  const importFileName = selectedFile.value.name || '库存表'
  importing.value = true
  updateImportStatus('info', '库存表导入中', `正在导入 ${importFileName}，系统会同步解析库存、重算风险和调拨建议，请稍等。`)
  showImportNotification('info', '库存表导入中', '系统正在处理库存表，处理期间可以停留在页面上，不要重复提交。', 0, false)
  try {
    const response = await request.post('/inventory/import', formData) as {
      message?: string
      data?: {
        business_forecast?: {
          skipped?: boolean
          reason?: string
        } | null
      }
    }
    const businessForecast = response.data?.business_forecast
    if (businessForecast?.skipped) {
      ElMessage.warning(`库存已导入并重算；经营趋势未重算：${businessForecast.reason || '暂无经营报表数据'}`)
    } else {
      ElMessage.success(response.message || '库存数据导入并联动重算完成')
    }
    importDialogVisible.value = false
    resetSelectedFile()
    // 数据刷新后 SKU 库存预警自动重拉最新批次，无需手动刷新页面
    await skuWarningRef.value?.refresh()
    await refreshAll()
    await refreshBusinessForecastPanels(true)
    if (decisionSkuKeyword.value) {
      await querySkuDecision(decisionSkuKeyword.value)
    }
    const doneMessage = businessForecast?.skipped
      ? `库存表已导入并重算完成；经营趋势未重算：${businessForecast.reason || '暂无经营报表数据'}`
      : response.message || '库存数据导入并联动重算完成'
    updateImportStatus(businessForecast?.skipped ? 'warning' : 'success', '库存表导入完成', doneMessage)
    showImportNotification(
      businessForecast?.skipped ? 'warning' : 'success',
      '库存表导入完成',
      doneMessage,
      0,
      true,
    )
  } catch (error) {
    const errorMessage = getRequestErrorMessage(error, '库存表导入失败，请检查文件或稍后重试')
    updateImportStatus('error', '库存表导入失败', errorMessage)
    showImportNotification('error', '库存表导入失败', errorMessage, 0, true)
    ElMessage.error(errorMessage)
  } finally {
    importing.value = false
  }
}

const recalculate = async () => {
  recalculating.value = true
  try {
    await request.post('/inventory/recalculate', {
      snapshot_date: currentSnapshotDate.value || undefined,
    })
    ElMessage.success('库存决策已重新计算')
    await skuWarningRef.value?.refresh()
    await refreshAll()
    await refreshBusinessForecastPanels(true)
  } finally {
    recalculating.value = false
  }
}

const getAgentMessages = (planId: number) => {
  if (!agentMessagesByPlan[planId]) {
    agentMessagesByPlan[planId] = []
  }
  return agentMessagesByPlan[planId]
}

const scrollAgentToBottom = async () => {
  await nextTick()
  if (agentBodyRef.value) {
    agentBodyRef.value.scrollTop = agentBodyRef.value.scrollHeight
  }
}

const scrollAgentMessageIntoView = async (index: number) => {
  await nextTick()
  const container = agentBodyRef.value
  const target = container?.querySelector<HTMLElement>(`[data-agent-message-index="${index}"]`)
  if (!container || !target) return

  const containerRect = container.getBoundingClientRect()
  const targetRect = target.getBoundingClientRect()
  container.scrollTop += targetRect.top - containerRect.top - 8
}

const syncUpdatedReason = (planId: number, reason?: string | null) => {
  if (!reason) return
  const target = plans.value.find((item) => item.id === planId)
  if (target) {
    target.reason = reason
  }
  if (activeAgentPlan.value?.id === planId) {
    activeAgentPlan.value.reason = reason
  }
}

const handleAgentStreamEvent = async (
  event: AgentStreamEvent,
  messages: AgentMessage[],
  assistantIndex: number,
  planId: number,
) => {
  if (event.type === 'delta' && event.content) {
    messages[assistantIndex].content += event.content
    await nextTick()
    return
  }

  if (event.type === 'done') {
    syncUpdatedReason(planId, event.reason)
    if (event.reason_updated) {
      ElMessage.success('解释已更新')
    }
    return
  }

  if (event.type === 'error') {
    throw new Error(event.message || 'AI助手流式响应失败')
  }
}

const streamAgentResponse = async (
  plan: TransferPlan,
  content: string,
  history: AgentMessage[],
  messages: AgentMessage[],
  assistantIndex: number,
) => {
  const response = await fetch('/api/ai/inventory_agent/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      plan_id: plan.id,
      message: content,
      messages: history,
    }),
  })

  if (!response.ok || !response.body) {
    throw new Error(await response.text() || 'AI助手流式接口请求失败')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    let splitIndex = buffer.indexOf('\n\n')
    while (splitIndex >= 0) {
      const rawEvent = buffer.slice(0, splitIndex)
      buffer = buffer.slice(splitIndex + 2)

      const dataLines = rawEvent
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())

      for (const dataLine of dataLines) {
        if (!dataLine || dataLine === '[DONE]') continue
        const event = JSON.parse(dataLine) as AgentStreamEvent
        await handleAgentStreamEvent(event, messages, assistantIndex, plan.id)
      }

      splitIndex = buffer.indexOf('\n\n')
    }
  }
}

const sendAgentMessage = async (presetMessage?: string) => {
  const plan = activeAgentPlan.value
  if (!plan || agentLoading.value) return

  const content = (presetMessage ?? agentInput.value).trim()
  if (!content) {
    ElMessage.warning('请输入要问AI助手的问题')
    return
  }

  const messages = getAgentMessages(plan.id)
  const history = messages.slice(-12)
  const userIndex = messages.length
  messages.push({ role: 'user', content })
  const assistantIndex = messages.length
  messages.push({ role: 'assistant', content: '' })
  agentInput.value = ''
  agentLoading.value = true

  try {
    try {
      await streamAgentResponse(plan, content, history, messages, assistantIndex)
      const streamedAnswer = messages[assistantIndex]?.content.trim()
      if (!streamedAnswer) {
        throw new Error('AI助手本次没有返回有效内容，请再试一次')
      }
    } catch (streamError) {
      messages.splice(assistantIndex, 1)
      const response = await request.post('/ai/inventory_agent/chat', {
        plan_id: plan.id,
        message: content,
        messages: history,
      }) as AgentChatResponse
      const answer = (response.answer || '').trim()
      if (!answer) {
        messages.splice(userIndex)
        ElMessage.warning('AI助手本次没有返回有效内容，请再试一次')
        return
      }
      messages.push({ role: 'assistant', content: answer })
      syncUpdatedReason(plan.id, response.reason)
      if (response.reason_updated) {
        ElMessage.success('解释已更新')
      }
    }
  } catch (error) {
    messages.splice(userIndex)
    throw error
  } finally {
    agentLoading.value = false
  }
}

const openAgent = (row: Record<string, unknown>) => {
  const plan = row as unknown as TransferPlan
  activeAgentPlan.value = plan
  skuWarehouseRows.value = []
  agentDrawerVisible.value = true
  void fetchSkuWarehouses(plan)
  getAgentMessages(plan.id)
  void scrollAgentToBottom()
}

const searchPlans = () => {
  planPagination.page = 1
  void fetchPlans()
}

const simulateTransfer = async () => {
  if (!simulator.sku_code || !simulator.from_warehouse || !simulator.to_warehouse || !simulator.transfer_qty) {
    ElMessage.warning('请填写 SKU、调出仓、调入仓和调拨数量')
    return
  }
  const response = await request.post('/inventory/simulate', {
    sku_code: simulator.sku_code,
    from_warehouse: simulator.from_warehouse,
    to_warehouse: simulator.to_warehouse,
    transfer_qty: simulator.transfer_qty,
    snapshot_date: currentSnapshotDate.value || undefined,
  }) as { data: Record<string, unknown> }
  simulation.value = response.data
}

watch(planVisibleColumns, (columns) => {
  const sanitized = sanitizePlanVisibleColumns(columns)
  if (sanitized.length !== columns.length || sanitized.some((key, index) => key !== columns[index])) {
    planVisibleColumns.value = sanitized
    return
  }
  savePlanColumnPreference()
}, { deep: true })

onMounted(() => {
  loadPlanColumnPreference()
  void fetchBrandOptions()
  void fetchCategoryOptions()
  void fetchPolicies()
  void fetchHuadongSyncPermission()
  void fetchHuadongSyncSetting()
  void fetchTrendFactorSetting()
  void loadSubTabPermission()
  startHuadongSyncStatusPolling()
  void refreshAll()
})

onBeforeUnmount(() => {
  closeImportNotification()
  stopHuadongSyncStatusPolling()
})

onActivated(() => {
  startHuadongSyncStatusPolling()
})

onDeactivated(() => {
  stopHuadongSyncStatusPolling()
})
</script>

<template>
  <section class="inventory-page">
    <header class="page-header">
      <div class="header-leading">
        <div class="header-heading-row">
          <div class="header-title-block">
            <p class="eyebrow">Inventory Decision Engine</p>
            <h1>库存分析决策</h1>
          </div>
          <div class="header-snapshot" aria-live="polite">
            <span>最新快照日期</span>
            <strong>{{ latestSnapshotDate }}</strong>
          </div>
        </div>
        <p class="subtitle">基于 SKU × 城市库存快照，输出缺货风险、可调库存和今日执行建议。</p>
      </div>
      <div class="header-actions">
        <el-button :icon="Upload" :loading="importing" size="large" type="primary" @click="importDialogVisible = true">
          导入库存表
        </el-button>
        <el-button :icon="MagicStick" :loading="recalculating" size="large" @click="recalculate">
          重算决策
        </el-button>
        <el-button :icon="Refresh" :loading="summaryLoading || planLoading" size="large" @click="refreshAll">
          刷新
        </el-button>
      </div>
    </header>

    <div v-if="importStatus.visible" :class="importStatusClass">
      <div>
        <strong>{{ importStatus.title }}</strong>
        <span>{{ importStatus.message }}</span>
      </div>
      <el-button v-if="!importing" link size="small" @click="clearImportStatus">我知道了</el-button>
    </div>

    <main class="decision-panel">
      <el-tabs v-if="allowedSubTabs.length" v-model="activeTab">
        <el-tab-pane v-if="isTabAllowed('plans')" name="plans">
          <template #label>
            <el-tooltip
              content="今日可执行的仓间调拨建议：看现在从哪个仓调到哪个仓，解决当前缺货风险。"
              placement="top"
            >
              <span class="tab-help-label">今日调拨建议</span>
            </el-tooltip>
          </template>
          <div class="toolbar">
            <div class="toolbar-left">
              <el-input v-model="planSkuKeyword" clearable placeholder="搜索 SKU" size="large" @keyup.enter="searchPlans" />
              <el-input v-model="planProductKeyword" clearable placeholder="商品名称" size="large" @keyup.enter="searchPlans" />
              <el-select
                v-model="planBrandKeyword"
                clearable
                filterable
                placeholder="品牌"
                size="large"
                @change="searchPlans"
              >
                <el-option
                  v-for="brand in planBrandOptions"
                  :key="brand"
                  :label="brand"
                  :value="brand"
                />
              </el-select>
              <el-select
                v-model="planCategoryKeyword"
                clearable
                filterable
                placeholder="类目"
                size="large"
                @change="searchPlans"
              >
                <el-option
                  v-for="category in categoryOptions"
                  :key="category"
                  :label="category"
                  :value="category"
                />
              </el-select>
              <el-input-number
                v-model="planMinTransferQty"
                :controls="false"
                :min="0"
                :precision="0"
                clearable
                placeholder="建议调拨量不低于"
                size="large"
                @keyup.enter="searchPlans"
              />
              <el-button :icon="Search" size="large" type="primary" plain @click="searchPlans">查询</el-button>
            </div>
            <div class="toolbar-right">
              <el-popover
                placement="bottom-end"
                popper-class="column-picker-popover"
                trigger="click"
                width="250"
              >
                <template #reference>
                  <el-button size="large">列选择</el-button>
                </template>
                <div class="column-picker">
                  <div class="column-picker-head">
                    <strong>选择显示列</strong>
                    <el-button link size="small" type="primary" @click="resetPlanColumns">
                      全选
                    </el-button>
                  </div>
                  <el-checkbox-group v-model="planVisibleColumns" class="column-checkbox-group">
                    <el-checkbox
                      v-for="column in planColumnOptions"
                      :key="column.key"
                      :value="column.key"
                    >
                      {{ column.label }}
                    </el-checkbox>
                  </el-checkbox-group>
                </div>
              </el-popover>
            </div>
          </div>

          <el-table v-loading="planLoading" :data="plans" border stripe empty-text="暂无调拨建议">
            <el-table-column v-if="isPlanColumnVisible('sku')" label="SKU" min-width="125" show-overflow-tooltip>
              <template #header>
                <el-tooltip content="点击SKU可查看该商品的补货决策；拖选文本可复制SKU。" placement="top">
                  <span class="table-help-header">SKU</span>
                </el-tooltip>
              </template>
              <template #default="{ row }">
                <span
                  class="sku-copy-link"
                  title="点击查看SKU补货决策，拖选可复制"
                  @click="handleSkuLinkClick(row.sku_code)"
                >
                  {{ formatSkuCode(row.sku_code) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column v-if="isPlanColumnVisible('product_name')" prop="product_name" label="商品名称" min-width="230" show-overflow-tooltip />
            <el-table-column v-if="isPlanColumnVisible('brand')" prop="brand" label="品牌" min-width="120" show-overflow-tooltip />
            <el-table-column v-if="isPlanColumnVisible('category')" prop="category" label="类目" min-width="90" show-overflow-tooltip />
            <el-table-column v-if="isPlanColumnVisible('path')" label="路径" min-width="210">
              <template #header>
                <el-tooltip content="蓝色为调入仓" placement="top">
                  <span class="table-help-header">路径</span>
                </el-tooltip>
              </template>
              <template #default="{ row }">
                <span class="route-path">
                  <template v-for="(node, index) in transferPathNodes(row)" :key="`${node}-${index}`">
                    <span class="route-node">{{ node }}</span>
                    <span v-if="index < transferPathNodes(row).length - 1" class="route-arrow">→</span>
                  </template>
                </span>
              </template>
            </el-table-column>
            <el-table-column v-if="isPlanColumnVisible('risk_days')" label="调入仓可售天数" align="right" min-width="130">
              <template #header>
                <el-tooltip placement="top" popper-class="table-help-tooltip">
                  <template #content>
                    <div class="table-help-content">
                      <strong>调入仓可售天数</strong>
                      <p>可售天数 = 调入仓库存 / 预测日均销量。</p>
                      <p>预测日均销量综合昨日、近7日、近30日销量，并结合历史趋势与波动系数修正。</p>
                      <p>若近7日、近30日和昨日均无销量且有库存，则显示近7日无出库。</p>
                    </div>
                  </template>
                  <span class="table-help-header right">调入仓可售天数</span>
                </el-tooltip>
              </template>
              <template #default="{ row }">
                <span class="plan-cell-emphasis risk-days">{{ formatDays(row.risk_days) }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="isPlanColumnVisible('eta_risk')" label="到货风险" min-width="100">
              <template #header>
                <el-tooltip placement="top" popper-class="table-help-tooltip">
                  <template #content>
                    <div class="table-help-content">
                      <strong>到货风险判断</strong>
                      <p>调入仓可售天数 ≥ 预计到达天数：可覆盖。</p>
                      <p>调入仓可售天数 &lt; 预计到达天数：可能断货。</p>
                    </div>
                  </template>
                  <span class="table-help-header">到货风险</span>
                </el-tooltip>
              </template>
              <template #default="{ row }">
                <el-tag :type="etaRiskTagType(row)">
                  {{ etaRiskText(row) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column v-if="isPlanColumnVisible('transfer_qty')" label="建议调拨数量" align="right" min-width="110">
              <template #default="{ row }">
                <span class="plan-cell-emphasis qty">{{ formatNumber(row.transfer_qty) }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="isPlanColumnVisible('surplus_days_after')" label="调出后可售天数" align="right" min-width="130">
              <template #header>
                <el-tooltip placement="top" popper-class="table-help-tooltip">
                  <template #content>
                    <div class="table-help-content">
                      <strong>调出后可售天数</strong>
                      <p>调出后可售天数 = (调出仓库存 - 调拨数量) / 调出仓预测日均销量。</p>
                      <p>若调出方是花东仓、南沙仓或供应商，则直接显示供给来源名称。</p>
                      <p>系统会校验调出后不能低于安全保留天数，避免拆东墙补西墙。</p>
                    </div>
                  </template>
                  <span class="table-help-header right">调出后可售天数</span>
                </el-tooltip>
              </template>
              <template #default="{ row }">
                <span class="plan-cell-emphasis surplus-days">{{ formatSourceSafety(row) }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="isPlanColumnVisible('eta')" label="预计到达天数" align="right" min-width="120">
              <template #default="{ row }">{{ formatTransferEta(row) }}</template>
            </el-table-column>
            <el-table-column v-if="isPlanColumnVisible('target_days')" label="目标周转" align="right" min-width="100">
              <template #header>
                <el-tooltip placement="top" popper-class="table-help-tooltip">
                  <template #content>
                    <div class="table-help-content">
                      <strong>目标周转</strong>
                      <p>目标周转来自顶部周转策略，默认30天，可按品牌调整。</p>
                      <p>风险判断会用调入仓可售天数和目标周转对比：低于目标即进入高风险判断。</p>
                    </div>
                  </template>
                  <span class="table-help-header right">目标周转</span>
                </el-tooltip>
              </template>
              <template #default="{ row }">{{ formatDays(row.target_days) }}</template>
            </el-table-column>
            <el-table-column v-if="isPlanColumnVisible('reason')" label="原因" align="center" min-width="86">
              <template #default="{ row }">
                <div class="reason-cell">
                  <el-popover
                    placement="left-start"
                    trigger="hover"
                    width="460"
                    popper-class="reason-popover"
                    :show-after="120"
                    :hide-after="80"
                  >
                    <template #reference>
                      <span class="reason-detail-btn">查看</span>
                    </template>
                    <div class="reason-card">
                      <div class="reason-card-head">
                        <strong>调拨原因</strong>
                        <span>{{ formatTransferPath(row) }}</span>
                      </div>
                      <p class="reason-full-text">{{ cleanReasonText(row.reason) }}</p>
                    </div>
                  </el-popover>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="操作" fixed="right" min-width="112">
              <template #default="{ row }">
                <el-button
                  size="small"
                  type="primary"
                  link
                  @click="openAgent(row)"
                >
                  AI助手
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination-bar">
            <span>共 {{ planPagination.total }} 条</span>
            <el-pagination
              v-model:current-page="planPagination.page"
              v-model:page-size="planPagination.pageSize"
              background
              layout="sizes, prev, pager, next"
              :page-sizes="[10, 20, 50, 100]"
              :total="planPagination.total"
              @current-change="fetchPlans"
              @size-change="() => { planPagination.page = 1; fetchPlans() }"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane v-if="isTabAllowed('sku-decision')" name="sku-decision">
          <template #label>
            <el-tooltip
              content="单个 SKU 的完整补货决策：输入 SKU 后，看全仓库存、花东供给、系统建议和经营趋势观察。"
              placement="top"
            >
              <span class="tab-help-label">SKU补货决策</span>
            </el-tooltip>
          </template>
          <section class="sku-decision-view">
            <div class="sku-decision-toolbar">
              <div class="sku-search-panel">
                <div class="sku-panel-title">
                  <strong>查SKU补货</strong>
                  <span>看全仓库存、花东供给和系统建议</span>
                </div>
                <div class="sku-search-row">
                  <el-input
                    v-model="decisionSkuKeyword"
                    clearable
                    placeholder="输入SKU"
                    size="large"
                    @keyup.enter="querySkuDecision()"
                  />
                  <el-button :icon="Search" :loading="skuDecisionLoading" size="large" type="primary" @click="querySkuDecision()">
                    查看SKU
                  </el-button>
                </div>
              </div>
            </div>

            <div v-loading="skuDecisionLoading" class="sku-decision-content">
              <template v-if="skuDecision">
                <div class="sku-overview-grid">
                  <div class="sku-overview-card product">
                    <span>SKU / 商品 / 品牌 / 类目</span>
                    <strong>{{ formatSkuCode(skuDecision.sku.sku_code) }}</strong>
                    <p>{{ skuDecision.sku.product_name || '-' }}</p>
                    <p class="product-brand-category">
                      {{ skuDecision.sku.brand || '-' }} · {{ skuDecision.sku.category || '-' }}
                    </p>
                  </div>
                  <div class="sku-overview-card">
                    <span>当前策略</span>
                    <strong>{{ formatNumber(skuDecision.policy.target_days) }} 天周转</strong>
                    <p>{{ skuDecision.policy.allow_jd_transfer ? '允许京东仓互调' : '仅花东补货' }}</p>
                  </div>
                  <div class="sku-overview-card">
                    <span>花东供给仓</span>
                    <strong>{{ formatNumber(skuDecision.supply_hub.stock?.available_qty ?? 0) }} 件可用</strong>
                    <p>{{ skuDecision.supply_hub.stock ? `更新时间 ${skuDecision.supply_hub.stock.snapshot_time || '-'}` : '查询不到库存信息' }}</p>
                  </div>
                  <div class="sku-overview-card">
                    <span>风险仓 / 建议</span>
                    <strong>{{ formatNumber(skuDecision.summary.high_risk_count) }} / {{ formatNumber(skuDecision.summary.plan_count) }}</strong>
                    <p>{{ skuDecision.snapshot_date }}</p>
                  </div>
                  <div class="sku-overview-card business-trend-card">
                    <span>经营趋势观察</span>
                    <template v-if="skuBusinessForecastRow">
                      <strong v-if="skuBusinessForecastRow.sku_link_status === 'PENDING_LINK'">待关联</strong>
                      <strong v-else>{{ formatNumber(skuBusinessForecastPredicted7d, 1) }} 件 / 7天</strong>
                      <div class="business-trend-tags">
                        <el-tag :type="businessTrendTagType(skuBusinessForecastRow.trend_level)" size="small">
                          {{ businessTrendText(skuBusinessForecastRow.trend_level) }}
                        </el-tag>
                        <el-tag :type="businessConfidenceTagType(skuBusinessForecastRow.confidence_level)" size="small">
                          {{ businessConfidenceText(skuBusinessForecastRow.confidence_level) }}
                        </el-tag>
                        <el-tag v-if="skuBusinessForecastRow.sku_link_status === 'PENDING_LINK'" type="warning" size="small">
                          {{ businessLinkStatusText(skuBusinessForecastRow.sku_link_status) }}
                        </el-tag>
                      </div>
                      <p class="business-trend-summary">
                        今日执行 {{ formatNumber(skuDecisionExecutableTotal) }} 件 ·
                        趋势观察 {{ formatNumber(skuBusinessForecastSuggestionTotal) }} 件 ·
                        潜在增量 {{ formatNumber(skuBusinessForecastPotentialIncrement) }} 件
                      </p>
                      <p class="business-trend-summary">
                        差值 {{ skuBusinessForecastDeltaText }} ·
                        修正 {{ formatAdjustmentFactor(skuBusinessForecastRow.adjustment_factor) }}
                      </p>
                    </template>
                    <template v-else>
                      <strong>{{ businessForecastStatusText(skuBusinessForecastStatus) }}</strong>
                      <p>观察，不改今日调拨</p>
                    </template>
                  </div>
                </div>

                <div class="sku-decision-columns">
                  <section class="sku-section">
                    <div class="section-title-row">
                      <div>
                        <strong>全仓库存与动销</strong>
                        <span>按风险、库存和近30日动销排序</span>
                      </div>
                    </div>
                    <el-table :data="skuDecision.warehouses" border class="strong-table" height="420" size="small" stripe>
                      <el-table-column label="仓库" min-width="75" show-overflow-tooltip>
                        <template #default="{ row }">{{ row.warehouse_name || row.warehouse_code }}</template>
                      </el-table-column>
                      <el-table-column label="风险" min-width="70">
                        <template #default="{ row }">
                          <el-tag :type="riskTagType(row.risk_level || '')" size="small">{{ riskText(row.risk_level || '') }}</el-tag>
                        </template>
                      </el-table-column>
                      <el-table-column label="库存" align="right" min-width="70">
                        <template #default="{ row }">{{ formatNumber(row.stock_qty) }}</template>
                      </el-table-column>
                      <el-table-column label="在途" align="right" min-width="70">
                        <template #default="{ row }">{{ formatNumber(row.inbound_qty) }}</template>
                      </el-table-column>
                      <el-table-column label="昨日" align="right" min-width="70">
                        <template #default="{ row }">{{ formatNumber(row.sales_1d) }}</template>
                      </el-table-column>
                      <el-table-column label="7日" align="right" min-width="70">
                        <template #default="{ row }">{{ formatNumber(row.sales_7d) }}</template>
                      </el-table-column>
                      <el-table-column label="30日" align="right" min-width="70">
                        <template #default="{ row }">{{ formatNumber(row.sales_30d) }}</template>
                      </el-table-column>
                      <el-table-column label="日均" align="right" min-width="70">
                        <template #default="{ row }">{{ formatNumber(row.daily_sales, 2) }}</template>
                      </el-table-column>
                      <el-table-column label="目标需求" align="right" min-width="70">
                        <template #default="{ row }">{{ formatNumber(row.demand_30d) }}</template>
                      </el-table-column>
                      <el-table-column label="可售" align="right" min-width="85">
                        <template #default="{ row }">{{ formatDays(row.days_of_supply) }}</template>
                      </el-table-column>
                    </el-table>
                  </section>

                  <section class="sku-section">
                    <div class="section-title-row">
                      <div>
                        <strong>系统补货建议</strong>
                        <span>箱包只走花东；其他类目优先安全京东仓，兜底花东。</span>
                      </div>
                    </div>
                    <el-table :data="skuDecision.plans" border class="strong-table" height="420" size="small" stripe empty-text="该SKU暂无补货建议">
                      <el-table-column label="路径" min-width="180" show-overflow-tooltip>
                        <template #header>
                          <el-tooltip content="蓝色为当前仓" placement="top">
                            <span class="table-help-header">路径</span>
                          </el-tooltip>
                        </template>
                        <template #default="{ row }">
                          <span class="route-path">
                            <template v-for="(node, index) in transferPathNodes(row)" :key="`${node}-${index}`">
                              <span class="route-node">{{ node }}</span>
                              <span v-if="index < transferPathNodes(row).length - 1" class="route-arrow">→</span>
                            </template>
                          </span>
                        </template>
                      </el-table-column>
                      <el-table-column label="数量" align="right" min-width="70">
                        <template #default="{ row }">{{ formatNumber(row.transfer_qty) }}</template>
                      </el-table-column>
                      <el-table-column label="预计天数" align="right" min-width="76">
                        <template #default="{ row }">{{ formatTransferEta(row) }}</template>
                      </el-table-column>
                      <el-table-column label="当前可售" align="right" min-width="94">
                        <template #default="{ row }">{{ formatDays(row.risk_days) }}</template>
                      </el-table-column>
                      <el-table-column label="到货风险" min-width="94">
                        <template #default="{ row }">
                          <el-tag :type="etaRiskTagType(row)" size="small">{{ etaRiskText(row) }}</el-tag>
                        </template>
                      </el-table-column>
                      <el-table-column label="操作" min-width="82">
                        <template #default="{ row }">
                          <el-button link type="primary" @click="openAgent(row)">AI助手</el-button>
                        </template>
                      </el-table-column>
                    </el-table>
                  </section>
                </div>

                <section class="sku-section business-observation-section">
                  <div class="section-title-row business-observation-head">
                    <div>
                      <strong>城市经营趋势观察</strong>
                      <span>
                        {{ skuBusinessForecastWindowText }} · 仅用于观察，不改今日调拨数量
                      </span>
                    </div>
                    <div class="business-observation-meta">
                      <el-tag :type="businessForecastStatusTagType(skuBusinessForecastStatus)" size="small">
                        {{ businessForecastStatusText(skuBusinessForecastStatus) }}
                      </el-tag>
                      <span>今日执行 {{ formatNumber(skuDecisionExecutableTotal) }} 件</span>
                      <span>趋势观察 {{ formatNumber(skuBusinessForecastSuggestionTotal) }} 件</span>
                      <span>差值 {{ skuBusinessForecastDeltaText }}</span>
                      <span>观察缺口 {{ formatNumber(skuBusinessForecastShortageTotal) }} 件</span>
                    </div>
                  </div>
                  <el-table
                    :data="skuBusinessForecastCities"
                    border
                    class="strong-table business-observation-table"
                    height="300"
                    size="small"
                    stripe
                    :empty-text="skuBusinessForecastEmptyText"
                  >
                    <el-table-column label="城市仓" min-width="100" show-overflow-tooltip>
                      <template #default="{ row }">{{ row.warehouse_name || row.warehouse_code }}</template>
                    </el-table-column>
                    <el-table-column label="经营7天需求" align="right" min-width="104">
                      <template #default="{ row }">{{ formatNumber(row.predicted_city_7d, 1) }}</template>
                    </el-table-column>
                    <el-table-column label="日均预测" align="right" min-width="86">
                      <template #default="{ row }">{{ formatNumber(row.daily_city_forecast, 2) }}</template>
                    </el-table-column>
                    <el-table-column label="库存" align="right" min-width="76">
                      <template #default="{ row }">{{ formatNumber(row.stock_qty) }}</template>
                    </el-table-column>
                    <el-table-column label="在途" align="right" min-width="76">
                      <template #default="{ row }">{{ formatNumber(row.inbound_qty) }}</template>
                    </el-table-column>
                    <el-table-column label="趋势可售" align="right" min-width="88">
                      <template #default="{ row }">{{ formatDays(row.days_of_supply) }}</template>
                    </el-table-column>
                    <el-table-column label="风险" min-width="78">
                      <template #default="{ row }">
                        <el-tag :type="riskTagType(row.risk_level || '')" size="small">{{ riskText(row.risk_level || '') }}</el-tag>
                      </template>
                    </el-table-column>
                    <el-table-column label="观察缺口" align="right" min-width="88">
                      <template #default="{ row }">{{ formatNumber(row.shortage_qty) }}</template>
                    </el-table-column>
                    <el-table-column label="观察建议" align="right" min-width="88">
                      <template #default="{ row }">{{ formatNumber(row.suggested_qty) }}</template>
                    </el-table-column>
                    <el-table-column label="建议来源" min-width="92">
                      <template #default="{ row }">{{ row.suggested_source || '-' }}</template>
                    </el-table-column>
                    <el-table-column label="预计天数" align="right" min-width="86">
                      <template #default="{ row }">{{ row.eta_days ? `${formatNumber(row.eta_days)} 天` : '-' }}</template>
                    </el-table-column>
                    <el-table-column label="原因" min-width="220" show-overflow-tooltip>
                      <template #default="{ row }">{{ row.reason || '-' }}</template>
                    </el-table-column>
                  </el-table>
                </section>
              </template>
              <div v-else class="sku-empty-state">
                <strong>输入 SKU 后查看完整补货决策</strong>
                <span>会同时展示全仓库存、花东供给仓、类目规则、目标周转天数和系统建议。</span>
              </div>
            </div>
          </section>
        </el-tab-pane>

        <el-tab-pane v-if="isTabAllowed('business-forecast')" name="business-forecast">
          <template #label>
            <el-tooltip
              content="未来7天经营趋势观察：看哪些 SKU 需求可能上涨、哪些城市仓有风险，不直接生成今日调拨单。"
              placement="top"
            >
              <span class="tab-help-label">经营趋势预测</span>
            </el-tooltip>
          </template>
          <BusinessForecast
            ref="businessForecastPanelRef"
            mode="forecast"
            @data-updated="refreshBusinessPurchasePanel"
          />
        </el-tab-pane>

        <el-tab-pane v-if="isTabAllowed('business-purchase-export')" name="business-purchase-export">
          <template #label>
            <el-tooltip
              content="运营补货表：按未来7天趋势汇总八大仓补货数量，可确认后导出给采购/ERP。"
              placement="top"
            >
              <span class="tab-help-label">补货导出明细</span>
            </el-tooltip>
          </template>
          <BusinessForecast
            ref="businessForecastRef"
            mode="purchase"
            :purchase-formula="purchaseFormula"
          />
        </el-tab-pane>

        <el-tab-pane v-if="isTabAllowed('sku-stock-warning')" name="sku-stock-warning">
          <template #label>
            <el-tooltip
              content="按每日库存表预测未来60天销量，对比花东+南沙聚水潭库存件数，预警有缺口的 SKU。"
              placement="top"
            >
              <span class="tab-help-label">SKU库存预警</span>
            </el-tooltip>
          </template>
          <SkuStockWarning ref="skuWarningRef" />
        </el-tab-pane>

        <el-tab-pane v-if="isTabAllowed('settings')" name="settings">
          <template #label>
            <el-tooltip
              content="库存分析设置：品牌周转策略、经营趋势因子、花东库存自动同步。"
              placement="top"
            >
              <span class="tab-help-label">库存分析设置</span>
            </el-tooltip>
          </template>
          <div class="risk-settings-panel">
            <div class="policy-editor">
              <div class="policy-editor-head">
                <div class="policy-title-row">
                  <el-tooltip placement="top" popper-class="policy-help-tooltip">
                    <template #content>
                      <div class="policy-help-content">
                        <strong>周转策略说明</strong>
                        <p>按品牌设置目标周转天数、供应商到花东预计天数和仓间规则。</p>
                        <p>保存后系统会立即重算该品牌的风险和补货建议；箱包品牌默认只能由花东补货。</p>
                      </div>
                    </template>
                    <strong class="policy-help-title">周转策略</strong>
                  </el-tooltip>
                </div>
                <span>只按品牌调整，保存后立即重算当前品牌。</span>
              </div>
              <div class="policy-form-grid">
                <div class="policy-field entity">
                  <span>品牌</span>
                  <el-select
                    v-model="policyForm.brand"
                    clearable
                    filterable
                    placeholder="选择品牌"
                    size="large"
                    @change="(value) => applyBrandPolicy(value)"
                  >
                    <el-option v-for="brand in brandOptions" :key="brand" :label="brand" :value="brand" />
                  </el-select>
                </div>
                <div class="policy-field number">
                  <span>目标周转</span>
                  <el-input-number v-model="policyForm.target_days" :min="1" :max="365" :precision="0" controls-position="right" size="large" />
                </div>
                <div class="policy-field number">
                  <span>供应商到花东</span>
                  <el-input-number v-model="policyForm.supplier_eta_days" :min="1" :max="365" :precision="0" controls-position="right" size="large" />
                </div>
                <div class="policy-field rule">
                  <span>仓间规则</span>
                  <el-select v-model="policyForm.allow_jd_transfer" :disabled="isSelectedBrandBox" size="large">
                    <el-option label="允许京东仓互调" :value="true" />
                    <el-option label="禁止京东仓互调" :value="false" />
                  </el-select>
                </div>
                <div class="policy-field action">
                  <span>&nbsp;</span>
                  <el-button :loading="policySaving" size="large" type="primary" plain @click="savePolicy">
                    保存并重算
                  </el-button>
                </div>
              </div>
              <div class="trend-factor-setting-row">
                <div class="trend-factor-copy">
                  <strong>经营趋势因子</strong>
                  <span>关闭后重算时，补货建议不再乘全国趋势上调系数（如 ×1.25），只按各仓销量基线计算；趋势标签仅作展示。</span>
                </div>
                <div class="trend-factor-controls">
                  <el-switch
                    v-model="trendFactorEnabled"
                    active-text="应用"
                    inactive-text="不应用"
                    size="large"
                  />
                  <el-button
                    :loading="trendFactorSaving"
                    size="large"
                    type="primary"
                    plain
                    @click="saveTrendFactorSetting"
                  >
                    保存并重算
                  </el-button>
                </div>
              </div>

              <div class="trend-factor-setting-row purchase-formula-setting-row">
                <div class="trend-factor-copy">
                  <strong>补货算法（补货导出明细）</strong>
                  <span>
                    切换后立即按所选公式重算八大仓补货建议。
                    现行算法 = 7天趋势预测×风险分级×调拨/供应封顶；
                    运营表算法 = 近30日出库 × (目标周转÷30) − 可订购库存(库存+在途)，保留负数展示（负数=已超储）。
                  </span>
                  <em v-if="!canManagePurchaseFormula" class="purchase-formula-locked-tip">仅管理员可调整补货算法</em>
                </div>
                <el-tooltip
                  :disabled="canManagePurchaseFormula"
                  content="仅管理员可调整补货算法"
                  placement="top"
                >
                  <div class="trend-factor-controls">
                    <el-switch
                      :model-value="purchaseFormula"
                      active-value="excel"
                      inactive-value="system"
                      active-text="运营表算法"
                      inactive-text="现行算法"
                      :loading="purchaseFormulaSaving"
                      :disabled="purchaseFormulaSaving || !canManagePurchaseFormula"
                      size="large"
                      @change="switchPurchaseFormula"
                    />
                  </div>
                </el-tooltip>
              </div>

              <div v-loading="syncSettingLoading" class="sync-setting-row">
                <div class="sync-setting-copy">
                  <strong>花东库存自动同步</strong>
                  <span :class="huadongSyncStatusClass">{{ huadongSyncStatusText }}</span>
                  <small>{{ huadongSyncMetaText }}；同步成功后自动重算补货建议</small>
                  <div v-if="huadongSyncSetting.last_status === 'RUNNING' && huadongSyncProgress" class="sync-progress">
                    <el-progress
                      :percentage="huadongSyncProgressPercent"
                      :stroke-width="8"
                      :show-text="false"
                    />
                    <small>{{ huadongSyncProgressMeta }}</small>
                  </div>
                </div>
                <el-tooltip
                  :disabled="canManageHuadongSync"
                  content="仅管理员可修改花东库存自动同步设置"
                  placement="top"
                >
                  <div class="sync-setting-controls">
                    <el-switch
                      v-model="huadongSyncSetting.enabled"
                      active-text="启用"
                      :disabled="!canManageHuadongSync"
                      inactive-text="停用"
                      size="large"
                    />
                    <label class="sync-interval-field">
                      <span>拉取间隔</span>
                      <el-input-number
                        v-model="huadongSyncSetting.interval_minutes"
                        :min="1"
                        :max="1440"
                        :precision="0"
                        :disabled="!canManageHuadongSync"
                        controls-position="right"
                        size="large"
                      />
                      <em>分钟</em>
                    </label>
                    <el-button
                      :disabled="!canManageHuadongSync"
                      :loading="syncSettingSaving"
                      size="large"
                      type="primary"
                      plain
                      @click="saveHuadongSyncSetting"
                    >
                      保存同步设置
                    </el-button>
                  </div>
                </el-tooltip>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane v-if="isTabAllowed('cities')" name="cities">
          <template #label>
            <el-tooltip
              content="城市仓整体健康度：看每个城市仓的高风险 SKU 数、总库存、在途和覆盖天数。"
              placement="top"
            >
              <span class="tab-help-label">城市库存健康度</span>
            </el-tooltip>
          </template>
          <el-table v-loading="cityLoading" :data="cityHealth" border stripe empty-text="暂无城市库存数据">
            <el-table-column prop="warehouse_name" label="城市/仓" min-width="140" />
            <el-table-column prop="region" label="大区" min-width="90" />
            <el-table-column label="有效SKU" align="right" min-width="100">
              <template #default="{ row }">{{ formatNumber(row.active_sku_count) }}</template>
            </el-table-column>
            <el-table-column label="高风险" align="right" min-width="100">
              <template #default="{ row }"><span class="danger-text">{{ formatNumber(row.high_count) }}</span></template>
            </el-table-column>
            <el-table-column label="中风险" align="right" min-width="100">
              <template #default="{ row }">{{ formatNumber(row.mid_count) }}</template>
            </el-table-column>
            <el-table-column label="可调出SKU" align="right" min-width="120">
              <template #default="{ row }">{{ formatNumber(row.excess_count) }}</template>
            </el-table-column>
            <el-table-column label="库存件数" align="right" min-width="120">
              <template #default="{ row }">{{ formatNumber(row.stock_qty) }}</template>
            </el-table-column>
            <el-table-column label="采购未到货" align="right" min-width="120">
              <template #default="{ row }">{{ formatNumber(row.inbound_qty) }}</template>
            </el-table-column>
            <el-table-column label="近7日出库" align="right" min-width="120">
              <template #default="{ row }">{{ formatNumber(row.sales_7d) }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane v-if="isTabAllowed('simulate')" name="simulate">
          <template #label>
            <el-tooltip
              content="手动模拟单个 SKU 调拨：输入调出仓、调入仓和数量，提前看是否安全。"
              placement="top"
            >
              <span class="tab-help-label">单SKU调拨模拟</span>
            </el-tooltip>
          </template>
          <div class="simulator-grid">
            <el-form class="simulator-form" label-position="top">
              <el-form-item label="SKU">
                <el-input v-model="simulator.sku_code" placeholder="例如 3216664" size="large" />
              </el-form-item>
              <el-form-item label="调出仓">
                <el-input v-model="simulator.from_warehouse" placeholder="例如 成都" size="large" />
              </el-form-item>
              <el-form-item label="调入仓">
                <el-input v-model="simulator.to_warehouse" placeholder="例如 北京" size="large" />
              </el-form-item>
              <el-form-item label="调拨数量">
                <el-input-number v-model="simulator.transfer_qty" :min="1" :step="1" size="large" />
              </el-form-item>
              <el-button :icon="Connection" size="large" type="primary" @click="simulateTransfer">
                模拟调拨
              </el-button>
            </el-form>

            <div class="simulation-result">
              <template v-if="simulation">
                <div class="result-status" :class="{ safe: simulation.is_safe }">
                  {{ simulation.is_safe ? '建议可执行' : '存在风险' }}
                </div>
                <dl>
                  <div><dt>预计到达</dt><dd>{{ simulation.eta_days }} 天</dd></div>
                  <div><dt>调出后库存</dt><dd>{{ formatNumber(simulation.from_stock_after) }}</dd></div>
                  <div><dt>调出后可售</dt><dd>{{ formatDays(simulation.from_days_after) }}</dd></div>
                  <div><dt>调入后库存</dt><dd>{{ formatNumber(simulation.to_stock_after) }}</dd></div>
                  <div><dt>调入后可售</dt><dd>{{ formatDays(simulation.to_days_after) }}</dd></div>
                </dl>
                <p v-if="Array.isArray(simulation.warnings) && simulation.warnings.length" class="warning-text">
                  {{ simulation.warnings.join('；') }}
                </p>
              </template>
              <template v-else>
                <span class="empty-result">填写 SKU 与调拨路径后，可立即验证是否会拆东墙补西墙。</span>
              </template>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
      <div v-else class="tabs-empty-state">
        <el-empty description="当前角色/人员没有任何页签的查看权限，请联系管理员在「系统管理 → 权限管理 → 库存分析决策 → 页面内容可见控制」中配置">
          <template #image>
            <el-icon :size="48"><Lock /></el-icon>
          </template>
        </el-empty>
      </div>
    </main>

    <el-drawer
      v-model="agentDrawerVisible"
      class="agent-drawer"
      direction="rtl"
      size="90vw"
    >
      <template #header>
        <div class="agent-header">
          <div class="agent-title-block">
            <strong>AI库存助手</strong>
            <span v-if="activeAgentPlan">
              {{ formatSkuCode(activeAgentPlan.sku_code) }} · {{ formatTransferPath(activeAgentPlan as unknown as Record<string, unknown>) }}
            </span>
          </div>
          <div v-if="activeAgentPlan?.reason" class="agent-reason-strip">
            <span>原因</span>
            <p>{{ cleanReasonText(activeAgentPlan.reason) }}</p>
          </div>
        </div>
      </template>

      <div class="agent-shell">
        <aside v-if="activeAgentPlan" class="agent-data-panel">
          <section class="agent-summary-block">
            <div class="agent-summary-grid">
              <div>
                <span>SKU</span>
                <strong>{{ formatSkuCode(activeAgentPlan.sku_code) }}</strong>
              </div>
              <div>
                <span>品牌</span>
                <strong>{{ activeAgentPlan.brand || '-' }}</strong>
              </div>
              <div>
                <span>类目</span>
                <strong>{{ activeAgentPlan.category || '-' }}</strong>
              </div>
              <div class="wide">
                <span>商品名称</span>
                <strong :title="activeAgentPlan.product_name">{{ activeAgentPlan.product_name || '-' }}</strong>
              </div>
              <div>
                <span>调拨方向</span>
                <strong>{{ formatTransferPath(activeAgentPlan as unknown as Record<string, unknown>) }}</strong>
              </div>
              <div>
                <span>调拨数量</span>
                <strong>{{ formatNumber(activeAgentPlan.transfer_qty) }} 件</strong>
              </div>
              <div>
                <span>预计到达天数</span>
                <strong>{{ formatTransferEta(activeAgentPlan as unknown as Record<string, unknown>) }}</strong>
              </div>
              <div>
                <span>目标周转</span>
                <strong>{{ formatDays(activeAgentPlan.target_days) }}</strong>
              </div>
            </div>
          </section>

          <section class="agent-compare-block">
            <h3>库存与动销对比</h3>
            <div class="agent-compare-table">
              <div class="agent-compare-row head">
                <span>指标</span>
                <strong>{{ activeAgentPlan.from_warehouse }}</strong>
                <strong>{{ activeAgentPlan.to_warehouse }}</strong>
              </div>
              <div class="agent-compare-row">
                <span>库存件数</span>
                <strong>{{ formatNumber(activeAgentPlan.from_stock_qty) }}</strong>
                <strong>{{ formatNumber(activeAgentPlan.to_stock_qty) }}</strong>
              </div>
              <div class="agent-compare-row">
                <span>采购未到货</span>
                <strong>{{ formatNumber(activeAgentPlan.from_inbound_qty) }}</strong>
                <strong>{{ formatNumber(activeAgentPlan.to_inbound_qty) }}</strong>
              </div>
              <div class="agent-compare-row">
                <span>昨日销量</span>
                <strong>{{ formatNumber(activeAgentPlan.from_sales_1d) }}</strong>
                <strong>{{ formatNumber(activeAgentPlan.to_sales_1d) }}</strong>
              </div>
              <div class="agent-compare-row">
                <span>近7日销量</span>
                <strong>{{ formatNumber(activeAgentPlan.from_sales_7d) }}</strong>
                <strong>{{ formatNumber(activeAgentPlan.to_sales_7d) }}</strong>
              </div>
              <div class="agent-compare-row">
                <span>近30日销量</span>
                <strong>{{ formatNumber(activeAgentPlan.from_sales_30d) }}</strong>
                <strong>{{ formatNumber(activeAgentPlan.to_sales_30d) }}</strong>
              </div>
              <div class="agent-compare-row">
                <span>平均日均销量</span>
                <strong>{{ formatNumber(activeAgentPlan.from_daily_sales, 2) }}</strong>
                <strong>{{ formatNumber(activeAgentPlan.to_daily_sales, 2) }}</strong>
              </div>
              <div class="agent-compare-row">
                <span>目标期预测需要销量</span>
                <strong>{{ formatNumber(activeAgentPlan.from_demand_30d) }}</strong>
                <strong>{{ formatNumber(activeAgentPlan.to_demand_30d) }}</strong>
              </div>
            </div>
          </section>

          <section class="agent-all-warehouse-block">
            <h3>该SKU全仓库库存</h3>
            <el-table
              v-loading="skuWarehouseLoading"
              :data="skuWarehouseRows"
              border
              class="agent-warehouse-table"
              empty-text="暂无其他仓库数据"
              height="100%"
              size="small"
              stripe
            >
              <el-table-column label="仓库" min-width="86" show-overflow-tooltip>
                <template #default="{ row }">{{ row.warehouse_name || row.warehouse_code }}</template>
              </el-table-column>
              <el-table-column label="风险" min-width="62">
                <template #default="{ row }">
                  <el-tag :type="riskTagType(row.risk_level || '')" size="small">{{ riskText(row.risk_level || '') }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="库存" align="right" min-width="62">
                <template #default="{ row }">{{ formatNumber(row.stock_qty) }}</template>
              </el-table-column>
              <el-table-column label="在途" align="right" min-width="62">
                <template #default="{ row }">{{ formatNumber(row.inbound_qty) }}</template>
              </el-table-column>
              <el-table-column label="昨日" align="right" min-width="62">
                <template #default="{ row }">{{ formatNumber(row.sales_1d) }}</template>
              </el-table-column>
              <el-table-column label="7日" align="right" min-width="62">
                <template #default="{ row }">{{ formatNumber(row.sales_7d) }}</template>
              </el-table-column>
              <el-table-column label="30日" align="right" min-width="62">
                <template #default="{ row }">{{ formatNumber(row.sales_30d) }}</template>
              </el-table-column>
              <el-table-column label="日均" align="right" min-width="62">
                <template #default="{ row }">{{ formatNumber(row.daily_sales, 2) }}</template>
              </el-table-column>
              <el-table-column label="30天预测" align="right" min-width="74">
                <template #default="{ row }">{{ formatNumber(row.demand_30d) }}</template>
              </el-table-column>
              <el-table-column label="预计可售" align="right" min-width="74">
                <template #default="{ row }">{{ formatDays(row.days_of_supply) }}</template>
              </el-table-column>
            </el-table>
          </section>
        </aside>

        <section class="agent-chat-panel">
          <div ref="agentBodyRef" class="agent-messages">
            <div v-if="!activeAgentMessages.length" class="agent-empty-choice">
              <strong>你想先了解哪一块？</strong>
              <span>AI 已带入当前调拨方案、SKU、库存、销量、风险和全仓数据，选择一个问题后再开始分析。</span>
              <div class="agent-choice-grid">
                <el-button
                  v-for="item in agentStarterPrompts"
                  :key="item.label"
                  :disabled="agentLoading"
                  plain
                  type="primary"
                  @click="sendAgentMessage(item.message)"
                >
                  {{ item.label }}
                </el-button>
              </div>
            </div>
            <div
              v-for="(message, index) in activeAgentMessages"
              :key="`${message.role}-${index}`"
              class="agent-message"
              :class="message.role"
              :data-agent-message-index="index"
            >
              <div
                v-if="message.role === 'assistant' && message.content"
                class="agent-bubble markdown-body"
                v-html="parseMarkdown(message.content)"
              />
              <div v-else-if="message.role === 'assistant'" class="agent-bubble muted">AI助手正在生成...</div>
              <div v-else class="agent-bubble">{{ message.content }}</div>
            </div>
          </div>

          <div class="agent-quick-actions">
            <el-button :disabled="agentLoading" size="small" @click="sendAgentMessage('为什么调这个数量？')">
              为什么调这个数量
            </el-button>
            <el-button :disabled="agentLoading" size="small" @click="sendAgentMessage('如果不调会怎样？')">
              不调会怎样
            </el-button>
            <el-button :disabled="agentLoading" size="small" @click="sendAgentMessage('其他仓库库存怎么样？')">
              其他仓库库存怎么样
            </el-button>
            <el-button :disabled="agentLoading" size="small" @click="sendAgentMessage('帮我更新解释，写得正式一点。')">
              更新解释
            </el-button>
          </div>

          <div class="agent-input-row">
            <el-input
              v-model="agentInput"
              :disabled="agentLoading"
              :autosize="{ minRows: 2, maxRows: 4 }"
              placeholder="继续问这条调拨方案..."
              type="textarea"
              @keydown.enter.exact.prevent="sendAgentMessage()"
            />
            <el-button :disabled="agentLoading" :loading="agentLoading" type="primary" @click="sendAgentMessage()">
              发送
            </el-button>
          </div>
        </section>
      </div>
    </el-drawer>

    <el-dialog
      v-model="importDialogVisible"
      class="import-dialog"
      :close-on-click-modal="!importing"
      :close-on-press-escape="!importing"
      destroy-on-close
      :show-close="!importing"
      title="导入库存RDC横版数据"
      width="680px"
      @closed="resetSelectedFile"
    >
      <el-upload
        ref="uploadRef"
        v-model:file-list="fileList"
        accept=".xlsx"
        action="#"
        :auto-upload="false"
        :before-upload="beforeUpload"
        drag
        :disabled="importing"
        :limit="1"
        :on-change="handleFileChange"
        :on-remove="handleFileRemove"
      >
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div class="upload-title">拖拽库存 Excel 到此处，或点击选择文件</div>
        <div class="upload-hint">导入后自动拆成长表、重算风险与调拨建议</div>
        <div class="upload-hint demo_life-rule-hint">
          品牌规则：iGear 按一级类目自动拆分 —— 工业品 →「iGear工业品」、家装建材 →「iGear」、其余类目不导入
        </div>
      </el-upload>
      <template #footer>
        <div class="dialog-footer">
          <el-button :disabled="importing" size="large" @click="importDialogVisible = false">取消</el-button>
          <el-button :disabled="importing" size="large" @click="resetSelectedFile">清空文件</el-button>
          <el-button :disabled="!canSubmitImport" :loading="importing" size="large" type="primary" @click="submitImport">
            开始导入
          </el-button>
        </div>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.inventory-page {
  min-height: 100vh;
  padding: 28px;
  color: var(--text-primary);
  background: var(--app-bg);
}

.page-header,
.toolbar,
.pagination-bar,
.header-actions,
.toolbar-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.page-header,
.toolbar,
.pagination-bar {
  justify-content: space-between;
}

.page-header {
  align-items: flex-end;
  flex-wrap: wrap;
  max-width: 1460px;
  margin: 0 auto 18px;
}

.import-status-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  max-width: 1460px;
  margin: -4px auto 18px;
  padding: 12px 16px;
  border: 1px solid light-dark(#bfdbfe, var(--border-color));
  border-radius: 12px;
  color: light-dark(#1e3a8a, #93c5fd);
  background: light-dark(#eff6ff, rgba(96, 165, 250, .12));
  box-shadow: var(--shadow-sm);
}

.import-status-strip > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.import-status-strip strong {
  font-size: 14px;
}

.import-status-strip span {
  font-size: 13px;
  line-height: 1.5;
}

.import-status-strip.success {
  border-color: light-dark(#bbf7d0, var(--border-color));
  color: light-dark(#166534, var(--text-secondary));
  background: light-dark(#f0fdf4, var(--primary-surface-2));
}

.import-status-strip.warning {
  border-color: light-dark(#fed7aa, var(--border-color));
  color: light-dark(#9a3412, #fbbf24);
  background: light-dark(#fff7ed, rgba(251, 191, 36, .12));
}

.import-status-strip.error {
  border-color: light-dark(#fecaca, var(--border-color));
  color: light-dark(#991b1b, #fca5a5);
  background: light-dark(#fef2f2, rgba(248, 113, 113, .12));
}

.header-leading {
  min-width: 0;
  flex: 1 1 720px;
}

.header-heading-row {
  display: flex;
  align-items: flex-start;
  gap: 24px;
}

.header-title-block {
  min-width: 0;
  flex: 0 1 auto;
}

.header-snapshot {
  display: grid;
  min-width: 190px;
  flex: 0 0 220px;
  gap: 5px;
  align-self: center;
  padding: 11px 14px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--app-surface);
  box-shadow: var(--shadow-sm);
}

.header-snapshot span {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
}

.header-snapshot strong {
  overflow: hidden;
  color: var(--text-heading);
  font-size: 20px;
  font-weight: 850;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header-actions {
  flex: 0 1 auto;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.header-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--primary);
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
}

.page-header h1 {
  margin: 0;
  color: var(--text-heading);
  font-size: 30px;
  line-height: 1.2;
}

.subtitle {
  margin: 10px 0 0;
  color: var(--text-secondary);
  font-size: 15px;
  line-height: 1.7;
}

.decision-panel,
.simulation-result {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--app-surface);
  box-shadow: var(--shadow-lg);
}

.danger-text {
  color: light-dark(#dc2626, #f87171) !important;
}

.decision-panel {
  max-width: 1460px;
  margin: 0 auto;
  padding: 18px;
}

.tab-help-label {
  display: inline-flex;
  align-items: center;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
  letter-spacing: 0.01em;
}

/* ── Tab 导航排版 ─────────────────────────────────────────── */
:deep(.el-tabs__header) {
  margin: 0 0 16px;
  padding: 0 4px;
}
:deep(.el-tabs__nav-wrap)::after {
  background-color: var(--border-color);
}
:deep(.el-tabs__nav) {
  gap: 0;
}
:deep(.el-tabs__item) {
  height: 44px;
  line-height: 44px;
  padding: 0 22px !important;
  margin-right: 14px !important;
  font-size: 14px !important;
  font-weight: 500;
  color: var(--text-secondary) !important;
  border-radius: 8px 8px 0 0;
  transition: color .18s ease, background-color .18s ease;
  white-space: nowrap;
  box-sizing: border-box;
}
:deep(.el-tabs__item:last-of-type) {
  margin-right: 0 !important;
}
:deep(.el-tabs__item:hover) {
  color: var(--text-heading) !important;
  background: var(--primary-surface);
}
:deep(.el-tabs__item.is-active) {
  color: var(--primary) !important;
  font-weight: 700;
  background: var(--primary-surface);
}
:deep(.el-tabs__item.is-active .tab-help-label) {
  color: var(--primary);
}
:deep(.el-tabs__active-bar) {
  height: 2px;
  background: linear-gradient(90deg, var(--primary) 0%, var(--primary-light) 100%);
  border-radius: 2px;
}

/* Tab 视觉顺序：补货导出明细 → SKU库存预警 → 经营趋势预测 */
:deep(#tab-business-purchase-export) { order: 1; }
:deep(#tab-sku-stock-warning)          { order: 2; }
:deep(#tab-business-forecast)          { order: 3; }
:deep(#tab-plans)                      { order: 4; }
:deep(#tab-sku-decision)               { order: 5; }
:deep(#tab-settings)                     { order: 6; }
:deep(#tab-cities)                     { order: 7; }
:deep(#tab-simulate)                   { order: 8; }

/* ── 页签全空（无任何可见权限） ─────────────────────────── */
.tabs-empty-state {
  padding: 40px 20px;
  text-align: center;
  color: var(--text-secondary);
}
.tabs-empty-state .el-icon {
  color: var(--text-muted);
}

.sku-link {
  padding: 0;
  font-weight: 700;
}

.sku-copy-link {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  color: light-dark(#1677ff, #93c5fd);
  cursor: pointer;
  font-weight: 750;
  text-decoration: none;
  text-overflow: ellipsis;
  user-select: text;
  white-space: nowrap;
  -webkit-user-select: text;
}

.sku-copy-link:hover {
  color: light-dark(#0958d9, #93c5fd);
  text-decoration: underline;
}

.sku-copy-link::selection {
  background: rgba(22, 119, 255, 0.22);
}

.route-path {
  display: inline-flex;
  max-width: 100%;
  align-items: center;
  gap: 4px;
  overflow: hidden;
  white-space: nowrap;
}

.table-help-header {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  cursor: help;
  text-decoration: underline dotted rgba(59, 130, 246, 0.48);
  text-underline-offset: 3px;
}

.table-help-header.right {
  justify-content: flex-end;
}

.table-help-content {
  max-width: 360px;
  line-height: 1.65;
}

.table-help-content strong {
  display: block;
  margin-bottom: 4px;
  font-size: 13px;
}

.table-help-content p {
  margin: 0;
}

.table-help-content p + p {
  margin-top: 4px;
}

.route-node {
  min-width: 0;
  overflow: hidden;
  color: light-dark(#172033, var(--text-secondary));
  font-weight: 650;
  text-overflow: ellipsis;
}

.route-node:last-child {
  color: light-dark(#1677ff, #93c5fd);
  font-weight: 760;
}

.route-arrow {
  flex: 0 0 auto;
  color: light-dark(#64748b, var(--text-secondary));
}

.sku-decision-view {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.sku-decision-toolbar,
.sku-decision-content {
  border: 1px solid light-dark(#cbd5e1, var(--border-color));
  border-radius: 8px;
  background: light-dark(#f8fafc, var(--app-surface-2));
}

.sku-decision-toolbar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
}

.sku-search-panel,
.policy-editor {
  min-width: 0;
  border: 1px solid light-dark(#d7e0ea, var(--border-color));
  border-radius: 8px;
  background: light-dark(#fff, var(--app-surface));
}

.risk-settings-panel {
  min-width: 0;
  margin-bottom: 14px;
  padding: 14px;
  border: 1px solid light-dark(#d7e0ea, var(--border-color));
  border-radius: 8px;
  background: light-dark(#f8fafc, var(--app-surface-2));
}

.sku-search-panel {
  display: grid;
  grid-template-columns: minmax(190px, 250px) minmax(320px, 520px);
  gap: 18px;
  align-items: center;
  padding: 12px 14px;
}

.sku-panel-title {
  min-width: 0;
}

.sku-panel-title strong {
  display: block;
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 16px;
  font-weight: 850;
}

.sku-panel-title span {
  display: block;
  margin-top: 4px;
  color: light-dark(#64748b, var(--text-secondary));
  font-size: 12px;
  line-height: 1.4;
}

.sku-search-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: start;
}

.policy-editor {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  padding: 0;
  border: 0;
  background: transparent;
}

.policy-editor-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.policy-title-row {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.policy-editor-head strong {
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 15px;
}

.policy-help-title {
  cursor: help;
  text-decoration: underline dotted rgba(59, 130, 246, 0.48);
  text-underline-offset: 3px;
}

.policy-help-content {
  max-width: 330px;
  line-height: 1.65;
}

.policy-help-content strong {
  display: block;
  margin-bottom: 4px;
  font-size: 13px;
}

.policy-help-content p {
  margin: 0;
}

.policy-help-content p + p {
  margin-top: 4px;
}

.policy-editor-head span {
  color: light-dark(#64748b, var(--text-secondary));
  font-size: 12px;
}

.policy-form-grid {
  display: grid;
  grid-template-columns:
    minmax(220px, 1.45fr)
    minmax(118px, 0.7fr)
    minmax(132px, 0.75fr)
    minmax(170px, 1fr)
    minmax(104px, auto);
  gap: 12px;
  align-items: end;
}

.policy-field {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 6px;
}

.policy-field > span {
  color: light-dark(#475569, var(--text-secondary));
  font-size: 12px;
  font-weight: 750;
  line-height: 1;
}

.policy-field :deep(.el-select),
.policy-field :deep(.el-input-number),
.policy-field :deep(.el-button) {
  width: 100%;
}

.policy-field.action {
  justify-content: end;
}

.sync-setting-row {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(420px, auto);
  gap: 14px;
  align-items: center;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid light-dark(#e2e8f0, var(--border-color));
}

.trend-factor-setting-row {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(420px, auto);
  gap: 14px;
  align-items: center;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid light-dark(#e2e8f0, var(--border-color));
}

.trend-factor-copy {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.trend-factor-copy strong {
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 14px;
  font-weight: 850;
}

.trend-factor-copy span {
  overflow: hidden;
  color: light-dark(#475569, var(--text-secondary));
  font-size: 13px;
  text-overflow: ellipsis;
}

.purchase-formula-locked-tip {
  align-self: flex-start;
  color: light-dark(#d97706, #fbbf24);
  font-size: 12px;
  font-style: normal;
}

.trend-factor-controls {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}

.sync-setting-copy {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.sync-setting-copy strong {
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 14px;
  font-weight: 850;
}

.sync-setting-copy span {
  overflow: hidden;
  color: light-dark(#475569, var(--text-secondary));
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sync-setting-copy span.success {
  color: light-dark(#047857, #6ee7b7);
}

.sync-setting-copy span.danger {
  color: light-dark(#b91c1c, #fca5a5);
}

.sync-setting-copy span.running {
  color: light-dark(#1d4ed8, #93c5fd);
}

.sync-setting-copy small {
  color: light-dark(#94a3b8, var(--text-secondary));
  font-size: 12px;
}

.sync-progress {
  display: grid;
  max-width: 620px;
  gap: 4px;
  padding-top: 2px;
}

.sync-progress small {
  color: light-dark(#475569, var(--text-secondary));
  font-weight: 650;
}

.sync-setting-controls {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}

.sync-interval-field {
  display: grid;
  grid-template-columns: auto minmax(118px, 132px) auto;
  gap: 8px;
  align-items: center;
  color: light-dark(#475569, var(--text-secondary));
  font-size: 12px;
  font-weight: 750;
}

.sync-interval-field :deep(.el-input-number) {
  width: 100%;
}

.sync-interval-field em {
  color: light-dark(#64748b, var(--text-secondary));
  font-style: normal;
}

.sku-decision-content {
  min-height: 520px;
  padding: 14px;
}

.sku-overview-grid {
  display: grid;
  grid-template-columns:
    minmax(260px, 1.55fr)
    repeat(3, minmax(145px, 1fr))
    minmax(280px, 1.7fr);
  gap: 10px;
  margin-bottom: 14px;
}

.sku-overview-card {
  min-width: 0;
  padding: 12px;
  border: 1px solid light-dark(#cbd5e1, var(--border-color));
  border-radius: 8px;
  background: light-dark(#f8fafc, var(--app-surface-2));
}

.sku-overview-card span {
  display: block;
  margin-bottom: 6px;
  color: light-dark(#475569, var(--text-secondary));
  font-size: 12px;
  font-weight: 700;
}

.sku-overview-card strong {
  display: block;
  overflow: hidden;
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 18px;
  font-weight: 850;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sku-overview-card p {
  overflow: hidden;
  margin: 6px 0 0;
  color: light-dark(#334155, var(--text-primary));
  font-size: 13px;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sku-overview-card.product strong {
  font-size: 16px;
}

.sku-overview-card.product .product-brand-category {
  color: light-dark(#64748b, var(--text-secondary));
  font-size: 12px;
  font-weight: 700;
}

.business-trend-card {
  grid-column: auto;
  background: light-dark(#f7fbff, var(--app-surface-2));
}

.business-trend-tags {
  display: flex;
  min-height: 24px;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 7px;
}

.sku-overview-card .business-trend-summary {
  white-space: normal;
}

.sku-decision-columns {
  display: grid;
  grid-template-columns: minmax(0, 1.08fr) minmax(430px, 0.92fr);
  gap: 14px;
  align-items: start;
}

.sku-section {
  min-width: 0;
  padding: 10px;
  border: 1px solid light-dark(#d7e0ea, var(--border-color));
  border-radius: 8px;
  background: light-dark(#fff, var(--app-surface));
}

.section-title-row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 8px;
}

.section-title-row strong {
  display: block;
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 16px;
  font-weight: 850;
}

.section-title-row span {
  display: block;
  margin-top: 3px;
  color: light-dark(#64748b, var(--text-secondary));
  font-size: 12px;
}

.business-observation-section {
  margin-top: 14px;
}

.business-observation-head {
  align-items: center;
  gap: 12px;
}

.business-observation-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  color: light-dark(#475569, var(--text-secondary));
  font-size: 12px;
  font-weight: 750;
}

.business-observation-table {
  width: 100%;
}

.strong-table :deep(.el-table__cell) {
  border-color: light-dark(#cbd5e1, var(--border-color)) !important;
  color: light-dark(#172033, var(--text-secondary));
}

.strong-table :deep(.el-table__header th) {
  background: light-dark(#eaf0f6, rgba(96, 165, 250, .12)) !important;
  color: light-dark(#172033, var(--text-secondary));
  font-weight: 800;
}

.sku-empty-state {
  display: flex;
  min-height: 450px;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 8px;
  border: 1px dashed light-dark(#cbd5e1, var(--border-color));
  border-radius: 8px;
  color: light-dark(#64748b, var(--text-secondary));
  text-align: center;
}

.sku-empty-state strong {
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 18px;
}

.reason-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
}

.reason-detail-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 6px;
  background: light-dark(#eff6ff, rgba(96, 165, 250, .12));
  color: light-dark(#2563eb, #93c5fd);
  cursor: default;
  font-size: 13px;
  font-weight: 700;
  line-height: 24px;
}

:global(.reason-popover.el-popper) {
  padding: 0;
  border: 1px solid light-dark(#cbd5e1, var(--border-color));
  border-radius: 8px;
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.16);
}

.reason-card {
  overflow: hidden;
  border-radius: 8px;
  background: light-dark(#fff, var(--app-surface));
}

.reason-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  background: light-dark(#f8fafc, var(--app-surface-2));
  border-bottom: 1px solid light-dark(#e2e8f0, var(--border-color));
}

.reason-card-head strong {
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 14px;
}

.reason-card-head span {
  color: light-dark(#64748b, var(--text-secondary));
  font-size: 12px;
  white-space: nowrap;
}

.reason-full-text {
  margin: 0;
  padding: 12px 16px 14px;
  color: light-dark(#1e293b, var(--text-primary));
  font-size: 13px;
  line-height: 1.75;
  white-space: normal;
  word-break: break-word;
}

.toolbar {
  margin-bottom: 16px;
}

.toolbar-left {
  flex: 1;
  min-width: 0;
  flex-wrap: wrap;
}

.toolbar-right {
  display: flex;
  flex: none;
  align-items: center;
  gap: 10px;
}

.toolbar-left :deep(.el-select),
.toolbar-left :deep(.el-input),
.toolbar-left :deep(.el-input-number) {
  width: 190px;
}

.column-picker {
  padding: 2px 0 4px;
}

.column-picker-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.column-picker-head strong {
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 14px;
}

.column-checkbox-group {
  display: grid;
  grid-template-columns: 1fr;
  gap: 2px;
}

.column-checkbox-group :deep(.el-checkbox) {
  height: 28px;
  margin-right: 0;
}

.column-checkbox-group :deep(.el-checkbox__label) {
  color: light-dark(#334155, var(--text-primary));
  font-size: 13px;
}

.plan-cell-emphasis {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  min-width: 58px;
  border-radius: 6px;
  padding: 2px 7px;
  font-weight: 800;
  line-height: 1.45;
}

.plan-cell-emphasis.qty {
  color: light-dark(#0f172a, var(--text-primary));
}

.plan-cell-emphasis.risk-days {
  color: light-dark(#b42318, #fca5a5);
  background: light-dark(#fff1f2, rgba(248, 113, 113, .12));
}

.plan-cell-emphasis.surplus-days {
  color: light-dark(#075985, #93c5fd);
  background: light-dark(#eff6ff, rgba(96, 165, 250, .12));
}

.pagination-bar {
  margin-top: 16px;
  color: var(--text-secondary);
  font-size: 14px;
}

.agent-drawer :deep(.el-drawer__body) {
  padding: 0;
}

.agent-drawer :deep(.el-drawer__header) {
  margin-bottom: 0;
  padding: 12px 22px 0;
}

.agent-header {
  display: grid;
  grid-template-columns: 200px minmax(520px, 1480px) 1fr;
  align-items: start;
  column-gap: 16px;
  min-width: 0;
  width: calc(100% - 44px);
}

.agent-title-block {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 6px;
}

.agent-title-block strong {
  color: var(--text-heading);
  font-size: 17px;
}

.agent-title-block span {
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-reason-strip {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: start;
  gap: 10px;
  width: 100%;
  margin-top: 0;
  padding: 6px 10px;
  border: 1px solid light-dark(#bfdbfe, var(--border-color));
  border-radius: 8px;
  background: light-dark(#eff6ff, rgba(96, 165, 250, .12));
}

.agent-reason-strip span {
  color: light-dark(#1d4ed8, #93c5fd);
  font-size: 14px;
  font-weight: 800;
  line-height: 1.7;
  white-space: nowrap;
}

.agent-reason-strip p {
  margin: 0;
  color: light-dark(#1e293b, var(--text-primary));
  font-size: 14px;
  line-height: 1.45;
  word-break: break-word;
}

.agent-shell {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  height: calc(100% + 34px);
  min-height: 0;
  margin-top: -34px;
  padding: 0 12px 12px;
  background: light-dark(#f8fafc, var(--app-surface-2));
}

.agent-data-panel,
.agent-chat-panel {
  min-width: 0;
  min-height: 0;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--app-surface);
  box-shadow: var(--shadow-lg);
}

.agent-data-panel {
  display: flex;
  overflow: hidden;
  flex-direction: column;
  padding: 12px;
}

.agent-chat-panel {
  display: flex;
  flex-direction: column;
}

.agent-summary-block {
  border-bottom: 1px solid var(--border-color);
  flex: none;
  padding-bottom: 9px;
}

.agent-summary-grid {
  display: grid;
  grid-template-columns: minmax(200px, 0.7fr) minmax(120px, 0.45fr) minmax(300px, 2.4fr);
  gap: 8px 12px;
  align-items: end;
}

.agent-summary-grid div {
  min-width: 0;
}

.agent-summary-grid .wide {
  grid-column: auto;
}

.agent-summary-grid span {
  display: block;
  margin-bottom: 2px;
  color: var(--text-secondary);
  font-size: 11px;
}

.agent-summary-grid strong {
  display: block;
  overflow: hidden;
  color: var(--text-heading);
  font-size: 13px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-compare-block {
  flex: none;
  padding-top: 10px;
}

.agent-all-warehouse-block {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  margin-top: 10px;
  border-top: 1px solid var(--border-color);
  padding-top: 10px;
}

.agent-compare-block h3,
.agent-all-warehouse-block h3 {
  margin: 0 0 8px;
  color: var(--text-heading);
  font-size: 15px;
  font-weight: 800;
}

.agent-compare-table {
  display: grid;
  overflow: hidden;
  border: 1px solid light-dark(#e2e8f0, var(--border-color));
  border-radius: 8px;
}

.agent-compare-row {
  display: grid;
  grid-template-columns: minmax(130px, 1.15fr) repeat(2, minmax(92px, 0.85fr));
  min-height: 34px;
  border-bottom: 1px solid light-dark(#e2e8f0, var(--border-color));
  background: light-dark(#fff, var(--app-surface));
}

.agent-compare-row:last-child {
  border-bottom: 0;
}

.agent-compare-row.head {
  background: light-dark(#eef2f7, var(--app-surface-2));
}

.agent-compare-row span,
.agent-compare-row strong {
  display: flex;
  align-items: center;
  min-width: 0;
  border-right: 1px solid light-dark(#e2e8f0, var(--border-color));
  padding: 0 10px;
}

.agent-compare-row span {
  color: light-dark(#334155, var(--text-primary));
  font-size: 13px;
  font-weight: 650;
}

.agent-compare-row strong {
  justify-content: flex-end;
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 13px;
  font-weight: 800;
  text-align: right;
  white-space: nowrap;
}

.agent-compare-row strong:last-child {
  border-right: 0;
}

.agent-compare-row.head span,
.agent-compare-row.head strong {
  color: var(--text-heading);
}

.agent-warehouse-table {
  width: 100%;
  min-height: 0;
  flex: 1;
  overflow: hidden;
  border: 1px solid light-dark(#cbd5e1, var(--border-color));
  border-radius: 6px;
  --el-table-border: 1px solid #cbd5e1;
  --el-table-border-color: light-dark(#cbd5e1, var(--border-color));
  --el-table-header-bg-color: light-dark(#eef2f7, var(--table-header-bg));
  --el-table-row-hover-bg-color: light-dark(#f8fafc, var(--primary-surface-2));
}

.agent-warehouse-table :deep(.el-table__cell) {
  border-color: light-dark(#cbd5e1, var(--border-color)) !important;
  padding: 5px 0;
}

.agent-warehouse-table :deep(.el-table__header th) {
  color: light-dark(#334155, var(--text-primary));
  font-weight: 800;
  background: light-dark(#eef2f7, var(--app-surface-2));
}

.agent-warehouse-table :deep(.el-table__body td) {
  color: light-dark(#1e293b, var(--text-primary));
  font-weight: 650;
}

.agent-warehouse-table :deep(.el-table__inner-wrapper::before),
.agent-warehouse-table :deep(.el-table__inner-wrapper::after) {
  background-color: light-dark(#cbd5e1, rgba(96, 165, 250, .12));
}

.agent-warehouse-table :deep(.cell) {
  padding: 0 8px;
}

.agent-messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 18px;
}

.agent-empty-choice {
  display: flex;
  min-height: 100%;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 12px;
  padding: 28px;
  color: light-dark(#64748b, var(--text-secondary));
  text-align: center;
}

.agent-empty-choice strong {
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 18px;
  font-weight: 850;
}

.agent-empty-choice span {
  max-width: 520px;
  font-size: 13px;
  line-height: 1.7;
}

.agent-choice-grid {
  display: grid;
  width: min(100%, 520px);
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 4px;
}

.agent-choice-grid :deep(.el-button) {
  justify-content: center;
  min-height: 38px;
  margin: 0;
}

.agent-message {
  display: flex;
  margin-bottom: 14px;
}

.agent-message.user {
  justify-content: flex-end;
}

.agent-bubble {
  max-width: 94%;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 11px 13px;
  color: var(--text-primary);
  background: var(--app-surface);
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.agent-bubble.markdown-body {
  white-space: normal;
}

.markdown-body :deep(p) {
  margin: 0 0 9px;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin: 2px 0 10px;
  color: var(--text-heading);
  font-weight: 800;
  line-height: 1.35;
}

.markdown-body :deep(h1) {
  font-size: 18px;
}

.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  font-size: 15px;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 8px 0 10px;
  padding-left: 18px;
}

.markdown-body :deep(li) {
  margin: 4px 0;
}

.markdown-body :deep(strong) {
  color: var(--text-heading);
  font-weight: 800;
}

.markdown-body :deep(code) {
  padding: 1px 5px;
  border-radius: 4px;
  background: light-dark(#e2e8f0, rgba(96, 165, 250, .12));
  color: light-dark(#0f172a, var(--text-primary));
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
}

.markdown-body :deep(pre) {
  overflow-x: auto;
  margin: 8px 0;
  border-radius: 8px;
  padding: 10px;
  background: #0f172a;
  color: light-dark(#e2e8f0, var(--text-secondary));
}

.markdown-body :deep(pre code) {
  padding: 0;
  background: transparent;
  color: inherit;
}

.markdown-body :deep(blockquote) {
  margin: 8px 0;
  border-left: 3px solid #93c5fd;
  padding: 4px 0 4px 10px;
  color: var(--text-secondary);
}

.markdown-body :deep(hr) {
  height: 1px;
  margin: 12px 0;
  border: 0;
  background: var(--border-color);
}

.markdown-body :deep(.markdown-table-wrap) {
  max-width: 100%;
  overflow-x: auto;
  margin: 8px 0 12px;
  border: 1px solid light-dark(#cbd5e1, var(--border-color));
  border-radius: 6px;
}

.markdown-body :deep(table) {
  width: 100%;
  min-width: 320px;
  border-collapse: collapse;
  font-size: 13px;
  table-layout: fixed;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid light-dark(#cbd5e1, var(--border-color));
  padding: 8px 10px;
  color: light-dark(#1e293b, var(--text-primary));
  text-align: left;
  vertical-align: middle;
  word-break: break-word;
}

.markdown-body :deep(th) {
  background: light-dark(#eef2f7, var(--app-surface-2));
  color: var(--text-heading);
  font-weight: 800;
}

.agent-message.user .agent-bubble {
  max-width: 72%;
  border-color: #2563eb;
  color: #fff;
  background: #2563eb;
}

.agent-bubble.muted {
  color: var(--text-secondary);
}

.agent-quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  border-top: 1px solid var(--border-color);
  padding: 12px 14px 0;
  background: var(--app-surface);
}

.agent-input-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  padding: 12px 14px 16px;
  background: var(--app-surface);
}

.agent-input-row .el-button {
  align-self: end;
}

.import-dialog :deep(.el-upload),
.import-dialog :deep(.el-upload-dragger) {
  width: 100%;
}

.upload-icon {
  margin-bottom: 12px;
  color: var(--primary);
  font-size: 46px;
}

.upload-title {
  color: var(--text-heading);
  font-size: 16px;
  font-weight: 800;
}

.upload-hint {
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 13px;
}

.upload-hint.demo_life-rule-hint {
  color: light-dark(#b45309, #fbbf24);
  font-size: 12px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.simulator-grid {
  display: grid;
  grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
  gap: 18px;
}

.simulator-form {
  padding: 8px 0;
}

.simulator-form :deep(.el-input-number) {
  width: 100%;
}

.simulation-result {
  min-height: 300px;
  padding: 22px;
}

.result-status {
  display: inline-flex;
  align-items: center;
  height: 32px;
  padding: 0 12px;
  border-radius: 8px;
  color: light-dark(#b91c1c, #fca5a5);
  background: light-dark(#fee2e2, rgba(248, 113, 113, .12));
  font-weight: 800;
}

.result-status.safe {
  color: light-dark(#047857, #6ee7b7);
  background: light-dark(#d1fae5, var(--primary-surface-2));
}

.simulation-result dl {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin: 18px 0 0;
}

.simulation-result dt {
  margin-bottom: 6px;
  color: var(--text-secondary);
  font-size: 13px;
}

.simulation-result dd {
  margin: 0;
  color: var(--text-heading);
  font-size: 22px;
  font-weight: 800;
}

.warning-text {
  margin: 18px 0 0;
  color: light-dark(#b45309, #fbbf24);
  line-height: 1.7;
}

.empty-result {
  color: var(--text-secondary);
  line-height: 1.8;
}

@media (max-width: 1100px) {
  .header-leading {
    flex-basis: 100%;
  }

  .header-snapshot {
    flex-basis: 210px;
  }

  .header-actions {
    flex: 1 1 430px;
  }

  .sku-overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .business-trend-card {
    grid-column: 1 / -1;
  }

  .sku-search-panel,
  .policy-form-grid,
  .sync-setting-row,
  .trend-factor-setting-row,
  .sku-decision-columns {
    grid-template-columns: 1fr;
  }

  .sync-setting-controls,
  .trend-factor-controls {
    align-items: stretch;
    flex-direction: column;
  }

  .business-observation-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .business-observation-meta {
    justify-content: flex-start;
  }

  .sync-interval-field {
    grid-template-columns: auto minmax(118px, 1fr) auto;
  }

  .agent-header {
    grid-template-columns: 1fr;
    row-gap: 10px;
  }

  .agent-reason-strip {
    width: min(100%, 980px);
  }

  .agent-shell {
    grid-template-columns: 1fr;
    overflow-y: auto;
  }

  .agent-data-panel,
  .agent-chat-panel {
    min-height: 520px;
  }

  .simulator-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .inventory-page {
    padding: 18px;
  }

  .page-header,
  .toolbar,
  .pagination-bar {
    align-items: stretch;
    flex-direction: column;
  }

  .header-title-block,
  .header-snapshot,
  .header-actions {
    box-sizing: border-box;
    width: 100%;
    min-width: 0;
  }

  .header-heading-row {
    align-items: stretch;
    flex-direction: column;
  }

  .sku-overview-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .business-trend-card {
    grid-column: auto;
  }

  .toolbar-left,
  .toolbar-right,
  .header-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .toolbar-left :deep(.el-select),
  .toolbar-left :deep(.el-input),
  .toolbar-left :deep(.el-button),
  .toolbar-right :deep(.el-button),
  .header-actions :deep(.el-button) {
    width: 100%;
  }

  .agent-drawer {
    width: 100% !important;
  }

  .agent-shell {
    padding: 12px;
  }

  .agent-summary-grid {
    grid-template-columns: 1fr;
  }

  .agent-compare-row {
    grid-template-columns: minmax(120px, 1fr) repeat(2, minmax(76px, auto));
  }

  .agent-input-row {
    grid-template-columns: 1fr;
  }
}
</style>
