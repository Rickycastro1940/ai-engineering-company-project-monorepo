from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKOFFICE_APP = REPO_ROOT / "uis" / "backoffice" / "app"
PUBLIC_WEBSITE = REPO_ROOT / "uis" / "web" / "index.html"


class FrontendRouteProtectionTest(unittest.TestCase):
    def assert_uses_protected_route(self, relative_path: str) -> None:
        source = (BACKOFFICE_APP / relative_path).read_text(encoding="utf-8")
        self.assertIn("ProtectedRoute", source)

    def test_protected_backoffice_views_use_route_guard(self) -> None:
        protected_pages = [
            "page.js",
            "account/profile/page.js",
            "account/change-password/page.js",
        ]
        for page in protected_pages:
            with self.subTest(page=page):
                self.assert_uses_protected_route(page)

    def test_public_backoffice_auth_pages_are_not_guarded(self) -> None:
        public_pages = [
            "login/page.js",
            "register/page.js",
        ]
        for page in public_pages:
            with self.subTest(page=page):
                source = (BACKOFFICE_APP / page).read_text(encoding="utf-8")
                self.assertNotIn("ProtectedRoute", source)

    def test_public_website_has_no_token_redirect_logic(self) -> None:
        source = PUBLIC_WEBSITE.read_text(encoding="utf-8")
        self.assertNotIn("localStorage", source)
        self.assertNotIn("auth_token", source)
        self.assertNotIn("/login", source)


if __name__ == "__main__":
    unittest.main()
