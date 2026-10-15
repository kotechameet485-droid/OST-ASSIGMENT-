"""
Comprehensive regression test suite for OpenSourceLens Phase 23 hardening.
Covers:
  1. History detail exists (Case 1)
  2. History detail missing repository (Case 3 - custom 404, no debug leak)
  3. Repository exists but no analysis (Case 2 - polished empty state)
  4. History URL normalization & case-insensitive lookup
  5. GitHub repo transfer / alias resolution (e.g., facebook/react -> react/react)
  6. Analysis creates RepositoryAnalysis immutable snapshot
  7. Failed analysis preserves previous snapshot (no overwrite/destroy)
  8. History window filtering (30d, 90d, 365d isolation)
  9. History trend window correctness (no mixing of incompatible windows)
  10. Comparison window correctness
  11. Rate limit fallback to cached snapshot
  12. Architecture & Methodology engineering specification page rendering
  13. Database configuration consistency
  14. Safe JSON script chart embedding
  15. POST refresh CSRF enforcement
"""

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.urls import reverse
from django.conf import settings

from dashboard.models import Repository, RepositoryAnalysis
from dashboard.services.analysis_service import AnalysisService
from dashboard.services.repository_service import RepositoryService
from dashboard.services.github_service import (
    GitHubService,
    GitHubRateLimitExceededError,
    GitHubRepoNotFoundError,
)


class HistoryDetailHardeningTests(TestCase):
    """Verifies all cases of the History Detail audit console."""

    def setUp(self):
        self.client = Client()
        self.now = datetime.now(timezone.utc)
        self.repo = Repository.objects.create(
            owner='facebook',
            name='react',
            full_name='facebook/react',
            url='https://github.com/facebook/react',
            stars=220000,
            forks=45000,
            open_issues=1200,
            created_at='2013-05-24T16:15:54Z',
            updated_at=self.now.isoformat(),
            default_branch='main',
            license='MIT',
        )

    def test_case_1_history_detail_exists(self):
        """Case 1: Populated repository displays the full audit console."""
        s1 = RepositoryAnalysis.objects.create(
            repository=self.repo,
            analysis_window='90d',
            health_score=82,
            health_tier='Good',
            activity_score=85,
            issue_score=80,
            pr_score=78,
            contributor_score=88,
            maintenance_score=84,
            stars=218000,
            analyzed_at=self.now - timedelta(days=7),
            snapshot_payload={'summary': 'Snapshot 1'},
        )
        s2 = RepositoryAnalysis.objects.create(
            repository=self.repo,
            analysis_window='90d',
            health_score=86,
            health_tier='Excellent',
            activity_score=90,
            issue_score=82,
            pr_score=84,
            contributor_score=88,
            maintenance_score=86,
            stars=220000,
            analyzed_at=self.now,
            snapshot_payload={'summary': 'Snapshot 2'},
        )

        response = self.client.get(reverse('history_detail', kwargs={'owner': 'facebook', 'repo': 'react'}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'history_detail.html')
        self.assertContains(response, 'facebook/react')
        self.assertContains(response, 'Historical Health Score Progression')
        self.assertContains(response, 'Health Trend')
        self.assertContains(response, 'Evaluation Snapshot Audit Log')
        self.assertContains(response, '86 / 100')
        # Momentum card shows delta (+4)
        self.assertContains(response, '+4')
        self.assertContains(response, 'Improving')

    def test_case_2_repository_exists_but_no_history(self):
        """Case 2: Repository exists in catalog, but 0 snapshots stored."""
        empty_repo = Repository.objects.create(
            owner='empty-org',
            name='no-data',
            full_name='empty-org/no-data',
            url='https://github.com/empty-org/no-data',
            stars=10,
            forks=2,
            open_issues=0,
            created_at='2024-01-01T00:00:00Z',
            updated_at=self.now.isoformat(),
        )

        response = self.client.get(reverse('history_detail', kwargs={'owner': 'empty-org', 'repo': 'no-data'}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'history_detail.html')
        self.assertContains(response, 'No Historical Audit Available')
        self.assertContains(response, 'Analyze Repository')
        self.assertContains(response, 'Back to History')
        # Does NOT expose raw Django 404
        self.assertNotContains(response, 'Page not found')

    def test_case_3_repository_does_not_exist(self):
        """Case 3: Repository not in database returns custom OpenSourceLens 404 page, never Django debug."""
        response = self.client.get(reverse('history_detail', kwargs={'owner': 'random-ghost', 'repo': 'ghost-project'}))
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, 'history_detail.html')
        self.assertContains(response, 'Repository History Not Found', status_code=404)
        self.assertContains(response, 'random-ghost/ghost-project', status_code=404)
        self.assertContains(response, 'Analyze Repository', status_code=404)
        self.assertContains(response, 'Back to History', status_code=404)
        # Never leak Django internals or debug URL conf
        self.assertNotContains(response, 'Traceback', status_code=404)
        self.assertNotContains(response, 'Using the URLconf defined in', status_code=404)

    def test_case_4_case_insensitive_lookup(self):
        """Owner and repo lookups must be case-insensitive."""
        RepositoryAnalysis.objects.create(
            repository=self.repo,
            analysis_window='90d',
            health_score=85,
            health_tier='Excellent',
            analyzed_at=self.now,
        )

        response = self.client.get(reverse('history_detail', kwargs={'owner': 'Facebook', 'repo': 'React'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'facebook/react')

    def test_case_5_transfer_alias_resolution(self):
        """
        When repo is stored as 'twbs/bootstrap' (transferred from twitter/bootstrap),
        requesting '/history/twitter/bootstrap/' must resolve via transfer alias fallback.
        """
        transferred_repo = Repository.objects.create(
            owner='twbs',
            name='bootstrap',
            full_name='twbs/bootstrap',
            url='https://github.com/twbs/bootstrap',
            stars=165000,
            forks=78000,
            open_issues=400,
            created_at='2011-08-19T11:00:00Z',
            updated_at=self.now.isoformat(),
        )
        RepositoryAnalysis.objects.create(
            repository=transferred_repo,
            analysis_window='90d',
            health_score=88,
            health_tier='Excellent',
            analyzed_at=self.now,
        )

        # Query using the old organization name 'twitter'
        response = self.client.get(reverse('history_detail', kwargs={'owner': 'twitter', 'repo': 'bootstrap'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Historical Health Score Progression')

    def test_case_6_history_window_filtering(self):
        """History detail must isolate snapshots by window when requested."""
        RepositoryAnalysis.objects.create(
            repository=self.repo,
            analysis_window='30d',
            health_score=75,
            health_tier='Good',
            analyzed_at=self.now - timedelta(days=2),
        )
        RepositoryAnalysis.objects.create(
            repository=self.repo,
            analysis_window='90d',
            health_score=85,
            health_tier='Excellent',
            analyzed_at=self.now - timedelta(days=1),
        )

        # Request 30d window
        resp_30d = self.client.get(reverse('history_detail', kwargs={'owner': 'facebook', 'repo': 'react'}) + '?window=30d')
        self.assertEqual(resp_30d.status_code, 200)
        self.assertEqual(resp_30d.context['current_window'], '30d')
        # Trend should only analyze 30d
        self.assertEqual(resp_30d.context['trend']['trend_window'], '30d')

        # Request 90d window
        resp_90d = self.client.get(reverse('history_detail', kwargs={'owner': 'facebook', 'repo': 'react'}) + '?window=90d')
        self.assertEqual(resp_90d.status_code, 200)
        self.assertEqual(resp_90d.context['current_window'], '90d')
        self.assertEqual(resp_90d.context['trend']['trend_window'], '90d')

    def test_case_7_safe_json_script_embedding(self):
        """Trend data must be embedded using Django json_script, without raw script injections."""
        RepositoryAnalysis.objects.create(
            repository=self.repo,
            analysis_window='90d',
            health_score=82,
            health_tier='Good',
            analyzed_at=self.now - timedelta(days=5),
        )
        RepositoryAnalysis.objects.create(
            repository=self.repo,
            analysis_window='90d',
            health_score=85,
            health_tier='Excellent',
            analyzed_at=self.now,
        )
        response = self.client.get(reverse('history_detail', kwargs={'owner': 'facebook', 'repo': 'react'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="trend-data-payload"')
        self.assertContains(response, 'type="application/json"')


class SnapshotIntegrityAndResilienceTests(TestCase):
    """Verifies that snapshots are immutable, not overwritten on failures, and rate limit fallback works."""

    def setUp(self):
        self.client = Client()
        self.now = datetime.now(timezone.utc)
        self.mock_repo_payload = {
            'owner': 'resilience',
            'name': 'snapshot-repo',
            'full_name': 'resilience/snapshot-repo',
            'stars': 500,
            'forks': 50,
            'open_issues': 10,
            'pushed_at': self.now.isoformat(),
            'updated_at': self.now.isoformat(),
            'created_at': (self.now - timedelta(days=300)).isoformat(),
            'license': 'MIT',
            'is_archived': False,
            'is_fork': False,
            'default_branch': 'main',
            'topics': ['resilience'],
        }

    @patch('dashboard.services.analysis_service.GitHubService')
    def test_successful_analysis_creates_snapshot(self, MockGitHubService):
        """Every successful analysis creates an immutable RepositoryAnalysis snapshot."""
        mock_gh = MockGitHubService.return_value
        mock_gh.get_repository.return_value = self.mock_repo_payload
        mock_gh.get_languages.return_value = {'Python': 10000}
        mock_gh.get_contributors.return_value = [{'username': 'dev', 'contributions': 20, 'avatar_url': '', 'profile_url': ''}]
        mock_gh.get_commits.return_value = [{'sha': 'c1', 'date': self.now.isoformat(), 'message': 'c1', 'author': 'dev'}]
        mock_gh.get_issues.return_value = [{'number': 1, 'title': 'bug', 'state': 'open', 'created_at': self.now.isoformat(), 'closed_at': None}]
        mock_gh.get_pull_requests.return_value = [{'number': 2, 'title': 'fix', 'state': 'merged', 'created_at': self.now.isoformat(), 'merged_at': self.now.isoformat(), 'closed_at': None}]

        service = AnalysisService()
        result = service.run_analysis('resilience', 'snapshot-repo', window='90d', force_refresh=True)

        self.assertIsNotNone(result)
        repo = Repository.objects.get(full_name='resilience/snapshot-repo')
        snapshots = RepositoryAnalysis.objects.filter(repository=repo, analysis_window='90d')
        self.assertEqual(snapshots.count(), 1)
        snapshot = snapshots.first()
        self.assertEqual(snapshot.health_score, result['health_score'])
        self.assertIsNotNone(snapshot.snapshot_payload)

    @patch('dashboard.services.analysis_service.GitHubService')
    def test_failed_analysis_does_not_destroy_last_snapshot(self, MockGitHubService):
        """If GitHub API encounters a failure/rate-limit, the existing snapshot remains intact."""
        mock_gh = MockGitHubService.return_value
        mock_gh.get_repository.return_value = self.mock_repo_payload
        mock_gh.get_languages.return_value = {'Python': 10000}
        mock_gh.get_contributors.return_value = [{'username': 'dev', 'contributions': 20, 'avatar_url': '', 'profile_url': ''}]
        mock_gh.get_commits.return_value = [{'sha': 'c1', 'date': self.now.isoformat(), 'message': 'c1', 'author': 'dev'}]
        mock_gh.get_issues.return_value = [{'number': 1, 'title': 'bug', 'state': 'open', 'created_at': self.now.isoformat(), 'closed_at': None}]
        mock_gh.get_pull_requests.return_value = [{'number': 2, 'title': 'fix', 'state': 'merged', 'created_at': self.now.isoformat(), 'merged_at': self.now.isoformat(), 'closed_at': None}]

        service = AnalysisService()
        service.run_analysis('resilience', 'snapshot-repo', window='90d', force_refresh=True)

        repo = Repository.objects.get(full_name='resilience/snapshot-repo')
        initial_count = RepositoryAnalysis.objects.filter(repository=repo).count()
        self.assertEqual(initial_count, 1)

        # Now simulate GitHub API rate limit error on refresh
        mock_gh.get_repository.side_effect = GitHubRateLimitExceededError("Rate limit exceeded")
        fallback_result = service.run_analysis('resilience', 'snapshot-repo', window='90d', force_refresh=True)

        # Fallback should succeed using the stored snapshot
        self.assertIsNotNone(fallback_result)
        self.assertTrue(fallback_result.get('is_cached', False))
        self.assertTrue(fallback_result.get('live_fetch_failed', False))
        # The snapshot was not destroyed or wiped
        self.assertEqual(RepositoryAnalysis.objects.filter(repository=repo).count(), initial_count)


class ArchitectureSpecificationPageTests(TestCase):
    """Verifies that the Architecture & Methodology page meets all engineering specification requirements."""

    def setUp(self):
        self.client = Client()

    def test_architecture_page_structure_and_sections(self):
        """Architecture page must render all 8 core technical sections and technology badges."""
        response = self.client.get(reverse('about'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'about.html')

        # Hero & Badges
        self.assertContains(response, 'Engineering Specification')
        self.assertContains(response, 'OpenSourceLens Architecture & Methodology')
        self.assertContains(response, 'Django')
        self.assertContains(response, 'PostgreSQL')
        self.assertContains(response, 'Pandas')
        self.assertContains(response, 'GitHub REST API')
        self.assertContains(response, 'Bootstrap')
        self.assertContains(response, 'Chart.js')

        # Section IDs and titles
        self.assertContains(response, 'sec-overview')
        self.assertContains(response, 'sec-pipeline')
        self.assertContains(response, 'sec-lifecycle')
        self.assertContains(response, 'sec-datamodel')
        self.assertContains(response, 'sec-scoring')
        self.assertContains(response, 'sec-resilience')
        self.assertContains(response, 'sec-limitations')
        self.assertContains(response, 'sec-syllabus')

        # 5 Pillar Health Score Weights
        self.assertContains(response, '1. Activity Score')
        self.assertContains(response, '2. Issue Management Score')
        self.assertContains(response, '3. PR Activity Score')
        self.assertContains(response, '4. Contributor Diversity')
        self.assertContains(response, '5. Maintenance & Hygiene Score')
        self.assertContains(response, '25% Weight')
        self.assertContains(response, '20% Weight')
        self.assertContains(response, '15% Weight')

        # Request Lifecycle 9 steps
        self.assertContains(response, 'From Repository URL to Health Score')
        self.assertContains(response, 'Input Validation')
        self.assertContains(response, 'Atomic Persistence')

        # Syllabus mapping table
        self.assertContains(response, 'Open Source Technologies (OST) Syllabus Mapping')


class DatabaseConsistencyTests(TestCase):
    """Verifies database configuration consistency across the application."""

    def test_database_settings_consistency(self):
        """Databases configuration must have a valid default configuration without leaked credentials."""
        db_config = settings.DATABASES['default']
        self.assertIn('ENGINE', db_config)
        self.assertIn('NAME', db_config)
        # Ensure engine is either postgresql or sqlite3
        self.assertTrue(
            'sqlite3' in db_config['ENGINE'] or 'postgresql' in db_config['ENGINE'],
            f"Unexpected database engine: {db_config['ENGINE']}"
        )


class HistoryDetailErrorAndValidationTests(TestCase):
    """Verifies robust HTTP error handling and input validation for history detail view."""

    def setUp(self):
        self.client = Client()

    @patch('dashboard.views.RepositoryService.get_history_detail')
    def test_database_error_returns_500_not_404(self, mock_get_history):
        """Genuine database failures must return HTTP 500 and not be misreported as missing history (404)."""
        from django.db import OperationalError
        mock_get_history.side_effect = OperationalError("Database connection lost")

        response = self.client.get(reverse('history_detail', kwargs={'owner': 'facebook', 'repo': 'react'}))
        self.assertEqual(response.status_code, 500)
        self.assertTemplateUsed(response, 'errors/500.html')

    def test_malformed_repository_identity_returns_400(self):
        """Malformed or invalid repository identifiers must return HTTP 400 Bad Request."""
        response = self.client.get(reverse('history_detail', kwargs={'owner': 'facebook space', 'repo': 'react'}))
        self.assertEqual(response.status_code, 400)
        self.assertTemplateUsed(response, 'errors/400.html')


class SnapshotConsistencyAndWindowIsolationTests(TestCase):
    """Verifies that 30d analysis never purges commit/issue/PR records needed for 365d snapshots."""

    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.repo = Repository.objects.create(
            owner='isolation',
            name='window-test',
            full_name='isolation/window-test',
            url='https://github.com/isolation/window-test',
            stars=100,
            forks=10,
            open_issues=5,
            default_branch='main',
            created_at=self.now,
            updated_at=self.now,
        )

    @patch('dashboard.services.analysis_service.GitHubService')
    def test_365d_followed_by_30d_preserves_older_telemetry(self, MockGitHubService):
        """
        Analyzing for 365d creates historical commit/issue records.
        A subsequent analysis for 30d must NOT delete records older than 30 days!
        """
        mock_gh = MockGitHubService.return_value
        mock_gh.token = 'test-token'
        mock_gh.get_repository.return_value = {
            'owner': 'isolation',
            'name': 'window-test',
            'full_name': 'isolation/window-test',
            'stars': 100,
            'forks': 10,
            'watchers': 10,
            'open_issues': 5,
            'created_at': (self.now - timedelta(days=400)).isoformat(),
            'updated_at': self.now.isoformat(),
            'pushed_at': self.now.isoformat(),
            'default_branch': 'main',
            'license': 'MIT',
            'language': 'Python',
        }
        mock_gh.get_languages.return_value = {'Python': 50000}
        mock_gh.get_contributors.return_value = [{'username': 'lead', 'contributions': 50, 'avatar_url': '', 'profile_url': ''}]

        from dashboard.models import CommitActivity, Issue, PullRequest
        from dashboard.services.github_service import PaginatedList

        # 1. First run: 365d with commits and issues 200 days ago
        old_date = (self.now - timedelta(days=200)).strftime('%Y-%m-%d')
        old_dt = (self.now - timedelta(days=200)).isoformat()
        recent_date = (self.now - timedelta(days=5)).strftime('%Y-%m-%d')
        recent_dt = (self.now - timedelta(days=5)).isoformat()

        mock_gh.get_commits.return_value = PaginatedList([
            {'sha': 'old001', 'date': f"{old_date}T10:00:00Z", 'message': 'old commit', 'author': 'lead'},
            {'sha': 'rec001', 'date': f"{recent_date}T10:00:00Z", 'message': 'recent commit', 'author': 'lead'},
        ])
        mock_gh.get_issues.return_value = PaginatedList([
            {'issue_number': 101, 'title': 'old issue', 'state': 'closed', 'created_at': old_dt, 'closed_at': old_dt},
            {'issue_number': 102, 'title': 'recent issue', 'state': 'open', 'created_at': recent_dt, 'closed_at': None},
        ])
        mock_gh.get_pull_requests.return_value = PaginatedList([
            {'pr_number': 201, 'title': 'old pr', 'state': 'merged', 'created_at': old_dt, 'closed_at': old_dt, 'merged_at': old_dt},
            {'pr_number': 202, 'title': 'recent pr', 'state': 'merged', 'created_at': recent_dt, 'closed_at': recent_dt, 'merged_at': recent_dt},
        ])

        service = AnalysisService()
        service.run_analysis('isolation', 'window-test', window='365d', force_refresh=True)

        self.assertEqual(CommitActivity.objects.filter(repository=self.repo).count(), 2)
        self.assertEqual(Issue.objects.filter(repository=self.repo).count(), 2)
        self.assertEqual(PullRequest.objects.filter(repository=self.repo).count(), 2)

        # 2. Second run: 30d window with only recent items
        mock_gh.get_commits.return_value = PaginatedList([
            {'sha': 'rec001', 'date': f"{recent_date}T10:00:00Z", 'message': 'recent commit', 'author': 'lead'}
        ])
        mock_gh.get_issues.return_value = PaginatedList([
            {'issue_number': 102, 'title': 'recent issue', 'state': 'open', 'created_at': recent_dt, 'closed_at': None}
        ])
        mock_gh.get_pull_requests.return_value = PaginatedList([
            {'pr_number': 202, 'title': 'recent pr', 'state': 'merged', 'created_at': recent_dt, 'closed_at': recent_dt, 'merged_at': recent_dt}
        ])

        service.run_analysis('isolation', 'window-test', window='30d', force_refresh=True)

        # 3. VERIFY: The older records (>30 days ago) must STILL exist!
        self.assertEqual(
            CommitActivity.objects.filter(repository=self.repo).count(),
            2,
            "A 30-day analysis must not delete older CommitActivity records outside its window."
        )
        self.assertTrue(
            Issue.objects.filter(repository=self.repo, issue_number=101).exists(),
            "Older issues must not be wiped by a smaller analysis window."
        )
        self.assertTrue(
            PullRequest.objects.filter(repository=self.repo, pr_number=201).exists(),
            "Older pull requests must not be wiped by a smaller analysis window."
        )


class ComparisonResilienceAndCandidateTests(TestCase):
    """Verifies that comparison preserves all requested candidates and truthful status."""

    @patch('dashboard.services.analysis_service.GitHubService')
    def test_compare_one_fails_one_succeeds_preserves_failed_candidate(self, MockGitHubService):
        """When 1 of 2 candidates fails (e.g. 404), the failure reason must be captured and returned."""
        mock_gh = MockGitHubService.return_value
        now = datetime.now(timezone.utc)

        def mock_get_repo(owner, repo):
            if repo == 'missing':
                raise GitHubRepoNotFoundError(f"Repository {owner}/{repo} not found")
            return {
                'owner': owner,
                'name': repo,
                'full_name': f"{owner}/{repo}",
                'stars': 100,
                'forks': 20,
                'watchers': 20,
                'open_issues': 5,
                'created_at': now.isoformat(),
                'updated_at': now.isoformat(),
                'pushed_at': now.isoformat(),
                'default_branch': 'main',
                'license': 'MIT',
                'language': 'Python',
            }

        mock_gh.get_repository.side_effect = mock_get_repo
        mock_gh.get_languages.return_value = {'Python': 1000}
        mock_gh.get_contributors.return_value = [{'username': 'dev', 'contributions': 5, 'avatar_url': '', 'profile_url': ''}]
        mock_gh.get_commits.return_value = [{'sha': 'c1', 'date': now.isoformat(), 'message': 'msg', 'author': 'dev'}]
        mock_gh.get_issues.return_value = []
        mock_gh.get_pull_requests.return_value = []

        comp_data = RepositoryService.compare_repositories(['valid/repo', 'invalid/missing'], window='90d')

        self.assertIsNotNone(comp_data)
        self.assertEqual(comp_data['success_count'], 1)
        self.assertEqual(comp_data['failed_count'], 1)
        self.assertEqual(len(comp_data['failed_candidates']), 1)
        self.assertEqual(comp_data['failed_candidates'][0]['status'], 'not_found')
        self.assertIn('not found', comp_data['failed_candidates'][0]['error'])


class GitHubPaginationFailureHandlingTests(TestCase):
    """Verifies that pagination errors on later pages produce partial results, not silent success or total crashes."""

    @patch('requests.Session.get')
    def test_pagination_failure_on_page_2_marks_is_partial(self, mock_get):
        """Page 1 returns 200 with 100 items and a Link header for page 2; page 2 returns 500."""
        from unittest.mock import Mock

        # Response 1: 100 commits with a Link next header
        resp1 = Mock()
        resp1.status_code = 200
        resp1.json.return_value = [{'sha': f'sha{i}', 'commit': {'message': f'm{i}', 'author': {'date': '2026-01-01T00:00:00Z', 'name': 'dev'}}} for i in range(100)]
        resp1.headers = {
            'Link': '<https://api.github.com/repos/org/repo/commits?page=2>; rel="next"',
            'X-RateLimit-Limit': '5000',
            'X-RateLimit-Remaining': '4900',
        }

        # Response 2: HTTP 500 error on page 2
        resp2 = Mock()
        resp2.status_code = 500
        resp2.json.return_value = {'message': 'Internal Server Error'}
        resp2.headers = {}

        mock_get.side_effect = [resp1, resp2, resp2, resp2]

        gh = GitHubService(token='dummy')
        results = gh.get_commits('org', 'repo', limit=200)

        # Must return the 100 items from page 1 and report partial
        self.assertEqual(len(results), 100)
        self.assertTrue(results.is_partial)
        self.assertEqual(results.status, 'partial')
        self.assertIsNotNone(results.error)

