<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  ElButton,
  ElIcon,
  ElMessage,
  ElOption,
  ElSelect,
  ElTable,
  ElTableColumn,
  ElTag,
} from 'element-plus'
import { DataAnalysis, Refresh, Search, TrendCharts, Upload } from '@element-plus/icons-vue'
import * as XLSX from 'xlsx'
import request from '../utils/request'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, ScatterChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components'

use([
  CanvasRenderer,
  BarChart,
  ScatterChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  VisualMapComponent,
])

interface ServiceRow {
  store: string
  agentName: string
  account: string
  agentRole: string
  reportWeekKey: string
  reportWeekLabel: string
  visitors: number
  questions: number
  consults: number
  robotMsgs: number
  humanMsgs: number
  qaRatio: number
  robotQaRatio: number
  humanQaRatio: number
  humanRespSec: number
  accountRespSec: number
  speedImprove: number
}

interface SummaryRow {
  key: string
  store?: string
  agentName?: string
  rowCount: number
  storeCount: number
  agentCount: number
  accountCount: number
  visitors: number
  questions: number
  consults: number
  robotMsgs: number
  humanMsgs: number
  robotShare: number
  qaRatio: number
  robotQaRatio: number
  humanQaRatio: number
  humanRespSec: number
  accountRespSec: number
  speedImprove: number
  questionsPerVisitor: number
}

interface WeekComparison {
  hasPrevious: boolean
  currentKey: string
  currentLabel: string
  previousKey: string
  previousLabel: string
  questions: number
  previousQuestions: number
  questionsDelta: number | null
  visitors: number
  previousVisitors: number
  visitorsDelta: number | null
  consults: number
  previousConsults: number
  consultsDelta: number | null
  robotShare: number
  previousRobotShare: number
  robotShareDelta: number | null
  speedImprove: number
  previousSpeedImprove: number
  speedImproveDelta: number | null
  humanRespSec: number
  previousHumanRespSec: number
  storeCount: number
  previousStoreCount: number
  storeCountDelta: number | null
  needAttention: number
  previousNeedAttention: number
  needAttentionDelta: number | null
}

type WorkbookField = Exclude<keyof ServiceRow, 'agentRole' | 'reportWeekKey' | 'reportWeekLabel'>

const DEFAULT_REPORT_URL = '/static/demo-fixtures/customer-service-demo.xlsx'
const DEFAULT_REPORT_NAME = '测试客服报表.xlsx'
const STORAGE_ROWS_KEY = 'cs-full-demo-dashboard-rows-v1'
const STORAGE_META_KEY = 'cs-full-demo-dashboard-meta-v1'
const SHARED_API = '/cs/dashboard'

const rows = ref<ServiceRow[]>([])
const sourceName = ref(DEFAULT_REPORT_NAME)
const loading = ref(false)
const loaded = ref(false)
const folderInput = ref<HTMLInputElement | null>(null)
const selectedStores = ref<string[]>([])
const selectedAgents = ref<string[]>([])
const selectedRoles = ref<string[]>([])
const selectedWeeks = ref<string[]>([])
const minQuestions = ref(100)

// 测试数据对应的客服账号映射；保留原报表解析与角色识别流程。
const ACCOUNT_NAME_MAP: Record<string, string> = {}
const addAccountMapping = (name: string, accounts: string[]) => {
  accounts.forEach((account) => { ACCOUNT_NAME_MAP[account] = name })
}
addAccountMapping('测试客服01', ['test-agent-01-shop-01', 'test-agent-01-shop-02', 'test-agent-01-shop-03', 'test-agent-01-shop-04', 'test-agent-01-shop-05', 'test-agent-01-shop-06'])
addAccountMapping('测试客服02', ['test-agent-02-shop-01', 'test-agent-02-shop-02', 'test-agent-02-shop-03', 'test-agent-02-shop-04', 'test-agent-02-shop-05', 'test-agent-02-shop-06'])
addAccountMapping('测试客服03', ['test-agent-03-shop-01', 'test-agent-03-shop-02', 'test-agent-03-shop-03', 'test-agent-03-shop-04', 'test-agent-03-shop-05', 'test-agent-03-shop-06'])
addAccountMapping('测试客服04', ['test-agent-04-shop-01', 'test-agent-04-shop-02', 'test-agent-04-shop-03', 'test-agent-04-shop-04', 'test-agent-04-shop-05', 'test-agent-04-shop-06'])
addAccountMapping('测试客服05', ['test-agent-05-shop-01', 'test-agent-05-shop-02', 'test-agent-05-shop-03', 'test-agent-05-shop-04', 'test-agent-05-shop-05', 'test-agent-05-shop-06'])

const columnMap: Record<WorkbookField, string[]> = {
  store: ['店铺'],
  agentName: ['客服名字'],
  account: ['客服'],
  visitors: ['接待人数'],
  questions: ['接待问题数'],
  consults: ['咨询人数'],
  robotMsgs: ['机器人发出消息数'],
  humanMsgs: ['人工发出消息数'],
  qaRatio: ['答问比'],
  robotQaRatio: ['机器人答问比'],
  humanQaRatio: ['人工答问比'],
  humanRespSec: ['人工平均响应时长（秒）'],
  accountRespSec: ['账号平均响应时长（秒）'],
  speedImprove: ['响应速度提升'],
}

const toNumber = (value: unknown) => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0
  if (typeof value === 'string') {
    const parsed = Number(value.replace(/,/g, '').replace('%', '').trim())
    return Number.isFinite(parsed) ? parsed : 0
  }
  return 0
}

const toPercentNumber = (value: unknown) => {
  if (typeof value === 'number') return value > 1 ? value / 100 : value
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (!trimmed) return 0
    const parsed = Number(trimmed.replace('%', '').replace(/,/g, ''))
    if (!Number.isFinite(parsed)) return 0
    return trimmed.includes('%') || parsed > 1 ? parsed / 100 : parsed
  }
  return 0
}

const normalizeHeader = (value: unknown) => String(value ?? '').trim()

const SALES_PRE_NAMES = new Set(['测试客服01', '测试客服02'])
const SALES_AFTER_NAMES = new Set(['测试客服03', '测试客服04', '测试客服05'])
const resolveAgentRole = (name: string) => {
  if (SALES_PRE_NAMES.has(name)) return '售前'
  if (SALES_AFTER_NAMES.has(name)) return '售后'
  return '未分类'
}

interface ReportWeek {
  key: string
  label: string
}

const pad2 = (value: number) => String(value).padStart(2, '0')
const formatDate = (date: Date) =>
  `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`

const parseReportWeek = (filename: string): ReportWeek => {
  const cleanName = filename.replace(/\.(xlsx|xls)$/i, '')
  const explicitRange = cleanName.match(/(\d{4})年(\d{1,2})月(\d{1,2})日\s*~\s*(\d{4})年(\d{1,2})月(\d{1,2})日/)
  if (explicitRange) {
    const [, sy, sm, sd, ey, em, ed] = explicitRange
    const start = `${sy}-${pad2(Number(sm))}-${pad2(Number(sd))}`
    const end = `${ey}-${pad2(Number(em))}-${pad2(Number(ed))}`
    return { key: `${start}_${end}`, label: `${start} ~ ${end}` }
  }

  const shortRange = cleanName.match(/(\d{4})年(\d{1,2})月(\d{1,2})日\s*~\s*(\d{1,2})月(\d{1,2})日/)
  if (shortRange) {
    const [, sy, sm, sd, em, ed] = shortRange
    const start = `${sy}-${pad2(Number(sm))}-${pad2(Number(sd))}`
    const end = `${sy}-${pad2(Number(em))}-${pad2(Number(ed))}`
    return { key: `${start}_${end}`, label: `${start} ~ ${end}` }
  }

  const compactDate = cleanName.match(/(\d{4})(\d{2})(\d{2})$/)
  if (compactDate) {
    const [, year, month, day] = compactDate
    const anchor = new Date(Number(year), Number(month) - 1, Number(day))
    const start = new Date(anchor)
    start.setDate(anchor.getDate() - 7)
    const end = new Date(anchor)
    end.setDate(anchor.getDate() - 1)
    const startLabel = formatDate(start)
    const endLabel = formatDate(end)
    return { key: `${startLabel}_${endLabel}`, label: `${startLabel} ~ ${endLabel}` }
  }

  return { key: cleanName, label: cleanName }
}

const hasExplicitReportWeek = (filename: string) => {
  const cleanName = filename.replace(/\.(xlsx|xls)$/i, '')
  return /\d{4}年\d{1,2}月\d{1,2}日\s*~\s*(?:\d{4}年)?\d{1,2}月\d{1,2}日/.test(cleanName)
}

const getPreviousCompleteWeek = (): ReportWeek => {
  const thisMonday = new Date()
  thisMonday.setHours(0, 0, 0, 0)
  const weekday = thisMonday.getDay() || 7
  thisMonday.setDate(thisMonday.getDate() - weekday + 1)

  const start = new Date(thisMonday)
  start.setDate(start.getDate() - 7)
  const end = new Date(thisMonday)
  end.setDate(end.getDate() - 1)
  const startLabel = formatDate(start)
  const endLabel = formatDate(end)
  return { key: `${startLabel}_${endLabel}`, label: `${startLabel} ~ ${endLabel}` }
}

const inferFolderReportWeek = (files: File[]) => {
  const namedReport = files.find((file) => hasExplicitReportWeek(file.name))
  return namedReport ? parseReportWeek(namedReport.name) : getPreviousCompleteWeek()
}

const fileStem = (filename: string) => filename.replace(/\.(xlsx|xls)$/i, '')

type DirectoryEntry = {
  kind: 'file' | 'directory'
  name: string
  getFile?: () => Promise<File>
  values?: () => AsyncIterableIterator<DirectoryEntry>
}

type DirectoryHandle = DirectoryEntry & {
  kind: 'directory'
  values: () => AsyncIterableIterator<DirectoryEntry>
}

type DirectoryPickerWindow = Window & {
  showDirectoryPicker?: (options?: { mode: 'read' }) => Promise<DirectoryHandle>
}

type BrowserFile = File & {
  webkitRelativePath?: string
}

const buildHeaderIndex = (headers: unknown[]) => {
  const normalized = headers.map(normalizeHeader)
  const result: Partial<Record<WorkbookField, number>> = {}

  Object.entries(columnMap).forEach(([field, labels]) => {
    const index = normalized.findIndex((header) => labels.includes(header))
    if (index >= 0) result[field as WorkbookField] = index
  })

  return result
}

interface ParseWorkbookOptions {
  reportWeek?: ReportWeek
  storeName?: string
}

const parseWorkbook = (
  arrayBuffer: ArrayBuffer,
  filename: string,
  options: ParseWorkbookOptions = {},
): ServiceRow[] => {
  const reportWeek = options.reportWeek ?? parseReportWeek(filename)
  const workbook = XLSX.read(arrayBuffer, { type: 'array' })
  const firstSheet = workbook.Sheets[workbook.SheetNames[0]]
  const raw = XLSX.utils.sheet_to_json<unknown[]>(firstSheet, { header: 1, defval: '' })
  const headerRowIndex = raw.findIndex((line) => line.some((cell) => normalizeHeader(cell)))
  if (headerRowIndex < 0) return []

  const headerIndex = buildHeaderIndex(raw[headerRowIndex])
  if (headerIndex.account === undefined) {
    throw new Error('报表缺少客服列')
  }

  const isMergedReport = headerIndex.store !== undefined && headerIndex.agentName !== undefined
  if (!isMergedReport && !options.storeName) {
    throw new Error('原始报表缺少店铺信息')
  }

  return raw.slice(headerRowIndex + 1).reduce<ServiceRow[]>((acc, line) => {
    const get = (field: WorkbookField) => line[headerIndex[field] ?? -1]
    const account = normalizeHeader(get('account'))
    const store = isMergedReport ? normalizeHeader(get('store')) : normalizeHeader(options.storeName)
    const agentName = isMergedReport
      ? normalizeHeader(get('agentName'))
      : ACCOUNT_NAME_MAP[account] || '未知'
    if (!store && !agentName && !account) return acc

    acc.push({
      store,
      agentName,
      account,
      agentRole: resolveAgentRole(agentName),
      reportWeekKey: reportWeek.key,
      reportWeekLabel: reportWeek.label,
      visitors: toNumber(get('visitors')),
      questions: toNumber(get('questions')),
      consults: toNumber(get('consults')),
      robotMsgs: toNumber(get('robotMsgs')),
      humanMsgs: toNumber(get('humanMsgs')),
      qaRatio: toNumber(get('qaRatio')),
      robotQaRatio: toNumber(get('robotQaRatio')),
      humanQaRatio: toNumber(get('humanQaRatio')),
      humanRespSec: toNumber(get('humanRespSec')),
      accountRespSec: toNumber(get('accountRespSec')),
      speedImprove: toPercentNumber(get('speedImprove')),
    })
    return acc
  }, [])
}

const workbookHasMergedColumns = (arrayBuffer: ArrayBuffer) => {
  try {
    const workbook = XLSX.read(arrayBuffer, { type: 'array' })
    const firstSheet = workbook.Sheets[workbook.SheetNames[0]]
    const raw = XLSX.utils.sheet_to_json<unknown[]>(firstSheet, { header: 1, defval: '' })
    const headerRowIndex = raw.findIndex((line) => line.some((cell) => normalizeHeader(cell)))
    if (headerRowIndex < 0) return false
    const headers = raw[headerRowIndex].map(normalizeHeader)
    return headers.includes('店铺') && headers.includes('客服名字')
  } catch {
    return false
  }
}

const applyParsedRows = (parsed: ServiceRow[], nextSourceName: string) => {
  const reportWeekKey = parsed[0].reportWeekKey
  rows.value = [...rows.value.filter((row) => row.reportWeekKey !== reportWeekKey), ...parsed]
  sourceName.value = nextSourceName
  loaded.value = true
  selectedStores.value = []
  selectedAgents.value = []
  selectedRoles.value = []
  const loadedWeekKeys = Array.from(new Set(rows.value.map((row) => row.reportWeekKey))).sort()
  selectedWeeks.value = [loadedWeekKeys[loadedWeekKeys.length - 1] ?? reportWeekKey]
  persistRows()
}

const loadArrayBuffer = async (
  arrayBuffer: ArrayBuffer,
  filename: string,
  options: ParseWorkbookOptions = {},
) => {
  const parsed = parseWorkbook(arrayBuffer, filename, options)
  if (!parsed.length) {
    ElMessage.warning('没有识别到可用数据')
    return
  }
  applyParsedRows(parsed, filename)
}

const collectDirectoryFiles = async (directory: DirectoryHandle) => {
  const files: File[] = []

  const walk = async (current: DirectoryHandle) => {
    for await (const entry of current.values()) {
      if (entry.kind === 'file' && entry.getFile && /\.(xlsx|xls)$/i.test(entry.name)) {
        files.push(await entry.getFile())
      } else if (entry.kind === 'directory' && entry.values) {
        await walk(entry as DirectoryHandle)
      }
    }
  }

  await walk(directory)
  return files
}

const importFolderFiles = async (files: File[], folderName: string) => {
  if (!files.length) {
    ElMessage.warning('所选文件夹中没有 Excel 报表')
    return
  }

  loading.value = true
  try {
    const reportWeek = inferFolderReportWeek(files)
    const parsedRows: ServiceRow[] = []
    const aggregateCandidates: Array<{ file: File; buffer: ArrayBuffer }> = []
    const skipped: string[] = []
    const stores = new Set<string>()

    for (const file of files) {
      const buffer = await file.arrayBuffer()
      if (workbookHasMergedColumns(buffer)) {
        // 文件夹中可能留有上次脚本生成的周报，不能再次作为原始报表参与合并。
        aggregateCandidates.push({ file, buffer })
        continue
      }

      try {
        const parsed = parseWorkbook(buffer, file.name, {
          reportWeek,
          storeName: fileStem(file.name),
        })
        if (parsed.length) {
          parsedRows.push(...parsed)
          stores.add(fileStem(file.name))
        } else {
          skipped.push(`${file.name}（无数据）`)
        }
      } catch (error) {
        skipped.push(`${file.name}（${(error as Error).message || '格式无法识别'}）`)
      }
    }

    // 兼容用户只选择了整合报表的文件夹：若没有原始店铺报表，则直接使用整合报表。
    if (!parsedRows.length && aggregateCandidates.length) {
      const fallback = aggregateCandidates[0]
      parsedRows.push(...parseWorkbook(fallback.buffer, fallback.file.name, { reportWeek }))
      stores.add('整合报表')
    }

    if (!parsedRows.length) {
      throw new Error('没有识别到可导入的客服报表，请确认文件夹内是脚本生成前的店铺原始报表')
    }

    applyParsedRows(parsedRows, `${folderName} · ${reportWeek.label}`)
    const skippedText = skipped.length ? `，跳过 ${skipped.length} 个文件` : ''
    ElMessage.success(`文件夹导入完成：${stores.size} 个店铺，${parsedRows.length} 行${skippedText}`)
  } catch (error) {
    ElMessage.error((error as Error).message || '文件夹解析失败')
  } finally {
    loading.value = false
  }
}

const openFolderPicker = async () => {
  const pickerWindow = window as DirectoryPickerWindow
  if (!pickerWindow.showDirectoryPicker) {
    // showDirectoryPicker() 仅在部分浏览器和安全上下文中可用（例如 HTTP
    // 内网地址、内嵌页面中通常不可用）。原生 input 的 webkitdirectory
    // 覆盖面更广，也能在不支持目录 API 的环境中退化为多选 Excel 文件。
    folderInput.value?.click()
    return
  }

  try {
    const directory = await pickerWindow.showDirectoryPicker({ mode: 'read' })
    const files = await collectDirectoryFiles(directory)
    await importFolderFiles(files, directory.name || '客服数据文件夹')
  } catch (error) {
    if ((error as DOMException).name === 'AbortError') return
    const errorName = (error as DOMException).name
    if (errorName === 'NotSupportedError' || errorName === 'SecurityError') {
      folderInput.value?.click()
      return
    }
    ElMessage.error((error as Error).message || '文件夹读取失败')
  }
}

const handleFolderInputChange = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? []).filter((file) => /\.(xlsx|xls)$/i.test(file.name))

  // 清空 input，确保用户再次选择同一个文件夹时仍会触发 change。
  input.value = ''
  if (!files.length) return

  const relativePath = (files[0] as BrowserFile).webkitRelativePath || ''
  const folderName = relativePath.split('/')[0] || '客服数据文件夹'
  await importFolderFiles(files, folderName)
}

const loadShared = async (): Promise<boolean> => {
  try {
    const data = await request.get(SHARED_API, { silent: true } as any) as {
      rows?: ServiceRow[]
      sourceName?: string
      loaded?: boolean
    }
    const sharedRows = data?.rows
    if (!Array.isArray(sharedRows) || !sharedRows.length) return false
    rows.value = sharedRows
    sourceName.value = data.sourceName || sourceName.value
    loaded.value = true
    const loadedWeekKeys = Array.from(new Set(rows.value.map((row) => row.reportWeekKey))).sort()
    selectedWeeks.value = [loadedWeekKeys[loadedWeekKeys.length - 1] ?? '']
    try {
      localStorage.setItem(STORAGE_ROWS_KEY, JSON.stringify(rows.value))
      localStorage.setItem(STORAGE_META_KEY, JSON.stringify({
        sourceName: sourceName.value,
        loaded: true,
      }))
    } catch {
      // 本地缓存失败不影响共享数据使用
    }
    return true
  } catch (error) {
    console.warn('客服看板共享数据读取失败', error)
    return false
  }
}

const pushShared = async () => {
  try {
    await request.put(SHARED_API, {
      rows: rows.value,
      sourceName: sourceName.value,
      loaded: loaded.value,
    }, { silent: true } as any)
  } catch (error) {
    console.warn('客服看板共享数据保存失败', error)
  }
}

const persistRows = () => {
  try {
    localStorage.setItem(STORAGE_ROWS_KEY, JSON.stringify(rows.value))
    localStorage.setItem(STORAGE_META_KEY, JSON.stringify({
      sourceName: sourceName.value,
      loaded: loaded.value,
    }))
  } catch (error) {
    console.warn('客服看板数据缓存保存失败', error)
  }
  void pushShared()
}

const restoreRows = () => {
  try {
    const raw = localStorage.getItem(STORAGE_ROWS_KEY)
    if (!raw) return false
    const parsed = JSON.parse(raw) as ServiceRow[]
    if (!Array.isArray(parsed) || !parsed.length || typeof parsed[0]?.reportWeekKey !== 'string') {
      return false
    }
    const meta = JSON.parse(localStorage.getItem(STORAGE_META_KEY) || '{}') as {
      sourceName?: string
      loaded?: boolean
    }
    rows.value = parsed
    sourceName.value = meta.sourceName || sourceName.value
    loaded.value = true
    const loadedWeekKeys = Array.from(new Set(rows.value.map((row) => row.reportWeekKey))).sort()
    selectedWeeks.value = [loadedWeekKeys[loadedWeekKeys.length - 1] ?? '']
    return true
  } catch (error) {
    console.warn('客服看板数据缓存恢复失败', error)
    return false
  }
}

const loadDefaultReport = async () => {
  loading.value = true
  try {
    rows.value = []
    const response = await fetch(DEFAULT_REPORT_URL, { cache: 'no-store' })
    if (!response.ok) throw new Error('默认报表读取失败')
    await loadArrayBuffer(await response.arrayBuffer(), DEFAULT_REPORT_NAME)
  } catch (error) {
    rows.value = []
    loaded.value = true
    ElMessage.error((error as Error).message || '默认报表读取失败')
  } finally {
    loading.value = false
  }
}

const matchesDimensionFilters = (row: ServiceRow) => {
  if (selectedStores.value.length && !selectedStores.value.includes(row.store)) return false
  if (selectedAgents.value.length && !selectedAgents.value.includes(row.agentName)) return false
  if (selectedRoles.value.length && !selectedRoles.value.includes(row.agentRole)) return false
  return true
}

const filteredRows = computed(() =>
  rows.value.filter((row) => {
    if (!matchesDimensionFilters(row)) return false
    if (selectedWeeks.value.length && !selectedWeeks.value.includes(row.reportWeekKey)) return false
    return true
  }),
)

const dimensionFilteredRows = computed(() => rows.value.filter(matchesDimensionFilters))

const uniqueSorted = (items: string[]) =>
  Array.from(new Set(items.filter(Boolean))).sort((a, b) => a.localeCompare(b, 'zh-CN'))

const storeOptions = computed(() => uniqueSorted(rows.value.map((row) => row.store)))
const agentOptions = computed(() => uniqueSorted(rows.value.map((row) => row.agentName)))
const roleOptions = computed(() => uniqueSorted(rows.value.map((row) => row.agentRole)))
const weekOptions = computed(() =>
  Array.from(
    new Map(rows.value.map((row) => [row.reportWeekKey, row.reportWeekLabel])).entries(),
  ).map(([key, label]) => ({ key, label })),
)

const weightedAverage = (items: ServiceRow[], field: 'humanRespSec' | 'accountRespSec') => {
  const totalWeight = items.reduce((sum, row) => sum + Math.max(row.questions, 0), 0)
  if (!totalWeight) return 0
  return items.reduce((sum, row) => sum + row[field] * Math.max(row.questions, 0), 0) / totalWeight
}

const weightedMetricAverage = (items: ServiceRow[], field: 'qaRatio' | 'robotQaRatio' | 'humanQaRatio') => {
  const totalWeight = items.reduce((sum, row) => sum + Math.max(row.questions, 0), 0)
  if (!totalWeight) return 0
  return items.reduce((sum, row) => sum + row[field] * Math.max(row.questions, 0), 0) / totalWeight
}

const aggregate = (
  items: ServiceRow[],
  getKey: (row: ServiceRow) => string,
  enrich: (groupRows: ServiceRow[], key: string) => Partial<SummaryRow> = () => ({}),
) => {
  const groups = new Map<string, ServiceRow[]>()
  items.forEach((row) => {
    const key = getKey(row)
    const groupRows = groups.get(key) ?? []
    groupRows.push(row)
    groups.set(key, groupRows)
  })

  return Array.from(groups.entries()).map(([key, groupRows]) => {
    const robotMsgs = groupRows.reduce((sum, row) => sum + row.robotMsgs, 0)
    const humanMsgs = groupRows.reduce((sum, row) => sum + row.humanMsgs, 0)
    const questions = groupRows.reduce((sum, row) => sum + row.questions, 0)
    const visitors = groupRows.reduce((sum, row) => sum + row.visitors, 0)
    const humanRespSec = weightedAverage(groupRows, 'humanRespSec')
    const accountRespSec = weightedAverage(groupRows, 'accountRespSec')

    return {
      key,
      rowCount: groupRows.length,
      storeCount: new Set(groupRows.map((row) => row.store)).size,
      agentCount: new Set(groupRows.map((row) => row.agentName)).size,
      accountCount: new Set(groupRows.map((row) => row.account)).size,
      visitors,
      questions,
      consults: groupRows.reduce((sum, row) => sum + row.consults, 0),
      robotMsgs,
      humanMsgs,
      robotShare: robotMsgs + humanMsgs > 0 ? robotMsgs / (robotMsgs + humanMsgs) : 0,
      qaRatio: weightedMetricAverage(groupRows, 'qaRatio'),
      robotQaRatio: weightedMetricAverage(groupRows, 'robotQaRatio'),
      humanQaRatio: weightedMetricAverage(groupRows, 'humanQaRatio'),
      humanRespSec,
      accountRespSec,
      speedImprove: humanRespSec > 0 ? 1 - accountRespSec / humanRespSec : 0,
      questionsPerVisitor: visitors > 0 ? questions / visitors : 0,
      ...enrich(groupRows, key),
    } satisfies SummaryRow
  })
}

const overall = computed(() => aggregate(filteredRows.value, () => '全部')[0])
const storeSummary = computed(() =>
  aggregate(filteredRows.value, (row) => row.store, (_items, key) => ({ store: key }))
    .sort((a, b) => b.questions - a.questions),
)
const agentSummary = computed(() =>
  aggregate(filteredRows.value, (row) => row.agentName, (_items, key) => ({ agentName: key }))
    .sort((a, b) => b.questions - a.questions),
)
const storeAgentSummary = computed(() =>
  aggregate(
    filteredRows.value,
    (row) => `${row.store}__${row.agentName}`,
    (items) => ({ store: items[0]?.store, agentName: items[0]?.agentName }),
  ).sort((a, b) => b.questions - a.questions),
)

const sortedLoadedWeeks = computed(() =>
  Array.from(new Set(rows.value.map((row) => row.reportWeekKey))).sort(),
)

const comparisonWeeks = computed(() => {
  const loaded = sortedLoadedWeeks.value
  const selected = selectedWeeks.value.length
    ? [...selectedWeeks.value].sort()
    : [...loaded]
  const currentKey = selected[selected.length - 1] ?? ''
  const previousKey = loaded.filter((key) => key < currentKey).pop() ?? ''
  const labels = new Map(rows.value.map((row) => [row.reportWeekKey, row.reportWeekLabel]))
  return {
    currentKey,
    previousKey,
    currentLabel: labels.get(currentKey) ?? currentKey,
    previousLabel: labels.get(previousKey) ?? previousKey,
  }
})

const currentRows = computed(() =>
  filteredRows.value.filter((row) => row.reportWeekKey === comparisonWeeks.value.currentKey),
)

const previousRows = computed(() =>
  dimensionFilteredRows.value.filter((row) => row.reportWeekKey === comparisonWeeks.value.previousKey),
)

const previousStoreSummary = computed(() =>
  new Map(
    aggregate(previousRows.value, (row) => row.store, (_items, key) => ({ store: key }))
      .map((row) => [row.store ?? row.key, row]),
  ),
)

const previousAgentSummary = computed(() =>
  new Map(
    aggregate(previousRows.value, (row) => row.agentName, (_items, key) => ({ agentName: key }))
      .map((row) => [row.agentName ?? row.key, row]),
  ),
)

const attentionCount = (items: ServiceRow[]) =>
  aggregate(items, (row) => `${row.store}__${row.agentName}`)
    .filter((row) => row.questions >= minQuestions.value).length

const weekCompare = computed<WeekComparison | undefined>(() => {
  const current = aggregate(currentRows.value, () => 'all')[0]
  if (!current || !comparisonWeeks.value.currentKey) return undefined
  const previous = previousRows.value.length
    ? aggregate(previousRows.value, () => 'all')[0]
    : undefined
  const pct = (currentValue: number, previousValue?: number) =>
    previousValue === undefined || previousValue <= 0
      ? null
      : (currentValue - previousValue) / previousValue
  const currentAttention = attentionCount(currentRows.value)
  const previousAttention = previous ? attentionCount(previousRows.value) : 0

  return {
    hasPrevious: Boolean(previous),
    currentKey: comparisonWeeks.value.currentKey,
    currentLabel: comparisonWeeks.value.currentLabel,
    previousKey: comparisonWeeks.value.previousKey,
    previousLabel: comparisonWeeks.value.previousLabel,
    questions: current.questions,
    previousQuestions: previous?.questions ?? 0,
    questionsDelta: pct(current.questions, previous?.questions),
    visitors: current.visitors,
    previousVisitors: previous?.visitors ?? 0,
    visitorsDelta: pct(current.visitors, previous?.visitors),
    consults: current.consults,
    previousConsults: previous?.consults ?? 0,
    consultsDelta: pct(current.consults, previous?.consults),
    robotShare: current.robotShare,
    previousRobotShare: previous?.robotShare ?? 0,
    robotShareDelta: pct(current.robotShare, previous?.robotShare),
    speedImprove: current.speedImprove,
    previousSpeedImprove: previous?.speedImprove ?? 0,
    speedImproveDelta: pct(current.speedImprove, previous?.speedImprove),
    humanRespSec: current.humanRespSec,
    previousHumanRespSec: previous?.humanRespSec ?? 0,
    storeCount: current.storeCount,
    previousStoreCount: previous?.storeCount ?? 0,
    storeCountDelta: pct(current.storeCount, previous?.storeCount),
    needAttention: currentAttention,
    previousNeedAttention: previousAttention,
    needAttentionDelta: previous ? pct(currentAttention, previousAttention) : null,
  }
})

const topStores = computed(() => storeSummary.value)
const topAgents = computed(() => agentSummary.value.slice(0, 8))
const comparisonStores = computed(() =>
  [...storeSummary.value].sort((a, b) => (b.robotMsgs + b.humanMsgs) - (a.robotMsgs + a.humanMsgs)),
)
const topComparisonStores = computed(() => comparisonStores.value)
const filteredPairsByVolume = computed(() =>
  storeAgentSummary.value.filter((row) => row.questions >= minQuestions.value),
)
const detailRows = computed(() => storeAgentSummary.value)
const storeChartHeight = computed(() => Math.max(360, topStores.value.length * 28 + 90))
const matrixChartHeight = computed(() => Math.max(420, matrixStores.value.length * 28 + 150))

const fmtInt = (value = 0) => value.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
const fmtDecimal = (value = 0, digits = 1) => value.toLocaleString('zh-CN', {
  minimumFractionDigits: digits,
  maximumFractionDigits: digits,
})
const fmtPercent = (value = 0, digits = 1) => `${(value * 100).toFixed(digits)}%`

const trendOf = (delta: number | null | undefined, higherIsBetter = true) => {
  if (delta === null || delta === undefined) return 'flat'
  const threshold = 0.005
  if (delta > threshold) return higherIsBetter ? 'up' : 'down'
  if (delta < -threshold) return higherIsBetter ? 'down' : 'up'
  return 'flat'
}

const trendText = (delta: number | null | undefined) => {
  if (delta === null || delta === undefined) return '暂无上周数据'
  const sign = delta > 0 ? '+' : ''
  return `${sign}${(delta * 100).toFixed(1)}%`
}

const statusType = (row: Partial<SummaryRow>) => {
  const questions = row.questions ?? 0
  const speedImprove = row.speedImprove ?? 0
  const robotShare = row.robotShare ?? 0
  if (questions >= minQuestions.value && speedImprove < 0.05) return 'danger'
  if (questions >= minQuestions.value && robotShare < 0.2) return 'warning'
  return 'success'
}

const statusLabel = (row: Partial<SummaryRow>) => {
  const questions = row.questions ?? 0
  const speedImprove = row.speedImprove ?? 0
  const robotShare = row.robotShare ?? 0
  if (questions >= minQuestions.value && speedImprove < 0.05) return '低提升'
  if (questions >= minQuestions.value && robotShare < 0.2) return '低协同'
  return '正常'
}

const chartText = '#64748b'
const chartGrid = 'rgba(148, 163, 184, 0.22)'
const compactStoreName = (store = '') => store.replace('京东自营旗舰店', '')

const storeBarOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'shadow' },
    formatter(params: any[]) {
      const index = params[0]?.dataIndex ?? 0
      const row = topStores.value[index]
      if (!row) return ''
      const lines = [
        `<b>${row.store}</b>`,
        `接待问题数：${fmtInt(row.questions)}`,
        `接待人数：${fmtInt(row.visitors)}`,
        `机器人消息占比：${fmtPercent(row.robotShare)}`,
        `响应提升：${fmtPercent(row.speedImprove)}`,
      ]
      const previous = previousStoreSummary.value.get(row.store ?? row.key)
      if (previous) lines.push(`上周接待问题数：${fmtInt(previous.questions)}`)
      return lines.join('<br/>')
    },
  },
  grid: { top: 10, right: 28, bottom: 24, left: 156 },
  xAxis: {
    type: 'value',
    axisLabel: { color: chartText },
    splitLine: { lineStyle: { color: chartGrid, type: 'dashed' } },
  },
  yAxis: {
    type: 'category',
    inverse: true,
    data: topStores.value.map((row) => (row.store ?? row.key).replace('京东自营旗舰店', '')),
    axisLabel: { color: chartText, width: 138, overflow: 'truncate' },
    axisTick: { show: false },
    axisLine: { show: false },
  },
  series: [{
    name: '接待问题数',
    type: 'bar',
    barMaxWidth: 18,
    data: topStores.value.map((row) => row.questions),
    itemStyle: {
      borderRadius: [0, 5, 5, 0],
      color: '#2563eb',
    },
  }],
}))

const agentBarOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'shadow' },
    formatter(params: any[]) {
      const index = params[0]?.dataIndex ?? 0
      const row = topAgents.value[index]
      if (!row) return ''
      const lines = [
        `<b>${row.agentName}</b>`,
        `覆盖店铺：${fmtInt(row.storeCount)}`,
        `接待问题数：${fmtInt(row.questions)}`,
        `机器人消息占比：${fmtPercent(row.robotShare)}`,
        `响应提升：${fmtPercent(row.speedImprove)}`,
      ]
      const previous = previousAgentSummary.value.get(row.agentName ?? row.key)
      if (previous) lines.push(`上周接待问题数：${fmtInt(previous.questions)}`)
      return lines.join('<br/>')
    },
  },
  grid: { top: 20, right: 28, bottom: 76, left: 54 },
  xAxis: {
    type: 'category',
    data: topAgents.value.map((row) => row.agentName),
    axisLabel: { color: chartText, rotate: 35, width: 62, overflow: 'truncate' },
    axisTick: { show: false },
    axisLine: { lineStyle: { color: chartGrid } },
  },
  yAxis: {
    type: 'value',
    axisLabel: { color: chartText },
    splitLine: { lineStyle: { color: chartGrid, type: 'dashed' } },
  },
  series: [{
    name: '接待问题数',
    type: 'bar',
    barMaxWidth: 38,
    data: topAgents.value.map((row) => row.questions),
    itemStyle: {
      borderRadius: [5, 5, 0, 0],
      color: '#0f766e',
    },
  }],
}))

const messageCompareOption = computed(() => ({
  backgroundColor: 'transparent',
  color: ['#22c55e', '#ff6b6b'],
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'shadow' },
    formatter(params: any[]) {
      const index = params[0]?.dataIndex ?? 0
      const row = topComparisonStores.value[index]
      if (!row) return ''
      return [
        `<b>${row.store}</b>`,
        `机器人发出：${fmtInt(row.robotMsgs)}`,
        `人工发出：${fmtInt(row.humanMsgs)}`,
        `机器人占比：${fmtPercent(row.robotShare)}`,
      ].join('<br/>')
    },
  },
  legend: {
    top: 10,
    left: 'center',
    itemWidth: 12,
    itemHeight: 12,
    textStyle: { color: chartText, fontWeight: 700 },
  },
  grid: { top: 52, right: 28, bottom: 116, left: 58 },
  xAxis: {
    type: 'category',
    data: topComparisonStores.value.map((row) => compactStoreName(row.store ?? row.key)),
    axisLabel: { color: chartText, rotate: 45, width: 128, overflow: 'truncate' },
    axisTick: { show: false },
    axisLine: { lineStyle: { color: chartGrid } },
  },
  yAxis: {
    type: 'value',
    axisLabel: { color: chartText },
    splitLine: { lineStyle: { color: chartGrid } },
  },
  series: [
    {
      name: '机器人发出',
      type: 'bar',
      barMaxWidth: 14,
      data: topComparisonStores.value.map((row) => row.robotMsgs),
      itemStyle: { borderRadius: [4, 4, 0, 0] },
    },
    {
      name: '人工发出',
      type: 'bar',
      barMaxWidth: 14,
      data: topComparisonStores.value.map((row) => row.humanMsgs),
      itemStyle: { borderRadius: [4, 4, 0, 0] },
    },
  ],
}))

const qaCompareOption = computed(() => ({
  backgroundColor: 'transparent',
  color: ['#ffb23f', '#2dd4bf', '#8b6eea'],
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'shadow' },
    formatter(params: any[]) {
      const index = params[0]?.dataIndex ?? 0
      const row = topComparisonStores.value[index]
      if (!row) return ''
      return [
        `<b>${row.store}</b>`,
        `答问比：${fmtDecimal(row.qaRatio, 2)}`,
        `机器人答问比：${fmtDecimal(row.robotQaRatio, 2)}`,
        `人工答问比：${fmtDecimal(row.humanQaRatio, 2)}`,
      ].join('<br/>')
    },
  },
  legend: {
    top: 10,
    left: 'center',
    itemWidth: 12,
    itemHeight: 12,
    textStyle: { color: chartText, fontWeight: 700 },
  },
  grid: { top: 52, right: 28, bottom: 116, left: 58 },
  xAxis: {
    type: 'category',
    data: topComparisonStores.value.map((row) => compactStoreName(row.store ?? row.key)),
    axisLabel: { color: chartText, rotate: 45, width: 128, overflow: 'truncate' },
    axisTick: { show: false },
    axisLine: { lineStyle: { color: chartGrid } },
  },
  yAxis: {
    type: 'value',
    axisLabel: { color: chartText },
    splitLine: { lineStyle: { color: chartGrid } },
  },
  series: [
    {
      name: '答问比',
      type: 'bar',
      barMaxWidth: 12,
      data: topComparisonStores.value.map((row) => row.qaRatio),
      itemStyle: { borderRadius: [4, 4, 0, 0] },
    },
    {
      name: '机器人答问比',
      type: 'bar',
      barMaxWidth: 12,
      data: topComparisonStores.value.map((row) => row.robotQaRatio),
      itemStyle: { borderRadius: [4, 4, 0, 0] },
    },
    {
      name: '人工答问比',
      type: 'bar',
      barMaxWidth: 12,
      data: topComparisonStores.value.map((row) => row.humanQaRatio),
      itemStyle: { borderRadius: [4, 4, 0, 0] },
    },
  ],
}))

const matrixStores = computed(() => storeSummary.value.map((row) => row.store ?? row.key))
const matrixAgents = computed(() => agentSummary.value.map((row) => row.agentName))
const matrixOption = computed(() => {
  const pairs = storeAgentSummary.value.filter((row) =>
    matrixStores.value.includes(row.store ?? '') && matrixAgents.value.includes(row.agentName ?? ''),
  )
  const maxQuestions = Math.max(...pairs.map((row) => row.questions), 1)

  return {
    backgroundColor: 'transparent',
    tooltip: {
      formatter(param: any) {
        const row = param.data?.[5] as SummaryRow | undefined
        if (!row) return ''
        return [
          `<b>${row.store}</b>`,
          `客服：${row.agentName}`,
          `接待问题数：${fmtInt(row.questions)}`,
          `机器人消息占比：${fmtPercent(row.robotShare)}`,
          `响应提升：${fmtPercent(row.speedImprove)}`,
        ].join('<br/>')
      },
    },
    grid: { top: 20, right: 26, bottom: 82, left: 150 },
    visualMap: {
      show: false,
      min: 0,
      max: 0.55,
      dimension: 2,
      inRange: { color: ['#ef4444', '#f59e0b', '#10b981'] },
    },
    xAxis: {
      type: 'category',
      data: matrixAgents.value,
      axisLabel: { color: chartText },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: chartGrid } },
    },
    yAxis: {
      type: 'category',
      data: matrixStores.value.map((store) => store.replace('京东自营旗舰店', '')),
      axisLabel: { color: chartText, width: 136, overflow: 'truncate' },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: chartGrid } },
    },
    series: [{
      name: '店铺 x 客服',
      type: 'scatter',
      data: pairs.map((row) => [
        matrixAgents.value.indexOf(row.agentName ?? ''),
        matrixStores.value.indexOf(row.store ?? ''),
        Math.max(row.speedImprove, 0),
        row.questions,
        row.robotShare,
        row,
      ]),
      symbolSize(data: any[]) {
        return 12 + Math.sqrt((data[3] / maxQuestions) * 900)
      },
      itemStyle: {
        borderColor: '#ffffff',
        borderWidth: 1,
        shadowBlur: 8,
        shadowColor: 'rgba(15, 23, 42, 0.18)',
      },
    }],
  }
})

onMounted(async () => {
  // 优先读取服务器共享数据（全公司同一份，任何人上传后全员可见）
  if (await loadShared()) return
  // 服务器还没有共享数据时，回退到本地缓存，并回填到服务器让全员可见
  if (restoreRows()) {
    void pushShared()
    return
  }
  // 本地也没有数据，加载内置默认报表（同时持久化到服务器共享）
  void loadDefaultReport()
})
</script>

<template>
  <section class="service-dashboard">
    <header class="service-header" data-testid="service-dashboard-header">
      <div class="header-title-wrap">
        <el-icon class="header-icon"><DataAnalysis /></el-icon>
        <div>
          <p class="eyebrow">客服中心</p>
          <h1>客服接待效率仪表盘</h1>
        </div>
      </div>
      <div class="header-actions">
        <el-tag effect="plain">{{ sourceName }}</el-tag>
        <el-tag type="info" effect="plain">{{ fmtInt(rows.length) }} 行</el-tag>
        <el-tag type="success" effect="plain">{{ weekOptions.length }} 周</el-tag>
        <el-button :icon="Upload" type="primary" :loading="loading" @click="openFolderPicker">导入报表</el-button>
        <input
          ref="folderInput"
          class="folder-input"
          type="file"
          accept=".xlsx,.xls"
          multiple
          webkitdirectory
          directory
          @change="handleFolderInputChange"
        />
        <el-button :icon="Refresh" plain @click="loadDefaultReport">恢复快照</el-button>
      </div>
    </header>

    <div class="filter-bar">
      <el-select
        v-model="selectedStores"
        class="filter-select"
        clearable
        filterable
        multiple
        collapse-tags
        collapse-tags-tooltip
        placeholder="店铺"
      >
        <el-option v-for="store in storeOptions" :key="store" :label="store" :value="store" />
      </el-select>
      <el-select
        v-model="selectedAgents"
        class="filter-select"
        clearable
        filterable
        multiple
        collapse-tags
        collapse-tags-tooltip
        placeholder="客服名字"
      >
        <el-option v-for="agent in agentOptions" :key="agent" :label="agent" :value="agent" />
      </el-select>
      <el-select
        v-model="selectedRoles"
        class="filter-select filter-select--role"
        clearable
        multiple
        collapse-tags
        collapse-tags-tooltip
        placeholder="售前/售后"
      >
        <el-option v-for="role in roleOptions" :key="role" :label="role" :value="role" />
      </el-select>
      <el-select
        v-model="selectedWeeks"
        class="filter-select filter-select--week"
        clearable
        multiple
        collapse-tags
        collapse-tags-tooltip
        placeholder="日期周期"
      >
        <el-option v-for="week in weekOptions" :key="week.key" :label="week.label" :value="week.key" />
      </el-select>
      <el-button :icon="Search" plain @click="selectedStores = []; selectedAgents = []; selectedRoles = []; selectedWeeks = []">清除筛选</el-button>
    </div>

    <section v-if="weekCompare" class="week-compare">
      <div class="week-compare-head">
        <div class="week-compare-title">
          <el-icon class="week-compare-icon"><TrendCharts /></el-icon>
          <div>
            <strong>对比上周</strong>
            <span>
              {{ weekCompare.previousLabel ? `${weekCompare.currentLabel} vs ${weekCompare.previousLabel}` : weekCompare.currentLabel }}
            </span>
          </div>
        </div>
        <el-tag v-if="weekCompare.hasPrevious" type="success" effect="plain">上周数据已载入</el-tag>
        <el-tag v-else type="info" effect="plain">导入上周报表后自动对比</el-tag>
      </div>
      <div class="week-compare-grid">
        <div class="week-compare-item">
          <span>接待问题数</span>
          <strong>{{ fmtInt(weekCompare.questions) }}</strong>
          <small>
            <span class="trend-dot" :class="`trend-dot--${trendOf(weekCompare.questionsDelta, false)}`">
              {{ weekCompare.hasPrevious ? trendText(weekCompare.questionsDelta) : '--' }}
            </span>
            <em>上周 {{ fmtInt(weekCompare.previousQuestions) }}</em>
          </small>
        </div>
        <div class="week-compare-item">
          <span>咨询人数</span>
          <strong>{{ fmtInt(weekCompare.consults) }}</strong>
          <small>
            <span class="trend-dot" :class="`trend-dot--${trendOf(weekCompare.consultsDelta)}`">
              {{ weekCompare.hasPrevious ? trendText(weekCompare.consultsDelta) : '--' }}
            </span>
            <em>上周 {{ fmtInt(weekCompare.previousConsults) }}</em>
          </small>
        </div>
        <div class="week-compare-item">
          <span>机器人满足占比</span>
          <strong>{{ fmtPercent(weekCompare.robotShare) }}</strong>
          <small>
            <span class="trend-dot" :class="`trend-dot--${trendOf(weekCompare.robotShareDelta)}`">
              {{ weekCompare.hasPrevious ? trendText(weekCompare.robotShareDelta) : '--' }}
            </span>
            <em>上周 {{ fmtPercent(weekCompare.previousRobotShare) }}</em>
          </small>
        </div>
        <div class="week-compare-item">
          <span>响应速度提升</span>
          <strong>{{ fmtPercent(weekCompare.speedImprove) }}</strong>
          <small>
            <span class="trend-dot" :class="`trend-dot--${trendOf(weekCompare.speedImproveDelta)}`">
              {{ weekCompare.hasPrevious ? trendText(weekCompare.speedImproveDelta) : '--' }}
            </span>
            <em>上周 {{ fmtPercent(weekCompare.previousSpeedImprove) }}</em>
          </small>
        </div>
        <div class="week-compare-item">
          <span>需关注组合</span>
          <strong>{{ fmtInt(weekCompare.needAttention) }}</strong>
          <small>
            <span class="trend-dot" :class="`trend-dot--${trendOf(weekCompare.needAttentionDelta, false)}`">
              {{ weekCompare.hasPrevious ? trendText(weekCompare.needAttentionDelta) : '--' }}
            </span>
            <em>上周 {{ fmtInt(weekCompare.previousNeedAttention) }}</em>
          </small>
        </div>
      </div>
    </section>

    <div v-if="overall" class="kpi-grid">
      <div class="kpi-card">
        <span>接待问题数</span>
        <strong>{{ fmtInt(overall.questions) }}</strong>
        <small>接待人数 {{ fmtInt(overall.visitors) }}</small>
        <span
          v-if="weekCompare"
          class="kpi-trend"
          :class="`kpi-trend--${trendOf(weekCompare.questionsDelta, false)}`"
        >
          {{ weekCompare.hasPrevious ? `较上周 ${trendText(weekCompare.questionsDelta)}` : '暂无上周数据' }}
        </span>
      </div>
      <div class="kpi-card">
        <span>咨询人数</span>
        <strong>{{ fmtInt(overall.consults) }}</strong>
        <small>人均问题 {{ fmtDecimal(overall.questionsPerVisitor, 2) }}</small>
        <span
          v-if="weekCompare"
          class="kpi-trend"
          :class="`kpi-trend--${trendOf(weekCompare.consultsDelta)}`"
        >
          {{ weekCompare.hasPrevious ? `较上周 ${trendText(weekCompare.consultsDelta)}` : '暂无上周数据' }}
        </span>
      </div>
      <div class="kpi-card">
        <span>机器人满足占比</span>
        <strong>{{ fmtPercent(overall.robotShare) }}</strong>
        <small>机器人 {{ fmtInt(overall.robotMsgs) }} / 人工 {{ fmtInt(overall.humanMsgs) }}</small>
        <span
          v-if="weekCompare"
          class="kpi-trend"
          :class="`kpi-trend--${trendOf(weekCompare.robotShareDelta)}`"
        >
          {{ weekCompare.hasPrevious ? `较上周 ${trendText(weekCompare.robotShareDelta)}` : '暂无上周数据' }}
        </span>
      </div>
      <div class="kpi-card">
        <span>响应速度提升</span>
        <strong>{{ fmtPercent(overall.speedImprove) }}</strong>
        <small>{{ fmtDecimal(overall.humanRespSec) }} 秒降至 {{ fmtDecimal(overall.accountRespSec) }} 秒</small>
        <span
          v-if="weekCompare"
          class="kpi-trend"
          :class="`kpi-trend--${trendOf(weekCompare.speedImproveDelta)}`"
        >
          {{ weekCompare.hasPrevious ? `较上周 ${trendText(weekCompare.speedImproveDelta)}` : '暂无上周数据' }}
        </span>
      </div>
      <div class="kpi-card">
        <span>店铺数</span>
        <strong>{{ fmtInt(overall.storeCount) }}</strong>
        <small>客服名字 {{ fmtInt(overall.agentCount) }}</small>
        <span
          v-if="weekCompare"
          class="kpi-trend"
          :class="`kpi-trend--${trendOf(weekCompare.storeCountDelta)}`"
        >
          {{ weekCompare.hasPrevious ? `上周 ${fmtInt(weekCompare.previousStoreCount)} 家` : '暂无上周数据' }}
        </span>
      </div>
      <div class="kpi-card kpi-card--amber">
        <span>需关注组合</span>
        <strong>{{ fmtInt(filteredPairsByVolume.length) }}</strong>
        <small>按当前阈值筛选</small>
        <span
          v-if="weekCompare"
          class="kpi-trend"
          :class="`kpi-trend--${trendOf(weekCompare.needAttentionDelta, false)}`"
        >
          {{ weekCompare.hasPrevious ? `较上周 ${trendText(weekCompare.needAttentionDelta)}` : '暂无上周数据' }}
        </span>
      </div>
    </div>

    <main v-if="overall" class="dashboard-grid">
      <section class="panel panel--full">
        <div class="panel-header">
          <h2>消息发送量对比</h2>
          <span>机器人 vs 人工 共 {{ comparisonStores.length }} 家店</span>
        </div>
        <v-chart class="chart chart--comparison" :option="messageCompareOption" autoresize />
      </section>

      <section class="panel panel--wide">
        <div class="panel-header">
          <h2>店铺接待压力排行</h2>
          <span>共 {{ topStores.length }} 家店</span>
        </div>
        <v-chart class="chart chart--bar" :style="{ height: `${storeChartHeight}px` }" :option="storeBarOption" autoresize />
      </section>

      <section class="panel">
        <div class="panel-header">
          <h2>客服工作量排行</h2>
          <span>{{ topAgents.length }} 人</span>
        </div>
        <v-chart class="chart chart--agent" :option="agentBarOption" autoresize />
      </section>

      <section class="panel panel--full">
        <div class="panel-header">
          <h2>答问比对比</h2>
          <span>答问比 / 机器人 / 人工 共 {{ comparisonStores.length }} 家店</span>
        </div>
        <v-chart class="chart chart--comparison" :option="qaCompareOption" autoresize />
      </section>

      <section class="panel panel--full">
        <div class="panel-header">
          <h2>店铺 x 客服矩阵</h2>
          <span>问题量 / 响应提升</span>
        </div>
        <v-chart class="chart chart--matrix" :style="{ height: `${matrixChartHeight}px` }" :option="matrixOption" autoresize />
      </section>

      <section class="panel panel--full">
        <div class="panel-header">
          <h2>店铺客服明细</h2>
          <span>{{ detailRows.length }} 条</span>
        </div>
        <el-table :data="detailRows" class="detail-table" stripe>
          <el-table-column prop="store" label="店铺" min-width="260" show-overflow-tooltip />
          <el-table-column prop="agentName" label="客服名字" width="110" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusType(row)" effect="plain" size="small">{{ statusLabel(row) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="接待人数" width="110" align="right">
            <template #default="{ row }">{{ fmtInt(row.visitors) }}</template>
          </el-table-column>
          <el-table-column label="接待问题数" width="120" align="right">
            <template #default="{ row }">{{ fmtInt(row.questions) }}</template>
          </el-table-column>
          <el-table-column label="机器人占比" width="120" align="right">
            <template #default="{ row }">{{ fmtPercent(row.robotShare) }}</template>
          </el-table-column>
          <el-table-column label="人工响应" width="110" align="right">
            <template #default="{ row }">{{ fmtDecimal(row.humanRespSec) }} 秒</template>
          </el-table-column>
          <el-table-column label="账号响应" width="110" align="right">
            <template #default="{ row }">{{ fmtDecimal(row.accountRespSec) }} 秒</template>
          </el-table-column>
          <el-table-column label="响应提升" width="110" align="right">
            <template #default="{ row }">{{ fmtPercent(row.speedImprove) }}</template>
          </el-table-column>
        </el-table>
      </section>
    </main>

    <div v-if="loaded && !overall && !loading" class="empty-state">
      当前筛选没有可展示数据
    </div>
  </section>
</template>

<style scoped>
.service-dashboard {
  min-height: 100%;
  padding: 20px;
  color: var(--text-primary);
  background: light-dark(#f8fafc, var(--app-bg));
  overflow-y: auto;
}

.service-header,
.header-title-wrap,
.header-actions,
.filter-bar,
.panel-header {
  display: flex;
  align-items: center;
}

.service-header {
  justify-content: space-between;
  gap: 18px;
  max-width: 1480px;
  margin: 0 auto 14px;
}

.header-title-wrap {
  gap: 14px;
  min-width: 0;
}

.header-icon {
  width: 44px;
  height: 44px;
  flex: 0 0 44px;
  justify-content: center;
  border-radius: 8px;
  color: #ffffff;
  background: #0f766e;
  font-size: 24px;
}

.eyebrow {
  margin: 0 0 6px;
  color: light-dark(#2563eb, #93c5fd);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0;
}

h1,
h2 {
  margin: 0;
  color: light-dark(#0f172a, var(--text-primary));
}

h1 {
  font-size: 28px;
  line-height: 1.15;
}

.header-actions {
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.folder-input {
  display: none;
}

.filter-bar {
  gap: 10px;
  max-width: 1480px;
  margin: 0 auto 14px;
  padding: 12px 14px;
  border: 1px solid light-dark(#dbe5ef, var(--border-color));
  border-radius: 8px;
  background: light-dark(#ffffff, var(--app-surface));
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.05);
}

.filter-bar :deep(.el-select) {
  width: 240px;
}

.filter-bar :deep(.filter-select--week) {
  width: 300px;
}

.week-compare {
  display: flex;
  align-items: stretch;
  gap: 18px;
  max-width: 1480px;
  margin: 0 auto 14px;
  padding: 14px 16px;
  border: 1px solid light-dark(#dbe5ef, var(--border-color));
  border-radius: 8px;
  background: light-dark(#ffffff, var(--app-surface));
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.05);
}

.week-compare-head {
  display: flex;
  flex: 0 0 230px;
  flex-direction: column;
  justify-content: space-between;
  gap: 10px;
  padding-right: 18px;
  border-right: 1px dashed light-dark(#dbe5ef, var(--border-color));
}

.week-compare-title {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.week-compare-icon {
  flex: 0 0 36px;
  justify-content: center;
  border-radius: 8px;
  color: light-dark(#2563eb, #93c5fd);
  background: light-dark(#eff6ff, rgba(96, 165, 250, .12));
  font-size: 20px;
}

.week-compare-title strong {
  display: block;
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 15px;
  font-weight: 850;
}

.week-compare-title span {
  display: block;
  margin-top: 4px;
  overflow: hidden;
  color: light-dark(#64748b, var(--text-secondary));
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.week-compare-grid {
  display: grid;
  flex: 1;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  min-width: 0;
}

.week-compare-item {
  min-width: 0;
  padding: 2px 0;
}

.week-compare-item > span {
  color: light-dark(#64748b, var(--text-secondary));
  font-size: 12px;
  font-weight: 800;
}

.week-compare-item strong {
  display: block;
  margin-top: 6px;
  overflow: hidden;
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 22px;
  font-weight: 850;
  line-height: 1.15;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.week-compare-item small {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  color: light-dark(#94a3b8, var(--text-secondary));
  font-size: 11px;
}

.week-compare-item em {
  overflow: hidden;
  font-style: normal;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trend-dot {
  flex: 0 0 auto;
  font-weight: 800;
}

.trend-dot--up,
.kpi-trend--up {
  color: light-dark(#16a34a, #6ee7b7);
}

.trend-dot--down,
.kpi-trend--down {
  color: light-dark(#dc2626, #f87171);
}

.trend-dot--flat,
.kpi-trend--flat {
  color: light-dark(#64748b, var(--text-secondary));
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
  max-width: 1480px;
  margin: 0 auto 14px;
}

.kpi-card {
  min-width: 0;
  padding: 14px 16px;
  border: 1px solid light-dark(#dbe5ef, var(--border-color));
  border-left: 4px solid #64748b;
  border-radius: 8px;
  background: light-dark(#ffffff, var(--app-surface));
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.05);
}

.kpi-card--amber {
  border-left-color: #d97706;
}

.kpi-card span,
.kpi-card small {
  display: block;
  overflow: hidden;
  color: light-dark(#64748b, var(--text-secondary));
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kpi-card span {
  margin-bottom: 9px;
  font-size: 12px;
  font-weight: 800;
}

.kpi-card strong {
  display: block;
  overflow: hidden;
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 25px;
  font-weight: 850;
  line-height: 1.15;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kpi-card small {
  margin-top: 8px;
  font-size: 12px;
}

.kpi-trend {
  display: block;
  margin-top: 8px;
  font-size: 11px;
  font-weight: 800;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(360px, 0.9fr);
  gap: 14px;
  max-width: 1480px;
  margin: 0 auto;
}

.panel {
  min-width: 0;
  border: 1px solid light-dark(#dbe5ef, var(--border-color));
  border-radius: 8px;
  background: light-dark(#ffffff, var(--app-surface));
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.05);
  overflow: hidden;
}

.panel--wide {
  min-height: 320px;
}

.panel--full {
  grid-column: 1 / -1;
}

.panel-header {
  justify-content: space-between;
  gap: 10px;
  min-height: 52px;
  padding: 0 18px;
  border-bottom: 1px solid light-dark(#e2e8f0, var(--border-color));
  background: light-dark(#fbfdff, var(--app-surface-2));
}

.panel-header h2 {
  font-size: 15px;
  font-weight: 850;
}

.panel-header span {
  color: light-dark(#64748b, var(--text-secondary));
  font-size: 12px;
  font-weight: 700;
}

.chart {
  width: 100%;
}

.chart--bar {
  height: 260px;
}

.chart--agent {
  height: 320px;
}

.chart--comparison {
  height: 360px;
}

.chart--matrix {
  height: 286px;
}

.detail-table {
  width: 100%;
}

.detail-table :deep(.el-table__header th) {
  color: light-dark(#475569, var(--text-secondary));
  background: light-dark(#f8fafc, var(--app-surface-2));
  font-weight: 800;
}

.detail-table :deep(.el-tag) {
  gap: 4px;
}

.empty-state {
  max-width: 1480px;
  margin: 18px auto 0;
  padding: 28px;
  border: 1px solid light-dark(#dbe5ef, var(--border-color));
  border-radius: 8px;
  color: light-dark(#64748b, var(--text-secondary));
  background: light-dark(#ffffff, var(--app-surface));
  text-align: center;
  font-weight: 700;
}

@media (max-width: 1180px) {
  .week-compare {
    flex-direction: column;
  }

  .week-compare-head {
    flex: none;
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    padding: 0 0 10px;
    border-right: none;
    border-bottom: 1px dashed light-dark(#dbe5ef, var(--border-color));
  }

  .week-compare-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .kpi-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .dashboard-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .service-dashboard {
    padding: 16px;
  }

  .service-header,
  .filter-bar {
    align-items: stretch;
    flex-direction: column;
  }

  .header-actions {
    justify-content: flex-start;
  }

  .filter-bar :deep(.el-select),
  .filter-bar :deep(.el-button),
  .header-actions :deep(.el-button) {
    width: 100%;
  }

  .week-compare-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .week-compare-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .kpi-grid {
    grid-template-columns: 1fr;
  }

  .chart--bar,
  .chart--agent {
    height: 300px;
  }

  .chart--matrix {
    height: 390px;
  }
}
</style>
