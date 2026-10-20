import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

import design_routes
from utils import design_library_service, permission_service


class DesignRecycleBinServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        with self.engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE design_library_item (
                    id TEXT PRIMARY KEY, item_type TEXT, title TEXT, body TEXT,
                    product TEXT, scene TEXT, category TEXT, images_json TEXT,
                    original_url TEXT, generated_url TEXT, source TEXT, sort_order INTEGER,
                    created_by TEXT, updated_by TEXT, deleted_by TEXT, deleted_at DATETIME
                )
            """))
            connection.execute(text("""
                INSERT INTO design_library_item
                (id, item_type, title, body, product, scene, category, images_json, source, sort_order)
                VALUES ('case-1', 'models', '示例', '描述', '', '', '',
                        '["/api/design/image/0123456789abcdefabcd.webp"]', '手动新增', 0)
            """))
        self.ready = patch.object(design_library_service, "ensure_ready", return_value=self.engine)
        self.ready.start()

    def tearDown(self):
        self.ready.stop()
        self.engine.dispose()

    def test_new_items_are_listed_before_existing_items(self):
        service = design_library_service
        created = service.create_item(
            {"item_type": "models", "title": "新资料", "text": "新描述"},
            user_name="设计师",
            engine=self.engine,
        )

        items = service.catalog(self.engine)["models"]
        self.assertEqual(items[0]["id"], created["id"])
        self.assertEqual(items[1]["id"], "case-1")

    def test_delete_restore_and_purge_keep_catalog_consistent(self):
        service = design_library_service
        image_url = "/api/design/image/0123456789abcdefabcd.webp"
        self.assertTrue(service.image_is_visible(image_url, {"models"}, admin=False, engine=self.engine))
        self.assertFalse(service.image_is_visible(image_url, {"prompts"}, admin=False, engine=self.engine))
        self.assertEqual(len(service.catalog(self.engine)["models"]), 1)
        self.assertTrue(service.delete_item("models", "case-1", user_name="聂悠悠", engine=self.engine))
        self.assertFalse(service.delete_item("models", "case-1", user_name="聂悠悠", engine=self.engine))
        self.assertEqual(service.catalog(self.engine)["models"], [])
        self.assertFalse(service.image_is_visible(image_url, {"models"}, admin=False, engine=self.engine))
        self.assertTrue(service.image_is_visible(image_url, set(), admin=True, engine=self.engine))
        self.assertIsNone(service.get_item("models", "case-1", self.engine))
        trashed = service.trash_items(self.engine)
        self.assertEqual(trashed[0]["deleted_by"], "聂悠悠")
        self.assertEqual(trashed[0]["item_type"], "models")
        self.assertTrue(service.restore_item("models", "case-1", self.engine))
        self.assertEqual(len(service.catalog(self.engine)["models"]), 1)
        self.assertEqual(service.trash_items(self.engine), [])
        self.assertFalse(service.purge_item("models", "case-1", self.engine))
        self.assertTrue(service.delete_item("models", "case-1", user_name="曾浠洋", engine=self.engine))
        self.assertTrue(service.purge_item("models", "case-1", self.engine))
        self.assertEqual(service.trash_items(self.engine), [])
        self.assertEqual(service.catalog(self.engine)["models"], [])
        self.assertFalse(service.image_is_visible(image_url, {"models"}, admin=True, engine=self.engine))


class DesignRecycleBinPermissionTest(unittest.IsolatedAsyncioTestCase):
    def test_only_named_unique_accounts_and_admin_can_soft_delete(self):
        with patch.object(permission_service, "legacy_name_if_unique", side_effect=lambda _, name: name):
            for name in ("聂悠悠", "曾浠洋"):
                self.assertTrue(permission_service.can_delete_design_item({"role": "designer", "real_name": name}))
            self.assertFalse(permission_service.can_delete_design_item({"role": "designer", "real_name": "其他人"}))
        with patch.object(permission_service, "legacy_name_if_unique", return_value=""):
            self.assertFalse(permission_service.can_delete_design_item({"role": "designer", "real_name": "聂悠悠"}))
        self.assertTrue(permission_service.can_delete_design_item({"role": "admin", "real_name": "管理员"}))

    async def test_non_admin_cannot_read_or_purge_recycle_bin(self):
        with patch.object(design_routes, "require_login", new=AsyncMock(return_value={"role": "designer"})), \
             patch.object(design_routes.design_library_service, "trash_items") as read_trash, \
             patch.object(design_routes.design_library_service, "purge_item") as purge:
            for operation in (
                design_routes.list_trash(None),
                design_routes.purge_item("models", "case-1", None),
                design_routes.restore_item("models", "case-1", None),
            ):
                with self.assertRaises(HTTPException) as context:
                    await operation
                self.assertEqual(context.exception.status_code, 403)
            read_trash.assert_not_called()
            purge.assert_not_called()

    async def test_named_user_can_move_visible_item_to_trash(self):
        user = {"role": "designer", "real_name": "曾浠洋", "username": "designer-2"}
        with patch.object(design_routes, "require_login", new=AsyncMock(return_value=user)), \
             patch.object(design_routes, "get_engine", return_value=object()), \
             patch.object(permission_service, "legacy_name_if_unique", return_value="曾浠洋"), \
             patch.object(design_routes, "_require_page"), \
             patch.object(design_routes.design_library_service, "delete_item", return_value=True) as move:
            result = await design_routes.delete_item("models", "case-1", None)
        self.assertEqual(result, {"deleted": True})
        move.assert_called_once_with("models", "case-1", user_name="曾浠洋")


if __name__ == "__main__":
    unittest.main()
