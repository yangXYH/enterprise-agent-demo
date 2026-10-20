-- 产品质检报告：共享元数据 + 可配置的页面访问权限。
-- PDF 原件来自 data/product-quality-reports/files 或 uploads/product-quality-reports。
-- 首次访问时后端从 catalog.json 幂等导入，不覆盖现有报告。
CREATE TABLE IF NOT EXISTS product_quality_report (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    models_json TEXT NOT NULL,
    categories_json TEXT NOT NULL,
    sources_json TEXT NOT NULL,
    search_text TEXT NOT NULL,
    report_number VARCHAR(100) NOT NULL,
    report_date VARCHAR(10) NOT NULL,
    page_count INT NOT NULL,
    file_size INT NOT NULL,
    created_by VARCHAR(191) NOT NULL,
    created_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO sys_page_permission (page_key, roles, updated_at)
VALUES ('product-quality-reports', '["*"]', NOW());
