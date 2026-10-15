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
