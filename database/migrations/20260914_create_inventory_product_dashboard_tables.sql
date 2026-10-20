CREATE TABLE IF NOT EXISTS inventory_product_import_batch (
    batch_id VARCHAR(32) NOT NULL,
    report_date DATE NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    source_name VARCHAR(255) NOT NULL DEFAULT '',
    row_count INT NOT NULL DEFAULT 0,
    image_count INT NOT NULL DEFAULT 0,
    imported_by VARCHAR(64) NOT NULL DEFAULT '',
    imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_id),
    UNIQUE KEY uk_inventory_product_report_date (report_date),
    KEY idx_inventory_product_period (period_start, period_end)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='进销商品看板导入批次';

CREATE TABLE IF NOT EXISTS inventory_product_dashboard_item (
    id BIGINT NOT NULL AUTO_INCREMENT,
    batch_id VARCHAR(32) NOT NULL,
    source_row INT NOT NULL,
    image_url TEXT,
    category VARCHAR(128) NOT NULL DEFAULT '',
    style_code VARCHAR(128) NOT NULL DEFAULT '',
    product_code VARCHAR(128) NOT NULL,
    product_name TEXT NOT NULL,
    color_spec VARCHAR(255) NOT NULL DEFAULT '',
    brand VARCHAR(128) NOT NULL DEFAULT '',
    opening_quantity DECIMAL(18,2) NOT NULL DEFAULT 0,
    closing_quantity DECIMAL(18,2) NOT NULL DEFAULT 0,
    imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_inventory_product_source (batch_id, source_row),
    KEY idx_inventory_product_code (product_code),
    KEY idx_inventory_product_category (category),
    KEY idx_inventory_product_brand (brand)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='进销商品看板明细快照';
