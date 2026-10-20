<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ElInput, ElMessage, ElMessageBox } from 'element-plus'
import { ArrowUp, Close, Collection, CopyDocument, Document, EditPen, FolderOpened, Plus, Search } from '@element-plus/icons-vue'

interface LibraryStatus { key: string; name: string; documents: number; chunks: number }
interface Source { library: string; path: string; name: string; chunk_id: number; score: number; snippet: string; matched_by?: string[] }
interface Retrieval { method: string; candidate_count: number; selected_count: number; libraries: string[] }
interface Message { id: string; role: 'user' | 'assistant'; content: string; createdAt: string; status?: 'pending' | 'done' | 'error'; stage?: string; sources?: Source[]; retrieval?: Retrieval; model?: string }
interface Session { id: string; title: string; library: string; createdAt: string; updatedAt: string; messages: Message[] }
interface Status { libraries: LibraryStatus[]; document_count: number; chunk_count: number; ai_configured: boolean; retrieval: string }
interface Preview { name: string; type: string; content?: string; html?: string; url?: string; message?: string }
interface InlinePart { kind: 'text' | 'strong' | 'code'; text: string }
interface AnswerBlock { kind: 'paragraph' | 'heading' | 'ul' | 'ol'; items: InlinePart[][] }

const status = ref<Status>({ libraries: [], document_count: 0, chunk_count: 0, ai_configured: true, retrieval: '' })
const sessions = ref<Session[]>([])
const currentId = ref('')
const selectedLibrary = ref('all')
const question = ref('')
const historyQuery = ref('')
const busy = ref(false)
const loading = ref(true)
const error = ref('')
const evidenceOpen = ref(window.innerWidth > 980)
const historyOpen = ref(window.innerWidth > 700)
const activeEvidenceId = ref('')
const preview = ref<Preview | null>(null)
const scroller = ref<HTMLElement | null>(null)

const account = localStorage.getItem('auth_username') || localStorage.getItem('auth_real_name') || 'account'
const storageKey = `knowledge-qa-v2:${account}`
const current = computed(() => sessions.value.find((item) => item.id === currentId.value) || null)
const filteredSessions = computed(() => {
  const q = historyQuery.value.trim().toLocaleLowerCase()
  return q ? sessions.value.filter((item) => item.title.toLocaleLowerCase().includes(q)) : sessions.value
})
const libraryMap = computed(() => Object.fromEntries(status.value.libraries.map((item) => [item.key, item.name])))
const activeAnswer = computed(() => {
  const answers = current.value?.messages.filter((item) => item.role === 'assistant') || []
  return answers.find((item) => item.id === activeEvidenceId.value) || answers[answers.length - 1] || null
})
const sourceCount = computed(() => activeAnswer.value?.sources?.length || 0)
const canSend = computed(() => question.value.trim() && !busy.value && !loading.value && status.value.ai_configured)

function newId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}
function persist() {
  try { localStorage.setItem(storageKey, JSON.stringify(sessions.value.slice(0, 30))) } catch { /* optional */ }
}
function hydrate() {
  try {
    const raw = JSON.parse(localStorage.getItem(storageKey) || '[]')
    if (Array.isArray(raw)) sessions.value = raw.filter((item) => item && Array.isArray(item.messages)).slice(0, 30)
  } catch { sessions.value = [] }
}
async function loadStatus() {
  const response = await fetch('/api/ecom-knowledge/status', { credentials: 'same-origin', cache: 'no-store' })
  const body = await response.json()
  if (!response.ok) throw new Error(body.detail || '知识库索引状态加载失败')
  status.value = body
}
function libraryName(key: string) { return key === 'all' ? '全部知识库' : libraryMap.value[key] || key }
function fresh() {
  currentId.value = ''; selectedLibrary.value = 'all'; activeEvidenceId.value = ''; question.value = ''; error.value = ''
  if (window.innerWidth <= 700) historyOpen.value = false
}
function openSession(item: Session) {
  currentId.value = item.id
  selectedLibrary.value = item.library || 'all'
  activeEvidenceId.value = [...item.messages].reverse().find((message) => message.role === 'assistant')?.id || ''
  void bottom()
  if (window.innerWidth <= 700) historyOpen.value = false
}
async function rename(item: Session) {
  try {
    const result = await ElMessageBox.prompt('为这段知识问答设置名称', '重命名对话', {
      inputValue: item.title,
      inputValidator: (value) => !!value?.trim() && value.trim().length <= 60,
      inputErrorMessage: '请输入 1–60 个字符',
    })
    item.title = result.value.trim(); item.updatedAt = new Date().toISOString(); persist()
  } catch { /* cancelled */ }
}
function ensureSession(questionText: string) {
  let session = current.value
  if (!session) {
    const now = new Date().toISOString()
    session = { id: newId(), title: questionText.slice(0, 32), library: selectedLibrary.value, createdAt: now, updatedAt: now, messages: [] }
    sessions.value.unshift(session); currentId.value = session.id
  }
  session.library = selectedLibrary.value
  return session
}
async function bottom() { await nextTick(); if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight }
function applyStreamEvent(message: Message, event: any) {
  if (event.type === 'start') {
    message.stage = '已完成跨库召回，正在核对证据…'; message.sources = event.sources || []; message.retrieval = event.retrieval; message.model = event.model || ''
  } else if (event.type === 'delta') {
    message.stage = '正在生成有依据的回答…'; message.content += event.delta || ''
  } else if (event.type === 'done') {
    message.content = event.answer || message.content; message.sources = event.sources || message.sources || []; message.retrieval = event.retrieval || message.retrieval; message.model = event.model || message.model; message.status = 'done'; message.stage = '回答已完成'
  } else if (event.type === 'error') throw new Error(event.message || '知识问答失败')
}
async function send(text = question.value) {
  const q = text.trim()
  if (!q || busy.value) return
  busy.value = true; error.value = ''
  const session = ensureSession(q)
  const user: Message = { id: newId(), role: 'user', content: q, createdAt: new Date().toISOString() }
  const answer: Message = { id: newId(), role: 'assistant', content: '', createdAt: new Date().toISOString(), status: 'pending', stage: '正在理解问题并准备检索…', sources: [] }
  const history = session.messages.slice(-6).map(({ role, content }) => ({ role, content }))
  session.messages.push(user, answer); session.updatedAt = new Date().toISOString(); question.value = ''; activeEvidenceId.value = answer.id; persist(); await bottom()
  try {
    const response = await fetch('/api/ecom-knowledge/ask/stream', {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ library: selectedLibrary.value, question: q, history, top_k: 10 }),
    })
    if (!response.ok || !response.body) {
      const body = await response.json().catch(() => ({})); throw new Error(body.detail || '问答服务暂时不可用')
    }
    const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
      const packets = buffer.split('\n\n'); buffer = packets.pop() || ''
      for (const packet of packets) {
        const line = packet.split('\n').find((item) => item.startsWith('data:'))
        if (!line) continue
        applyStreamEvent(answer, JSON.parse(line.slice(5).trim())); await bottom()
      }
      if (done) break
    }
    if (buffer.trim()) {
      const line = buffer.split('\n').find((item) => item.startsWith('data:'))
      if (line) applyStreamEvent(answer, JSON.parse(line.slice(5).trim()))
    }
    if (answer.status === 'pending') answer.status = 'done'
  } catch (err: any) {
    answer.status = 'error'; answer.stage = '回答失败'; answer.content = err?.message || '问答请求失败，请稍后重试'; error.value = answer.content
  } finally {
    session.updatedAt = new Date().toISOString(); sessions.value = [session, ...sessions.value.filter((item) => item.id !== session.id)]; persist(); busy.value = false; await bottom()
  }
}
function keydown(event: Event | KeyboardEvent) {
  const keyboardEvent = event as KeyboardEvent
  if (keyboardEvent.key === 'Enter' && !keyboardEvent.shiftKey && !keyboardEvent.isComposing && keyboardEvent.keyCode !== 229) { keyboardEvent.preventDefault(); void send() }
}
async function copy(message: Message) {
  try { await navigator.clipboard.writeText(message.content); ElMessage.success('回答已复制') } catch { ElMessage.error('复制失败，请手动选择回答') }
}
async function openSource(source: Source) {
  try {
    const response = await fetch(`/api/ecom-knowledge/preview?library=${encodeURIComponent(source.library)}&path=${encodeURIComponent(source.path)}`, { credentials: 'same-origin' })
    const body = await response.json(); if (!response.ok) throw new Error(body.detail || '原文预览失败')
    preview.value = { ...body, name: source.name }
  } catch (err: any) { ElMessage.error(err?.message || '原文预览失败') }
}
function showEvidence(message: Message) { activeEvidenceId.value = message.id; evidenceOpen.value = true }
function time(value: string) { return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) }
function inlineParts(value: string): InlinePart[] {
  const parts: InlinePart[] = []
  const token = /(\*\*.+?\*\*|`[^`]+`)/g
  let cursor = 0
  for (const match of value.matchAll(token)) {
    const index = match.index || 0
    if (index > cursor) parts.push({ kind: 'text', text: value.slice(cursor, index) })
    const raw = match[0]
    parts.push(raw.startsWith('**')
      ? { kind: 'strong', text: raw.slice(2, -2) }
      : { kind: 'code', text: raw.slice(1, -1) })
    cursor = index + raw.length
  }
  if (cursor < value.length) parts.push({ kind: 'text', text: value.slice(cursor) })
  return parts.length ? parts : [{ kind: 'text', text: value }]
}
function answerBlocks(value: string): AnswerBlock[] {
  const blocks: AnswerBlock[] = []
  const paragraph: string[] = []
  const flushParagraph = () => {
    const text = paragraph.splice(0).map((line) => line.trim()).filter(Boolean).join(' ')
    if (text) blocks.push({ kind: 'paragraph', items: [inlineParts(text)] })
  }
  for (const rawLine of value.replace(/\r/g, '').split('\n')) {
    const line = rawLine.trim()
    if (!line) { flushParagraph(); continue }
    const heading = line.match(/^#{1,6}\s+(.+)$/)
    if (heading) { flushParagraph(); blocks.push({ kind: 'heading', items: [inlineParts(heading[1])] }); continue }
    const unordered = line.match(/^[-*]\s+(.+)$/)
    if (unordered) {
      flushParagraph()
      const previous = blocks[blocks.length - 1]
      if (previous?.kind === 'ul') previous.items.push(inlineParts(unordered[1]))
      else blocks.push({ kind: 'ul', items: [inlineParts(unordered[1])] })
      continue
    }
    const ordered = line.match(/^\d+[.)、]\s*(.+)$/)
    if (ordered) {
      flushParagraph()
      const previous = blocks[blocks.length - 1]
      if (previous?.kind === 'ol') previous.items.push(inlineParts(ordered[1]))
      else blocks.push({ kind: 'ol', items: [inlineParts(ordered[1])] })
      continue
    }
    paragraph.push(line)
  }
  flushParagraph()
  return blocks
}

watch(selectedLibrary, (value) => { if (current.value && !current.value.messages.length) current.value.library = value })
onMounted(async () => {
  hydrate()
  try { await loadStatus() } catch (err: any) { error.value = err?.message || '知识库状态加载失败' } finally { loading.value = false }
})
</script>

<template>
  <section class="knowledge-workspace">
    <aside v-if="historyOpen" class="history-panel">
      <div class="panel-title"><strong>知识问答</strong><button class="icon-button" aria-label="收起历史" @click="historyOpen = false"><Collection /></button></div>
      <button class="new-chat" :disabled="busy" @click="fresh"><Plus />新对话</button>
      <el-input v-model="historyQuery" :prefix-icon="Search" clearable placeholder="搜索本机历史" />
      <div class="history-label"><span>历史对话</span><small>{{ sessions.length }}</small></div>
      <div class="session-list">
        <div v-for="item in filteredSessions" :key="item.id" class="session-row" :class="{ active: currentId === item.id }">
          <button class="session-link" @click="openSession(item)"><span>{{ item.title }}</span><small>{{ libraryName(item.library) }} · {{ time(item.updatedAt) }}</small></button>
          <button class="icon-button rename" aria-label="重命名" @click="rename(item)"><EditPen /></button>
        </div>
        <p v-if="!filteredSessions.length" class="empty-tip">{{ historyQuery ? '没有匹配的对话' : '提问后，对话会保存在当前浏览器' }}</p>
      </div>
      <div class="coverage"><FolderOpened /><span><strong>{{ status.document_count }}</strong> 份文档<br><small>{{ status.chunk_count }} 个可检索片段</small></span></div>
    </aside>

    <main class="conversation">
      <header class="workspace-header">
        <div class="heading">
          <button v-if="!historyOpen" class="icon-button" aria-label="展开历史" @click="historyOpen = true"><Collection /></button>
          <div><h1>AI 知识问答</h1><p>{{ status.retrieval || '统一检索公司知识库并给出可回查依据' }}</p></div>
        </div>
        <div class="header-actions">
          <label>检索范围<select v-model="selectedLibrary" :disabled="busy"><option value="all">全部知识库</option><option v-for="item in status.libraries" :key="item.key" :value="item.key">{{ item.name }} · {{ item.documents }} 份</option></select></label>
          <button class="evidence-toggle" :class="{ selected: evidenceOpen }" @click="evidenceOpen = !evidenceOpen"><Document />证据 <span>{{ sourceCount }}</span></button>
        </div>
      </header>

      <div ref="scroller" class="conversation-scroll">
        <div v-if="!current?.messages.length" class="welcome">
          <span class="welcome-icon"><Search /></span><h2>从公司知识里找准确答案</h2><p>一次检索全部知识库，回答附文件、原文片段和检索范围。</p>
          <div class="capabilities"><span>跨库统一排序</span><span>连续追问</span><span>原文可回查</span></div>
          <div class="starters">
            <button @click="send('公司的退换货规则是什么？请列出关键期限和例外情况')"><strong>查制度与规则</strong><span>关键期限、条件与例外</span></button>
            <button @click="send('新员工入职要完成哪些步骤？请按顺序整理')"><strong>整理工作流程</strong><span>从多份文件归纳步骤</span></button>
            <button @click="send('仓库盘点有哪些注意事项和责任分工？')"><strong>核对执行要点</strong><span>定位 SOP 与责任分工</span></button>
          </div>
          <div v-if="status.libraries.length" class="library-overview"><span v-for="item in status.libraries" :key="item.key">{{ item.name }} <b>{{ item.documents }}</b></span></div>
        </div>

        <div v-else class="messages">
          <template v-for="message in current.messages" :key="message.id">
            <article v-if="message.role === 'user'" class="user-message"><small>{{ time(message.createdAt) }}</small><p>{{ message.content }}</p></article>
            <article v-else class="answer" :class="{ failed: message.status === 'error' }">
              <header><span class="ai-mark">AI</span><strong>知识检索助手</strong><small v-if="message.status === 'pending'"><i />{{ message.stage }}</small></header>
              <div v-if="message.content" class="answer-text">
                <template v-for="(block, blockIndex) in answerBlocks(message.content)" :key="blockIndex">
                  <p v-if="block.kind === 'paragraph' || block.kind === 'heading'" :class="{ 'answer-heading': block.kind === 'heading' }"><component :is="part.kind === 'strong' ? 'strong' : part.kind === 'code' ? 'code' : 'span'" v-for="(part, partIndex) in block.items[0]" :key="partIndex">{{ part.text }}</component></p>
                  <ul v-else-if="block.kind === 'ul'"><li v-for="(item, itemIndex) in block.items" :key="itemIndex"><component :is="part.kind === 'strong' ? 'strong' : part.kind === 'code' ? 'code' : 'span'" v-for="(part, partIndex) in item" :key="partIndex">{{ part.text }}</component></li></ul>
                  <ol v-else><li v-for="(item, itemIndex) in block.items" :key="itemIndex"><component :is="part.kind === 'strong' ? 'strong' : part.kind === 'code' ? 'code' : 'span'" v-for="(part, partIndex) in item" :key="partIndex">{{ part.text }}</component></li></ol>
                </template>
                <span v-if="message.status === 'pending'" class="cursor" />
              </div>
              <div v-else class="thinking"><i /><span>{{ message.stage }}</span></div>
              <footer v-if="message.status === 'done'"><button @click="copy(message)"><CopyDocument />复制</button><button @click="showEvidence(message)"><Document />{{ message.sources?.length || 0 }} 条依据</button><span v-if="message.retrieval">从 {{ message.retrieval.candidate_count }} 个片段中选出 {{ message.retrieval.selected_count }} 条</span></footer>
            </article>
          </template>
        </div>
      </div>

      <div class="composer-area">
        <div v-if="error" class="request-error">{{ error }}</div>
        <form class="composer" @submit.prevent="send()">
          <el-input v-model="question" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" maxlength="2000" resize="none" :placeholder="`向${libraryName(selectedLibrary)}提问，或继续追问…`" @keydown="keydown" />
          <div class="composer-bottom"><span>{{ busy ? '正在检索、核对并生成回答…' : 'Enter 发送 · Shift + Enter 换行' }}</span><button type="submit" class="send-button" :disabled="!canSend" aria-label="发送"><ArrowUp /></button></div>
        </form>
        <p>AI 只根据已上传文档回答；重要制度请点击证据回查原文。</p>
      </div>
    </main>

    <aside v-if="evidenceOpen" class="evidence-panel">
      <div class="panel-title"><div><strong>回答依据</strong><small v-if="activeAnswer?.retrieval">{{ activeAnswer.retrieval.method }}</small></div><button class="icon-button" @click="evidenceOpen = false"><Close /></button></div>
      <p v-if="!activeAnswer" class="empty-tip">完成一次问答后，这里会展示命中的知识库、文件与原文片段。</p>
      <template v-else>
        <div class="retrieval-summary"><span>候选片段 <b>{{ activeAnswer.retrieval?.candidate_count || 0 }}</b></span><span>采用依据 <b>{{ sourceCount }}</b></span></div>
        <div class="source-list">
          <button v-for="(source, index) in activeAnswer.sources" :key="`${source.library}-${source.path}-${source.chunk_id}`" class="source-card" @click="openSource(source)"><span class="source-number">{{ index + 1 }}</span><div><strong>{{ source.name }}</strong><small>{{ libraryName(source.library) }} · {{ source.path }}</small><p>{{ source.snippet || '点击查看原文' }}</p><em>查看原文</em></div></button>
          <p v-if="!sourceCount" class="empty-tip">本次回答没有检索到可引用的文档片段。</p>
        </div>
      </template>
    </aside>

    <Teleport to="body"><div v-if="preview" class="preview-mask" @click.self="preview = null"><section class="preview-dialog"><header><strong>{{ preview.name }}</strong><button class="icon-button" @click="preview = null"><Close /></button></header><div class="preview-body"><img v-if="preview.type === 'image'" :src="preview.url" :alt="preview.name" /><iframe v-else-if="preview.type === 'pdf'" :src="preview.url" :title="preview.name" /><div v-else-if="preview.type === 'html'" class="preview-html" v-html="preview.html" /><pre v-else-if="preview.type === 'text' || preview.type === 'doc'">{{ preview.content }}</pre><p v-else>{{ preview.message || '该文件暂不支持在线预览' }}</p></div></section></div></Teleport>
  </section>
</template>

<style scoped>
.knowledge-workspace{height:calc(100vh - 150px);min-height:650px;display:flex;overflow:hidden;background:light-dark(#fff, var(--app-surface));border:1px solid light-dark(#e8ebef, var(--border-color));border-radius:8px;color:light-dark(#242a31, var(--text-primary));font-family:"Microsoft YaHei","Segoe UI",sans-serif}.history-panel{width:245px;flex:none;display:flex;flex-direction:column;gap:14px;padding:20px 14px;background:light-dark(#f7f8fa, var(--app-surface-2));border-right:1px solid light-dark(#eceef1, var(--border-color))}.panel-title{display:flex;align-items:flex-start;justify-content:space-between;padding:0 5px}.panel-title>div{display:flex;flex-direction:column;gap:5px}.panel-title strong{font-size:15px}.panel-title small{font-size:9px;color:light-dark(#949da7, var(--text-secondary));font-weight:400}.icon-button{display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;border:0;border-radius:7px;background:transparent;color:light-dark(#747d87, var(--text-secondary));cursor:pointer}.icon-button:hover{background:light-dark(#e9ecef, var(--app-surface-2))}.icon-button svg,.new-chat svg,.evidence-toggle svg,.answer footer svg{width:16px;height:16px}.new-chat{display:flex;align-items:center;gap:9px;padding:11px 12px;border:1px solid light-dark(#dde2e6, var(--border-color));border-radius:10px;background:light-dark(#fff, var(--app-surface));font-size:13px;cursor:pointer}.history-label{display:flex;justify-content:space-between;padding:7px 8px 0;color:light-dark(#929aa4, var(--text-secondary));font-size:11px}.session-list{flex:1;min-height:0;overflow:auto}.session-row{position:relative;display:flex;margin-bottom:5px;border-radius:9px}.session-row.active,.session-row:hover{background:light-dark(#e9edf1, var(--app-surface-2))}.session-link{width:100%;min-width:0;display:flex;flex-direction:column;gap:7px;padding:11px 31px 11px 10px;border:0;background:transparent;text-align:left;cursor:pointer}.session-link span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}.session-link small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:light-dark(#929aa4, var(--text-secondary));font-size:10px}.rename{position:absolute;right:2px;top:7px;opacity:0}.session-row:hover .rename{opacity:1}.empty-tip{padding:12px 7px;color:light-dark(#959da7, var(--text-secondary));font-size:11px;line-height:1.8}.coverage{display:flex;align-items:center;gap:10px;padding:15px 8px 0;border-top:1px solid light-dark(#e2e6e9, var(--border-color));color:light-dark(#65707b, var(--text-secondary));font-size:11px}.coverage svg{width:22px}.coverage strong{font-size:15px;color:light-dark(#26313a, var(--text-primary))}.coverage small{color:light-dark(#969ea7, var(--text-secondary))}.conversation{min-width:0;flex:1;display:flex;flex-direction:column}.workspace-header{height:70px;flex:none;display:flex;align-items:center;justify-content:space-between;gap:15px;padding:0 24px;border-bottom:1px solid light-dark(#eff1f3, var(--border-color))}.heading{display:flex;align-items:center;gap:10px}.heading h1{margin:0 0 4px;font-size:17px;font-weight:600}.heading p{margin:0;color:light-dark(#98a0a9, var(--text-secondary));font-size:10px}.header-actions{display:flex;align-items:center;gap:12px}.header-actions label{display:flex;align-items:center;gap:8px;color:light-dark(#7d8791, var(--text-secondary));font-size:11px}.header-actions select{height:33px;max-width:180px;padding:0 28px 0 9px;border:1px solid light-dark(#dfe4e8, var(--border-color));border-radius:8px;background:light-dark(#fff, var(--app-surface));color:light-dark(#303942, var(--text-primary));font-size:12px}.evidence-toggle{display:flex;align-items:center;gap:6px;padding:7px 9px;border:0;border-radius:8px;background:light-dark(#f4f6f7, var(--app-surface-2));color:light-dark(#737d87, var(--text-secondary));font-size:11px;cursor:pointer}.evidence-toggle span{padding:1px 5px;border-radius:5px;background:light-dark(#e5e9ec, var(--app-surface-2))}.selected{color:light-dark(#0f766e, var(--text-accent))!important}.conversation-scroll{flex:1;min-height:0;overflow-y:auto}.welcome{max-width:760px;margin:clamp(45px,10vh,120px) auto 35px;padding:0 28px;text-align:center}.welcome-icon{display:inline-flex;padding:14px;border-radius:18px;background:light-dark(#eef7f5, var(--app-surface-2));color:light-dark(#0f766e, var(--text-accent))}.welcome-icon svg{width:28px;height:28px}.welcome h2{margin:22px 0 10px;font-size:26px;font-weight:500;letter-spacing:.5px}.welcome>p{margin:0;color:light-dark(#8f98a2, var(--text-secondary));font-size:13px}.capabilities{display:flex;justify-content:center;gap:8px;margin-top:16px}.capabilities span{padding:5px 9px;border-radius:7px;background:light-dark(#f3f6f5, var(--app-surface-2));color:light-dark(#648079, var(--text-secondary));font-size:10px}.starters{display:grid;grid-template-columns:repeat(3,1fr);gap:11px;margin-top:30px;text-align:left}.starters button{display:flex;flex-direction:column;gap:9px;padding:18px 15px;border:1px solid light-dark(#e4e8eb, var(--border-color));border-radius:12px;background:light-dark(#fff, var(--app-surface));text-align:left;cursor:pointer}.starters button:hover{border-color:#a8beb8;background:light-dark(#f9fbfa, var(--app-surface-2))}.starters strong{font-size:13px;font-weight:500}.starters span{color:light-dark(#929ba4, var(--text-secondary));font-size:11px;line-height:1.5}.library-overview{display:flex;justify-content:center;gap:6px;flex-wrap:wrap;margin-top:25px}.library-overview span{padding:4px 7px;border:1px solid light-dark(#eceff1, var(--border-color));border-radius:6px;color:light-dark(#9199a2, var(--text-secondary));font-size:9px}.library-overview b{color:light-dark(#52615e, var(--text-secondary))}.messages{padding:18px 30px 34px}.user-message{display:flex;flex-direction:column;align-items:flex-end;gap:7px;margin:16px 0 27px}.user-message small{color:light-dark(#a0a7ae, var(--text-secondary));font-size:9px}.user-message p{max-width:82%;margin:0;padding:11px 17px;border-radius:18px 18px 5px 18px;background:light-dark(#f0f2f4, var(--app-surface-2));font-size:14px;line-height:1.8;white-space:pre-wrap}.answer{margin:0 0 34px}.answer>header{display:flex;align-items:center;gap:9px}.ai-mark{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:50%;background:#0f766e;color:#fff;font-size:10px}.answer>header strong{font-size:13px}.answer>header small{display:flex;align-items:center;gap:5px;margin-left:auto;color:light-dark(#8f98a2, var(--text-secondary));font-size:10px}.answer>header small i,.thinking i{width:6px;height:6px;border-radius:50%;background:#0f766e;animation:pulse 1.2s infinite}.answer-text{padding:15px 0 7px 37px;color:light-dark(#303943, var(--text-primary));font-size:14px;line-height:2;white-space:pre-wrap;overflow-wrap:anywhere}.answer.failed .answer-text{color:light-dark(#b45309, #fbbf24)}.thinking{display:flex;align-items:center;gap:9px;padding:18px 0 20px 38px;color:light-dark(#6f7983, var(--text-secondary));font-size:12px}.cursor{display:inline-block;width:2px;height:1.05em;margin-left:3px;vertical-align:-2px;background:#0f766e;animation:blink .8s steps(1) infinite}.answer footer{display:flex;align-items:center;gap:14px;padding:7px 0 0 37px}.answer footer button{display:flex;align-items:center;gap:5px;padding:0;border:0;background:transparent;color:light-dark(#87919b, var(--text-secondary));font-size:10px;cursor:pointer}.answer footer span{margin-left:auto;color:light-dark(#a0a8b0, var(--text-secondary));font-size:9px}.composer-area{flex:none;padding:8px 30px 14px;background:light-dark(#fff, var(--app-surface))}.request-error{margin-bottom:9px;padding:9px 13px;border-radius:8px;background:light-dark(#fffbeb, rgba(251, 191, 36, .12));color:light-dark(#b45309, #fbbf24);font-size:11px}.composer{padding:11px 14px;border:1px solid light-dark(#dce2e6, var(--border-color));border-radius:17px;background:light-dark(#fafbfc, var(--app-surface-2));box-shadow:0 4px 16px #1a314407}.composer:focus-within{border-color:#9bb5ae}.composer :deep(.el-textarea__inner){padding:2px;background:transparent;box-shadow:none;color:light-dark(#29333c, var(--text-primary));font-family:inherit;font-size:14px;line-height:1.8}.composer-bottom{display:flex;align-items:center;justify-content:space-between;margin-top:7px}.composer-bottom>span{color:light-dark(#9ba3ac, var(--text-secondary));font-size:10px}.send-button{width:32px;height:32px;display:flex;align-items:center;justify-content:center;border:0;border-radius:10px;background:#202d2a;color:#fff;cursor:pointer}.send-button:disabled{background:light-dark(#e3e7e9, var(--app-surface-2));color:light-dark(#a5adb4, var(--text-secondary));cursor:default}.send-button svg{width:18px}.composer-area>p{margin:9px 0 0;text-align:center;color:light-dark(#a0a8b0, var(--text-secondary));font-size:9px}.evidence-panel{width:300px;flex:none;display:flex;flex-direction:column;padding:20px 14px;border-left:1px solid light-dark(#eceef1, var(--border-color));background:light-dark(#fcfdfd, var(--app-surface-2))}.retrieval-summary{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:20px 4px 10px}.retrieval-summary span{padding:10px;border:1px solid light-dark(#e7ebed, var(--border-color));border-radius:9px;color:light-dark(#8c959e, var(--text-secondary));font-size:9px}.retrieval-summary b{display:block;margin-top:5px;color:light-dark(#26322f, var(--text-primary));font-size:17px}.source-list{flex:1;min-height:0;overflow:auto}.source-card{width:100%;display:flex;gap:9px;padding:14px 6px;border:0;border-bottom:1px solid light-dark(#eceff1, var(--border-color));background:transparent;text-align:left;cursor:pointer}.source-card:hover{background:light-dark(#f6f9f8, var(--app-surface-2))}.source-number{width:21px;height:21px;flex:none;display:inline-flex;align-items:center;justify-content:center;border-radius:6px;background:light-dark(#e9f3f1, var(--app-surface-2));color:light-dark(#0f766e, var(--text-accent));font-size:10px}.source-card>div{min-width:0}.source-card strong{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px;font-weight:600}.source-card small{display:block;margin:5px 0;color:light-dark(#949da6, var(--text-secondary));font-size:9px;line-height:1.5;overflow-wrap:anywhere}.source-card p{display:-webkit-box;overflow:hidden;margin:8px 0;color:light-dark(#5f6973, var(--text-secondary));font-size:10px;line-height:1.65;-webkit-box-orient:vertical;-webkit-line-clamp:4}.source-card em{color:light-dark(#0f766e, var(--text-accent));font-size:9px;font-style:normal}.preview-mask{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:#1118279e}.preview-dialog{width:min(1100px,92vw);height:min(820px,90vh);display:flex;flex-direction:column;overflow:hidden;border-radius:12px;background:light-dark(#fff, var(--app-surface));box-shadow:0 25px 70px #10182855}.preview-dialog>header{height:56px;flex:none;display:flex;align-items:center;justify-content:space-between;padding:0 18px;border-bottom:1px solid light-dark(#e6e9ec, var(--border-color))}.preview-body{flex:1;min-height:0;overflow:auto;padding:20px}.preview-body pre{margin:0;white-space:pre-wrap;line-height:1.8;font-family:inherit}.preview-body img{display:block;max-width:100%;margin:auto}.preview-body iframe{width:100%;height:100%;border:0}.preview-html :deep(table){border-collapse:collapse}.preview-html :deep(td),.preview-html :deep(th){padding:7px 10px;border:1px solid light-dark(#e5e7eb, var(--border-color))}@keyframes pulse{50%{opacity:.25}}@keyframes blink{50%{opacity:0}}@media(max-width:1200px){.history-panel{width:205px}.evidence-panel{width:250px}.workspace-header{padding:0 18px}.messages,.composer-area{padding-left:22px;padding-right:22px}.heading p{display:none}}@media(max-width:980px){.evidence-panel{position:absolute;right:0;top:0;bottom:0;z-index:10;width:280px;box-shadow:-10px 0 25px #1f29370f}.knowledge-workspace{position:relative}.starters{grid-template-columns:1fr}.starters button{padding:12px}.welcome{margin-top:35px}.library-overview{display:none}}@media(max-width:700px){.history-panel{position:absolute;left:0;top:0;bottom:0;z-index:11;width:220px;box-shadow:10px 0 25px #1f29370f}.header-actions label{display:none}.workspace-header{height:62px}.heading h1{font-size:15px}.welcome h2{font-size:21px}.messages{padding:12px 17px}.composer-area{padding:7px 15px 12px}.answer footer{flex-wrap:wrap}.answer footer span{width:100%;margin-left:0}}
.welcome{max-width:920px;margin:clamp(38px,8vh,86px) auto 38px;padding:0 34px}.welcome-icon{padding:17px;border-radius:20px}.welcome-icon svg{width:34px;height:34px}.welcome h2{margin:24px 0 11px;font-size:31px}.welcome>p{font-size:14px}.capabilities{gap:10px;margin-top:18px}.capabilities span{padding:7px 12px;border-radius:8px;font-size:11px}.starters{gap:14px;margin-top:34px}.starters button{gap:10px;min-height:94px;padding:22px 20px;border-radius:14px}.starters button:hover{box-shadow:0 8px 22px #173f3310}.starters strong{font-size:15px}.starters span{font-size:12px;line-height:1.55}.library-overview{gap:8px;margin-top:29px}.library-overview span{padding:6px 9px;border-radius:7px;font-size:10px}
.answer-text{max-width:820px;line-height:1.85;white-space:normal}.answer-text p{margin:0 0 10px}.answer-text p:last-of-type{margin-bottom:0}.answer-text ul,.answer-text ol{margin:5px 0 12px;padding-left:23px}.answer-text li{margin:6px 0;padding-left:2px}.answer-text strong{color:light-dark(#18241f, var(--text-primary));font-weight:650}.answer-text code{padding:2px 6px;border-radius:5px;background:light-dark(#eef5f3, var(--app-surface-2));color:light-dark(#0f766e, var(--text-accent));font-family:Consolas,"Microsoft YaHei",monospace;font-size:.92em}.answer-text .answer-heading{margin:2px 0 10px;color:light-dark(#17221f, var(--text-primary));font-size:16px;font-weight:650}
@media(max-width:1200px){.welcome{max-width:820px;padding:0 24px}.welcome h2{font-size:28px}.starters button{padding:19px 16px}}
@media(max-width:980px){.starters button{min-height:0;padding:14px}}
@media(max-width:700px){.welcome h2{font-size:23px}}
</style>
