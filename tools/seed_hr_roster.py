# -*- coding: utf-8 -*-
"""人力行政模块 · 花名册数据灌入脚本（D1 交付物）。

用法（在项目根目录执行）：
    python tools/seed_hr_roster.py [xlsx路径]

默认读取 D:\\enterprise_agent\\示例科技 员工花名册.xlsx：
1. 「员工花名册」工作表 → hr_employee + hr_contract + hr_emergency_contact（虚构测试员工）
2. 「离职员工」「2024年5月前离职人员」工作表 → hr_resign
幂等：按 source_key 存在则更新，重复执行安全。
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")

from utils import hr_service  # noqa: E402

DEFAULT_XLSX = "demo-roster.xlsx"


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_XLSX
    print(f"== 读取花名册: {path}")
    r1 = hr_service.import_roster_workbook(path, operator="seed")
    print("== 员工花名册:", r1["message"])
    for err in r1.get("errors", [])[:10]:
        print("   -", err)
    r2 = hr_service.import_resign_workbook(path, operator="seed")
    print("== 离职表:", r2["message"])
    for err in r2.get("errors", [])[:10]:
        print("   -", err)
    print("== 完成")


if __name__ == "__main__":
    main()
