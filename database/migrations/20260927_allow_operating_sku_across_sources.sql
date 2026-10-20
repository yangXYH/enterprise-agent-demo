-- Allow the same product-day key to be stored once per report source.
-- Run once before importing reports from both 示例科技 and 示例户外.
-- This preserves every existing row. Run during a quiet window because MySQL
-- may rebuild the jy_records primary index while applying the ALTER TABLE.

UPDATE jy_records SET filename = '' WHERE filename IS NULL;

SET @jy_records_primary_key := (
    SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ',')
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'jy_records'
      AND INDEX_NAME = 'PRIMARY'
);

SET @jy_source_migration_sql := IF(
    @jy_records_primary_key = 'day,sku,filename',
    'SELECT 1',
    'ALTER TABLE `jy_records` MODIFY `filename` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL, DROP PRIMARY KEY, ADD PRIMARY KEY (`day`, `sku`, `filename`)'
);

PREPARE jy_source_migration FROM @jy_source_migration_sql;
EXECUTE jy_source_migration;
DEALLOCATE PREPARE jy_source_migration;
