<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  ElButton,
  ElCard,
  ElDatePicker,
  ElDrawer,
  ElEmpty,
  ElIcon,
  ElInput,
  ElMessage,
  ElOption,
  ElPopconfirm,
  ElSelect,
  ElTable,
  ElTableColumn,
  ElTag,
  ElTimePicker,
  ElUpload,
} from 'element-plus'
import { Download, Loading, Plus, Refresh, Search, UploadFilled } from '@element-plus/icons-vue'
import type { UploadUserFile } from 'element-plus'
import axios from 'axios'
import request from '../../utils/request'

// ── 招聘总览（KPI）───────────────────────────────────────────────────────────
const kpis = ref<Record<string, any> | null>(null)

const loadDashboard = async () => {
  try {
    const k = await request.get('/hr/recruit/dashboard') as any
    kpis.value = k?.kpis || null
  } catch {
    kpis.value = null
  }
}

// ── 简历跟进看板（面试邀约登记）─────────────────────────────────────────────
interface InterviewRow {
  uid: string
  id: number
  dirty: boolean
  saving: boolean
  name: string
  position: string
  gender: string
  age: string
  birthday: string
  phone: string
  first_interview_date: string
  first_interview_time: string
  second_interview_date: string
  second_interview_time: string
  is_present: string
  interview_status: string
  hire_status: string
  join_date: string
  inviter: string
  remark: string
  archived: number  // 0=active 1=archived
  archived_at: string
}

// 面试情况 / 问题情况 下拉选项（可选也可手填自定义值）
const interviewStatusOptions = [
  '初筛未通过',
  '一面未通过',
  '二面未通过',
  '面试进行中候选人主动放弃',
  '面试进行中公司主动终止',
  '面试已完成，进入offer沟通环节未达成一致',
  '面试已完成，作为备选池',
  '候选人爽约',
  '候选人多次改期，最终未面成',
  '已发offer，候选人拒接',
  '已发offer，背调未通过后撤回',
  '已发offer，候选人入职当天未到',
  '面试通过，已录用',
  '面试通过，待定',
  '面试通过，但HC暂缓入职',
]
const issueStatusOptions = [
  '薪酬类',
  '人岗匹配类（硬技能/经验）',
  '个人原因类（软素质/态度）',
  '编制/HC类',
  '稳定性/跳槽频率类',
  '背调/材料真实性类',
  '综合对比劣势类（有更优候选人）',
  '客观/突发因素类',
]

// 面试通过类状态：无需填问题情况；有问题的候选人不会有入职时间
const PASS_INTERVIEW_STATUSES = new Set([
  '面试通过，已录用',
  '面试通过，待定',
  '面试通过，但HC暂缓入职',
])
const isPassInterview = (v?: string) => !!v && PASS_INTERVIEW_STATUSES.has(String(v))

const onInterviewStatusChange = (row: InterviewRow) => {
  markDirty(row)
  if (isPassInterview(row.interview_status)) {
    // 面试通过类无需填问题情况：清空已填的问题情况
    if (row.hire_status) {
      row.hire_status = ''
    }
  } else {
    // 非通过类（未填写或其他状态）不能有入职时间：清空入职时间
    if (row.join_date) {
      row.join_date = ''
    }
  }
}

const onIssueStatusChange = (row: InterviewRow) => {
  markDirty(row)
  // 有问题的候选人不可能有入职时间：清空入职时间
  if (row.hire_status && row.join_date) {
    row.join_date = ''
  }
}

const makeUid = () => Math.random().toString(36).slice(2) + Date.now().toString(36)

const AUTH_REAL_NAME_KEY = 'auth_real_name'
const currentRealName = (() => {
  try { return localStorage.getItem(AUTH_REAL_NAME_KEY) || '' } catch { return '' }
})()

const fileList = ref<UploadUserFile[]>([])
const rows = ref<InterviewRow[]>([])
const parsing = ref(false)
const loadingList = ref(false)
const savingAll = ref(false)
const lastSavedAt = ref<Date | null>(null)
const now = ref(Date.now())
let tickInterval: ReturnType<typeof setInterval> | null = null

// Archive drawer state
const archiveDrawerOpen = ref(false)
const archiveRows = ref<InterviewRow[]>([])
const archiveLoading = ref(false)
const archiveSelected = ref<number[]>([])
const archiveRestoring = ref(false)

// ── 筛选查询 ─────────────────────────────────────────────────────────────────
const keywordFilter = ref('')
const statusFilter = ref('')
const issueFilter = ref('')
const EMPTY_FLAG = '__none__'

const filteredRows = computed(() => {
  const kw = keywordFilter.value.trim().toLowerCase()
  const sf = statusFilter.value
  const ix = issueFilter.value
  return rows.value.filter((r) => {
    if (kw) {
      const hay = [r.name, r.phone, r.position, r.inviter].join(' ').toLowerCase()
      if (!hay.includes(kw)) return false
    }
    if (sf) {
      if (sf === EMPTY_FLAG) {
        if (r.interview_status) return false
      } else if (r.interview_status !== sf) {
        return false
      }
    }
    if (ix) {
      if (ix === EMPTY_FLAG) {
        if (r.hire_status) return false
      } else if (r.hire_status !== ix) {
        return false
      }
    }
    return true
  })
})

// ── Computed ─────────────────────────────────────────────────────────────────
const canParse = computed(() => fileList.value.length > 0 && !parsing.value)
const canExport = computed(() => rows.value.length > 0)
const dirtyCount = computed(() => rows.value.filter((r) => r.dirty).length)
const savedAgoText = computed(() => {
  if (!lastSavedAt.value) return ''
  const sec = Math.floor((now.value - lastSavedAt.value.getTime()) / 1000)
  if (sec < 5) return '刚刚已保存'
  return `${sec} 秒前已保存`
})

// ── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(() => {
  tickInterval = setInterval(() => { now.value = Date.now() }, 1000)
  loadDashboard()
  refreshList()
})

onUnmounted(() => {
  if (tickInterval !== null) {
    clearInterval(tickInterval)
    tickInterval = null
  }
})

// 顶部刷新：总览 KPI + 看板数据一起刷新
const load = () => {
  loadDashboard()
  refreshList()
}

// Pull the current set of active (non-archived) interview register rows
// from the server and replace the local table. Any unsaved local edits
// (dirty rows) are discarded; the user just clicked "刷新" so they expect
// fresh data from the DB.
const refreshList = async () => {
  loadingList.value = true
  try {
    const resp = await request.get('/hr/register/list') as { code: number; message: string; data: InterviewRow[] }
    if (resp.data && Array.isArray(resp.data)) {
      // The default /list endpoint returns both active and archived rows;
      // for the main kanban we only want non-archived rows. Archived rows
      // are reached via the "查看已归档" drawer.
      const activeOnly = resp.data.filter((r) => (r.archived ?? 0) !== 1)
      rows.value = activeOnly.map((r) => ({
        ...r,
        age: r.age ?? '',
        birthday: r.birthday ?? '',
        archived: r.archived ?? 0,
        archived_at: r.archived_at ?? '',
        dirty: false,
        saving: false,
      }))
      lastSavedAt.value = null
    }
  } catch {
    ElMessage.error('加载历史记录失败，请稍后重试')
  } finally {
    loadingList.value = false
  }
}

// ── Dirty tracking ────────────────────────────────────────────────────────────
const markDirty = (row: InterviewRow) => { row.dirty = true }

// ── CRUD helpers ──────────────────────────────────────────────────────────────
const saveRow = async (row: InterviewRow) => {
  if (!row || !row.dirty || row.saving) return
  row.saving = true
  try {
    const resp = await request.post('/hr/register/save', {
        id: row.id,
        name: row.name,
        position: row.position,
        gender: row.gender,
        age: row.age,
        birthday: row.birthday,
        phone: row.phone,
        first_interview_date: row.first_interview_date,
        first_interview_time: row.first_interview_time,
        second_interview_date: row.second_interview_date,
        second_interview_time: row.second_interview_time,
        is_present: row.is_present,
        interview_status: row.interview_status,
        hire_status: row.hire_status,
        join_date: row.join_date,
        inviter: row.inviter,
        remark: row.remark,
      },
    )
    const saved = resp.data
    row.id = saved.id
    row.archived = saved.archived ?? row.archived
    row.archived_at = saved.archived_at ?? row.archived_at
    row.dirty = false
    lastSavedAt.value = new Date()
    ElMessage.success('已保存')
    loadDashboard()
  } catch (err: unknown) {
    ElMessage.error('保存失败：' + ((err as { message?: string })?.message ?? '未知错误'))
  } finally {
    row.saving = false
  }
}

const deleteRow = async (row: InterviewRow) => {
  const idx = rows.value.findIndex((r) => r.uid === row.uid)
  if (row.id > 0) {
    try {
      await request.post('/hr/register/delete', { ids: [row.id] })
      if (idx >= 0) rows.value.splice(idx, 1)
      loadDashboard()
    } catch {
      ElMessage.error('删除失败，请稍后重试')
    }
  } else if (idx >= 0) {
    rows.value.splice(idx, 1)
  }
}

const saveAll = async () => {
  const dirty = rows.value.filter((r) => r.dirty && !r.saving)
  if (dirty.length === 0) return
  savingAll.value = true
  let ok = 0
  let fail = 0
  for (const row of dirty) {
    row.saving = true
    try {
      const resp = await request.post('/hr/register/save', {
          id: row.id,
          name: row.name,
          position: row.position,
          gender: row.gender,
          age: row.age,
          birthday: row.birthday,
          phone: row.phone,
          first_interview_date: row.first_interview_date,
          first_interview_time: row.first_interview_time,
          second_interview_date: row.second_interview_date,
          second_interview_time: row.second_interview_time,
          is_present: row.is_present,
          interview_status: row.interview_status,
          hire_status: row.hire_status,
          join_date: row.join_date,
          inviter: row.inviter,
          remark: row.remark,
        },
      )
      const saved = resp.data
      row.id = saved.id
      row.archived = saved.archived ?? row.archived
      row.archived_at = saved.archived_at ?? row.archived_at
      row.dirty = false
      ok++
    } catch {
      fail++
    } finally {
      row.saving = false
    }
  }
  if (ok > 0) {
    lastSavedAt.value = new Date()
    loadDashboard()
  }
  if (fail === 0) {
    ElMessage.success(`已保存 ${ok} 条`)
  } else {
    ElMessage.warning(`保存成功 ${ok} 条，失败 ${fail} 条`)
  }
  savingAll.value = false
}

const clearingAll = ref(false)

const clearAll = async () => {
  if (rows.value.length === 0) {
    ElMessage.info('当前没有未归档的记录')
    return
  }
  const dirty = rows.value.filter((r) => r.dirty)
  let warn = '确定清空所有未归档记录？此操作会从数据库中删除。'
  if (dirty.length > 0) warn += `\n当前还有 ${dirty.length} 条未保存修改，清空将一起丢弃。`
  if (!window.confirm(warn)) return
  clearingAll.value = true
  try {
    const resp = (await request.post('/hr/register/clear-active')) as
      { code: number; message: string; data: { deleted: number; archived_kept: number } }
    const { deleted, archived_kept } = resp.data ?? { deleted: 0, archived_kept: 0 }
    rows.value = []
    lastSavedAt.value = null
    loadDashboard()
    if (archived_kept > 0) {
      ElMessage.success(`已清空 ${deleted} 条未归档记录；${archived_kept} 条归档记录已保留`)
    } else {
      ElMessage.success(`已清空 ${deleted} 条未归档记录`)
    }
  } catch (err: unknown) {
    ElMessage.error('清空失败：' + ((err as { message?: string })?.message ?? '未知错误'))
  } finally {
    clearingAll.value = false
  }
}

// ── Parse handler ─────────────────────────────────────────────────────────────
const handleParse = async () => {
  if (!canParse.value) return

  parsing.value = true
  try {
    // ① 构建全局去重 map：DB 已有的 + 本地 rows（含未保存的脏数据）
    //    用 uid 作 key 因为本地行 id=0，DB 行 id>0，uid 才能统一两个来源
    const dedupeByName = new Map<string, InterviewRow>()

    // 先把 DB 已有的加进去（按 trim 后的姓名索引）
    try {
      const listResp = await request.get('/hr/register/list') as {
        code: number; message: string; data: InterviewRow[]
      }
      if (listResp.data && Array.isArray(listResp.data)) {
        for (const r of listResp.data) {
          if (r.archived !== 1 && r.name) {
            dedupeByName.set(r.name.trim().toLocaleLowerCase('zh-CN'), r)
          }
        }
      }
    } catch {
      // 拉取失败不影响后续流程
    }

    // 再用本地 rows 覆盖（未保存的脏数据优先级最高，且不会被 DB 的空姓名覆盖）
    for (const r of rows.value) {
      if (r.archived !== 1 && r.name) {
        dedupeByName.set(r.name.trim().toLocaleLowerCase('zh-CN'), r)
      }
    }

    const formData = new FormData()
    for (const item of fileList.value) {
      if (item.raw) {
        formData.append('files', item.raw)
      }
    }

    const resp = await request.post<{ code: number; message: string; data: InterviewRow[] }>(
      '/hr/parse-resumes',
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )

    const newRows: InterviewRow[] = Array.isArray(resp.data) ? resp.data : []
    let persisted = 0
    let updated = 0
    let failed = 0
    let needsReview = 0

    for (const row of newRows) {
      const candidate: InterviewRow = {
        ...JSON.parse(JSON.stringify(row)),
        uid: makeUid(),
        id: 0,
        dirty: false,
        saving: false,
        inviter: row.inviter || currentRealName,
      }

      // ② 按姓名去重（trim 后比较，忽略大小写差异）
      const key = candidate.name?.trim().toLocaleLowerCase('zh-CN') || ''
      const existing = key ? dedupeByName.get(key) : undefined
      if (candidate.remark) needsReview++
      if (existing) {
        // 命中：用 AI 最新数据覆盖基础信息，**保留** HR 已填写的邀约人/面试日期/状态/入职时间等
        existing.name        = candidate.name
        existing.position    = candidate.position
        existing.gender      = candidate.gender
        existing.age         = candidate.age
        existing.birthday    = candidate.birthday
        existing.phone       = candidate.phone
        existing.hire_status = candidate.hire_status
        existing.remark      = candidate.remark
        existing.dirty       = true

        // 如果这条原本在 DB 里但本地没加载过，把它的副本 push 到 rows 让用户看到
        if (!rows.value.find((r) => r.id === existing.id && existing.id > 0)) {
          rows.value.push({ ...existing, uid: makeUid(), dirty: true, saving: false })
        }
        // 更新 dedupe map 防止同一批里出现同名重复
        dedupeByName.set(key, existing)
        updated++
        continue
      }

      // ③ 全新候选人：先登记到 dedupe map（防本批内重名），再入库
      if (key) dedupeByName.set(key, candidate)
      try {
        const saveResp = await request.post(
          '/hr/register/save',
          {
            id: 0,
            name: candidate.name,
            position: candidate.position,
            gender: candidate.gender,
            age: candidate.age,
            birthday: candidate.birthday,
            phone: candidate.phone,
            first_interview_date: candidate.first_interview_date,
            first_interview_time: candidate.first_interview_time,
            second_interview_date: candidate.second_interview_date,
            second_interview_time: candidate.second_interview_time,
            is_present: candidate.is_present,
            interview_status: candidate.interview_status,
            hire_status: candidate.hire_status,
            join_date: candidate.join_date,
            inviter: candidate.inviter,
            remark: candidate.remark,
          },
        ) as { code: number; message: string; data: InterviewRow }
        if (saveResp?.data?.id) {
          candidate.id = saveResp.data.id
          candidate.archived = saveResp.data.archived ?? 0
          candidate.archived_at = saveResp.data.archived_at ?? ''
        }
        persisted++
      } catch {
        candidate.dirty = true
        failed++
      }
      rows.value.push(candidate)
    }

    if (persisted > 0 || updated > 0) lastSavedAt.value = new Date()
    const parts: string[] = []
    if (updated > 0) parts.push(`去重更新 ${updated} 条`)
    if (persisted > 0) parts.push(`新增 ${persisted} 份`)
    if (failed > 0) parts.push(`失败 ${failed} 份`)
    if (needsReview > 0) parts.push(`需人工核对 ${needsReview} 份`)
    if (parts.length > 0) {
      if (failed > 0 || needsReview > 0) ElMessage.warning(parts.join('，'))
      else ElMessage.success(parts.join('，'))
    }
    fileList.value = []
    loadDashboard()
  } catch {
    ElMessage.error('AI 解析失败，请稍后重试')
  } finally {
    parsing.value = false
  }
}

// ── Export handler ────────────────────────────────────────────────────────────
const handleExport = async () => {
  if (!canExport.value) return

  ElMessage.info('正在生成 Excel…')

  const monthStr = new Date().toLocaleString('zh-CN', { year: 'numeric', month: 'long' })
  const title = `${monthStr}面试邀约登记表`
  const payload = { title, rows: rows.value }

  try {
    const resp = await axios.post('/api/hr/export-excel', payload, { responseType: 'blob' })
    const blob = new Blob([resp.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '')
    const a = document.createElement('a')
    a.href = url
    a.download = `面试邀约登记表-${dateStr}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('Excel 已生成下载')
  } catch (err: unknown) {
    ElMessage.error('导出失败：' + ((err as { message?: string })?.message ?? '未知错误'))
  }
}

// ── 手工新增一行（不依赖 AI 导入） ───────────────────────────────────────────
const addEmptyRow = () => {
  rows.value.push({
    uid: makeUid(),
    id: 0,
    dirty: true,
    saving: false,
    name: '',
    position: '',
    gender: '',
    age: '',
    birthday: '',
    phone: '',
    first_interview_date: '',
    first_interview_time: '',
    second_interview_date: '',
    second_interview_time: '',
    is_present: '',
    interview_status: '',
    hire_status: '',
    join_date: '',
    inviter: currentRealName,
    remark: '',
    archived: 0,
    archived_at: '',
  })
}

// ── Clear ─────────────────────────────────────────────────────────────────────
const handleClear = () => {
  fileList.value = []
  rows.value = []
}

// ── Archive handlers ──────────────────────────────────────────────────────────
const openArchiveDrawer = async () => {
  archiveDrawerOpen.value = true
  archiveSelected.value = []
  archiveLoading.value = true
  try {
    const resp = (await request.get('/hr/register/list', { params: { archived: 1 } })) as
      { code: number; message: string; data: InterviewRow[] }
    archiveRows.value = Array.isArray(resp.data) ? resp.data : []
  } catch {
    ElMessage.error('加载归档列表失败')
  } finally {
    archiveLoading.value = false
  }
}

const restoreSelected = async () => {
  if (archiveSelected.value.length === 0) {
    ElMessage.warning('请先勾选要还原的记录')
    return
  }
  archiveRestoring.value = true
  try {
    await request.post('/hr/register/archive', {
      ids: archiveSelected.value,
      archived: false,
    })
    ElMessage.success(`已还原 ${archiveSelected.value.length} 条`)
    archiveSelected.value = []
    await openArchiveDrawer()  // refresh list
    loadDashboard()
  } catch {
    ElMessage.error('还原失败，请稍后重试')
  } finally {
    archiveRestoring.value = false
  }
}

const onArchiveSelectionChange = (selection: InterviewRow[]) => {
  archiveSelected.value = selection.map((r) => r.id)
}

const archiveRow = async (row: InterviewRow) => {
  if (row.id <= 0) {
    ElMessage.warning('该行尚未保存到数据库，请先保存')
    return
  }
  try {
    await request.post('/hr/register/archive', { ids: [row.id], archived: true })
    const idx = rows.value.findIndex((r) => r.uid === row.uid)
    if (idx >= 0) rows.value.splice(idx, 1)
    ElMessage.success(`已归档：${row.name || '未命名'}`)
    loadDashboard()
  } catch {
    ElMessage.error('归档失败，请稍后重试')
  }
}

</script>

<template>
  <div class="hr-page">
    <!-- ── 页面头 ──────────────────────────────────────────────────────── -->
    <div class="page-head">
      <div class="title">招聘管理</div>
      <div class="actions">
        <el-button :icon="Refresh" circle title="刷新" @click="load" />
      </div>
    </div>

    <!-- ── 招聘总览 KPI ────────────────────────────────────────────────── -->
    <div class="kpis" v-if="kpis">
      <el-card shadow="never" class="kpi"><div class="kpi-label">待跟进</div><div class="kpi-value">{{ kpis.pending_followup }}</div></el-card>
      <el-card shadow="never" class="kpi"><div class="kpi-label">候选人总数</div><div class="kpi-value">{{ kpis.total_candidates }}</div></el-card>
      <el-card shadow="never" class="kpi"><div class="kpi-label">录用率</div><div class="kpi-value">{{ ((kpis.offer_rate || 0) * 100).toFixed(0) + '%' }}</div></el-card>
      <el-card shadow="never" class="kpi"><div class="kpi-label">到岗率</div><div class="kpi-value">{{ ((kpis.onboard_rate || 0) * 100).toFixed(0) + '%' }}</div></el-card>
      <el-card shadow="never" class="kpi"><div class="kpi-label">平均招聘周期</div><div class="kpi-value">{{ (kpis.avg_cycle_days || 0).toFixed(1) }}<span style="font-size:13px">天</span></div></el-card>
    </div>

    <!-- ── 简历跟进看板（与招聘管理合并） ─────────────────────────────── -->
    <div class="page-container">
      <!-- B) Upload + parse card -->
      <div class="upload-card">
        <div class="upload-card-header">
          <div class="section-title-row">
            <span class="accent-bar" />
            <span class="section-title">简历解析</span>
          </div>
          <div class="upload-actions">
            <span v-if="fileList.length > 0" class="file-summary">
              已选 <strong>{{ fileList.length }}</strong> 份
            </span>
            <el-upload
              v-model:file-list="fileList"
              accept=".pdf,.docx,.doc"
              action="#"
              :auto-upload="false"
              :show-file-list="false"
              multiple
              class="inline-upload-trigger"
            >
              <el-button size="default" :disabled="parsing">
                <el-icon><UploadFilled /></el-icon>
                <span style="margin-left: 4px">选择简历</span>
              </el-button>
            </el-upload>
            <el-button
              type="primary"
              size="default"
              :disabled="!canParse"
              :loading="parsing"
              @click="handleParse"
            >
              {{ parsing ? 'AI 解析中…' : '开始 AI 解析' }}
            </el-button>
            <el-button
              v-if="rows.length > 0 || fileList.length > 0"
              text
              size="default"
              @click="handleClear"
            >
              清空
            </el-button>
            <el-button
              size="default"
              @click="openArchiveDrawer"
            >
              查看已归档
            </el-button>
          </div>
        </div>

        <!-- Tiny chip list of currently-queued files (so HR can see what they selected) -->
        <div v-if="fileList.length > 0" class="queued-files">
          <el-tag
            v-for="(file, idx) in fileList"
            :key="file.uid || idx"
            closable
            size="small"
            type="info"
            effect="light"
            @close="fileList.splice(idx, 1)"
          >
            {{ file.name }}
          </el-tag>
        </div>

        <div v-if="parsing" class="parsing-hint">
          AI 解析中，可能需要 10~30 秒…
        </div>
      </div>

      <!-- C) Table card -->
      <div class="table-card">
        <div class="table-card-header">
          <div class="section-title-row">
            <span class="accent-bar" />
            <span class="section-title">面试邀约信息</span>
          </div>
          <div class="table-header-actions">
            <el-button
              size="default"
              :icon="Plus"
              @click="addEmptyRow"
            >
              新增一行
            </el-button>
            <el-button
              text
              type="danger"
              size="default"
              :disabled="rows.length === 0 || clearingAll"
              :loading="clearingAll"
              @click="clearAll"
            >
              清空全部
            </el-button>
            <el-button
              size="default"
              :loading="loadingList"
              @click="refreshList"
            >
              <el-icon><Refresh /></el-icon>
              <span style="margin-left: 4px">刷新</span>
            </el-button>
            <span v-if="lastSavedAt && dirtyCount === 0" class="saved-indicator">
              {{ savedAgoText }}
            </span>
            <el-button
              type="primary"
              :disabled="dirtyCount === 0 || savingAll"
              :loading="savingAll"
              @click="saveAll"
            >
              保存全部 ({{ dirtyCount }})
            </el-button>
            <el-button
              type="primary"
              :disabled="!canExport"
              @click="handleExport"
            >
              <el-icon><Download /></el-icon>
              一键导出为 Excel
            </el-button>
          </div>
        </div>

        <div class="table-filters">
          <el-input
            v-model="keywordFilter"
            placeholder="搜索 姓名 / 电话 / 应聘职务 / 邀约人"
            clearable
            :prefix-icon="Search"
            style="width: 250px"
          />
          <el-select v-model="statusFilter" placeholder="面试情况" clearable style="width: 210px">
            <el-option label="（未填写）" value="__none__" />
            <el-option v-for="opt in interviewStatusOptions" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <el-select v-model="issueFilter" placeholder="问题情况" clearable style="width: 210px">
            <el-option label="（未填写）" value="__none__" />
            <el-option v-for="opt in issueStatusOptions" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <span v-if="filteredRows.length !== rows.length" class="filter-count">
            筛选出 {{ filteredRows.length }} / {{ rows.length }} 条
          </span>
        </div>

        <el-table
          v-if="rows.length > 0"
          :data="filteredRows"
          border
          stripe
          style="width: 100%; flex: 1 1 auto; min-height: 0;"
          height="100%"
          size="default"
        >
          <el-table-column label="序号" width="70" align="center" fixed="left">
            <template #default="{ $index }">
              {{ $index + 1 }}
            </template>
          </el-table-column>

          <el-table-column label="邀约人" width="140" min-width="120">
            <template #default="{ row }">
              <el-input v-model="(row as InterviewRow).inviter" size="default" @input="markDirty(row as InterviewRow)" />
            </template>
          </el-table-column>

          <el-table-column label="姓名" width="120" min-width="110">
            <template #default="{ row }">
              <el-input v-model="(row as InterviewRow).name" size="default" @input="markDirty(row as InterviewRow)" />
            </template>
          </el-table-column>

          <el-table-column label="应聘职务" width="180" min-width="160">
            <template #default="{ row }">
              <el-input v-model="(row as InterviewRow).position" size="default" @input="markDirty(row as InterviewRow)" />
            </template>
          </el-table-column>

          <el-table-column label="性别" width="100" align="center">
            <template #default="{ row }">
              <el-select v-model="(row as InterviewRow).gender" size="default" clearable placeholder="" style="width: 100%" @change="markDirty(row as InterviewRow)">
                <el-option label="男" value="男" />
                <el-option label="女" value="女" />
              </el-select>
            </template>
          </el-table-column>

          <el-table-column label="年龄" width="90" align="center">
            <template #default="{ row }">
              <el-input v-model="(row as InterviewRow).age" size="default" @input="markDirty(row as InterviewRow)" />
            </template>
          </el-table-column>

          <el-table-column label="出生日期" width="140" align="center">
            <template #default="{ row }">
              <el-input v-model="(row as InterviewRow).birthday" size="default" @input="markDirty(row as InterviewRow)" />
            </template>
          </el-table-column>

          <el-table-column label="联系电话" width="170" min-width="150">
            <template #default="{ row }">
              <el-input v-model="(row as InterviewRow).phone" size="default" @input="markDirty(row as InterviewRow)" />
            </template>
          </el-table-column>

          <el-table-column label="初面日期" width="160" min-width="150">
            <template #default="{ row }">
              <el-date-picker
                v-model="(row as InterviewRow).first_interview_date"
                type="date"
                size="default"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                style="width: 100%"
                @change="markDirty(row as InterviewRow)"
              />
            </template>
          </el-table-column>

          <el-table-column label="初面时间" width="140" min-width="130">
            <template #default="{ row }">
              <el-time-picker
                v-model="(row as InterviewRow).first_interview_time"
                size="default"
                format="HH:mm"
                value-format="HH:mm"
                style="width: 100%"
                @change="markDirty(row as InterviewRow)"
              />
            </template>
          </el-table-column>

          <el-table-column label="复试日期" width="160" min-width="150">
            <template #default="{ row }">
              <el-date-picker
                v-model="(row as InterviewRow).second_interview_date"
                type="date"
                size="default"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                style="width: 100%"
                @change="markDirty(row as InterviewRow)"
              />
            </template>
          </el-table-column>

          <el-table-column label="复试时间" width="140" min-width="130">
            <template #default="{ row }">
              <el-time-picker
                v-model="(row as InterviewRow).second_interview_time"
                size="default"
                format="HH:mm"
                value-format="HH:mm"
                style="width: 100%"
                @change="markDirty(row as InterviewRow)"
              />
            </template>
          </el-table-column>

          <el-table-column label="是否到面" width="120" align="center">
            <template #default="{ row }">
              <el-select v-model="(row as InterviewRow).is_present" size="default" clearable placeholder="" style="width: 100%" @change="markDirty(row as InterviewRow)">
                <el-option label="是" value="是" />
                <el-option label="否" value="否" />
                <el-option label="待定" value="待定" />
              </el-select>
            </template>
          </el-table-column>

          <el-table-column label="面试情况" width="240" min-width="220">
            <template #default="{ row }">
              <el-select
                v-model="(row as InterviewRow).interview_status"
                filterable
                allow-create
                clearable
                size="default"
                placeholder="请选择或输入"
                style="width: 100%"
                popper-class="interview-status-popper"
                :class="{ 'pass-select': isPassInterview((row as InterviewRow).interview_status) }"
                @change="onInterviewStatusChange(row as InterviewRow)"
              >
                <el-option v-for="opt in interviewStatusOptions" :key="opt" :label="opt" :value="opt">
                  <span :class="{ 'pass-option-text': isPassInterview(opt) }">{{ opt }}</span>
                </el-option>
              </el-select>
            </template>
          </el-table-column>

          <el-table-column label="问题情况" width="240" min-width="220">
            <template #default="{ row }">
              <el-select
                v-model="(row as InterviewRow).hire_status"
                filterable
                allow-create
                clearable
                size="default"
                placeholder="请选择或输入"
                style="width: 100%"
                :disabled="isPassInterview((row as InterviewRow).interview_status)"
                @change="onIssueStatusChange(row as InterviewRow)"
              >
                <el-option v-for="opt in issueStatusOptions" :key="opt" :label="opt" :value="opt" />
              </el-select>
            </template>
          </el-table-column>

          <el-table-column label="入职时间" width="160" min-width="150">
            <template #default="{ row }">
              <el-date-picker
                v-model="(row as InterviewRow).join_date"
                type="date"
                size="default"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                style="width: 100%"
                :disabled="!isPassInterview((row as InterviewRow).interview_status) || !!(row as InterviewRow).hire_status"
                @change="markDirty(row as InterviewRow)"
              />
            </template>
          </el-table-column>

          <el-table-column label="操作" width="180" align="center" fixed="right">
            <template #default="{ $index, row }">
              <div class="op-cell">
                <el-button
                  type="primary"
                  text
                  size="small"
                  :disabled="!(row as InterviewRow).dirty || (row as InterviewRow).saving"
                  @click="saveRow(row as InterviewRow)"
                >
                  <el-icon v-if="(row as InterviewRow).saving" class="is-loading"><Loading /></el-icon>
                  <span>{{ (row as InterviewRow).saving ? '保存中' : '保存' }}</span>
                </el-button>
                <el-popconfirm
                  title="确定归档这条记录吗？归档后可在「查看已归档」中恢复。"
                  confirm-button-text="确认归档"
                  cancel-button-text="取消"
                  confirm-button-type="warning"
                  width="240"
                  @confirm="archiveRow(row as InterviewRow)"
                >
                  <template #reference>
                    <el-button type="warning" text size="small" :disabled="(row as InterviewRow).id <= 0">归档</el-button>
                  </template>
                </el-popconfirm>
                <el-popconfirm
                  title="确定删除这条记录吗？"
                  confirm-button-text="确认删除"
                  cancel-button-text="取消"
                  confirm-button-type="danger"
                  width="220"
                  @confirm="deleteRow(row as InterviewRow)"
                >
                  <template #reference>
                    <el-button type="danger" text size="small">删除</el-button>
                  </template>
                </el-popconfirm>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <div v-else class="empty-state">
          <el-icon class="empty-icon"><UploadFilled /></el-icon>
          <p class="empty-tip">{{ rows.length === 0 ? '暂无记录：可点击上方「新增一行」手工录入候选人信息，或选择简历文件后点击「开始 AI 解析」' : '没有符合当前筛选条件的记录，请调整筛选条件' }}</p>
        </div>
      </div>

      <!-- ── Tip ─────────────────────────────────────────────────────────── -->
      <p class="usage-tip">
        💡 小贴士：可直接点击「新增一行」手工录入面试邀约信息；也可以选择简历文件 AI 解析后批量填入。所有字段修改后，点击右上角「一键导出为 Excel」即可生成与「面试邀约登记表」模板完全对齐的 Excel 文件。
      </p>
    </div>

    <!-- ── Archive drawer (查看已归档 / 还原) ────────────────────────── -->
    <el-drawer
      v-model="archiveDrawerOpen"
      title="已归档的面试登记表"
      direction="rtl"
      size="80%"
      :destroy-on-close="false"
    >
      <div class="archive-drawer-body">
        <div class="archive-toolbar">
          <span class="archive-count">
            共 <strong>{{ archiveRows.length }}</strong> 条已归档记录
          </span>
          <div class="archive-toolbar-actions">
            <el-button
              type="primary"
              :disabled="archiveSelected.length === 0 || archiveRestoring"
              :loading="archiveRestoring"
              @click="restoreSelected"
            >
              还原选中的 {{ archiveSelected.length > 0 ? `(${archiveSelected.length})` : '' }}
            </el-button>
          </div>
        </div>

        <el-table
          v-if="archiveDrawerOpen"
          v-loading="archiveLoading"
          :data="archiveRows"
          border
          stripe
          height="100%"
          size="default"
          @selection-change="onArchiveSelectionChange"
        >
          <el-table-column type="selection" width="48" />
          <el-table-column label="原序号" width="80" align="center">
            <template #default="{ $index }">
              {{ $index + 1 }}
            </template>
          </el-table-column>
          <el-table-column prop="name" label="姓名" width="120" />
          <el-table-column prop="position" label="应聘职务" width="160" />
          <el-table-column prop="gender" label="性别" width="80" align="center" />
          <el-table-column prop="age" label="年龄" width="80" align="center" />
          <el-table-column prop="birthday" label="出生日期" width="140" align="center" />
          <el-table-column prop="phone" label="联系电话" width="140" />
          <el-table-column prop="first_interview_date" label="初面日期" width="120" align="center" />
          <el-table-column prop="interview_status" label="面试情况" min-width="240" show-overflow-tooltip />
          <el-table-column prop="hire_status" label="问题情况" min-width="200" show-overflow-tooltip />
          <el-table-column prop="inviter" label="邀约人" width="110" />
          <el-table-column label="归档时间" width="170" align="center">
            <template #default="{ row }">
              {{ (row as InterviewRow).archived_at || '-' }}
            </template>
          </el-table-column>
        </el-table>

        <el-empty v-if="!archiveLoading && archiveRows.length === 0" description="暂无已归档记录" />
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.hr-page {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px 24px 12px;
  box-sizing: border-box;
  overflow: hidden;
  background: var(--app-bg);
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}
.page-head .title { font-size: 18px; font-weight: 800; }
.actions { display: flex; gap: 8px; }

/* ── KPI ─────────────────────────────────────────────────────────────── */
.kpis {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 14px;
  flex-shrink: 0;
}
.kpi { text-align: center; }
.kpi-label { color: light-dark(#64748b, var(--text-secondary)); font-size: 13px; }
.kpi-value { font-size: 24px; font-weight: 800; color: light-dark(#0f766e, var(--text-accent)); margin-top: 4px; }

/* ── 看板容器（占满剩余高度，内部表格滚动） ─────────────────────── */
.page-container {
  width: 100%;
  max-width: 1800px;
  margin: 0 auto;
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* ── Section title with accent bar ───────────────────────────────────── */
.section-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.accent-bar {
  display: inline-block;
  width: 4px;
  height: 18px;
  background: var(--primary);
  border-radius: 2px;
  flex-shrink: 0;
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-heading);
}

/* ── Upload card ─────────────────────────────────────────────────────── */
.upload-card {
  background: var(--app-surface);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 14px 20px;
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex-shrink: 0;
}

.upload-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.upload-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.file-summary {
  font-size: 13px;
  color: var(--text-secondary);
  padding: 0 4px;
}
.file-summary strong {
  color: var(--primary);
  font-size: 15px;
  margin: 0 2px;
}

.queued-files {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding-top: 4px;
}

.parsing-hint {
  font-size: 12px;
  color: var(--text-secondary);
  text-align: center;
  padding: 4px 0;
}

/* ── Table card ──────────────────────────────────────────────────────── */
.table-card {
  background: var(--app-surface);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 16px 24px;
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
}

.table-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  flex-shrink: 0;
}

.table-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.table-filters {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.filter-count {
  font-size: 12px;
  color: var(--text-muted);
  padding: 0 4px;
}

.saved-indicator {
  font-size: 12px;
  color: var(--text-muted);
  padding: 0 4px;
  white-space: nowrap;
}

.op-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  white-space: nowrap;
}
.op-cell :deep(.el-button.is-text) {
  padding: 4px 6px;
}

/* ── Archive drawer ────────────────────────────────────────────────── */
.archive-drawer-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  padding: 0 4px;
}

.archive-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 4px 0 8px;
  border-bottom: 1px solid var(--border-color);
}

.archive-count {
  font-size: 13px;
  color: var(--text-secondary);
}
.archive-count strong {
  color: var(--primary);
  font-size: 16px;
  font-weight: 700;
  margin: 0 4px;
}

.archive-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Table styles — sized for "more spacious" feel */
:deep(.el-table__header th) {
  color: var(--table-header-text);
  background: var(--table-header-bg);
  font-weight: 700;
  font-size: 13px;
  padding: 8px 8px !important;
  height: auto;
}

:deep(.el-table__cell) {
  padding: 6px 8px !important;
  font-size: 13px;
  color: var(--text-primary);
}

:deep(.el-table__row:hover > td) {
  background: var(--app-surface-2) !important;
}

:deep(.el-input__wrapper),
:deep(.el-select__wrapper) {
  border-radius: 6px;
}

/* When table is fixed-height, body should be the only scroll surface */
:deep(.el-table) {
  display: flex;
  flex-direction: column;
}
:deep(.el-table__inner-wrapper) {
  flex: 1 1 auto;
  min-height: 0;
}

/* ── Empty state (compact) ─────────────────────────────────────────── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 48px 0;
}

.empty-icon {
  font-size: 56px;
  color: var(--text-muted);
  opacity: 0.55;
}

.empty-tip {
  margin: 0;
  font-size: 14px;
  color: var(--text-muted);
}

/* ── Usage tip ───────────────────────────────────────────────────────── */
.usage-tip {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.6;
  padding: 0 4px;
  flex-shrink: 0;
}

/* ── 面试通过类：行内选中值黑色加粗 ───────────────────────────── */
.pass-select :deep(.el-select__selected-item) {
  color: light-dark(#000000, var(--text-primary));
  font-weight: 700;
}

/* ── 面试通过类：下拉面板选项黑色加粗（面板在 body，需全局） ───── */
:global(.interview-status-popper .pass-option-text) {
  color: light-dark(#000000, var(--text-primary));
  font-weight: 700;
}
:global(.interview-status-popper .el-select-dropdown__item:hover .pass-option-text),
:global(.interview-status-popper .el-select-dropdown__item.is-selected .pass-option-text) {
  color: light-dark(#000000, var(--text-primary));
}

/* ── Responsive ──────────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .hr-page {
    padding: 16px;
  }

  .upload-card,
  .table-card {
    padding: 16px;
  }
}
</style>
