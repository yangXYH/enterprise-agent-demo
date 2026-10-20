<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  ElButton, ElCard, ElDescriptions, ElDescriptionsItem, ElDrawer, ElEmpty,
  ElInput, ElMessage, ElOption, ElSelect, ElTable, ElTableColumn, ElTabs,
  ElTabPane, ElTag,
} from 'element-plus'
import { AlarmClock, Calendar, CircleCheck, Clock, DataAnalysis, Money, Refresh, Search, Timer, TrendCharts, User, Warning } from '@element-plus/icons-vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import request from '../../utils/request'
import ImportBlock from './ImportBlock.vue'

use([CanvasRenderer, BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent])

const month = ref('')
const months = ref<string[]>([])
const dept = ref('')
const depts = ref<string[]>([])
const keyword = ref('')

const rows = ref<any[]>([])
const overview = ref<any>({})
const deptSummary = ref<any[]>([])
const dailyRows = ref<any[]>([])
const lateRows = ref<any[]>([])
const leaveRows = ref<any[]>([])
const makeupRows = ref<any[]>([])

const activeTab = ref('summary')
const loading = ref(false)
const detailLoading = ref(false)

// 人员详情抽屉
const drawerVisible = ref(false)
const drawerLoading = ref(false)
const person = ref<any>(null)

const fmtNum = (v: any, digits = 1) => {
  const n = Number(v ?? 0)
  if (Number.isNaN(n)) return '0'
  return n.toFixed(digits)
}

// ── 统计卡片 ─────────────────────────────────────────────
const statCards = computed(() => [
  {
    label: '在册人数', value: fmtNum(overview.value.employee_count, 0), unit: '人',
    sub: `${fmtNum(overview.value.work_days_total)} 天应出勤`, icon: User, color: '#0f766e', bg: '#ecfdf5',
  },
  {
    label: '实际出勤', value: fmtNum(overview.value.actual_days_total), unit: '天',
    sub: `出勤率 ${overview.value.work_days_total ? fmtNum((overview.value.actual_days_total || 0) / (overview.value.work_days_total || 1) * 100, 1) : '0'}%`,
    icon: CircleCheck, color: '#0284c7', bg: '#f0f9ff',
  },
  {
    label: '迟到', value: fmtNum(overview.value.late_total, 0), unit: '人次',
    sub: `负激励 ${fmtNum(overview.value.late_penalty_total)} 元`, icon: AlarmClock, color: '#d97706', bg: '#fffbeb',
  },
  {
    label: '早退', value: fmtNum(overview.value.early_total, 0), unit: '人次',
    sub: `负激励 ${fmtNum(overview.value.early_penalty_total)} 元`, icon: Clock, color: '#ea580c', bg: '#fff7ed',
  },
  {
    label: '请假', value: fmtNum(overview.value.leave_total), unit: '天',
    sub: `事假 ${fmtNum(overview.value.personal_days_total)} · 病假 ${fmtNum(overview.value.sick_days_total)}`,
    icon: Calendar, color: '#7c3aed', bg: '#f5f3ff',
  },
  {
    label: '加班', value: fmtNum(overview.value.overtime_total), unit: '小时',
    sub: '本月累计', icon: Timer, color: '#0891b2', bg: '#ecfeff',
  },
  {
    label: '补卡', value: fmtNum(overview.value.makeup_total, 0), unit: '次',
    sub: `负激励 ${fmtNum(overview.value.makeup_penalty_total)} 元`, icon: TrendCharts, color: '#2563eb', bg: '#eff6ff',
  },
  {
    label: '负激励合计', value: fmtNum(overview.value.penalty_total), unit: '元',
    sub: `含病假工资 ${fmtNum(overview.value.sick_wage_total)} 元`, icon: Money, color: '#dc2626', bg: '#fef2f2',
  },
])

// ── 部门图表 ─────────────────────────────────────────────
const deptChartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['应出勤(均)', '实际出勤(均)'], top: 0, right: 0 },
  grid: { left: 40, right: 12, top: 36, bottom: 28 },
  xAxis: { type: 'category', data: (deptSummary.value || []).map((d: any) => d.dept_name) },
  yAxis: { type: 'value', name: '天' },
  series: [
    { name: '应出勤(均)', type: 'bar', barWidth: 14, data: (deptSummary.value || []).map((d: any) => d.avg_work_days ?? d.avg_actual_days), itemStyle: { color: '#cbd5e1', borderRadius: [3, 3, 0, 0] } },
    { name: '实际出勤(均)', type: 'bar', barWidth: 14, data: (deptSummary.value || []).map((d: any) => d.avg_actual_days), itemStyle: { color: '#0f766e', borderRadius: [3, 3, 0, 0] } },
  ],
}))

const lateChartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['迟到人次', '迟到负激励(元)'], top: 0, right: 0 },
  grid: { left: 40, right: 44, top: 36, bottom: 28 },
  xAxis: { type: 'category', data: (deptSummary.value || []).map((d: any) => d.dept_name) },
  yAxis: [
    { type: 'value', name: '人次' },
    { type: 'value', name: '元' },
  ],
  series: [
    { name: '迟到人次', type: 'bar', barWidth: 14, data: (deptSummary.value || []).map((d: any) => d.late_total), itemStyle: { color: '#f59e0b', borderRadius: [3, 3, 0, 0] } },
    { name: '迟到负激励(元)', type: 'line', yAxisIndex: 1, smooth: true, data: (deptSummary.value || []).map((d: any) => d.late_penalty_total), itemStyle: { color: '#dc2626' } },
  ],
}))

// ── 加载 ─────────────────────────────────────────────────
const load = async () => {
  loading.value = true
  try {
    const [s, ov, ds] = await Promise.all([
      request.get('/hr/attendance/summary', { params: { month: month.value, dept: dept.value, keyword: keyword.value } }) as Promise<any>,
      request.get('/hr/attendance/overview', { params: { month: month.value } }) as Promise<any>,
      request.get('/hr/attendance/dept-summary', { params: { month: month.value } }) as Promise<any>,
    ])
    rows.value = s || []
    overview.value = ov || {}
    deptSummary.value = ds || []
    if (!months.value.length) {
      months.value = Array.from(new Set((s || []).map((r: any) => r.month).filter(Boolean)))
    }
    if (!depts.value.length) {
      depts.value = Array.from(new Set((s || []).map((r: any) => r.dept1 || r.dept_name).filter(Boolean)))
    }
    // 默认选中最近月份
    if (!month.value && months.value.length) {
      month.value = months.value[0]
      await load()
      return
    }
    await loadDetailData()
  } finally {
    loading.value = false
  }
}

const loadDetailData = async () => {
  try {
    const [daily, late, leave, makeup] = await Promise.all([
      request.get('/hr/attendance/detail', { params: { month: month.value, dept: dept.value } }) as Promise<any>,
      request.get('/hr/attendance/late', { params: { month: month.value } }) as Promise<any>,
      request.get('/hr/attendance/leave', { params: { month: month.value } }) as Promise<any>,
      request.get('/hr/attendance/makeup', { params: { month: month.value } }) as Promise<any>,
    ])
    dailyRows.value = daily || []
    lateRows.value = late || []
    leaveRows.value = leave || []
    makeupRows.value = makeup || []
  } catch { /* interceptor */ }
}

const onTabChange = () => {
  // 明细数据已在 load 时统一加载
}

const onImported = async () => {
  months.value = []
  depts.value = []
  month.value = ''
  await load()
}

const openPerson = async (row: any) => {
  drawerVisible.value = true
  drawerLoading.value = true
  person.value = null
  try {
    person.value = await request.get('/hr/attendance/person', { params: { month: month.value, name: row.name } }) as any
  } finally {
    drawerLoading.value = false
  }
}

// 汇总行数值展示
const penaltySum = (row: any) => {
  return ((Number(row.late_penalty) || 0) + (Number(row.early_penalty) || 0) + (Number(row.makeup_penalty) || 0)).toFixed(0)
}
const attendanceRate = (row: any) => {
  const w = Number(row.work_days) || 0
  const a = Number(row.actual_days) || 0
  return w ? Math.round((a / w) * 1000) / 10 : 0
}
const abnormalTag = (row: any) => {
  const n = Number(row.abnormal_count) || 0
  if (n === 0) return { text: '正常', type: 'success' as any }
  if (n < 4) return { text: `异常 ${n}`, type: 'warning' as any }
  return { text: `异常 ${n}`, type: 'danger' as any }
}
const leaveTag = (type: string) => {
  const map: Record<string, string> = { 病假: 'danger', 事假: 'warning', 年假: 'success', 调休: 'primary', 婚假: 'danger', 产假: 'warning', 陪产假: 'warning', 产检假: 'info', 丧假: 'info', 哺乳假: 'info' }
  return map[type] || 'info'
}

onMounted(load)
</script>

<template>
  <div class="hr-page">
    <!-- 页头 -->
    <div class="page-head">
      <div class="title">
        考勤汇总
        <span v-if="month" class="title-month">{{ month }}</span>
      </div>
      <div class="head-actions">
        <el-select v-model="month" placeholder="选择月份" clearable style="width: 150px" @change="load">
          <el-option v-for="m in months" :key="m" :label="m" :value="m" />
        </el-select>
        <el-button :icon="Refresh" circle @click="load" title="刷新" />
      </div>
    </div>

    <el-card shadow="never" class="top-card">
      <ImportBlock import-api="/api/hr/import/attendance" template-api="/api/hr/attendance/template"
        title="考勤" tip="支持导入《考勤汇总表》（汇总/迟到/请假/补卡/每日统计）或《每日统计》Excel，自动识别两行表头与月份" @imported="onImported" />

      <!-- 统计卡片 -->
      <div class="stat-grid" v-loading="loading">
        <div v-for="c in statCards" :key="c.label" class="stat-card" :style="{ '--stat-color': c.color, '--stat-bg': c.bg }">
          <div class="stat-icon">
            <component :is="c.icon" />
          </div>
          <div class="stat-body">
            <div class="stat-label">{{ c.label }}</div>
            <div class="stat-value">
              {{ c.value }}<span class="stat-unit">{{ c.unit }}</span>
            </div>
            <div class="stat-sub">{{ c.sub }}</div>
          </div>
        </div>
      </div>

      <!-- 部门图表 -->
      <div class="chart-grid" v-loading="loading">
        <div class="chart-card">
          <div class="chart-title"><el-icon><DataAnalysis /></el-icon> 部门出勤对比（均天）</div>
          <v-chart :option="deptChartOption" style="height: 230px" autoresize />
        </div>
        <div class="chart-card">
          <div class="chart-title"><el-icon><Warning /></el-icon> 部门迟到与负激励</div>
          <v-chart :option="lateChartOption" style="height: 230px" autoresize />
        </div>
      </div>

      <!-- 筛选 -->
      <div class="filters">
        <el-input v-model="keyword" placeholder="按姓名搜索" clearable style="width: 200px" class="filter-input" @keyup.enter="load">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="dept" placeholder="一级部门" clearable filterable style="width: 190px" class="filter-select" @change="load">
          <el-option v-for="d in depts" :key="d" :label="d" :value="d" />
        </el-select>
        <el-button type="primary" :icon="Search" @click="load">查询</el-button>
        <span class="filter-tip">共 {{ rows.length }} 人 · 点击姓名行查看每日明细</span>
      </div>

      <!-- Tabs -->
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <!-- 汇总 -->
        <el-tab-pane label="汇总" name="summary">
          <el-table :data="rows" v-loading="loading" stripe border class="att-table" :header-row-class-name="'tbl-header'"
            row-key="id" @row-click="openPerson" max-height="560">
            <el-table-column type="index" label="#" width="48" align="center" fixed />
            <el-table-column label="基础信息" fixed>
              <el-table-column prop="name" label="姓名" width="96">
                <template #default="{ row }">
                  <span class="cell-name">{{ row.name }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="dept1" label="一级部门" width="120" show-overflow-tooltip />
              <el-table-column prop="dept2" label="二级部门" width="130" show-overflow-tooltip>
                <template #default="{ row }"><span v-if="row.dept2 && row.dept2 !== '/'">{{ row.dept2 }}</span><span v-else class="cell-empty">—</span></template>
              </el-table-column>
              <el-table-column prop="dept3" label="三级部门" width="120" show-overflow-tooltip />
              <el-table-column prop="position" label="岗位" width="120" show-overflow-tooltip />
              <el-table-column prop="hire_date" label="入职" width="104" />
            </el-table-column>
            <el-table-column label="出勤（天）" align="center">
              <el-table-column prop="paid_days" label="应计薪" width="76" align="right" />
              <el-table-column prop="actual_paid_days" label="实计薪" width="76" align="right" />
              <el-table-column prop="work_days" label="应出勤" width="76" align="right" />
              <el-table-column prop="actual_days" label="实出勤" width="76" align="right">
                <template #default="{ row }">
                  <span class="num-main">{{ fmtNum(row.actual_days) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="出勤率" width="82" align="right">
                <template #default="{ row }">
                  <el-tag size="small" :type="attendanceRate(row) >= 90 ? 'success' : attendanceRate(row) >= 80 ? 'warning' : 'danger'" effect="plain">
                    {{ attendanceRate(row) }}%
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="absent_work_days" label="旷工" width="70" align="right">
                <template #default="{ row }"><span v-if="Number(row.absent_work_days) > 0" class="num-bad">{{ fmtNum(row.absent_work_days) }}</span><span v-else class="cell-empty">—</span></template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="休假（天）" align="center">
              <el-table-column prop="annual_leave" label="年假" width="66" align="right" />
              <el-table-column prop="comp_leave" label="调休" width="66" align="right" />
              <el-table-column prop="sick_days" label="病假" width="66" align="right" />
              <el-table-column prop="personal_days" label="事假" width="66" align="right" />
              <el-table-column prop="comp_days_extra" label="可调休" width="72" align="right">
                <template #default="{ row }"><span v-if="Number(row.comp_days_extra) > 0" class="num-ok">{{ fmtNum(row.comp_days_extra) }}</span><span v-else class="cell-empty">—</span></template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="异常" align="center">
              <el-table-column prop="late_count" label="迟到" width="70" align="right">
                <template #default="{ row }"><span v-if="Number(row.late_count) > 0" class="num-bad">{{ row.late_count }}</span><span v-else class="cell-empty">—</span></template>
              </el-table-column>
              <el-table-column prop="serious_late_count" label="严迟" width="66" align="right" />
              <el-table-column prop="early_count" label="早退" width="66" align="right" />
              <el-table-column prop="makeup_count" label="补卡" width="66" align="right" />
              <el-table-column label="缺卡" width="76" align="center">
                <template #default="{ row }">
                  <span v-if="(Number(row.on_missing_count) || 0) + (Number(row.off_missing_count) || 0) > 0" class="num-bad">{{ row.on_missing_count || 0 }}/{{ row.off_missing_count || 0 }}</span>
                  <span v-else class="cell-empty">—</span>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="88" align="center">
                <template #default="{ row }">
                  <el-tag size="small" :type="abnormalTag(row).type" effect="plain">{{ abnormalTag(row).text }}</el-tag>
                </template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="需支付（元）" align="center">
              <el-table-column prop="late_penalty" label="迟到" width="72" align="right">
                <template #default="{ row }"><span v-if="Number(row.late_penalty) > 0" class="num-bad">{{ fmtNum(row.late_penalty, 0) }}</span><span v-else class="cell-empty">—</span></template>
              </el-table-column>
              <el-table-column prop="early_penalty" label="早退" width="72" align="right">
                <template #default="{ row }"><span v-if="Number(row.early_penalty) > 0" class="num-bad">{{ fmtNum(row.early_penalty, 0) }}</span><span v-else class="cell-empty">—</span></template>
              </el-table-column>
              <el-table-column prop="makeup_penalty" label="补卡" width="72" align="right">
                <template #default="{ row }"><span v-if="Number(row.makeup_penalty) > 0" class="num-bad">{{ fmtNum(row.makeup_penalty, 0) }}</span><span v-else class="cell-empty">—</span></template>
              </el-table-column>
              <el-table-column prop="sick_wage" label="病假工资" width="84" align="right">
                <template #default="{ row }"><span v-if="Number(row.sick_wage) > 0">{{ fmtNum(row.sick_wage, 0) }}</span><span v-else class="cell-empty">—</span></template>
              </el-table-column>
              <el-table-column label="小计" width="84" align="right">
                <template #default="{ row }">
                  <span v-if="Number(penaltySum(row)) > 0" class="num-total">{{ penaltySum(row) }}</span>
                  <span v-else class="cell-empty">—</span>
                </template>
              </el-table-column>
            </el-table-column>
            <el-table-column prop="overtime_hours" label="加班(时)" width="86" align="right" />
            <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip />
            <template #empty>
              <el-empty description="暂无考勤数据，请先导入《考勤汇总表》或《每日统计》" :image-size="80" />
            </template>
          </el-table>
        </el-tab-pane>

        <!-- 每日明细 -->
        <el-tab-pane :label="`每日明细 (${dailyRows.length})`" name="daily">
          <el-table :data="dailyRows" v-loading="loading" stripe border class="att-table" :header-row-class-name="'tbl-header'" max-height="560">
            <el-table-column prop="work_date" label="日期" width="110" fixed />
            <el-table-column prop="weekday" label="星期" width="80" align="center" />
            <el-table-column prop="name" label="姓名" width="100" />
            <el-table-column prop="dept_name" label="部门" width="130" show-overflow-tooltip />
            <el-table-column label="上班" width="170">
              <template #default="{ row }">
                <div class="punch">
                  <span class="punch-time">{{ row.on_time || '—' }}</span>
                  <el-tag size="small" effect="plain" :type="(row.on_result || '').includes('迟到') ? 'danger' : (row.on_result || '').includes('正常') ? 'success' : 'info'">{{ row.on_result || '—' }}</el-tag>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="下班" width="170">
              <template #default="{ row }">
                <div class="punch">
                  <span class="punch-time">{{ row.off_time || '—' }}</span>
                  <el-tag size="small" effect="plain" :type="(row.off_result || '').includes('早退') ? 'danger' : (row.off_result || '').includes('正常') ? 'success' : 'info'">{{ row.off_result || '—' }}</el-tag>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="出勤" align="center">
              <el-table-column prop="actual_days" label="天数" width="66" align="right" />
              <el-table-column prop="actual_hours" label="时长(h)" width="76" align="right" />
            </el-table-column>
            <el-table-column label="异常" align="center">
              <el-table-column prop="late_count" label="迟到" width="64" align="right" />
              <el-table-column prop="early_count" label="早退" width="64" align="right" />
              <el-table-column prop="makeup_count" label="补卡" width="64" align="right" />
              <el-table-column prop="absent_hours" label="缺勤(h)" width="80" align="right" />
            </el-table-column>
            <el-table-column label="加班(h)" align="center">
              <el-table-column prop="overtime_hours" label="总" width="60" align="right" />
              <el-table-column prop="overtime_paid_hours" label="计费" width="64" align="right" />
              <el-table-column prop="overtime_comp_hours" label="调休" width="64" align="right" />
            </el-table-column>
            <template #empty>
              <el-empty description="暂无每日明细，请导入《每日统计》或包含该表的汇总工作簿" :image-size="80" />
            </template>
          </el-table>
        </el-tab-pane>

        <!-- 迟到 -->
        <el-tab-pane :label="`迟到记录 (${lateRows.length})`" name="late">
          <el-table :data="lateRows" v-loading="loading" stripe border class="att-table" :header-row-class-name="'tbl-header'" max-height="560">
            <el-table-column type="index" label="#" width="50" align="center" />
            <el-table-column prop="name" label="姓名" width="110" />
            <el-table-column prop="late_date" label="迟到日期" width="120" />
            <el-table-column prop="late_time" label="迟到时间" width="110" />
            <el-table-column label="负激励" width="120" align="right">
              <template #default="{ row }">
                <span class="num-bad">-{{ fmtNum(row.penalty_amount, 0) }} 元</span>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty description="本月无迟到记录" :image-size="80" />
            </template>
          </el-table>
        </el-tab-pane>

        <!-- 请假 -->
        <el-tab-pane :label="`请假记录 (${leaveRows.length})`" name="leave">
          <el-table :data="leaveRows" v-loading="loading" stripe border class="att-table" :header-row-class-name="'tbl-header'" max-height="560">
            <el-table-column prop="name" label="姓名" width="100" />
            <el-table-column label="假期类型" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="leaveTag(row.leave_type) as any" effect="plain">{{ row.leave_type }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="reason" label="请假事由" min-width="160" show-overflow-tooltip />
            <el-table-column prop="start_time" label="开始" min-width="170" show-overflow-tooltip />
            <el-table-column prop="end_time" label="结束" min-width="170" show-overflow-tooltip />
            <el-table-column prop="hours" label="时长(h)" width="84" align="right" />
            <el-table-column prop="days" label="时长(天)" width="84" align="right">
              <template #default="{ row }"><span class="num-main">{{ fmtNum(row.days) }}</span></template>
            </el-table-column>
            <template #empty>
              <el-empty description="本月无请假记录" :image-size="80" />
            </template>
          </el-table>
        </el-tab-pane>

        <!-- 补卡 -->
        <el-tab-pane :label="`补卡记录 (${makeupRows.length})`" name="makeup">
          <el-table :data="makeupRows" v-loading="loading" stripe border class="att-table" :header-row-class-name="'tbl-header'" max-height="560">
            <el-table-column type="index" label="#" width="50" align="center" />
            <el-table-column prop="name" label="姓名" width="100" />
            <el-table-column prop="makeup_date" label="补卡日期" width="130" />
            <el-table-column prop="makeup_time" label="补卡时间" width="110" />
            <el-table-column prop="reason" label="补卡事由" min-width="180" show-overflow-tooltip />
            <el-table-column label="负激励" width="120" align="right">
              <template #default="{ row }">
                <span class="num-bad">-{{ fmtNum(row.penalty_amount, 0) }} 元</span>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty description="本月无补卡记录" :image-size="80" />
            </template>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 员工考勤档案抽屉 -->
    <el-drawer v-model="drawerVisible" size="720px" :title="person?.summary?.name ? `${person.summary.name} · ${month || ''} 考勤档案` : '考勤档案'">
      <div v-loading="drawerLoading">
        <template v-if="person">
          <el-descriptions :column="4" border size="small" class="person-desc">
            <el-descriptions-item label="一级部门">{{ person.summary?.dept1 || '—' }}</el-descriptions-item>
            <el-descriptions-item label="二级部门">{{ (person.summary?.dept2 && person.summary.dept2 !== '/') ? person.summary.dept2 : '—' }}</el-descriptions-item>
            <el-descriptions-item label="三级部门">{{ person.summary?.dept3 || '—' }}</el-descriptions-item>
            <el-descriptions-item label="岗位">{{ person.summary?.position || '—' }}</el-descriptions-item>
            <el-descriptions-item label="应出勤(天)">{{ fmtNum(person.summary?.work_days) }}</el-descriptions-item>
            <el-descriptions-item label="实际出勤(天)">{{ fmtNum(person.summary?.actual_days) }}</el-descriptions-item>
            <el-descriptions-item label="应计薪(天)">{{ fmtNum(person.summary?.paid_days) }}</el-descriptions-item>
            <el-descriptions-item label="实计薪(天)">{{ fmtNum(person.summary?.actual_paid_days) }}</el-descriptions-item>
            <el-descriptions-item label="迟到 / 负激励">{{ person.summary?.late_count || 0 }} 次 / {{ fmtNum(person.summary?.late_penalty, 0) }} 元</el-descriptions-item>
            <el-descriptions-item label="补卡 / 负激励">{{ person.summary?.makeup_count || 0 }} 次 / {{ fmtNum(person.summary?.makeup_penalty, 0) }} 元</el-descriptions-item>
            <el-descriptions-item label="请假(天)">{{ fmtNum(person.summary?.leave_days) }}</el-descriptions-item>
            <el-descriptions-item label="加班(时)">{{ fmtNum(person.summary?.overtime_hours) }}</el-descriptions-item>
            <el-descriptions-item label="年假">{{ fmtNum(person.summary?.annual_leave) }} 天</el-descriptions-item>
            <el-descriptions-item label="调休">{{ fmtNum(person.summary?.comp_leave) }} 天</el-descriptions-item>
            <el-descriptions-item label="病假">{{ fmtNum(person.summary?.sick_days) }} 天</el-descriptions-item>
            <el-descriptions-item label="事假">{{ fmtNum(person.summary?.personal_days) }} 天</el-descriptions-item>
          </el-descriptions>

          <h4>每日明细（{{ person.daily?.length || 0 }}）</h4>
          <el-table :data="person.daily || []" size="small" border max-height="300">
            <el-table-column prop="work_date" label="日期" width="100" />
            <el-table-column prop="weekday" label="星期" width="64" />
            <el-table-column prop="on_time" label="上班" width="64" />
            <el-table-column prop="on_result" label="上班结果" min-width="96" />
            <el-table-column prop="off_time" label="下班" width="64" />
            <el-table-column prop="off_result" label="下班结果" min-width="96" />
            <el-table-column prop="actual_hours" label="时长(h)" width="80" align="right" />
          </el-table>

          <h4 v-if="(person.late || []).length">迟到记录</h4>
          <el-table v-if="(person.late || []).length" :data="person.late" size="small" border>
            <el-table-column prop="late_date" label="日期" width="110" />
            <el-table-column prop="late_time" label="时间" width="90" />
            <el-table-column label="负激励" width="100" align="right">
              <template #default="{ row }">-{{ fmtNum(row.penalty_amount, 0) }} 元</template>
            </el-table-column>
          </el-table>

          <h4 v-if="(person.leave || []).length">请假记录</h4>
          <el-table v-if="(person.leave || []).length" :data="person.leave" size="small" border>
            <el-table-column prop="leave_type" label="类型" width="80" />
            <el-table-column prop="reason" label="事由" min-width="120" show-overflow-tooltip />
            <el-table-column prop="start_time" label="开始" min-width="150" show-overflow-tooltip />
            <el-table-column prop="days" label="天" width="60" align="right" />
          </el-table>

          <h4 v-if="(person.makeup || []).length">补卡记录</h4>
          <el-table v-if="(person.makeup || []).length" :data="person.makeup" size="small" border>
            <el-table-column prop="makeup_date" label="日期" width="110" />
            <el-table-column prop="makeup_time" label="时间" width="90" />
            <el-table-column prop="reason" label="事由" min-width="140" show-overflow-tooltip />
            <el-table-column label="负激励" width="100" align="right">
              <template #default="{ row }">-{{ fmtNum(row.penalty_amount, 0) }} 元</template>
            </el-table-column>
          </el-table>

          <el-empty v-if="!(person.late || []).length && !(person.leave || []).length && !(person.makeup || []).length" description="本月无异常记录" :image-size="60" />
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.hr-page { padding: 18px 22px 30px; }

/* === 页头 === */
.page-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.page-head .title { font-size: 18px; font-weight: 800; color: light-dark(#0f172a, var(--text-primary)); display: flex; align-items: center; gap: 10px; }
.title-month { font-size: 13px; font-weight: 600; color: light-dark(#0f766e, var(--text-accent)); background: light-dark(#ecfdf5, var(--primary-surface-2)); padding: 2px 10px; border-radius: 999px; border: 1px solid rgba(15,118,110,.18); }
.head-actions { display: flex; align-items: center; gap: 10px; }

.top-card { border: 1px solid light-dark(#e2e8f0, var(--border-color)); box-shadow: 0 1px 2px rgba(15,23,42,.04); }

/* === 统计卡片 === */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
@media (max-width: 1200px) { .stat-grid { grid-template-columns: repeat(2, 1fr); } }
.stat-card {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 16px; border-radius: 12px;
  border: 1px solid rgba(15,23,42,.05);
  background: light-dark(var(--stat-bg), var(--app-surface));
  transition: transform .15s ease, box-shadow .15s ease;
}
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(15,23,42,.08); }
.stat-icon {
  width: 42px; height: 42px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center; font-size: 20px;
  color: light-dark(var(--stat-color), color-mix(in srgb, var(--stat-color) 40%, white));
  background: light-dark(var(--stat-bg), color-mix(in srgb, var(--stat-color) 14%, var(--app-surface)));
}
.stat-body { flex: 1; min-width: 0; }
.stat-label { font-size: 12px; color: light-dark(#64748b, var(--text-secondary)); font-weight: 600; }
.stat-value { color: light-dark(var(--stat-color), color-mix(in srgb, var(--stat-color) 40%, white)); font-size: 22px; font-weight: 800; line-height: 1.2; font-variant-numeric: tabular-nums; }
.stat-unit { font-size: 12px; font-weight: 600; color: light-dark(#94a3b8, var(--text-secondary)); margin-left: 3px; }
.stat-sub { font-size: 11px; color: light-dark(#94a3b8, var(--text-secondary)); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* === 图表 === */
.chart-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
@media (max-width: 1100px) { .chart-grid { grid-template-columns: 1fr; } }
.chart-card { border: 1px solid light-dark(#eef2f7, var(--border-color)); border-radius: 10px; padding: 12px 14px; }
.chart-title { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 700; color: light-dark(#334155, var(--text-primary)); margin-bottom: 6px; }

/* === 筛选 === */
.filters { display: flex; gap: 10px; align-items: center; margin-bottom: 6px; --el-component-size: 36px; }
.filter-tip { margin-left: auto; color: light-dark(#94a3b8, var(--text-secondary)); font-size: 12px; }

/* === Tabs 与表格 === */
.att-table {
  --el-table-border-color: light-dark(#eef2f7, var(--border-color));
  border-radius: 8px;
  overflow: hidden;
}
.att-table :deep(.el-table__cell) { padding: 8px 0; }
.att-table :deep(.el-table__row) { cursor: pointer; transition: background-color .15s ease; }
.att-table :deep(.el-table__row--striped td.el-table__cell) { background: light-dark(#fafbfc, var(--app-surface-2)); }
.att-table :deep(.el-table__row:hover > td.el-table__cell) { background: rgba(15,118,110,.06) !important; }
.att-table :deep(.tbl-header th.el-table__cell) {
  background: light-dark(#f8fafc, var(--app-surface-2)) !important;
  color: light-dark(#475569, var(--text-secondary)); font-weight: 600; font-size: 12px;
  border-bottom: 1px solid light-dark(#e2e8f0, var(--border-color));
}
.att-table :deep(.el-table__header th.el-table__cell > .cell) { line-height: 1.3; }

.cell-name { font-weight: 700; color: light-dark(#0f172a, var(--text-primary)); }
.cell-empty { color: light-dark(#cbd5e1, var(--text-secondary)); }
.num-main { font-weight: 600; color: light-dark(#0f766e, var(--text-accent)); font-variant-numeric: tabular-nums; }
.num-bad { color: light-dark(#dc2626, #f87171); font-weight: 600; font-variant-numeric: tabular-nums; }
.num-ok { color: light-dark(#16a34a, #6ee7b7); font-weight: 600; font-variant-numeric: tabular-nums; }
.num-total { color: light-dark(#0f172a, var(--text-primary)); font-weight: 800; font-variant-numeric: tabular-nums; }

.punch { display: flex; align-items: center; gap: 6px; }
.punch-time { font-weight: 600; color: light-dark(#334155, var(--text-primary)); font-variant-numeric: tabular-nums; }

/* Drawer */
.person-desc { margin-bottom: 4px; }
h4 { margin: 18px 0 10px; font-size: 14px; color: light-dark(#334155, var(--text-primary)); }
</style>
