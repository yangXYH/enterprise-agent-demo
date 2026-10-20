-- 移除电商中台看板「设计部」模块及其测试数据（设计任务 / 素材库 / 页面研发）。
-- 这些数据均为种子测试数据，整体下线删除；可重复执行。
-- 注意：ecom_* 各表通过 page_key / route 逻辑关联，无外键约束，按业务 key 删除即可。

-- 1) 删除「设计部」顶级菜单及其子菜单（设计任务 / 素材库 / 页面研发）
DELETE FROM ecom_menu
WHERE label = '设计部'
   OR route IN ('design', 'design-assets', 'design-dev');

-- 2) 删除「设计部」页面 KPI
DELETE FROM ecom_kpi
WHERE page_key = 'design';

-- 3) 删除「设计部」页面 Tab
DELETE FROM ecom_table_tab
WHERE page_key = 'design';

-- 4) 删除「设计部」页面列定义
DELETE FROM ecom_table_col
WHERE page_key = 'design';

-- 5) 删除「设计部」页面测试数据行
DELETE FROM ecom_table_row
WHERE page_key = 'design';

-- 6) 删除人员花名册 mock 中的「设计部」员工行（陈曦·设计部）
DELETE FROM ecom_table_row
WHERE page_key = 'hr'
  AND tab_key = 'roster'
  AND meta_json LIKE '%设计部%';
