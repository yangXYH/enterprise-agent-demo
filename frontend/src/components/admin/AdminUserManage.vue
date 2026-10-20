<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  ElButton, ElCard, ElDialog, ElForm, ElFormItem, ElInput,
  ElLoading, ElMessage, ElMessageBox, ElOption, ElSelect,
  ElTable, ElTableColumn, ElTag,
} from 'element-plus'
import request from '../../utils/request'

const vLoading = ElLoading.directive

interface Account {
  id: number
  username: string
  real_name: string
  department: string
  job_title: string
  role: string
  created_at: string
}

const roleNames: Record<string, string> = {
  admin: '管理员', 管理员: '管理员', boss: '总经理/副总', operator: '运营/客服',
  designer: '设计师', hr: '人力行政', finance: '财务', supply: '供应链', user: '普通员工',
}
const roles = ['user', 'designer', 'operator', 'supply', 'hr', 'finance', 'boss', 'admin', '管理员']
const accounts = ref<Account[]>([])
const currentUsername = localStorage.getItem('auth_username') || ''
const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
const department = ref('')
const dialogOpen = ref(false)
const passwordOpen = ref(false)
const editingId = ref<number | null>(null)
const resetTarget = ref<Account | null>(null)
const newPassword = ref('')
const form = reactive({ username: '', real_name: '', department: '', job_title: '', role: 'user', password: '' })

const departments = computed(() => [...new Set(accounts.value.map(x => x.department).filter(Boolean))].sort())
const jobTitles = computed(() => [...new Set(accounts.value.map(x => x.job_title).filter(Boolean))].sort())
const filtered = computed(() => accounts.value.filter(x => {
  const query = keyword.value.trim().toLowerCase()
  return (!department.value || x.department === department.value) &&
    (!query || [x.username, x.real_name, x.department, x.job_title, x.role]
      .some(v => (v || '').toLowerCase().includes(query)))
}))
const adminCount = computed(() => accounts.value.filter(x => ['admin', '管理员'].includes(x.role)).length)

async function load() {
  loading.value = true
  try {
    const data = await request.get('/admin/users') as { users: Account[] }
    accounts.value = data.users || []
  } finally { loading.value = false }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { username: '', real_name: '', department: '', job_title: '', role: 'user', password: '' })
  dialogOpen.value = true
}

function openEdit(row: Account) {
  editingId.value = row.id
  Object.assign(form, { username: row.username, real_name: row.real_name,
    department: row.department, job_title: row.job_title || '', role: row.role, password: '' })
  dialogOpen.value = true
}

async function save() {
  if (!form.real_name.trim() || !form.department.trim() || !form.username.trim()) {
    ElMessage.warning('请填写账号、姓名和部门')
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await request.put(`/admin/users/${editingId.value}`, {
        real_name: form.real_name, department: form.department,
        job_title: form.job_title, role: form.role,
      })
    } else {
      await request.post('/admin/users', { ...form })
    }
    dialogOpen.value = false
    ElMessage.success(editingId.value ? '账号已更新' : '账号已创建')
    await load()
  } catch { /* 请求拦截器显示错误 */ }
  finally { saving.value = false }
}

function openReset(row: Account) {
  resetTarget.value = row
  newPassword.value = ''
  passwordOpen.value = true
}

async function resetPassword() {
  if (!resetTarget.value) return
  saving.value = true
  try {
    await request.post(`/admin/users/${resetTarget.value.id}/reset-password`, { password: newPassword.value })
    ElMessage.success('密码已重置，原登录状态将失效')
    passwordOpen.value = false
    newPassword.value = ''
  } catch { /* 请求拦截器显示错误 */ }
  finally { saving.value = false }
}

async function remove(row: Account) {
  try {
    await ElMessageBox.confirm(`删除 ${row.real_name}（${row.username}）的登录账号？`, '确认删除', {
      type: 'warning', confirmButtonText: '删除账号', cancelButtonText: '取消',
    })
  } catch { return }
  try {
    await request.delete(`/admin/users/${row.id}`)
    ElMessage.success('账号已删除')
    await load()
  } catch { /* 请求拦截器显示错误 */ }
}

onMounted(() => { void load().catch(() => {}) })
</script>

<template>
  <div class="users-page">
    <header class="users-header">
      <div>
        <div class="eyebrow">系统管理 / 账号管理</div>
        <h2>员工账号管理</h2>
        <p>创建登录账号、分配角色、维护员工资料与重置密码。页面访问范围请在权限管理中设置。</p>
      </div>
      <el-button type="primary" @click="openCreate">＋ 新增账号</el-button>
    </header>

    <div class="stats">
      <div class="stat"><span>登录账号</span><strong>{{ accounts.length }}</strong></div>
      <div class="stat"><span>管理员</span><strong>{{ adminCount }}</strong></div>
      <div class="stat"><span>覆盖部门</span><strong>{{ departments.length }}</strong></div>
    </div>

    <el-card shadow="never" class="table-card">
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="搜索姓名、账号、岗位或角色" clearable style="max-width: 310px" />
        <el-select v-model="department" placeholder="全部部门" clearable style="width: 180px">
          <el-option v-for="item in departments" :key="item" :label="item" :value="item" />
        </el-select>
        <el-button @click="load">刷新</el-button>
        <span class="result-count">{{ filtered.length }} 条结果</span>
      </div>
      <el-table :data="filtered" v-loading="loading" stripe class="account-table">
        <el-table-column label="员工" min-width="170">
          <template #default="{ row }"><div class="person"><span class="avatar">{{ row.real_name?.slice(0, 1) }}</span><div><strong>{{ row.real_name }}</strong><small>{{ row.username }}</small></div></div></template>
        </el-table-column>
        <el-table-column prop="department" label="部门" min-width="150" />
        <el-table-column prop="job_title" label="岗位" min-width="150" show-overflow-tooltip />
        <el-table-column label="角色" min-width="130">
          <template #default="{ row }"><el-tag :type="['admin', '管理员'].includes(row.role) ? 'danger' : 'info'" effect="plain">{{ roleNames[row.role] || row.role }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" min-width="160">
          <template #default="{ row }">{{ row.created_at ? String(row.created_at).slice(0, 10) : '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="225" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row as Account)">编辑</el-button>
            <el-button link type="primary" @click="openReset(row as Account)">重置密码</el-button>
            <el-button link type="danger" :disabled="row.username === currentUsername" @click="remove(row as Account)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogOpen" :title="editingId ? '编辑员工账号' : '新增员工账号'" width="520px" destroy-on-close>
      <el-form label-position="top">
        <div class="form-grid">
          <el-form-item label="登录账号"><el-input v-model="form.username" :disabled="!!editingId" /></el-form-item>
          <el-form-item label="员工姓名"><el-input v-model="form.real_name" maxlength="50" /></el-form-item>
          <el-form-item label="所属部门"><el-select v-model="form.department" filterable allow-create default-first-option style="width: 100%">
            <el-option v-for="item in departments" :key="item" :label="item" :value="item" />
          </el-select></el-form-item>
          <el-form-item label="岗位"><el-select v-model="form.job_title" filterable allow-create default-first-option style="width: 100%">
            <el-option v-for="item in jobTitles" :key="item" :label="item" :value="item" />
          </el-select></el-form-item>
          <el-form-item label="角色"><el-select v-model="form.role" style="width: 100%"><el-option v-for="role in roles" :key="role" :label="roleNames[role]" :value="role" /></el-select></el-form-item>
          <el-form-item v-if="!editingId" label="初始密码"><el-input v-model="form.password" type="password" show-password autocomplete="new-password" /></el-form-item>
        </div>
      </el-form>
      <template #footer><el-button @click="dialogOpen = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存账号</el-button></template>
    </el-dialog>

    <el-dialog v-model="passwordOpen" :title="`重置密码 · ${resetTarget?.real_name || ''}`" width="430px" destroy-on-close>
      <p class="dialog-help">设置后，当前账号的已有登录状态将失效。</p>
      <el-input v-model="newPassword" type="password" show-password autocomplete="new-password" @keyup.enter="resetPassword" />
      <template #footer><el-button @click="passwordOpen = false">取消</el-button><el-button type="primary" :loading="saving" @click="resetPassword">确认重置</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.users-page { padding: 22px; color: light-dark(#17243a, var(--text-primary)); }
.users-header { display: flex; justify-content: space-between; align-items: center; gap: 20px; margin-bottom: 22px; }
.users-header h2 { margin: 5px 0 6px; font-size: 24px; }
.users-header p { margin: 0; color: light-dark(#66758c, var(--text-secondary)); font-size: 13px; }
.eyebrow { color: light-dark(#6280aa, var(--text-secondary)); font-size: 12px; font-weight: 700; letter-spacing: .06em; }
.stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }
.stat { padding: 18px 22px; background: light-dark(#fff, var(--app-surface)); border: 1px solid light-dark(#e6ebf2, var(--border-color)); border-radius: 12px; display: flex; justify-content: space-between; align-items: center; }
.stat span { color: light-dark(#687a92, var(--text-secondary)); font-size: 13px; } .stat strong { font-size: 25px; }
.table-card { border-radius: 12px; } .toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
.result-count { margin-left: auto; color: light-dark(#8390a4, var(--text-secondary)); font-size: 12px; }
.person { display: flex; align-items: center; gap: 10px; } .person strong, .person small { display: block; }
.person small { color: light-dark(#8b98aa, var(--text-secondary)); font-size: 12px; margin-top: 2px; }
.avatar { width: 34px; height: 34px; border-radius: 10px; background: light-dark(#e8efff, rgba(96, 165, 250, .12)); color: light-dark(#426ab2, #93c5fd); display: grid; place-items: center; font-weight: 700; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; } .dialog-help { color: light-dark(#66758c, var(--text-secondary)); margin-top: 0; }
@media (max-width: 700px) { .users-header { align-items: flex-start; flex-direction: column; } .stats { grid-template-columns: 1fr; } .form-grid { grid-template-columns: 1fr; } }
</style>
