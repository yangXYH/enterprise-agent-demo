<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  ElButton, ElCard, ElDescriptions, ElDescriptionsItem, ElDialog, ElDrawer,
  ElEmpty, ElForm, ElFormItem, ElIcon, ElInput, ElMessage, ElOption,
  ElPagination, ElPopconfirm, ElSelect, ElTable, ElTableColumn, ElTag, ElUpload,
} from 'element-plus'
import { Bell, Download, Plus, Refresh, Search, UploadFilled } from '@element-plus/icons-vue'
import request from '../../utils/request'
import type { UploadUserFile } from 'element-plus'

const rows = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const keyword = ref('')
const dept = ref('')
const company = ref('')
const depts = ref<string[]>([])

// 公司下拉固定三项：全部 / 示例科技 / 示例传媒
const companyOptions = [
  { label: '全部', value: '' },
  { label: '示例科技', value: '示例科技' },
  { label: '示例传媒', value: '示例传媒' },
]

const detailVisible = ref(false)
const detail = ref<any>(null)
const detailLoading = ref(false)

const editVisible = ref(false)
const editForm = ref<any>({})
const isNew = ref(false)

const reminders = ref<any>({})
const remindersLoading = ref(false)
const remindersOpen = ref(false)

const fileList = ref<UploadUserFile[]>([])
const importing = ref(false)
const importVisible = ref(false)
const importReport = ref<any>(null)

const isAdmin = computed(() => {
  const role = (localStorage.getItem('auth_role') || '').toLowerCase()
  return role === 'admin' || role === 'hr'
})

// 顶部统计：在职数（页面固定展示在职花名册）
const activeCount = computed(() => total.value)

const load = async () => {
  loading.value = true
  try {
    const resp = await request.get('/hr/roster/list', {
      params: {
        keyword: keyword.value,
        dept: dept.value,
        company: company.value,
        status: 'active',
        page: page.value,
        page_size: pageSize.value,
      },
    }) as any
    rows.value = resp.items || []
    total.value = resp.total || 0
    if (!depts.value.length) depts.value = Array.from(new Set(rows.value.map((r: any) => r.dept_name).filter(Boolean)))
  } finally {
    loading.value = false
  }
}

const openDetail = async (row: any) => {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    const resp = await request.get(`/hr/roster/detail/${row.id}`) as any
    detail.value = resp
  } finally {
    detailLoading.value = false
  }
}

const openEdit = (row?: any) => {
  if (row) {
    isNew.value = false
    editForm.value = { ...row }
  } else {
    isNew.value = true
    editForm.value = { name: '', dept_name: '', position: '', hire_date: '' }
  }
  editVisible.value = true
}

const descOf = (label: string): [string, string] => {
  const map: Record<string, [string, string]> = {
    contract_expiry: ['合同到期', 'danger'],
    regular_upcoming: ['转正预警', 'warning'],
    probation_expiry: ['试用期到期', 'warning'],
    probation_overdue: ['试用期已超期', 'danger'],
    birthday: ['生日', 'primary'],
    id_card_expiry: ['证件到期', 'danger'],
  }
  return map[label] || [label, 'info']
}

const loadReminders = async () => {
  remindersLoading.value = true
  try {
    const resp = await request.get('/hr/roster/reminders') as any
    reminders.value = resp.reminders || {}
  } finally {
    remindersLoading.value = false
  }
}

const openReminders = () => {
  remindersOpen.value = true
  loadReminders()
}

const save = async () => {
  try {
    await request.post('/hr/roster/save', editForm.value)
    ElMessage.success(isNew.value ? '已新增员工' : '已保存')
    editVisible.value = false
    load()
  } catch { /* interceptor */ }
}

const remove = async (row: any) => {
  try {
    await request.post('/hr/roster/delete', { id: row.id })
    ElMessage.success('已删除')
    load()
  } catch { /* interceptor */ }
}

const doImport = async () => {
  const file = fileList.value[0]
  if (!file || !file.raw) { ElMessage.warning('请选择文件'); return }
  importing.value = true
  importReport.value = null
  try {
    const form = new FormData()
    form.append('file', file.raw)
    const resp = await fetch('/api/hr/import/roster', { method: 'POST', body: form, credentials: 'same-origin' })
    const data = await resp.json()
    if (!resp.ok) { ElMessage.error(data.detail || '导入失败'); return }
    importReport.value = data
    ElMessage.success('导入完成')
    load()
  } catch (e: any) {
    ElMessage.error(e.message || '导入失败')
  } finally {
    importing.value = false
  }
}

const doExport = async () => {
  try {
    const resp = await fetch('/api/hr/roster/export', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ keyword: keyword.value, dept: dept.value, company: company.value, status: 'active' }),
    })
    if (!resp.ok) { ElMessage.error('导出失败'); return }
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = '员工花名册.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  } catch { /* */ }
}

const notice = (label: string, v: string) => label + (v ? `：${v}` : '')

// 合同类型配色
const contractTypeOf = (t: string): { label: string; type: string } => {
  if (!t) return { label: '—', type: 'info' }
  if (t.includes('劳务')) return { label: t, type: 'warning' }
  if (t.includes('临时')) return { label: t, type: 'info' }
  if (t.includes('劳动合同') || t === '劳动合同') return { label: t, type: 'success' }
  return { label: t, type: 'info' }
}

// 司龄换算（按入职日期到今天）
const seniorityOf = (hireDate: string): string => {
  if (!hireDate) return ''
  const d = new Date(hireDate)
  if (isNaN(d.getTime())) return ''
  const now = new Date()
  let years = now.getFullYear() - d.getFullYear()
  let months = now.getMonth() - d.getMonth()
  if (months < 0) { years -= 1; months += 12 }
  if (years < 1) return `${months} 个月`
  if (years < 10) return `${years} 年${months > 0 ? ' ' + months + ' 个月' : ''}`
  return `${years} 年`
}

// 性别配色
const genderTag = (g: string) => g === '男' ? 'primary' : 'danger'

onMounted(load)
</script>

<template>
  <div class="hr-page">
    <el-card shadow="never" class="roster-card">
      <!-- 顶部工具栏 -->
      <div class="toolbar">
        <div class="toolbar-left">
          <el-button v-if="isAdmin" type="primary" :icon="Plus" @click="openEdit()" class="toolbar-btn">新增员工</el-button>
          <el-button v-if="isAdmin" :icon="UploadFilled" @click="importVisible = true" class="toolbar-btn">导入花名册</el-button>
          <el-button :icon="Download" @click="doExport" :disabled="!rows.length" class="toolbar-btn">导出</el-button>
        </div>
        <div class="toolbar-right">
          <el-button :icon="Bell" @click="openReminders" class="toolbar-btn">
            提醒中心
            <el-tag v-if="reminders.summary?.total" size="small" type="danger" round class="btn-tag">{{ reminders.summary.total }}</el-tag>
          </el-button>
          <span class="stat-pill">
            <span class="stat-dot" />
            在职 <b>{{ activeCount }}</b> 人
          </span>
          <el-button :icon="Refresh" circle @click="load" title="刷新" />
        </div>
      </div>

      <!-- 筛选区 -->
      <div class="filters">
        <el-input v-model="keyword" placeholder="姓名 / 岗位 / 工号" clearable style="width: 220px" class="filter-input" @keyup.enter="page=1; load()">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="company" placeholder="选择公司" class="filter-select" style="width: 150px" @change="page=1; load()">
          <el-option v-for="c in companyOptions" :key="c.value" :label="c.label" :value="c.value" />
        </el-select>
        <el-select v-model="dept" placeholder="选择部门" clearable filterable class="filter-select" style="width: 200px" @change="page=1; load()">
          <el-option v-for="d in depts" :key="d" :label="d" :value="d" />
        </el-select>
        <el-button type="primary" :icon="Search" @click="page=1; load()" class="filter-btn">搜索</el-button>
      </div>

      <!-- 表格 -->
      <el-table
        :data="rows"
        v-loading="loading"
        stripe
        border
        @row-click="openDetail"
        class="roster-table"
        :header-row-class-name="'tbl-header'"
      >
        <el-table-column type="index" label="#" width="60" align="center" />
        <el-table-column prop="name" label="姓名" width="120">
          <template #default="{ row }">
            <span class="cell-name">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="dept_name" label="部门" min-width="160" show-overflow-tooltip />
        <el-table-column prop="group_name" label="组别" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.group_name">{{ row.group_name }}</span>
            <span v-else class="cell-empty">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="position" label="岗位" min-width="160" show-overflow-tooltip />
        <el-table-column prop="gender" label="性别" width="84" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.gender" :type="genderTag(row.gender)" size="small" effect="plain" round>{{ row.gender }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="education" label="学历" width="96" align="center" />
        <el-table-column label="入职日期" width="150">
          <template #default="{ row }">
            <div class="cell-date">
              <span class="date-main">{{ row.hire_date || '—' }}</span>
              <span v-if="row.hire_date" class="date-sub">{{ seniorityOf(row.hire_date) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="合同类型" width="112" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.contract_type" :type="contractTypeOf(row.contract_type).type as any" size="small" effect="plain">{{ contractTypeOf(row.contract_type).label }}</el-tag>
            <span v-else class="cell-empty">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="phone" label="电话" width="150">
          <template #default="{ row }">
            <span class="cell-phone">{{ row.phone || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="172" fixed="right" align="center">
          <template #default="{ row }">
            <div class="row-ops">
              <el-button v-if="isAdmin" size="small" plain type="primary" @click.stop="openEdit(row)">编辑</el-button>
              <el-popconfirm v-if="isAdmin" title="确认删除该员工？" @confirm="remove(row)">
                <template #reference><el-button size="small" plain type="danger" @click.stop>删除</el-button></template>
              </el-popconfirm>
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="没有匹配的员工，试试调整筛选条件" :image-size="80" />
        </template>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrap">
        <span class="page-summary">共 <b>{{ total }}</b> 条</span>
        <el-pagination
          v-model:current-page="page" :page-size="pageSize" :total="total"
          layout="prev, pager, next" background
          @current-change="load"
        />
      </div>
    </el-card>

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" title="员工档案" size="520px">
      <div v-loading="detailLoading">
        <template v-if="detail">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="姓名">{{ detail.name }}</el-descriptions-item>
            <el-descriptions-item label="工号">{{ detail.emp_no }}</el-descriptions-item>
            <el-descriptions-item label="部门">{{ detail.dept_name }}</el-descriptions-item>
            <el-descriptions-item label="组别">{{ detail.group_name }}</el-descriptions-item>
            <el-descriptions-item label="岗位">{{ detail.position }}</el-descriptions-item>
            <el-descriptions-item label="合同类型">{{ detail.contract_type }}</el-descriptions-item>
            <el-descriptions-item label="入职日期">{{ detail.hire_date }}</el-descriptions-item>
            <el-descriptions-item label="转正日期">{{ detail.regular_date }}</el-descriptions-item>
            <el-descriptions-item label="性别">{{ detail.gender }}</el-descriptions-item>
            <el-descriptions-item label="学历">{{ detail.education }} {{ detail.school }}</el-descriptions-item>
            <el-descriptions-item label="电话">{{ detail.phone }}</el-descriptions-item>
            <el-descriptions-item label="邮箱">{{ detail.email }}</el-descriptions-item>
            <el-descriptions-item label="身份证">{{ detail.id_card }}</el-descriptions-item>
            <el-descriptions-item label="社保公积金">{{ detail.has_social_insurance }} / {{ detail.has_housing_fund }}</el-descriptions-item>
            <el-descriptions-item label="现住地址" :span="2">{{ detail.current_address }}</el-descriptions-item>
          </el-descriptions>
          <h4>劳动合同与续签</h4>
          <el-table :data="detail.contracts || []" size="small" border>
            <el-table-column label="合同阶段" width="120">
              <template #default="{ row }">
                {{ row.seq_no === 1 ? '首次' : row.seq_no === 2 ? '二次续签' : row.seq_no === 3 ? '三次续签' : row.contract_type }}
              </template>
            </el-table-column>
            <el-table-column prop="start_date" label="开始" />
            <el-table-column prop="end_date" label="截止" />
          </el-table>
        </template>
      </div>
    </el-drawer>

    <!-- 新增/编辑 -->
    <el-drawer v-model="editVisible" :title="isNew ? '新增员工' : '编辑员工'" size="480px">
      <el-form :model="editForm" label-width="90px">
        <el-form-item label="姓名"><el-input v-model="editForm.name" /></el-form-item>
        <el-form-item label="部门"><el-input v-model="editForm.dept_name" /></el-form-item>
        <el-form-item label="组别"><el-input v-model="editForm.group_name" /></el-form-item>
        <el-form-item label="岗位"><el-input v-model="editForm.position" /></el-form-item>
        <el-form-item label="入职日期"><el-input v-model="editForm.hire_date" placeholder="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="转正日期"><el-input v-model="editForm.regular_date" placeholder="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="性别">
          <el-select v-model="editForm.gender" style="width: 100%">
            <el-option label="男" value="男" /><el-option label="女" value="女" />
          </el-select>
        </el-form-item>
        <el-form-item label="学历"><el-input v-model="editForm.education" /></el-form-item>
        <el-form-item label="电话"><el-input v-model="editForm.phone" /></el-form-item>
        <el-form-item label="身份证（HR）"><el-input v-model="editForm.id_card" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="editForm.remark" type="textarea" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-drawer>

    <!-- 提醒中心 -->
    <el-drawer v-model="remindersOpen" title="提醒中心" size="520px">
      <div v-loading="remindersLoading">
        <el-empty v-if="!Object.keys(reminders || {}).some((k) => (reminders as any)[k]?.length)" description="暂无提醒" />
        <template v-for="(group, label) in (reminders || {})" :key="label">
          <template v-if="(group as any[])?.length">
            <h4>{{ descOf(label as string)[0] }}（{{ (group as any[]).length }}）</h4>
            <el-table :data="(group as any[])" size="small" border>
              <el-table-column prop="name" label="姓名" width="90" />
              <el-table-column prop="dept" label="部门" />
              <el-table-column label="说明">
                <template #default="{ row }">
                  <span v-if="label === 'contract_expiry'">{{ notice('合同', row.end_date) }}（剩 {{ row.days_left }} 天）</span>
                  <span v-else-if="label === 'regular_upcoming'">{{ notice('转正', row.regular_date) }}</span>
                  <span v-else-if="label === 'probation_overdue'">入职 {{ row.hire_date }} 试用期已超期 {{ row.days_overdue }} 天</span>
                  <span v-else-if="label === 'probation_expiry'">入职 {{ row.hire_date }}，试用到期 {{ row.probation_end }}</span>
                  <span v-else-if="label === 'birthday'">{{ row.birthday }}（{{ row.age }} 岁）</span>
                  <span v-else-if="label === 'id_card_expiry'">证件 {{ row.expiry_date }} 到期</span>
                </template>
              </el-table-column>
            </el-table>
          </template>
        </template>
      </div>
    </el-drawer>

    <!-- 导入 -->
    <el-dialog v-model="importVisible" title="导入员工花名册" width="560px">
      <p>上传《示例科技 员工花名册.xlsx》（将自动导入员工花名册 + 离职两表，幂等去重）。</p>
      <el-upload v-model:file-list="fileList" :auto-upload="false" drag :limit="1" accept=".xlsx"
        :on-change="() => { importReport = null }">
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽文件到此处或点击选择</div>
      </el-upload>
      <div v-if="importReport" style="margin-top: 12px">
        <el-alert v-if="importReport.roster" :title="importReport.roster.message" type="success" :closable="false" show-icon />
        <el-alert v-if="importReport.resign" :title="importReport.resign.message" type="info" :closable="false" show-icon style="margin-top: 6px" />
      </div>
      <template #footer>
        <el-button @click="importVisible = false">关闭</el-button>
        <el-button type="primary" :loading="importing" :disabled="!fileList.length" @click="doImport">开始导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.hr-page { padding: 18px 22px 30px; }

/* === 工具栏 === */
.roster-card { border: 1px solid light-dark(#e2e8f0, var(--border-color)); box-shadow: 0 1px 2px rgba(15,23,42,.04); }
.toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 4px 4px 14px;
  border-bottom: 1px solid light-dark(#f1f5f9, var(--border-color));
  margin-bottom: 14px;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; }
.toolbar-btn { font-weight: 600; }
.btn-tag { margin-left: 6px; transform: translateY(-1px); }

/* 顶部统计 pill */
.stat-pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 12px; border-radius: 999px;
  background: linear-gradient(135deg, #ecfdf5 0%, #f0fdfa 100%);
  color: light-dark(#065f46, var(--text-accent)); font-size: 13px; font-weight: 600;
  border: 1px solid rgba(15,118,110,.18);
}
.stat-pill b { font-weight: 800; color: light-dark(#0f766e, var(--text-accent)); font-size: 14px; }
.stat-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #10b981; box-shadow: 0 0 0 3px rgba(16,185,129,.18);
  animation: pulse 1.8s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 3px rgba(16,185,129,.18); }
  50% { box-shadow: 0 0 0 6px rgba(16,185,129,.06); }
}

/* === 筛选区 === */
.filters {
  display: flex; gap: 10px; align-items: center;
  --el-component-size: 36px;
  margin-bottom: 16px;
  padding-bottom: 14px;
  border-bottom: 1px dashed light-dark(#eef1f5, var(--border-color));
}
.filter-input :deep(.el-input__wrapper),
.filter-select :deep(.el-select__wrapper) {
  min-height: 36px; border-radius: 8px;
}
.filter-btn { height: 36px; padding: 0 18px; }

/* === 表格 === */
.roster-table {
  --el-table-border-color: light-dark(#eef2f7, var(--border-color));
  border-radius: 8px;
  overflow: hidden;
}
.roster-table :deep(.el-table__cell) { padding: 10px 0; }
.roster-table :deep(.el-table__row) { transition: background-color .15s ease; }
.roster-table :deep(.el-table__row--striped td.el-table__cell) { background: light-dark(#fafbfc, var(--app-surface-2)); }
.roster-table :deep(.el-table__row:hover > td.el-table__cell) { background: rgba(15,118,110,.06) !important; }
.roster-table :deep(.tbl-header th.el-table__cell) {
  background: light-dark(#f8fafc, var(--app-surface-2)) !important;
  color: light-dark(#475569, var(--text-secondary)); font-weight: 600; font-size: 13px;
  border-bottom: 1px solid light-dark(#e2e8f0, var(--border-color));
}

/* 单元格样式 */
.cell-name { font-weight: 700; color: light-dark(#0f172a, var(--text-primary)); letter-spacing: .02em; }
.cell-empty { color: light-dark(#cbd5e1, var(--text-secondary)); }
.cell-date {
  display: flex; flex-direction: column; justify-content: center;
  gap: 3px; line-height: 1.35;
}
.cell-date .date-main { font-weight: 600; color: light-dark(#334155, var(--text-primary)); font-variant-numeric: tabular-nums; }
.cell-date .date-sub { font-size: 11px; color: light-dark(#94a3b8, var(--text-secondary)); }
.cell-phone { font-variant-numeric: tabular-nums; color: light-dark(#475569, var(--text-secondary)); }

/* 操作列按钮 */
.row-ops { display: flex; align-items: center; justify-content: center; gap: 8px; }
.row-ops :deep(.el-button) { margin: 0; min-width: 56px; }
.row-ops :deep(.el-popover__reference) { display: inline-flex; }

/* === 分页 === */
.pagination-wrap {
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 10px;
  margin-top: 18px;
  padding: 14px 4px 8px;
  border-top: 1px dashed light-dark(#eef1f5, var(--border-color));
}
.page-summary { color: light-dark(#64748b, var(--text-secondary)); font-size: 13px; }
.page-summary b { color: light-dark(#0f766e, var(--text-accent)); font-weight: 800; }

/* === Drawer / Dialog 内部样式 === */
h4 { margin: 18px 0 10px; font-size: 14px; color: light-dark(#334155, var(--text-primary)); }
</style>
