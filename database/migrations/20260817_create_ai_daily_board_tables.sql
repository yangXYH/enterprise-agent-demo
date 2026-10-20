-- AI 项目推进看板数据库迁移脚本。
-- 作用：
--   1. ai_daily_board：保存看板名称、当前日期和四个模块的显示开关。
--   2. ai_daily_board_project：AI 项目（名称/状态/当前重点一句话）。
--   3. ai_daily_board_daily_log：每日推进记录（所属项目/今天做了什么/明天计划/风险）。
--   4. ai_daily_board_risk：风险与阻塞，支持阻塞天数计算。
-- 说明：
--   - 本脚本只新增表，不删除、不清空、不修改已有业务表。
--   - 使用 CREATE TABLE IF NOT EXISTS，重复执行不会重复建表。
--   - 早期版本的任务/站会/历史表已不再使用，但为兼容存量库不在此删除。
--   - 需要在 enterprise_agent_db 对应的 MySQL 数据库中执行。

SET NAMES utf8mb4;

-- AI 项目推进看板配置表：每个看板一行，前端通过 board_key 读写。
CREATE TABLE IF NOT EXISTS ai_daily_board (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '看板主键ID',
    board_key VARCHAR(64) NOT NULL DEFAULT 'default' COMMENT '看板唯一标识，默认看板为 default，预留多看板扩展',
    board_title VARCHAR(128) NOT NULL DEFAULT 'AI 项目进度看板' COMMENT '看板名称',
    `current_date` DATE NOT NULL COMMENT '看板当前日期',
    show_charts TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否显示顶部指标，1显示，0隐藏',
    show_standup TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否显示每日推进记录，1显示，0隐藏',
    show_timeline TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否显示风险阻塞，1显示，0隐藏',
    show_table TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否显示项目概览，1显示，0隐藏',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_daily_board_key (board_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI项目推进看板配置表';

-- AI 项目推进看板项目表：每个 AI 项目一行，携带名称、状态与当前重点。
CREATE TABLE IF NOT EXISTS ai_daily_board_project (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT 'AI项目主键ID',
    board_id BIGINT NOT NULL COMMENT '所属看板ID，关联ai_daily_board.id',
    client_id VARCHAR(80) NOT NULL COMMENT '前端生成的客户端项目ID',
    name VARCHAR(128) NOT NULL COMMENT '项目名称',
    status VARCHAR(16) NOT NULL DEFAULT '开发中' COMMENT '项目状态：开发中/测试/已上线/业务使用',
    focus VARCHAR(255) NOT NULL DEFAULT '' COMMENT '当前重点一句话',
    owner VARCHAR(64) NOT NULL DEFAULT '' COMMENT '项目负责人，为空表示本人',
    start_date DATE NULL COMMENT '项目开始日期',
    end_date DATE NULL COMMENT '项目结束日期',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '项目排序序号',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_daily_project_board_client (board_id, client_id),
    KEY idx_ai_daily_project_board (board_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI项目推进看板项目表';

-- AI 项目推进看板每日推进记录表：每天每个任务/项目一条独立记录。
CREATE TABLE IF NOT EXISTS ai_daily_board_daily_log (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '每日推进记录主键ID',
    board_id BIGINT NOT NULL COMMENT '所属看板ID，关联ai_daily_board.id',
    log_date DATE NOT NULL COMMENT '记录所属日期',
    project_id VARCHAR(80) NOT NULL DEFAULT '' COMMENT '所属项目客户端ID，空表示总体推进',
    project_name VARCHAR(128) NOT NULL DEFAULT '' COMMENT '所属项目名称快照',
    work VARCHAR(1000) NOT NULL DEFAULT '' COMMENT '今天做了什么',
    tomorrow VARCHAR(500) NOT NULL DEFAULT '' COMMENT '明天计划',
    risk_note VARCHAR(500) NOT NULL DEFAULT '' COMMENT '风险与阻塞',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_daily_log_board_date_project (board_id, log_date, project_id),
    KEY idx_ai_daily_log_project (board_id, project_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI项目推进看板每日推进记录表';

-- 兼容升级：若为存量库已建过旧"一天一条"唯一键 (board_id, log_date)，替换为按日期+项目区分的新键，
-- 使同一天可保存多条相互独立的推进记录（每个任务/项目一条）。
SET @has_old_uk := (SELECT COUNT(*) FROM information_schema.statistics
    WHERE table_schema = DATABASE() AND table_name = 'ai_daily_board_daily_log'
      AND index_name = 'uk_ai_daily_log_board_date');
SET @sql := IF(@has_old_uk > 0,
    'ALTER TABLE ai_daily_board_daily_log DROP INDEX uk_ai_daily_log_board_date',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @has_new_uk := (SELECT COUNT(*) FROM information_schema.statistics
    WHERE table_schema = DATABASE() AND table_name = 'ai_daily_board_daily_log'
      AND index_name = 'uk_ai_daily_log_board_date_project');
SET @sql := IF(@has_new_uk = 0,
    'ALTER TABLE ai_daily_board_daily_log ADD UNIQUE KEY uk_ai_daily_log_board_date_project (board_id, log_date, project_id)',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- AI 项目推进看板风险表：风险描述、影响、负责人、状态与阻塞开始日期。
CREATE TABLE IF NOT EXISTS ai_daily_board_risk (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '风险记录主键ID',
    board_id BIGINT NOT NULL COMMENT '所属看板ID，关联ai_daily_board.id',
    client_id VARCHAR(80) NOT NULL COMMENT '前端生成的客户端风险ID',
    risk VARCHAR(255) NOT NULL COMMENT '风险描述',
    project_id VARCHAR(80) NOT NULL DEFAULT '' COMMENT '所属项目客户端ID，空表示总体',
    project_name VARCHAR(128) NOT NULL DEFAULT '' COMMENT '所属项目名称快照',
    impact VARCHAR(16) NOT NULL DEFAULT '中' COMMENT '影响程度：高/中/低',
    owner VARCHAR(64) NOT NULL DEFAULT '' COMMENT '负责人',
    status VARCHAR(32) NOT NULL DEFAULT '待解决' COMMENT '状态：待解决/处理中/已解决',
    blocked_since DATE NULL COMMENT '阻塞开始日期，用于计算已阻塞天数',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '风险在列表中的排序序号',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_ai_daily_risk_board_client (board_id, client_id),
    KEY idx_ai_daily_risk_board (board_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI项目推进看板风险表';

-- AI 项目推进看板操作日志表：记录谁在何时做了什么操作（审计）。
CREATE TABLE IF NOT EXISTS ai_daily_board_activity (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '操作日志主键ID',
    board_key VARCHAR(64) NOT NULL DEFAULT 'default' COMMENT '所属看板标识',
    operator VARCHAR(64) NOT NULL DEFAULT '' COMMENT '操作人',
    action VARCHAR(64) NOT NULL COMMENT '操作类型',
    target VARCHAR(128) NOT NULL DEFAULT '' COMMENT '操作对象（如项目名）',
    detail VARCHAR(500) NOT NULL DEFAULT '' COMMENT '操作详情',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
    PRIMARY KEY (id),
    KEY idx_ai_daily_activity_board (board_key, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI项目进度看板操作日志表';
