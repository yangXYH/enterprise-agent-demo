-- 人力行政模块数据库迁移脚本（2026-08-25）
-- 作用：创建仍在使用的 hr_* 表
--   1. hr_employee            员工主档（含单一值扩展字段：学历/户口/住址/银行卡/社保公积金）
--   2. hr_emergency_contact   紧急联系人（一对多）
--   3. hr_contract            劳动合同与 1~3 次续签（一对多，到期提醒数据源）
--   4. hr_resign              离职记录（花名册离职表快照，含离职原因）
--   5. hr_job_requisition     招聘需求台账（部门提需求 → HR 发布）
--   6. hr_candidate           招聘候选人管道（简历池→初面→复试→录用→到岗→入职）
--   7. hr_attendance_sum      月度考勤汇总（考勤机/钉钉/企微导出导入）
--   8. hr_import_log         导入日志（幂等与错误报告）
-- 说明：
--   - 只新增表，不删除/清空/修改已有业务表；CREATE TABLE IF NOT EXISTS 可重复执行。
--   - 幂等设计：员工/离职/考勤等表均有唯一键，重导同数据给出 新增/更新/跳过 报告。
--   - 敏感字段（身份证、银行卡、住址）落库明文但受权限控制：仅 admin/hr 角色可见，
--     其余角色一律脱敏（前端脱敏 + 列表/导出默认脱敏列）。
--   - 需要在 enterprise_agent_db 对应的 MySQL 数据库中执行。

SET NAMES utf8mb4;

-- 1. 员工主档
CREATE TABLE IF NOT EXISTS hr_employee (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '员工主键ID',
    source_key VARCHAR(100) NOT NULL DEFAULT '' COMMENT '来源幂等键（sheet:序号 或 manual:xxx），重导去重依据',
    emp_no VARCHAR(50) NOT NULL DEFAULT '' COMMENT '工号（花名册无工号，暂用序号占位，可补录）',
    name VARCHAR(50) NOT NULL COMMENT '姓名',
    company VARCHAR(100) NOT NULL DEFAULT '示例科技' COMMENT '所属公司',
    contract_type VARCHAR(50) NOT NULL DEFAULT '' COMMENT '合同类型：劳动合同/劳务合同/临时工',
    dept_name VARCHAR(100) NOT NULL DEFAULT '' COMMENT '部门（当前）',
    group_name VARCHAR(100) NOT NULL DEFAULT '' COMMENT '组别（当前）',
    position VARCHAR(100) NOT NULL DEFAULT '' COMMENT '岗位',
    hire_date DATE NULL COMMENT '入职日期',
    regular_date DATE NULL COMMENT '转正日期',
    seniority_text VARCHAR(50) NOT NULL DEFAULT '' COMMENT '工龄原文（文本）',
    id_card VARCHAR(30) NOT NULL DEFAULT '' COMMENT '身份证号（敏感，仅 admin/hr 可见）',
    id_card_hash VARCHAR(64) NOT NULL DEFAULT '' COMMENT '身份证 SHA-256 散列（查重用）',
    id_card_expiry DATE NULL COMMENT '身份证有效期至',
    birthday DATE NULL COMMENT '出生日期',
    gender VARCHAR(10) NOT NULL DEFAULT '' COMMENT '性别',
    nationality VARCHAR(20) NOT NULL DEFAULT '' COMMENT '民族',
    marital_status VARCHAR(20) NOT NULL DEFAULT '' COMMENT '婚姻状态',
    political_status VARCHAR(20) NOT NULL DEFAULT '' COMMENT '政治面貌',
    phone VARCHAR(30) NOT NULL DEFAULT '' COMMENT '电话（列表脱敏）',
    email VARCHAR(100) NOT NULL DEFAULT '' COMMENT '邮箱',
    education VARCHAR(20) NOT NULL DEFAULT '' COMMENT '学历：大专/本科/高中/中专/初中/本科在籍',
    is_fulltime VARCHAR(10) NOT NULL DEFAULT '' COMMENT '是否统招：是/否',
    school VARCHAR(100) NOT NULL DEFAULT '' COMMENT '学校',
    major VARCHAR(100) NOT NULL DEFAULT '' COMMENT '专业',
    cert_no VARCHAR(100) NOT NULL DEFAULT '' COMMENT '证书编号',
    grad_date DATE NULL COMMENT '毕业时间',
    tech_title VARCHAR(100) NOT NULL DEFAULT '' COMMENT '技术职称',
    hukou_type VARCHAR(50) NOT NULL DEFAULT '' COMMENT '户口性质',
    native_place VARCHAR(100) NOT NULL DEFAULT '' COMMENT '籍贯',
    hukou_address VARCHAR(255) NOT NULL DEFAULT '' COMMENT '户口所在地址（敏感，脱敏）',
    id_address VARCHAR(255) NOT NULL DEFAULT '' COMMENT '身份证住址（敏感，脱敏）',
    current_address VARCHAR(255) NOT NULL DEFAULT '' COMMENT '现住地址（脱敏）',
    bank_card VARCHAR(50) NOT NULL DEFAULT '' COMMENT '银行卡号（敏感，仅 admin/hr 可见）',
    bank_name VARCHAR(100) NOT NULL DEFAULT '' COMMENT '开户行',
    has_social_insurance VARCHAR(10) NOT NULL DEFAULT '' COMMENT '是否购买社保：是/否',
    has_housing_fund VARCHAR(10) NOT NULL DEFAULT '' COMMENT '是否购买公积金：是/否',
    fund_ratio VARCHAR(50) NOT NULL DEFAULT '' COMMENT '公积金比例',
    remark TEXT NULL COMMENT '备注（差部分入职资料等）',
    status VARCHAR(20) NOT NULL DEFAULT 'active' COMMENT '状态：active 在职 / resigned 离职',
    source_sheet VARCHAR(50) NOT NULL DEFAULT '' COMMENT '来源工作表名',
    source_row INT NULL COMMENT '来源行号',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_hr_employee_source (source_key),
    KEY idx_hr_employee_dept (dept_name),
    KEY idx_hr_employee_hire (hire_date),
    KEY idx_hr_employee_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='员工主档';

-- 2. 紧急联系人（一对多）
CREATE TABLE IF NOT EXISTS hr_emergency_contact (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    employee_id BIGINT NOT NULL COMMENT '关联 hr_employee.id',
    contact_name VARCHAR(50) NOT NULL DEFAULT '' COMMENT '联系人',
    relation VARCHAR(20) NOT NULL DEFAULT '' COMMENT '关系',
    phone VARCHAR(30) NOT NULL DEFAULT '' COMMENT '联系电话（脱敏）',
    sort_no INT NOT NULL DEFAULT 0 COMMENT '排序（第1/第2联系人）',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    PRIMARY KEY (id),
    KEY idx_hr_emergency_employee (employee_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='紧急联系人';

-- 3. 劳动合同与续签（一对多）
CREATE TABLE IF NOT EXISTS hr_contract (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    employee_id BIGINT NOT NULL COMMENT '关联 hr_employee.id',
    contract_type VARCHAR(50) NOT NULL DEFAULT '' COMMENT '合同类型/阶段：首次/2次续签/3次续签/无固定期限',
    seq_no INT NOT NULL DEFAULT 1 COMMENT '合同序号：1 首次，2 二次续签，3 三次续签',
    start_date DATE NULL COMMENT '开始时间',
    end_date DATE NULL COMMENT '截止时间',
    note VARCHAR(255) NOT NULL DEFAULT '' COMMENT '备注（如：无固定期限：2024年8月1日）',
    source_key VARCHAR(100) NOT NULL DEFAULT '' COMMENT '来源幂等键',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_hr_contract_source (source_key),
    KEY idx_hr_contract_employee (employee_id),
    KEY idx_hr_contract_end (end_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='劳动合同与续签';

-- 4. 离职记录（快照）
CREATE TABLE IF NOT EXISTS hr_resign (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    source_key VARCHAR(100) NOT NULL DEFAULT '' COMMENT '来源幂等键',
    name VARCHAR(50) NOT NULL DEFAULT '' COMMENT '姓名',
    company VARCHAR(100) NOT NULL DEFAULT '示例科技' COMMENT '所属公司',
    contract_type VARCHAR(50) NOT NULL DEFAULT '' COMMENT '合同类型',
    dept_name VARCHAR(100) NOT NULL DEFAULT '' COMMENT '离职时部门',
    group_name VARCHAR(100) NOT NULL DEFAULT '' COMMENT '离职时组别',
    position VARCHAR(100) NOT NULL DEFAULT '' COMMENT '离职时岗位',
    hire_date DATE NULL COMMENT '入职日期',
    regular_date DATE NULL COMMENT '转正时间',
    resign_date DATE NULL COMMENT '离职日期',
    resign_reason VARCHAR(255) NOT NULL DEFAULT '' COMMENT '离职原因',
    id_card VARCHAR(30) NOT NULL DEFAULT '' COMMENT '身份证号（敏感）',
    id_card_hash VARCHAR(64) NOT NULL DEFAULT '' COMMENT '身份证散列',
    phone VARCHAR(30) NOT NULL DEFAULT '' COMMENT '电话（脱敏）',
    education VARCHAR(20) NOT NULL DEFAULT '' COMMENT '学历',
    source_sheet VARCHAR(50) NOT NULL DEFAULT '' COMMENT '来源工作表',
    source_row INT NULL COMMENT '来源行号',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_hr_resign_source (source_key),
    KEY idx_hr_resign_date (resign_date),
    KEY idx_hr_resign_dept (dept_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='离职记录';

-- 5. 招聘需求台账
CREATE TABLE IF NOT EXISTS hr_job_requisition (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    req_no VARCHAR(50) NOT NULL DEFAULT '' COMMENT '需求编号',
    dept_name VARCHAR(100) NOT NULL DEFAULT '' COMMENT '用人部门',
    position VARCHAR(100) NOT NULL DEFAULT '' COMMENT '招聘岗位',
    headcount INT NOT NULL DEFAULT 1 COMMENT '招聘人数（编制）',
    reason TEXT NULL COMMENT '招聘原因',
    status VARCHAR(20) NOT NULL DEFAULT 'open' COMMENT '状态：open 招聘中 / closed 已关闭',
    priority VARCHAR(20) NOT NULL DEFAULT 'normal' COMMENT '优先级：high/normal/low',
    proposer VARCHAR(50) NOT NULL DEFAULT '' COMMENT '提出人',
    publish_date DATE NULL COMMENT '发布日期（HR 发布）',
    close_date DATE NULL COMMENT '关闭日期',
    remark VARCHAR(255) NOT NULL DEFAULT '' COMMENT '备注',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (id),
    KEY idx_hr_req_status (status),
    KEY idx_hr_req_dept (dept_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='招聘需求台账';

-- 6. 招聘候选人管道
CREATE TABLE IF NOT EXISTS hr_candidate (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    req_id BIGINT NULL COMMENT '关联 hr_job_requisition.id（可空）',
    name VARCHAR(50) NOT NULL DEFAULT '' COMMENT '候选人姓名',
    position VARCHAR(100) NOT NULL DEFAULT '' COMMENT '应聘职务',
    gender VARCHAR(10) NOT NULL DEFAULT '' COMMENT '性别',
    age VARCHAR(10) NOT NULL DEFAULT '' COMMENT '年龄',
    birthday DATE NULL COMMENT '出生日期',
    phone VARCHAR(30) NOT NULL DEFAULT '' COMMENT '联系电话（脱敏）',
    source_channel VARCHAR(50) NOT NULL DEFAULT '' COMMENT '来源渠道：BOSS直聘/内推/猎头/其他',
    stage VARCHAR(20) NOT NULL DEFAULT 'resume_pool' COMMENT '阶段：resume_pool 简历池 / first_interview 初面 / second_interview 复试 / offer 录用 / onboard 到岗 / hired 入职 / rejected 淘汰',
    resume_summary TEXT NULL COMMENT 'AI 解析摘要（姓名/职务/性别/年龄/出生日期/电话）',
    interview_note TEXT NULL COMMENT '面试情况备注',
    inviter VARCHAR(50) NOT NULL DEFAULT '' COMMENT '邀约人',
    first_interview_date DATE NULL COMMENT '初面日期',
    second_interview_date DATE NULL COMMENT '复试日期',
    offer_date DATE NULL COMMENT '录用日期',
    onboard_date DATE NULL COMMENT '到岗日期',
    hire_date DATE NULL COMMENT '入职日期',
    is_present VARCHAR(10) NOT NULL DEFAULT '' COMMENT '是否到面：是/否',
    hire_status VARCHAR(20) NOT NULL DEFAULT '' COMMENT '录用情况：录用/待定/未录用',
    remark VARCHAR(255) NOT NULL DEFAULT '' COMMENT '备注',
    source_key VARCHAR(100) NOT NULL DEFAULT '' COMMENT '来源幂等键',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_hr_candidate_source (source_key),
    KEY idx_hr_candidate_stage (stage),
    KEY idx_hr_candidate_req (req_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='招聘候选人管道';

-- 7. 月度考勤汇总
CREATE TABLE IF NOT EXISTS hr_attendance_sum (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    employee_id BIGINT NULL COMMENT '关联 hr_employee.id（可为空，导入时按姓名匹配）',
    month VARCHAR(7) NOT NULL COMMENT '月份 YYYY-MM',
    name VARCHAR(50) NOT NULL DEFAULT '' COMMENT '员工姓名（冗余，便于导入不匹配时展示）',
    dept_name VARCHAR(100) NOT NULL DEFAULT '' COMMENT '部门（冗余）',
    work_days DECIMAL(6,1) NOT NULL DEFAULT 0 COMMENT '应出勤天数',
    actual_days DECIMAL(6,1) NOT NULL DEFAULT 0 COMMENT '实际出勤天数',
    late_count INT NOT NULL DEFAULT 0 COMMENT '迟到次数',
    early_count INT NOT NULL DEFAULT 0 COMMENT '早退次数',
    absent_days DECIMAL(6,1) NOT NULL DEFAULT 0 COMMENT '缺勤天数',
    leave_days DECIMAL(6,1) NOT NULL DEFAULT 0 COMMENT '请假天数',
    overtime_hours DECIMAL(6,1) NOT NULL DEFAULT 0 COMMENT '加班时长',
    abnormal_count INT NOT NULL DEFAULT 0 COMMENT '异常记录数',
    remark VARCHAR(255) NOT NULL DEFAULT '' COMMENT '备注',
    source_key VARCHAR(100) NOT NULL DEFAULT '' COMMENT '来源幂等键',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_hr_attendance (employee_id, month),
    KEY idx_hr_attendance_month (month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='月度考勤汇总';

-- 8. 导入日志
CREATE TABLE IF NOT EXISTS hr_import_log (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    import_type VARCHAR(50) NOT NULL COMMENT '导入类型：roster/resign/attendance',
    filename VARCHAR(255) NOT NULL DEFAULT '' COMMENT '文件名',
    sheet_name VARCHAR(50) NOT NULL DEFAULT '' COMMENT '工作表名',
    rows_read INT NOT NULL DEFAULT 0 COMMENT '读取行数',
    inserted INT NOT NULL DEFAULT 0 COMMENT '新增',
    updated INT NOT NULL DEFAULT 0 COMMENT '更新',
    skipped INT NOT NULL DEFAULT 0 COMMENT '跳过',
    errors_json TEXT NULL COMMENT '错误报告（JSON 数组：行号/字段/原因）',
    operator VARCHAR(50) NOT NULL DEFAULT '' COMMENT '操作人',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    PRIMARY KEY (id),
    KEY idx_hr_import_type (import_type, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='导入日志';
