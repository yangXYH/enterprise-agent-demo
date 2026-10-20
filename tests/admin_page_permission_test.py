import unittest
from unittest.mock import patch

from fastapi import HTTPException

import design_routes
from utils.permission_service import PAGE_DEFS, PERM_DEFAULTS


class PagePermissionTest(unittest.IsolatedAsyncioTestCase):
    def test_real_navigation_pages_are_registered(self):
        required = {
            "design-overview", "design-models", "design-prompts", "design-comparisons", "design-styles",
            "insight", "insight-trend", "insight-category", "insight-brand",
            "shop-report",
            "inventory-stockout", "inventory-shortage", "inventory-listed", "inventory-delisted",
            "points", "points-rule", "points-log", "ecommerce-dashboard",
        }
        self.assertTrue(required <= PAGE_DEFS.keys())
        self.assertEqual(set(PAGE_DEFS), set(PERM_DEFAULTS))

    async def test_design_catalog_removes_ungranted_sections(self):
        user = {"username": "designer1", "role": "designer"}
        data = {"models": [{"id": "1"}], "prompts": [{"id": "2"}],
                "comparisons": [{"id": "3"}], "styles": [{"id": "4"}], "sources": []}
        with patch.object(design_routes, "require_login", return_value=user), \
             patch.object(design_routes, "_allowed_pages", return_value={"design-models"}), \
             patch.object(design_routes.design_library_service, "catalog", return_value=data):
            result = await design_routes.catalog(None)
        self.assertEqual(result["models"], [{"id": "1"}])
        self.assertEqual(result["prompts"], [])
        self.assertEqual(result["comparisons"], [])
        self.assertEqual(result["styles"], [])

    async def test_design_catalog_denies_users_without_design_pages(self):
        with patch.object(design_routes, "require_login", return_value={"role": "user"}), \
             patch.object(design_routes, "_allowed_pages", return_value=set()):
            with self.assertRaises(HTTPException) as context:
                await design_routes.catalog(None)
        self.assertEqual(context.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
