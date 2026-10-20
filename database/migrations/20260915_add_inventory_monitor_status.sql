-- 20260915 库存看板监控增加商品上下柜状态
-- 供运营部看板统计上柜、下柜数量，并按筛选条件查看状态明细。

USE `enterprise_agent_db`;

SET @schema_name = DATABASE();

SET @ddl = IF(
    EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = @schema_name
          AND TABLE_NAME = 'inv_monitor_snapshot'
          AND COLUMN_NAME = 'product_status'
    ),
    'SELECT 1',
    'ALTER TABLE inv_monitor_snapshot ADD COLUMN product_status VARCHAR(32) NOT NULL DEFAULT '''' COMMENT ''商品上下柜状态'' AFTER shop_name'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
