-- 店铺报表 AI 问答表结构
-- 说明：对应 utils/shop_report_chat_service.py；与经营分析问答分表存储，互不影响。

CREATE TABLE IF NOT EXISTS jy_shop_report_chat_session (
    id VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '会话 ID',
    owner VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '所属用户 ID',
    title VARCHAR(512) NOT NULL COMMENT '会话标题',
    filters TEXT NOT NULL COMMENT '最近一次有效查询条件 JSON',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY shop_report_chat_owner (owner, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='店铺报表 AI 会话';

CREATE TABLE IF NOT EXISTS jy_shop_report_chat_turn (
    id VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '问答轮次 ID',
    session_id VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '所属会话 ID',
    ordinal INT NOT NULL COMMENT '会话内轮次序号',
    request_id VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '客户端幂等请求 ID',
    question TEXT NOT NULL COMMENT '用户问题',
    status VARCHAR(32) NOT NULL COMMENT 'pending/completed/error',
    response TEXT NULL COMMENT '完整回答及证据 JSON',
    context_refs TEXT NOT NULL COMMENT '关联历史轮次 JSON',
    filters TEXT NOT NULL COMMENT '本轮查询条件 JSON',
    error TEXT NULL COMMENT '失败原因',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '提问时间',
    completed_at DATETIME NULL COMMENT '完成时间',
    stage VARCHAR(120) NOT NULL DEFAULT '' COMMENT '生成阶段',
    partial_answer TEXT NULL COMMENT '生成中的已核对答案',
    PRIMARY KEY (id),
    UNIQUE KEY uq_shop_report_turn_request (session_id, request_id),
    UNIQUE KEY uq_shop_report_turn_ordinal (session_id, ordinal),
    KEY shop_report_chat_turn_session (session_id, ordinal)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='店铺报表 AI 问答轮次';
