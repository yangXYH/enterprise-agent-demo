<script setup lang="ts">
import { computed, onActivated, ref } from 'vue'
import {
  ElButton, ElDatePicker, ElDialog, ElForm, ElFormItem, ElInput,
  ElInputNumber, ElMessage, ElOption, ElPagination, ElSelect,
  ElSwitch, ElTable, ElTableColumn, ElTag, vLoading,
} from 'element-plus'
import request from '../utils/request'

type Employee = {
  id: number; rank: number; emp_no: string; name: string; company: string
  dept_name: string; position: string; total_points: number; month_points: number; record_count: number
}
type Rule = { id: number; name: string; points: number; description: string; is_active: number }
type RecordItem = {
  id: number; employee_id: number; employee_name: string; rule_name: string
  points: number; note: string; operator: string; created_at: string
}
type RankResponse = {
  items: Employee[]; total: number; scored_count: number; total_points: number
  companies: string[]; departments: string[]; month: string
}
const props = defineProps<{ view: string }>()
const canEdit = computed(() => ['admin', 'hr', '管理员'].includes((localStorage.getItem('auth_role') || '').toLowerCase()))
const loading = ref(false)
const rows = ref<Employee[]>([])
const allEmployees = ref<Employee[]>([])
const companies = ref<string[]>([])
const departments = ref<string[]>([])
const scoredCount = ref(0)
const totalPoints = ref(0)
const company = ref('')
const dept = ref('')
const keyword = ref('')
const month = ref(`${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}`)
const sort = ref<'total' | 'month'>('total')
const rules = ref<Rule[]>([])
const records = ref<RecordItem[]>([])
const recordTotal = ref(0)
const recordPage = ref(1)
const recordMonth = ref('')
const recordEmployeeId = ref(0)
const awardVisible = ref(false)
const awardSaving = ref(false)
const awardForm = ref({ employee_id: 0, rule_id: 0, note: '' })
const ruleVisible = ref(false)
const ruleSaving = ref(false)
const ruleForm = ref({ id: 0, name: '', points: 1, description: '', is_active: true })
const activeRules = computed(() => rules.value.filter(rule => rule.is_active))

const loadRank = async () => {
  loading.value = true
  try {
    const data = await request.get('/points/leaderboard', {
      params: { company: company.value, dept: dept.value, keyword: keyword.value, month: month.value, sort: sort.value },
    }) as RankResponse
    rows.value = data.items
    companies.value = data.companies
    departments.value = data.departments
    scoredCount.value = data.scored_count
    totalPoints.value = data.total_points
  } catch { rows.value = [] } finally { loading.value = false }
}

const loadEmployees = async () => {
  try {
    const data = await request.get('/points/leaderboard') as RankResponse
    allEmployees.value = data.items
  } catch { allEmployees.value = [] }
}

const loadRules = async () => {
  try {
    const data = await request.get('/points/rules') as { items: Rule[] }
    rules.value = data.items
  } catch { rules.value = [] }
}

const loadRecords = async () => {
  loading.value = true
  try {
    const data = await request.get('/points/records', {
      params: { employee_id: recordEmployeeId.value || 0, month: recordMonth.value || '', page: recordPage.value, page_size: 20 },
    }) as { items: RecordItem[]; total: number }
    records.value = data.items
    recordTotal.value = data.total
  } catch { records.value = []; recordTotal.value = 0 } finally { loading.value = false }
}

const openAward = (employeeId = 0) => {
  awardForm.value = { employee_id: employeeId, rule_id: 0, note: '' }
  awardVisible.value = true
}
const saveAward = async () => {
  if (!awardForm.value.employee_id || !awardForm.value.rule_id || !awardForm.value.note.trim()) {
    ElMessage.warning('请选择员工、积分规则并填写事项说明')
    return
  }
  awardSaving.value = true
  try {
    await request.post('/points/records', awardForm.value)
    ElMessage.success('积分登记成功')
    awardVisible.value = false
    await Promise.all([loadRank(), loadRecords()])
  } catch {} finally { awardSaving.value = false }
}
const openRule = (rule?: Rule) => {
  ruleForm.value = rule
    ? { id: rule.id, name: rule.name, points: rule.points, description: rule.description, is_active: Boolean(rule.is_active) }
    : { id: 0, name: '', points: 1, description: '', is_active: true }
  ruleVisible.value = true
}
const saveRule = async () => {
  ruleSaving.value = true
  try {
    await request.post('/points/rules', ruleForm.value)
    ElMessage.success('规则已保存')
    ruleVisible.value = false
    await loadRules()
  } catch {} finally { ruleSaving.value = false }
}
const scoreText = (score: number) => score > 0 ? `+${score}` : String(score)
const timestamp = (value: string) => value ? value.replace('T', ' ').slice(0, 19) : '—'

onActivated(async () => {
  await Promise.all([loadRules(), loadEmployees()])
  if (props.view === 'points') await loadRank()
  if (props.view === 'points-log') await loadRecords()
})
</script>

<template>
  <div class="points-page">
    <div class="points-heading">
      <div>
        <div class="points-eyebrow">EMPLOYEE RECOGNITION</div>
        <h1>{{ view === 'points' ? '员工积分排行榜' : view === 'points-rule' ? '积分规则' : '积分明细' }}</h1>
        <p>人员来自人力资源花名册；积分来自已登记的真实流水。</p>
      </div>
      <el-button v-if="canEdit && view !== 'points-rule'" type="primary" @click="openAward()">登记积分</el-button>
      <el-button v-if="canEdit && view === 'points-rule'" type="primary" @click="openRule()">新建规则</el-button>
    </div>

    <template v-if="view === 'points'">
      <div class="points-stats">
        <div><span>在职员工</span><strong>{{ rows.length }}</strong><small>当前筛选范围</small></div>
        <div><span>有积分员工</span><strong>{{ scoredCount }}</strong><small>至少有一条积分记录</small></div>
        <div><span>累计净积分</span><strong>{{ totalPoints.toLocaleString() }}</strong><small>当前筛选范围</small></div>
      </div>
      <div class="points-panel">
        <div class="points-toolbar">
          <el-input v-model="keyword" clearable placeholder="搜索姓名或工号" style="width:190px" @keyup.enter="loadRank" @clear="loadRank" />
          <el-select v-model="company" placeholder="全部公司" clearable style="width:145px" @change="dept = ''; loadRank()"><el-option v-for="item in companies" :key="item" :label="item" :value="item" /></el-select>
          <el-select v-model="dept" placeholder="全部部门" clearable filterable style="width:160px" @change="loadRank"><el-option v-for="item in departments" :key="item" :label="item" :value="item" /></el-select>
          <el-date-picker v-model="month" type="month" value-format="YYYY-MM" placeholder="统计月份" style="width:145px" @change="loadRank" />
          <el-select v-model="sort" style="width:130px" @change="loadRank"><el-option label="累计排行" value="total" /><el-option label="当月排行" value="month" /></el-select>
          <el-button @click="loadRank">查询</el-button>
        </div>
        <el-table v-loading="loading" :data="rows" stripe empty-text="花名册暂无在职员工" class="points-table">
          <el-table-column label="排名" width="86"><template #default="{ row }"><span class="rank-number" :class="{ top: row.rank <= 3 && (sort === 'month' ? row.month_points : row.total_points) !== 0 }">{{ row.rank }}</span></template></el-table-column>
          <el-table-column label="员工" min-width="160"><template #default="{ row }"><div class="employee-cell"><span class="avatar">{{ row.name.slice(-1) }}</span><div><strong>{{ row.name }}</strong><small>{{ row.emp_no || '—' }}</small></div></div></template></el-table-column>
          <el-table-column prop="company" label="公司" min-width="120" />
          <el-table-column prop="dept_name" label="部门" min-width="130" />
          <el-table-column prop="position" label="岗位" min-width="130" />
          <el-table-column label="累计积分" min-width="115"><template #default="{ row }"><strong>{{ row.total_points.toLocaleString() }}</strong></template></el-table-column>
          <el-table-column label="当月积分" min-width="115"><template #default="{ row }"><span :class="row.month_points > 0 ? 'positive' : row.month_points < 0 ? 'negative' : ''">{{ scoreText(row.month_points) }}</span></template></el-table-column>
          <el-table-column v-if="canEdit" label="操作" width="90"><template #default="{ row }"><el-button link type="primary" @click="openAward(row.id)">登记</el-button></template></el-table-column>
        </el-table>
        <p v-if="rows.length && !scoredCount" class="points-hint">所有员工当前为 0 分。请先在“积分规则”中建立规则，再登记积分。</p>
      </div>
    </template>

    <div v-else-if="view === 'points-rule'" class="points-panel">
      <div class="panel-intro"><h2>计分规则</h2><p>正数为加分，负数为扣分；停用后不可再用于新登记。修改规则不会改变历史积分。</p></div>
      <el-table :data="rules" stripe empty-text="暂无规则，请管理员或 HR 新建规则">
        <el-table-column prop="name" label="规则名称" min-width="170" />
        <el-table-column label="积分" width="100"><template #default="{ row }"><strong :class="row.points > 0 ? 'positive' : 'negative'">{{ scoreText(row.points) }}</strong></template></el-table-column>
        <el-table-column prop="description" label="适用说明" min-width="260" show-overflow-tooltip />
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag></template></el-table-column>
        <el-table-column v-if="canEdit" label="操作" width="90"><template #default="{ row }"><el-button link type="primary" @click="openRule(row as Rule)">编辑</el-button></template></el-table-column>
      </el-table>
    </div>

    <div v-else class="points-panel">
      <div class="panel-intro"><h2>积分流水</h2><p>每次登记都会留下员工、规则、分值、操作人和时间；需要纠正时请登记一条反向积分。</p></div>
      <div class="points-toolbar">
        <el-select v-model="recordEmployeeId" filterable clearable placeholder="全部员工" style="width:190px" @change="recordPage = 1; loadRecords()"><el-option v-for="item in allEmployees" :key="item.id" :label="`${item.name} · ${item.company}`" :value="item.id" /></el-select>
        <el-date-picker v-model="recordMonth" type="month" value-format="YYYY-MM" placeholder="全部月份" style="width:155px" @change="recordPage = 1; loadRecords()" />
        <el-button @click="loadRecords">刷新</el-button>
      </div>
      <el-table v-loading="loading" :data="records" stripe empty-text="暂无积分记录">
        <el-table-column prop="employee_name" label="员工" min-width="115" />
        <el-table-column prop="rule_name" label="计分规则" min-width="165" />
        <el-table-column label="积分变动" width="115"><template #default="{ row }"><strong :class="row.points > 0 ? 'positive' : 'negative'">{{ scoreText(row.points) }}</strong></template></el-table-column>
        <el-table-column prop="note" label="备注" min-width="220" show-overflow-tooltip />
        <el-table-column prop="operator" label="操作人" width="110" />
        <el-table-column label="登记时间" width="178"><template #default="{ row }">{{ timestamp(row.created_at) }}</template></el-table-column>
      </el-table>
      <div class="pager"><el-pagination v-model:current-page="recordPage" layout="prev, pager, next, total" :page-size="20" :total="recordTotal" @current-change="loadRecords" /></div>
    </div>

    <el-dialog v-model="awardVisible" title="登记员工积分" width="480px">
      <el-form label-position="top">
        <el-form-item label="员工"><el-select v-model="awardForm.employee_id" filterable placeholder="搜索在职员工" style="width:100%"><el-option v-for="item in allEmployees" :key="item.id" :label="`${item.name} · ${item.company} · ${item.dept_name}`" :value="item.id" /></el-select></el-form-item>
        <el-form-item label="积分规则"><el-select v-model="awardForm.rule_id" placeholder="请选择规则" style="width:100%"><el-option v-for="item in activeRules" :key="item.id" :label="`${item.name} (${scoreText(item.points)})`" :value="item.id" /></el-select></el-form-item>
        <el-form-item label="备注"><el-input v-model="awardForm.note" type="textarea" :rows="3" maxlength="1000" show-word-limit placeholder="记录具体事项，便于追溯" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="awardVisible = false">取消</el-button><el-button type="primary" :loading="awardSaving" @click="saveAward">确认登记</el-button></template>
    </el-dialog>

    <el-dialog v-model="ruleVisible" :title="ruleForm.id ? '编辑积分规则' : '新建积分规则'" width="480px">
      <el-form label-position="top">
        <el-form-item label="规则名称"><el-input v-model="ruleForm.name" maxlength="100" placeholder="例如：跨部门协作" /></el-form-item>
        <el-form-item label="积分值"><el-input-number v-model="ruleForm.points" :min="-100000" :max="100000" :step="1" :precision="0" controls-position="right" style="width:100%" /><span class="form-help">正数加分，负数扣分，不能为 0</span></el-form-item>
        <el-form-item label="适用说明"><el-input v-model="ruleForm.description" type="textarea" :rows="3" maxlength="500" show-word-limit /></el-form-item>
        <el-form-item label="状态"><el-switch v-model="ruleForm.is_active" active-text="启用" inactive-text="停用" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="ruleVisible = false">取消</el-button><el-button type="primary" :loading="ruleSaving" @click="saveRule">保存规则</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.points-page{padding:24px;min-height:100%;background:light-dark(#f7f9fc, var(--app-bg));color:light-dark(#17243a, var(--text-primary))}
.points-heading{display:flex;justify-content:space-between;align-items:center;gap:18px;margin-bottom:22px}
.points-eyebrow{color:light-dark(#4f73a4, #93c5fd);font-size:11px;font-weight:800;letter-spacing:.15em;margin-bottom:7px}
h1{font-size:26px;line-height:1.3;margin:0 0 6px;font-weight:750}h2{font-size:17px;margin:0 0 5px}
.points-heading p,.panel-intro p{margin:0;color:light-dark(#718096, var(--text-secondary));font-size:13px}
.points-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-bottom:16px}
.points-stats>div{display:flex;flex-direction:column;background:light-dark(#fff, var(--app-surface));border:1px solid light-dark(#e8edf3, var(--border-color));border-radius:12px;padding:18px 20px;box-shadow:0 2px 8px rgba(24,42,67,.03)}
.points-stats span{color:light-dark(#718096, var(--text-secondary));font-size:13px}.points-stats strong{font-size:29px;line-height:1.3;margin:7px 0 2px;font-variant-numeric:tabular-nums}.points-stats small{color:light-dark(#94a3b8, var(--text-secondary));font-size:12px}
.points-panel{background:light-dark(#fff, var(--app-surface));border:1px solid light-dark(#e8edf3, var(--border-color));border-radius:12px;padding:19px 20px;box-shadow:0 2px 8px rgba(24,42,67,.03)}
.points-toolbar{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-bottom:17px}.panel-intro{margin-bottom:18px}
.employee-cell{display:flex;align-items:center;gap:10px}.employee-cell strong,.employee-cell small{display:block}.employee-cell small{color:light-dark(#9aa7b8, var(--text-secondary));font-size:11px;margin-top:2px}.avatar{width:32px;height:32px;border-radius:10px;background:light-dark(#e8f0fb, rgba(96, 165, 250, .12));color:light-dark(#3764a0, #93c5fd);display:grid;place-items:center;font-weight:700}
.rank-number{display:inline-grid;place-items:center;width:25px;height:25px;color:light-dark(#66788f, var(--text-secondary));font-weight:700}.rank-number.top{border-radius:7px;background:light-dark(#fff2db, rgba(248, 113, 113, .12));color:light-dark(#a56813, #fbbf24)}
.positive{color:light-dark(#0c9a70, var(--text-accent))}.negative{color:light-dark(#d45454, #fca5a5)}.points-hint{color:light-dark(#8a98a9, var(--text-secondary));font-size:12px;margin:14px 0 0}.pager{display:flex;justify-content:flex-end;margin-top:17px}.form-help{color:light-dark(#8a98a9, var(--text-secondary));font-size:12px;margin-top:5px}
@media(max-width:850px){.points-page{padding:14px}.points-stats{grid-template-columns:1fr}.points-panel{padding:14px}.points-heading{align-items:flex-start}.points-toolbar>*{max-width:100%}}
</style>
