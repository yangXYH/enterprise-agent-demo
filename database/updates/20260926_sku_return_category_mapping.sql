-- SKU Return category mapping update for an existing deployment.
-- MySQL 5.5.6+ (utf8mb4 support required). Clones the active immutable run, remaps its source categories,
-- rebuilds the aggregate, and atomically switches the active run pointer.
-- The previous run is retained for audit/history. Do not run while imports or
-- brand-rule updates are in progress. If mappings are already applied, this
-- script reports that no work is needed and does not create another run.

DROP PROCEDURE IF EXISTS apply_sku_return_category_mapping_20260926;
DELIMITER //
CREATE PROCEDURE apply_sku_return_category_mapping_20260926()
main: BEGIN
  DECLARE v_source_run_id CHAR(32);
  DECLARE v_new_run_id CHAR(32);
  DECLARE v_rule_version INT;
  DECLARE v_pending_units INT DEFAULT 0;
  DECLARE v_expected_facts INT DEFAULT 0;
  DECLARE v_copied_facts INT DEFAULT 0;
  DECLARE v_expected_included INT DEFAULT 0;
  DECLARE v_aggregated_facts INT DEFAULT 0;
  DECLARE v_manifest CHAR(64);
  DECLARE v_report_json LONGTEXT;
  DECLARE v_unknown_category_items LONGTEXT;
  DECLARE v_report_start INT DEFAULT 0;
  DECLARE v_report_end INT DEFAULT 0;
  DECLARE v_old_group_concat_max_len BIGINT UNSIGNED DEFAULT NULL;

  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    DROP TEMPORARY TABLE IF EXISTS tmp_sku_return_source_map_20260926;
    IF v_old_group_concat_max_len IS NOT NULL THEN
      SET SESSION group_concat_max_len = v_old_group_concat_max_len;
    END IF;
    RESIGNAL;
  END;

  START TRANSACTION;
  SET v_old_group_concat_max_len = @@SESSION.group_concat_max_len;
  SET SESSION group_concat_max_len = 65535;
  SELECT active_run_id, rule_version
    INTO v_source_run_id, v_rule_version
    FROM sku_return_state
   WHERE id = 1
   FOR UPDATE;

  IF v_source_run_id IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'SKU退货数据没有活动版本';
  END IF;

  SELECT COUNT(*) INTO v_pending_units
    FROM sku_return_source_unit
   WHERE run_id = v_source_run_id
     AND ((entity = 'B2B' AND category = '未分类'
           AND relative_path LIKE '%/B2B/%' AND relative_path LIKE '% B2B 2026-%')
       OR (entity = '示例科技' AND category = '未分类'
           AND relative_path LIKE '%电脑事业%')
       OR (entity = '示例户外' AND category <> '示例户外箱包'));

  IF v_pending_units = 0 THEN
    COMMIT;
    SELECT '类别映射已应用，无需更新' AS message, v_source_run_id AS active_run_id;
    LEAVE main;
  END IF;

  SET v_new_run_id = REPLACE(UUID(), '-', '');

  CREATE TEMPORARY TABLE tmp_sku_return_source_map_20260926 (
    old_source_unit_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    new_source_unit_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    PRIMARY KEY (old_source_unit_id),
    UNIQUE KEY uq_tmp_sku_return_new_source (new_source_unit_id)
  ) ENGINE=InnoDB;

  INSERT INTO tmp_sku_return_source_map_20260926 (old_source_unit_id, new_source_unit_id)
  SELECT id, REPLACE(UUID(), '-', '')
    FROM sku_return_source_unit
   WHERE run_id = v_source_run_id;

  SELECT manifest_sha256, target_rows, included_rows
    INTO v_manifest, v_expected_facts, v_expected_included
    FROM sku_return_import_run
   WHERE id = v_source_run_id AND status = 'complete';

  IF v_manifest IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '活动导入版本不存在或尚未完成';
  END IF;

  INSERT INTO sku_return_import_run (
    id, manifest_sha256, rule_version, status, started_at, source_units, scanned_rows,
    target_rows, isolated_rows, duplicate_rows, included_rows, report_json
  )
  SELECT v_new_run_id,
         SHA2(CONCAT(manifest_sha256, ':sku-category-mapping-20260926'), 256),
         rule_version, 'building', CURRENT_TIMESTAMP, source_units, scanned_rows,
         target_rows, isolated_rows, duplicate_rows, included_rows, report_json
    FROM sku_return_import_run
   WHERE id = v_source_run_id;

  INSERT INTO sku_return_source_unit (
    id, run_id, relative_path, path_sha256, file_sha256, sheet_name,
    period, entity, category, scanned_rows, target_rows, included_rows
  )
  SELECT m.new_source_unit_id, v_new_run_id, u.relative_path, u.path_sha256,
         u.file_sha256, u.sheet_name, u.period, u.entity,
         CASE
           WHEN u.entity = 'B2B' AND u.category = '未分类'
             AND u.relative_path LIKE '%/B2B/%'
             AND u.relative_path LIKE '% B2B 2026-%' THEN '喜来登'
           WHEN u.entity = '示例科技' AND u.category = '未分类'
             AND u.relative_path LIKE '%电脑事业%' THEN '电脑事业'
           WHEN u.entity = '示例户外' THEN '示例户外箱包'
           ELSE u.category
         END,
         u.scanned_rows, u.target_rows, u.included_rows
    FROM sku_return_source_unit u
    JOIN tmp_sku_return_source_map_20260926 m
      ON m.old_source_unit_id = u.id
   WHERE u.run_id = v_source_run_id;

  INSERT INTO sku_return_fact (
    run_id, source_unit_id, source_row, document_type, supplier_name,
    supplier_raw, sku_code, sku_name, sku_name_raw, brand, brand_rule_id,
    raw_quantity, sales_quantity, return_in_quantity, after_sales_quantity,
    technical_document_id, technical_document_no, dedupe_sha256, included,
    excluded_reason, duplicate_of_source_unit_id, duplicate_of_row
  )
  SELECT v_new_run_id, m.new_source_unit_id, f.source_row, f.document_type,
         f.supplier_name, f.supplier_raw, f.sku_code, f.sku_name,
         f.sku_name_raw, f.brand, f.brand_rule_id, f.raw_quantity,
         f.sales_quantity, f.return_in_quantity, f.after_sales_quantity,
         f.technical_document_id, f.technical_document_no, f.dedupe_sha256,
         f.included, f.excluded_reason, d.new_source_unit_id, f.duplicate_of_row
    FROM sku_return_fact f
    JOIN tmp_sku_return_source_map_20260926 m
      ON m.old_source_unit_id = f.source_unit_id
    LEFT JOIN tmp_sku_return_source_map_20260926 d
      ON d.old_source_unit_id = f.duplicate_of_source_unit_id
   WHERE f.run_id = v_source_run_id;

  SELECT COUNT(*) INTO v_copied_facts
    FROM sku_return_fact WHERE run_id = v_new_run_id;
  IF v_copied_facts <> v_expected_facts THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '事实行复制数量与源版本不一致';
  END IF;

  INSERT INTO sku_return_aggregate (
    run_id, period, entity, category, supplier_name, sku_code, sku_name,
    brand, sales_quantity, return_in_quantity, after_sales_quantity, fact_count
  )
  SELECT f.run_id, u.period, u.entity, u.category, f.supplier_name,
         f.sku_code, f.sku_name, f.brand, SUM(f.sales_quantity),
         SUM(f.return_in_quantity), SUM(f.after_sales_quantity), COUNT(*)
    FROM sku_return_fact f
    JOIN sku_return_source_unit u ON u.id = f.source_unit_id
   WHERE f.run_id = v_new_run_id AND f.included = 1
   GROUP BY f.run_id, u.period, u.entity, u.category, f.supplier_name,
            f.sku_code, f.sku_name, f.brand;

  SELECT COALESCE(SUM(fact_count), 0) INTO v_aggregated_facts
    FROM sku_return_aggregate WHERE run_id = v_new_run_id;
  IF v_aggregated_facts <> v_expected_included THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '聚合行数与源版本计入事实数不一致';
  END IF;

  IF EXISTS (
    SELECT 1 FROM sku_return_source_unit
     WHERE run_id = v_new_run_id AND category = '未分类' AND entity <> '示例户外'
       AND relative_path REGEXP '[[:cntrl:]]'
  ) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '未分类来源路径含控制字符，无法安全更新质量报告';
  END IF;

  SELECT GROUP_CONCAT(
           CONCAT(
             '{"path":"',
             REPLACE(
               REPLACE(relative_path, CONVERT(0x5C USING utf8mb4),
                       CONCAT(CONVERT(0x5C USING utf8mb4), CONVERT(0x5C USING utf8mb4))),
               CONVERT(0x22 USING utf8mb4),
               CONCAT(CONVERT(0x5C USING utf8mb4), CONVERT(0x22 USING utf8mb4))
             ),
             '","token":null}'
           )
           SEPARATOR ','
         )
    INTO v_unknown_category_items
    FROM sku_return_source_unit
   WHERE run_id = v_new_run_id AND category = '未分类' AND entity <> '示例户外';

  SELECT report_json INTO v_report_json
    FROM sku_return_import_run WHERE id = v_source_run_id;
  SET v_report_start = LOCATE('"unknown_categories": [', v_report_json);
  SET v_report_end = LOCATE('], "new_category_combinations"', v_report_json);
  IF v_report_start = 0 OR v_report_end = 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '导入质量报告格式不符合预期，已取消发布';
  END IF;
  SET v_report_json = CONCAT(
    SUBSTRING(v_report_json, 1, v_report_start - 1),
    '"unknown_categories": [', COALESCE(v_unknown_category_items, ''), ']',
    SUBSTRING(v_report_json, v_report_end + 1)
  );

  UPDATE sku_return_import_run r
     SET report_json = v_report_json,
         status = 'complete', completed_at = CURRENT_TIMESTAMP
   WHERE r.id = v_new_run_id;

  UPDATE sku_return_state
     SET active_run_id = v_new_run_id
   WHERE id = 1 AND active_run_id = v_source_run_id;
  IF ROW_COUNT() <> 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = '活动版本已变化，已取消发布';
  END IF;

  COMMIT;
  DROP TEMPORARY TABLE IF EXISTS tmp_sku_return_source_map_20260926;
  SET SESSION group_concat_max_len = v_old_group_concat_max_len;

  SELECT v_source_run_id AS previous_run_id, v_new_run_id AS active_run_id,
         v_pending_units AS remapped_source_units,
         v_copied_facts AS copied_fact_rows,
         v_aggregated_facts AS aggregated_fact_rows;
  SELECT a.entity, a.category, COUNT(DISTINCT CONCAT(a.sku_code, '|', a.sku_name)) AS sku_combos,
         SUM(a.sales_quantity) AS sales_quantity,
         SUM(a.return_in_quantity + a.after_sales_quantity) AS return_quantity
    FROM sku_return_aggregate a
   WHERE a.run_id = v_new_run_id
     AND a.category IN ('喜来登', '电脑事业', '示例户外箱包')
   GROUP BY a.entity, a.category
   ORDER BY a.entity, a.category;
END //
DELIMITER ;

CALL apply_sku_return_category_mapping_20260926();
DROP PROCEDURE IF EXISTS apply_sku_return_category_mapping_20260926;
