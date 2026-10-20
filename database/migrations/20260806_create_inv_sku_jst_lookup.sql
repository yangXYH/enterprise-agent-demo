-- SKU to Jushuitan inventory lookup code mapping.
-- Additive and idempotent. Run against enterprise_agent_db.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS inv_sku_jst_lookup (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Primary key',
    sku_code VARCHAR(64) NOT NULL COMMENT 'Internal SKU code',
    lookup_code VARCHAR(128) NOT NULL COMMENT 'Jushuitan inventory query code',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Created at',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Updated at',
    PRIMARY KEY (id),
    UNIQUE KEY uk_inv_sku_jst_lookup_sku (sku_code),
    KEY idx_inv_sku_jst_lookup_code (lookup_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='SKU to Jushuitan lookup code mapping';
