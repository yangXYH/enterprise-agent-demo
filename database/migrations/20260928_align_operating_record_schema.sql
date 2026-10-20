-- Align local operating records with the current production schema.
-- Run after 20260917_create_operating_analysis_mysql_tables.sql.

UPDATE jy_records SET filename = '' WHERE filename IS NULL;

SET @jy_records_primary_key := (
    SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ',')
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'jy_records'
      AND INDEX_NAME = 'PRIMARY'
);

SET @jy_align_primary_sql := IF(
    @jy_records_primary_key = 'day,sku,filename',
    'SELECT 1',
    'ALTER TABLE `jy_records` DROP PRIMARY KEY, ADD PRIMARY KEY (`day`, `sku`, `filename`)'
);

PREPARE jy_align_primary FROM @jy_align_primary_sql;
EXECUTE jy_align_primary;
DEALLOCATE PREPARE jy_align_primary;

SET @jy_has_source := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'jy_records' AND COLUMN_NAME = 'source'
);
SET @jy_add_source_sql := IF(
    @jy_has_source > 0,
    'SELECT 1',
    'ALTER TABLE `jy_records` ADD COLUMN `source` VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL DEFAULT ''示例科技'' AFTER `raw`'
);
PREPARE jy_add_source FROM @jy_add_source_sql;
EXECUTE jy_add_source;
DEALLOCATE PREPARE jy_add_source;

SET @jy_has_brand := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'jy_records' AND COLUMN_NAME = 'brand'
);
SET @jy_add_brand_sql := IF(
    @jy_has_brand > 0,
    'SELECT 1',
    'ALTER TABLE `jy_records` ADD COLUMN `brand` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL COMMENT ''标准化品牌名称'' AFTER `source`'
);
PREPARE jy_add_brand FROM @jy_add_brand_sql;
EXECUTE jy_add_brand;
DEALLOCATE PREPARE jy_add_brand;

ALTER TABLE jy_records
    MODIFY COLUMN day VARCHAR(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '统计日期 YYYY-MM-DD',
    MODIFY COLUMN sku VARCHAR(191) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL COMMENT '商品 SKU',
    MODIFY COLUMN name VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL COMMENT 'SKU 名称',
    MODIFY COLUMN code VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL COMMENT '商品货号',
    MODIFY COLUMN category VARCHAR(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL COMMENT '三级类目',
    MODIFY COLUMN filename VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    MODIFY COLUMN source VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL DEFAULT '示例科技' AFTER raw,
    MODIFY COLUMN brand VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL COMMENT '标准化品牌名称' AFTER source;
