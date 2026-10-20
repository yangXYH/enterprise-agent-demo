<script setup lang="ts">
import { computed, reactive, ref, onMounted, watch } from 'vue'
import {
  ElAside,
  ElConfigProvider,
  ElContainer,
  ElIcon,
  ElMain,
  ElMenu,
  ElMenuItem,
  ElSubMenu,
  ElMessage,
} from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import {
  Close,
  Expand,
  Fold,
  Grid,
  Moon,
  Sunny,
  SwitchButton,
} from '@element-plus/icons-vue'
import ResumeFilter from './components/ResumeFilter.vue'
import AfterSalesQualityDashboard from './components/AfterSalesQualityDashboard.vue'
import AiProjectBoard from './components/AiProjectBoard.vue'
import AiPromptReference from './components/AiPromptReference.vue'
import EcommerceDashboard from './components/EcommerceDashboard.vue'
import CustomerService from './components/CustomerService.vue'
import ProductQualityReports from './components/ProductQualityReports.vue'
import InventoryDecision from './components/InventoryDecision.vue'
import OperatingAnalysis from './components/OperatingAnalysis.vue'
import ExecutiveBoard from './components/ExecutiveBoard.vue'
import DesignBoard from './components/DesignBoard.vue'
import OperatingChat from './components/OperatingChat.vue'
import SkuReturnData from './components/SkuReturnData.vue'
import InventoryMonitor from './components/InventoryMonitor.vue'
import InventoryMonitorMetric from './components/InventoryMonitorMetric.vue'
import InventoryProductDashboard from './components/InventoryProductDashboard.vue'
import JushuitanDashboard from './components/JushuitanDashboard.vue'
import PurchaseOrderDashboard from './components/PurchaseOrderDashboard.vue'
import SalesDashboard from './components/SalesDashboard.vue'
import KnowledgeAssistantView from './components/KnowledgeAssistantView.vue'
import HrDriver from './components/hr/HrDriver.vue'
import HrRoster from './components/hr/HrRoster.vue'
import HrRecruit from './components/hr/HrRecruit.vue'
import HrPermissionManage from './components/hr/HrPermissionManage.vue'
import AdminUserManage from './components/admin/AdminUserManage.vue'
import PointsSystem from './components/PointsSystem.vue'
import ShopReport from './components/ShopReport.vue'
import ShopReportChat from './components/ShopReportChat.vue'

// ── Auth ─────────────────────────────────────────────────────────────────────
const AUTH_REAL_NAME_KEY   = 'auth_real_name'
const AUTH_ROLE_KEY        = 'auth_role'
const AUTH_USERNAME_KEY    = 'auth_username'
const AUTH_JOB_TITLE_KEY   = 'auth_job_title'
const AUTH_DEPARTMENT_KEY  = 'auth_department'
const AUTH_DEPT_CODE_KEY   = 'auth_dept_code'
const AUTH_LOGIN_TIME_KEY  = 'auth_login_time'
const SEVEN_DAYS_MS        = 7 * 24 * 60 * 60 * 1000

const authRealName  = ref('')
const authRole      = ref('')
const authUsername  = ref('')
const authJobTitle  = ref('')
const authDepartment = ref('')
const authDeptCode  = ref('')
const authChecked   = ref(false)
const isDarkTheme = ref(document.documentElement.classList.contains('dark-theme'))

const toggleTheme = () => {
  isDarkTheme.value = !isDarkTheme.value
  document.documentElement.classList.toggle('dark-theme', isDarkTheme.value)
  document.documentElement.classList.toggle('dark', isDarkTheme.value)
  try { localStorage.setItem('user_theme', isDarkTheme.value ? 'dark' : 'light') } catch {}
}

const redirectToLogin = () => {
  window.location.replace('/login.html')
}

const hasAuthState = () => Boolean(authRealName.value && authRole.value)

onMounted(() => {
  authRealName.value   = localStorage.getItem(AUTH_REAL_NAME_KEY)  || ''
  authRole.value       = localStorage.getItem(AUTH_ROLE_KEY)        || ''
  authUsername.value   = localStorage.getItem(AUTH_USERNAME_KEY)    || ''
  authJobTitle.value   = localStorage.getItem(AUTH_JOB_TITLE_KEY)   || ''
  authDepartment.value = localStorage.getItem(AUTH_DEPARTMENT_KEY)  || ''
  authDeptCode.value   = localStorage.getItem(AUTH_DEPT_CODE_KEY)   || ''

  if (!authRealName.value || !authRole.value) {
    clearAuthCache()
    redirectToLogin()
    return
  }

  // 【防御补丁】7 天登录超时校验
  const loginTime = parseInt(localStorage.getItem(AUTH_LOGIN_TIME_KEY) || '0', 10)
  if (loginTime > 0 && Date.now() - loginTime > SEVEN_DAYS_MS) {
    // 清除所有登录缓存，强制回到登录页
    clearAuthCache()
    authRealName.value   = ''
    authRole.value       = ''
    authUsername.value   = ''
    authJobTitle.value   = ''
    authDepartment.value = ''
    authDeptCode.value   = ''
    ElMessage.error('您的登录已过期，请重新登录')
    redirectToLogin()
    return
  }

  hydrateSidebarState()
  authChecked.value = true
  void loadPagePermission()
})

const loadPagePermission = async () => {
  try {
    const response = await fetch('/api/hr/permission/my', { credentials: 'same-origin', cache: 'no-store' })
    if (response.status === 401) {
      clearAuthCache()
      redirectToLogin()
      return
    }
    if (!response.ok) return
    pagePermission.value = await response.json()
    normalizeActiveMenu()
    hydrateWorkspaceTabs()
    if (canAccess('shop-report')) void loadShopReport()
  } catch {
    // 后端不可用时不阻塞页面
  }
}

const isAuthenticated = computed(hasAuthState)

// ── Menu permission ──────────────────────────────────────────────────────────
// 侧边栏仅保留「电商中台看板」。客服中心、人力行政、业务运营、项目看板等
// 功能均已并入电商中台看板（电商中台内点击通过 postMessage 跳回本壳渲染），
// 登录用户均可访问。

// ── Menu state ──────────────────────────────────────────────────────────────
const _SAVED_MENU_KEY = 'boss_active_menu_v3'
const _OPENED_TABS_KEY = 'boss_opened_workspace_tabs_v1'
const _SIDEBAR_COLLAPSED_KEY = 'boss_sidebar_collapsed_v1'
const _OPENED_NAV_GROUPS_KEY = 'boss_opened_nav_groups_v1'
const DEFAULT_APP_MENU = 'ecommerce-dashboard'
type InventoryMetricKey = 'stockout' | 'shortage' | 'listed' | 'delisted'
type InventoryMetricFilters = {
  snapshot_date: string[]
  keyword: string
  brand: string[]
  category_l1: string[]
  shop_name: string[]
  product_status: string[]
}
const INVENTORY_METRIC_ROUTE_BY_METRIC: Record<InventoryMetricKey, string> = {
  stockout: 'inventory-stockout',
  shortage: 'inventory-shortage',
  listed: 'inventory-listed',
  delisted: 'inventory-delisted',
}
const INVENTORY_METRIC_BY_ROUTE: Record<string, InventoryMetricKey> = {
  'inventory-stockout': 'stockout',
  'inventory-shortage': 'shortage',
  'inventory-listed': 'listed',
  'inventory-delisted': 'delisted',
}
const emptyInventoryMetricFilters = (): InventoryMetricFilters => ({
  snapshot_date: [],
  keyword: '',
  brand: [],
  category_l1: [],
  shop_name: [],
  product_status: ['上柜'],
})
const _VALID_MENUS = new Set([
  'insight', 'insight-trend', 'insight-category', 'insight-brand',
  'shop-report', 'shop-report-chat',
  'design-overview', 'design-models', 'design-prompts', 'design-comparisons', 'design-styles', 'design-trash',
  'operating-analysis',
  'operating-chat',
  'sku-return-data',
  'sys-permissions',
  'sys-users',
  'hr-filter',
  'hr-driver', 'hr-roster', 'hr-recruit',
  'points', 'points-rule', 'points-log',
  'cs-audit', 'after-sales-quality', 'product-quality-reports',
  'inventory-decision',
  'inventory-monitor',
  'inventory-stockout',
  'inventory-shortage',
  'inventory-listed',
  'inventory-delisted',
  'inventory-product-dashboard',
  'jushuitan-dashboard',
  'purchase-order-dashboard',
  'sales-dashboard',
  'ai-project-board',
  'ai-prompt-reference',
  'ecommerce-dashboard',
  'ai-knowledge-qa',
])

const MENU_VIEW_LABELS: Record<string, string> = {
  'insight': '经营总览',
  'insight-trend': '趋势分析',
  'insight-category': '品类分析',
  'insight-brand': '品牌与商品',
  'shop-report': '店铺报表',
  'shop-report-chat': '店铺报表 AI 问答',
  'design-overview': '设计资料总览',
  'design-models': 'AI模特与场景案例',
  'design-prompts': 'AI生图提示词库',
  'design-comparisons': '生图前后对照',
  'design-styles': '视觉要素手册',
  'design-trash': '设计资料回收站',
  'operating-analysis': '经营数据分析',
  'operating-chat': 'AI 经营问答',
  'sku-return-data': 'SKU 退货数据',
  'sys-permissions': '权限管理',
  'sys-users': '账号管理',
  'ai-project-board': 'AI 项目进度看板',
  'ai-prompt-reference': 'AI 提示词参考',
  'ecommerce-dashboard': '电商中台看板',
  'ai-knowledge-qa': 'AI 知识问答',
  'inventory-decision': '库存分析决策',
  'inventory-monitor': '库存看板监控',
  'inventory-stockout': '库存断货数据',
  'inventory-shortage': '库存缺货数据',
  'inventory-listed': '库存上柜数据',
  'inventory-delisted': '库存下柜数据',
  'inventory-product-dashboard': '进销商品看板',
  'jushuitan-dashboard': '商品库存看板',
  'purchase-order-dashboard': '采购单看板',
  'sales-dashboard': '销售数据看板',
  'cs-audit': '客服数据看板',
  'after-sales-quality': '售后质量分析',
  'product-quality-reports': '产品质检报告',
  'hr-filter': 'AI 智能简历筛选',
  'hr-driver': '人事驾驶舱',
  'hr-roster': '人员花名册',
  'hr-recruit': '招聘管理',
  'points': '积分排行榜',
  'points-rule': '积分规则',
  'points-log': '积分明细',
}

const _savedMenu = (() => {
  try {
    const raw = sessionStorage.getItem(_SAVED_MENU_KEY)
    if (raw && _VALID_MENUS.has(raw)) return raw
  } catch {}
  return DEFAULT_APP_MENU
})()

const activeMenu = ref(_savedMenu)
const openedWorkspaceTabs = ref<string[]>([])
const isSidebarCollapsed = ref(false)
const inventoryMetricInitialFilters = ref<InventoryMetricFilters>(emptyInventoryMetricFilters())
const isInventoryMetricMenu = computed(() => Boolean(INVENTORY_METRIC_BY_ROUTE[activeMenu.value]))
const activeInventoryMetric = computed<InventoryMetricKey>(() => INVENTORY_METRIC_BY_ROUTE[activeMenu.value] || 'stockout')

const _syncMenu = (key: string) => {
  activeMenu.value = key
  try { sessionStorage.setItem(_SAVED_MENU_KEY, key) } catch {}
  ensureWorkspaceTab(key)
}

const goKnowledgeQA = () => {
  if (_VALID_MENUS.has('ai-knowledge-qa')) {
    _syncMenu('ai-knowledge-qa')
  }
}

// 电商中台 iframe 内点击外部模块（项目看板/库存/简历）时，跳回主壳渲染对应页面
const openExternalMenu = (key: string) => {
  if (_VALID_MENUS.has(key) && canAccess(key)) {
    if (INVENTORY_METRIC_BY_ROUTE[key]) {
      inventoryMetricInitialFilters.value = emptyInventoryMetricFilters()
    }
    _syncMenu(key)
  }
}

const openInventoryMetric = (payload: { metric?: InventoryMetricKey; filters?: InventoryMetricFilters }) => {
  const metric = payload?.metric
  const route = metric ? INVENTORY_METRIC_ROUTE_BY_METRIC[metric] : ''
  if (!route || !_VALID_MENUS.has(route) || !canAccess(route)) return
  inventoryMetricInitialFilters.value = payload.filters
    ? {
        snapshot_date: [...payload.filters.snapshot_date],
        keyword: payload.filters.keyword,
        brand: [...payload.filters.brand],
        category_l1: [...payload.filters.category_l1],
        shop_name: [...payload.filters.shop_name],
        product_status: [...payload.filters.product_status],
      }
    : emptyInventoryMetricFilters()
  _syncMenu(route)
}

const backToInventoryMonitor = () => openExternalMenu('inventory-monitor')

const hydrateSidebarState = () => {
  try {
    isSidebarCollapsed.value = sessionStorage.getItem(_SIDEBAR_COLLAPSED_KEY) === 'true'
  } catch {
    isSidebarCollapsed.value = false
  }
}

const toggleSidebarCollapsed = () => {
  isSidebarCollapsed.value = !isSidebarCollapsed.value
  try { sessionStorage.setItem(_SIDEBAR_COLLAPSED_KEY, String(isSidebarCollapsed.value)) } catch {}
}

// ── Guard: 页面查看权限（权限管理后台可配置，覆盖全部业务页面） ───────────
// - 权限管理（sys-permissions）：仅 admin / 管理员；
// - 其余受控页面：权限表（sys_page_permission）控制，默认 HR 页仅 admin / hr，
//   其他业务模块默认全员可见，管理员可在「系统管理-权限管理」调整。
const PERM_PAGE_KEYS = new Set([
  'ecommerce-dashboard', 'insight', 'insight-trend', 'insight-category', 'insight-brand',
  'shop-report', 'shop-report-chat',
  'design-overview', 'design-models', 'design-prompts', 'design-comparisons', 'design-styles',
  'operating-analysis',
  'operating-chat',
  'sku-return-data',
  'hr-driver', 'hr-roster', 'hr-recruit', 'hr-filter',
  'ai-project-board', 'inventory-decision', 'inventory-monitor', 'inventory-stockout', 'inventory-shortage', 'inventory-listed', 'inventory-delisted', 'inventory-product-dashboard', 'jushuitan-dashboard', 'purchase-order-dashboard', 'sales-dashboard', 'cs-audit', 'after-sales-quality', 'product-quality-reports', 'points', 'points-rule', 'points-log',
  'knowledge-qa',
])

// 菜单路由与 activeMenu 不一致时归一到权限表 key（AI 知识问答：knowledge-qa）
const permKeyOf = (key: string) => {
  if (key === 'home') return 'ecommerce-dashboard'
  if (key === 'ai-prompt-reference') return 'ai-project-board'
  // 具体店铺（shop-report:{channel}:{shop_id}）按独立 page_key 授权，不再归一到总开关
  // 店铺报表 AI 问答不单独授权，跟随店铺报表页面权限（单一控制点）
  if (key === 'shop-report-chat') return 'shop-report'
  return key === 'ai-knowledge-qa' ? 'knowledge-qa' : key
}

const pagePermission = ref<{ role: string; is_admin: boolean; can_delete_design?: boolean; allowed: string[] } | null>(null)
const canManageDesignTrash = computed(() => pagePermission.value?.role?.trim().toLowerCase() === 'admin')
const canDeleteDesign = computed(() => canManageDesignTrash.value || pagePermission.value?.can_delete_design === true)

const canAccess = (key: string): boolean => {
  if (key === 'design-trash') return canManageDesignTrash.value
  if (key === 'sys-permissions' || key === 'sys-users') {
    return pagePermission.value?.is_admin === true
  }
  const permKey = permKeyOf(key)
  // 静态受控页面 + 动态店铺报表（shop-report:{channel}:{shop_id}）都走权限表
  const controlled = PERM_PAGE_KEYS.has(permKey) || permKey.startsWith('shop-report:')
  if (controlled) {
    const perm = pagePermission.value
    if (!perm) return false
    return perm.allowed.includes(permKey)
  }
  return true
}

// 过滤出当前用户可见的子项；无可视子项的分组整个隐藏（如非 admin 看不到「系统管理」）
const visibleChildren = (group: EcomNavGroup): EcomNavChild[] =>
  group.children.filter((c) => canAccess(c.route))

// 权限配置加载完成后：把已打开却无权的页面收走，切回人事驾驶舱
watch(pagePermission, (perm) => {
  if (!perm) return
  if (!canAccess(activeMenu.value)) {
    _syncMenu(getDefaultAccessibleMenu())
  }
  openedWorkspaceTabs.value = openedWorkspaceTabs.value.filter((k) => canAccess(k))
  persistWorkspaceTabs()
})

const sanitizeWorkspaceTabs = (tabs: unknown[]): string[] => {
  const seen = new Set<string>()
  const sanitized: string[] = []

  for (const tab of tabs) {
    if (typeof tab !== 'string') continue
    if (!_VALID_MENUS.has(tab) || !canAccess(tab) || seen.has(tab)) continue
    seen.add(tab)
    sanitized.push(tab)
  }

  return sanitized
}

const persistWorkspaceTabs = () => {
  try {
    sessionStorage.setItem(_OPENED_TABS_KEY, JSON.stringify(openedWorkspaceTabs.value))
  } catch {}
}

const hydrateWorkspaceTabs = () => {
  let savedTabs: unknown[] = []
  try {
    const raw = sessionStorage.getItem(_OPENED_TABS_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) savedTabs = parsed
    }
  } catch {}

  openedWorkspaceTabs.value = sanitizeWorkspaceTabs([activeMenu.value, ...savedTabs])
  if (!openedWorkspaceTabs.value.length && canAccess(activeMenu.value)) {
    openedWorkspaceTabs.value = [activeMenu.value]
  }
  persistWorkspaceTabs()
}

const ensureWorkspaceTab = (key: string) => {
  if (!_VALID_MENUS.has(key) || !canAccess(key)) return
  if (openedWorkspaceTabs.value.includes(key)) return
  openedWorkspaceTabs.value = [...openedWorkspaceTabs.value, key]
  persistWorkspaceTabs()
}

const workspaceTabs = computed(() => (
  openedWorkspaceTabs.value
    .filter((key) => _VALID_MENUS.has(key) && canAccess(key))
    .map((key) => ({ key, label: MENU_VIEW_LABELS[key] ?? key }))
))

const switchWorkspaceTab = (key: string) => {
  if (!canAccess(key)) return
  _syncMenu(key)
}

const closeWorkspaceTab = (key: string) => {
  if (openedWorkspaceTabs.value.length <= 1) return

  const nextTabs = openedWorkspaceTabs.value.filter((tab) => tab !== key)
  openedWorkspaceTabs.value = nextTabs
  persistWorkspaceTabs()

  if (activeMenu.value === key) {
    _syncMenu(nextTabs[nextTabs.length - 1] || getDefaultAccessibleMenu())
  }
}

const getDefaultAccessibleMenu = (): string => {
  // 全部功能已并入电商中台看板，所有兜底一律回到电商中台
  if (canAccess(DEFAULT_APP_MENU)) return DEFAULT_APP_MENU
  return Array.from(_VALID_MENUS).find((key) => canAccess(key)) || DEFAULT_APP_MENU
}

const normalizeActiveMenu = () => {
  const forcedMenu = new URLSearchParams(window.location.search).get('menu')
  if (forcedMenu && _VALID_MENUS.has(forcedMenu) && canAccess(forcedMenu)) {
    _syncMenu(forcedMenu)
    return
  }
  if (canAccess(activeMenu.value)) return
  _syncMenu(getDefaultAccessibleMenu())
}

// ── 电商中台嵌入协作 ─────────────────────────────────────────────────────────
// 主壳侧边栏直接呈现电商中台菜单树；点击子项时：
//  - 外部模块（简历/库存/项目看板/客服）→ 在主壳打开对应页面
//  - 电商中台内部路由 → 切回 iframe 并通知它切换到对应页面
const EXTERNAL_ECOM_KEYS = new Set([
  'insight', 'insight-trend', 'insight-category', 'insight-brand',
  'shop-report', 'shop-report-chat',
  'design-overview', 'design-models', 'design-prompts', 'design-comparisons', 'design-styles', 'design-trash',
  'operating-analysis',
  'operating-chat',
  'sku-return-data',
  'sys-permissions',
  'sys-users',
  'ai-project-board', 'ai-prompt-reference', 'inventory-decision', 'inventory-monitor', 'inventory-stockout', 'inventory-shortage', 'inventory-listed', 'inventory-delisted', 'inventory-product-dashboard', 'jushuitan-dashboard', 'purchase-order-dashboard', 'sales-dashboard', 'hr-filter',
  'cs-audit', 'after-sales-quality', 'product-quality-reports',
  'hr-driver', 'hr-roster', 'hr-recruit',
  'points', 'points-rule', 'points-log',
])

// 电商中台内尚未接真实数据的 mock 演示页面（淡色提示"待开发"）
const TEST_ECOM_ROUTES = new Set([
  'support', 'support-scripts', 'support-rating',
  'operation', 'operation-content', 'operation-user',
  'warehouse', 'warehouse-flow', 'warehouse-stock',
  'anchor', 'anchor-live', 'anchor-commission',
  'finance', 'finance-expense', 'finance-invoice',
])

const isEcomDevRoute = (route: string) => TEST_ECOM_ROUTES.has(route)

// ── 侧边栏导航（写死在前端，随 git 同步；不再依赖数据库 ecom_menu） ──────
interface EcomNavChild { label: string; route: string; kind?: string }
interface EcomNavGroup { label: string; icon: string; route: string; children: EcomNavChild[] }

type ShopReportShop = { channel: string; shop_id: string; shop_name: string; months: string[] }
type ShopReportPayload = { source?: Record<string, any>; months: string[]; shops: ShopReportShop[]; rows: any[] }
const shopReportData = ref<ShopReportPayload | null>(null)
const shopReportError = ref('')
const selectedReportShop = ref('')
const reportNavRoute = (shop: ShopReportShop) => `shop-report:${shop.channel}:${shop.shop_id}`
const shopKey = (shop: ShopReportShop) => `${shop.channel}:${shop.shop_id}`

const ECOM_NAV = reactive<EcomNavGroup[]>([
  { label: '公司首页', icon: 'home', route: 'home', children: [
    { label: '经营看板首页', route: 'home' },
    { label: 'AI 知识问答', route: 'knowledge-qa', kind: 'external' },
    { label: 'AI 项目进度看板', route: 'ai-project-board', kind: 'external' },
    { label: 'AI 提示词参考', route: 'ai-prompt-reference', kind: 'external' },
  ]},
  { label: '数据洞察', icon: 'bar-chart', route: '', children: [
    { label: '经营总览', route: 'insight', kind: 'external' },
    { label: '趋势分析', route: 'insight-trend', kind: 'external' },
    { label: '品类分析', route: 'insight-category', kind: 'external' },
    { label: '品牌与商品', route: 'insight-brand', kind: 'external' },
  ]},
  { label: '店铺报表', icon: 'shop', route: '', children: [
    { label: '查看店铺报表', route: 'shop-report', kind: 'external' },
    { label: '店铺报表 AI 问答', route: 'shop-report-chat', kind: 'external' },
  ]},
  { label: '设计部', icon: 'palette', route: '', children: [
    { label: '设计资料总览', route: 'design-overview', kind: 'external' },
    { label: 'AI模特与场景案例', route: 'design-models', kind: 'external' },
    { label: 'AI生图提示词库', route: 'design-prompts', kind: 'external' },
    { label: '生图前后对照', route: 'design-comparisons', kind: 'external' },
    { label: '视觉要素手册', route: 'design-styles', kind: 'external' },
    { label: '回收站', route: 'design-trash', kind: 'external' },
  ]},
  { label: '客服部', icon: 'headset', route: '', children: [
    { label: '客服数据看板', route: 'cs-audit', kind: 'external' },
    { label: '售后质量分析', route: 'after-sales-quality', kind: 'external' },
    { label: '产品质检报告', route: 'product-quality-reports', kind: 'external' },
  ]},
  { label: '运营部', icon: 'megaphone', route: '', children: [
    { label: '经营数据分析', route: 'operating-analysis', kind: 'external' },
    { label: 'AI 经营问答', route: 'operating-chat', kind: 'external' },
    { label: 'SKU 退货数据', route: 'sku-return-data', kind: 'external' },
    { label: '库存分析决策', route: 'inventory-decision', kind: 'external' },
    { label: '库存看板监控', route: 'inventory-monitor', kind: 'external' },
    { label: '库存断货数据', route: 'inventory-stockout', kind: 'external' },
    { label: '库存缺货数据', route: 'inventory-shortage', kind: 'external' },
    { label: '库存上柜数据', route: 'inventory-listed', kind: 'external' },
    { label: '库存下柜数据', route: 'inventory-delisted', kind: 'external' },
  ]},
  { label: '供应链部', icon: 'supply', route: '', children: [
    { label: '商品库存看板', route: 'jushuitan-dashboard', kind: 'external' },
    { label: '销售数据看板', route: 'sales-dashboard', kind: 'external' },
    { label: '进销商品看板', route: 'inventory-product-dashboard', kind: 'external' },
    { label: '采购单看板', route: 'purchase-order-dashboard', kind: 'external' },
  ]},
  // 仓库部 / 主播 / 财务 板块暂未启用，先隐藏
  // { label: '仓库部', icon: 'warehouse', route: '', children: [
  //   { label: '库存管理', route: 'warehouse' },
  //   { label: '出入库记录', route: 'warehouse-flow' },
  //   { label: '盘点管理', route: 'warehouse-stock' },
  // ]},
  // { label: '主播', icon: 'video', route: '', children: [
  //   { label: '主播排期', route: 'anchor' },
  //   { label: '直播数据', route: 'anchor-live' },
  //   { label: '佣金结算', route: 'anchor-commission' },
  // ]},
  // { label: '财务', icon: 'wallet', route: '', children: [
  //   { label: '销售对账', route: 'finance' },
  //   { label: '费用报销', route: 'finance-expense' },
  //   { label: '发票管理', route: 'finance-invoice' },
  // ]},
  { label: '人力资源', icon: 'users', route: '', children: [
    { label: '人事驾驶舱', route: 'hr-driver', kind: 'external' },
    { label: '人员花名册', route: 'hr-roster', kind: 'external' },
    { label: '招聘管理', route: 'hr-recruit', kind: 'external' },
    { label: 'AI 智能简历筛选', route: 'hr-filter', kind: 'external' },
  ]},
  { label: '系统管理', icon: 'setting', route: '', children: [
    { label: '权限管理', route: 'sys-permissions', kind: 'external' },
    { label: '账号管理', route: 'sys-users', kind: 'external' },
  ]},
  { label: '积分系统', icon: 'star', route: '', children: [
    { label: '积分排行榜', route: 'points', kind: 'external' },
    { label: '积分规则', route: 'points-rule', kind: 'external' },
    { label: '积分明细', route: 'points-log', kind: 'external' },
  ]},
])

const loadShopReport = async () => {
  try {
    const response = await fetch('/api/shop-report', { credentials: 'same-origin', cache: 'no-store' })
    const result = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(result.detail || `店铺报表读取失败（${response.status}）`)
    if (!Array.isArray(result.shops) || !Array.isArray(result.rows)) throw new Error('店铺报表数据格式不正确')
    shopReportData.value = result as ShopReportPayload
    shopReportError.value = ''
    const group = ECOM_NAV.find((item) => item.label === '店铺报表')
    if (group) {
      const fixed = group.children.filter((child) => child.route === 'shop-report-chat')
      group.children = [...fixed, ...result.shops.map((shop: ShopReportShop) => ({
        label: `${shop.channel === 'self' ? '自营' : shop.channel === 'pop' ? 'POP' : '线下'} · ${shop.shop_name}`,
        route: reportNavRoute(shop),
        kind: 'external',
      }))]
    }
    if (!result.shops.some((shop: ShopReportShop) => shopKey(shop) === selectedReportShop.value)) {
      selectedReportShop.value = result.shops[0] ? shopKey(result.shops[0]) : ''
    }
  } catch (error: any) {
    shopReportError.value = error?.message || '店铺报表读取失败'
  }
}

const ecomGroupIndex = (group: { label: string; route: string }) => group.route || group.label

// 导航分组展开状态：记住用户上次手动展开/收起的子菜单，刷新后保持原状。
// 默认全收起（之前是全展开，刷新体验很差）。
const _validGroupIndex = (idx: string) =>
  ECOM_NAV.some((g) => ecomGroupIndex(g) === idx)

const ecomOpenedGroups = ref<string[]>((() => {
  try {
    const raw = sessionStorage.getItem(_OPENED_NAV_GROUPS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((idx): idx is string => typeof idx === 'string' && _validGroupIndex(idx))
  } catch {
    return []
  }
})())

watch(ecomOpenedGroups, (next) => {
  try { sessionStorage.setItem(_OPENED_NAV_GROUPS_KEY, JSON.stringify(next)) } catch {}
}, { deep: true })

const handleEcomSubMenuOpen = (index: string) => {
  if (!index || ecomOpenedGroups.value.includes(index)) return
  ecomOpenedGroups.value = [...ecomOpenedGroups.value, index]
}

const handleEcomSubMenuClose = (index: string) => {
  if (!index) return
  ecomOpenedGroups.value = ecomOpenedGroups.value.filter((i) => i !== index)
}

const ecomActiveRoute = ref('')
const ecomFrameRef = ref<InstanceType<typeof EcommerceDashboard> | null>(null)
const pendingEcomRoute = ref('')

// 侧边栏高亮：
//  - 打开外部模块（简历/库存/客服等）→ 高亮对应电商中台子项
//  - 否则 → 高亮电商中台当前路由，未同步时回落到公司首页
const ecommerceActiveFallback = computed<string>(() => {
  const active = activeMenu.value
  if (active === 'ai-knowledge-qa') return 'knowledge-qa'
  if (active === 'shop-report' && selectedReportShop.value) return `shop-report:${selectedReportShop.value}`
  if (active !== 'ecommerce-dashboard' && EXTERNAL_ECOM_KEYS.has(active)) return active
  return ecomActiveRoute.value || 'home'
})

const handleEcomMenuSelect = (route: string) => {
  if (!route) return
  if (route.startsWith('shop-report:')) {
    if (!canAccess(route)) return
    selectedReportShop.value = route.slice('shop-report:'.length)
    _syncMenu('shop-report')
    return
  }
  if (route === 'knowledge-qa') {
    pendingEcomRoute.value = ''
    goKnowledgeQA()
    return
  }
  if (EXTERNAL_ECOM_KEYS.has(route)) {
    pendingEcomRoute.value = ''
    _syncMenu(route)
    return
  }
  ecomActiveRoute.value = route
  pendingEcomRoute.value = route
  if (activeMenu.value !== 'ecommerce-dashboard') {
    _syncMenu('ecommerce-dashboard')
  }
  // iframe 已就绪则立即下发展值；未就绪则由 frame-ready 补发
  ecomFrameRef.value?.navigateTo(route)
}

// iframe 首次加载完成：若存在未投递的路由（用户在 iframe 就绪前点了侧边栏），补发
const handleEcomFrameReady = () => {
  const pending = pendingEcomRoute.value
  pendingEcomRoute.value = ''
  if (pending && activeMenu.value === 'ecommerce-dashboard') {
    ecomFrameRef.value?.navigateTo(pending)
  }
}

const handleEcomRouteChange = (route: string) => {
  if (route === 'knowledge-qa') {
    goKnowledgeQA()
    return
  }
  if (route && !EXTERNAL_ECOM_KEYS.has(route)) ecomActiveRoute.value = route
}

// ── Active dashboard ─────────────────────────────────────────────────────────
const activeDashboard = computed(() => {
  const menu = activeMenu.value
  if (menu === 'hr-filter') return ResumeFilter
  if (menu === 'hr-driver') return HrDriver
  if (menu === 'hr-roster') return HrRoster
  if (menu === 'hr-recruit') return HrRecruit
  if (menu === 'sys-permissions') return HrPermissionManage
  if (menu === 'sys-users') return AdminUserManage
  if (menu === 'operating-analysis') return OperatingAnalysis
  if (menu === 'operating-chat') return OperatingChat
  if (menu === 'sku-return-data') return SkuReturnData
  if (menu === 'inventory-decision') return InventoryDecision
  if (menu === 'inventory-monitor') return InventoryMonitor
  if (isInventoryMetricMenu.value) return InventoryMonitorMetric
  if (menu === 'inventory-product-dashboard') return InventoryProductDashboard
  if (menu === 'jushuitan-dashboard') return JushuitanDashboard
  if (menu === 'purchase-order-dashboard') return PurchaseOrderDashboard
  if (menu === 'sales-dashboard') return SalesDashboard
  if (menu === 'cs-audit') return CustomerService
  if (menu === 'product-quality-reports') return ProductQualityReports
  if (menu === 'after-sales-quality') return AfterSalesQualityDashboard
  if (menu === 'ai-project-board') return AiProjectBoard
  if (menu === 'ai-prompt-reference') return AiPromptReference
  if (menu === 'ecommerce-dashboard') return EcommerceDashboard
  if (menu === 'ai-knowledge-qa') return KnowledgeAssistantView
  if (menu === 'shop-report') return ShopReport
  if (menu === 'shop-report-chat') return ShopReportChat
  return InventoryDecision
})

// ── Role label ───────────────────────────────────────────────────────────────
const roleLabelMap: Record<string, string> = {
  admin:     '管理员',
  hr:        'HR专员',
  designer:  '设计师',
  employee:  '员工',
}

const jobTitleLabel = computed(() => authJobTitle.value || roleLabelMap[authRole.value] || authRole.value)

const clearAuthCache = () => {
  localStorage.removeItem(AUTH_REAL_NAME_KEY)
  localStorage.removeItem(AUTH_ROLE_KEY)
  localStorage.removeItem(AUTH_USERNAME_KEY)
  localStorage.removeItem(AUTH_JOB_TITLE_KEY)
  localStorage.removeItem(AUTH_DEPARTMENT_KEY)
  localStorage.removeItem(AUTH_DEPT_CODE_KEY)
  localStorage.removeItem(AUTH_LOGIN_TIME_KEY)
  try { sessionStorage.removeItem(_SAVED_MENU_KEY) } catch {}
  try { sessionStorage.removeItem(_OPENED_TABS_KEY) } catch {}
  try { sessionStorage.removeItem(_SIDEBAR_COLLAPSED_KEY) } catch {}
}

// ── Section label for topbar ─────────────────────────────────────────────────
const sectionLabel = computed(() => {
  const m = activeMenu.value
  if (m.startsWith('design-')) return '设计部'
  if (['insight', 'insight-trend', 'insight-category', 'insight-brand'].includes(m)) return '数据洞察'
  if (m === 'shop-report' || m === 'shop-report-chat') return '店铺报表'
  if (m === 'sys-permissions' || m === 'sys-users') return '系统管理'
  if (['inventory-decision', 'inventory-monitor', 'inventory-stockout', 'inventory-shortage', 'inventory-listed', 'inventory-delisted'].includes(m)) return '业务运营'
  if (m === 'jushuitan-dashboard' || m === 'sales-dashboard' || m === 'inventory-product-dashboard' || m === 'purchase-order-dashboard') return '供应链部'
  if (m.startsWith('hr-')) return '人力行政'
  if (m === 'cs-audit') return '客服数据看板'
  if (m === 'after-sales-quality') return '售后质量分析'
  if (m === 'product-quality-reports') return '客服部'
  if (m === 'ai-project-board' || m === 'ai-prompt-reference') return '项目看板'
  if (m === 'ecommerce-dashboard') return '电商中台'
  return '总经办'
})

const doLogout = async () => {
  try {
    await fetch('/api/auth/logout', { method: 'POST' })
  } catch {}
  clearAuthCache()
  window.location.href = '/login.html'
}
</script>

<template>
  <el-config-provider v-if="authChecked && isAuthenticated" :locale="zhCn">
    <el-container class="company-shell">
      <el-aside
        class="company-aside"
        :class="{ 'is-collapsed': isSidebarCollapsed }"
        :width="isSidebarCollapsed ? '72px' : '248px'"
      >
        <div class="brand-block">
          <img class="brand-logo" src="/demo-logo.svg" alt="示例科技 logo" />
          <div>
            <strong>示例企业 AI 工作台</strong>
            <span>Enterprise Command</span>
          </div>
        </div>

        <el-menu
          class="company-menu"
          :default-active="ecommerceActiveFallback"
          :collapse="isSidebarCollapsed"
          :collapse-transition="false"
          :default-openeds="ecomOpenedGroups"
          background-color="var(--app-surface)"
          text-color="var(--text-secondary)"
          active-text-color="#ffffff"
        >
          <template v-for="group in ECOM_NAV" :key="ecomGroupIndex(group)">
            <!-- 有可见子项的顶级分组：展开为一级菜单 -->
            <el-sub-menu
              v-if="visibleChildren(group).length"
              :index="ecomGroupIndex(group)"
              popper-class="sidebar-menu-popper"
              @open="handleEcomSubMenuOpen"
              @close="handleEcomSubMenuClose"
            >
              <template #title>
                <el-icon v-if="group.icon"><Grid /></el-icon>
                <span>{{ group.label }}</span>
              </template>
              <el-menu-item
                v-for="child in visibleChildren(group)"
                :key="child.route"
                :index="child.route"
                :class="{ 'ecom-dev-item': isEcomDevRoute(child.route) }"
                @click="handleEcomMenuSelect(child.route)"
              >
                <span class="menu-item-label">{{ child.label }}</span>
              </el-menu-item>
            </el-sub-menu>
            <!-- 原本就无子项的顶级菜单项（只有定义为「无 children」的分组才落到这里）。
                 如果分组有子项但全部被权限过滤掉，则整组隐藏、不再降级成顶级项，避免暴露无意义入口。 -->
            <el-menu-item
              v-else-if="!(group.children && group.children.length)"
              :index="ecomGroupIndex(group)"
              @click="handleEcomMenuSelect(ecomGroupIndex(group))"
            >
              <el-icon v-if="group.icon"><Grid /></el-icon>
              <span>{{ group.label }}</span>
            </el-menu-item>
          </template>
        </el-menu>
      </el-aside>

      <el-container class="workspace-container">
        <header class="workspace-topbar">
          <div class="topbar-left">
            <button
              class="topbar-sidebar-toggle"
              type="button"
              :title="isSidebarCollapsed ? '展开导航' : '收起导航'"
              :aria-label="isSidebarCollapsed ? '展开导航' : '收起导航'"
              @click="toggleSidebarCollapsed"
            >
              <el-icon>
                <Expand v-if="isSidebarCollapsed" />
                <Fold v-else />
              </el-icon>
            </button>
            <span class="topbar-section-label">{{ sectionLabel }}</span>
          </div>
          <div class="topbar-right">
            <button
              class="theme-toggle"
              type="button"
              :title="isDarkTheme ? '切换到日间模式' : '切换到夜间模式'"
              :aria-label="isDarkTheme ? '切换到日间模式' : '切换到夜间模式'"
              :aria-pressed="isDarkTheme"
              @click="toggleTheme"
            >
              <el-icon><Sunny v-if="isDarkTheme" /><Moon v-else /></el-icon>
            </button>
            <span class="welcome-badge">
              <span class="welcome-name">{{ authRealName }}</span>
              <span class="welcome-sep">(</span>
              <span class="welcome-dept">{{ authDepartment }}</span>
              <span class="welcome-sep">)</span>
            </span>
            <span class="role-chip">{{ jobTitleLabel }}</span>
            <button class="logout-btn" type="button" title="退出登录" @click="doLogout">
              <el-icon><SwitchButton /></el-icon>
              <span>退出登录</span>
            </button>
          </div>
        </header>

        <nav v-if="workspaceTabs.length" class="workspace-tabs" aria-label="已打开页面">
          <div
            v-for="tab in workspaceTabs"
            :key="tab.key"
            class="workspace-tab"
            :class="{ 'is-active': tab.key === activeMenu }"
            role="tab"
            tabindex="0"
            :aria-selected="tab.key === activeMenu"
            :title="tab.label"
            @click="switchWorkspaceTab(tab.key)"
            @keydown.enter.prevent="switchWorkspaceTab(tab.key)"
            @keydown.space.prevent="switchWorkspaceTab(tab.key)"
          >
            <span class="workspace-tab-label">{{ tab.label }}</span>
            <button
              v-if="workspaceTabs.length > 1"
              class="workspace-tab-close"
              type="button"
              title="关闭页签"
              aria-label="关闭页签"
              @click.stop="closeWorkspaceTab(tab.key)"
            >
              <el-icon><Close /></el-icon>
            </button>
          </div>
        </nav>

        <el-main class="workspace-main">
          <KeepAlive>
            <InventoryMonitorMetric
              v-if="isInventoryMetricMenu"
              :key="activeMenu"
              :metric="activeInventoryMetric"
              :initial-filters="inventoryMetricInitialFilters"
              @back="backToInventoryMonitor"
            />
            <ExecutiveBoard
              v-else-if="['insight', 'insight-trend', 'insight-category', 'insight-brand'].includes(activeMenu)"
              :key="activeMenu"
              :view="activeMenu === 'insight-trend' ? 'trend' : activeMenu === 'insight-category' ? 'category' : activeMenu === 'insight-brand' ? 'brand' : 'overview'"
            />
            <DesignBoard
              v-else-if="activeMenu.startsWith('design-')"
              :key="activeMenu"
              :view="activeMenu"
              :can-delete="canDeleteDesign"
              @navigate="handleEcomMenuSelect"
            />
            <ShopReport
              v-else-if="activeMenu === 'shop-report'"
              :data="shopReportData"
              :shop-key="selectedReportShop"
              :error="shopReportError"
              @choose-shop="selectedReportShop = $event"
              @retry="loadShopReport"
            />
            <PointsSystem
              v-else-if="['points', 'points-rule', 'points-log'].includes(activeMenu)"
              :key="activeMenu"
              :view="activeMenu"
            />
            <AiProjectBoard
              v-else-if="activeMenu === 'ai-project-board'"
              :key="activeMenu"
              :theme="isDarkTheme ? 'dark' : 'light'"
            />
            <component
              v-else-if="activeMenu !== 'ecommerce-dashboard'"
              :is="activeDashboard"
              :key="activeMenu"
              @open-metric-page="openInventoryMetric"
            />
          </KeepAlive>
          <!-- 电商中台 iframe 常驻挂载：切到外部模块时仅隐藏（v-show），
               避免重新加载导致 ecom-set-route 消息丢失 -->
          <component
            v-if="pagePermission && canAccess('ecommerce-dashboard')"
            v-show="activeMenu === 'ecommerce-dashboard'"
            :is="EcommerceDashboard"
            :allowed-routes="ECOM_NAV.flatMap(group => group.children.map(child => child.route)).filter(canAccess)"
            :theme="isDarkTheme ? 'dark' : 'light'"
            ref="ecomFrameRef"
            @open-knowledge-qa="goKnowledgeQA"
            @open-external="openExternalMenu"
            @route-change="handleEcomRouteChange"
            @frame-ready="handleEcomFrameReady"
          />
          <div v-else-if="activeMenu === 'ecommerce-dashboard' && pagePermission" class="workspace-denied">当前账号没有经营看板首页的访问权限，请联系管理员配置页面权限。</div>
        </el-main>
      </el-container>
    </el-container>
  </el-config-provider>
</template>

<style scoped>
/* ── Shell ────────────────────────────────────────────────────────────────── */
.company-shell {
  height: 100vh;
  height: 100dvh;
  min-height: 0;
  overflow: hidden;
  background: var(--app-bg);
  transition: background 0.3s ease;
}

/* ── Sidebar ───────────────────────────────────────────────────────────────── */
.company-aside {
  position: sticky;
  top: 0;
  display: flex;
  height: 100vh;
  flex-direction: column;
  border-right: 1px solid var(--border-color);
  background: var(--app-surface);
  box-shadow: var(--shadow-sm);
  transition: width 0.22s ease, flex-basis 0.22s ease, max-width 0.22s ease, background 0.2s ease;
  overflow: visible;
}

.company-aside.is-collapsed {
  box-shadow: var(--shadow-sm);
}

/* ── Brand block ─────────────────────────────────────────────────────────────── */
.brand-block {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 88px;
  padding: 22px 20px 18px;
  border-bottom: 1px solid var(--border-color);
  transition: padding 0.22s ease;
}

.company-aside.is-collapsed .brand-block {
  justify-content: center;
  padding: 22px 12px 18px;
}

.company-aside.is-collapsed .brand-block > div {
  display: none;
}

.brand-logo {
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  border-radius: 8px;
  object-fit: contain;
  box-shadow: 0 6px 14px rgba(15, 118, 110, 0.22);
}

.brand-block strong,
.brand-block span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.brand-block strong {
  color: var(--text-heading);
  font-size: 16px;
  font-weight: 800;
  line-height: 1.3;
}

.brand-block span {
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 12px;
}

/* ── Sidebar menu ───────────────────────────────────────────────────────────── */
.company-menu {
  flex: 1;
  padding: 14px 10px;
  border-right: 0;
  width: 100%;
  overflow-x: hidden;
  background: var(--app-surface);
}

.company-aside.is-collapsed .company-menu {
  padding: 14px 4px;
}

.company-menu :deep(.el-menu-item) {
  height: 46px;
  margin: 4px 0;
  border-radius: 8px;
  font-weight: 700;
  color: var(--text-secondary);
}

.company-menu :deep(.el-menu-item .el-icon) {
  color: inherit;
  font-size: 18px;
}

.company-aside.is-collapsed .company-menu :deep(.el-menu-item),
.company-aside.is-collapsed .company-menu :deep(.el-sub-menu__title) {
  justify-content: center;
  width: 64px;
  padding: 0 !important;
}

.company-aside.is-collapsed .company-menu :deep(.el-menu-item .el-icon),
.company-aside.is-collapsed .company-menu :deep(.el-sub-menu__title .el-icon) {
  margin: 0;
}

.company-menu :deep(.el-sub-menu__title) {
  height: 46px;
  margin: 4px 0;
  border-radius: 8px;
  color: var(--text-secondary);
  font-weight: 700;
  transition: background 0.2s, color 0.2s;
}

.company-menu :deep(.el-sub-menu__title:hover) {
  color: var(--text-accent);
  background: var(--primary-surface);
}

.company-menu :deep(.el-sub-menu.is-opened > .el-sub-menu__title) {
  color: var(--text-accent);
}

.company-menu :deep(.el-menu-item:hover) {
  color: var(--text-accent);
  background: var(--primary-surface);
}

.company-menu :deep(.el-menu-item.is-active) {
  color: #ffffff;
  background: linear-gradient(135deg, #0f766e, #0d9488);
  box-shadow: 0 8px 18px rgba(15, 118, 110, 0.22);
}

.company-menu :deep(.el-menu-item.is-active .el-icon),
.company-menu :deep(.el-menu-item.is-active .nav-ai-label) {
  color: #ffffff;
}

.company-menu :deep(.nav-ai-label) {
  font-weight: 700;
  letter-spacing: 0.01em;
}

/* 测试页（演示数据）子菜单项：淡色弱化提示 */
.company-menu :deep(.el-menu-item.ecom-dev-item) {
  color: #9aa7bb;
  background: rgba(148, 163, 184, 0.08);
  font-weight: 600;
}

.company-menu :deep(.el-menu-item.ecom-dev-item:hover) {
  color: #7c8ba1;
  background: rgba(148, 163, 184, 0.16);
}

.company-menu :deep(.el-menu-item.ecom-dev-item.is-active) {
  color: #ffffff;
  background: linear-gradient(135deg, #0f766e, #0d9488);
}

/* 侧边栏收起后悬浮弹出的子菜单（弹层挂载在 body，需全局生效）：
   修复当前打开页面在弹出层中白字白底“透明”看不见的问题 */
:global(.sidebar-menu-popper .el-menu-item.is-active) {
  color: #ffffff;
  background: linear-gradient(135deg, #0f766e, #0d9488);
  box-shadow: 0 8px 18px rgba(15, 118, 110, 0.22);
}
:global(.sidebar-menu-popper .el-menu-item.is-active .el-icon) {
  color: #ffffff;
}
:global(.sidebar-menu-popper .el-menu-item.is-active:hover) {
  color: #ffffff;
  background: linear-gradient(135deg, #0f766e, #0d9488);
}
:global(.sidebar-menu-popper .el-menu-item:hover) {
  color: var(--text-accent);
  background: var(--primary-surface);
}

.menu-item-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Workspace container ───────────────────────────────────────────────────── */
.workspace-container {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* ── Top bar ───────────────────────────────────────────────────────────────── */
.workspace-topbar {
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 28px;
  background: var(--app-surface);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
  transition: background 0.3s ease, border-color 0.3s ease;
  box-shadow: 0 1px 0 var(--border-subtle);
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.topbar-sidebar-toggle {
  display: inline-flex;
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: var(--text-accent);
  background: var(--primary-surface-2);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  cursor: pointer;
  transition: color 0.2s ease, background 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}

.topbar-sidebar-toggle:hover {
  color: #ffffff;
  background: var(--primary);
  border-color: var(--primary);
  box-shadow: 0 8px 18px rgba(15, 118, 110, 0.16);
}

.topbar-sidebar-toggle .el-icon {
  font-size: 17px;
}

.topbar-section-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  transition: color 0.3s ease;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.theme-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 34px;
  flex: 0 0 36px;
  padding: 0;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--app-surface-2);
  color: var(--text-secondary);
  cursor: pointer;
  transition: color 0.2s ease, background 0.2s ease, border-color 0.2s ease;
}

.theme-toggle .el-icon { font-size: 17px; }
.theme-toggle:hover,
.theme-toggle:focus-visible {
  color: var(--text-accent);
  background: var(--primary-surface);
  border-color: var(--border-focus);
}

.theme-toggle:focus-visible { outline: 2px solid var(--border-focus); outline-offset: 2px; }

/* Welcome badge */
.welcome-badge {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 5px 12px;
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.7), rgba(14, 165, 233, 0.7));
  border-radius: 20px;
  letter-spacing: 0.01em;
}

.welcome-name {
  color: #fff;
}

.welcome-sep,
.welcome-dept {
  color: rgba(255, 255, 255, 0.75);
}

/* Role chip */
.role-chip {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 700;
  color: var(--text-accent);
  background: var(--primary-surface-2);
  border: 1px solid var(--border-color);
  border-radius: 20px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

/* Logout button */
.logout-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 34px;
  min-width: 92px;
  padding: 0 12px;
  color: light-dark(#b91c1c, #fca5a5);
  background: light-dark(#fff7f7, rgba(239, 68, 68, 0.1));
  border: 1px solid light-dark(rgba(185, 28, 28, 0.2), rgba(248, 113, 113, 0.32));
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
  transition: color 0.2s ease, background 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}

.logout-btn .el-icon {
  font-size: 16px;
}

.logout-btn:hover {
  color: light-dark(#991b1b, #fecaca);
  background: light-dark(#fee2e2, rgba(239, 68, 68, 0.18));
  border-color: light-dark(rgba(185, 28, 28, 0.34), rgba(248, 113, 113, 0.5));
  box-shadow: 0 8px 18px rgba(185, 28, 28, 0.12);
}

/* ── Workspace tabs ────────────────────────────────────────────────────────── */
.workspace-tabs {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 48px;
  padding: 7px 28px;
  overflow-x: auto;
  overflow-y: hidden;
  background: var(--app-surface);
  border-bottom: 1px solid var(--border-subtle);
  box-shadow: 0 1px 0 rgba(15, 23, 42, 0.02);
  flex-shrink: 0;
}

.workspace-tab {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 112px;
  max-width: 260px;
  height: 34px;
  padding: 0 14px;
  color: var(--text-secondary);
  background: var(--app-surface-2);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
  transition: color 0.2s ease, background 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
  user-select: none;
}

.workspace-tab:hover {
  color: var(--text-heading);
  border-color: rgba(15, 118, 110, 0.24);
  background: rgba(15, 118, 110, 0.04);
}

/* 激活态：浅色背景 + 绿色文字（不再使用深色实底），弱化边框区分 */
.workspace-tab.is-active {
  color: var(--text-accent);
  background: var(--primary-surface-2);
  border-color: var(--border-focus);
  box-shadow: none;
}

.workspace-tab-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-tab-close {
  display: inline-flex;
  width: 18px;
  height: 18px;
  flex: 0 0 18px;
  align-items: center;
  justify-content: center;
  padding: 0;
  color: inherit;
  background: transparent;
  border: 0;
  border-radius: 6px;
  cursor: pointer;
  opacity: 0.72;
}

.workspace-tab-close:hover {
  background: rgba(15, 23, 42, 0.08);
  opacity: 1;
}

.workspace-tab.is-active .workspace-tab-close:hover {
  background: rgba(15, 118, 110, 0.16);
}

.workspace-tab:not(.is-active) .workspace-tab-close:hover {
  background: rgba(15, 23, 42, 0.08);
}

.workspace-tab-close .el-icon {
  font-size: 13px;
}

/* ── Workspace main ─────────────────────────────────────────────────────────── */
.workspace-main {
  min-width: 0;
  min-height: 0;
  flex: 1;
  padding: 0;
  background: var(--app-bg);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  transition: background 0.3s ease;
}

/* ── Responsive ─────────────────────────────────────────────────────────────── */
@media (max-width: 900px) {
  .company-shell {
    flex-direction: column;
    height: auto;
    min-height: 100vh;
    min-height: 100dvh;
    overflow: visible;
  }

  .company-aside {
    position: relative;
    width: 100% !important;
    height: auto;
    min-height: 0;
  }

  .brand-block {
    min-height: 72px;
  }

  .company-menu {
    display: flex;
    overflow-x: auto;
    padding: 8px 10px 12px;
  }

  .company-menu :deep(.el-menu-item) {
    flex: 0 0 auto;
    margin: 0 4px;
    padding: 0 14px;
  }

  .company-menu :deep(.el-sub-menu) {
    flex: 0 0 auto;
  }

  .workspace-topbar {
    padding: 0 16px;
  }

  .workspace-tabs {
    padding: 7px 16px;
  }

  .workspace-tab {
    min-width: 104px;
    max-width: 200px;
    padding: 0 12px;
  }

  .topbar-right {
    gap: 8px;
  }

  .welcome-badge {
    font-size: 12px;
  }

  .role-chip {
    display: none;
  }

  .logout-btn {
    min-width: 78px;
    padding: 0 10px;
    font-size: 12px;
  }
}
@media (max-width: 600px) {
  .workspace-topbar { gap: 8px; }
  .topbar-section-label { white-space: nowrap; }
  .topbar-right { gap: 6px; }
  .welcome-badge { display: none; }
}
@media (min-width: 901px) {
  :global(html),
  :global(body),
  :global(#app) {
    width: 100%;
    height: 100%;
    min-height: 0;
    overflow: hidden;
  }
}
</style>
