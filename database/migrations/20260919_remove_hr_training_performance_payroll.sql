-- 移除已下线的人力资源子模块：培训管理、绩效看板、工资台账。
-- 可重复执行；先删培训记录，再删培训主表，避免历史库存在依赖时失败。

DROP TABLE IF EXISTS hr_training_record;
DROP TABLE IF EXISTS hr_training;
DROP TABLE IF EXISTS hr_performance;
DROP TABLE IF EXISTS hr_payroll;

DELETE FROM sys_page_permission
WHERE page_key IN ('hr-training', 'hr-performance', 'hr-payroll');

DELETE FROM ecom_menu
WHERE route IN ('hr-training', 'hr-performance', 'hr-payroll');
