export type OperatingData = Record<string, any>
export type OperatingFilters = { range: string[]; keyword: string; brand: string; metric: string }
export const chartColors = ['#0f766e', '#3b82f6', '#8b5cf6', '#f59e0b', '#06b6d4', '#ec4899', '#94a3b8']
export const compactNumber = (value: number) => Math.abs(value) >= 10000 ? `${(value / 10000).toFixed(1)}万` : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
export const shortLabel = (value: string, size = 24) => value.length > size ? `${value.slice(0, size)}…` : value
export const metricUnit = (metric: string) => ['revenue', 'cart_amount'].includes(metric) ? '元' : ['quantity', 'cart_quantity'].includes(metric) ? '件' : metric === 'orders' ? '单' : ['customers', 'visitors', 'cart_customers'].includes(metric) ? '人次' : '次'

export function trendOption(evidence: OperatingData | null, label: string) {
  const metric = evidence?.filters.metric || 'revenue'
  return { color: chartColors, tooltip: { trigger: 'axis', renderMode: 'richText' },
    grid: { left: 76, right: 30, top: 45, bottom: 75 },
    xAxis: { type: 'category', boundaryGap: false, data: evidence?.trend.map((r: OperatingData) => r.day) || [], axisLabel: { color: '#64748b', formatter: (v: string) => v.slice(5) }, axisLine: { lineStyle: { color: '#e2e8f0' } } },
    yAxis: { type: 'value', name: metricUnit(metric), axisLabel: { color: '#64748b', formatter: compactNumber }, splitLine: { lineStyle: { color: '#edf2f7', type: 'dashed' } } },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 15, borderColor: 'transparent', fillerColor: '#0f766e15' }],
    series: [{ name: label, type: 'line', showSymbol: false, lineStyle: { width: 3 }, areaStyle: { opacity: .09 }, data: evidence?.trend.map((r: OperatingData) => r[metric]) || [] }] }
}

export function rankingOption(rows: OperatingData[], metric: string, label: string, group = 'sku', limit = 10) {
  const shown = rows.slice(0, limit)
  const isSku = group === 'sku'
  const isModel = group === 'model'
  return { tooltip: { trigger: 'axis', renderMode: 'richText', axisPointer: { type: 'shadow' } },
    grid: { left: isSku ? 235 : isModel ? 180 : 115, right: 86, top: 25, bottom: 40 },
    xAxis: { type: 'value', name: metricUnit(metric), axisLabel: { formatter: compactNumber, color: '#64748b' }, splitLine: { lineStyle: { color: '#edf2f7', type: 'dashed' } } },
    yAxis: { type: 'category', inverse: true, data: shown.map(r => isSku ? `${r.name || r.label}\n${r.code || r.label}` : r.label || (isModel ? '未匹配型号' : '未分类')),
      axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#334155', lineHeight: 19, formatter: (v: string) => v.split('\n').map((s, i) => shortLabel(s, i ? 24 : 17)).join('\n') } },
    series: [{ name: label, type: 'bar', barMaxWidth: 24, label: { show: true, position: 'right', color: '#334155', formatter: (p: OperatingData) => compactNumber(p.value) },
      data: shown.map((r, i) => ({ value: r.value, itemStyle: { color: i === 0 ? '#0f766e' : i < 3 ? '#14b8a6' : '#93c5fd', borderRadius: [0, 5, 5, 0] } })) }] }
}

export function categoryOption(rows: OperatingData[]) {
  const positive = rows.filter(r => r.value > 0)
  const total = positive.reduce((sum, r) => sum + r.value, 0)
  const entries = positive.slice(0, 6).map(r => ({ name: r.label || '未分类', value: r.value }))
  const rest = positive.slice(6).reduce((sum, r) => sum + r.value, 0)
  if (rest) entries.push({ name: '其他类目', value: rest })
  return { color: chartColors, tooltip: { trigger: 'item', renderMode: 'richText', formatter: '{b}\n{c}（{d}%）' },
    legend: { bottom: 0, type: 'scroll', textStyle: { color: '#64748b' } },
    graphic: [{ type: 'text', left: 'center', top: '40%', style: { text: compactNumber(total), fill: '#0f172a', fontSize: 25, fontWeight: 700 } },
      { type: 'text', left: 'center', top: '51%', style: { text: '正值贡献合计', fill: '#64748b', fontSize: 12 } }],
    series: [{ type: 'pie', radius: ['48%', '70%'], center: ['50%', '45%'], itemStyle: { borderColor: '#fff', borderWidth: 3, borderRadius: 5 },
      label: { show: false }, emphasis: { label: { show: false }, scaleSize: 6 }, data: entries }] }
}

export function comparisonOption(evidence: OperatingData, label: string) {
  const metric = evidence.filters.metric
  return { tooltip: { trigger: 'axis', renderMode: 'richText' }, grid: { left: 65, right: 25, top: 30, bottom: 40 },
    xAxis: { type: 'category', data: ['本期', '去年同期', '上月同期'], axisLine: { lineStyle: { color: '#e2e8f0' } } },
    yAxis: { type: 'value', name: metricUnit(metric), axisLabel: { formatter: compactNumber }, splitLine: { lineStyle: { color: '#edf2f7', type: 'dashed' } } },
    series: [{ name: label, type: 'bar', barMaxWidth: 44, label: { show: true, position: 'top', formatter: (p: OperatingData) => compactNumber(p.value) },
      data: [ { value: evidence.summary[metric], itemStyle: { color: '#0f766e', borderRadius: [5, 5, 0, 0] } },
        ...['yoy', 'mom'].map((key, i) => ({ value: evidence.comparisons[key].coverage.available_days ? evidence.comparisons[key].summary[metric] : null,
          itemStyle: { color: evidence.comparisons[key].coverage.complete ? chartColors[i + 1] : '#cbd5e1', borderRadius: [5, 5, 0, 0] } }))] }] }
}
