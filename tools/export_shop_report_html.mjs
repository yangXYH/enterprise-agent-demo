// Bundle the existing report and its public snapshot into one file://-safe HTML.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { createRequire } from 'node:module'
import { createHash } from 'node:crypto'
import os from 'node:os'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const frontend = path.join(root, 'frontend')
const requireFrontend = createRequire(path.join(frontend, 'package.json'))
const { build } = await import(pathToFileURL(requireFrontend.resolve('vite')).href)
const { default: vue } = await import(pathToFileURL(requireFrontend.resolve('@vitejs/plugin-vue')).href)
const args = process.argv.slice(2)
const argument = (name, fallback) => args.includes(name) ? args[args.indexOf(name) + 1] : fallback
const sourcePath = path.resolve(argument('--data', path.join(root, 'data/shop_report.json')))
const source = JSON.parse(fs.readFileSync(sourcePath, 'utf8'))
if (source.source.labor_included || source.rows.some(row => Number(row.labor || 0) !== 0)) {
  throw new Error('公开报表快照中包含人工数据，请先核对导出规则')
}

const rowFields = new Set([
  'month', 'channel', 'shop_id', 'revenue', 'costG', 'rentAlloc', 'data_status', 'data_note',
  'known_total_fees', 'total_fees', 'expense_only', 'missing_cost', 'missing_cost_count', 'missing_fees',
  'source_conflict', 'cost_estimated', 'estimated_cost_count', 'estimated_cost_amount', 'known_fee_keys',
  'settlement_fee_breakdown', 'profit_provisional', 'has_data', 'gross_profit', 'product_profit', 'net_profit',
  'source_kind', 'fee_labels', 'gross_adjustment', 'gross_adjustment_items', 'sales_source',
  'storageGen', 'storageCons', ...source.fee_keys,
])
const snapshot = {
  source: Object.fromEntries(['name', 'year', 'currency', 'labor_included', 'exported_at', 'database_modified_at', 'profit_policy']
    .map(key => [key, source.source[key]])),
  shops: source.shops,
  months: source.months,
  fee_keys: source.fee_keys,
  fee_labels: source.fee_labels,
  rows: source.rows.map(row => Object.fromEntries(Object.entries(row).filter(([key]) => rowFields.has(key)))),
}
const date = source.source.exported_at.slice(0, 10).replaceAll('-', '')
const filename = `店铺报表_离线版_${date}.html`
const output = path.resolve(argument('--output', path.join(root, `outputs/shop-report-offline-${date}`, filename)))
const result = await build({
  root: frontend,
  configFile: false,
  plugins: [vue()],
  logLevel: 'warn',
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  build: {
    write: false,
    minify: true,
    cssCodeSplit: false,
    assetsInlineLimit: Infinity,
    lib: { entry: path.join(frontend, 'src/offline/ShopReportOffline.ts'), name: 'ShopReportOffline', formats: ['iife'] },
    rolldownOptions: { output: { inlineDynamicImports: true } },
  },
})
const chunks = (Array.isArray(result) ? result : [result]).flatMap(bundle => bundle.output)
const scripts = chunks.filter(chunk => chunk.type === 'chunk')
const assets = chunks.filter(chunk => chunk.type === 'asset')
if (scripts.length !== 1 || assets.some(asset => !asset.fileName.endsWith('.css'))) {
  throw new Error('构建产生外部依赖，无法生成单文件离线版')
}
const css = assets.map(asset => String(asset.source)).join('\n')
const json = JSON.stringify(snapshot).replaceAll('<', '\\u003c').replaceAll('\u2028', '\\u2028').replaceAll('\u2029', '\\u2029')
const javascript = scripts[0].code.replace(/<\/script/gi, '<\\/script')
const html = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; object-src 'none'; base-uri 'none'">
<title>店铺报表 · 离线版</title><style>
${css}
:root{color-scheme:light;--app-bg:#f4f7fa;--app-surface:#fff;--app-surface-2:#f8fafc;--text-primary:#1f2937;--text-secondary:#64748b;--text-heading:#0f172a;--text-muted:#94a3b8;--text-accent:#0f766e;--border-color:rgba(148,163,184,.24);--border-subtle:rgba(148,163,184,.18);--shadow-sm:0 2px 8px rgba(15,23,42,.06);--el-color-primary:#0f766e;font-family:"Microsoft YaHei","Segoe UI",sans-serif;background:var(--app-bg)}
*{box-sizing:border-box}body{margin:0}.offline-shell{max-width:1540px;margin:auto}.offline-toolbar{display:flex;justify-content:space-between;align-items:center;gap:15px;padding:20px 26px 0}.offline-toolbar strong{display:block;color:#0f766e;font-size:14px}.offline-toolbar span{display:block;color:#64748b;font-size:11px;margin-top:7px}.offline-actions{display:flex;gap:8px;flex-wrap:wrap}.offline-actions button{padding:9px 13px;border-radius:8px;border:1px solid #dbe4e8;background:#fff;color:#0f766e;font:inherit;font-size:12px;cursor:pointer}.offline-actions button:hover{background:#ecfdf5}.offline-footer{color:#64748b;font-size:11px;padding:0 26px 24px;line-height:1.7}.shop-report-page{min-height:0!important}.el-table{--el-table-header-bg-color:#f8fafc;--el-table-border-color:#e8edf2}
@media(max-width:760px){.offline-toolbar{padding:16px 15px 0;align-items:flex-start;flex-direction:column}.offline-footer{padding:0 15px 20px}}
@media print{@page{size:A4 landscape;margin:10mm}body,:root{background:#fff}.offline-actions{display:none}.offline-toolbar{padding:0 15px}.shop-report-page{padding:15px!important}.core-card,.summary-card,.fee-card{break-inside:avoid;box-shadow:none!important}.data-note{break-inside:avoid}.offline-footer{padding-bottom:0}}
</style></head><body><div id="app"><noscript>请在浏览器中允许 JavaScript，以查看离线店铺报表。</noscript></div>
<script id="shop-report-data" type="application/json">${json}</script><script>${javascript}</script></body></html>`
fs.mkdirSync(path.dirname(output), { recursive: true })
fs.writeFileSync(output, html, 'utf8')
const destinations = [output]
if (args.includes('--desktop')) {
  const desktop = path.join(os.homedir(), 'Desktop', filename)
  fs.copyFileSync(output, desktop)
  destinations.push(desktop)
}
const summary = {
  outputs: destinations,
  bytes: Buffer.byteLength(html),
  shops: snapshot.shops.length,
  rows: snapshot.rows.length,
  months: snapshot.months,
  source_sha256: createHash('sha256').update(fs.readFileSync(sourcePath)).digest('hex'),
  bundled_files: scripts.length + assets.length,
  external_dependencies: false,
  protected_labor_included: false,
}
fs.writeFileSync(path.join(path.dirname(output), 'export_summary.json'), JSON.stringify(summary, null, 2) + '\n', 'utf8')
console.log(JSON.stringify(summary, null, 2))
