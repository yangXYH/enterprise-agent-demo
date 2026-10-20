# 测试资料

`shop_report.json` 为完整应用使用的虚构店铺快照，包含 9 家测试店铺、测试年度一月至生成时所在月份及完整 28 项费用字段。公式位于 `tools/full_demo_fixtures.py` 的 `write_shop_snapshot`，财务关系由 `tests/demo_data_test.py` 验证。

原业务其他模块的数据在首次启动时自动写入专用 MySQL 演示库。测试工作簿、退货导入源、设计图形、知识文件和测试 PDF 由同一生成器建立，运行时文件不提交 Git。原模型接入、业务查询和权限继续使用原服务代码。
