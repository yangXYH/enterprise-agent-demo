-- SKU 退货数据。执行本文件或由导入命令的 ensure_schema 幂等创建。
-- 回滚：先停止该模块请求，再按 fact、aggregate、source_unit、import_run、brand_rule、state 顺序 DROP TABLE。

CREATE TABLE IF NOT EXISTS sku_return_import_run (
  id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '完整导入版本 ID',
  manifest_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '排序文件清单摘要',
  rule_version INT NOT NULL COMMENT '品牌规则版本',
  status VARCHAR(20) NOT NULL COMMENT 'building、complete 或 failed',
  started_at DATETIME NOT NULL DEFAULT '1970-01-01 00:00:00' COMMENT '开始时间',
  completed_at DATETIME NULL COMMENT '完成时间',
  source_units INT NOT NULL DEFAULT 0 COMMENT '来源数据表数',
  scanned_rows INT NOT NULL DEFAULT 0 COMMENT '扫描业务行数',
  target_rows INT NOT NULL DEFAULT 0 COMMENT '目标单据行数',
  isolated_rows INT NOT NULL DEFAULT 0 COMMENT '隔离行数',
  duplicate_rows INT NOT NULL DEFAULT 0 COMMENT '跨来源重复排除行数',
  included_rows INT NOT NULL DEFAULT 0 COMMENT '计入统计行数',
  report_json LONGTEXT NULL COMMENT '不含用户可见技术编号的质量报告 JSON',
  error_message TEXT NULL COMMENT '失败诊断',
  PRIMARY KEY (id),
  KEY idx_sku_return_run_manifest (manifest_sha256, rule_version, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='SKU 退货导入运行';

CREATE TABLE IF NOT EXISTS sku_return_source_unit (
  id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '来源工作表 ID',
  run_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '导入版本',
  relative_path TEXT NOT NULL COMMENT '导入根目录内相对路径',
  path_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '相对路径摘要',
  file_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '文件摘要',
  sheet_name VARCHAR(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '工作表名',
  period CHAR(7) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '结算归属月 YYYY-MM',
  entity VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '主体',
  category VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '文件名类目',
  scanned_rows INT NOT NULL DEFAULT 0 COMMENT '扫描行数',
  target_rows INT NOT NULL DEFAULT 0 COMMENT '目标行数',
  included_rows INT NOT NULL DEFAULT 0 COMMENT '计入行数',
  PRIMARY KEY (id),
  UNIQUE KEY uq_sku_return_source (run_id, path_sha256, sheet_name),
  KEY idx_sku_return_source_dimensions (run_id, period, entity, category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='SKU 退货来源工作表';

CREATE TABLE IF NOT EXISTS sku_return_fact (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '事实行 ID',
  run_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '导入版本',
  source_unit_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '来源工作表',
  source_row INT NOT NULL COMMENT 'Excel 行号',
  document_type VARCHAR(40) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '应付帐单据类型',
  supplier_name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '规范供应商名称',
  supplier_raw VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '源供应商名称',
  sku_code VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'SKU 编码',
  sku_name VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '规范 SKU 名称',
  sku_name_raw VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '源 SKU 名称',
  brand VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '匹配标准品牌',
  brand_rule_id BIGINT NULL COMMENT '命中品牌规则 ID',
  raw_quantity DECIMAL(24,6) NULL COMMENT '带符号原始数量；隔离时可空',
  sales_quantity DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '净销售数量',
  return_in_quantity DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '退货入库数量',
  after_sales_quantity DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '售后退货数量',
  technical_document_id VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL DEFAULT '' COMMENT '仅技术去重的单据 ID',
  technical_document_no VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL DEFAULT '' COMMENT '仅技术去重的单据编号',
  dedupe_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '候选键摘要',
  included TINYINT(1) NOT NULL COMMENT '是否计入指标',
  excluded_reason VARCHAR(64) NOT NULL DEFAULT '' COMMENT '隔离或重复原因',
  duplicate_of_source_unit_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '首次出现工作表',
  duplicate_of_row INT NULL COMMENT '首次出现行号',
  PRIMARY KEY (id),
  UNIQUE KEY uq_sku_return_fact_source_row (source_unit_id, source_row),
  KEY idx_sku_return_fact_run_source (run_id, source_unit_id, included),
  KEY idx_sku_return_fact_sku (run_id, sku_code(183), included),
  KEY idx_sku_return_fact_dedupe (run_id, dedupe_sha256),
  KEY idx_sku_return_fact_brand (run_id, brand(183)),
  KEY idx_sku_return_fact_supplier (run_id, supplier_name(183))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='SKU 退货逐笔事实及去重证据';

CREATE TABLE IF NOT EXISTS sku_return_aggregate (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '聚合行 ID',
  run_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '导入版本',
  period CHAR(7) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '结算归属月',
  entity VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '主体',
  category VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '类目',
  supplier_name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '供应商',
  sku_code VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'SKU 编码',
  sku_name VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT 'SKU 名称',
  brand VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '品牌',
  sales_quantity DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '净销售数量',
  return_in_quantity DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '退货入库数量',
  after_sales_quantity DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '售后退货数量',
  fact_count INT NOT NULL DEFAULT 0 COMMENT '计入事实行数',
  PRIMARY KEY (id),
  KEY idx_sku_return_agg_scope (run_id, period, entity, category),
  KEY idx_sku_return_agg_sku (run_id, sku_code(183)),
  KEY idx_sku_return_agg_brand (run_id, brand(183)),
  KEY idx_sku_return_agg_supplier (run_id, supplier_name(183))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='SKU 退货维度预聚合';

CREATE TABLE IF NOT EXISTS sku_return_brand_rule (
  id BIGINT NOT NULL AUTO_INCREMENT COMMENT '品牌规则 ID',
  rule_version INT NOT NULL COMMENT '不可变规则集版本',
  match_type VARCHAR(12) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT 'exact 或 prefix',
  pattern VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '原始匹配文本',
  pattern_key VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '大小写折叠匹配键',
  canonical_brand VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '标准品牌',
  priority INT NOT NULL DEFAULT 0 COMMENT '次级优先级',
  enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  updated_at DATETIME NOT NULL DEFAULT '1970-01-01 00:00:00' COMMENT '规则保存时间',
  updated_by VARCHAR(191) NOT NULL DEFAULT '' COMMENT '维护用户',
  PRIMARY KEY (id),
  UNIQUE KEY uq_sku_return_brand_rule (rule_version, match_type, pattern_key(178)),
  KEY idx_sku_return_brand_version (rule_version, enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='SKU 退货可配置品牌规则集';

CREATE TABLE IF NOT EXISTS sku_return_state (
  id TINYINT NOT NULL COMMENT '固定为 1 的活动状态行',
  active_run_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '原子切换的活动版本',
  rule_version INT NOT NULL DEFAULT 1 COMMENT '当前品牌规则集版本',
  updated_at DATETIME NOT NULL DEFAULT '1970-01-01 00:00:00' COMMENT '更新时间',
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='SKU 退货活动数据版本指针';
