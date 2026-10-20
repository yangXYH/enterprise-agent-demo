-- 极简登录历史：每次登录成功新增一行，仅保存登录账号和登录时间。

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS sys_user_login_record (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    username VARCHAR(50) NOT NULL COMMENT '登录账号，对应sys_user.username',
    login_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '登录成功时间',
    PRIMARY KEY (id),
    KEY idx_sys_user_login_record_username_time (username, login_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户登录成功记录表';
