-- 删除已下线的登录会话状态和登录审计功能表。
-- 先删除事件表，再删除会话表，便于兼容可能存在的关联约束。

SET NAMES utf8mb4;

DROP TABLE IF EXISTS sys_auth_event;
DROP TABLE IF EXISTS sys_auth_session;
