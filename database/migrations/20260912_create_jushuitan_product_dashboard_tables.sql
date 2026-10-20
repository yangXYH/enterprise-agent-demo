CREATE TABLE IF NOT EXISTS jst_product_import_batch (
    batch_id VARCHAR(32) NOT NULL,
    source_name VARCHAR(255) NOT NULL DEFAULT '',
    row_count INT NOT NULL DEFAULT 0,
    image_count INT NOT NULL DEFAULT 0,
    imported_by VARCHAR(64) NOT NULL DEFAULT '',
    imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='聚水潭商品资料导入批次';

CREATE TABLE IF NOT EXISTS jst_product_stock (
    id BIGINT NOT NULL AUTO_INCREMENT,
    batch_id VARCHAR(32) NOT NULL,
    source_row INT NOT NULL,
    style_code VARCHAR(128) NOT NULL DEFAULT '',
    product_code VARCHAR(128) NOT NULL,
    product_name TEXT NOT NULL,
    brand VARCHAR(128) NOT NULL DEFAULT '',
    color_spec VARCHAR(255) NOT NULL DEFAULT '',
    color VARCHAR(128) NOT NULL DEFAULT '',
    spec VARCHAR(255) NOT NULL DEFAULT '',
    actual_stock DECIMAL(18,2) NOT NULL DEFAULT 0,
    order_occupied DECIMAL(18,2) NOT NULL DEFAULT 0,
    available_stock DECIMAL(18,2) NOT NULL DEFAULT 0,
    stock_updated_at DATETIME NULL,
    image_key VARCHAR(96) NOT NULL DEFAULT '',
    imported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_jst_product_code (product_code),
    KEY idx_jst_product_brand (brand),
    KEY idx_jst_product_available (available_stock),
    KEY idx_jst_product_updated (stock_updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='聚水潭商品库存看板当前快照';
