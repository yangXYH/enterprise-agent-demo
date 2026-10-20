-- 员工积分：花名册 hr_employee 为人员主档；积分流水只追加，不因规则修改回写历史。
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS points_rule (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    points INT NOT NULL,
    description VARCHAR(500) NOT NULL DEFAULT '',
    is_active TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    KEY idx_points_rule_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS points_record (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    employee_id BIGINT NOT NULL,
    employee_name VARCHAR(100) NOT NULL,
    rule_id BIGINT NOT NULL,
    rule_name VARCHAR(100) NOT NULL,
    points INT NOT NULL,
    note TEXT NOT NULL,
    operator VARCHAR(100) NOT NULL,
    created_at DATETIME NOT NULL,
    KEY idx_points_record_employee_time (employee_id, created_at),
    KEY idx_points_record_time (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
