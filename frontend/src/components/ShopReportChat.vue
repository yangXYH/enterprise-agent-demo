<script setup lang="ts">
import { computed, nextTick, onActivated, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { ElInput, ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, EditPen, Collection, ArrowUp, Close, CopyDocument, ChatLineRound, Shop } from '@element-plus/icons-vue'

type Meta = {
  months: string[]
  shops: { channel: string; shop_id: string; shop_name: string }[]
  fee_keys: string[]
  fee_labels: Record<string, string>
  currency: string
  ai_configured?: boolean
}
type Row = Record<string, any>
type Turn = Record<string, any>
type Session = Record<string, any>

const meta = ref<Meta>({ months: [], shops: [], fee_keys: [], fee_labels: {}, currency: 'CNY' })
const sessions = ref<Session[]>([]), session = ref<Session | null>(null)
const query = ref(''), question = ref(''), indexQuery = ref(''), error = ref('')
const busy = ref(false), loading = ref(true), historyOpen = ref(window.innerWidth > 650), indexOpen = ref(false)
const scroller = ref<HTMLElement | null>(null)
const storageKey = `shop-report-chat-session:${localStorage.getItem('auth_username') || localStorage.getItem('auth_real_name') || 'account'}`
const now = ref(Date.now())
const pendingTurn = computed(() => session.value?.turns.find((t: Turn) => t.status === 'pending'))
const pending = computed(() => !!pendingTurn.value)
const indexed = computed(() => (session.value?.turns || []).filter((t: Turn) => t.question.includes(indexQuery.value)))
let timer: ReturnType<typeof setTimeout> | undefined, searchTimer: ReturnType<typeof setTimeout> | undefined
let elapsedTimer: ReturnType<typeof setInterval> | undefined
let selection = 0, searchVersion = 0, alive = true

function newId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

async function api(path: string, init?: RequestInit) {
  const r = await fetch(`/api/shop-report-chat${path}`, { credentials: 'same-origin', ...init })
  const body = await r.json().catch(() => ({}))
  if (!r.ok) throw Object.assign(new Error(typeof body.detail === 'string' ? body.detail : '请求失败，请稍后重试'), { status: r.status })
  return body
}
const json = (body: any, method = 'POST') => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
async function list() {
  const version = ++searchVersion
  try { const r = await api(`/sessions?q=${encodeURIComponent(query.value)}`); if (alive && version === searchVersion) sessions.value = r.items }
  catch (e: any) { if (alive) error.value = e.message }
}
watch(query, () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => void list(), 250) })
async function bottom() { await nextTick(); if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight }
function schedule(id: string, version: number) {
  clearTimeout(timer)
  if (!alive || !pending.value) return
  timer = setTimeout(async () => {
    try {
      const turn = session.value?.turns.find((t: Turn) => t.status === 'pending')
      if (!turn) return
      const state = await api(`/sessions/${id}/turns/${turn.id}/progress`)
      if (!alive || version !== selection) return
      if (state.status !== 'pending') { session.value = await api(`/sessions/${id}`); await list() }
      else Object.assign(turn, state)
    } catch (e: any) { if (alive && version === selection) error.value = e.message }
    if (alive && version === selection) schedule(id, version)
  }, 650)
}
async function open(id: string) {
  const version = ++selection; clearTimeout(timer); error.value = ''; loading.value = true
  try {
    const s = await api(`/sessions/${id}`)
    if (!alive || version !== selection) return
    session.value = s; localStorage.setItem(storageKey, id); await bottom(); schedule(id, version)
    if (window.innerWidth <= 650) historyOpen.value = false
  } catch (e: any) {
    if (version === selection) { error.value = e.message; session.value = null; if (e.status === 404) localStorage.removeItem(storageKey) }
  } finally { if (version === selection) loading.value = false }
}
async function fresh() {
  ++selection; clearTimeout(timer); session.value = null; error.value = ''; question.value = ''
  localStorage.removeItem(storageKey); loading.value = false
  if (window.innerWidth <= 650) historyOpen.value = false
}
async function send(text = question.value) {
  text = text.trim()
  if (!text || busy.value || pending.value || loading.value) return
  busy.value = true; error.value = ''
  const version = selection
  try {
    if (!session.value) { session.value = await api('/sessions', json({})); localStorage.setItem(storageKey, session.value!.id) }
    const id = session.value!.id
    const turn = await api(`/sessions/${id}/turns`, json({ question: text, request_id: newId(), context_ids: [] }))
    if (!alive || version !== selection) return
    if (!session.value!.turns.some((t: Turn) => t.id === turn.id)) session.value!.turns.push(turn)
    question.value = ''
    await list(); await bottom(); schedule(id, version)
  } catch (e: any) {
    if (alive && version === selection) { error.value = e.message; question.value = text }
  } finally { busy.value = false }
}
function keydown(event: Event | KeyboardEvent) { const e = event as KeyboardEvent; if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) { e.preventDefault(); void send() } }
function jump(id: string) { document.getElementById(`shop-report-turn-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
async function rename(s: Session) {
  try {
    const result = await ElMessageBox.prompt('为这段店铺报表分析设置一个名称', '重命名对话', { inputValue: s.title, inputValidator: v => !!v?.trim() && v.trim().length <= 120, inputErrorMessage: '请输入 1–120 个字符' })
    await api(`/sessions/${s.id}`, json({ title: result.value.trim() }, 'PATCH')); await list()
    if (session.value && session.value.id === s.id) session.value.title = result.value.trim()
  } catch (e: any) { if (e instanceof Error) ElMessage.error(e.message) }
}
async function copy(t: Turn) {
  try {
    const text = t.response?.answer || ''
    if (window.isSecureContext && navigator.clipboard) await navigator.clipboard.writeText(text)
    else {
      const ta = document.createElement('textarea'); ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0'
      document.body.appendChild(ta); ta.select(); const ok = document.execCommand('copy'); document.body.removeChild(ta)
      if (!ok) throw new Error('copy failed')
    }
    ElMessage.success('回答已复制')
  } catch { ElMessage.error('浏览器未允许复制，请选中回答复制') }
}
const timestamp = (value: string) => value ? Date.parse(value.replace(' ', 'T')) : NaN
const time = (value: string) => value ? new Date(timestamp(value)).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) : ''
const thinkingSeconds = (t: Turn) => { const started = timestamp(t.created_at); return Number.isFinite(started) ? Math.max(0, Math.floor((now.value - started) / 1000)) : 0 }

onMounted(async () => {
  elapsedTimer = setInterval(() => { now.value = Date.now() }, 1000)
  try {
    meta.value = await api('/metadata')
    await list(); const id = localStorage.getItem(storageKey); if (id) await open(id)
  } catch (e: any) { error.value = e.message }
  finally { loading.value = false }
})
onActivated(() => { void bottom() })
onBeforeUnmount(() => { alive = false; ++selection; clearTimeout(timer); clearTimeout(searchTimer); clearInterval(elapsedTimer) })
</script>

<template>
  <section class="chat-page">
    <aside v-if="historyOpen" class="history">
      <div class="history-top"><strong>店铺报表问答</strong><button aria-label="收起历史" class="icon-button" @click="historyOpen = false"><Collection /></button></div>
      <button class="new-chat" :disabled="busy" @click="fresh"><Plus />新对话</button>
      <el-input v-model="query" :prefix-icon="Search" clearable placeholder="搜索历史对话" maxlength="200" />
      <p class="sidebar-label">历史对话 <span>{{ sessions.length }}</span></p>
      <div class="session-list">
        <div v-for="s in sessions" :key="s.id" class="session-row" :class="{ active: session?.id === s.id }">
          <button class="session-link" :disabled="busy" :title="s.title" @click="open(s.id)"><span>{{ s.title }}</span><small>{{ time(s.updated_at) }} · {{ s.turn_count }} 轮</small></button>
          <button class="icon-button rename" :aria-label="`重命名 ${s.title}`" @click="rename(s)"><EditPen /></button>
        </div>
        <p v-if="!sessions.length" class="empty-history">{{ query ? '没有匹配的历史对话' : '开始提问，分析会保存在这里' }}</p>
      </div>
      <div class="history-footer"><ChatLineRound /><span>历史随账号保存<br><small>随时回来继续分析</small></span></div>
    </aside>
    <main class="conversation">
      <header class="chat-header">
        <div><button v-if="!historyOpen" class="icon-button" aria-label="展开历史" @click="historyOpen = true"><Collection /></button><h1>店铺报表 AI 问答</h1><span class="model">{{ meta.ai_configured ? '店铺经营助手' : 'AI 未配置' }}</span></div>
        <button class="index-toggle" :class="{ selected: indexOpen }" @click="indexOpen = !indexOpen"><Collection />上下文索引<span v-if="session?.turns.length">{{ session.turns.length }}</span></button>
      </header>
      <div ref="scroller" class="conversation-scroll">
        <div v-if="!session?.turns.length" class="welcome">
          <span class="welcome-mark"><Shop /></span>
          <h2>今天想了解店铺的经营与费用？</h2>
          <p>基于店铺报表快照，直接回答各店收入、毛利、费用、净利与原因分析。</p>
          <div class="starters">
            <button @click="send('最近一个完整月各店铺项目净利排名')"><strong>看盈利排名</strong><span>各店铺项目净利排行</span></button>
            <button @click="send('8月哪些店铺亏损了？分析原因')"><strong>找亏损原因</strong><span>亏损店铺与环比变化</span></button>
            <button @click="send('最近一个月费用最高的店铺及费用结构')"><strong>看费用结构</strong><span>各项费用构成与占比</span></button>
            <button @click="send('测试箱包8月经营数据怎么样')"><strong>看店铺经营</strong><span>单店收入、毛利、费用与净利</span></button>
          </div>
        </div>
        <div v-else class="messages">
          <article v-for="t in session.turns" :id="`shop-report-turn-${t.id}`" :key="t.id" class="turn">
            <div class="user-message"><span>#{{ t.ordinal }} · {{ time(t.created_at) }}</span><p>{{ t.question }}</p></div>
            <div v-if="t.status === 'completed'" class="answer-card">
              <div class="response-head"><span class="avatar">AI</span><strong>店铺经营助手</strong><el-tag v-if="t.response?.evidence" type="success" size="small">已查询店铺报表数据</el-tag></div>
              <p v-if="t.response?.report?.understood_as" class="understood">问题理解：{{ t.response.report.understood_as }}</p>
              <div v-if="t.response?.report?.highlights?.length" class="report-highlights">
                <article v-for="(card, i) in t.response.report.highlights" :key="i"><span>{{ card.label }}</span><strong>{{ card.value }}</strong><small>{{ card.note }}</small></article>
              </div>
              <section v-for="(section, i) in t.response?.report?.sections || []" :key="i" class="report-section" :class="{ direct: i === 0 }">
                <h4>{{ section.title }}</h4><p v-for="(p, j) in section.paragraphs" :key="`p${j}`">{{ p }}</p>
                <ul v-if="section.bullets.length"><li v-for="(b, j) in section.bullets" :key="`b${j}`">{{ b }}</li></ul>
              </section>
              <details v-if="t.response?.report?.tables?.length" class="report-tables"><summary>查看数据表</summary>
                <section v-for="(table, ti) in t.response.report.tables" :key="ti"><h4>{{ table.title }}<small v-if="table.total_rows > table.rows.length">展示 {{ table.rows.length }} / {{ table.total_rows }} 条</small></h4>
                  <table class="data-table"><thead><tr><th v-for="col in table.columns" :key="col.key">{{ col.label }}</th></tr></thead><tbody><tr v-for="(row, ri) in table.rows" :key="ri"><td v-for="col in table.columns" :key="col.key">{{ row[col.key] }}</td></tr></tbody></table>
                </section>
              </details>
              <section v-if="t.response?.report?.limitations?.length" class="limitations"><h4>口径与限制</h4><ul><li v-for="(item, i) in t.response.report.limitations" :key="i">{{ item }}</li></ul></section>
              <div class="turn-tools"><button @click="copy(t)"><CopyDocument />复制回答</button><span>已留痕 · {{ time(t.completed_at) }}</span></div>
            </div>
            <div v-else-if="t.status === 'pending' && t.partial_answer" class="streaming-answer">
              <div class="response-head"><span class="stream-avatar">AI</span><strong>店铺经营助手</strong><span class="stream-state"><i></i>{{ t.stage || '正在生成回答' }} · 已思考 {{ thinkingSeconds(t) }} 秒</span></div>
              <p>{{ t.partial_answer }}<span class="stream-cursor"></span></p><small>精确结论已先行展示，详细分析仍在生成</small>
            </div>
            <div v-else-if="t.status === 'pending'" class="thinking"><span class="pulse"></span><div>{{ t.stage || '正在理解问题…' }}<small>已思考 {{ thinkingSeconds(t) }} 秒 · 问题已保存，可以稍后回来查看</small></div></div>
            <div v-else class="turn-error"><p>{{ t.error }}</p><button @click="send(t.question)">重新发送</button></div>
          </article>
        </div>
      </div>
      <div class="composer-area"><div class="composer-width">
        <div v-if="error" role="alert" class="request-error">{{ error }}</div>
        <form class="composer" @submit.prevent="send()">
          <el-input v-model="question" type="textarea" :autosize="{ minRows: 2, maxRows: 7 }" maxlength="2000" placeholder="向店铺经营助手提问，如：8月哪些店铺亏损、测试箱包推广费、各店净利排名…" aria-label="店铺报表问题" resize="none" @keydown="keydown" />
          <div class="composer-bottom"><span>{{ pending && pendingTurn ? `正在回答 · 已思考 ${thinkingSeconds(pendingTurn)} 秒` : busy ? '正在保存问题…' : 'Enter 发送 · Shift + Enter 换行' }}</span><button class="send-button" type="submit" aria-label="发送提问" :disabled="!question.trim() || busy || pending || loading"><ArrowUp /></button></div>
        </form>
        <p class="composer-note">按店铺报表统一口径查询 · 回答附计算证据与数据表</p>
      </div></div>
    </main>
    <aside v-if="indexOpen" class="context-index">
      <div class="index-head"><strong>上下文索引</strong><button class="icon-button" aria-label="关闭索引" @click="indexOpen = false"><Close /></button></div>
      <p>本次会话的问答记录，方便回顾已分析的问题。</p>
      <el-input v-model="indexQuery" :prefix-icon="Search" clearable placeholder="查找本次会话" />
      <div class="index-list"><section v-for="t in indexed" :key="t.id">
        <button class="index-link" @click="jump(t.id)"><span>#{{ t.ordinal }} <small>{{ t.status === 'completed' ? '已完成' : t.status === 'pending' ? '分析中' : '未完成' }}</small></span><strong>{{ t.question }}</strong></button>
        <p v-if="t.response?.report?.understood_as">{{ t.response.report.understood_as }}</p>
      </section><p v-if="!indexed.length">暂无匹配的问答</p></div>
    </aside>
  </section>
</template>

<style scoped>
.chat-page{height:100%;min-height:0;flex:1;display:flex;background:light-dark(#fff, var(--app-surface));color:light-dark(#20252b, var(--text-primary));overflow:hidden;font-family:"Microsoft YaHei","Segoe UI",sans-serif}
.history{width:245px;flex:none;display:flex;flex-direction:column;padding:20px 14px;background:light-dark(#f7f8fa, var(--app-surface-2));border-right:1px solid light-dark(#eceef1, var(--border-color));gap:14px}
.history-top,.index-head{display:flex;align-items:center;justify-content:space-between;padding:0 6px;font-size:15px}
button{font:inherit;cursor:pointer}button:disabled{cursor:default;opacity:.45}button svg{width:17px;height:17px;flex:none}
.icon-button{display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;border:0;background:transparent;border-radius:7px;color:light-dark(#737b85, var(--text-secondary))}
.icon-button:hover{background:light-dark(#e9ecef, var(--app-surface-2))}
.new-chat{display:flex;align-items:center;gap:9px;border:1px solid light-dark(#e2e5e9, var(--border-color));border-radius:10px;background:light-dark(white, var(--app-surface));padding:12px;font-size:13px}.new-chat:hover{border-color:#9ea7b2}
.sidebar-label{display:flex;justify-content:space-between;font-size:11px;color:light-dark(#9198a1, var(--text-secondary));margin:7px 8px 0}
.session-list{overflow:auto;flex:1;min-height:0}.session-row{display:flex;border-radius:9px;position:relative;margin-bottom:5px}
.session-row.active,.session-row:hover{background:light-dark(#e9edf1, var(--app-surface-2))}
.session-link{border:0;background:none;display:flex;flex-direction:column;text-align:left;padding:12px 32px 12px 10px;gap:7px;min-width:0;width:100%}
.session-link span{overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-size:13px}
.session-link small{font-size:10px;color:light-dark(#9198a1, var(--text-secondary))}
.rename{position:absolute;right:2px;top:8px;opacity:0}.session-row:hover .rename,.rename:focus-visible{opacity:1}
.empty-history{font-size:12px;color:light-dark(#969da6, var(--text-secondary));line-height:1.8;padding:12px 8px}
.history-footer{display:flex;align-items:center;gap:10px;font-size:12px;color:light-dark(#59636e, var(--text-secondary));border-top:1px solid light-dark(#e4e7eb, var(--border-color));padding:16px 8px 0;line-height:1.8}.history-footer svg{width:23px;height:23px}.history-footer small{color:light-dark(#9299a2, var(--text-secondary));font-size:10px}
.conversation{flex:1;min-width:0;display:flex;flex-direction:column;min-height:0}
.chat-header{height:64px;flex:none;display:flex;align-items:center;justify-content:space-between;padding:0 25px;gap:12px;border-bottom:1px solid light-dark(#f2f3f5, var(--border-color))}.chat-header>div{display:flex;align-items:center;gap:12px}
.chat-header h1{font-size:17px;font-weight:600;margin:0}.model{font-size:10px;color:light-dark(#88929d, var(--text-secondary));border-left:1px solid light-dark(#e4e7eb, var(--border-color));padding-left:12px}
.index-toggle{border:0;background:transparent;display:flex;align-items:center;gap:7px;color:light-dark(#7a838e, var(--text-secondary));font-size:12px;white-space:nowrap}
.index-toggle span{background:light-dark(#eff2f5, var(--app-surface-2));padding:2px 6px;border-radius:5px}.selected{color:light-dark(#0f766e, var(--text-accent))!important}
.conversation-scroll{overflow-y:auto;flex:1;min-height:0}
.welcome{max-width:760px;margin:clamp(50px,12vh,150px) auto 40px;padding:0 30px;text-align:center}
.welcome-mark{display:inline-flex;padding:14px;border-radius:18px;background:light-dark(#f1f7f6, var(--app-surface-2));color:light-dark(#0f766e, var(--text-accent))}.welcome-mark svg{width:29px;height:29px}
.welcome h2{font-size:27px;font-weight:500;letter-spacing:1px;margin:23px 0 12px}.welcome>p{font-size:13px;color:light-dark(#939ba5, var(--text-secondary));line-height:1.8}
.starters{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-top:35px;text-align:left}
.starters button{display:flex;flex-direction:column;gap:10px;border:1px solid light-dark(#e7eaee, var(--border-color));border-radius:12px;background:light-dark(#fff, var(--app-surface));padding:20px 16px;align-items:flex-start}
.starters button:hover{background:light-dark(#f8fafb, var(--app-surface-2));border-color:light-dark(#bccbc8, var(--border-color))}
.starters strong{font-size:13px;font-weight:500}.starters span{font-size:11px;color:light-dark(#939ba5, var(--text-secondary))}
.messages{width:100%;max-width:none;box-sizing:border-box;margin:0;padding:20px 32px 30px}
.turn{scroll-margin-top:18px;margin-bottom:36px}
.user-message{display:flex;flex-direction:column;align-items:flex-end;gap:8px;margin:16px 0 20px}
.user-message>span{font-size:10px;color:light-dark(#a0a7af, var(--text-secondary))}
.user-message p{max-width:85%;white-space:pre-wrap;overflow-wrap:anywhere;background:light-dark(#f1f3f5, var(--app-surface-2));border-radius:18px 18px 5px 18px;padding:12px 18px;margin:0;font-size:14px;line-height:1.8}
.answer-card{border:1px solid light-dark(#e2e8f0, var(--border-color));border-radius:14px;background:light-dark(white, var(--app-surface));overflow:hidden;padding:22px}
.response-head{display:flex;align-items:center;gap:10px;font-size:14px}.avatar{width:27px;height:27px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;background:#0f766e;color:white;font-size:10px}
.understood{font-size:11px;color:light-dark(#8a949f, var(--text-secondary));margin:10px 0 18px}
.report-highlights{display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr));gap:1px;background:light-dark(#e7ebee, var(--app-surface-2));border:1px solid light-dark(#e7ebee, var(--border-color));border-radius:12px;overflow:hidden;margin:18px 0 24px}
.report-highlights article{background:light-dark(#fff, var(--app-surface));padding:16px;display:flex;flex-direction:column;gap:8px}
.report-highlights span,.report-highlights small{font-size:11px;color:light-dark(#7c8793, var(--text-secondary))}
.report-highlights strong{font-size:17px;line-height:1.45;color:light-dark(#0f766e, var(--text-accent));overflow-wrap:anywhere}
.report-section{margin:25px 0}.report-section.direct{border-left:3px solid #0f766e;padding:4px 0 4px 17px}
.report-section h4{font-size:15px}.report-section p,.report-section li,.limitations li{font-size:14px;line-height:1.95;color:light-dark(#303943, var(--text-primary));white-space:pre-wrap}
.report-section ul,.limitations ul{padding-left:20px}
.limitations{background:light-dark(#f8fafb, var(--app-surface-2));border-radius:10px;padding:14px 18px;margin-top:20px}
.report-tables{margin-top:22px;border-top:1px solid light-dark(#edf2f7, var(--border-color));padding-top:18px}
.report-tables summary{cursor:pointer;color:light-dark(#0f766e, var(--text-accent));font-size:13px}
.report-tables h4{font-size:14px;margin:18px 0 8px}.report-tables h4 small{font-weight:400;color:light-dark(#98a1ab, var(--text-secondary));margin-left:10px}
.data-table{width:100%;border-collapse:collapse;font-size:12px}
.data-table th,.data-table td{border:1px solid light-dark(#e7eaee, var(--border-color));padding:8px 10px;text-align:left}
.data-table th{background:light-dark(#f7f8fa, var(--app-surface-2));color:light-dark(#59636e, var(--text-secondary))}
.turn-tools{display:flex;align-items:center;gap:16px;margin-top:16px}
.turn-tools button{display:flex;gap:5px;align-items:center;border:0;background:none;font-size:11px;color:light-dark(#929ba5, var(--text-secondary));padding:0}
.turn-tools>span{margin-left:auto;font-size:10px;color:light-dark(#adb4bc, var(--text-secondary))}
.thinking{display:flex;align-items:center;gap:12px;padding:10px 0 25px;font-size:14px;color:light-dark(#59636e, var(--text-secondary))}.thinking small{display:block;font-size:11px;color:light-dark(#a1a9b2, var(--text-secondary));margin-top:10px}
.pulse{width:10px;height:10px;border-radius:50%;background:#0f766e;animation:pulse 1.4s infinite}@keyframes pulse{50%{opacity:.3}}
.turn-error,.request-error{font-size:12px;color:light-dark(#b45309, #fbbf24);background:light-dark(#fffbeb, rgba(251, 191, 36, .12));padding:12px 16px;border-radius:8px;line-height:1.8}.turn-error button{border:0;background:none;color:light-dark(#0f766e, var(--text-accent));padding:0}
.composer-area{flex:none;background:light-dark(white, var(--app-surface));padding:8px 32px 16px}
.composer{border:1px solid light-dark(#dfe4e8, var(--border-color));border-radius:18px;background:light-dark(#fafbfc, var(--app-surface-2));padding:12px 15px;box-shadow:0 4px 16px #1a314407}
.composer:focus-within{border-color:#a7bcb6}.composer :deep(.el-textarea__inner){background:transparent;box-shadow:none;padding:2px 3px;font-family:inherit;line-height:1.8;font-size:14px;color:light-dark(#293440, var(--text-primary))}
.composer-bottom{display:flex;align-items:center;justify-content:space-between;margin-top:8px}.composer-bottom>span{font-size:10px;color:light-dark(#a1a9b2, var(--text-secondary))}
.send-button{width:32px;height:32px;display:flex;align-items:center;justify-content:center;border:0;border-radius:10px;background:#202d2a;color:white}.send-button:disabled{background:light-dark(#e4e8eb, var(--app-surface-2));color:light-dark(#a6adb4, var(--text-secondary));opacity:1}.send-button svg{width:19px;height:19px}
.composer-note{text-align:center;font-size:10px;color:light-dark(#a4acb5, var(--text-secondary));margin:11px 0 0}
.streaming-answer{padding:2px 0 22px}.streaming-answer .response-head{display:flex;align-items:center;gap:10px;font-size:13px}
.stream-avatar{width:27px;height:27px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;background:#0f766e;color:white;font-size:10px}
.stream-state{display:flex;align-items:center;gap:5px;margin-left:auto;color:light-dark(#8b959f, var(--text-secondary));font-size:10px}.stream-state i{width:6px;height:6px;border-radius:50%;background:#0f766e;animation:pulse 1.2s infinite}
.streaming-answer p{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;line-height:1.95;color:light-dark(#303943, var(--text-primary));margin:18px 0 8px;padding-left:37px}
.streaming-answer>small{display:block;padding-left:37px;color:light-dark(#9aa3ad, var(--text-secondary));font-size:10px}
.stream-cursor{display:inline-block;width:2px;height:1.1em;margin-left:3px;vertical-align:-2px;background:#0f766e;animation:blink .8s steps(1) infinite}@keyframes blink{50%{opacity:0}}
.context-index{width:265px;flex:none;border-left:1px solid light-dark(#eceef1, var(--border-color));padding:22px 16px;display:flex;flex-direction:column;gap:12px;background:light-dark(#fcfdfd, var(--app-surface-2))}
.context-index p{font-size:11px;color:light-dark(#929ca6, var(--text-secondary));line-height:1.8;margin:0}.index-list{overflow:auto;flex:1;min-height:0}
.index-list section{border-bottom:1px solid light-dark(#edf0f2, var(--border-color));padding:17px 4px}
.index-link{display:flex;flex-direction:column;text-align:left;gap:9px;border:0;background:none;padding:0;width:100%}
.index-link>span{font-size:11px;color:light-dark(#0f766e, var(--text-accent));display:flex;justify-content:space-between}.index-link small{color:light-dark(#a0a8b0, var(--text-secondary));font-size:10px}
.index-link strong{font-size:12px;line-height:1.7;font-weight:500;overflow-wrap:anywhere}.index-list section p{margin-top:10px;font-size:10px}
.request-error{margin-bottom:12px}
@media(max-width:1200px){.history{width:205px}.context-index{width:225px}.model{display:none}.chat-header{padding:0 18px}.messages{padding:18px 24px}}
@media(max-width:900px){.history{width:180px}.context-index{position:absolute;right:0;top:0;bottom:0;z-index:10;box-shadow:-8px 0 25px #24334010;width:260px}.chat-page{position:relative}.starters{grid-template-columns:1fr}.starters button{padding:12px;gap:5px}.welcome{margin-top:40px}.welcome h2{font-size:22px}.composer-area{padding:8px 20px 14px}}
@media(max-width:650px){.history{position:absolute;left:0;top:0;bottom:0;z-index:11;width:220px;box-shadow:8px 0 25px #24334010}.chat-header h1{font-size:15px}.messages{padding:12px 18px}.turn-tools{flex-wrap:wrap}.turn-tools>span{margin-left:0}.composer-bottom>span{font-size:9px}.report-highlights{grid-template-columns:1fr}}
</style>
