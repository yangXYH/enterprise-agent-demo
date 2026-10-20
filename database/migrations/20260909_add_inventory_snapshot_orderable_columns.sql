-- 20260909 库存快照新增运营表口径字段
-- inv_stock_snapshot 增加 可用库存件数 / 可订购库存件数，供补货导出「运营表(Excel 40周转)」算法取值。
-- 该迁移是幂等、增量式：重复执行无副作用（列已存在时跳过）。
-- 运行时 ensure_inventory_schema 的 _ensure_inventory_columns 会以同样 DDL 自动补齐，此文件供部署环境初始化使用。

USE `enterprise_agent_db`;

SET @schema_name = DATABASE();

-- 可用库存件数
SET @ddl = IF(
    EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = @schema_name
          AND TABLE_NAME = 'inv_stock_snapshot'
          AND COLUMN_NAME = 'available_qty'
    ),
    'SELECT 1',
    'ALTER TABLE inv_stock_snapshot ADD COLUMN available_qty DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT ''可用库存件数'' AFTER inbound_qty'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 可订购库存件数（运营表40周转口径）
SET @ddl = IF(
    EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = @schema_name
          AND TABLE_NAME = 'inv_stock_snapshot'
          AND COLUMN_NAME = 'orderable_qty'
    ),
    'SELECT 1',
    'ALTER TABLE inv_stock_snapshot ADD COLUMN orderable_qty DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT ''可订购库存件数（运营表40周转口径）'' AFTER available_qty'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
