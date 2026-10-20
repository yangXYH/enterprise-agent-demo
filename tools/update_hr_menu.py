# -*- coding: utf-8 -*-
"""更新 ecom_menu 人力资源分组子项：把待开发演示页替换为真实页面菜单（幂等）。

新增/更新由 route 唯一标识：对人力资源分组（label='人力资源'）下的子项，
按 route 归并：已存在的更新 label/sort，不存在的插入。
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")

from sqlalchemy import text
from utils.import_service import get_engine

# route -> (菜单名)  排序按插入顺序
HR_MENU_ITEMS = [
    ("hr-driver", "人事驾驶舱"),
    ("hr-roster", "人员花名册"),
    ("hr-recruit", "招聘管理"),
    ("hr-knowledge", "人力行政知识库"),
]


def main() -> None:
    eng = get_engine()
    with eng.begin() as conn:
        parent = conn.execute(text("SELECT id FROM ecom_menu WHERE label = '人力资源' AND parent_id = 0")).scalar_one_or_none()
        if parent is None:
            print("!! 未找到人力资源分组，中止")
            return

        # 清理已下线的旧菜单，避免历史 ecom_menu 数据重新把它们展示出来。
        conn.execute(
            text("DELETE FROM ecom_menu WHERE parent_id = :p AND route IN ('hr-training', 'hr-performance', 'hr-payroll', 'hr-attendance')"),
            {"p": parent},
        )
        for sort_no, (route, label) in enumerate(HR_MENU_ITEMS):
            existing = conn.execute(
                text("SELECT id FROM ecom_menu WHERE parent_id = :p AND route = :r"),
                {"p": parent, "r": route},
            ).scalar_one_or_none()
            if existing is not None:
                conn.execute(
                    text("UPDATE ecom_menu SET label = :l, sort_order = :s WHERE id = :id"),
                    {"l": label, "s": sort_no, "id": existing},
                )
            else:
                conn.execute(
                    text("INSERT INTO ecom_menu (parent_id, label, icon, route, sort_order) VALUES (:p, :l, '', :r, :s)"),
                    {"p": parent, "l": label, "r": route, "s": sort_no},
                )
            print(f"  {'更新' if existing else '新增'} {route} -> {label}")

        # 老的待开发 hr 若仍存在则更新为对应真实页，或删除多余旧项
        # 旧 'hr' 已由 hr-roster 承接；'hr-recruit' 已存在保留
        for old_route, new_route in (("hr", "hr-roster"),):
            old_id = conn.execute(
                text("SELECT id FROM ecom_menu WHERE parent_id = :p AND route = :r"),
                {"p": parent, "r": old_route},
            ).scalar_one_or_none()

    print("== ecom_menu 人力资源分组更新完成")


if __name__ == "__main__":
    main()
