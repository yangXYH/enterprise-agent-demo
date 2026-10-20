<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  ElButton,
  ElCard,
  ElCheckbox,
  ElCheckboxGroup,
  ElCollapse,
  ElCollapseItem,
  ElDivider,
  ElDrawer,
  ElIcon,
  ElMessage,
  ElTable,
  ElTableColumn,
  ElTag,
} from 'element-plus'
import { Check, Refresh, Search } from '@element-plus/icons-vue'
import request from '../../utils/request'

interface SubPerm {
  sub_key: string
  label: string
  roles: string[]
}
interface PagePerm {
  page_key: string
  label: string
  roles: string[]
  subpages?: SubPerm[]
}
interface RoleItem {
  role: string
  label: string
  username: string
  real_name: string
}
interface UserItem {
  username: string
  real_name: string
  emp_no: string
  department: string
  job_title: string
  role: string
}
interface NavGroup {
  label: string
  pages: { page_key: string; label: string }[]
}

// 镜像主导航，只保留「真正接入了权限管控」的页面
// reactive 包裹：load() 拿到后端 pages 后会动态把店铺子项注入「店铺报表」分组
const pageNavGroups = reactive<NavGroup[]>([
  { label: '公司首页', pages: [
    { page_key: 'ecommerce-dashboard', label: '经营看板首页' },
    { page_key: 'knowledge-qa', label: 'AI 知识问答' },
    { page_key: 'ai-project-board', label: 'AI 项目进度看板' },
  ]},
  { label: '数据洞察', pages: [
    { page_key: 'insight', label: '经营总览' },
    { page_key: 'insight-trend', label: '趋势分析' },
    { page_key: 'insight-category', label: '品类分析' },
    { page_key: 'insight-brand', label: '品牌与商品' },
  ]},
  { label: '店铺报表', pages: [
    { page_key: 'shop-report', label: '店铺报表' },
  ]},
  { label: '设计部', pages: [
    { page_key: 'design-overview', label: '设计资料总览' },
    { page_key: 'design-models', label: 'AI模特与场景案例' },
    { page_key: 'design-prompts', label: 'AI生图提示词库' },
    { page_key: 'design-comparisons', label: '生图前后对照' },
    { page_key: 'design-styles', label: '视觉要素手册' },
  ]},
  { label: '客服部', pages: [
    { page_key: 'cs-audit', label: '客服数据看板' },
    { page_key: 'after-sales-quality', label: '售后质量分析' },
    { page_key: 'product-quality-reports', label: '产品质检报告' },
  ]},
  { label: '运营部', pages: [
    { page_key: 'operating-analysis', label: '经营数据分析' },
    { page_key: 'operating-chat', label: 'AI 经营问答' },
    { page_key: 'sku-return-data', label: 'SKU 退货数据' },
    { page_key: 'inventory-decision', label: '库存分析决策' },
    { page_key: 'inventory-monitor', label: '库存看板监控' },
    { page_key: 'inventory-stockout', label: '库存断货数据' },
    { page_key: 'inventory-shortage', label: '库存缺货数据' },
    { page_key: 'inventory-listed', label: '库存上柜数据' },
    { page_key: 'inventory-delisted', label: '库存下柜数据' },
  ]},
  { label: '供应链部', pages: [
    { page_key: 'jushuitan-dashboard', label: '商品库存看板' },
    { page_key: 'sales-dashboard', label: '销售数据看板' },
    { page_key: 'inventory-product-dashboard', label: '进销商品看板' },
    { page_key: 'purchase-order-dashboard', label: '采购单看板' },
  ]},
  { label: '人力资源', pages: [
    { page_key: 'hr-driver', label: '人事驾驶舱' },
    { page_key: 'hr-roster', label: '人员花名册' },
    { page_key: 'hr-recruit', label: '招聘管理' },
    { page_key: 'hr-filter', label: 'AI 智能简历筛选' },
    { page_key: 'hr-knowledge', label: '人力行政知识库' },
  ]},
  { label: '积分系统', pages: [
    { page_key: 'points', label: '积分排行榜' },
    { page_key: 'points-rule', label: '积分规则' },
    { page_key: 'points-log', label: '积分明细' },
  ]},
])

const pages = ref<PagePerm[]>([])
const allRoles = ref<RoleItem[]>([])
const allUsers = ref<UserItem[]>([])
const ALL_ROLE = '*'
const loading = ref(false)
const saving = ref(false)

const drawerVisible = ref(false)
const editingPage = ref<PagePerm | null>(null)
const draftRoles = ref<string[]>([])
// 页签级（页面内容）权限草稿：sub_key -> 授权角色数组
const subDrafts = ref<Record<string, string[]>>({})
const openSubs = ref<string[]>([])

const navKeyword = ref('')

const normalize = (raw: any[]): PagePerm[] =>
  (raw || []).map((p) => ({
    page_key: p.page_key,
    label: p.label,
    roles: Array.isArray(p.roles) ? [...p.roles] : [],
    subpages: Array.isArray(p.subpages)
      ? p.subpages.map((s: any) => ({
          sub_key: s.sub_key,
          label: s.label || s.sub_key,
          roles: Array.isArray(s.roles) ? [...s.roles] : [],
        }))
      : undefined,
  }))

const load = async () => {
  loading.value = true
  try {
    const resp = await request.get('/hr/permission/pages') as any
    pages.value = normalize(resp.pages)
    allRoles.value = resp.roles || []
    allUsers.value = resp.users || []
    // 把后端返回的动态店铺页（shop-report:{channel}:{shop_id}）注入左侧「店铺报表」分组，
    // 位置紧跟在静态「店铺报表」「店铺报表 AI 问答」之后；其余分组保持硬编码。
    const shopGroup = pageNavGroups.find((g) => g.label === '店铺报表')
    if (shopGroup) {
      const staticKeys = new Set(shopGroup.pages.map((p) => p.page_key))
      const dynamic = (resp.pages || [])
        .filter((p: any) => typeof p.page_key === 'string' && p.page_key.startsWith('shop-report:') && !staticKeys.has(p.page_key))
        .map((p: any) => ({ page_key: p.page_key, label: p.label || p.page_key }))
      // 去重后按 label 排序，保持与侧边栏展开顺序一致
      const seen = new Set(shopGroup.pages.map((p) => p.page_key))
      for (const d of dynamic) {
        if (!seen.has(d.page_key)) {
          shopGroup.pages.push(d)
          seen.add(d.page_key)
        }
      }
    }
  } catch {
    // 拦截器已提示（403 为无权限，非 admin 不会进入此页）
  } finally {
    loading.value = false
  }
}

const roleLabelOf = (roleValue: string): string => {
  if (roleValue === ALL_ROLE) return '所有人可见'
  // 优先按角色名匹配；否则按用户名匹配
  const roleHit = allRoles.value.find((x) => x.role === roleValue)
  if (roleHit) return roleHit.label
  const userHit = allUsers.value.find((x) => x.username === roleValue)
  if (userHit) return userHit.real_name || userHit.username
  return roleValue
}

// 对当前页的授权 chips 按 label 去重，避免「管理员」+「管理员」显示成两个一样的标签
const dedupedChips = (roles: string[]): string[] => {
  const seen = new Set<string>()
  const out: string[] = []
  for (const r of roles) {
    const label = roleLabelOf(r)
    if (!seen.has(label)) {
      seen.add(label)
      out.push(r)
    }
  }
  return out
}

const isAllSelected = computed(() => draftRoles.value.includes(ALL_ROLE))
const isKnownGrant = (value: string): boolean =>
  value === ALL_ROLE || allRoles.value.some(r => r.role === value) || allUsers.value.some(u => u.username === value)
const legacyGrants = computed(() => draftRoles.value.filter(value => !isKnownGrant(value)))
const legacySubGrants = (key: string): string[] =>
  (subDrafts.value[key] || []).filter(value => !isKnownGrant(value))

const openEdit = (row: PagePerm) => {
  editingPage.value = row
  draftRoles.value = [...row.roles]
  subDrafts.value = {}
  for (const sp of row.subpages || []) subDrafts.value[sp.sub_key] = [...sp.roles]
  openSubs.value = []
  drawerVisible.value = true
}

const openEditByKey = (pageKey: string) => {
  const found = pages.value.find((p) => p.page_key === pageKey)
  if (found) openEdit(found)
}

const cancelEdit = () => {
  drawerVisible.value = false
  editingPage.value = null
  draftRoles.value = []
  subDrafts.value = {}
  openSubs.value = []
}

const confirmEdit = async () => {
  if (!editingPage.value) return
  const target = editingPage.value
  const sub_updates = (target.subpages || []).map((sp) => ({
    page_key: target.page_key,
    sub_key: sp.sub_key,
    roles: [...(subDrafts.value[sp.sub_key] || [])],
  }))
  saving.value = true
  try {
    // 保存当前这一页（页面权限 + 页签级内容权限），立即生效（无需再点全局保存）
    const resp = await request.put('/hr/permission/pages', {
      updates: [{ page_key: target.page_key, roles: [...draftRoles.value] }],
      sub_updates,
    }) as any
    const fresh = (resp.pages || []).find((p: any) => p.page_key === target.page_key)
    target.roles = fresh && Array.isArray(fresh.roles) ? [...fresh.roles] : [...draftRoles.value]
    // 用后端返回值回填页签权限，保持抽屉与数据库一致
    if (Array.isArray(resp.subpages) && target.subpages) {
      const mine = resp.subpages.filter((s: any) => s.page_key === target.page_key)
      for (const sp of target.subpages) {
        const hit = mine.find((s: any) => s.sub_key === sp.sub_key)
        if (hit && Array.isArray(hit.roles)) sp.roles = [...hit.roles]
        if (hit && Array.isArray(hit.roles)) subDrafts.value[sp.sub_key] = [...hit.roles]
      }
    }
    ElMessage.success('已保存并立即生效')
    cancelEdit()
  } catch {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
}

const onToggleAll = (val: boolean | string | number) => {
  const checked = !!val
  if (checked && !draftRoles.value.includes(ALL_ROLE)) {
    draftRoles.value = [ALL_ROLE, ...draftRoles.value]
  } else if (!checked) {
    draftRoles.value = draftRoles.value.filter((r) => r !== ALL_ROLE)
  }
}

// ── 页签级（页面内容）权限辅助 ───────────────────────────────────────────────
const subIsAll = (subKey: string): boolean => (subDrafts.value[subKey] || []).includes(ALL_ROLE)

const onSubToggleAll = (subKey: string, val: boolean | string | number) => {
  const checked = !!val
  const cur = subDrafts.value[subKey] || []
  subDrafts.value = {
    ...subDrafts.value,
    [subKey]: checked
      ? (cur.includes(ALL_ROLE) ? cur : [ALL_ROLE, ...cur])
      : cur.filter((r) => r !== ALL_ROLE),
  }
}

const subScopeSummary = (subKey: string, fallback: string[]): { text: string; hidden: boolean } => {
  const roles = subDrafts.value[subKey] ?? fallback
  if (!roles.length) return { text: '已隐藏', hidden: true }
  if (roles.includes(ALL_ROLE)) return { text: '所有人可见', hidden: false }
  const views = dedupedChips(roles).map((r) => roleLabelOf(r))
  const label = views.length <= 2 ? views.join('、') : `${views.slice(0, 2).join('、')} 等 ${views.length} 项`
  return { text: label, hidden: false }
}

// 把「全员」按部门分组显示
const groupedUsers = computed(() => {
  const map: Record<string, UserItem[]> = {}
  for (const u of allUsers.value) {
    const key = u.department || '其他'
    if (!map[key]) map[key] = []
    map[key].push(u)
  }
  return Object.fromEntries(
    Object.entries(map).sort(([a], [b]) => {
      if (!a || a === '其他') return 1
      if (!b || b === '其他') return -1
      return a.localeCompare(b, 'zh-Hans-CN')
    })
  )
})

// 左侧导航过滤（按关键字）
const filteredNavGroups = computed(() => {
  const kw = navKeyword.value.trim().toLowerCase()
  if (!kw) return pageNavGroups
  return pageNavGroups
    .map((g) => ({
      ...g,
      pages: g.pages.filter(
        (p) => p.label.toLowerCase().includes(kw) || p.page_key.toLowerCase().includes(kw),
      ),
    }))
    .filter((g) => g.pages.length > 0)
})

onMounted(load)
</script>

<template>
  <div class="perm-page">
    <div class="perm-head">
      <div>
        <div class="perm-title">页面查看权限管理</div>
        <div class="perm-subtitle">管控全部业务页面的可见范围；从左侧导航选择页面，或直接在表格里点编辑</div>
      </div>
      <div class="perm-actions">
        <el-button :icon="Refresh" circle title="刷新" @click="load" />
      </div>
    </div>

    <div class="perm-layout">
      <!-- ── 左侧导航 ── -->
      <aside class="perm-sidebar">
        <div class="sidebar-title">
          <span>页面导航</span>
          <span class="sidebar-count">{{ pages.length }}</span>
        </div>
        <el-input
          v-model="navKeyword"
          placeholder="搜索页面..."
          clearable
          size="small"
          class="sidebar-search"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <div class="nav-scroll">
          <div v-for="group in filteredNavGroups" :key="group.label" class="nav-group">
            <div class="nav-group-label">{{ group.label }}</div>
            <div
              v-for="p in group.pages"
              :key="p.page_key"
              class="nav-leaf"
              :class="{ 'is-active': editingPage?.page_key === p.page_key }"
              @click="openEditByKey(p.page_key)"
            >
              <span class="nav-leaf-label">{{ p.label }}</span>
            </div>
          </div>
          <div v-if="!filteredNavGroups.length" class="nav-empty">没有匹配的页面</div>
        </div>
      </aside>

      <!-- ── 主表格 ── -->
      <main class="perm-main">
        <el-card shadow="never" class="perm-card">
          <el-table :data="pages" border stripe class="perm-table" :header-row-class-name="'tbl-header'" v-loading="loading">
            <el-table-column type="index" label="#" width="60" align="center" />
            <el-table-column label="页面" min-width="200">
              <template #default="{ row }">
                <div class="page-cell">
                  <span class="page-name">{{ row.label }}</span>
                  <code class="page-key">{{ row.page_key }}</code>
                  <div v-if="row.subpages?.length" class="page-sub-badge">
                    <el-tag size="small" type="info" effect="plain" round>内容权限 {{ row.subpages.length }} 项</el-tag>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="当前授权范围" min-width="380">
              <template #default="{ row }">
                <div class="perm-chips">
                  <el-tag
                    v-for="r in dedupedChips(row.roles)"
                    :key="r"
                    size="small"
                    :type="r === ALL_ROLE ? 'success' : 'primary'"
                    effect="light"
                    round
                    class="perm-chip"
                  >
                    {{ roleLabelOf(r) }}
                  </el-tag>
                  <span v-if="!row.roles.length" class="perm-empty">未授权（空 = 任何角色/人员均不可见）</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openEdit(row as PagePerm)">编辑</el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="perm-save-row">
            <span class="perm-hint">
              共 {{ pages.length }} 个页面；点击任一页「编辑」，在抽屉里勾选后点「保存此页面」即立即生效。
            </span>
          </div>
        </el-card>
      </main>
    </div>

    <el-drawer
      v-model="drawerVisible"
      :title="editingPage ? `权限配置：${editingPage.label}` : '权限配置'"
      size="520px"
      :destroy-on-close="false"
      @closed="cancelEdit"
    >
      <div v-if="editingPage" class="editor">
        <div class="editor-section">
          <div class="editor-section-title">
            <span>基础设置</span>
            <code class="editor-page-key">{{ editingPage.page_key }}</code>
          </div>
          <div class="editor-item editor-item-all">
            <el-checkbox :model-value="isAllSelected" @change="onToggleAll">
              <span class="editor-item-main">所有人可见（<code>*</code>）</span>
              <span class="editor-item-sub">开启后所有角色与人员都能访问此页面</span>
            </el-checkbox>
          </div>
        </div>

        <el-divider />

        <div class="editor-section">
          <div class="editor-section-title"><span>按角色授权</span></div>
          <el-checkbox-group v-model="draftRoles" class="editor-list">
            <div v-for="r in allRoles" :key="r.role" class="editor-item">
              <el-checkbox :value="r.role" :label="r.role">{{ r.label }} <code class="editor-role-code">{{ r.role }}</code></el-checkbox>
            </div>
          </el-checkbox-group>
        </div>
        <div v-if="legacyGrants.length" class="editor-section">
          <div class="editor-section-title"><span>历史按姓名授权</span></div>
          <el-checkbox-group v-model="draftRoles" class="editor-list">
            <div v-for="value in legacyGrants" :key="value" class="editor-item">
              <el-checkbox :value="value" :label="value">{{ value }}（建议改为账号授权）</el-checkbox>
            </div>
          </el-checkbox-group>
        </div>

        <div v-for="(items, dept) in groupedUsers" :key="dept" class="editor-section">
          <div class="editor-section-title">
            <span>{{ dept }}</span>
            <span class="editor-section-count">{{ items.length }}</span>
          </div>
          <el-checkbox-group v-model="draftRoles" class="editor-list">
            <div v-for="u in items" :key="u.username" class="editor-item">
              <el-checkbox :value="u.username" :label="u.username">
                <span class="editor-item-main">
                  {{ u.real_name || u.username }}
                  <code class="editor-role-code">{{ u.emp_no || u.username }}</code>
                </span>
                <span v-if="u.job_title" class="editor-item-sub">· {{ u.job_title }}</span>
              </el-checkbox>
            </div>
          </el-checkbox-group>
        </div>

        <template v-if="editingPage.subpages && editingPage.subpages.length">
          <el-divider />
          <div class="editor-section">
            <div class="editor-section-title">
              <span>页面内容可见控制</span>
              <span class="editor-section-count">{{ editingPage.subpages.length }} 项</span>
            </div>
            <div class="sub-intro">页签级权限：对各页签单独控制可见范围，未授权的角色/人员看不到该页签。</div>
            <el-collapse v-model="openSubs" class="sub-collapse">
              <el-collapse-item v-for="sp in editingPage.subpages" :key="sp.sub_key" :name="sp.sub_key">
                <template #title>
                  <div class="sub-title">
                    <span class="sub-name">{{ sp.label }}</span>
                    <span class="sub-scope" :class="{ 'is-hidden': subScopeSummary(sp.sub_key, sp.roles).hidden }">
                      {{ subScopeSummary(sp.sub_key, sp.roles).text }}
                    </span>
                  </div>
                </template>
                <div class="sub-body">
                  <div class="editor-item editor-item-all">
                    <el-checkbox
                      :model-value="subIsAll(sp.sub_key)"
                      @change="(v: boolean | string | number) => onSubToggleAll(sp.sub_key, v)"
                    >
                      <span class="editor-item-main">所有人可见（<code>*</code>）</span>
                      <span class="editor-item-sub">开启后该页签对所有角色与人员显示</span>
                    </el-checkbox>
                  </div>
                  <el-divider />
                  <div class="editor-section">
                    <div class="editor-section-title"><span>按角色授权</span></div>
                    <el-checkbox-group v-model="subDrafts[sp.sub_key]" class="editor-list">
                      <div v-for="r in allRoles" :key="r.role" class="editor-item">
                        <el-checkbox :value="r.role" :label="r.role">{{ r.label }} <code class="editor-role-code">{{ r.role }}</code></el-checkbox>
                      </div>
                    </el-checkbox-group>
                  </div>
                  <div v-if="legacySubGrants(sp.sub_key).length" class="editor-section">
                    <div class="editor-section-title"><span>历史按姓名授权</span></div>
                    <el-checkbox-group v-model="subDrafts[sp.sub_key]" class="editor-list">
                      <div v-for="value in legacySubGrants(sp.sub_key)" :key="value" class="editor-item">
                        <el-checkbox :value="value" :label="value">{{ value }}（建议改为账号授权）</el-checkbox>
                      </div>
                    </el-checkbox-group>
                  </div>
                  <div v-if="!subDrafts[sp.sub_key]?.length" class="sub-empty-hint">
                    未授权任何角色/人员：该页签对所有人生效为「隐藏」。
                  </div>
                  <div v-for="(items, dept) in groupedUsers" :key="dept" class="editor-section">
                    <div class="editor-section-title">
                      <span>{{ dept }}</span>
                      <span class="editor-section-count">{{ items.length }}</span>
                    </div>
                    <el-checkbox-group v-model="subDrafts[sp.sub_key]" class="editor-list">
                      <div v-for="u in items" :key="u.username" class="editor-item">
                        <el-checkbox :value="u.username" :label="u.username">
                          <span class="editor-item-main">
                            {{ u.real_name || u.username }}
                            <code class="editor-role-code">{{ u.emp_no || u.username }}</code>
                          </span>
                          <span v-if="u.job_title" class="editor-item-sub">· {{ u.job_title }}</span>
                        </el-checkbox>
                      </div>
                    </el-checkbox-group>
                  </div>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>
        </template>
      </div>

      <template #footer>
        <el-button @click="cancelEdit">取消</el-button>
        <el-button type="primary" :icon="Check" @click="confirmEdit">保存此页面</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.perm-page {
  padding: 18px 22px 30px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* ── 顶部 ─────────────────────────── */
.perm-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.perm-title {
  font-size: 18px;
  font-weight: 800;
  color: light-dark(#0f172a, var(--text-primary));
}
.perm-subtitle {
  font-size: 13px;
  color: light-dark(#94a3b8, var(--text-secondary));
  margin-top: 4px;
}
.perm-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ── 说明卡 ───────────────────────── */
.perm-notice {
  border-radius: 12px;
  background: linear-gradient(180deg, #f0fdfa 0%, #ecfeff 100%);
  border: 1px solid rgba(15, 118, 110, 0.18);
  padding: 14px 20px;
  font-size: 13px;
  color: light-dark(#475569, var(--text-secondary));
  line-height: 1.7;
}
.perm-notice p { margin: 2px 0; }
.perm-notice b { color: light-dark(#0f766e, var(--text-accent)); font-weight: 700; }

/* ── 左右布局 ─────────────────────── */
.perm-layout {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}
.perm-main { flex: 1; min-width: 0; }

/* ── 左侧导航 ─────────────────────── */
.perm-sidebar {
  width: 240px;
  flex-shrink: 0;
  background: light-dark(#ffffff, var(--app-surface));
  border: 1px solid light-dark(#e2e8f0, var(--border-color));
  border-radius: 10px;
  padding: 12px;
  position: sticky;
  top: 0;
  max-height: calc(100vh - 160px);
  display: flex;
  flex-direction: column;
}
.sidebar-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 700;
  color: light-dark(#334155, var(--text-primary));
  margin-bottom: 8px;
  padding: 0 2px;
}
.sidebar-count {
  font-size: 11px;
  font-weight: 700;
  color: light-dark(#0f766e, var(--text-accent));
  background: rgba(15, 118, 110, 0.1);
  padding: 1px 8px;
  border-radius: 10px;
}
.sidebar-search {
  margin-bottom: 10px;
}
.sidebar-search :deep(.el-input__wrapper) {
  border-radius: 6px;
  background: light-dark(#f8fafc, var(--app-surface-2));
  box-shadow: 0 0 0 1px #e2e8f0 inset;
}
.sidebar-search :deep(.el-input__wrapper):hover,
.sidebar-search :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px #0f766e inset;
}
.nav-scroll {
  flex: 1;
  overflow-y: auto;
  margin-right: -4px;
  padding-right: 4px;
}
.nav-scroll::-webkit-scrollbar { width: 6px; }
.nav-scroll::-webkit-scrollbar-thumb { background: light-dark(#cbd5e1, rgba(96, 165, 250, .12)); border-radius: 3px; }

.nav-group { margin-bottom: 10px; }
.nav-group-label {
  font-size: 11px;
  font-weight: 700;
  color: light-dark(#94a3b8, var(--text-secondary));
  letter-spacing: 0.06em;
  padding: 4px 8px;
  text-transform: uppercase;
}
.nav-leaf {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background .12s ease, color .12s ease;
  color: light-dark(#475569, var(--text-secondary));
  font-size: 13px;
}
.nav-leaf:hover {
  background: light-dark(#f1f5f9, var(--app-surface-2));
  color: light-dark(#0f172a, var(--text-primary));
}
.nav-leaf.is-active {
  background: linear-gradient(180deg, #ecfdf5 0%, #f0fdfa 100%);
  color: light-dark(#0f766e, var(--text-accent));
  font-weight: 600;
}
.nav-leaf.is-active .nav-leaf-key {
  background: rgba(15, 118, 110, 0.15);
  color: light-dark(#0f766e, var(--text-accent));
}
.nav-leaf-label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.nav-leaf-key {
  font-size: 10px;
  background: light-dark(#f1f5f9, var(--app-surface-2));
  color: light-dark(#94a3b8, var(--text-secondary));
  padding: 0 4px;
  border-radius: 3px;
  font-family: ui-monospace, "JetBdemo_rain Mono", Menlo, Consolas, monospace;
  white-space: nowrap;
}
.nav-empty {
  font-size: 12px;
  color: light-dark(#94a3b8, var(--text-secondary));
  padding: 8px;
  text-align: center;
}

/* ── 主表格 ───────────────────────── */
.perm-card {
  border-radius: 12px;
  border: 1px solid light-dark(#e2e8f0, var(--border-color));
}
.perm-table {
  --el-table-border-color: light-dark(#eef2f7, var(--border-color));
  border-radius: 8px;
  overflow: hidden;
}
.perm-table :deep(.el-table__cell) { padding: 12px 0; }
.perm-table :deep(.el-table__row) { transition: background-color .15s ease; }
.perm-table :deep(.el-table__row--striped td.el-table__cell) { background: light-dark(#fafbfc, var(--app-surface-2)); }
.perm-table :deep(.el-table__row:hover > td.el-table__cell) { background: rgba(15, 118, 110, 0.06) !important; }
.perm-table :deep(.tbl-header th.el-table__cell) {
  background: light-dark(#f8fafc, var(--app-surface-2)) !important;
  color: light-dark(#475569, var(--text-secondary)); font-weight: 600; font-size: 13px;
  border-bottom: 1px solid light-dark(#e2e8f0, var(--border-color));
}

.page-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.page-name {
  font-weight: 700;
  color: light-dark(#0f172a, var(--text-primary));
  font-size: 14px;
}
.page-key {
  font-size: 11px;
  color: light-dark(#94a3b8, var(--text-secondary));
  background: light-dark(#f1f5f9, var(--app-surface-2));
  padding: 1px 6px;
  border-radius: 3px;
  font-family: ui-monospace, "JetBdemo_rain Mono", Menlo, Consolas, monospace;
  align-self: flex-start;
}

.perm-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  min-height: 24px;
}
.perm-chip { border-radius: 999px; }
.perm-empty {
  color: light-dark(#94a3b8, var(--text-secondary));
  font-size: 12px;
  font-style: italic;
}

.perm-save-row {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px dashed light-dark(#eef1f5, var(--border-color));
  display: flex;
  align-items: center;
}
.perm-hint {
  font-size: 12px;
  color: light-dark(#94a3b8, var(--text-secondary));
}

/* ── 抽屉编辑器 ────────────────────── */
.editor {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.editor-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.editor-section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 700;
  color: light-dark(#334155, var(--text-primary));
  letter-spacing: 0.02em;
}
.editor-section-count {
  font-size: 11px;
  font-weight: 600;
  color: light-dark(#94a3b8, var(--text-secondary));
  background: light-dark(#f1f5f9, var(--app-surface-2));
  padding: 1px 8px;
  border-radius: 10px;
}
.editor-page-key {
  font-size: 11px;
  color: light-dark(#94a3b8, var(--text-secondary));
  background: light-dark(#f1f5f9, var(--app-surface-2));
  padding: 1px 6px;
  border-radius: 3px;
  font-family: ui-monospace, "JetBdemo_rain Mono", Menlo, Consolas, monospace;
  font-weight: 400;
}
.editor-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.editor-item {
  padding: 8px 12px;
  border: 1px solid light-dark(#eef1f5, var(--border-color));
  border-radius: 6px;
  background: light-dark(#f8fafc, var(--app-surface-2));
  transition: background .15s, border-color .15s;
}
.editor-item:hover {
  background: light-dark(#f1f5f9, var(--app-surface-2));
  border-color: light-dark(#cbd5e1, var(--border-color));
}
.editor-item.is-locked {
  background: light-dark(#f1f5f9, var(--app-surface-2));
  opacity: 0.9;
}
.editor-item-all {
  background: linear-gradient(180deg, #ecfdf5 0%, #f0fdfa 100%);
  border-color: rgba(15, 118, 110, 0.25);
}
.editor-item-all:hover {
  background: linear-gradient(180deg, #d1fae5 0%, #ccfbf1 100%);
}
.editor-item-main {
  font-weight: 600;
  color: light-dark(#0f172a, var(--text-primary));
}
.editor-item-main code,
.editor-role-code {
  font-size: 11px;
  color: light-dark(#64748b, var(--text-secondary));
  background: light-dark(#e2e8f0, rgba(96, 165, 250, .12));
  padding: 1px 6px;
  border-radius: 3px;
  margin-left: 4px;
  font-family: ui-monospace, "JetBdemo_rain Mono", Menlo, Consolas, monospace;
  font-weight: 400;
}
.editor-item-sub {
  margin-left: 6px;
  color: light-dark(#94a3b8, var(--text-secondary));
  font-size: 12px;
}
.role-lock {
  margin-left: 6px;
  color: light-dark(#94a3b8, var(--text-secondary));
  vertical-align: -2px;
}

/* ── 页签级（页面内容）权限 ─────────────────────── */
.page-sub-badge {
  margin-top: 4px;
}
.sub-intro {
  font-size: 12px;
  color: light-dark(#64748b, var(--text-secondary));
  background: light-dark(#f8fafc, var(--app-surface-2));
  border: 1px dashed light-dark(#e2e8f0, var(--border-color));
  border-radius: 6px;
  padding: 6px 10px;
  margin-bottom: 10px;
  line-height: 1.6;
}
.sub-collapse {
  border-radius: 8px;
  overflow: hidden;
}
.sub-collapse :deep(.el-collapse-item__header) {
  height: auto;
  line-height: 1.4;
  padding: 10px 12px;
  font-weight: 600;
  color: light-dark(#334155, var(--text-primary));
  background: light-dark(#fbfcfe, var(--app-surface-2));
}
.sub-collapse :deep(.el-collapse-item__content) {
  padding: 12px 14px;
}
.sub-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}
.sub-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sub-scope {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  color: light-dark(#0f766e, var(--text-accent));
  background: rgba(15, 118, 110, 0.1);
  border-radius: 999px;
  padding: 1px 8px;
}
.sub-scope.is-hidden {
  color: light-dark(#b45309, #fbbf24);
  background: rgba(245, 158, 11, 0.12);
}
.sub-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sub-body :deep(.el-divider) {
  margin: 8px 0;
}
.sub-empty-hint {
  font-size: 12px;
  color: light-dark(#b45309, #fbbf24);
  background: rgba(245, 158, 11, 0.08);
  border: 1px dashed rgba(245, 158, 11, 0.35);
  border-radius: 6px;
  padding: 6px 10px;
  margin-bottom: 4px;
}
</style>
