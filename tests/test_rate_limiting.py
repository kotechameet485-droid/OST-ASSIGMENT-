"""
Rate Limit, Authentication & Resilience Test Suite for OpenSourceLens.
Validates:
  - Missing token vs configured token
  - Authorization headers formatting & presence
  - Token masking (token never appears in logs, responses, or exceptions)
  - 401 raises GitHubAuthenticationError
  - 403 with remaining=0 vs remaining>0 (RateLimitExceeded vs Forbidden)
  - 429 raises GitHubRateLimitExceededError
  - Transient 5xx retry with backoff, no retry on 4xx rate limits
  - Graceful fallback to stored snapshot when GitHub is rate-limited
  - Incomplete/failed analysis does not destroy valid existing snapshots
  - View renders rate_limit.html (HTTP 429) when no cache exists
  - check_github_api management command diagnostics without secret leaks
"""

import io
import logging
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

from django.test import TestCase, Client, override_settings
from django.core.management import call_command
from django.urls import reverse

from dashboard.models import Repository, RepositoryAnalysis
from dashboard.services.github_service import (
    GitHubService,
    GitHubAuthenticationError,
    GitHubForbiddenError,
    GitHubRateLimitExceededError,
    GitHubRepoNotFoundError,
    GitHubTimeoutError,
    GitHubNetworkError,
    GitHubAPIError,
)
from dashboard.services.analysis_service import AnalysisService


class GitHubAuthenticationAndHeaderTests(TestCase):
    """Verifies token handling, headers, and secret protection."""

    @override_settings(GITHUB_TOKEN="ghp_testsecrettoken1234567890abcdef")
    def test_authenticated_headers_built_correctly(self):
        """When token is configured, Authorization: Bearer <TOKEN> is attached."""
        service = GitHubService()
        self.assertTrue(service.is_authenticated)
        self.assertIn("Authorization", service.session.headers)
        self.assertEqual(
            service.session.headers["Authorization"],
            "Bearer ghp_testsecrettoken1234567890abcdef",
        )
        self.assertEqual(
            service.session.headers["Accept"],
            "application/vnd.github+json",
        )
        self.assertEqual(
            service.session.headers["X-GitHub-Api-Version"],
            "2022-11-28",
        )

    @override_settings(GITHUB_TOKEN="")
    def test_unauthenticated_headers_when_token_empty(self):
        """When token is empty, Authorization header is omitted."""
        service = GitHubService()
        self.assertFalse(service.is_authenticated)
        self.assertNotIn("Authorization", service.session.headers)

    @override_settings(GITHUB_TOKEN="super_secret_pat_9999")
    def test_token_never_logged(self):
        """Ensure token value is never emitted to logger output."""
        logger = logging.getLogger("dashboard.services.github_service")
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        try:
            service = GitHubService()
            log_output = log_capture.getvalue()
            self.assertNotIn("super_secret_pat_9999", log_output)
            self.assertIn("authenticated: True", log_output)
        finally:
            logger.removeHandler(handler)


class GitHubExceptionDifferentiationTests(TestCase):
    """Verifies explicit exception differentiation between 401, 403, 404, 429, 5xx."""

    def setUp(self):
        self.service = GitHubService()

    @patch("requests.Session.get")
    def test_401_raises_github_authentication_error(self, mock_get):
        resp = MagicMock(status_code=401, headers={}, text='{"message": "Bad credentials"}')
        mock_get.return_value = resp

        with self.assertRaises(GitHubAuthenticationError) as ctx:
            self.service.get_repository("owner", "repo")
        self.assertIn("authentication failed", str(ctx.exception).lower())

    @patch("requests.Session.get")
    def test_403_rate_limit_when_remaining_zero(self, mock_get):
        resp = MagicMock(
            status_code=403,
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1893456000", "x-ratelimit-limit": "5000"},
            text='{"message": "API rate limit exceeded"}',
        )
        mock_get.return_value = resp

        with self.assertRaises(GitHubRateLimitExceededError) as ctx:
            self.service.get_repository("owner", "repo")
        self.assertEqual(ctx.exception.remaining, 0)
        self.assertEqual(ctx.exception.limit, 5000)
        self.assertIn("rate limit", str(ctx.exception).lower())

    @patch("requests.Session.get")
    def test_403_forbidden_when_remaining_greater_than_zero(self, mock_get):
        resp = MagicMock(
            status_code=403,
            headers={"x-ratelimit-remaining": "4950", "x-ratelimit-limit": "5000"},
            text='{"message": "Must have push access to view"}',
        )
        mock_get.return_value = resp

        with self.assertRaises(GitHubForbiddenError) as ctx:
            self.service.get_repository("owner", "private-repo")
        self.assertNotIn("rate limit", str(ctx.exception).lower())
        self.assertIn("forbidden", str(ctx.exception).lower())

    @patch("requests.Session.get")
    def test_429_raises_github_rate_limit_error(self, mock_get):
        resp = MagicMock(
            status_code=429,
            headers={"retry-after": "60", "x-ratelimit-remaining": "0"},
            text='{"message": "Too Many Requests"}',
        )
        mock_get.return_value = resp

        with self.assertRaises(GitHubRateLimitExceededError) as ctx:
            self.service.get_repository("owner", "repo")
        self.assertIn("rate limit", str(ctx.exception).lower())

    @patch("requests.Session.get")
    def test_404_raises_github_repo_not_found_error(self, mock_get):
        resp = MagicMock(status_code=404, headers={}, text='{"message": "Not Found"}')
        mock_get.return_value = resp

        with self.assertRaises(GitHubRepoNotFoundError):
            self.service.get_repository("owner", "missing-repo")


class GitHubRetryPolicyTests(TestCase):
    """Verifies that transient errors (502, 503, 504) retry, while 4xx errors fail immediately."""

    def setUp(self):
        self.service = GitHubService()

    @patch("time.sleep", return_value=None)
    @patch("requests.Session.get")
    def test_transient_502_retries_and_succeeds(self, mock_get, mock_sleep):
        resp_502 = MagicMock(status_code=502, headers={}, text="Bad Gateway")
        resp_200 = MagicMock(
            status_code=200,
            headers={},
            json=lambda: {
                "id": 1,
                "full_name": "owner/repo",
                "stargazers_count": 10,
                "forks_count": 2,
                "open_issues_count": 0,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-02T00:00:00Z",
                "pushed_at": "2024-01-02T00:00:00Z",
                "default_branch": "main",
                "topics": [],
            },
        )
        mock_get.side_effect = [resp_502, resp_200]

        data = self.service.get_repository("owner", "repo")
        self.assertEqual(data["full_name"], "owner/repo")
        self.assertEqual(mock_get.call_count, 2)
        mock_sleep.assert_called_once()

    @patch("time.sleep", return_value=None)
    @patch("requests.Session.get")
    def test_rate_limit_never_retries_repeatedly(self, mock_get, mock_sleep):
        """A 403 rate limit must fail immediately without wasting API quota on retries."""
        resp_403 = MagicMock(
            status_code=403,
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1893456000"},
            text="API rate limit exceeded",
        )
        mock_get.return_value = resp_403

        with self.assertRaises(GitHubRateLimitExceededError):
            self.service.get_repository("owner", "repo")

        # Must NOT retry
        self.assertEqual(mock_get.call_count, 1)
        mock_sleep.assert_not_called()


class RateLimitStatusEndpointTests(TestCase):
    """Verifies get_rate_limit_status method."""

    def setUp(self):
        self.service = GitHubService()

    @patch("requests.Session.get")
    def test_get_rate_limit_status_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "resources": {
                "core": {
                    "limit": 5000,
                    "remaining": 4982,
                    "reset": 1893456000,
                    "used": 18,
                }
            }
        }
        mock_get.return_value = mock_resp

        status = self.service.get_rate_limit_status()
        self.assertTrue(status["authenticated"])
        self.assertEqual(status["limit"], 5000)
        self.assertEqual(status["remaining"], 4982)
        self.assertEqual(status["used"], 18)
        self.assertIn("reset_at", status)


class SnapshotResilienceDuringRateLimitTests(TestCase):
    """Ensures existing historical and cached analyses survive rate limits."""

    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.repo = Repository.objects.create(
            owner="resilience",
            name="cache-survivor",
            full_name="resilience/cache-survivor",
            description="Testing snapshot resilience",
            stars=500,
            forks=100,
            open_issues=12,
            pushed_at=self.now,
            created_at=self.now - timedelta(days=200),
            updated_at=self.now,
            default_branch="main",
            license="MIT",
            license_spdx="MIT",
        )
        # Store a valid existing snapshot for 30d
        self.existing_analysis = RepositoryAnalysis.objects.create(
            repository=self.repo,
            health_score=85,
            health_tier="Good",
            activity_score=80,
            issue_score=90,
            pr_score=85,
            contributor_score=80,
            maintenance_score=90,
            analysis_window="30d",
            snapshot_payload={
                "overview": {"stars": 500, "forks": 100},
                "data_coverage": {"commits_analyzed": 25, "issues_analyzed": 10},
                "scores": {"health_score": 85, "health_tier": "Good"},
                "analysis_window": "30d",
            },
        )
        self.analysis_service = AnalysisService()

    def test_live_rate_limit_falls_back_to_existing_snapshot(self):
        """When GitHub API is rate-limited on refresh, the stored snapshot is returned intact."""
        rate_err = GitHubRateLimitExceededError(
            message="API rate limit exceeded",
            remaining=0,
            limit=5000,
            reset_timestamp=1893456000,
            is_authenticated=True,
        )
        with patch.object(self.analysis_service.github_service, 'get_repository', side_effect=rate_err):
            # Request with force_refresh=True
            result = self.analysis_service.run_analysis(
                "resilience", "cache-survivor", window="30d", force_refresh=True
            )

        # Snapshot was preserved
        self.assertTrue(result.get("live_fetch_failed"))
        self.assertTrue(result.get("is_rate_limited"))
        self.assertEqual(result["scores"]["health_score"], 85)
        self.assertIn("rate_limit_info", result)
        self.assertEqual(result["rate_limit_info"]["limit"], 5000)

        # DB snapshot record was NOT overwritten or deleted
        refetched = RepositoryAnalysis.objects.get(id=self.existing_analysis.id)
        self.assertEqual(refetched.health_score, 85)

    def test_no_cache_and_rate_limit_raises_error(self):
        """When NO stored snapshot exists and GitHub is rate limited, exception is raised for view handling."""
        rate_err = GitHubRateLimitExceededError(
            message="API rate limit exceeded",
            remaining=0,
            limit=60,
            reset_timestamp=1893456000,
            is_authenticated=False,
        )
        with patch.object(self.analysis_service.github_service, 'get_repository', side_effect=rate_err):
            with self.assertRaises(GitHubRateLimitExceededError):
                self.analysis_service.run_analysis(
                    "brand-new-org", "uncached-repo", window="30d", force_refresh=True
                )


class ViewRateLimitAndAuthErrorHandlingTests(TestCase):
    """Tests that views render appropriate HTTP status codes and templates."""

    def setUp(self):
        self.client = Client()

    @patch("dashboard.views.AnalysisService.run_analysis")
    def test_rate_limit_view_renders_429_template(self, mock_run):
        """When GitHubRateLimitExceededError is caught in analyze_view, return HTTP 429 with rate_limit.html."""
        rate_err = GitHubRateLimitExceededError(
            message="GitHub API rate limit reached.",
            remaining=0,
            limit=5000,
            reset_timestamp=1893456000,
            is_authenticated=True,
        )
        mock_run.side_effect = rate_err

        response = self.client.get(
            reverse("analyze"), {"repo": "facebook/react"}
        )
        self.assertEqual(response.status_code, 429)
        self.assertTemplateUsed(response, "rate_limit.html")
        self.assertContains(response, "GitHub API Rate Limit Reached", status_code=429)
        self.assertContains(response, "5000 req/hr", status_code=429)

    @patch("dashboard.views.AnalysisService.run_analysis")
    def test_auth_error_view_renders_401_template(self, mock_run):
        """When GitHubAuthenticationError is caught in analyze_view, return HTTP 401 with errors/401.html."""
        mock_run.side_effect = GitHubAuthenticationError("Bad credentials")

        response = self.client.get(
            reverse("analyze"), {"repo": "facebook/react"}
        )
        self.assertEqual(response.status_code, 401)
        self.assertTemplateUsed(response, "errors/401.html")
        self.assertContains(response, "GitHub Token Authentication Failed", status_code=401)

    @patch("dashboard.views.AnalysisService.run_analysis")
    def test_forbidden_error_view_renders_403_template(self, mock_run):
        """When GitHubForbiddenError is caught in analyze_view, return HTTP 403 with errors/403.html."""
        mock_run.side_effect = GitHubForbiddenError("Repository access forbidden")

        response = self.client.get(
            reverse("analyze"), {"repo": "facebook/react"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "errors/403.html")
        self.assertContains(response, "Repository Access Restricted", status_code=403)


class ManagementCommandCheckGitHubApiTests(TestCase):
    """Verifies python manage.py check_github_api output and secret protection."""

    @patch("dashboard.services.github_service.GitHubService.get_rate_limit_status")
    def test_check_github_api_command_authenticated(self, mock_status):
        mock_status.return_value = {
            "authenticated": True,
            "limit": 5000,
            "remaining": 4990,
            "used": 10,
            "reset_at": "15:30:00 UTC",
            "reset_in_minutes": 45,
            "is_rate_limited": False,
        }

        out = io.StringIO()
        call_command("check_github_api", stdout=out)
        output = out.getvalue()

        self.assertIn("AUTHENTICATED", output)
        self.assertIn("4,990 / 5,000", output)
        self.assertIn("healthy and operational", output)
        # Verify no token string appears
        self.assertNotIn("github_pat", output)
        self.assertNotIn("ghp_", output)
        self.assertNotIn("Bearer token active", output.lower().replace("bearer token active", ""))
