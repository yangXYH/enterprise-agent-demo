import { createApp, h, ref } from 'vue'
import 'element-plus/dist/index.css'
import ShopReport from '../components/ShopReport.vue'

const element = document.getElementById('shop-report-data')
if (!element?.textContent) throw new Error('离线报表缺少数据')
const snapshot = JSON.parse(element.textContent)
const shopKey = ref(`${snapshot.shops[0].channel}:${snapshot.shops[0].shop_id}`)

const escapeCsv = (value: unknown) => {
  const text = value == null ? '' : String(value)
  return `"${text.replaceAll('"', '""')}"`
}

function downloadCsv() {
  const [channel, shopId] = shopKey.value.split(':')
  const shop = snapshot.shops.find((s: any) => s.channel === channel && s.shop_id === shopId)
  const label = `${channel === 'self' ? '京东自营' : channel === 'pop' ? 'POP' : '线下'} · ${shop.shop_name}`
  const fields = [
    ['month', '月份'], ['revenue', '收入'], ['costG', '产品成本'], ['gross_profit', '毛利'],
    ['known_total_fees', '已录费用合计'], ['net_profit', '项目净利'],
    ...snapshot.fee_keys.filter((key: string) => key !== 'labor').map((key: string) => [key, snapshot.fee_labels[key] || key]),
    ['rentAlloc', '房租分摊'], ['missing_cost', '产品成本待补'], ['missing_fees', '费用待补'],
    ['cost_estimated', '含均价暂估成本'], ['source_conflict', '收入来源冲突'], ['data_note', '数据说明'],
  ]
  const rows = snapshot.rows.filter((row: any) => row.has_data && row.channel === channel && row.shop_id === shopId)
    .sort((a: any, b: any) => a.month.localeCompare(b.month))
  const csv = '\uFEFF' + [
    ['店铺', ...fields.map((field: string[]) => field[1])],
    ...rows.map((row: any) => [label, ...fields.map((field: string[]) => row[field[0]])]),
  ].map(row => row.map(escapeCsv).join(',')).join('\r\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${label.replace(/[\\/:*?"<>|]/g, '_')}_店铺报表.csv`
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

createApp({
  setup() {
    return () => h('main', { class: 'offline-shell' }, [
      h('header', { class: 'offline-toolbar' }, [
        h('div', [
          h('strong', '店铺报表 · 离线版'),
          h('span', `数据更新：${snapshot.source.exported_at?.replace('T', ' ').slice(0, 16) || '未记录'}　·　${snapshot.shops.length}家店铺　·　未计人工`),
        ]),
        h('div', { class: 'offline-actions' }, [
          h('button', { type: 'button', onClick: downloadCsv }, '导出当前店铺 CSV'),
          h('button', { type: 'button', onClick: () => window.print() }, '打印 / 保存 PDF'),
        ]),
      ]),
      h(ShopReport, {
        data: snapshot,
        shopKey: shopKey.value,
        error: '',
        onChooseShop: (key: string) => { shopKey.value = key },
      }),
      h('footer', { class: 'offline-footer' }, '此文件包含导出时的数据快照，可断网查看。后续数据更新后，请使用新生成的离线文件。'),
    ])
  },
}).mount('#app')
