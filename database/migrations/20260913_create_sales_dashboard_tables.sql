CREATE TABLE IF NOT EXISTS sales_dashboard_import_batch (
    batch_id VARCHAR(32) NOT NULL,
    source_name VARCHAR(255) NOT NULL DEFAULT '',
    row_count INT NOT NULL DEFAULT 0,
    imported_by VARCHAR(64) NOT NULL DEFAULT '',
    imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='销售数据看板导入批次';

CREATE TABLE IF NOT EXISTS sales_dashboard_item (
    id BIGINT NOT NULL AUTO_INCREMENT,
    batch_id VARCHAR(32) NOT NULL,
    source_row INT NOT NULL,
    image_url TEXT,
    product_code VARCHAR(128) NOT NULL,
    product_name TEXT NOT NULL,
    category VARCHAR(128) NOT NULL DEFAULT '',
    brand VARCHAR(128) NOT NULL DEFAULT '',
    sales_quantity DECIMAL(18,2) NOT NULL DEFAULT 0,
    shipped_quantity DECIMAL(18,2) NOT NULL DEFAULT 0,
    returned_quantity DECIMAL(18,2) NOT NULL DEFAULT 0,
    imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_sales_dashboard_source (batch_id, source_row),
    KEY idx_sales_dashboard_code (product_code),
    KEY idx_sales_dashboard_category (category),
    KEY idx_sales_dashboard_brand (brand)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='销售数据看板当前快照';
