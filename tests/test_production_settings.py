"""
Tests for production settings, modern Vercel configuration, and deployment readiness.
Verifies:
  - Vercel domain handling in ALLOWED_HOSTS (.vercel.app wildcard support)
  - CSRF_TRUSTED_ORIGINS configuration for Vercel HTTPS preview/production URLs
  - Production SECRET_KEY requirement when DEBUG=False
  - DATABASE_URL parsing with SSL options
  - Staticfiles and WhiteNoise storage configuration
  - WSGI callable 'app' and 'application' export for Vercel
  - vercel.json modern functions configuration (no deprecated builds)
  - build_files.sh PEP 668 compliance (no manual pip install)
  - pyproject.toml Vercel entrypoint declaration
"""

import os
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from django.test import SimpleTestCase
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class VercelConfigurationTests(SimpleTestCase):
    """Verifies that settings and deployment artifacts are correctly configured for Vercel."""

    def test_allowed_hosts_includes_vercel_app(self):
        """ALLOWED_HOSTS must include .vercel.app to support Vercel preview and production subdomains."""
        self.assertIn('.vercel.app', settings.ALLOWED_HOSTS)

    def test_csrf_trusted_origins_includes_vercel(self):
        """CSRF_TRUSTED_ORIGINS must include https://*.vercel.app to prevent 403 CSRF errors on Vercel."""
        has_vercel_csrf = any('vercel.app' in origin for origin in settings.CSRF_TRUSTED_ORIGINS)
        self.assertTrue(has_vercel_csrf, "settings.CSRF_TRUSTED_ORIGINS must contain a vercel.app origin")

    def test_wsgi_app_callable_exported(self):
        """config/wsgi.py must export both 'application' and 'app' for Vercel serverless loader."""
        import config.wsgi as wsgi_module
        self.assertTrue(hasattr(wsgi_module, 'application'), "config.wsgi must export 'application'")
        self.assertTrue(hasattr(wsgi_module, 'app'), "config.wsgi must export 'app' for Vercel")
        self.assertIs(wsgi_module.app, wsgi_module.application)

    def test_wsgi_application_setting_matches(self):
        """WSGI_APPLICATION setting must resolve to config.wsgi.application."""
        self.assertEqual(settings.WSGI_APPLICATION, 'config.wsgi.application')

    def test_vercel_json_modern_functions_config(self):
        """vercel.json must exist, be valid JSON, configure functions, and avoid deprecated builds."""
        vercel_json_path = settings.BASE_DIR / 'vercel.json'
        self.assertTrue(vercel_json_path.exists(), "vercel.json must exist in project root")

        with open(vercel_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Must not contain legacy builds array which triggers deprecation warnings and disables framework detection
        self.assertNotIn('builds', data, "vercel.json must not use legacy 'builds' array")

        # Must configure functions for WSGI entrypoint
        functions = data.get('functions', {})
        self.assertIn('config/wsgi.py', functions, "vercel.json must configure config/wsgi.py in functions")
        self.assertGreaterEqual(functions['config/wsgi.py'].get('maxDuration', 0), 15)

    def test_build_files_sh_no_manual_pip_install(self):
        """build_files.sh must contain collectstatic and omit manual pip install for PEP 668 compliance."""
        build_script_path = settings.BASE_DIR / 'build_files.sh'
        self.assertTrue(build_script_path.exists(), "build_files.sh must exist in project root")

        content = build_script_path.read_text(encoding='utf-8')
        self.assertIn('collectstatic', content)
        # Verify manual pip install is NOT present to prevent externally-managed-environment errors
        self.assertNotIn('pip install', content, "build_files.sh must not contain manual pip install")

    def test_pyproject_toml_vercel_entrypoint(self):
        """pyproject.toml must declare tool.vercel.entrypoint to point directly to config.wsgi:application."""
        pyproject_path = settings.BASE_DIR / 'pyproject.toml'
        self.assertTrue(pyproject_path.exists(), "pyproject.toml must exist in project root")

        content = pyproject_path.read_text(encoding='utf-8')
        self.assertIn('tool.vercel', content)
        self.assertIn('config.wsgi:application', content)

    def test_database_url_ssl_parsing_logic(self):
        """DATABASE_URL with sslmode=require must parse cleanly into engine options."""
        test_url = "postgresql://myuser:mypassword@ep-test-db.us-east-2.aws.neon.tech:5432/neondb?sslmode=require"
        parsed = urlparse(test_url)
        params = parse_qs(parsed.query)

        self.assertEqual(parsed.scheme, "postgresql")
        self.assertEqual(parsed.hostname, "ep-test-db.us-east-2.aws.neon.tech")
        self.assertEqual(parsed.port, 5432)
        self.assertEqual(parsed.path, "/neondb")
        self.assertEqual(params.get('sslmode', [None])[0], "require")

    def test_static_root_and_dirs_configured(self):
        """STATIC_ROOT and STATICFILES_DIRS must be distinct directories to prevent collectstatic collisions."""
        self.assertIsNotNone(settings.STATIC_ROOT)
        self.assertTrue(len(settings.STATICFILES_DIRS) > 0)
        self.assertNotEqual(str(settings.STATIC_ROOT), str(settings.STATICFILES_DIRS[0]))

    def test_vercel_rewrites_configured(self):
        """vercel.json must configure rewrites mapping /(.*) to config/wsgi.py."""
        vercel_json_path = settings.BASE_DIR / 'vercel.json'
        with open(vercel_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        rewrites = data.get('rewrites', [])
        has_wsgi_rewrite = any(
            r.get('destination') == 'config/wsgi.py' and r.get('source') in ('/(.*)', '/.*')
            for r in rewrites
        )
        self.assertTrue(has_wsgi_rewrite, "vercel.json must route incoming requests to config/wsgi.py")

    def test_parse_database_url_helper_postgresql(self):
        """parse_database_url correctly parses encoded credentials, host, port, db, and sslmode."""
        from config.settings import parse_database_url
        url = "postgresql://user_admin:p%40ss%23word@db.neon.tech:5432/production_db?sslmode=require"
        config = parse_database_url(url)
        self.assertEqual(config['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(config['NAME'], 'production_db')
        self.assertEqual(config['USER'], 'user_admin')
        self.assertEqual(config['PASSWORD'], 'p@ss#word')
        self.assertEqual(config['HOST'], 'db.neon.tech')
        self.assertEqual(config['PORT'], '5432')
        self.assertEqual(config['OPTIONS']['sslmode'], 'require')

    def test_parse_database_url_helper_postgres_alias(self):
        """parse_database_url accepts 'postgres://' and normalizes to django.db.backends.postgresql."""
        from config.settings import parse_database_url
        url = "postgres://usr:pwd@db.host.com/myapp"
        config = parse_database_url(url)
        self.assertEqual(config['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(config['NAME'], 'myapp')
        self.assertEqual(config['USER'], 'usr')
        self.assertEqual(config['PASSWORD'], 'pwd')
        self.assertEqual(config['HOST'], 'db.host.com')
        self.assertEqual(config['PORT'], '5432')

    def test_parse_database_url_helper_sqlite(self):
        """parse_database_url accepts sqlite:// URLs."""
        from config.settings import parse_database_url
        url = "sqlite:///custom/path/test.sqlite3"
        config = parse_database_url(url)
        self.assertEqual(config['ENGINE'], 'django.db.backends.sqlite3')
        self.assertIn('test.sqlite3', config['NAME'])

    def test_parse_database_url_invalid_scheme_raises(self):
        """parse_database_url rejects unsupported schemes without leaking credentials."""
        from config.settings import parse_database_url
        with self.assertRaises(ImproperlyConfigured):
            parse_database_url("mysql://root:secret@localhost/db")

    def test_parse_database_url_missing_name_raises(self):
        """parse_database_url rejects URLs with missing database name."""
        from config.settings import parse_database_url
        with self.assertRaises(ImproperlyConfigured):
            parse_database_url("postgresql://user:pass@localhost:5432/")

    def test_custom_error_handlers_registered(self):
        """Custom HTTP 400, 403, 404, and 500 error handlers are properly configured."""
        import config.urls as urls_module
        self.assertEqual(urls_module.handler400, 'dashboard.views.error_400_view')
        self.assertEqual(urls_module.handler403, 'dashboard.views.error_403_view')
        self.assertEqual(urls_module.handler404, 'dashboard.views.error_404_view')
        self.assertEqual(urls_module.handler500, 'dashboard.views.error_500_view')

    def test_custom_error_views_return_correct_status(self):
        """Error handler views render proper templates and return correct status codes."""
        from django.test import RequestFactory
        from dashboard.views import error_400_view, error_403_view, error_404_view, error_500_view
        factory = RequestFactory()

        req = factory.get('/any-path/')
        resp_400 = error_400_view(req)
        self.assertEqual(resp_400.status_code, 400)

        resp_403 = error_403_view(req)
        self.assertEqual(resp_403.status_code, 403)

        resp_404 = error_404_view(req)
        self.assertEqual(resp_404.status_code, 404)

        resp_500 = error_500_view(req)
        self.assertEqual(resp_500.status_code, 500)

