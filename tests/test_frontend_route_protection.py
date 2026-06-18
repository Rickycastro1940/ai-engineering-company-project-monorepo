from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKOFFICE_APP = REPO_ROOT / "uis" / "backoffice" / "app"
BACKOFFICE_COMPONENTS = REPO_ROOT / "uis" / "backoffice" / "components"
BACKOFFICE_LIB = REPO_ROOT / "uis" / "backoffice" / "lib"
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

    def test_token_lifecycle_is_implemented(self) -> None:
        api_client = (BACKOFFICE_LIB / "api.js").read_text(encoding="utf-8")
        auth_provider = (BACKOFFICE_COMPONENTS / "AuthProvider.js").read_text(encoding="utf-8")
        login_page = (BACKOFFICE_APP / "login" / "page.js").read_text(encoding="utf-8")
        register_page = (BACKOFFICE_APP / "register" / "page.js").read_text(encoding="utf-8")

        self.assertIn('const TOKEN_KEY = "auth_token"', api_client)
        self.assertIn("window.localStorage.setItem(TOKEN_KEY, token)", api_client)
        self.assertIn("window.localStorage.getItem(TOKEN_KEY)", api_client)
        self.assertIn('headers.set("Authorization", `Bearer ${token}`)', api_client)
        self.assertIn("response.status === 401 && token", api_client)
        self.assertIn("clearToken();", api_client)
        self.assertIn("window.location.assign(`/login?next=", api_client)

        self.assertIn("signIn(authResponse)", login_page)
        self.assertIn("signIn(authResponse)", register_page)
        self.assertIn("storeToken(authResponse.token)", auth_provider)
        self.assertIn("clearToken();", auth_provider)
        self.assertIn('router.replace("/login")', auth_provider)


if __name__ == "__main__":
    unittest.main()
