-- SKU stock warning forecast table.
-- Additive and idempotent. Run against enterprise_agent_db.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS inv_sku_warning_forecast (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
    snapshot_date DATE NOT NULL COMMENT 'Inventory snapshot date',
    sku_code VARCHAR(64) NOT NULL COMMENT 'SKU code',
    product_name VARCHAR(512) NOT NULL DEFAULT '' COMMENT 'Product name',
    brand VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Brand',
    category VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'Category',
    warehouse_count INT NOT NULL DEFAULT 0 COMMENT 'Warehouse rows used',
    daily_sales DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'Daily sales sum across warehouses',
    predicted_60d DECIMAL(18,4) NOT NULL DEFAULT 0 COMMENT 'Predicted 60-day sales',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (id),
    UNIQUE KEY uk_inv_sku_warning_date_sku (snapshot_date, sku_code),
    KEY idx_inv_sku_warning_date (snapshot_date),
    KEY idx_inv_sku_warning_brand (snapshot_date, brand),
    KEY idx_inv_sku_warning_category (snapshot_date, category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='SKU stock warning forecast table';

CREATE TABLE IF NOT EXISTS inv_sku_warning_setting (
    id TINYINT NOT NULL DEFAULT 1 COMMENT 'Fixed primary key',
    forecast_days INT NOT NULL DEFAULT 60 COMMENT 'Safety period in days',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='SKU stock warning safety period setting';
