<script setup lang="ts">
import { computed, onActivated, onMounted, ref, watch } from 'vue'
import { ElDialog, ElMessage, ElPopconfirm } from 'element-plus'

type DesignView = 'design-overview' | 'design-models' | 'design-prompts' | 'design-comparisons' | 'design-styles' | 'design-trash'
type EditorItemType = 'models' | 'prompts' | 'comparisons' | 'styles'
type DesignItem = {
  id: string
  title: string
  text: string
  images?: string[]
  original?: string | null
  generated?: string | null
  product?: string
  scene?: string
  category?: string
  source: string
  item_type?: EditorItemType
  deleted_by?: string
  deleted_at?: string
}
type Catalog = {
  version: number
  models: DesignItem[]
  prompts: DesignItem[]
  comparisons: DesignItem[]
  styles: DesignItem[]
  sources: string[]
}
type TextPart = { text: string; bold: boolean; italic: boolean }
type DetailBlock = {
  kind: 'heading' | 'paragraph' | 'list' | 'divider' | 'table'
  level?: number
  content?: TextPart[]
  marker?: string
  depth?: number
  headers?: TextPart[][]
  rows?: TextPart[][][]
}

const props = defineProps<{ view: string; canDelete?: boolean }>()
const emit = defineEmits<{ (event: 'navigate', route: DesignView): void }>()
const catalog = ref<Catalog | null>(null)
const loading = ref(true)
const error = ref('')
const keyword = ref('')
const product = ref('')
const scene = ref('')
const category = ref('')
const page = ref(1)
const pageSize = 24
const selected = ref<DesignItem | null>(null)
const detailOpen = ref(false)
const canDelete = computed(() => props.canDelete === true)
const trashItems = ref<DesignItem[]>([])
const trashBusy = ref(false)
const editorOpen = ref(false)
const editorMode = ref<'create' | 'edit'>('create')
const editorSaving = ref(false)
const editorError = ref('')
const editingId = ref('')
const editorType = ref<EditorItemType>('models')
const editorTitle = ref('')
const editorText = ref('')
const editorProduct = ref('')
const editorScene = ref('')
const editorCategory = ref('')
const editorImages = ref<string[]>([])
const editorOriginal = ref<string | null>(null)
const editorGenerated = ref<string | null>(null)
const editorImageFiles = ref<File[]>([])
const editorOriginalFile = ref<File | null>(null)
const editorGeneratedFile = ref<File | null>(null)

let catalogRequest: Promise<Catalog> | null = null
function getCatalog(): Promise<Catalog> {
  if (!catalogRequest) {
    catalogRequest = fetch('/api/design/catalog', { credentials: 'same-origin' })
      .then(async response => {
        if (!response.ok) throw new Error(`设计资料读取失败（${response.status}）`)
        return response.json() as Promise<Catalog>
      })
      .catch(reason => { catalogRequest = null; throw reason })
  }
  return catalogRequest
}

async function loadTrash() {
  const response = await fetch('/api/design/trash', { credentials: 'same-origin', cache: 'no-store' })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || `回收站读取失败（${response.status}）`)
  trashItems.value = body.items || []
}

onMounted(async () => {
  try {
    if (props.view === 'design-trash') {
      await loadTrash()
    } else catalog.value = await getCatalog()
  }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '设计资料读取失败' }
  finally { loading.value = false }
})
let firstActivation = true
onActivated(async () => {
  if (firstActivation) { firstActivation = false; return }
  try {
    error.value = ''
    if (props.view === 'design-trash') await loadTrash()
    else { catalogRequest = null; catalog.value = await getCatalog() }
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '设计资料读取失败' }
})

watch(() => props.view, () => {
  keyword.value = ''; product.value = ''; scene.value = ''; category.value = ''; page.value = 1
})
watch([keyword, product, scene, category], () => { page.value = 1 })

const headings: Record<DesignView, { title: string; subtitle: string }> = {
  'design-overview': { title: '设计资料总览', subtitle: '从实际案例出发，快速找到图片、提示词和视觉参考。' },
  'design-models': { title: 'AI模特与场景案例', subtitle: '检索模特姿态、穿搭、商品展示和拍摄场景。' },
  'design-prompts': { title: 'AI生图提示词库', subtitle: '查看参考图，复制可复用的生图描述。' },
  'design-comparisons': { title: '生图前后对照', subtitle: '对比金宇案例中的上传图片、生成图片与描述。' },
  'design-styles': { title: '视觉要素手册', subtitle: '按身材、拍摄角度、构图、穿搭、发型等维度查看参考。' },
  'design-trash': { title: '设计资料回收站', subtitle: '查看已删除的资料，按需恢复或永久删除。' },
}
const currentView = computed<DesignView>(() => (props.view in headings ? props.view : 'design-overview') as DesignView)
const heading = computed(() => headings[currentView.value])
const allItems = computed<DesignItem[]>(() => {
  if (!catalog.value) return []
  if (currentView.value === 'design-models') return catalog.value.models
  if (currentView.value === 'design-prompts') return catalog.value.prompts
  if (currentView.value === 'design-comparisons') return catalog.value.comparisons
  if (currentView.value === 'design-styles') return catalog.value.styles
  return []
})
const products = computed(() => [...new Set(allItems.value.map(item => item.product).filter((item): item is string => !!item))].sort())
const scenes = computed(() => [...new Set(allItems.value.map(item => item.scene).filter((item): item is string => !!item))].sort())
const categories = computed(() => [...new Set(allItems.value.map(item => item.category).filter((item): item is string => !!item))])
const filtered = computed(() => {
  const search = keyword.value.trim().toLocaleLowerCase()
  return allItems.value.filter(item => {
    if (product.value && item.product !== product.value) return false
    if (scene.value && item.scene !== scene.value) return false
    if (category.value && item.category !== category.value) return false
    return !search || `${item.title} ${item.text} ${item.product || ''} ${item.scene || ''}`.toLocaleLowerCase().includes(search)
  })
})
const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize)))
const shown = computed(() => filtered.value.slice((page.value - 1) * pageSize, page.value * pageSize))
const imageFor = (item: DesignItem) => item.images?.[0] || item.generated || item.original || ''
const preview = (text: string) => text.replace(/[#*`]/g, '').replace(/\s+/g, ' ').slice(0, 180)
function textParts(value: string): TextPart[] {
  return value.split(/(\*\*[^*\n]+\*\*|\*[^*\n]+\*)/g).filter(Boolean).map(part => {
    const bold = part.startsWith('**') && part.endsWith('**')
    const italic = !bold && part.startsWith('*') && part.endsWith('*')
    return { text: bold ? part.slice(2, -2) : italic ? part.slice(1, -1) : part.replace(/\*\*/g, ''), bold, italic }
  })
}
function parseDetailText(value: string): DetailBlock[] {
  const lines = value.replace(/\r\n?/g, '\n').replace(/([。；.!?])\s+(#{1,3})\s+/g, '$1\n$2 ').split('\n')
  const blocks: DetailBlock[] = []
  let paragraph: string[] = []
  const flushParagraph = () => {
    if (paragraph.length) blocks.push({ kind: 'paragraph', content: textParts(paragraph.join('\n')) })
    paragraph = []
  }
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index].trim()
    if (!line) { flushParagraph(); continue }
    if (/^(?:-{3,}|\*{3,})$/.test(line)) {
      flushParagraph()
      blocks.push({ kind: 'divider' })
      continue
    }
    if (line.startsWith('|') && line.endsWith('|')) {
      flushParagraph()
      const tableLines: string[] = []
      while (index < lines.length && lines[index].trim().startsWith('|') && lines[index].trim().endsWith('|')) {
        tableLines.push(lines[index].trim())
        index++
      }
      index--
      const cells = tableLines.map(row => row.slice(1, -1).split('|').map(cell => cell.trim()))
      const hasHeader = cells.length > 1 && cells[1].every(cell => /^:?-{3,}:?$/.test(cell))
      blocks.push({
        kind: 'table',
        headers: hasHeader ? cells[0].map(textParts) : undefined,
        rows: (hasHeader ? cells.slice(2) : cells).map(row => row.map(textParts)),
      })
      continue
    }
    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/)
    if (headingMatch) {
      flushParagraph()
      blocks.push({ kind: 'heading', level: headingMatch[1].length, content: textParts(headingMatch[2]) })
      continue
    }
    const listMatch = lines[index].match(/^(\s*)([-*+•]|\d+[.)])\s+(.+)$/)
    if (listMatch) {
      flushParagraph()
      blocks.push({
        kind: 'list',
        marker: /^\d/.test(listMatch[2]) ? listMatch[2] : '•',
        depth: Math.min(3, Math.floor(listMatch[1].length / 2)),
        content: textParts(listMatch[3]),
      })
      continue
    }
    paragraph.push(line)
  }
  flushParagraph()
  return blocks
}
const detailBlocks = computed(() => parseDetailText(selected.value?.text || ''))
const stats = computed(() => [
  { label: '模特与场景案例', value: catalog.value?.models.length || 0, route: 'design-models' as DesignView },
  { label: '生图与替换提示词', value: catalog.value?.prompts.length || 0, route: 'design-prompts' as DesignView },
  { label: '前后对照案例', value: catalog.value?.comparisons.length || 0, route: 'design-comparisons' as DesignView },
  { label: '视觉参考页', value: catalog.value?.styles.length || 0, route: 'design-styles' as DesignView },
])
function breakdown(items: DesignItem[], field: 'product' | 'category') {
  const counts = new Map<string, number>()
  for (const item of items) {
    const label = item[field] || '其他'
    counts.set(label, (counts.get(label) || 0) + 1)
  }
  return [...counts].map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count)
}
const modelBreakdown = computed(() => breakdown(catalog.value?.models || [], 'product'))
const styleBreakdown = computed(() => breakdown(catalog.value?.styles || [], 'category'))
const sections = [
  { route: 'design-models' as DesignView, number: '01', title: 'AI模特与场景案例', detail: '从人物状态、穿搭、商品和场景描述找画面参考。' },
  { route: 'design-prompts' as DesignView, number: '02', title: 'AI生图提示词库', detail: '阅读、检索并复制提示词，保留对应的参考图片。' },
  { route: 'design-comparisons' as DesignView, number: '03', title: '生图前后对照', detail: '并排查看上传图和生成图，回看使用的画面描述。' },
  { route: 'design-styles' as DesignView, number: '04', title: '视觉要素手册', detail: '按视觉主题查找构图、人物和造型的具体示例。' },
]

function showDetail(item: DesignItem) { selected.value = item; detailOpen.value = true }
function itemTypeForView(view: DesignView): EditorItemType | null {
  if (view === 'design-models') return 'models'
  if (view === 'design-prompts') return 'prompts'
  if (view === 'design-comparisons') return 'comparisons'
  if (view === 'design-styles') return 'styles'
  return null
}
const editorTypeLabel = computed(() => ({ models: 'AI模特与场景案例', prompts: 'AI生图提示词库', comparisons: '生图前后对照', styles: '视觉要素手册' })[editorType.value])
const itemTypeLabel = (type?: EditorItemType) => type ? ({ models: 'AI模特与场景案例', prompts: 'AI生图提示词库', comparisons: '生图前后对照', styles: '视觉要素手册' })[type] : '设计资料'
const editorHeading = computed(() => `${editorMode.value === 'create' ? '新增' : '编辑'}${editorTypeLabel.value}`)
function resetEditor() {
  editorError.value = ''
  editorImageFiles.value = []
  editorOriginalFile.value = null
  editorGeneratedFile.value = null
}
function openCreate() {
  const type = itemTypeForView(currentView.value)
  if (!type) return
  editorMode.value = 'create'
  editorType.value = type
  editingId.value = ''
  editorTitle.value = ''
  editorText.value = ''
  editorProduct.value = ''
  editorScene.value = ''
  editorCategory.value = ''
  editorImages.value = []
  editorOriginal.value = null
  editorGenerated.value = null
  resetEditor()
  detailOpen.value = false
  editorOpen.value = true
}
function openEdit(item: DesignItem) {
  const type = itemTypeForView(currentView.value)
  if (!type) return
  editorMode.value = 'edit'
  editorType.value = type
  editingId.value = item.id
  editorTitle.value = item.title
  editorText.value = item.text
  editorProduct.value = item.product || ''
  editorScene.value = item.scene || ''
  editorCategory.value = item.category || ''
  editorImages.value = [...(item.images || [])]
  editorOriginal.value = item.original || null
  editorGenerated.value = item.generated || null
  resetEditor()
  detailOpen.value = false
  editorOpen.value = true
}
function onImageFilesSelected(event: Event) {
  const input = event.target as HTMLInputElement
  editorImageFiles.value = Array.from(input.files || [])
}
function onOriginalSelected(event: Event) {
  editorOriginalFile.value = ((event.target as HTMLInputElement).files || [])[0] || null
}
function onGeneratedSelected(event: Event) {
  editorGeneratedFile.value = ((event.target as HTMLInputElement).files || [])[0] || null
}
async function uploadEditorFile(file: File): Promise<string> {
  const form = new FormData()
  form.append('file', file)
  const response = await fetch('/api/design/upload', { method: 'POST', body: form, credentials: 'same-origin' })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || `图片上传失败（${response.status}）`)
  return body.url as string
}
async function saveEditor() {
  editorError.value = ''
  if (!editorTitle.value.trim() || !editorText.value.trim()) {
    editorError.value = '请填写标题和完整描述'
    return
  }
  editorSaving.value = true
  try {
    const imageUrls = editorImageFiles.value.length
      ? await Promise.all(editorImageFiles.value.map(file => uploadEditorFile(file)))
      : editorImages.value
    const original = editorOriginalFile.value ? await uploadEditorFile(editorOriginalFile.value) : editorOriginal.value
    const generated = editorGeneratedFile.value ? await uploadEditorFile(editorGeneratedFile.value) : editorGenerated.value
    const payload = {
      item_type: editorType.value,
      title: editorTitle.value.trim(),
      text: editorText.value,
      images: editorType.value === 'comparisons' ? [] : imageUrls,
      original: editorType.value === 'comparisons' ? original : null,
      generated: editorType.value === 'comparisons' ? generated : null,
      product: editorProduct.value.trim(),
      scene: editorScene.value.trim(),
      category: editorCategory.value.trim(),
    }
    const endpoint = editorMode.value === 'create'
      ? '/api/design/items'
      : `/api/design/items/${editorType.value}/${encodeURIComponent(editingId.value)}`
    const response = await fetch(endpoint, {
      method: editorMode.value === 'create' ? 'POST' : 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(payload),
    })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(body.detail || `保存失败（${response.status}）`)
    catalogRequest = null
    catalog.value = await getCatalog()
    editorOpen.value = false
    ElMessage.success(editorMode.value === 'create' ? '资料已新增' : '资料已更新')
  } catch (reason) {
    editorError.value = reason instanceof Error ? reason.message : '保存失败，请稍后重试'
  } finally {
    editorSaving.value = false
  }
}
async function deleteItem(item: DesignItem) {
  if (!canDelete.value) return
  try {
    const type = itemTypeForView(currentView.value)
    if (!type) return
    const response = await fetch(`/api/design/items/${type}/${encodeURIComponent(item.id)}`, { method: 'DELETE', credentials: 'same-origin' })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(body.detail || `删除失败（${response.status}）`)
    catalogRequest = null
    catalog.value = await getCatalog()
    detailOpen.value = false
    selected.value = null
    page.value = Math.min(page.value, pageCount.value)
    ElMessage.success('已成功删除')
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '删除失败，请稍后重试')
  }
}
async function restoreTrashItem(item: DesignItem) {
  if (!item.item_type || trashBusy.value) return
  trashBusy.value = true
  try {
    const response = await fetch(`/api/design/trash/${item.item_type}/${encodeURIComponent(item.id)}/restore`, { method: 'POST', credentials: 'same-origin' })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(body.detail || `恢复失败（${response.status}）`)
    catalogRequest = null
    await loadTrash()
    ElMessage.success('资料已恢复')
  } catch (reason) { ElMessage.error(reason instanceof Error ? reason.message : '恢复失败') }
  finally { trashBusy.value = false }
}
async function purgeTrashItem(item: DesignItem) {
  if (!item.item_type || trashBusy.value) return
  trashBusy.value = true
  try {
    const response = await fetch(`/api/design/trash/${item.item_type}/${encodeURIComponent(item.id)}`, { method: 'DELETE', credentials: 'same-origin' })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(body.detail || `永久删除失败（${response.status}）`)
    await loadTrash()
    ElMessage.success('资料已永久删除')
  } catch (reason) { ElMessage.error(reason instanceof Error ? reason.message : '永久删除失败') }
  finally { trashBusy.value = false }
}
function changePage(next: number) {
  page.value = next
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
async function copyText(text: string) {
  try { await navigator.clipboard.writeText(text); ElMessage.success('内容已复制') }
  catch { ElMessage.error('复制失败，请在详情中手动选择文本') }
}
</script>

<template>
  <div class="design-board">
    <header class="design-header">
      <div>
        <span class="eyebrow">DESIGN LIBRARY</span>
        <h1>{{ heading.title }}</h1>
        <p>{{ heading.subtitle }}</p>
      </div>
      <div v-if="currentView !== 'design-overview'" class="header-actions">
        <button v-if="currentView !== 'design-trash'" class="primary-button" type="button" @click="openCreate">新增资料</button>
        <button class="back-button" type="button" @click="emit('navigate', 'design-overview')">返回总览</button>
      </div>
    </header>

    <div v-if="loading" class="state-box">正在读取设计资料…</div>
    <div v-else-if="error" class="state-box error">{{ error }}</div>
    <template v-else-if="currentView === 'design-trash'">
      <div v-if="!trashItems.length" class="state-box">回收站暂无资料。</div>
      <div v-else class="trash-list">
        <article v-for="item in trashItems" :key="item.id" class="trash-card">
          <img v-if="imageFor(item)" :src="imageFor(item)" :alt="item.title" loading="lazy" />
          <div v-else class="trash-no-image">无图片</div>
          <div class="trash-info">
            <span>{{ itemTypeLabel(item.item_type) }}</span>
            <h2>{{ item.title }}</h2>
            <p>{{ preview(item.text) }}</p>
            <small>删除人：{{ item.deleted_by || '未知' }} · 删除时间：{{ item.deleted_at || '未知' }}</small>
          </div>
          <div class="trash-actions">
            <button type="button" :disabled="trashBusy" @click="restoreTrashItem(item)">恢复</button>
            <ElPopconfirm title="是否确认删除？" confirm-button-text="确认" cancel-button-text="取消" @confirm="purgeTrashItem(item)">
              <template #reference><button type="button" class="danger-action" :disabled="trashBusy">永久删除</button></template>
            </ElPopconfirm>
          </div>
        </article>
      </div>
    </template>
    <template v-else-if="catalog">
      <template v-if="currentView === 'design-overview'">
        <div class="stats-grid">
          <button v-for="stat in stats" :key="stat.route" class="stat-card" type="button" @click="emit('navigate', stat.route)">
            <span>{{ stat.label }}</span>
            <strong>{{ stat.value }}</strong>
            <small>查看资料 →</small>
          </button>
        </div>
        <div class="section-header"><h2>资料目录</h2><span>按工作需要进入对应页面</span></div>
        <div class="section-grid">
          <button v-for="section in sections" :key="section.route" class="section-card" type="button" @click="emit('navigate', section.route)">
            <span class="section-number">{{ section.number }}</span>
            <strong>{{ section.title }}</strong>
            <p>{{ section.detail }}</p>
            <span class="section-arrow">进入页面 →</span>
          </button>
        </div>
        <div class="breakdown-grid">
          <section class="breakdown-panel">
            <h2>模特案例商品类型</h2>
            <p>依据案例文字初步归类</p>
            <div v-for="item in modelBreakdown" :key="item.label" class="breakdown-row">
              <span>{{ item.label }}</span>
              <div class="bar-track"><div :style="{ width: `${(item.count / (catalog.models.length || 1)) * 100}%` }"></div></div>
              <strong>{{ item.count }}</strong>
            </div>
          </section>
          <section class="breakdown-panel">
            <h2>视觉手册主题</h2>
            <p>来自《生图 -分类》的内容页</p>
            <div v-for="item in styleBreakdown" :key="item.label" class="breakdown-row">
              <span>{{ item.label }}</span>
              <div class="bar-track"><div :style="{ width: `${(item.count / (catalog.styles.length || 1)) * 100}%` }"></div></div>
              <strong>{{ item.count }}</strong>
            </div>
          </section>
        </div>
      </template>

      <template v-else>
        <div class="filter-bar">
          <label class="search-field">
            <span class="sr-only">搜索资料</span>
            <input v-model="keyword" type="search" placeholder="搜索标题、描述或关键词" />
          </label>
          <select v-if="currentView === 'design-styles'" v-model="category" aria-label="视觉主题">
            <option value="">全部主题</option>
            <option v-for="name in categories" :key="name" :value="name">{{ name }}</option>
          </select>
          <template v-else>
            <select v-model="product" aria-label="商品类型">
              <option value="">全部商品</option>
              <option v-for="name in products" :key="name" :value="name">{{ name }}</option>
            </select>
            <select v-model="scene" aria-label="场景类型">
              <option value="">全部场景</option>
              <option v-for="name in scenes" :key="name" :value="name">{{ name }}</option>
            </select>
          </template>
          <span class="result-count">{{ filtered.length }} 条结果</span>
        </div>
        <div v-if="!shown.length" class="state-box">没有匹配的资料，请调整筛选条件。</div>

        <div v-else-if="currentView === 'design-comparisons'" class="comparison-grid">
          <article v-for="item in shown" :key="item.id" class="comparison-card">
            <div class="pair-images">
              <div><span>上传图片</span><img v-if="item.original" :src="item.original" :alt="`${item.title}上传图片`" loading="lazy" /><div v-else class="missing-image">无图片</div></div>
              <div><span>生成图片</span><img v-if="item.generated" :src="item.generated" :alt="`${item.title}生成图片`" loading="lazy" /><div v-else class="missing-image">无图片</div></div>
            </div>
            <div class="card-body">
              <div class="tag-row"><span>{{ item.product }}</span><span>{{ item.scene }}</span></div>
              <h3>{{ item.title }}</h3>
              <p>{{ preview(item.text) }}</p>
              <div class="comparison-actions"><button type="button" class="text-link" @click="showDetail(item)">查看完整描述</button><span class="card-action-group"><button type="button" class="card-edit-button" @click="openEdit(item)">编辑</button><ElPopconfirm v-if="canDelete" title="是否确认删除？" confirm-button-text="确认" cancel-button-text="取消" @confirm="deleteItem(item)"><template #reference><button type="button" class="card-delete-button">删除</button></template></ElPopconfirm></span></div>
            </div>
          </article>
        </div>

        <div v-else class="case-grid">
          <article v-for="item in shown" :key="item.id" class="case-card" role="button" tabindex="0" @click="showDetail(item)" @keydown.enter="showDetail(item)" @keydown.space.prevent="showDetail(item)">
            <div v-if="imageFor(item)" class="card-image"><img :src="imageFor(item)" :alt="item.title" loading="lazy" /></div>
            <div v-else class="text-only-cover"><span>原文件未附图</span><p>{{ preview(item.text) }}</p></div>
            <div class="card-body">
              <div class="tag-row"><span v-if="item.category">{{ item.category }}</span><template v-else><span>{{ item.product }}</span><span>{{ item.scene }}</span></template></div>
              <h3>{{ item.title }}</h3>
              <p v-if="imageFor(item)">{{ preview(item.text) }}</p>
              <div class="card-footer"><span>{{ item.source }}</span><span class="card-action-group"><button type="button" class="card-edit-button" @click.stop="openEdit(item)">编辑</button><ElPopconfirm v-if="canDelete" title="是否确认删除？" confirm-button-text="确认" cancel-button-text="取消" @confirm="deleteItem(item)"><template #reference><button type="button" class="card-delete-button" @click.stop>删除</button></template></ElPopconfirm></span><span>查看详情 →</span></div>
            </div>
          </article>
        </div>

        <nav v-if="pageCount > 1" class="pager" aria-label="案例分页">
          <button type="button" :disabled="page === 1" @click="changePage(page - 1)">上一页</button>
          <span>第 {{ page }} / {{ pageCount }} 页</span>
          <button type="button" :disabled="page === pageCount" @click="changePage(page + 1)">下一页</button>
        </nav>
      </template>
    </template>

    <ElDialog v-model="detailOpen" :title="selected?.title || '案例详情'" width="min(1120px, 94vw)" top="3vh" class="design-detail-dialog">
      <div v-if="selected" class="detail-scroll">
        <div class="detail-media">
          <div class="detail-source">{{ selected.source }}</div>
          <div v-if="selected.original || selected.generated" class="detail-pair">
            <figure>
              <figcaption>上传图片</figcaption>
              <img v-if="selected.original" :src="selected.original" alt="上传图片" />
            </figure>
            <figure>
              <figcaption>生成图片</figcaption>
              <img v-if="selected.generated" :src="selected.generated" alt="生成图片" />
            </figure>
          </div>
          <div v-else-if="selected.images?.length" class="detail-images">
            <figure v-for="(url, index) in selected.images" :key="url + index">
              <img :src="url" :alt="`${selected.title}参考图 ${index + 1}`" />
              <figcaption>参考图 {{ index + 1 }}</figcaption>
            </figure>
          </div>
        </div>
        <div class="detail-text-head"><strong>{{ currentView === 'design-styles' ? '原始说明' : '完整描述 / 提示词' }}</strong><div class="detail-actions"><button type="button" @click="openEdit(selected); detailOpen = false">编辑</button><ElPopconfirm v-if="canDelete" title="是否确认删除？" confirm-button-text="确认" cancel-button-text="取消" @confirm="deleteItem(selected)"><template #reference><button type="button" class="danger-action">删除</button></template></ElPopconfirm><button type="button" @click="copyText(selected.text)">复制文字</button></div></div>
        <div class="detail-text">
          <template v-for="(block, index) in detailBlocks" :key="index">
            <h3 v-if="block.kind === 'heading'" class="detail-heading" :class="`level-${block.level}`">
              <template v-for="(part, partIndex) in block.content || []" :key="partIndex"><strong v-if="part.bold">{{ part.text }}</strong><em v-else-if="part.italic">{{ part.text }}</em><span v-else>{{ part.text }}</span></template>
            </h3>
            <p v-else-if="block.kind === 'paragraph'" class="detail-paragraph">
              <template v-for="(part, partIndex) in block.content || []" :key="partIndex"><strong v-if="part.bold">{{ part.text }}</strong><em v-else-if="part.italic">{{ part.text }}</em><span v-else>{{ part.text }}</span></template>
            </p>
            <div v-else-if="block.kind === 'list'" class="detail-list-item" :style="{ paddingLeft: `${(block.depth || 0) * 16}px` }">
              <span class="detail-list-marker">{{ block.marker }}</span>
              <span><template v-for="(part, partIndex) in block.content || []" :key="partIndex"><strong v-if="part.bold">{{ part.text }}</strong><em v-else-if="part.italic">{{ part.text }}</em><span v-else>{{ part.text }}</span></template></span>
            </div>
            <div v-else-if="block.kind === 'table'" class="detail-table-wrap">
              <table class="detail-table">
                <thead v-if="block.headers"><tr><th v-for="(cell, cellIndex) in block.headers" :key="cellIndex"><template v-for="(part, partIndex) in cell" :key="partIndex"><strong v-if="part.bold">{{ part.text }}</strong><em v-else-if="part.italic">{{ part.text }}</em><span v-else>{{ part.text }}</span></template></th></tr></thead>
                <tbody><tr v-for="(row, rowIndex) in block.rows || []" :key="rowIndex"><td v-for="(cell, cellIndex) in row" :key="cellIndex"><template v-for="(part, partIndex) in cell" :key="partIndex"><strong v-if="part.bold">{{ part.text }}</strong><em v-else-if="part.italic">{{ part.text }}</em><span v-else>{{ part.text }}</span></template></td></tr></tbody>
              </table>
            </div>
            <hr v-else-if="block.kind === 'divider'" class="detail-divider" />
          </template>
        </div>
      </div>
    </ElDialog>

    <ElDialog v-model="editorOpen" :title="editorHeading" width="min(760px, 92vw)" top="6vh" class="design-editor-dialog" @closed="resetEditor">
      <form class="editor-form" @submit.prevent="saveEditor">
        <div class="editor-grid">
          <label><span>标题</span><input v-model="editorTitle" maxlength="255" placeholder="例如：城市通勤人物状态" /></label>
          <label v-if="editorType === 'styles'"><span>视觉主题</span><input v-model="editorCategory" placeholder="例如：构图与视角" /></label>
          <label v-else><span>商品类型</span><input v-model="editorProduct" placeholder="例如：背包/箱包" /></label>
          <label v-if="editorType !== 'styles'"><span>场景类型</span><input v-model="editorScene" placeholder="例如：城市/通勤" /></label>
        </div>
        <label><span>完整描述 / 提示词</span><textarea v-model="editorText" rows="12" maxlength="200000" placeholder="支持 Markdown 标题、列表和表格文本" /></label>
        <template v-if="editorType === 'comparisons'">
          <div class="editor-grid">
            <label><span>上传图片</span><input type="file" accept="image/*" @change="onOriginalSelected" /><small>{{ editorOriginalFile ? editorOriginalFile.name : (editorOriginal ? '已保留原上传图片' : '未选择图片') }}</small></label>
            <label><span>生成图片</span><input type="file" accept="image/*" @change="onGeneratedSelected" /><small>{{ editorGeneratedFile ? editorGeneratedFile.name : (editorGenerated ? '已保留原生成图片' : '未选择图片') }}</small></label>
          </div>
        </template>
        <label v-else><span>参考图片</span><input type="file" accept="image/*" multiple @change="onImageFilesSelected" /><small>{{ editorImageFiles.length ? `本次将替换为 ${editorImageFiles.length} 张新图片` : `当前保留 ${editorImages.length} 张图片；不选文件则不变` }}</small></label>
        <p v-if="editorError" class="editor-error">{{ editorError }}</p>
        <div class="editor-footer"><button type="button" class="back-button" @click="editorOpen = false">取消</button><button type="submit" class="primary-button" :disabled="editorSaving">{{ editorSaving ? '保存中…' : '保存资料' }}</button></div>
      </form>
    </ElDialog>
  </div>
</template>

<style scoped>
.design-board{box-sizing:border-box;width:100%;max-width:1600px;margin:0 auto;padding:30px 30px 56px;color:light-dark(#18283f, var(--text-primary));font-family:inherit}
.design-header{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;margin-bottom:28px}.header-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.eyebrow{display:block;color:light-dark(#4387be, #93c5fd);font-size:11px;font-weight:800;letter-spacing:.16em;margin-bottom:10px}
.design-header h1{font-size:30px;line-height:1.25;margin:0 0 9px;font-weight:750;letter-spacing:-.02em}
.design-header p{margin:0;color:light-dark(#6a788a, var(--text-secondary));font-size:14px}
.back-button,.pager button{border:1px solid light-dark(#d9e2ed, var(--border-color));background:light-dark(#fff, var(--app-surface));border-radius:9px;color:light-dark(#355371, var(--text-primary));padding:9px 14px;cursor:pointer;font:inherit}
.back-button:hover,.pager button:not(:disabled):hover{border-color:#77a9d0;background:light-dark(#f4f9fd, var(--app-surface-2))}
.primary-button{border:1px solid #0b938a;background:#0f9188;color:#fff;border-radius:9px;padding:9px 15px;cursor:pointer;font:inherit;font-weight:650;box-shadow:0 6px 14px rgba(15,145,136,.16)}.primary-button:hover{background:#087d76}.primary-button:disabled{opacity:.55;cursor:not-allowed}
.stats-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:4px 0 34px}
.stat-card{display:flex;flex-direction:column;align-items:flex-start;text-align:left;min-height:142px;border:1px solid light-dark(#e1e9f0, var(--border-color));background:light-dark(#fff, var(--app-surface));border-radius:14px;padding:20px;box-shadow:0 6px 24px rgba(29,54,85,.035);cursor:pointer;color:inherit}
.stat-card span{color:light-dark(#66788c, var(--text-secondary));font-size:13px}.stat-card strong{font-size:36px;margin:6px 0;font-variant-numeric:tabular-nums}.stat-card small{color:light-dark(#3180bc, #93c5fd);margin-top:auto;font-size:12px}
.stat-card:hover,.section-card:hover,.case-card:hover,.comparison-card:hover{border-color:#9ac9e8;box-shadow:0 10px 28px rgba(38,89,131,.1)}
.section-header{display:flex;align-items:baseline;gap:14px;margin-bottom:14px}.section-header h2{margin:0;font-size:20px}.section-header span{font-size:13px;color:light-dark(#8795a4, var(--text-secondary))}
.section-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px}
.section-card{border:1px solid light-dark(#e1e9f0, var(--border-color));border-radius:14px;background:light-dark(#fff, var(--app-surface));padding:22px;text-align:left;min-height:175px;display:flex;flex-direction:column;align-items:flex-start;cursor:pointer;color:inherit}
.section-number{font-size:12px;font-weight:800;color:#73a9cf;margin-bottom:13px}.section-card strong{font-size:18px}.section-card p{margin:8px 0 16px;font-size:13px;line-height:1.6;color:light-dark(#6a788a, var(--text-secondary))}.section-arrow{margin-top:auto;color:light-dark(#2780bc, #93c5fd);font-size:13px;font-weight:650}
.breakdown-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px;margin-top:24px}.breakdown-panel{background:light-dark(#fff, var(--app-surface));border:1px solid light-dark(#e1e9f0, var(--border-color));border-radius:13px;padding:20px 22px}.breakdown-panel h2{font-size:16px;margin:0 0 4px}.breakdown-panel>p{font-size:12px;color:light-dark(#8a9baa, var(--text-secondary));margin:0 0 18px}.breakdown-row{display:grid;grid-template-columns:90px 1fr 32px;gap:10px;align-items:center;margin:10px 0;font-size:12px;color:light-dark(#65798b, var(--text-secondary))}.breakdown-row strong{font-variant-numeric:tabular-nums;text-align:right;color:light-dark(#314f69, var(--text-primary))}.bar-track{height:7px;background:light-dark(#eef3f7, var(--app-surface-2));border-radius:7px;overflow:hidden}.bar-track div{height:100%;background:#61a6cf;border-radius:7px}
.overview-note{background:light-dark(#edf5fa, rgba(96, 165, 250, .12));border:1px solid light-dark(#d8e8f2, var(--border-color));border-radius:12px;margin-top:23px;padding:18px 21px}.overview-note strong{font-size:14px}.overview-note p{font-size:13px;color:light-dark(#516c80, var(--text-secondary));line-height:1.6;margin:7px 0}.overview-note span{font-size:12px;color:light-dark(#8193a2, var(--text-secondary))}
.filter-bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;background:light-dark(#fff, var(--app-surface));border:1px solid light-dark(#e0e8f0, var(--border-color));border-radius:12px;padding:14px;margin-bottom:20px}
.search-field{flex:1 1 300px}.filter-bar input,.filter-bar select{height:38px;width:100%;border:1px solid light-dark(#dbe4ec, var(--border-color));border-radius:8px;background:light-dark(#fff, var(--app-surface));color:light-dark(#243951, var(--text-primary));font:inherit;font-size:13px;padding:0 11px;outline:none}.filter-bar select{width:auto;min-width:130px}.filter-bar input:focus,.filter-bar select:focus{border-color:#67a8d1}.result-count{font-size:13px;color:light-dark(#728499, var(--text-secondary));margin-left:auto;white-space:nowrap}
.case-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.case-card,.comparison-card{background:light-dark(#fff, var(--app-surface));border:1px solid light-dark(#e1e9f0, var(--border-color));border-radius:13px;overflow:hidden;transition:.16s;min-width:0}.case-card{cursor:pointer}.card-image{height:210px;background:light-dark(#f1f4f7, var(--app-surface-2))}.card-image img{height:100%;width:100%;object-fit:cover}.missing-image{height:100%;display:flex;align-items:center;justify-content:center;color:light-dark(#9caab7, var(--text-secondary));font-size:13px;background:light-dark(#f3f5f7, var(--app-surface-2))}.card-body{padding:14px 16px 17px}.tag-row{display:flex;gap:6px;flex-wrap:wrap;min-height:23px}.tag-row span{font-size:11px;background:light-dark(#edf5fb, rgba(96, 165, 250, .12));color:light-dark(#45799a, #93c5fd);padding:3px 7px;border-radius:5px}.card-body h3{font-size:14px;line-height:1.45;margin:9px 0 7px;font-weight:700;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.card-body p{font-size:12px;line-height:1.6;color:light-dark(#788899, var(--text-secondary));margin:0;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;min-height:57px}.card-footer{border-top:1px solid light-dark(#edf1f5, var(--border-color));margin-top:14px;padding-top:11px;display:flex;justify-content:space-between;gap:8px;color:light-dark(#8b99a6, var(--text-secondary));font-size:11px}.card-footer span:first-child{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.card-footer span:last-child{white-space:nowrap;color:light-dark(#3881b5, #93c5fd)}
.card-action-group{display:inline-flex;align-items:center;gap:8px;white-space:nowrap}.card-edit-button,.card-delete-button{border:0;background:transparent;cursor:pointer;padding:0;font:inherit;font-size:11px;white-space:nowrap}.card-edit-button{color:light-dark(#3380b4, #93c5fd)}.card-edit-button:hover{color:light-dark(#0b6d9c, #5eead4);text-decoration:underline}.card-delete-button,.danger-action{color:light-dark(#c65c63, #fca5a5)}.card-delete-button:hover,.danger-action:hover{color:light-dark(#aa3039, #fca5a5);text-decoration:underline}
.text-only-cover{box-sizing:border-box;height:210px;overflow:hidden;padding:18px;background:light-dark(#f3f7fa, var(--app-surface-2));border-bottom:1px solid light-dark(#e1e9f0, var(--border-color))}
.text-only-cover>span{display:inline-block;padding:4px 8px;border-radius:5px;background:light-dark(#e4eef5, rgba(96, 165, 250, .12));color:light-dark(#56768d, var(--text-secondary));font-size:11px;font-weight:650}
.text-only-cover>p{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:6;overflow:hidden;margin:12px 0 0;color:light-dark(#4d6273, var(--text-secondary));font-size:13px;line-height:1.65;overflow-wrap:anywhere}
.comparison-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.pair-images{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:light-dark(#e6edf3, rgba(96, 165, 250, .12))}.pair-images>div{height:240px;position:relative;background:light-dark(#f4f6f8, var(--app-surface-2))}.pair-images img{height:100%;width:100%;object-fit:contain}.pair-images span{position:absolute;left:10px;top:10px;background:rgba(255,255,255,.94);border-radius:5px;padding:4px 8px;font-size:11px;font-weight:700;color:light-dark(#52677d, var(--text-primary))}.comparison-card .card-body p{min-height:0}.comparison-actions{display:flex;align-items:center;justify-content:space-between;gap:12px}.text-link{border:0;background:none;color:light-dark(#2c82bd, #93c5fd);cursor:pointer;padding:11px 0 0;font:inherit;font-size:12px;font-weight:650}
.pager{display:flex;justify-content:center;align-items:center;gap:18px;margin-top:28px;color:light-dark(#74889b, var(--text-secondary));font-size:13px}.pager button:disabled{opacity:.45;cursor:not-allowed}
.state-box{padding:65px 20px;text-align:center;color:light-dark(#7890a4, var(--text-secondary));background:light-dark(#fff, var(--app-surface));border:1px solid light-dark(#e1e9f0, var(--border-color));border-radius:12px}.state-box.error{color:light-dark(#b44f54, #fca5a5)}
.trash-list{display:flex;flex-direction:column;gap:12px}.trash-card{display:flex;align-items:center;gap:18px;padding:16px;background:light-dark(#fff, var(--app-surface));border:1px solid light-dark(#e1e9f0, var(--border-color));border-radius:12px}.trash-card>img,.trash-no-image{width:110px;height:90px;flex:none;object-fit:contain;border-radius:7px;background:light-dark(#f4f7fa, var(--app-surface-2))}.trash-no-image{display:flex;align-items:center;justify-content:center;color:light-dark(#91a0af, var(--text-secondary));font-size:12px}.trash-info{min-width:0;flex:1}.trash-info>span{font-size:11px;color:light-dark(#4387be, #93c5fd)}.trash-info h2{font-size:15px;margin:4px 0}.trash-info p{font-size:12px;color:light-dark(#64788c, var(--text-secondary));margin:4px 0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.trash-info small{font-size:11px;color:light-dark(#8a99a8, var(--text-secondary))}.trash-actions{display:flex;gap:8px;flex:none}.trash-actions button{border:1px solid light-dark(#bdd8eb, var(--border-color));background:light-dark(#f1f8fc, rgba(96, 165, 250, .12));color:light-dark(#317da9, #93c5fd);border-radius:7px;padding:8px 12px;cursor:pointer}.trash-actions button.danger-action{border-color:light-dark(#f0c7ca, var(--border-color));background:light-dark(#fff5f5, rgba(248, 113, 113, .12));color:light-dark(#bb454e, #fca5a5)}.trash-actions button:disabled{opacity:.5;cursor:not-allowed}
:global(.design-detail-dialog){box-sizing:border-box;display:flex;flex-direction:column;height:94vh;max-height:94vh;margin-bottom:0;overflow:hidden}
:global(.design-detail-dialog .el-dialog__header){flex:none}
:global(.design-detail-dialog .el-dialog__body){flex:1;min-height:0;overflow:hidden;padding-top:0}
.detail-scroll{height:100%;min-height:0;overflow-y:auto;overflow-x:hidden;overscroll-behavior:contain;scrollbar-gutter:stable}
.detail-media{position:sticky;top:0;z-index:2;background:light-dark(#fff, var(--app-surface));padding-bottom:12px;box-shadow:0 8px 12px -12px rgba(30,60,85,.45)}
.detail-source{color:light-dark(#8b9ba9, var(--text-secondary));font-size:12px;margin-bottom:10px}
.detail-images{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,200px),1fr));gap:10px}
.detail-images figure{min-width:0;margin:0;background:light-dark(#f5f7f8, var(--app-surface-2));border-radius:8px;overflow:hidden}
.detail-images img{display:block;width:100%;max-height:min(35vh,340px);object-fit:contain;background:light-dark(#f5f6f8, var(--app-surface-2))}
.detail-pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.detail-pair figure{margin:0;min-width:0;background:light-dark(#f5f7f8, var(--app-surface-2));border-radius:8px;overflow:hidden}
.detail-pair img{display:block;width:100%;max-height:min(35vh,340px);object-fit:contain}
.detail-images figcaption,.detail-pair figcaption{padding:9px 12px;font-size:12px;color:light-dark(#667889, var(--text-secondary))}
.detail-text-head{display:flex;justify-content:space-between;align-items:center;border-top:1px solid light-dark(#e4eaf0, var(--border-color));padding-top:14px}
.detail-actions{display:flex;gap:8px}.detail-text-head button{border:1px solid light-dark(#bdd8eb, var(--border-color));border-radius:7px;background:light-dark(#f1f8fc, rgba(96, 165, 250, .12));color:light-dark(#317da9, #93c5fd);padding:7px 11px;cursor:pointer}.detail-text-head button:hover{background:light-dark(#e5f3fa, rgba(96, 165, 250, .12))}.detail-text-head button.danger-action{border-color:light-dark(#f0c7ca, var(--border-color));background:light-dark(#fff5f5, rgba(248, 113, 113, .12));color:light-dark(#c65c63, #fca5a5)}.detail-text-head button.danger-action:hover{background:light-dark(#ffebec, rgba(248, 113, 113, .12))}
.detail-text{width:100%;min-width:0;overflow-wrap:anywhere;word-break:break-word;margin:12px 0 18px;color:light-dark(#33465a, var(--text-secondary));font-size:13px;line-height:1.75}
.detail-text *{overflow-wrap:anywhere;word-break:break-word}
.detail-heading{margin:20px 0 8px;color:light-dark(#19364e, var(--text-primary));font-size:16px;line-height:1.45}
.detail-heading:first-child{margin-top:0}
.detail-heading.level-1{font-size:19px}
.detail-heading.level-3,.detail-heading.level-4,.detail-heading.level-5,.detail-heading.level-6{font-size:14px}
.detail-paragraph{white-space:pre-line;margin:8px 0 14px}
.detail-list-item{display:flex;align-items:flex-start;gap:8px;margin:5px 0;white-space:pre-line}
.detail-list-marker{flex:0 0 23px;color:light-dark(#5388a9, #93c5fd);font-weight:700;text-align:right}
.detail-divider{border:0;border-top:1px solid light-dark(#e3ebf1, var(--border-color));margin:17px 0}
.detail-table-wrap{overflow-x:hidden;margin:12px 0 18px}
.detail-table{border-collapse:collapse;width:100%;table-layout:fixed;font-size:12px;line-height:1.6}
.detail-table th,.detail-table td{border:1px solid light-dark(#dfe8ef, var(--border-color));padding:8px 10px;text-align:left;vertical-align:top}
.detail-table th{background:light-dark(#f0f6fa, rgba(96, 165, 250, .12));color:light-dark(#294c66, var(--text-secondary))}
.editor-form{display:flex;flex-direction:column;gap:16px}.editor-form label{display:flex;flex-direction:column;gap:7px;color:light-dark(#314b63, var(--text-primary));font-size:13px;font-weight:650}.editor-form input,.editor-form textarea{box-sizing:border-box;width:100%;border:1px solid light-dark(#d7e2eb, var(--border-color));border-radius:8px;background:light-dark(#fff, var(--app-surface));color:light-dark(#243951, var(--text-primary));font:inherit;font-size:13px;padding:10px 11px;outline:none}.editor-form textarea{resize:vertical;line-height:1.65}.editor-form input:focus,.editor-form textarea:focus{border-color:#62a5d0;box-shadow:0 0 0 3px rgba(98,165,208,.1)}.editor-form input[type=file]{padding:8px;background:light-dark(#f8fbfd, var(--app-surface-2))}.editor-form small{font-size:11px;color:light-dark(#8294a3, var(--text-secondary));font-weight:400}.editor-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.editor-hidden-label input{color:light-dark(#8092a1, var(--text-secondary));background:light-dark(#f5f7f9, var(--app-surface-2))}.editor-error{margin:0;padding:10px 12px;border-radius:7px;background:light-dark(#fff1f1, rgba(248, 113, 113, .12));color:light-dark(#b34d51, #fca5a5);font-size:12px}.editor-footer{display:flex;justify-content:flex-end;gap:10px;padding-top:2px}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:1200px){.case-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:850px){.stats-grid{grid-template-columns:repeat(2,1fr)}.case-grid,.comparison-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.design-board{padding:20px}}@media(max-width:620px){.case-grid,.comparison-grid,.section-grid,.breakdown-grid{grid-template-columns:1fr}.design-header{display:block}.header-actions{margin-top:16px}.pair-images>div{height:180px}.detail-media{position:static}.detail-pair{grid-template-columns:1fr}.detail-images{grid-template-columns:repeat(2,minmax(0,1fr))}.detail-images img,.detail-pair img{max-height:25vh}.editor-grid{grid-template-columns:1fr}.trash-card{align-items:flex-start;flex-wrap:wrap}.trash-info{flex-basis:calc(100% - 128px)}.trash-actions{margin-left:auto}}
</style>
