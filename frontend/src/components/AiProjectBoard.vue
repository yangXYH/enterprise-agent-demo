<script setup lang="ts">
import { ref, watch } from 'vue'

const props = withDefaults(defineProps<{ theme?: 'light' | 'dark' }>(), {
  theme: 'light',
})
const frame = ref<HTMLIFrameElement | null>(null)

function syncFrameTheme() {
  frame.value?.contentWindow?.postMessage(
    { type: 'ecom-theme', theme: props.theme },
    window.location.origin,
  )
}

watch(() => props.theme, syncFrameTheme)
</script>

<template>
  <div class="daily-board-frame">
    <iframe
      ref="frame"
      src="/ai-project-daily-board.html"
      title="AI 项目进度看板"
      loading="eager"
      @load="syncFrameTheme"
    />
  </div>
</template>

<style scoped>
.daily-board-frame {
  width: 100%;
  height: calc(100vh - 150px);
  min-height: 720px;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: light-dark(#f3f4f6, var(--app-bg));
}

iframe {
  display: block;
  width: 100%;
  height: 100%;
  border: 0;
}
</style>
