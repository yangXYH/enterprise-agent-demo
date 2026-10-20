<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElButton, ElEmpty, ElOption, ElSelect, ElTable, ElTableColumn, ElTag } from 'element-plus'

type Shop = { channel: string; shop_id: string; shop_name: string; months: string[] }
type ReportRow = Record<string, any> & {
  channel: string
  shop_id: string
  month: string
  revenue: number | null
  costG: number | null
  gross_profit: number | null
  total_fees: number | null
  product_profit: number | null
  net_profit: number | null
  data_status?: string
  data_note?: string
  expense_only?: boolean
  missing_cost?: boolean
  missing_fees?: boolean
  cost_estimated?: boolean
  estimated_cost_count?: number
  estimated_cost_amount?: number
  known_fee_keys?: string[]
  profit_provisional?: boolean
  sales_source?: string
  source_conflict?: boolean
  known_total_fees?: number
  settlement_fee_breakdown?: { key: string; parent_key: string; label: string; amount: number }[]
}
type Payload = { source?: Record<string, any>; months: string[]; shops: Shop[]; rows: ReportRow[] }

const props = defineProps<{ data: Payload | null; shopKey: string; error: string }>()
const emit = defineEmits<{ 'choose-shop': [key: string]; retry: [] }>()
const month = ref('')
const includeZero = ref(false)

const keyOf = (shop: Shop) => `${shop.channel}:${shop.shop_id}`
const selectedShop = computed(() => props.data?.shops.find(shop => keyOf(shop) === props.shopKey) || props.data?.shops[0])
const shopRows = computed(() => (props.data?.rows || [])
  .filter(row => row.has_data && row.channel === selectedShop.value?.channel && row.shop_id === selectedShop.value?.shop_id)
  .sort((a, b) => b.month.localeCompare(a.month)))
const monthsAsc = computed(() => [...shopRows.value].sort((a, b) => a.month.localeCompare(b.month)))
const singleYear = computed(() => new Set(monthsAsc.value.map(r => r.month.slice(0, 4))).size <= 1)
const monthShort = (value: string) => {
  const [y, m] = value.split('-')
  return singleYear.value ? `${Number(m)}月` : `${y.slice(2)}年${Number(m)}月`
}
const activeRow = computed(() => shopRows.value.find(row => row.month === month.value) || null)
const shopLabel = (shop: Shop) => `${shop.channel === 'self' ? '京东自营' : shop.channel === 'pop' ? 'POP' : '线下'} · ${shop.shop_name}`

watch([() => props.shopKey, () => props.data], () => {
  const withRevenue = shopRows.value.find(row => Number(row.revenue) !== 0 && !row.expense_only)
  month.value = (withRevenue || shopRows.value[0])?.month || ''
}, { immediate: true })

const feeDefinitions = [
  ['promo', '推广费'], ['maobaoFee', '毛保金额'], ['brand_rebate', '广告费返款'],
  ['virtual_income', '云朵交易服务费'], ['tcFwd', 'TC正向转运费'], ['tcRev', 'TC逆向转运费'],
  ['storage', '京东仓储费'], ['storageHd', '花都仓储费'], ['express', '京东快递费'],
  ['expressHd', '第三方快递费'], ['baitiao', '白条'], ['promoService', '促销服务费'],
  ['crossRegion', '平行库存补贴'], ['transRebate', '优惠券 / 红包 / 补贴'],
  ['afterSale', '售后赔付'], ['commission', '佣金'], ['platform', '平台服务费'],
  ['transFee', '交易服务费'], ['shipInsure', '运费保险'], ['prodInsure', '商品保险'],
  ['jdBeans', '京豆成本'], ['penalty', '违约金'], ['deliveryIncome', '配送费收入（抵减）'],
  ['priceRebate', '价保返佣（抵减）'], ['tax', '模拟税金'], ['rent', '租金杂费'],
  ['capital', '资金成本'], ['labor', '人工'], ['rentAlloc', '房租分摊'],
] as const

const feeCards = computed(() => {
  const row = activeRow.value
  if (!row) return []
  const cards: { key: string; label: string; value: number; ratio: string; note?: string }[] = []
  const knownFees = row.missing_fees ? new Set(row.known_fee_keys || []) : null
  for (const [key, defaultLabel] of feeDefinitions) {
    const label = row.fee_labels?.[key] || defaultLabel
    if (knownFees && !knownFees.has(key)) continue
    const breakdowns = (row.settlement_fee_breakdown || []).filter(item => item.parent_key === key)
    for (const item of breakdowns) {
      if (includeZero.value || Math.abs(item.amount) >= 0.005) cards.push({
        key: item.key, label: item.label, value: item.amount, ratio: rate(Math.abs(item.amount), row.revenue),
      })
    }
    const value = Number(row[key] || 0) - breakdowns.reduce((total, item) => total + item.amount, 0)
    if (!includeZero.value && Math.abs(value) < 0.005) continue
    if (key === 'storage' && (Number(row.storageGen || 0) || Number(row.storageCons || 0))) {
      const generic = Number(row.storageGen || 0)
      const consumable = Number(row.storageCons || 0)
      const other = value - generic - consumable
      for (const [subKey, subLabel, subValue] of [
        ['storageGen', '仓储服务费（通用）', generic],
        ['storageCons', '仓储服务费（耗材）', consumable],
        ['storageOther', '其他京东仓储费', other],
      ] as const) {
        if (includeZero.value || Math.abs(subValue) >= 0.005) cards.push({
          key: subKey, label: subLabel, value: subValue, ratio: rate(Math.abs(subValue), row.revenue),
        })
      }
      continue
    }
    cards.push({
      key, label, value, ratio: rate(Math.abs(value), row.revenue),
      note: key === 'brand_rebate' && value !== 0 ? '源报表将此金额计入费用合计，返款符号待核对。' : undefined,
    })
  }
  return cards
})

const money = (value: number | null | undefined) => value == null || !Number.isFinite(Number(value))
  ? '—'
  : `¥${Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const effectMoney = (value: number | null | undefined) => value == null
  ? '—'
  : `${Number(value) > 0 ? '+' : Number(value) < 0 ? '−' : ''}${money(Math.abs(Number(value)))}`
const expenseEffect = (value: number) => effectMoney(-value)
const statusText = (row: any) => row.expense_only ? '收入待补'
  : row.source_conflict ? '收入来源待核对'
  : row.missing_cost && row.missing_fees ? '成本、费用待补'
  : row.missing_cost ? '成本待补'
  : row.cost_estimated && row.missing_fees ? '成本暂估 · 费用待补'
  : row.cost_estimated ? '成本均价暂估'
  : row.missing_fees ? '净利暂估 · 费用待补'
  : row.profit_provisional || row.data_status === 'partial' ? '利润暂估' : '已录数据'
const monthLabel = (value: string) => {
  const [year, m] = value.split('-')
  return `${year}年${Number(m)}月`
}
const rate = (part: number | null | undefined, total: number | null | undefined) => part == null || total == null || total <= 0
  ? '—' : `${(part / total * 100).toFixed(1)}%`

const coreCards = computed(() => {
  const row = activeRow.value
  if (!row) return []
  return [
    { key: 'net', label: '项目净利', value: row.net_profit, share: rate(row.net_profit, row.revenue), description: row.source_conflict ? '收入来源冲突，暂不计算' : row.expense_only ? '收入和成本待补' : row.missing_cost ? '产品成本未齐，暂不计算' : row.cost_estimated ? `含均价暂估成本${row.missing_fees ? ' · 费用待补' : ''} · 未计人工` : row.missing_fees ? '按已录费用暂估 · 费用待补 · 未计人工' : row.profit_provisional ? '沿用已录费用口径暂估 · 未计人工' : '未计人工' },
    { key: 'revenue', label: '收入', value: row.expense_only ? null : row.revenue, share: null, description: row.source_conflict ? '沿用原来源金额，结算单差异待核对' : row.source_kind === 'project_profit' ? '月度利润表结算账单收入' : row.sales_source ? '按销售明细表汇总' : row.channel === 'self' ? '京东结算金额，毛保单列扣除' : '当前店铺结算收入' },
    { key: 'cost', label: '产品成本', value: row.missing_cost && !Number(row.costG) ? null : row.costG, share: row.missing_cost && !Number(row.costG) ? '—' : rate(Math.abs(Number(row.costG || 0)), row.revenue), description: row.missing_cost ? '仅含已匹配 SKU 的成本' : row.cost_estimated ? `含${row.estimated_cost_count}个SKU均价暂估 ${money(row.estimated_cost_amount)}` : row.source_kind === 'project_profit' ? '月度利润表账单产品成本' : '按净销量 × 单位成本' },
    { key: 'gross', label: '毛利', value: row.expense_only ? null : row.gross_profit, share: rate(row.gross_profit, row.revenue), description: row.source_conflict ? '收入来源冲突，暂不计算' : row.missing_cost ? '产品成本未齐，暂不计算' : row.cost_estimated ? '收入 − 产品成本（含均价暂估）' : row.gross_adjustment ? '收入 − 产品成本 − 返利及种菜成本' : '收入 − 产品成本' },
  ]
})

function chooseShop(key: string) { emit('choose-shop', key) }
</script>

<template>
  <section class="shop-report-page">
    <header class="page-heading">
      <div>
        <span class="eyebrow">店铺报表 / 费用明细</span>
        <h1>{{ selectedShop ? shopLabel(selectedShop) : '店铺报表' }}</h1>
        <p>按店铺、按业务月份查看收入、成本、毛利、费用与项目净利。</p>
      </div>
      <div class="heading-controls">
        <el-select
          :model-value="selectedShop ? keyOf(selectedShop) : ''"
          aria-label="选择店铺"
          placeholder="选择店铺"
          filterable
          class="shop-select"
          @update:model-value="chooseShop"
        >
          <el-option v-for="shop in data?.shops || []" :key="keyOf(shop)" :label="shopLabel(shop)" :value="keyOf(shop)" />
        </el-select>
        <div class="month-slicer" role="group" aria-label="选择业务月份">
          <button
            v-for="row in monthsAsc"
            :key="row.month"
            type="button"
            class="month-chip"
            :class="{ active: row.month === month }"
            :title="monthLabel(row.month)"
            @click="month = row.month"
          >{{ monthShort(row.month) }}</button>
        </div>
      </div>
    </header>

    <div v-if="error" class="state-panel error-panel">
      <strong>店铺报表读取失败</strong><p>{{ error }}</p><el-button type="primary" @click="emit('retry')">重试</el-button>
    </div>
    <div v-else-if="!data" class="state-panel">正在读取店铺费用明细…</div>
    <el-empty v-else-if="!activeRow" description="该店铺尚无可展示的费用明细" />
    <template v-else>
      <div class="scope-line">
        <span>{{ monthLabel(activeRow.month) }}</span>
        <el-tag :type="activeRow.data_status === 'complete' && !activeRow.profit_provisional ? 'success' : 'warning'" effect="plain">{{ statusText(activeRow) }}</el-tag>
        <span>金额单位：元</span>
        <span>占比按当月收入计算</span>
      </div>
      <div v-if="activeRow.data_note || activeRow.expense_only || activeRow.profit_provisional || activeRow.missing_fees" class="data-note">
        <strong>{{ statusText(activeRow) }}</strong>
        <span>{{ activeRow.data_note || (activeRow.net_profit != null ? '项目净利按已录费用暂估，后续费用补齐后重算。' : '收入或产品成本待核对，暂不计算净利。') }}</span>
      </div>
      <div v-if="Number(activeRow.brand_rebate || 0) > 0" class="data-note">
        <strong>返款口径待核对</strong>
        <span>源明细将广告费返款显示为收入项，但项目净利公式把同一正数计入费用。本页按该公式计算项目净利，返款卡显示其实际扣减影响。</span>
      </div>

      <div class="core-grid">
        <article v-for="card in coreCards" :key="card.key" class="core-card" :class="[card.key, { loss: card.key === 'net' && Number(card.value) < 0 }]">
          <span class="card-label">{{ card.label }}</span>
          <strong>{{ money(card.value) }}</strong>
          <small v-if="card.share !== null">占收入 {{ card.share }}</small>
          <small>{{ card.description }}</small>
        </article>
      </div>

      <div v-if="activeRow.gross_adjustment_items?.length" class="data-note">
        <strong>毛利调整（已计入毛利）</strong>
        <span v-for="item in activeRow.gross_adjustment_items" :key="item.label">{{ item.label }}：{{ expenseEffect(item.amount) }}；不再计入费用合计。</span>
      </div>

      <div class="result-grid">
        <article class="summary-card">
          <div><span>{{ activeRow.missing_fees ? '已录费用合计' : '费用合计' }}</span><strong>{{ money(activeRow.total_fees ?? activeRow.known_total_fees) }}</strong></div>
          <small class="summary-share">占收入 {{ rate(activeRow.total_fees ?? activeRow.known_total_fees, activeRow.revenue) }}</small>
          <small>{{ activeRow.missing_fees ? '完整费用尚未导入' : activeRow.source_kind === 'project_profit' ? '人工未计入；店租已含在其他费用中' : '人工未计入；房租分摊另计' }}</small>
        </article>
        <article class="summary-card">
          <div><span>产品净利润</span><strong :class="{ negative: Number(activeRow.product_profit) < 0 }">{{ money(activeRow.product_profit) }}</strong></div>
          <small class="summary-share">占收入 {{ rate(activeRow.product_profit, activeRow.revenue) }}</small>
          <small>{{ activeRow.source_conflict ? '收入来源核对后计算' : activeRow.missing_cost ? '产品成本补齐后计算' : activeRow.missing_fees ? '毛利 − 已录费用合计（暂估）' : '毛利 − 费用合计' }}</small>
        </article>
        <article class="summary-card">
          <div><span>房租分摊影响</span><strong>{{ activeRow.rentAlloc == null ? '—' : expenseEffect(Number(activeRow.rentAlloc)) }}</strong></div>
          <small class="summary-share">占收入 {{ activeRow.rentAlloc == null ? '—' : rate(-Number(activeRow.rentAlloc), activeRow.revenue) }}</small>
          <small>{{ activeRow.rentAlloc == null ? '房租分摊待补' : activeRow.source_kind === 'project_profit' ? '店租已含在其他费用中，不再重复分摊' : '负分摊表示补贴，增加项目净利' }}</small>
        </article>
      </div>

      <section class="panel expense-section">
        <div class="section-heading">
          <div><h2>费用明细指标卡</h2><p>{{ activeRow.missing_fees ? '只显示本月已录费用；金额旁显示占当月收入比例。' : '金额旁显示占当月收入比例。正数返利或抵减显示为利润影响。' }}</p></div>
          <button type="button" class="text-button" @click="includeZero = !includeZero">{{ includeZero ? '隐藏零金额项' : '显示全部费用项' }}</button>
        </div>
        <div v-if="feeCards.length" class="fee-grid">
          <article v-for="card in feeCards" :key="card.key" class="fee-card">
            <span>{{ card.label }}</span>
            <div class="fee-card-main"><strong :class="{ credit: card.value < 0 }">{{ expenseEffect(card.value) }}</strong><small>占收入 {{ card.ratio }}</small></div>
            <small v-if="card.note">{{ card.note }}</small>
          </article>
        </div>
        <el-empty v-else :description="activeRow.missing_fees ? '本月尚无可展示的费用明细' : '本月无已录费用'" :image-size="72" />
      </section>

      <section class="panel history-section">
        <div class="section-heading"><div><h2>各月费用明细</h2><p>点击月份查看该店铺的指标卡。</p></div><span>{{ shopRows.length }} 个有数据月份</span></div>
        <el-table :data="shopRows" stripe class="history-table" @row-click="row => month = row.month">
          <el-table-column label="月份" min-width="120"><template #default="{ row }"><strong>{{ monthLabel(row.month) }}</strong></template></el-table-column>
          <el-table-column label="状态" min-width="145"><template #default="{ row }"><span :class="{ provisional: row.data_status !== 'complete' }">{{ statusText(row) }}</span></template></el-table-column>
          <el-table-column label="项目净利" min-width="150" align="right"><template #default="{ row }"><strong :class="{ negative: Number(row.net_profit) < 0 }">{{ money(row.net_profit) }}</strong></template></el-table-column>
          <el-table-column label="收入" min-width="145" align="right"><template #default="{ row }">{{ money(row.expense_only ? null : row.revenue) }}</template></el-table-column>
          <el-table-column label="产品成本" min-width="145" align="right"><template #default="{ row }">{{ money(row.missing_cost && !Number(row.costG) ? null : row.costG) }}<small v-if="row.cost_estimated">（含均价暂估）</small></template></el-table-column>
          <el-table-column label="毛利" min-width="145" align="right"><template #default="{ row }">{{ money(row.expense_only ? null : row.gross_profit) }}</template></el-table-column>
          <el-table-column label="费用合计" min-width="145" align="right"><template #default="{ row }">{{ money(row.total_fees ?? row.known_total_fees) }}<small v-if="row.missing_fees">（已录）</small></template></el-table-column>
        </el-table>
      </section>
      <p class="source-note">数据来源：{{ activeRow.sales_source || 'DEMO_BAGS 经营分析看板的店铺维度“费用明细”' }}。源库更新日期：{{ data.source?.database_modified_at?.slice(0, 10) || '未记录' }}。收入、成本和费用沿用当前月份已标注的数据口径。</p>
    </template>
  </section>
</template>

<style scoped>
.shop-report-page{padding:26px;min-height:100%;color:var(--text-primary);font-family:"Microsoft YaHei","Segoe UI",sans-serif}
.page-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin-bottom:16px}
.eyebrow{font-size:12px;font-weight:700;color:var(--text-accent);letter-spacing:.04em}
h1{font-size:28px;line-height:1.25;margin:8px 0;color:var(--text-heading)}
p{margin:0;color:var(--text-secondary);font-size:13px;line-height:1.6}
.heading-controls{display:flex;gap:10px;flex-wrap:wrap}.shop-select{width:230px}
.month-slicer{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.month-chip{border:1px solid var(--border-color);background:var(--app-surface-2);color:var(--text-secondary);border-radius:999px;padding:6px 13px;font-size:12px;font-weight:600;line-height:1.4;cursor:pointer;transition:all .15s}
.month-chip:hover{border-color:var(--text-accent);color:var(--text-accent)}
.month-chip.active{background:var(--text-accent);border-color:var(--text-accent);color:var(--app-surface)}
.scope-line{display:flex;align-items:center;gap:12px;color:var(--text-secondary);font-size:12px;margin:18px 0 12px}
.data-note{display:flex;gap:10px;align-items:flex-start;padding:13px 16px;border:1px solid #e7c577;border-radius:10px;background:light-dark(#fffbeb,#423719);font-size:12px;line-height:1.7;margin-bottom:16px}
.data-note strong{flex:none;color:light-dark(#92400e,#fcd34d)}.data-note span{color:var(--text-primary)}
.core-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.core-card,.summary-card,.panel{background:var(--app-surface);border:1px solid var(--border-color);border-radius:14px;box-shadow:var(--shadow-sm)}
.core-card{padding:21px 20px;display:flex;flex-direction:column;gap:10px;min-height:143px}.core-card.net{background:light-dark(#ecfdf5,#113b37);border-color:light-dark(#99e3c4,#21695f)}.core-card.net.loss{background:light-dark(#fff7ed,#3f281d);border-color:light-dark(#fed7aa,#7c4628)}
.card-label{font-size:13px;color:var(--text-secondary);font-weight:600}.core-card strong{font-size:26px;color:var(--text-heading);line-height:1.25;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}.core-card.net strong{color:light-dark(#047857,#6ee7b7)}.core-card.net.loss strong{color:light-dark(#c2410c,#fdba74)}.core-card small,.summary-card small{color:var(--text-secondary);font-size:11px;line-height:1.5}
.result-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:14px 0 22px}.summary-card{padding:16px 20px}.summary-card>div{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}.summary-card span{font-size:12px;color:var(--text-secondary)}.summary-card strong{font-size:18px;font-variant-numeric:tabular-nums;color:var(--text-heading)}.summary-share{display:block;margin:-3px 0 6px;color:var(--text-accent)!important;font-weight:600}.negative{color:light-dark(#c2410c,#fb923c)!important}
.panel{padding:21px;margin:18px 0}.section-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:18px}.section-heading h2{font-size:17px;margin:0 0 5px;color:var(--text-heading)}.section-heading>span{font-size:12px;color:var(--text-secondary)}.text-button{border:0;background:none;color:var(--text-accent);font:inherit;font-size:12px;font-weight:600;cursor:pointer;padding:3px 0;white-space:nowrap}.text-button:hover{text-decoration:underline}
.fee-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:11px}.fee-card{display:flex;flex-direction:column;gap:8px;min-height:92px;background:var(--app-surface-2);border:1px solid var(--border-subtle);border-radius:10px;padding:15px}.fee-card span{font-size:12px;color:var(--text-secondary)}.fee-card-main{display:flex;align-items:baseline;justify-content:space-between;gap:8px}.fee-card strong{font-size:18px;color:var(--text-heading);font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.fee-card strong.credit{color:light-dark(#047857,#6ee7b7)}.fee-card-main small{flex:none;color:var(--text-accent);font-size:11px;font-weight:600}.fee-card>small{font-size:11px;line-height:1.5;color:light-dark(#b45309,#fcd34d)}
.history-table{width:100%}.history-table :deep(.el-table__row){cursor:pointer}.provisional{color:light-dark(#b45309,#fcd34d)}.source-note{font-size:11px;margin:20px 2px;color:var(--text-muted)}.state-panel{background:var(--app-surface);border:1px solid var(--border-color);border-radius:12px;padding:36px;text-align:center;color:var(--text-secondary)}.error-panel strong{color:light-dark(#c2410c,#fb923c)}.error-panel p{margin:10px 0 18px}
@media(max-width:1180px){.core-grid,.fee-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:760px){.shop-report-page{padding:15px}.page-heading{align-items:stretch;flex-direction:column}.heading-controls>*{flex:1;min-width:140px}.core-grid,.result-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.fee-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:520px){.core-grid,.result-grid,.fee-grid{grid-template-columns:1fr}.section-heading{flex-direction:column}}
</style>
