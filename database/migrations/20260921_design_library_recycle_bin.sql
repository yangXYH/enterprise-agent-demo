-- 设计部资料回收站。服务运行时也会自动补齐字段；脚本可重复执行。
SET @schema_name = DATABASE();

SET @ddl = IF(
    EXISTS (SELECT 1 FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = @schema_name AND TABLE_NAME = 'design_library_item'
              AND COLUMN_NAME = 'deleted_by'),
    'SELECT 1',
    'ALTER TABLE design_library_item ADD COLUMN deleted_by VARCHAR(191) NULL'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl = IF(
    EXISTS (SELECT 1 FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = @schema_name AND TABLE_NAME = 'design_library_item'
              AND COLUMN_NAME = 'deleted_at'),
    'SELECT 1',
    'ALTER TABLE design_library_item ADD COLUMN deleted_at DATETIME NULL'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl = IF(
    EXISTS (SELECT 1 FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = @schema_name AND TABLE_NAME = 'design_library_item'
              AND INDEX_NAME = 'idx_design_deleted'),
    'SELECT 1',
    'ALTER TABLE design_library_item ADD KEY idx_design_deleted (deleted_at, item_type)'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS design_library_meta (
    meta_key VARCHAR(64) NOT NULL PRIMARY KEY
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
