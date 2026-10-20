-- 移除电商中台看板「产品部」模块及其测试数据（产品列表 / 上新管理 / 详情优化）。
-- 可重复执行；ecom_* 页面数据通过 page_key / route 关联，无外键依赖。

-- 1) 删除「产品部」顶级菜单及其子菜单
DELETE FROM ecom_menu
WHERE label = '产品部'
   OR route IN ('product', 'product-new', 'product-detail');

-- 2) 删除「产品部」页面 KPI、Tab、列定义和测试数据
DELETE FROM ecom_kpi
WHERE page_key = 'product';

DELETE FROM ecom_table_tab
WHERE page_key = 'product';

DELETE FROM ecom_table_col
WHERE page_key = 'product';

DELETE FROM ecom_table_row
WHERE page_key = 'product';

-- 3) 删除人员花名册 mock 中的「产品部」员工行
DELETE FROM ecom_table_row
WHERE page_key = 'hr'
  AND tab_key = 'roster'
  AND meta_json LIKE '%产品部%';
