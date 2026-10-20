<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import {
  ElButton,
  ElEmpty,
  ElInput,
  ElInputNumber,
  ElMessage,
  ElOption,
  ElPagination,
  ElSelect,
  ElSwitch,
  ElTable,
  ElTableColumn,
  ElTag,
  ElTooltip,
  ElUpload,
  type UploadFile,
} from 'element-plus'
import { Download, Refresh, Search, UploadFilled } from '@element-plus/icons-vue'
import request from '../utils/request'

interface WarningOptions {
  snapshot_dates: string[]
  latest_snapshot_date?: string | null
  brands: string[]
  categories: string[]
  forecast_days?: number
}

interface WarningSummary {
  total: number
  shortage_count: number
  safe_count: number
  no_jushuitan_count: number
}

interface WarningRow {
  snapshot_date?: string
  sku_code: string
  product_name?: string
  brand?: string
  category?: string
  daily_sales?: number
  predicted_sales?: number
  jst_stock_qty?: number | null
  shortage_qty?: number | null
  status: string
}

interface WarningListResponse {
  items: WarningRow[]
  total: number
  page: number
  page_size: number
  snapshot_date?: string | null
  forecast_days?: number | null
  jst_snapshot_time?: string | null
  summary?: WarningSummary
  brands?: string[]
  categories?: string[]
}

const options = reactive<WarningOptions>({
  snapshot_dates: [],
  latest_snapshot_date: null,
  brands: [],
  categories: [],
})

const filters = reactive({
  snapshotDate: '',
  skuCode: '',
  productName: '',
  brand: '',
  category: '',
  onlyShortage: true,
})

const rows = ref<WarningRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const recalculating = ref(false)
const savingSetting = ref(false)
const settingForecastDays = ref(60)
const activeForecastDays = ref(60)
const lookupImporting = ref(false)
const lookupDownloading = ref(false)
const summary = reactive<WarningSummary>({
  total: 0,
  shortage_count: 0,
  safe_count: 0,
  no_jushuitan_count: 0,
})

const statusMeta: Record<string, { label: string; type: 'danger' | 'success' | 'warning' | 'info' }> = {
  SHORTAGE: { label: '有缺口', type: 'danger' },
  SAFE: { label: '无缺口', type: 'success' },
  NO_JUSHUITAN: { label: '无聚水潭数据', type: 'warning' },
}

const formatNumber = (value: number | null | undefined, digits = 0): string => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  const number = Number(value)
  return number.toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

const fetchOptions = async () => {
  const response = await request.get('/inventory/sku-warnings/options') as { data: WarningOptions }
  const data = response.data || {}
  options.snapshot_dates = data.snapshot_dates || []
  options.latest_snapshot_date = data.latest_snapshot_date || null
  options.brands = data.brands || []
  options.categories = data.categories || []
  if (data.forecast_days) {
    settingForecastDays.value = data.forecast_days
    activeForecastDays.value = data.forecast_days
  }
  if (!filters.snapshotDate && options.snapshot_dates.length) {
    filters.snapshotDate = options.snapshot_dates[0]
  }
}

const fetchRows = async () => {
  loading.value = true
  try {
    const response = await request.get('/inventory/sku-warnings', {
      params: {
        snapshot_date: filters.snapshotDate || undefined,
        view: filters.onlyShortage ? 'shortage' : 'safe',
        sku_code: filters.skuCode || undefined,
        product_name: filters.productName || undefined,
        brand: filters.brand || undefined,
        category: filters.category || undefined,
        forecast_days: settingForecastDays.value || undefined,
        page: page.value,
        page_size: pageSize.value,
      },
    }) as WarningListResponse
    rows.value = response.items || []
    total.value = response.total || 0
    if (response.snapshot_date && !filters.snapshotDate) {
      filters.snapshotDate = response.snapshot_date
    }
    if (response.forecast_days) {
      activeForecastDays.value = response.forecast_days
    }
    const nextSummary: WarningSummary = response.summary || {
      total: 0,
      shortage_count: 0,
      safe_count: 0,
      no_jushuitan_count: 0,
    }
    summary.total = nextSummary.total || 0
    summary.shortage_count = nextSummary.shortage_count || 0
    summary.safe_count = nextSummary.safe_count || 0
    summary.no_jushuitan_count = nextSummary.no_jushuitan_count || 0
    if (response.brands?.length) options.brands = response.brands
    if (response.categories?.length) options.categories = response.categories
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  page.value = 1
  void fetchRows()
}

const handleReset = () => {
  filters.skuCode = ''
  filters.productName = ''
  filters.brand = ''
  filters.category = ''
  filters.onlyShortage = true
  page.value = 1
  void fetchRows()
}

const handleViewChange = () => {
  page.value = 1
  void fetchRows()
}

const handleDateChange = () => {
  page.value = 1
  void fetchRows()
}

const handlePageChange = (nextPage: number) => {
  page.value = nextPage
  void fetchRows()
}

const handlePageSizeChange = (nextSize: number) => {
  pageSize.value = nextSize
  page.value = 1
  void fetchRows()
}

const handleRecalculate = async () => {
  recalculating.value = true
  try {
    const response = await request.post('/inventory/sku-warnings/recalculate') as {
      data?: { snapshot_date?: string | null }
    }
    const snapshotDate = response.data?.snapshot_date
    if (snapshotDate) filters.snapshotDate = snapshotDate
    await fetchOptions()
    page.value = 1
    await fetchRows()
    ElMessage.success('SKU库存预警已按最新库存表重新计算')
  } finally {
    recalculating.value = false
  }
}

const handleSaveSetting = async () => {
  savingSetting.value = true
  try {
    const days = Math.max(1, Math.min(365, Math.round(Number(settingForecastDays.value) || 60)))
    const response = await request.post('/inventory/sku-warnings/setting', {
      forecast_days: days,
    }) as { data?: { forecast_days?: number } }
    const savedDays = response.data?.forecast_days || days
    settingForecastDays.value = savedDays
    activeForecastDays.value = savedDays
    page.value = 1
    await fetchRows()
    ElMessage.success(`安全期限已更新为 ${savedDays} 天`)
  } finally {
    savingSetting.value = false
  }
}

const downloadLookupTemplate = async () => {
  lookupDownloading.value = true
  try {
    const response = await request.get('/inventory/sku-jst-lookup/template', {
      responseType: 'blob',
    } as never) as unknown as Blob
    const blob = response instanceof Blob
      ? response
      : new Blob([response as BlobPart], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = '聚水潭查找编码模板.xlsx'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success('模板已下载，请按 sku / 聚水潭查找编码 填写后导入')
  } finally {
    lookupDownloading.value = false
  }
}

const importLookupTemplate = async (file: UploadFile) => {
  const rawFile = file.raw
  if (!rawFile) {
    ElMessage.warning('请先选择模板文件')
    return
  }
  lookupImporting.value = true
  const formData = new FormData()
  formData.append('file', rawFile)
  try {
    const response = await request.post('/inventory/sku-jst-lookup/import', formData) as {
      data?: { imported?: number; skipped?: number; rows_read?: number }
    }
    const imported = response.data?.imported || 0
    ElMessage.success(`模板导入成功，共导入 ${imported} 条映射，下次同步聚水潭库存时生效`)
  } finally {
    lookupImporting.value = false
  }
}

const refresh = async () => {
  await fetchOptions()
  await fetchRows()
}

onMounted(() => {
  void refresh()
})

defineExpose({ refresh })
</script>

<template>
  <section class="warning-panel">
    <div class="warning-head">
      <div>
        <h2>SKU 库存预警</h2>
        <span>预测销量来自每日库存表各仓库日均之和，按未来 {{ activeForecastDays }} 天对比聚水潭库存件数</span>
      </div>
      <div class="warning-actions">
        <el-tooltip
          content="下载 SKU 与聚水潭查找编码对照模板，给查询不到库存的 SKU 填写对应的聚水潭编码"
          placement="top"
        >
          <el-button :icon="Download" :loading="lookupDownloading" @click="downloadLookupTemplate">
            下载模板
          </el-button>
        </el-tooltip>
        <el-tooltip
          content="导入填好的对照表，保存映射后会立即用这些编码向聚水潭同步一次库存"
          placement="top"
        >
          <el-upload
            :auto-upload="false"
            :show-file-list="false"
            :limit="1"
            accept=".xlsx"
            :on-change="importLookupTemplate"
          >
            <el-button :icon="UploadFilled" :loading="lookupImporting" type="primary">
              导入模板
            </el-button>
          </el-upload>
        </el-tooltip>
        <div class="setting-control">
          <span class="setting-label">仓库安全期限(天)</span>
          <el-input-number
            v-model="settingForecastDays"
            :min="1"
            :max="365"
            :step="1"
            :controls="false"
            class="setting-input"
          />
          <el-button
            type="success"
            plain
            :loading="savingSetting"
            @click="handleSaveSetting"
          >
            保存期限
          </el-button>
        </div>
        <el-button
          type="primary"
          plain
          :icon="Refresh"
          :loading="recalculating"
          @click="handleRecalculate"
        >
          重新计算
        </el-button>
      </div>
    </div>

    <section class="filter-bar">
      <el-select
        v-model="filters.snapshotDate"
        class="filter-control date-control"
        placeholder="预测日期"
        clearable
        filterable
        @change="handleDateChange"
      >
        <el-option v-for="item in options.snapshot_dates" :key="item" :label="item" :value="item" />
      </el-select>
      <el-input
        v-model="filters.skuCode"
        class="filter-control keyword-input"
        placeholder="SKU"
        clearable
        @keyup.enter="handleSearch"
      />
      <el-input
        v-model="filters.productName"
        class="filter-control name-input"
        placeholder="商品名称"
        clearable
        @keyup.enter="handleSearch"
      />
      <el-select v-model="filters.brand" class="filter-control" placeholder="品牌" clearable filterable>
        <el-option v-for="item in options.brands" :key="item" :label="item" :value="item" />
      </el-select>
      <el-select v-model="filters.category" class="filter-control" placeholder="类目" clearable filterable>
        <el-option v-for="item in options.categories" :key="item" :label="item" :value="item" />
      </el-select>
      <div class="filter-actions">
        <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
        <el-button @click="handleReset">重置</el-button>
      </div>
      <div class="view-toggle">
        <el-switch
          v-model="filters.onlyShortage"
          active-text="只看缺口"
          inactive-text="无缺口"
          @change="handleViewChange"
        />
        <span>关闭后仅显示无缺口的 SKU</span>
      </div>
    </section>

    <section class="summary-strip">
      <div>
        <span>数据日期</span>
        <strong>{{ filters.snapshotDate || summary.total ? filters.snapshotDate : '-' }}</strong>
      </div>
      <div>
        <span>总 SKU</span>
        <strong>{{ formatNumber(summary.total) }}</strong>
      </div>
      <div class="summary-danger">
        <span>有缺口</span>
        <strong>{{ formatNumber(summary.shortage_count) }}</strong>
      </div>
      <div class="summary-warning">
        <span>无聚水潭数据</span>
        <strong>{{ formatNumber(summary.no_jushuitan_count) }}</strong>
      </div>
      <div class="summary-success">
        <span>无缺口</span>
        <strong>{{ formatNumber(summary.safe_count) }}</strong>
      </div>
    </section>

    <el-table
      v-loading="loading"
      :data="rows"
      stripe
      table-layout="fixed"
      class="warning-table"
    >
      <el-table-column label="SKU" prop="sku_code" width="150" fixed="left" show-overflow-tooltip />
      <el-table-column label="商品名称" min-width="240" fixed="left">
        <template #default="{ row }">
          <el-tooltip :content="row.product_name || '-'" placement="top">
            <span class="product-name">{{ row.product_name || '-' }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="品牌" min-width="140" show-overflow-tooltip>
        <template #default="{ row }">{{ row.brand || '-' }}</template>
      </el-table-column>
      <el-table-column label="类目" min-width="100" show-overflow-tooltip>
        <template #default="{ row }">{{ row.category || '-' }}</template>
      </el-table-column>
      <el-table-column :label="`未来 ${activeForecastDays} 天预测`" min-width="130" align="right">
        <template #default="{ row }">
          <strong>{{ formatNumber(row.predicted_sales, 1) }}</strong>
        </template>
      </el-table-column>
      <el-table-column label="聚水潭库存件数" min-width="130" align="right">
        <template #default="{ row }">
          {{ row.jst_stock_qty === null || row.jst_stock_qty === undefined ? '-' : formatNumber(row.jst_stock_qty) }}
        </template>
      </el-table-column>
      <el-table-column label="缺口" min-width="110" align="right">
        <template #default="{ row }">
          <strong :class="{ 'shortage-qty': (row.shortage_qty || 0) > 0 }">
            {{ row.shortage_qty === null || row.shortage_qty === undefined ? '-' : formatNumber(row.shortage_qty) }}
          </strong>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="130" align="center" fixed="right">
        <template #default="{ row }">
          <el-tag :type="statusMeta[row.status]?.type || 'info'" effect="light" size="small">
            {{ statusMeta[row.status]?.label || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <template #empty>
        <el-empty
          :description="summary.total > 0 ? '当前筛选条件下暂无数据' : '暂无预警数据，导入库存表后会自动生成'"
          :image-size="88"
        />
      </template>
    </el-table>

    <div v-if="total > 0" class="pagination-row">
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

<style scoped>
.warning-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.warning-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.warning-head h2 {
  margin: 0;
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 18px;
  font-weight: 800;
  letter-spacing: 0;
}

.warning-head span {
  display: block;
  margin-top: 4px;
  color: light-dark(#64748b, var(--text-secondary));
  font-size: 12px;
}

.warning-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  flex-shrink: 0;
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding: 12px;
  border: 1px solid light-dark(#e2e8f0, var(--border-color));
  border-radius: 8px;
  background: light-dark(#ffffff, var(--app-surface));
}

.filter-control {
  width: 150px;
}

.filter-control.date-control {
  width: 150px;
}

.filter-control.keyword-input {
  width: 150px;
}

.filter-control.name-input {
  width: 180px;
}

.filter-actions {
  display: inline-flex;
  gap: 8px;
}

.view-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  color: light-dark(#475569, var(--text-secondary));
  font-size: 12px;
}

.view-toggle span {
  color: light-dark(#94a3b8, var(--text-secondary));
}

.setting-control {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.setting-label {
  color: light-dark(#475569, var(--text-secondary));
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.setting-input {
  width: 104px;
}

.summary-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.summary-strip > div {
  display: flex;
  min-width: 132px;
  flex: 1 1 132px;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 14px;
  border: 1px solid light-dark(#e2e8f0, var(--border-color));
  border-radius: 8px;
  background: light-dark(#ffffff, var(--app-surface));
}

.summary-strip span {
  color: light-dark(#64748b, var(--text-secondary));
  font-size: 12px;
  font-weight: 600;
}

.summary-strip strong {
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 18px;
  font-weight: 800;
}

.summary-strip .summary-danger strong {
  color: light-dark(#dc2626, #f87171);
}

.summary-strip .summary-warning strong {
  color: light-dark(#d97706, #fbbf24);
}

.summary-strip .summary-success strong {
  color: light-dark(#16a34a, #6ee7b7);
}

.warning-table {
  border-radius: 8px;
}

.product-name {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}

.shortage-qty {
  color: light-dark(#dc2626, #f87171);
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
  padding: 4px 0;
}

@media (max-width: 900px) {
  .warning-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .warning-actions {
    width: 100%;
    justify-content: flex-start;
    flex-wrap: wrap;
  }

  .view-toggle {
    width: 100%;
    margin-left: 0;
  }

  .setting-control {
    width: 100%;
    justify-content: flex-start;
  }

  .filter-control,
  .filter-control.date-control,
  .filter-control.keyword-input,
  .filter-control.name-input {
    width: 100%;
  }
}
</style>
