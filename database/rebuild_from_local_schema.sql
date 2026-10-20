-- Rebuild enterprise_agent_db from local MySQL schema.
-- Generated from local enterprise_agent_db using SHOW CREATE TABLE.
-- WARNING: Running this on the server will DROP the existing database and all data in it.

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP DATABASE IF EXISTS `enterprise_agent_db`;
CREATE DATABASE `enterprise_agent_db` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `enterprise_agent_db`;

-- Table structure for `hr_job_template`
DROP TABLE IF EXISTS `hr_job_template`;
CREATE TABLE `hr_job_template` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '岗位模板主键ID',
  `job_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '岗位名称(如: 京东运营主管)，已设置唯一防重',
  `job_info` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '岗位要求/JD详细信息，用于AI识别的上下文',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '系统入库时间(自动写入)',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后跟进修改时间(自动触发更新)',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_job_name` (`job_name`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='人力行政中心-常用岗位信息模板持久化表';

-- Table structure for `interview_register`
DROP TABLE IF EXISTS `interview_register`;
CREATE TABLE `interview_register` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '主键自增ID',
  `inviter` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '邀约人/所属HR',
  `name` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '候选人姓名',
  `position` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '应聘职务/岗位',
  `gender` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '性别',
  `age` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '年龄',
  `birthday` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '出生日期',
  `phone` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '联系电话',
  `first_interview_date` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '初面日期',
  `first_interview_time` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '初面时间',
  `second_interview_date` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '复试日期',
  `second_interview_time` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '复试时间',
  `is_present` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '是否到面 (是/否/待定)',
  `interview_status` text COLLATE utf8mb4_unicode_ci COMMENT '面试情况/面试评语',
  `hire_status` text COLLATE utf8mb4_unicode_ci COMMENT '录用情况/薪资方案',
  `join_date` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '入职时间排期',
  `remark` text COLLATE utf8mb4_unicode_ci COMMENT '待定/遗留问题备注',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '系统记录创建时间',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后跟进修改时间',
  `archived` tinyint(1) NOT NULL DEFAULT '0' COMMENT '是否已归档 (0=否 1=是)',
  `archived_at` datetime DEFAULT NULL COMMENT '归档时间',
  PRIMARY KEY (`id`),
  KEY `idx_phone` (`phone`),
  KEY `idx_first_date` (`first_interview_date`),
  KEY `idx_archived` (`archived`)
) ENGINE=InnoDB AUTO_INCREMENT=47 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='人力行政中心-面试邀约与全周期跟进登记表';

-- Table structure for `resume_history`
DROP TABLE IF EXISTS `resume_history`;
CREATE TABLE `resume_history` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '自增主键ID',
  `job_title` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '岗位名称(如：数据分析师)',
  `jd_text` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '当时对应的岗位需求描述(JD)',
  `filename` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '上传的简历原始文件名',
  `name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'AI提取出的候选人姓名',
  `education` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'AI提取并打平后的最高学历(学校/专业)',
  `skills` text COLLATE utf8mb4_unicode_ci COMMENT 'AI提取的核心技术栈(以JSON字符串或逗号分隔存储)',
  `experience` text COLLATE utf8mb4_unicode_ci COMMENT 'AI提取并洗净的工作/项目经历纯文本',
  `match_score` int DEFAULT NULL COMMENT 'AI计算出的简历与JD核心匹配度得分(0-100)',
  `ai_review` text COLLATE utf8mb4_unicode_ci COMMENT 'AI深度诊断报告(包含匹配优势、风险短板及面试提问建议)',
  `created_at` datetime DEFAULT NULL COMMENT '记录创建/AI解析完成的时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_resume_history_job_name` (`job_title`,`name`)
) ENGINE=InnoDB AUTO_INCREMENT=16 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='人力行政中心-AI简历筛选与初筛历史沉淀表';

-- Table structure for `sys_user`
DROP TABLE IF EXISTS `sys_user`;
CREATE TABLE `sys_user` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  `username` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '登录账号(名字全拼)',
  `password` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '123456' COMMENT '明文密码(默认123456)',
  `real_name` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '员工姓名',
  `department` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '所属部门',
  `job_title` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '岗位职位',
  `role` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '核心角色: admin(管理员)/boss(老板)/operator(运营)/designer(内容美工)/hr(人力行政)/finance(财务)/supply(供应链)/user(普通员工)',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '系统入库时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_username` (`username`)
) ENGINE=InnoDB AUTO_INCREMENT=75 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统基础用户表-明文纯享版';

SET FOREIGN_KEY_CHECKS = 1;
