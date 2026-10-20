<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElCard, ElEmpty, ElOption, ElSelect } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import {
  GridComponent, LegendComponent, TooltipComponent,
} from 'echarts/components'
import request from '../../utils/request'

use([CanvasRenderer, BarChart, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent])

const overview = ref<any>(null)
const flow = ref<any>(null)
const contractEmployees = ref<any[]>([])
const loading = ref(true)
const company = ref('')

const loadAll = async () => {
  loading.value = true
  try {
    const params = company.value ? { company: company.value } : {}
    const [o, f, r] = await Promise.all([
      request.get('/hr/dashboard/overview', { params }) as Promise<any>,
      request.get('/hr/dashboard/flow', { params }) as Promise<any>,
      request.get('/hr/dashboard/reminders', { params }) as Promise<any>,
    ])
    overview.value = o
    flow.value = f
    contractEmployees.value = r.contract_expiry_employees || []
  } finally {
    loading.value = false
  }
}

// 通用渐变填充（顶部亮 → 底部深）
const grad = (top: string, bottom: string) => ({
  type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
  colorStops: [
    { offset: 0, color: top },
    { offset: 1, color: bottom },
  ],
})

// 部门环形图：13 部门主题渐变配色 + 中心数据 + 底部换行图例
const DEPT_PALETTE: [string, string][] = [
  ['#0f766e', '#14b8a6'], ['#14b8a6', '#5eead4'],
  ['#f59e0b', '#fbbf24'], ['#e11d48', '#fb7185'],
  ['#8b5cf6', '#a78bfa'], ['#3b82f6', '#60a5fa'],
  ['#06b6d4', '#22d3ee'], ['#ec4899', '#f472b6'],
  ['#84cc16', '#a3e635'], ['#f97316', '#fb923c'],
  ['#6366f1', '#818cf8'], ['#10b981', '#34d399'],
  ['#0ea5e9', '#38bdf8'],
]

const deptOption = computed(() => {
  const struct = overview.value?.dept_structure || []
  const total = struct.reduce((s: number, d: any) => s + (d.cnt || 0), 0)
  return {
    tooltip: { trigger: 'item', formatter: '{b}：{c} 人（{d}%）' },
    legend: {
      bottom: 4, icon: 'circle',
      itemWidth: 10, itemHeight: 10, itemGap: 8,
      textStyle: { fontSize: 13, color: '#334155' },
      formatter: (name: string) => name.length > 6 ? name.slice(0, 6) + '…' : name,
    },
    graphic: [{
      type: 'text', left: 'center', top: '44%',
      style: {
        text: `${total}\n人在职`,
        textAlign: 'center', fontSize: 20, fontWeight: 800,
        fill: '#0f766e', lineHeight: 24,
      },
    }],
    series: [{
      type: 'pie', radius: ['40%', '66%'], center: ['50%', '44%'],
      avoidLabelOverlap: true,
      label: { show: false }, labelLine: { show: false },
      itemStyle: { borderColor: '#ffffff', borderWidth: 2, borderRadius: 4 },
      data: struct.map((d: any, i: number) => {
        const c = DEPT_PALETTE[i % DEPT_PALETTE.length]
        return { name: d.dept_name, value: d.cnt, itemStyle: { color: grad(c[0], c[1]) } }
      }),
    }],
  }
})

// 司龄分布：渐变柱 + 数值 label + 圆角顶部
const tenureOption = computed(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { left: 40, right: 24, top: 32, bottom: 30, containLabel: true },
  xAxis: {
    type: 'category',
    data: (overview.value?.tenure_structure || []).map((t: any) => t.bucket),
    axisLine: { lineStyle: { color: '#cbd5e1' } },
    axisTick: { show: false },
    axisLabel: { color: '#64748b', fontSize: 12 },
  },
  yAxis: {
    type: 'value',
    splitLine: { lineStyle: { color: '#e2e8f0', type: 'dashed' } },
    axisLabel: { color: '#94a3b8' },
  },
  series: [{
    type: 'bar', barWidth: '52%',
    data: (overview.value?.tenure_structure || []).map((t: any) => t.cnt),
    itemStyle: { color: grad('#14b8a6', '#0f766e'), borderRadius: [8, 8, 0, 0] },
    label: { show: true, position: 'top', color: '#334155', fontSize: 12, fontWeight: 700 },
  }],
}))

// 学历分布
const eduOption = computed(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { left: 40, right: 24, top: 32, bottom: 30, containLabel: true },
  xAxis: {
    type: 'category',
    data: (overview.value?.education_structure || []).map((e: any) => e.education || '未填写'),
    axisLine: { lineStyle: { color: '#cbd5e1' } },
    axisTick: { show: false },
    axisLabel: { color: '#64748b', fontSize: 12, interval: 0 },
  },
  yAxis: { type: 'value', splitLine: { lineStyle: { color: '#e2e8f0', type: 'dashed' } }, axisLabel: { color: '#94a3b8' } },
  series: [{
    type: 'bar', barWidth: '52%',
    data: (overview.value?.education_structure || []).map((e: any) => e.cnt),
    itemStyle: { color: grad('#5eead4', '#0d9488'), borderRadius: [8, 8, 0, 0] },
    label: { show: true, position: 'top', color: '#334155', fontSize: 12, fontWeight: 700 },
  }],
}))

// 入职-离职趋势：渐变面积填充 + marker
const trendOption = computed(() => {
  const s = flow.value?.series || []
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['入职', '离职'], top: 8, textStyle: { color: '#475569' }, icon: 'roundRect' },
    grid: { left: 40, right: 24, top: 44, bottom: 30, containLabel: true },
    xAxis: {
      type: 'category',
      data: s.map((x: any) => x.month),
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#cbd5e1' } }, axisTick: { show: false },
      axisLabel: { color: '#94a3b8', fontSize: 11 },
    },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#e2e8f0', type: 'dashed' } }, axisLabel: { color: '#94a3b8' } },
    series: [
      {
        name: '入职', type: 'line', smooth: true, symbol: 'circle', symbolSize: 7,
        data: s.map((x: any) => x.hires),
        lineStyle: { color: '#0f766e', width: 2.5 },
        itemStyle: { color: '#0f766e', borderColor: '#fff', borderWidth: 1.5 },
        areaStyle: { color: grad('rgba(15,118,110,0.42)', 'rgba(15,118,110,0.02)') },
      },
      {
        name: '离职', type: 'line', smooth: true, symbol: 'circle', symbolSize: 7,
        data: s.map((x: any) => x.resigns),
        lineStyle: { color: '#e11d48', width: 2.5 },
        itemStyle: { color: '#e11d48', borderColor: '#fff', borderWidth: 1.5 },
        areaStyle: { color: grad('rgba(225,29,72,0.38)', 'rgba(225,29,72,0.02)') },
      },
    ],
  }
})

// 离职原因 Top：前 3 名警示渐变（红/橙），后 7 名灰色
const reasonOption = computed(() => {
  const reasons = flow.value?.top_reasons || []
  // 强调色：红 > 橙 > 黄；其余灰色
  const EMPHASIS: [string, string][] = [
    ['#ef4444', '#fca5a5'],
    ['#f59e0b', '#fbbf24'],
    ['#eab308', '#facc15'],
  ]
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 130, right: 32, top: 16, bottom: 16, containLabel: true },
    xAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#e2e8f0', type: 'dashed' } },
      axisLabel: { color: '#94a3b8' },
    },
    yAxis: {
      type: 'category', inverse: true,
      data: reasons.map((r: any) => r.resign_reason || '(未填写原因)'),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: '#475569', fontSize: 12 },
    },
    series: [{
      type: 'bar', barWidth: '60%',
      data: reasons.map((r: any, i: number) => {
        if (i < 3) {
          const c = EMPHASIS[i]
          return { value: r.cnt, itemStyle: { color: grad(c[0], c[1]), borderRadius: [0, 6, 6, 0] } }
        }
        return { value: r.cnt, itemStyle: { color: grad('#cbd5e1', '#94a3b8'), borderRadius: [0, 6, 6, 0] } }
      }),
      label: { show: true, position: 'right', color: '#334155', fontSize: 12, fontWeight: 700 },
    }],
  }
})

// 合同到期分布：已改为提醒卡片形式（contract-list），不再使用柱图
// （旧 contractOption 已删除）

// 4 个 KPI + sparkline（最近 6 月入职或离职趋势）
type KpiItem = {
  label: string
  value: string | number
  sparkData: number[]
  sparkTop: string
  sparkBottom: string
  hint?: string
}

const kpis = computed<KpiItem[]>(() => {
  const series = (flow.value?.series || []).slice(-6)
  const f = flow.value
  const o = overview.value
  return [
    {
      label: '在职员工',
      value: o?.active ?? '—',
      sparkData: series.map((s: any) => s.hires),
      sparkTop: 'rgba(15,118,110,0.55)',
      sparkBottom: 'rgba(15,118,110,0.02)',
      hint: '当前在册',
    },
    {
      label: '本月入职',
      value: o?.hired_this_month ?? '—',
      sparkData: series.map((s: any) => s.hires),
      sparkTop: 'rgba(20,184,166,0.55)',
      sparkBottom: 'rgba(20,184,166,0.02)',
      hint: '本月新增',
    },
    {
      label: '近12月离职',
      value: f?.total_resigns ?? '—',
      sparkData: series.map((s: any) => s.resigns),
      sparkTop: 'rgba(225,29,72,0.55)',
      sparkBottom: 'rgba(225,29,72,0.02)',
      hint: '近 12 月',
    },
    {
      label: '试用期离职占比',
      value: f ? ((f.probation_resign_rate || 0) * 100).toFixed(0) + '%' : '—',
      sparkData: series.map((s: any) => s.resigns),
      sparkTop: 'rgba(245,158,11,0.55)',
      sparkBottom: 'rgba(245,158,11,0.02)',
      hint: '离职中试用期占比',
    },
  ]
})

// 通用 sparkline 配置
const sparkOption = (k: KpiItem) => ({
  grid: { left: 0, right: 0, top: 4, bottom: 0 },
  xAxis: { type: 'category', show: false, data: k.sparkData.map((_, i) => i) },
  yAxis: { type: 'value', show: false, scale: true },
  tooltip: { show: false },
  series: [{
    type: 'line', smooth: true, symbol: 'none',
    data: k.sparkData,
    lineStyle: { width: 2 },
    areaStyle: { color: grad(k.sparkTop, k.sparkBottom) },
  }],
})

onMounted(loadAll)
</script>

<template>
  <div class="hr-driver" v-loading="loading">
    <div class="driver-toolbar">
      <span class="toolbar-label">统计范围：</span>
      <el-select v-model="company" class="company-select" style="width: 210px" @change="loadAll">
        <el-option label="全部公司（汇总）" value="" />
        <el-option label="示例科技（现公司）" value="示例科技" />
        <el-option label="示例传媒（分公司）" value="示例传媒" />
      </el-select>
      <span class="toolbar-hint">切换后，上方 KPI、组织结构、趋势、提醒均按所选公司统计</span>
    </div>

    <div class="kpis">
      <el-card v-for="(k, i) in kpis" :key="i" shadow="never" class="kpi" :body-style="{ padding: '0' }">
        <div class="kpi-row">
          <div class="kpi-text">
            <div class="kpi-label">{{ k.label }}</div>
            <div class="kpi-value">{{ k.value }}</div>
            <div v-if="k.hint" class="kpi-hint">{{ k.hint }}</div>
          </div>
          <v-chart v-if="k.sparkData.length" :option="sparkOption(k)" class="kpi-spark" autoresize />
        </div>
      </el-card>
    </div>

    <div class="grid">
      <el-card shadow="never" class="chart-card">
        <template #header><span class="card-title">👥 部门人员结构</span></template>
        <v-chart v-if="overview?.dept_structure?.length" :option="deptOption" class="chart-fill" autoresize />
        <el-empty v-else class="empty-fill" description="暂无数据" />
      </el-card>
      <el-card shadow="never" class="chart-card">
        <template #header><span class="card-title">⏳ 司龄分布</span></template>
        <v-chart v-if="overview?.tenure_structure?.length" :option="tenureOption" class="chart-fill" autoresize />
        <el-empty v-else class="empty-fill" description="暂无数据" />
      </el-card>
      <el-card shadow="never" class="chart-card">
        <template #header><span class="card-title">🎓 学历分布</span></template>
        <v-chart v-if="overview?.education_structure?.length" :option="eduOption" class="chart-fill" autoresize />
        <el-empty v-else class="empty-fill" description="暂无数据" />
      </el-card>
      <el-card shadow="never" class="chart-card">
        <template #header><span class="card-title">📈 入职-离职趋势（近12月）</span></template>
        <v-chart v-if="flow?.series?.length" :option="trendOption" class="chart-fill" autoresize />
        <el-empty v-else class="empty-fill" description="暂无数据" />
      </el-card>
      <el-card shadow="never" class="chart-card">
        <template #header><span class="card-title">🚪 离职原因 Top</span></template>
        <v-chart v-if="flow?.top_reasons?.length" :option="reasonOption" class="chart-fill" autoresize />
        <el-empty v-else class="empty-fill" description="暂无数据" />
      </el-card>
      <el-card shadow="never" class="chart-card">
        <template #header>
          <div class="card-head-row">
            <span class="card-title">📅 合同到期提醒（未来90天）</span>
            <el-tag v-if="contractEmployees.length" size="small" type="danger" effect="dark">{{ contractEmployees.length }} 人</el-tag>
          </div>
        </template>
        <div v-if="contractEmployees.length" class="contract-list">
          <div v-for="(c, idx) in contractEmployees" :key="c.id + '-' + c.seq_no" class="contract-row">
            <span class="cr-no">{{ idx + 1 }}.</span>
            <span class="cr-name">{{ c.name }}</span>
            <span class="cr-dept">{{ c.dept }}</span>
            <el-tag size="small" effect="plain" :type="c.seq_no === 1 ? 'primary' : 'info'">
              {{ c.seq_no === 1 ? '首次合同' : c.seq_no === 2 ? '二次续签' : c.seq_no === 3 ? '三次续签' : '续签' }}
            </el-tag>
            <span class="cr-date">{{ c.end_date }}</span>
            <el-tag size="small" :type="c.level === 'danger' ? 'danger' : 'warning'" effect="dark">
              剩 {{ c.days_left }} 天
            </el-tag>
          </div>
        </div>
        <div v-else class="contract-empty">
          <el-empty description="未来 90 天无合同到期，状态平稳" />
        </div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.hr-driver { padding: 18px 22px; }

.driver-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  padding: 10px 14px;
  background: light-dark(#fff, var(--app-surface));
  border: 1px solid light-dark(#e2e8f0, var(--border-color));
  border-radius: 10px;
  flex-wrap: wrap;
}
.toolbar-label {
  font-size: 13px;
  font-weight: 700;
  color: light-dark(#334155, var(--text-primary));
}
.toolbar-hint {
  font-size: 12px;
  color: light-dark(#94a3b8, var(--text-secondary));
}
.hr-driver :deep(.el-card) { border: 1px solid light-dark(#e2e8f0, var(--border-color)); box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); transition: box-shadow .2s ease, transform .2s ease; }
.hr-driver :deep(.el-card:hover) { box-shadow: 0 6px 16px rgba(15, 23, 42, 0.06); }

/* === 顶部 KPI（4 列）— 渐变背景 + 迷你 sparkline === */
.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 18px; }
.kpi { position: relative; overflow: hidden; }
.kpi-row { display: flex; align-items: center; justify-content: space-between; padding: 18px 20px; gap: 14px; }
.kpi-text { flex: 1; min-width: 0; }
.kpi-label { color: light-dark(#64748b, var(--text-secondary)); font-size: 13px; font-weight: 600; letter-spacing: .02em; }
.kpi-value { font-size: 30px; font-weight: 800; color: light-dark(#0f172a, var(--text-primary)); line-height: 1.2; margin-top: 6px; }
.kpi-hint { color: light-dark(#94a3b8, var(--text-secondary)); font-size: 12px; margin-top: 2px; }
.kpi-spark { width: 96px; height: 44px; flex-shrink: 0; }

/* 各 KPI 背景渐变 + 左侧色条 */
.kpi:nth-child(1) { background: linear-gradient(135deg, light-dark(#ecfdf5, var(--primary-surface-2)) 0%, light-dark(#ffffff, var(--app-surface)) 80%); }
.kpi:nth-child(2) { background: linear-gradient(135deg, light-dark(#f0fdfa, var(--primary-surface-2)) 0%, light-dark(#ffffff, var(--app-surface)) 80%); }
.kpi:nth-child(3) { background: linear-gradient(135deg, light-dark(#fff1f2, rgba(248, 113, 113, .12)) 0%, light-dark(#ffffff, var(--app-surface)) 80%); }
.kpi:nth-child(4) { background: linear-gradient(135deg, light-dark(#fffbeb, rgba(251, 191, 36, .12)) 0%, light-dark(#ffffff, var(--app-surface)) 80%); }
.kpi::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; }
.kpi:nth-child(1)::before { background: #0f766e; }
.kpi:nth-child(2)::before { background: #14b8a6; }
.kpi:nth-child(3)::before { background: #e11d48; }
.kpi:nth-child(4)::before { background: #f59e0b; }

/* === 图表卡片：等高布局 + 标题图标 === */
.grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; align-items: stretch; }
.chart-card :deep(.el-card__header) { padding: 16px 20px 8px; border-bottom: none; background: linear-gradient(180deg, light-dark(#f8fafc, var(--app-surface)) 0%, transparent 100%); }
.card-title { font-size: 14px; font-weight: 700; color: light-dark(#334155, var(--text-primary)); letter-spacing: .02em; }

.grid :deep(.el-card) { display: flex; flex-direction: column; height: 100%; }
.grid :deep(.el-card__body) { flex: 1; display: flex; flex-direction: column; min-height: 0; padding: 8px 14px 16px; }
.chart-fill { flex: 1; width: 100%; min-height: 240px; }
.empty-fill { flex: 1; }

/* === 合同到期提醒列表 === */
.card-head-row { display: flex; align-items: center; justify-content: space-between; }
.contract-list { padding: 4px 4px 6px; display: flex; flex-direction: column; gap: 4px; }
.contract-row {
  display: grid;
  grid-template-columns: 24px 92px 1fr auto 110px auto;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  background: light-dark(#f8fafc, var(--app-surface-2));
  font-size: 13px;
  transition: background .15s ease;
}
.contract-row:hover { background: light-dark(#f1f5f9, var(--app-surface-2)); }
.cr-no { color: light-dark(#94a3b8, var(--text-secondary)); font-weight: 700; }
.cr-name { font-weight: 700; color: light-dark(#0f172a, var(--text-primary)); }
.cr-dept { color: light-dark(#64748b, var(--text-secondary)); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cr-date { color: light-dark(#475569, var(--text-secondary)); font-variant-numeric: tabular-nums; font-size: 13px; }
.contract-empty { flex: 1; display: flex; align-items: center; justify-content: center; }

@media (max-width: 1100px) { .kpis { grid-template-columns: repeat(2, 1fr); } .grid { grid-template-columns: 1fr; } }
</style>
