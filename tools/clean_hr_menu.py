# -*- coding: utf-8 -*-
"""清理人力资源菜单：删除旧的 'hr' 演示页（已被 hr-roster 承接），并重排真实菜单顺序。"""
import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")
from sqlalchemy import text
from utils.import_service import get_engine

# 规范排序（仅参与重排的 route；其余如 hr-filter 保持原地）
ORDER = [
    "hr-driver", "hr-roster", "hr-recruit",
    "hr-knowledge",
    "hr-filter",
]


def main() -> None:
    eng = get_engine()
    with eng.begin() as conn:
        parent = conn.execute(text("SELECT id FROM ecom_menu WHERE label='人力资源' AND parent_id=0")).scalar_one_or_none()
        if parent is None:
            print("!! 未找到人力资源分组")
            return
        # 删除旧的 'hr' 演示页（已被 hr-roster 承接）
        old_hr = conn.execute(text(
            "SELECT id FROM ecom_menu WHERE parent_id=:p AND route='hr'"
        ), {"p": parent}).scalar_one_or_none()
        if old_hr is not None:
            conn.execute(text("DELETE FROM ecom_menu WHERE id=:id"), {"id": old_hr})
            print("  删除旧的人力资源菜单项")

        conn.execute(text(
            "DELETE FROM ecom_menu WHERE parent_id=:p AND route IN ('hr-training', 'hr-performance', 'hr-payroll', 'hr-attendance')"
        ), {"p": parent})

        # 重排 sort_order
        for sort_no, route in enumerate(ORDER):
            conn.execute(
                text("UPDATE ecom_menu SET sort_order=:s WHERE parent_id=:p AND route=:r"),
                {"s": sort_no, "p": parent, "r": route},
            )
        # 其余未列出的（若有）排在最后
        rows = conn.execute(text(
            "SELECT id, route FROM ecom_menu WHERE parent_id=:p ORDER BY sort_order"
        ), {"p": parent}).all()
        print(f"== 人力资源菜单现有 {len(rows)} 项（按 sort 排序）：")
        for r in conn.execute(text(
            "SELECT route, label, sort_order FROM ecom_menu WHERE parent_id=:p ORDER BY sort_order"
        ), {"p": parent}).all():
            print(f"   {r[2]}. {r[1]} ({r[0]})")


if __name__ == "__main__":
    main()
