-- ============================================================
-- 服务器缺失表建表脚本（结构/表/字段注释 与本地环境完全一致）
-- 生成时间: 2026-08-26
-- 共 11 张表：10 张人力行政管理表 + 1 张页面权限配置表
--
-- 运行方式：
--   方式一：mysql -u<用户名> -p<密码> enterprise_agent_db < server_missing_tables.sql
--   方式二：登录 MySQL 后 USE enterprise_agent_db; SOURCE 本文件;
--   或用 Navicat / DBeaver 直接打开本文件执行
--
-- 安全说明：全部 CREATE TABLE IF NOT EXISTS，重复执行不会报错、
--          不会覆盖已存在表；本脚本只建表结构，不写入任何数据。
-- 注释说明：每张表与每个字段均带中文注释，便于后续维护。
-- ============================================================

-- ========== hr_employee（员工花名册主表（在职与离职员工的完整档案）） ==========
CREATE TABLE IF NOT EXISTS `hr_employee` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键自增ID',
  `source_key` varchar(100) COLLATE utf8mb4_general_ci NOT NULL COMMENT '来源去重键（Excel 行来源唯一标识，幂等导入用）',
  `emp_no` varchar(50) COLLATE utf8mb4_general_ci NOT NULL COMMENT '工号',
  `name` varchar(50) COLLATE utf8mb4_general_ci NOT NULL COMMENT '姓名',
  `company` varchar(100) COLLATE utf8mb4_general_ci NOT NULL COMMENT '所属公司',
  `contract_type` varchar(50) COLLATE utf8mb4_general_ci NOT NULL COMMENT '合同类型',
  `dept_name` varchar(100) COLLATE utf8mb4_general_ci NOT NULL COMMENT '部门',
  `group_name` varchar(100) COLLATE utf8mb4_general_ci NOT NULL COMMENT '组别',
  `position` varchar(100) COLLATE utf8mb4_general_ci NOT NULL COMMENT '岗位',
  `hire_date` date DEFAULT NULL COMMENT '入职日期',
  `regular_date` date DEFAULT NULL COMMENT '转正日期',
  `seniority_text` varchar(50) COLLATE utf8mb4_general_ci NOT NULL COMMENT '司龄（文本描述）',
  `id_card` varchar(30) COLLATE utf8mb4_general_ci NOT NULL COMMENT '身份证号（敏感字段，脱敏显示）',
  `id_card_hash` varchar(64) COLLATE utf8mb4_general_ci NOT NULL COMMENT '身份证号哈希（脱敏后唯一标识）',
  `id_card_expiry` date DEFAULT NULL COMMENT '身份证有效期',
  `birthday` date DEFAULT NULL COMMENT '出生日期',
  `gender` varchar(10) COLLATE utf8mb4_general_ci NOT NULL COMMENT '性别',
  `nationality` varchar(20) COLLATE utf8mb4_general_ci NOT NULL COMMENT '民族',
  `marital_status` varchar(20) COLLATE utf8mb4_general_ci NOT NULL COMMENT '婚姻状况',
  `political_status` varchar(20) COLLATE utf8mb4_general_ci NOT NULL COMMENT '政治面貌',
  `phone` varchar(30) COLLATE utf8mb4_general_ci NOT NULL COMMENT '联系电话（敏感字段，脱敏显示）',
  `email` varchar(100) COLLATE utf8mb4_general_ci NOT NULL COMMENT '邮箱',
  `education` varchar(20) COLLATE utf8mb4_general_ci NOT NULL COMMENT '学历',
  `is_fulltime` varchar(10) COLLATE utf8mb4_general_ci NOT NULL COMMENT '是否全日制',
  `school` varchar(100) COLLATE utf8mb4_general_ci NOT NULL COMMENT '毕业院校',
  `major` varchar(100) COLLATE utf8mb4_general_ci NOT NULL COMMENT '专业',
  `cert_no` varchar(100) COLLATE utf8mb4_general_ci NOT NULL COMMENT '学历证书编号',
  `grad_date` date DEFAULT NULL COMMENT '毕业日期',
  `tech_title` varchar(100) COLLATE utf8mb4_general_ci NOT NULL COMMENT '职称',
  `hukou_type` varchar(50) COLLATE utf8mb4_general_ci NOT NULL COMMENT '户口性质',
  `native_place` varchar(100) COLLATE utf8mb4_general_ci NOT NULL COMMENT '籍贯',
  `hukou_address` varchar(255) COLLATE utf8mb4_general_ci NOT NULL COMMENT '户籍地址（敏感字段，脱敏显示）',
  `id_address` varchar(255) COLLATE utf8mb4_general_ci NOT NULL COMMENT '身份证地址（敏感字段，脱敏显示）',
  `current_address` varchar(255) COLLATE utf8mb4_general_ci NOT NULL COMMENT '现居住地址（敏感字段，脱敏显示）',
  `bank_card` varchar(50) COLLATE utf8mb4_general_ci NOT NULL COMMENT '银行卡号（敏感字段，脱敏显示）',
  `bank_name` varchar(100) COLLATE utf8mb4_general_ci NOT NULL COMMENT '开户行',
  `has_social_insurance` varchar(10) COLLATE utf8mb4_general_ci NOT NULL COMMENT '是否参加社会保险',
  `has_housing_fund` varchar(10) COLLATE utf8mb4_general_ci NOT NULL COMMENT '是否缴存住房公积金',
  `fund_ratio` varchar(50) COLLATE utf8mb4_general_ci NOT NULL COMMENT '公积金缴存比例',
  `remark` text COLLATE utf8mb4_general_ci COMMENT '备注',
  `status` varchar(20) COLLATE utf8mb4_general_ci NOT NULL COMMENT '在职状态（active=在职 / resigned=离职）',
  `source_sheet` varchar(50) COLLATE utf8mb4_general_ci NOT NULL COMMENT '来源工作表名',
  `source_row` int DEFAULT NULL COMMENT '来源 Excel 行号',
  `created_at` datetime DEFAULT NULL COMMENT '创建时间',
  `updated_at` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=70 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='员工花名册主表（在职与离职员工的完整档案）'
;

-- ========== hr_contract（员工劳动合同表） ==========
CREATE TABLE IF NOT EXISTS `hr_contract` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键自增ID',
  `employee_id` int NOT NULL COMMENT '关联员工ID（hr_employee.id）',
  `contract_type` varchar(50) COLLATE utf8mb4_general_ci NOT NULL COMMENT '合同类型',
  `seq_no` int NOT NULL COMMENT '合同序号',
  `start_date` date DEFAULT NULL COMMENT '合同开始日期',
  `end_date` date DEFAULT NULL COMMENT '合同结束日期',
  `note` varchar(255) COLLATE utf8mb4_general_ci NOT NULL COMMENT '合同备注',
  `source_key` varchar(100) COLLATE utf8mb4_general_ci NOT NULL COMMENT '来源去重键（Excel 行来源唯一标识，幂等导入用）',
  `created_at` datetime DEFAULT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=247 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='员工劳动合同表'
;

-- ========== hr_emergency_contact（员工紧急联系人表） ==========
CREATE TABLE IF NOT EXISTS `hr_emergency_contact` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键自增ID',
  `employee_id` int NOT NULL COMMENT '关联员工ID（hr_employee.id）',
  `contact_name` varchar(50) COLLATE utf8mb4_general_ci NOT NULL COMMENT '联系人姓名',
  `relation` varchar(20) COLLATE utf8mb4_general_ci NOT NULL COMMENT '与本人关系',
  `phone` varchar(30) COLLATE utf8mb4_general_ci NOT NULL COMMENT '联系电话（敏感字段，脱敏显示）',
  `sort_no` int NOT NULL COMMENT '排序号（第几位联系人）',
  `created_at` datetime DEFAULT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=193 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='员工紧急联系人表'
;

-- ========== hr_resign（员工离职信息表） ==========
CREATE TABLE IF NOT EXISTS `hr_resign` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键自增ID',
  `source_key` varchar(100) COLLATE utf8mb4_general_ci NOT NULL COMMENT '来源去重键（Excel 行来源唯一标识，幂等导入用）',
  `name` varchar(50) COLLATE utf8mb4_general_ci NOT NULL COMMENT '姓名',
  `company` varchar(100) COLLATE utf8mb4_general_ci NOT NULL COMMENT '所属公司',
  `contract_type` varchar(50) COLLATE utf8mb4_general_ci NOT NULL COMMENT '合同类型',
  `dept_name` varchar(100) COLLATE utf8mb4_general_ci NOT NULL COMMENT '部门',
  `group_name` varchar(100) COLLATE utf8mb4_general_ci NOT NULL COMMENT '组别',
  `position` varchar(100) COLLATE utf8mb4_general_ci NOT NULL COMMENT '岗位',
  `hire_date` date DEFAULT NULL COMMENT '入职日期',
  `regular_date` date DEFAULT NULL COMMENT '转正日期',
  `resign_date` date DEFAULT NULL COMMENT '离职日期',
  `resign_reason` varchar(255) COLLATE utf8mb4_general_ci NOT NULL COMMENT '离职原因',
  `id_card` varchar(30) COLLATE utf8mb4_general_ci NOT NULL COMMENT '身份证号（敏感字段，脱敏显示）',
  `id_card_hash` varchar(64) COLLATE utf8mb4_general_ci NOT NULL COMMENT '身份证号哈希（脱敏后唯一标识）',
  `phone` varchar(30) COLLATE utf8mb4_general_ci NOT NULL COMMENT '联系电话（敏感字段，脱敏显示）',
  `education` varchar(20) COLLATE utf8mb4_general_ci NOT NULL COMMENT '学历',
  `source_sheet` varchar(50) COLLATE utf8mb4_general_ci NOT NULL COMMENT '来源工作表名',
  `source_row` int DEFAULT NULL COMMENT '来源 Excel 行号',
  `created_at` datetime DEFAULT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=281 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='员工离职信息表'
;

-- ========== hr_import_log（人力资源模块 Excel 导入日志表） ==========
CREATE TABLE IF NOT EXISTS `hr_import_log` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键自增ID',
  `import_type` varchar(50) COLLATE utf8mb4_general_ci NOT NULL COMMENT '导入类型（roster/resign/attendance）',
  `filename` varchar(255) COLLATE utf8mb4_general_ci NOT NULL COMMENT '导入文件名',
  `sheet_name` varchar(50) COLLATE utf8mb4_general_ci NOT NULL COMMENT '工作表名',
  `rows_read` int NOT NULL COMMENT '读取行数',
  `inserted` int NOT NULL COMMENT '新增行数',
  `updated` int NOT NULL COMMENT '更新行数',
  `skipped` int NOT NULL COMMENT '跳过行数',
  `errors_json` text COLLATE utf8mb4_general_ci COMMENT '错误明细（JSON 数组）',
  `operator` varchar(50) COLLATE utf8mb4_general_ci NOT NULL COMMENT '操作人',
  `created_at` datetime DEFAULT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='人力资源模块 Excel 导入日志表'
;

-- ========== hr_attendance_sum（考勤汇总表（按月按人统计出勤/迟到/请假/加班等）） ==========
CREATE TABLE IF NOT EXISTS `hr_attendance_sum` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键自增ID',
  `employee_id` int DEFAULT NULL COMMENT '关联员工ID（hr_employee.id）',
  `month` varchar(7) COLLATE utf8mb4_general_ci NOT NULL COMMENT '统计月份（YYYY-MM）',
  `name` varchar(50) COLLATE utf8mb4_general_ci NOT NULL COMMENT '姓名',
  `dept_name` varchar(100) COLLATE utf8mb4_general_ci NOT NULL COMMENT '部门',
  `work_days` decimal(6,1) NOT NULL COMMENT '应出勤天数',
  `actual_days` decimal(6,1) NOT NULL COMMENT '实际出勤天数',
  `late_count` int NOT NULL COMMENT '迟到次数',
  `early_count` int NOT NULL COMMENT '早退次数',
  `absent_days` decimal(6,1) NOT NULL COMMENT '缺勤天数',
  `leave_days` decimal(6,1) NOT NULL COMMENT '请假天数',
  `overtime_hours` decimal(6,1) NOT NULL COMMENT '加班时长（小时）',
  `abnormal_count` int NOT NULL COMMENT '考勤异常次数',
  `remark` varchar(255) COLLATE utf8mb4_general_ci NOT NULL COMMENT '备注',
  `source_key` varchar(100) COLLATE utf8mb4_general_ci NOT NULL COMMENT '来源去重键（Excel 行来源唯一标识，幂等导入用）',
  `created_at` datetime DEFAULT NULL COMMENT '创建时间',
  `updated_at` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='考勤汇总表（按月按人统计出勤/迟到/请假/加班等）'
;

-- ========== sys_page_permission（人力资源页面查询权限配置表（page_key -> 可见角色）） ==========
CREATE TABLE IF NOT EXISTS `sys_page_permission` (
  `page_key` varchar(64) COLLATE utf8mb4_general_ci NOT NULL COMMENT '页面标识（如 hr-roster / hr-recruit）',
  `roles` text COLLATE utf8mb4_general_ci NOT NULL COMMENT '可见角色（JSON 数组，如 ["admin","hr"]）',
  `updated_at` datetime DEFAULT NULL COMMENT '更新时间',
  PRIMARY KEY (`page_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='人力资源页面查询权限配置表（page_key -> 可见角色）'
;
