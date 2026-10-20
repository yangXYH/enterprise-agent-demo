<template>
  <div class="ecom-dashboard-frame">
    <iframe
      ref="frameRef"
      src="/ecommerce-dashboard.html?sb=0"
      title="电商中台看板"
      loading="eager"
      @load="onFrameLoad"
    />
    <Teleport to="body">
      <div
        v-if="preview"
        class="ecom-preview-overlay"
        role="dialog"
        aria-modal="true"
        @click.self="closePreview"
      >
        <div class="ecom-preview-drawer">
          <header class="ecom-preview-head">
            <span class="ecom-preview-title">{{ preview.name || '预览' }}</span>
            <button
              type="button"
              class="ecom-preview-close"
              data-ecom-preview-close
              @click="closePreview"
            >
              关闭
            </button>
          </header>
          <div class="ecom-preview-body">
            <div
              v-if="preview.kind === 'image'"
              class="ecom-preview-img"
            >
              <img :src="preview.url" :alt="preview.name || ''" />
            </div>
            <div
              v-else-if="preview.kind === 'pdf'"
              class="ecom-preview-iframe"
            >
              <iframe
                :src="preview.url"
                :title="preview.name || 'PDF预览'"
              ></iframe>
            </div>
            <pre
              v-else-if="preview.kind === 'text' || preview.kind === 'doc'"
              class="ecom-preview-text"
            >{{ preview.content || '(无内容)' }}</pre>
            <div
              v-else-if="preview.kind === 'html'"
              class="ecom-preview-html"
              v-html="preview.html || '(无内容)'"
            ></div>
            <div v-else class="ecom-preview-err">
              {{ preview.message || '该文件类型暂不支持在线预览' }}
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'

const props = defineProps<{ allowedRoutes: string[]; theme: 'dark' | 'light' }>()

const emit = defineEmits<{
  (e: 'open-knowledge-qa'): void
  (e: 'open-external', menu: string): void
  (e: 'route-change', route: string): void
  (e: 'frame-ready'): void
}>()

interface EcomPreviewPayload {
  type?: 'image' | 'pdf' | 'text' | 'doc' | 'html' | 'error' | 'unsupported'
  name?: string
  url?: string
  content?: string
  html?: string
  message?: string
  ext?: string
}

interface EcomPreviewState extends EcomPreviewPayload {
  kind: string
  name: string
}

const frameRef = ref<HTMLIFrameElement | null>(null)
const preview = ref<EcomPreviewState | null>(null)
const frameReady = ref(false)

function postToFrame(payload: unknown) {
  const frame = frameRef.value
  if (!frame || !frame.contentWindow) return
  try {
    frame.contentWindow.postMessage(payload, '*')
  } catch (_e) {
    /* ignore */
  }
}

function onFrameLoad() {
  frameReady.value = true
  postToFrame({ type: 'ecom-theme', theme: props.theme })
  postToFrame({ type: 'ecom-permissions', routes: props.allowedRoutes })
  emit('frame-ready')
}

watch(() => props.allowedRoutes, routes => {
  if (frameReady.value) postToFrame({ type: 'ecom-permissions', routes })
})

watch(() => props.theme, theme => {
  if (frameReady.value) postToFrame({ type: 'ecom-theme', theme })
})

// 由主壳侧边栏调用：通知电商中台 iframe 切换到指定路由（嵌入模式）
function navigateTo(route: string) {
  if (!route) return
  postToFrame({ type: 'ecom-set-route', route })
}

defineExpose({ navigateTo })

async function handleMessage(ev: MessageEvent) {
  // 同源校验：仅接受当前 iframe 发送的消息
  const frame = frameRef.value
  if (!frame || ev.source !== frame.contentWindow) return
  const msg = ev.data
  if (!msg || typeof msg !== 'object') return

  if (msg.type === 'ecom-preview-open') {
    const data = (msg.data || {}) as EcomPreviewPayload
    preview.value = {
      ...data,
      kind: String(data.type || ''),
      name: String(msg.name || data.name || ''),
    }
    return
  }
  if (msg.type === 'ecom-preview-close') {
    preview.value = null
    return
  }

  // 通知父层切换到 AI 知识问答路由
  if (msg.type === 'ecom-knowledge-qa-open') {
    emit('open-knowledge-qa')
    return
  }

  // 电商中台侧边栏点击外部模块（项目看板/库存/简历）时，通知父壳在主壳打开对应页面
  if (msg.type === 'ecom-external-open') {
    emit('open-external', String(msg.menu || ''))
    return
  }

  // 嵌入模式下 iframe 内部路由变化，回传主壳用于侧边栏高亮
  if (msg.type === 'ecom-route-change') {
    emit('route-change', String(msg.route || ''))
    return
  }

  // 企业版 alert/confirm 通道：iframe 内 ecomAlert / ecomConfirm 通过 postMessage 把提示/确认抛到这里
  if (msg.type === 'ecom-alert' || msg.type === 'ecom-confirm') {
    const id = msg.id
    const message = String(msg.message || '')
    const title = String(msg.title || (msg.type === 'ecom-alert' ? '提示' : '确认'))
    if (id == null) return
    let ok = false
    try {
      if (msg.type === 'ecom-alert') {
        await ElMessageBox.alert(message, title, {
          confirmButtonText: '确定',
          type: 'warning',
          customClass: 'ecom-messagebox',
        })
        ok = true
      } else {
        try {
          await ElMessageBox.confirm(message, title, {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            type: 'warning',
            customClass: 'ecom-messagebox',
          })
          ok = true
        } catch (_canceled) {
          ok = false
        }
      }
    } catch (_err) {
      ok = false
    }
    postToFrame({ type: 'ecom-dialog-result', id, ok })
  }
}

function closePreview() {
  preview.value = null
}

function onKeydown(ev: KeyboardEvent) {
  if (ev.key === 'Escape' && preview.value) {
    closePreview()
  }
}

onMounted(() => {
  window.addEventListener('message', handleMessage)
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('message', handleMessage)
  window.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
.ecom-dashboard-frame {
  width: 100%;
  height: calc(100vh - 150px);
  min-height: 720px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--app-bg);
  position: relative;
}
iframe {
  display: block;
  width: 100%;
  height: 100%;
  border: 0;
}

/* 穿透 iframe：在父层渲染的全屏遮罩，确保覆盖外层 SPA 的顶栏与侧栏 */
.ecom-preview-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.62);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: ecomPvFade 0.18s ease;
}
.ecom-preview-drawer {
  width: min(94vw, 1500px);
  height: 92vh;
  max-height: 92vh;
  background: var(--app-surface);
  border-radius: 12px;
  box-shadow: 0 24px 70px rgba(15, 23, 42, 0.38);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: ecomPvIn 0.2s ease;
}
@keyframes ecomPvFade {
  from { opacity: 0; }
  to { opacity: 1; }
}
@keyframes ecomPvIn {
  from { opacity: 0; transform: scale(0.96); }
  to { opacity: 1; transform: scale(1); }
}
.ecom-preview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}
.ecom-preview-title {
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.ecom-preview-close {
  border: 1px solid var(--border-color);
  background: var(--app-surface);
  border-radius: 6px;
  padding: 5px 12px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  flex-shrink: 0;
}
.ecom-preview-close:hover {
  border-color: #4f6ef7;
  color: #4f6ef7;
}
.ecom-preview-body {
  flex: 1;
  overflow: auto;
  padding: 18px;
  min-height: 0;
  color: var(--text-primary);
  font-size: 14px;
}
.ecom-preview-img {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
}
.ecom-preview-img img {
  max-width: 100%;
  max-height: calc(92vh - 130px);
  border-radius: 6px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04), 0 1px 3px rgba(16, 24, 40, 0.06);
}
.ecom-preview-iframe {
  height: calc(92vh - 96px);
}
.ecom-preview-iframe iframe {
  width: 100%;
  height: 100%;
  border: 1px solid var(--border-color);
  border-radius: 6px;
}
.ecom-preview-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-primary);
  background: var(--app-bg);
  padding: 16px;
  border-radius: 8px;
}
.ecom-preview-html {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-primary);
}
.ecom-preview-html :deep(table) {
  width: 100%;
  border-collapse: collapse;
}
.ecom-preview-html :deep(th),
.ecom-preview-html :deep(td) {
  border: 1px solid var(--border-color);
  padding: 8px 12px;
  text-align: left;
}
.ecom-preview-html :deep(th) {
  background: var(--table-header-bg);
  font-weight: 600;
  color: var(--table-header-text);
}
.ecom-preview-html :deep(.pv-xlsx),
.ecom-preview-html :deep(.pv-doc) {
  overflow: auto;
}
/* Excel 预览专用：保留服务端生成的列宽/对齐方式 */
.ecom-preview-html :deep(.pv-xlsx) > table {
  width: auto;
  table-layout: fixed;
}
.ecom-preview-html :deep(.pv-xlsx) td,
.ecom-preview-html :deep(.pv-xlsx) th {
  /* 单元格内的对齐/换行由服务端在 inline style 里指定，不要再被通用规则压成 left */
  text-align: inherit;
  padding: 6px 10px;
  vertical-align: middle;
}
.ecom-preview-html :deep(.pv-h1) {
  font-size: 20px;
  font-weight: 700;
  margin: 8px 0 10px;
}
.ecom-preview-html :deep(.pv-h2) {
  font-size: 17px;
  font-weight: 600;
  margin: 8px 0 8px;
}
.ecom-preview-html :deep(.pv-h3) {
  font-size: 15px;
  font-weight: 600;
  color: #5b6472;
  margin: 6px 0 6px;
}
.ecom-preview-html :deep(.pv-p) {
  margin: 4px 0;
}
.ecom-preview-html :deep(.pv-ul) {
  margin: 4px 0;
  padding-left: 22px;
}
.ecom-preview-html :deep(.pv-li) {
  margin: 2px 0;
}
.ecom-preview-html :deep(.pv-note) {
  color: #98a0ae;
  text-align: center;
  padding: 20px;
}
.ecom-preview-err {
  padding: 40px;
  color: #e5484d;
  text-align: center;
}
</style>
