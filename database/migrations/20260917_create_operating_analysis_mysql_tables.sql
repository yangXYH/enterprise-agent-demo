-- 经营分析模块 MySQL 表结构
-- 说明：本文件对应 utils/operating_db.py，表名统一使用 jy_ 前缀。

CREATE TABLE IF NOT EXISTS jy_batches (
    filename VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '导入文件名',
    digest VARCHAR(64) NULL COMMENT '文件 SHA-256 摘要',
    imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '导入时间',
    row_count INT NULL COMMENT '有效明细行数',
    start VARCHAR(10) NULL COMMENT '数据起始日期',
    end VARCHAR(10) NULL COMMENT '数据结束日期',
    control TEXT NULL COMMENT '原报表合计行 JSON',
    headers TEXT NULL COMMENT '原报表表头 JSON',
    PRIMARY KEY (filename)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='经营分析导入批次';

CREATE TABLE IF NOT EXISTS jy_records (
    day VARCHAR(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '统计日期 YYYY-MM-DD',
    sku VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '商品 SKU',
    name VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL COMMENT 'SKU 名称',
    code VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL COMMENT '商品货号',
    category VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL COMMENT '三级类目',
    filename VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL COMMENT '来源文件名',
    source_row INT NULL COMMENT '来源文件行号',
    revenue BIGINT NULL COMMENT '成交金额，百万分之一元',
    quantity FLOAT NULL COMMENT '成交商品件数',
    orders FLOAT NULL COMMENT '成交单量',
    customers FLOAT NULL COMMENT '成交客户数',
    views FLOAT NULL COMMENT '商品浏览量',
    visitors FLOAT NULL COMMENT '商品访客数',
    cart_quantity FLOAT NULL COMMENT '加购商品件数',
    cart_customers FLOAT NULL COMMENT '加购客户数',
    cart_amount BIGINT NULL COMMENT '加购金额，百万分之一元',
    raw TEXT NULL COMMENT '原始行完整字段 JSON',
    source VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL DEFAULT '示例科技',
    brand VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL COMMENT '标准化品牌名称',
    PRIMARY KEY (day, sku),
    KEY operating_day (day),
    KEY operating_sku (sku),
    KEY operating_sku_code (sku, code),
    KEY operating_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='经营分析商品日明细';

CREATE TABLE IF NOT EXISTS jy_operating_settings (
    setting_key VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '配置键',
    value TEXT NULL COMMENT '配置值',
    PRIMARY KEY (setting_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='经营分析内部配置及数据版本';

CREATE TABLE IF NOT EXISTS jy_operating_brands (
    name VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'SKU 名称',
    brand VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL COMMENT '标准化品牌名称',
    PRIMARY KEY (name),
    KEY operating_brands_brand (brand)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='经营分析商品名称与品牌映射';

CREATE TABLE IF NOT EXISTS jy_operating_model_mapping (
    sku VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '商品 SKU',
    code VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '运营维护的商品货号/型号',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首次维护时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后维护时间',
    PRIMARY KEY (sku),
    KEY operating_model_mapping_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='经营分析 SKU 与型号货号的显式映射';

CREATE TABLE IF NOT EXISTS jy_operating_chat_session (
    id VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '会话 ID',
    owner VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '所属用户 ID',
    title VARCHAR(512) NOT NULL COMMENT '会话标题',
    filters TEXT NOT NULL COMMENT '最近一次有效查询条件 JSON',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY operating_chat_owner (owner, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='经营分析 AI 会话';

CREATE TABLE IF NOT EXISTS jy_operating_chat_turn (
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
    UNIQUE KEY uq_operating_turn_request (session_id, request_id),
    UNIQUE KEY uq_operating_turn_ordinal (session_id, ordinal),
    KEY operating_chat_turn_session (session_id, ordinal)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='经营分析 AI 问答轮次';

CREATE TABLE IF NOT EXISTS jy_operating_knowledge_document (
    id VARCHAR(24) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '文档版本 ID',
    library VARCHAR(64) NULL COMMENT '知识库类型',
    path VARCHAR(1024) NULL COMMENT '知识目录相对路径',
    title VARCHAR(512) NULL COMMENT '文档标题',
    digest VARCHAR(64) NULL COMMENT '内容 SHA-256 摘要',
    status VARCHAR(32) NULL COMMENT '索引状态',
    error TEXT NULL COMMENT '解析错误',
    indexed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首次索引时间',
    modified_ns BIGINT NOT NULL DEFAULT 0 COMMENT '源文件修改时间纳秒值',
    size BIGINT NOT NULL DEFAULT 0 COMMENT '源文件字节数',
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='经营分析知识文档索引';

CREATE TABLE IF NOT EXISTS jy_operating_knowledge_chunk (
    id VARCHAR(24) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '知识片段 ID',
    document_id VARCHAR(24) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL COMMENT '所属文档 ID',
    heading VARCHAR(512) NULL COMMENT '章节标题',
    location VARCHAR(512) NULL COMMENT '页码或行号位置',
    text TEXT NULL COMMENT '知识片段正文',
    PRIMARY KEY (id),
    KEY operating_knowledge_chunks_doc (document_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='经营分析知识检索片段';
