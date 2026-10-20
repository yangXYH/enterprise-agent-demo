-- 客服数据看板共享状态表 + 系统子页面权限表 数据库迁移脚本。
-- 作用：
--   1. cs_dashboard_state：客服数据看板（cs-audit 页）的共享数据存储。
--      此前上传的报表只存在浏览器 localStorage，导致一人上传他人看不到；
--      本表把解析后的全部行数据整份存进 MySQL，所有登录用户读取同一份数据。
--      前端通过 GET/PUT /api/cs/dashboard 读写本表。
--   2. sys_subpage_permission：页面内「页签级」权限配置（page_key + sub_key 粒度）。
--      与页面级权限表 sys_page_permission 配套，目前仅「库存分析决策」页使用，
--      后续其他页面有内容级权限需求时在此扩展。
-- 说明：
--   - 本脚本只新增表，不删除、不清空、不修改已有业务表。
--   - 使用 CREATE TABLE IF NOT EXISTS，重复执行不会重复建表。
--   - sys_subpage_permission 的默认页签配置使用 INSERT IGNORE 补齐，
--     与 utils/permission_service.py 的 _ensure_subpage_permissions 逻辑保持一致，
--     只对缺失的页签生效，绝不覆盖已保存的权限配置。
--   - 需要在 enterprise_agent_db 对应的 MySQL 数据库中执行。

SET NAMES utf8mb4;

-- ============================================================================
-- 1. 客服数据看板共享状态表（单行 KV 结构，id 固定为 1）
-- ============================================================================
CREATE TABLE IF NOT EXISTS cs_dashboard_state (
    id TINYINT NOT NULL DEFAULT 1 COMMENT '固定主键（单行存储）',
    rows_json LONGTEXT NOT NULL COMMENT '客服看板解析后的全部行数据 JSON 数组',
    source_name VARCHAR(255) NOT NULL DEFAULT '' COMMENT '数据来源文件名',
    loaded TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已载入数据，1载入，0未载入',
    updated_by VARCHAR(64) NOT NULL DEFAULT '' COMMENT '最后更新人（登录用户姓名）',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客服数据看板共享状态';

-- 说明：本表初始为空即可。后端 GET /api/cs/dashboard 在无数据时返回空结构，
--       前端首次打开看板会自动加载内置默认快照并写回本表（id=1 行）。

-- ============================================================================
-- 2. 系统子页面权限表（页签级权限，page_key + sub_key 联合主键）
-- ============================================================================
CREATE TABLE IF NOT EXISTS sys_subpage_permission (
    page_key VARCHAR(64) NOT NULL COMMENT '所属页面标识（如 inventory-decision）',
    sub_key VARCHAR(64) NOT NULL COMMENT '页签标识（如 forecast / plans / settings）',
    roles TEXT NOT NULL COMMENT '可见角色 JSON 数组，含 "*" 表示所有人可见，空数组表示暂不开放',
    updated_at DATETIME NULL COMMENT '更新时间',
    PRIMARY KEY (page_key, sub_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统子页面权限表';

-- 默认页签配置（与 utils/permission_service.py 的 SUB_PERM_DEFS / SUB_PERM_DEFAULTS 一致）：
-- 默认角色为空数组 = 对所有角色/人员隐藏，由管理员在「权限管理」后台自行配置；
-- INSERT IGNORE 保证只补缺失页签，绝不覆盖已保存的权限配置。
INSERT IGNORE INTO sys_subpage_permission (page_key, sub_key, roles, updated_at) VALUES
    ('inventory-decision', 'forecast',        '[]', NOW()),
    ('inventory-decision', 'purchase-export', '[]', NOW()),
    ('inventory-decision', 'sku-warning',     '[]', NOW()),
    ('inventory-decision', 'plans',           '[]', NOW()),
    ('inventory-decision', 'sku-decision',    '[]', NOW()),
    ('inventory-decision', 'settings',        '[]', NOW()),
    ('inventory-decision', 'cities',          '[]', NOW()),
    ('inventory-decision', 'simulate',        '[]', NOW());
