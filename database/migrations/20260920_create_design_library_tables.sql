-- 设计部资料库：文字与图片引用入 MySQL，图片文件仍存放在 data/design-data/images。
-- 该脚本可重复执行；服务首次访问设计资料时也会自动确保此表存在。
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS design_library_item (
    id VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    item_type VARCHAR(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    title VARCHAR(255) NOT NULL DEFAULT '',
    body LONGTEXT NOT NULL,
    product VARCHAR(64) NOT NULL DEFAULT '',
    scene VARCHAR(64) NOT NULL DEFAULT '',
    category VARCHAR(64) NOT NULL DEFAULT '',
    images_json LONGTEXT NULL,
    original_url VARCHAR(1024) NULL,
    generated_url VARCHAR(1024) NULL,
    source VARCHAR(512) NOT NULL DEFAULT '手动新增',
    sort_order INT NOT NULL DEFAULT 0,
    created_by VARCHAR(191) NOT NULL DEFAULT '',
    updated_by VARCHAR(191) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_design_item_type (item_type, sort_order, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='设计部资料库';
