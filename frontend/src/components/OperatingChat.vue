<script setup lang="ts">
import { computed, nextTick, onActivated, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { ElInput, ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, EditPen, Collection, ArrowUp, Close, CopyDocument, ChatLineRound } from '@element-plus/icons-vue'
import OperatingAnswer from './OperatingAnswer.vue'
import type { OperatingData as Data } from './operatingCharts'

const meta = ref<Data>({ dates: [], metrics: {}, brands: [], categories: [] })
const sessions = ref<Data[]>([]), session = ref<Data | null>(null)
const query = ref(''), question = ref(''), indexQuery = ref(''), error = ref('')
const busy = ref(false), loading = ref(true), indexOpen = ref(false), historyOpen = ref(window.innerWidth > 650)
const pinned = ref<string[]>([])
const scroller = ref<HTMLElement | null>(null)
const storageKey = `operating-chat-session:${localStorage.getItem('auth_username') || localStorage.getItem('auth_real_name') || 'account'}`
const now = ref(Date.now())
const pendingTurn = computed(() => session.value?.turns.find((t: Data) => t.status === 'pending'))
const pending = computed(() => !!pendingTurn.value)
const indexed = computed(() => (session.value?.turns || []).filter((t: Data) => t.question.includes(indexQuery.value)))
const references = computed(() => (session.value?.turns || []).filter((t: Data) => pinned.value.includes(t.id)))
let timer: ReturnType<typeof setTimeout> | undefined, searchTimer: ReturnType<typeof setTimeout> | undefined
let elapsedTimer: ReturnType<typeof setInterval> | undefined
let selection = 0, searchVersion = 0, alive = true
let retryRequest: { id: string; sessionId: string; text: string; context_ids: string[] } | null = null

// crypto.randomUUID 只在 HTTPS/localhost 等安全上下文可用；http 部署时兜底生成
function newId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

async function api(path: string, init?: RequestInit) {
  const r = await fetch(`/api/operating-chat${path}`, { credentials: 'same-origin', ...init })
  const body = await r.json()
  if (!r.ok) throw Object.assign(new Error(typeof body.detail === 'string' ? body.detail : '请求失败，请稍后重试'), { status: r.status })
  return body
}
const json = (body: Data, method = 'POST') => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
async function list() {
  const version = ++searchVersion
  try { const r = await api(`/sessions?q=${encodeURIComponent(query.value)}`); if (alive && version === searchVersion) sessions.value = r.items }
  catch (e: any) { if (alive) error.value = e.message }
}
watch(query, () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => void list(), 250) })
async function bottom() {
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
}
function schedule(id: string, version: number) {
  clearTimeout(timer)
  if (!alive || !pending.value) return
  timer = setTimeout(async () => {
    try {
      const turn = session.value?.turns.find((t: Data) => t.status === 'pending')
      if (!turn) return
      const state = await api(`/sessions/${id}/turns/${turn.id}/progress`)
      if (!alive || version !== selection) return
      if (state.status !== 'pending') {
        session.value = await api(`/sessions/${id}`)
        await list()
      } else {
        Object.assign(turn, state)
      }
    } catch (e: any) { if (alive && version === selection) error.value = e.message }
    if (alive && version === selection) schedule(id, version)
  }, 650)
}
async function open(id: string) {
  const version = ++selection; clearTimeout(timer); error.value = ''; loading.value = true
  pinned.value = []; question.value = ''; retryRequest = null
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
  ++selection; clearTimeout(timer); session.value = null; pinned.value = []; question.value = ''; error.value = ''; retryRequest = null
  localStorage.removeItem(storageKey)
  loading.value = false
  if (window.innerWidth <= 650) historyOpen.value = false
}
async function send(text = question.value) {
  text = text.trim()
  if (!text || busy.value || pending.value || !meta.value.ai_configured || loading.value) return
  busy.value = true; error.value = ''
  const version = selection
  try {
    if (!session.value) { session.value = await api('/sessions', json({})); localStorage.setItem(storageKey, session.value!.id) }
    const id = session.value!.id
    const request = retryRequest && retryRequest.sessionId === id && retryRequest.text === text ? retryRequest : {
      id: newId(), sessionId: id, text, context_ids: [...pinned.value],
    }
    retryRequest = request
    const turn = await api(`/sessions/${id}/turns`, json({ question: text, request_id: request.id, context_ids: request.context_ids }))
    retryRequest = null
    if (!alive || version !== selection) return
    if (!session.value!.turns.some((t: Data) => t.id === turn.id)) session.value!.turns.push(turn)
    question.value = ''; pinned.value = []
    await list(); await bottom(); schedule(id, version)
  } catch (e: any) {
    if (alive && version === selection) {
      error.value = e.message; question.value = text
      if (e.status === 409 && session.value) {
        const id = session.value.id
        try { const s = await api(`/sessions/${id}`); if (alive && version === selection) { session.value = s; schedule(id, version) } } catch { /* The original error remains visible. */ }
      }
    }
  }
  finally { busy.value = false }
}
function keydown(event: Event | KeyboardEvent) { const e = event as KeyboardEvent; if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) { e.preventDefault(); void send() } }
function jump(id: string) { document.getElementById(`operating-turn-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
function pin(t: Data) {
  if (pinned.value.includes(t.id)) pinned.value = pinned.value.filter(id => id !== t.id)
  else if (pinned.value.length < 5) pinned.value.push(t.id)
  else ElMessage.info('每次最多引用五轮历史问答')
}
async function rename(s: Data) {
  try {
    const result = await ElMessageBox.prompt('为这段经营分析设置一个名称', '重命名对话', { inputValue: s.title, inputValidator: v => !!v?.trim() && v.trim().length <= 120, inputErrorMessage: '请输入 1–120 个字符' })
    await api(`/sessions/${s.id}`, json({ title: result.value.trim() }, 'PATCH')); await list()
    if (session.value && session.value.id === s.id) session.value.title = result.value.trim()
  } catch (e: any) { if (e instanceof Error) ElMessage.error(e.message) }
}
async function copy(t: Data) {
  try {
    const text = t.response.answer
    if (window.isSecureContext && navigator.clipboard) {
      await navigator.clipboard.writeText(text)
    } else {
      // http 非安全上下文没有 clipboard API：临时 textarea + execCommand 降级复制
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      const ok = document.execCommand('copy')
      document.body.removeChild(ta)
      if (!ok) throw new Error('copy failed')
    }
    ElMessage.success('回答已复制')
  } catch { ElMessage.error('浏览器未允许复制，请选中回答复制') }
}
// MySQL CURRENT_TIMESTAMP is returned without a timezone and represents local server time.
const timestamp = (value: string) => value ? Date.parse(value.replace(' ', 'T')) : NaN
const time = (value: string) => value ? new Date(timestamp(value)).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) : ''
const thinkingSeconds = (turn: Data) => {
  const started = timestamp(turn.created_at)
  return Number.isFinite(started) ? Math.max(0, Math.floor((now.value - started) / 1000)) : 0
}
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
      <div class="history-top"><strong>经营问答</strong><button aria-label="收起历史" class="icon-button" @click="historyOpen = false"><Collection /></button></div>
      <button class="new-chat" :disabled="busy" @click="fresh"><Plus />新对话</button>
      <el-input v-model="query" :prefix-icon="Search" clearable placeholder="搜索历史对话" maxlength="200" />
      <p class="sidebar-label">历史对话 <span>{{ sessions.length }}</span></p>
      <div class="session-list"><div v-for="s in sessions" :key="s.id" class="session-row" :class="{ active: session?.id === s.id }"><button class="session-link" :disabled="busy" :title="s.title" @click="open(s.id)"><span>{{ s.title }}</span><small>{{ time(s.updated_at) }} · {{ s.turn_count }} 轮</small></button><button class="icon-button rename" :aria-label="`重命名 ${s.title}`" @click="rename(s)"><EditPen /></button></div><p v-if="!sessions.length" class="empty-history">{{ query ? '没有匹配的历史对话' : '开始提问，分析会保存在这里' }}</p></div>
      <div class="history-footer"><ChatLineRound /><span>历史随账号保存<br><small>随时回来继续分析</small></span></div>
    </aside>
    <main class="conversation">
      <header class="chat-header"><div><button v-if="!historyOpen" class="icon-button" aria-label="展开历史" @click="historyOpen = true"><Collection /></button><h1>AI 经营问答</h1><span class="model">{{ meta.ai_configured ? '经营分析助手' : 'AI 未配置' }}</span></div><button class="index-toggle" :class="{ selected: indexOpen }" @click="indexOpen = !indexOpen"><Collection />上下文索引<span v-if="session?.turns.length">{{ session.turns.length }}</span></button></header>
      <div ref="scroller" class="conversation-scroll">
        <div v-if="!session?.turns.length" class="welcome"><span class="welcome-mark"><ChatLineRound /></span><h2>今天想了解哪些经营变化？</h2><p>从真实经营数据出发，串联问题、图表与分析。</p><div class="starters"><button @click="send('最近一个完整月成交金额同比和环比怎么样？')"><strong>看经营变化</strong><span>成交金额的同比与环比</span></button><button @click="send('最近一个完整月哪些商品成交金额最高？请分析商品结构')"><strong>找到增长机会</strong><span>商品排行与类目贡献</span></button><button @click="send('分析最近一个完整月的访客和加购变化')"><strong>分析转化表现</strong><span>访客、加购与成交趋势</span></button></div></div>
        <div v-else class="messages"><article v-for="t in session.turns" :id="`operating-turn-${t.id}`" :key="t.id" class="turn">
          <div class="user-message"><span>#{{ t.ordinal }} · {{ time(t.created_at) }}</span><p>{{ t.question }}</p></div>
          <div v-if="t.context_refs.length" class="context-refs"><span>关联上下文</span><button v-for="r in t.context_refs" :key="r.id" :title="r.question" @click="jump(r.id)">#{{ r.ordinal }}</button></div>
          <OperatingAnswer v-if="t.status === 'completed'" :message="{ ...t.response, question: t.question }" :metrics="meta.metrics" compact />
          <div v-else-if="t.status === 'pending' && t.partial_answer" class="streaming-answer"><div class="response-head"><span class="stream-avatar">AI</span><strong>经营分析助手</strong><span class="stream-state"><i></i>{{ t.stage || '正在生成回答' }} · 已思考 {{ thinkingSeconds(t) }} 秒</span></div><p>{{ t.partial_answer }}<span class="stream-cursor"></span></p><small>精确结论已先行展示，详细分析、图表与依据仍在生成</small></div>
          <div v-else-if="t.status === 'pending'" class="thinking"><span class="pulse"></span><div>{{ t.stage || '正在理解问题…' }}<small>已思考 {{ thinkingSeconds(t) }} 秒 · 问题已保存，可以稍后回来查看</small></div></div>
          <div v-else class="turn-error"><p>{{ t.error }}</p><button @click="send(t.question)">重新发送</button></div>
          <div v-if="t.status === 'completed'" class="turn-tools"><button @click="copy(t)"><CopyDocument />复制回答</button><button :class="{ selected: pinned.includes(t.id) }" @click="pin(t)"><Collection />{{ pinned.includes(t.id) ? '已加入引用' : '引用本轮' }}</button><span>已留痕 · {{ time(t.completed_at) }}</span></div>
        </article></div>
      </div>
      <div class="composer-area"><div class="composer-width"><div v-if="error" role="alert" class="request-error">{{ error }}</div><div v-if="references.length" class="pinned"><span>指定引用</span><button v-for="t in references" :key="t.id" :title="t.question" @click="pin(t)">#{{ t.ordinal }} {{ t.question.slice(0, 16) }}<Close /></button></div><form class="composer" @submit.prevent="send()"><el-input v-model="question" type="textarea" :autosize="{ minRows: 2, maxRows: 7 }" maxlength="2000" placeholder="向经营分析助手提问，或接着上一轮继续分析…" aria-label="经营问题" resize="none" @keydown="keydown" /><div class="composer-bottom"><span>{{ pending && pendingTurn ? `正在回答 · 已思考 ${thinkingSeconds(pendingTurn)} 秒` : busy ? '正在保存问题…' : 'Enter 发送 · Shift + Enter 换行' }}</span><button class="send-button" type="submit" aria-label="发送提问" :disabled="!question.trim() || busy || pending || loading || !meta.ai_configured"><ArrowUp /></button></div></form><p class="composer-note">按问题自动查询经营数据 · 追问关联历史，回答附计算证据</p></div></div>
    </main>
    <aside v-if="indexOpen" class="context-index"><div class="index-head"><strong>上下文索引</strong><button class="icon-button" aria-label="关闭索引" @click="indexOpen = false"><Close /></button></div><p>最近问答自动关联；也可指定历史轮次，辅助理解追问。</p><el-input v-model="indexQuery" :prefix-icon="Search" clearable placeholder="查找本次会话" /><div class="index-list"><section v-for="t in indexed" :key="t.id"><button class="index-link" @click="jump(t.id)"><span>#{{ t.ordinal }} <small>{{ t.status === 'completed' ? '已完成' : t.status === 'pending' ? '分析中' : '未完成' }}</small></span><strong>{{ t.question }}</strong></button><p v-if="t.response?.evidence">{{ t.response.evidence.filters.start }} 至 {{ t.response.evidence.filters.end }}<br>{{ t.response.evidence.filters.brand || '全部品牌' }}</p><button v-if="t.status === 'completed'" class="pin-button" :class="{ selected: pinned.includes(t.id) }" @click="pin(t)">{{ pinned.includes(t.id) ? '取消引用' : '引用这轮问答' }}</button></section><p v-if="!indexed.length">暂无匹配的问答</p></div></aside>
  </section>
</template>

<style scoped>
.chat-page{height:100%;min-height:0;flex:1;display:flex;background:light-dark(#fff, var(--app-surface));color:light-dark(#20252b, var(--text-primary));overflow:hidden;font-family:"Microsoft YaHei","Segoe UI",sans-serif}.history{width:245px;flex:none;display:flex;flex-direction:column;padding:20px 14px;background:light-dark(#f7f8fa, var(--app-surface-2));border-right:1px solid light-dark(#eceef1, var(--border-color));gap:14px}.history-top,.index-head{display:flex;align-items:center;justify-content:space-between;padding:0 6px;font-size:15px}button{font:inherit;cursor:pointer}button:disabled{cursor:default;opacity:.45}button svg{width:17px;height:17px;flex:none}.icon-button{display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;border:0;background:transparent;border-radius:7px;color:light-dark(#737b85, var(--text-secondary))}.icon-button:hover{background:light-dark(#e9ecef, var(--app-surface-2))}.new-chat{display:flex;align-items:center;gap:9px;border:1px solid light-dark(#e2e5e9, var(--border-color));border-radius:10px;background:light-dark(white, var(--app-surface));padding:12px;font-size:13px}.new-chat:hover{border-color:#9ea7b2}.sidebar-label{display:flex;justify-content:space-between;font-size:11px;color:light-dark(#9198a1, var(--text-secondary));margin:7px 8px 0}.session-list{overflow:auto;flex:1;min-height:0}.session-row{display:flex;border-radius:9px;position:relative;margin-bottom:5px}.session-row.active,.session-row:hover{background:light-dark(#e9edf1, var(--app-surface-2))}.session-link{border:0;background:none;display:flex;flex-direction:column;text-align:left;padding:12px 32px 12px 10px;gap:7px;min-width:0;width:100%}.session-link span{overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-size:13px}.session-link small{font-size:10px;color:light-dark(#9198a1, var(--text-secondary))}.rename{position:absolute;right:2px;top:8px;opacity:0}.session-row:hover .rename,.rename:focus-visible{opacity:1}.empty-history{font-size:12px;color:light-dark(#969da6, var(--text-secondary));line-height:1.8;padding:12px 8px}.history-footer{display:flex;align-items:center;gap:10px;font-size:12px;color:light-dark(#59636e, var(--text-secondary));border-top:1px solid light-dark(#e4e7eb, var(--border-color));padding:16px 8px 0;line-height:1.8}.history-footer svg{width:23px;height:23px}.history-footer small{color:light-dark(#9299a2, var(--text-secondary));font-size:10px}.conversation{flex:1;min-width:0;display:flex;flex-direction:column;min-height:0}.chat-header{height:64px;flex:none;display:flex;align-items:center;justify-content:space-between;padding:0 25px;gap:12px;border-bottom:1px solid light-dark(#f2f3f5, var(--border-color))}.chat-header>div{display:flex;align-items:center;gap:12px}.chat-header h1{font-size:17px;font-weight:600;margin:0}.model{font-size:10px;color:light-dark(#88929d, var(--text-secondary));border-left:1px solid light-dark(#e4e7eb, var(--border-color));padding-left:12px}.index-toggle{border:0;background:transparent;display:flex;align-items:center;gap:7px;color:light-dark(#7a838e, var(--text-secondary));font-size:12px;white-space:nowrap}.index-toggle span{background:light-dark(#eff2f5, var(--app-surface-2));padding:2px 6px;border-radius:5px}.selected{color:light-dark(#0f766e, var(--text-accent))!important}.conversation-scroll{overflow-y:auto;flex:1;min-height:0}.welcome{max-width:740px;margin:clamp(50px,12vh,150px) auto 40px;padding:0 30px;text-align:center}.welcome-mark{display:inline-flex;padding:14px;border-radius:18px;background:light-dark(#f1f7f6, var(--app-surface-2));color:light-dark(#0f766e, var(--text-accent))}.welcome-mark svg{width:29px;height:29px}.welcome h2{font-size:27px;font-weight:500;letter-spacing:1px;margin:23px 0 12px}.welcome>p{font-size:13px;color:light-dark(#939ba5, var(--text-secondary));line-height:1.8}.starters{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:35px;text-align:left}.starters button{display:flex;flex-direction:column;gap:10px;border:1px solid light-dark(#e7eaee, var(--border-color));border-radius:12px;background:light-dark(#fff, var(--app-surface));padding:20px 16px;align-items:flex-start}.starters button:hover{background:light-dark(#f8fafb, var(--app-surface-2));border-color:light-dark(#bccbc8, var(--border-color))}.starters strong{font-size:13px;font-weight:500}.starters span{font-size:11px;color:light-dark(#939ba5, var(--text-secondary))}.messages{width:100%;max-width:none;box-sizing:border-box;margin:0;padding:20px 32px 30px}.turn{scroll-margin-top:18px;margin-bottom:36px}.user-message{display:flex;flex-direction:column;align-items:flex-end;gap:8px;margin:16px 0 28px}.user-message>span{font-size:10px;color:light-dark(#a0a7af, var(--text-secondary))}.user-message p{max-width:85%;white-space:pre-wrap;overflow-wrap:anywhere;background:light-dark(#f1f3f5, var(--app-surface-2));border-radius:18px 18px 5px 18px;padding:12px 18px;margin:0;font-size:14px;line-height:1.8}.context-refs{display:flex;gap:7px;align-items:center;font-size:11px;color:light-dark(#98a1ab, var(--text-secondary));margin:0 0 15px}.context-refs button{border:0;background:light-dark(#f2f6f5, var(--app-surface-2));color:light-dark(#0f766e, var(--text-accent));font-size:11px;border-radius:5px;padding:3px 7px}.turn-tools{display:flex;align-items:center;gap:16px;margin-top:16px}.turn-tools button{display:flex;gap:5px;align-items:center;border:0;background:none;font-size:11px;color:light-dark(#929ba5, var(--text-secondary));padding:0}.turn-tools>span{margin-left:auto;font-size:10px;color:light-dark(#adb4bc, var(--text-secondary))}.thinking{display:flex;align-items:center;gap:12px;padding:10px 0 25px;font-size:14px;color:light-dark(#59636e, var(--text-secondary))}.thinking small{display:block;font-size:11px;color:light-dark(#a1a9b2, var(--text-secondary));margin-top:10px}.pulse{width:10px;height:10px;border-radius:50%;background:#0f766e;animation:pulse 1.4s infinite}@keyframes pulse{50%{opacity:.3}}.turn-error,.request-error{font-size:12px;color:light-dark(#b45309, #fbbf24);background:light-dark(#fffbeb, rgba(251, 191, 36, .12));padding:12px 16px;border-radius:8px;line-height:1.8}.turn-error button{border:0;background:none;color:light-dark(#0f766e, var(--text-accent));padding:0}.composer-area{flex:none;background:light-dark(white, var(--app-surface));padding:8px 32px 16px}.composer-width{width:100%;max-width:none;margin:0}.composer{border:1px solid light-dark(#dfe4e8, var(--border-color));border-radius:18px;background:light-dark(#fafbfc, var(--app-surface-2));padding:12px 15px;box-shadow:0 4px 16px #1a314407}.composer:focus-within{border-color:#a7bcb6}.composer :deep(.el-textarea__inner){background:transparent;box-shadow:none;padding:2px 3px;font-family:inherit;line-height:1.8;font-size:14px;color:light-dark(#293440, var(--text-primary))}.composer-bottom{display:flex;align-items:center;justify-content:space-between;margin-top:8px}.composer-bottom>span{font-size:10px;color:light-dark(#a1a9b2, var(--text-secondary))}.send-button{width:32px;height:32px;display:flex;align-items:center;justify-content:center;border:0;border-radius:10px;background:#202d2a;color:white}.send-button:disabled{background:light-dark(#e4e8eb, var(--app-surface-2));color:light-dark(#a6adb4, var(--text-secondary));opacity:1}.send-button svg{width:19px;height:19px}.composer-note{text-align:center;font-size:10px;color:light-dark(#a4acb5, var(--text-secondary));margin:11px 0 0}.pinned{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-bottom:10px;font-size:10px;color:light-dark(#98a1aa, var(--text-secondary))}.pinned button{display:flex;align-items:center;gap:6px;background:light-dark(#edf6f3, var(--app-surface-2));color:light-dark(#0f766e, var(--text-accent));border:0;border-radius:7px;padding:5px 8px;font-size:10px}.pinned svg{width:11px;height:11px}.context-index{width:265px;flex:none;border-left:1px solid light-dark(#eceef1, var(--border-color));padding:22px 16px;display:flex;flex-direction:column;gap:12px;background:light-dark(#fcfdfd, var(--app-surface-2))}.context-index p{font-size:11px;color:light-dark(#929ca6, var(--text-secondary));line-height:1.8;margin:0}.index-list{overflow:auto;flex:1;min-height:0}.index-list section{border-bottom:1px solid light-dark(#edf0f2, var(--border-color));padding:17px 4px}.index-link{display:flex;flex-direction:column;text-align:left;gap:9px;border:0;background:none;padding:0;width:100%}.index-link>span{font-size:11px;color:light-dark(#0f766e, var(--text-accent));display:flex;justify-content:space-between}.index-link small{color:light-dark(#a0a8b0, var(--text-secondary));font-size:10px}.index-link strong{font-size:12px;line-height:1.7;font-weight:500;overflow-wrap:anywhere}.index-list section p{margin-top:10px;font-size:10px}.pin-button{border:0;background:none;padding:8px 0 0;color:light-dark(#929ca6, var(--text-secondary));font-size:10px}.request-error{margin-bottom:12px}@media(max-width:1200px){.history{width:205px}.context-index{width:225px}.model{display:none}.chat-header{padding:0 18px}.messages{padding:18px 24px}}@media(max-width:900px){.history{width:180px}.context-index{position:absolute;right:0;top:0;bottom:0;z-index:10;box-shadow:-8px 0 25px #24334010;width:260px}.chat-page{position:relative}.starters{grid-template-columns:1fr}.starters button{padding:12px;gap:5px}.welcome{margin-top:40px}.welcome h2{font-size:22px}.composer-area{padding:8px 20px 14px}}@media(max-width:650px){.history{position:absolute;left:0;top:0;bottom:0;z-index:11;width:220px;box-shadow:8px 0 25px #24334010}.chat-header h1{font-size:15px}.messages{padding:12px 18px}.turn-tools{flex-wrap:wrap}.turn-tools>span{margin-left:0}.composer-bottom>span{font-size:9px}}
.streaming-answer{padding:2px 0 22px}.streaming-answer .response-head{display:flex;align-items:center;gap:10px;font-size:13px}.stream-avatar{width:27px;height:27px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;background:#0f766e;color:white;font-size:10px}.stream-state{display:flex;align-items:center;gap:5px;margin-left:auto;color:light-dark(#8b959f, var(--text-secondary));font-size:10px}.stream-state i{width:6px;height:6px;border-radius:50%;background:#0f766e;animation:pulse 1.2s infinite}.streaming-answer p{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;line-height:1.95;color:light-dark(#303943, var(--text-primary));margin:18px 0 8px;padding-left:37px}.streaming-answer>small{display:block;padding-left:37px;color:light-dark(#9aa3ad, var(--text-secondary));font-size:10px}.stream-cursor{display:inline-block;width:2px;height:1.1em;margin-left:3px;vertical-align:-2px;background:#0f766e;animation:blink .8s steps(1) infinite}@keyframes blink{50%{opacity:0}}
</style>
