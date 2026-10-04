"""
Comprehensive regression and hardening test suite for OpenSourceLens.
Covers:
  - Cache and analysis window isolation (30d vs 90d data isolation)
  - PR analysis window constraint & cutoff
  - Stale entity synchronization (issues, PRs, commits pruned from current snapshot)
  - Historical snapshot immutability
  - Comparison validity (no synthetic fallback scores)
  - Commit velocity: active-day vs calendar-day averages
  - Security (.env git protection, POST refresh CSRF)
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from pathlib import Path
from django.test import TestCase, Client
from django.urls import reverse
from django.conf import settings

from dashboard.models import Repository, RepositoryAnalysis, Issue, PullRequest, CommitActivity
from dashboard.services.analysis_service import AnalysisService
from dashboard.services.repository_service import RepositoryService
from dashboard.services.github_service import GitHubService
from dashboard.analytics.analytics_engine import AnalyticsEngine


class CacheAndWindowIsolationTests(TestCase):
    """Verifies that different analysis windows on the same repository never contaminate each other."""

    def setUp(self):
        self.client = Client()
        self.now = datetime.now(timezone.utc)
        self.mock_repo_payload = {
            'owner': 'hardening',
            'name': 'isolation-test',
            'full_name': 'hardening/isolation-test',
            'description': 'Window isolation verification repo',
            'stars': 120,
            'forks': 20,
            'open_issues': 5,
            'pushed_at': self.now.isoformat(),
            'updated_at': self.now.isoformat(),
            'created_at': (self.now - timedelta(days=500)).isoformat(),
            'license': 'MIT',
            'is_archived': False,
            'is_fork': False,
            'default_branch': 'main',
            'topics': ['testing', 'hardening'],
        }

    @patch('dashboard.services.analysis_service.GitHubService')
    def test_window_isolation_between_30d_and_90d(self, MockGitHubService):
        """A 30-day analysis must never contain 90-day commits or PRs, and vice versa."""
        mock_gh = MockGitHubService.return_value
        mock_gh.get_repository.return_value = self.mock_repo_payload
        mock_gh.get_languages.return_value = {'Python': 50000}
        mock_gh.get_contributors.return_value = [
            {'username': 'alice', 'contributions': 50, 'avatar_url': '', 'profile_url': ''}
        ]

        # 90d run: commits across last 70 days
        commits_90d = [
            {'sha': f'sha{i}', 'date': (self.now - timedelta(days=i * 5)).isoformat(), 'message': f'Commit {i}', 'author': 'alice'}
            for i in range(12)  # up to 55 days old
        ]
        issues_90d = [
            {'number': 1, 'title': 'Old Issue', 'state': 'closed', 'created_at': (self.now - timedelta(days=60)).isoformat(), 'closed_at': (self.now - timedelta(days=55)).isoformat()},
            {'number': 2, 'title': 'Recent Issue', 'state': 'open', 'created_at': (self.now - timedelta(days=10)).isoformat(), 'closed_at': None},
        ]
        prs_90d = [
            {'number': 101, 'title': 'Old PR', 'state': 'merged', 'created_at': (self.now - timedelta(days=50)).isoformat(), 'merged_at': (self.now - timedelta(days=48)).isoformat(), 'closed_at': None},
            {'number': 102, 'title': 'Recent PR', 'state': 'open', 'created_at': (self.now - timedelta(days=5)).isoformat(), 'merged_at': None, 'closed_at': None},
        ]

        mock_gh.get_commits.return_value = commits_90d
        mock_gh.get_issues.return_value = issues_90d
        mock_gh.get_pull_requests.return_value = prs_90d

        service = AnalysisService()
        result_90d = service.run_analysis('hardening', 'isolation-test', window='90d', force_refresh=True)
        self.assertEqual(result_90d['analysis_window'], '90d')
        self.assertEqual(result_90d['data_coverage']['commits_analyzed'], 12)

        # Now run 30d analysis: only commits within last 25 days
        commits_30d = [
            {'sha': f'sha30_{i}', 'date': (self.now - timedelta(days=i * 4)).isoformat(), 'message': f'Commit {i}', 'author': 'alice'}
            for i in range(4)  # up to 12 days old
        ]
        issues_30d = [
            {'number': 2, 'title': 'Recent Issue', 'state': 'open', 'created_at': (self.now - timedelta(days=10)).isoformat(), 'closed_at': None},
        ]
        prs_30d = [
            {'number': 102, 'title': 'Recent PR', 'state': 'open', 'created_at': (self.now - timedelta(days=5)).isoformat(), 'merged_at': None, 'closed_at': None},
        ]

        mock_gh.get_commits.return_value = commits_30d
        mock_gh.get_issues.return_value = issues_30d
        mock_gh.get_pull_requests.return_value = prs_30d

        result_30d = service.run_analysis('hardening', 'isolation-test', window='30d', force_refresh=True)
        self.assertEqual(result_30d['analysis_window'], '30d')
        self.assertEqual(result_30d['data_coverage']['commits_analyzed'], 4)
        self.assertEqual(result_30d['data_coverage']['issues_analyzed'], 1)
        self.assertEqual(result_30d['data_coverage']['prs_analyzed'], 1)

        # Crucial check: Reconstruct 90d from DB/cache - must retain its original 90d count
        cached_90d = service.run_analysis('hardening', 'isolation-test', window='90d', force_refresh=False)
        self.assertEqual(cached_90d['analysis_window'], '90d')
        self.assertEqual(cached_90d['data_coverage']['commits_analyzed'], 12)

        # Crucial check: Reconstruct 30d from DB/cache - must retain its original 30d count without 90d data
        cached_30d = service.run_analysis('hardening', 'isolation-test', window='30d', force_refresh=False)
        self.assertEqual(cached_30d['analysis_window'], '30d')
        self.assertEqual(cached_30d['data_coverage']['commits_analyzed'], 4)


class StaleRecordSynchronizationTests(TestCase):
    """Ensures old issues, PRs, and commits are pruned from current snapshot tables without corrupting history."""

    @patch('dashboard.services.analysis_service.GitHubService')
    def test_stale_records_removed_from_current_tables(self, MockGitHubService):
        mock_gh = MockGitHubService.return_value
        now = datetime.now(timezone.utc)
        mock_gh.get_repository.return_value = {
            'owner': 'sync',
            'name': 'stale-test',
            'full_name': 'sync/stale-test',
            'stars': 50,
            'forks': 5,
            'open_issues': 2,
            'pushed_at': now.isoformat(),
            'updated_at': now.isoformat(),
            'created_at': (now - timedelta(days=200)).isoformat(),
            'license': 'Apache-2.0',
            'is_archived': False,
            'is_fork': False,
            'default_branch': 'main',
            'topics': [],
        }
        mock_gh.get_languages.return_value = {'Go': 10000}
        mock_gh.get_contributors.return_value = [{'username': 'bob', 'contributions': 20, 'avatar_url': '', 'profile_url': ''}]

        # First run: Issues 1, 2, 3 and PRs 10, 20
        mock_gh.get_commits.return_value = [{'sha': 'c1', 'date': now.isoformat(), 'message': 'm1', 'author': 'bob'}]
        mock_gh.get_issues.return_value = [
            {'number': 1, 'title': 'Issue 1', 'state': 'open', 'created_at': now.isoformat(), 'closed_at': None},
            {'number': 2, 'title': 'Issue 2', 'state': 'closed', 'created_at': now.isoformat(), 'closed_at': now.isoformat()},
            {'number': 3, 'title': 'Issue 3', 'state': 'open', 'created_at': now.isoformat(), 'closed_at': None},
        ]
        mock_gh.get_pull_requests.return_value = [
            {'number': 10, 'title': 'PR 10', 'state': 'merged', 'created_at': now.isoformat(), 'merged_at': now.isoformat(), 'closed_at': None},
            {'number': 20, 'title': 'PR 20', 'state': 'open', 'created_at': now.isoformat(), 'merged_at': None, 'closed_at': None},
        ]

        service = AnalysisService()
        service.run_analysis('sync', 'stale-test', window='30d', force_refresh=True)

        repo = Repository.objects.get(full_name='sync/stale-test')
        self.assertEqual(repo.issues.count(), 3)
        self.assertEqual(repo.pull_requests.count(), 2)
        self.assertEqual(repo.analyses.count(), 1)

        # Second run: Issue 1 and PR 10 were deleted on GitHub; only Issue 2, 3 and PR 20 remain
        mock_gh.get_issues.return_value = [
            {'number': 2, 'title': 'Issue 2', 'state': 'closed', 'created_at': now.isoformat(), 'closed_at': now.isoformat()},
            {'number': 3, 'title': 'Issue 3', 'state': 'open', 'created_at': now.isoformat(), 'closed_at': None},
        ]
        mock_gh.get_pull_requests.return_value = [
            {'number': 20, 'title': 'PR 20', 'state': 'open', 'created_at': now.isoformat(), 'merged_at': None, 'closed_at': None},
        ]

        service.run_analysis('sync', 'stale-test', window='30d', force_refresh=True)

        # Current tables should have only active items
        self.assertEqual(repo.issues.count(), 2)
        self.assertFalse(repo.issues.filter(issue_number=1).exists())
        self.assertEqual(repo.pull_requests.count(), 1)
        self.assertFalse(repo.pull_requests.filter(pr_number=10).exists())

        # Historical snapshots: both snapshots preserved
        self.assertEqual(repo.analyses.count(), 2)
        first_snapshot = repo.analyses.order_by('id').first()
        self.assertIn('Issue 1', str(first_snapshot.snapshot_payload))


class ComparisonMethodologyTests(TestCase):
    """Ensures comparison uses identical windows and runs full analyses without fake fallback values."""

    @patch('dashboard.services.analysis_service.GitHubService')
    def test_comparison_runs_full_analysis_with_same_window(self, MockGitHubService):
        mock_gh = MockGitHubService.return_value
        now = datetime.now(timezone.utc)

        def mock_repo_side_effect(owner, repo):
            return {
                'owner': owner,
                'name': repo,
                'full_name': f'{owner}/{repo}',
                'stars': 100,
                'forks': 10,
                'open_issues': 2,
                'pushed_at': now.isoformat(),
                'updated_at': now.isoformat(),
                'created_at': (now - timedelta(days=300)).isoformat(),
                'license': 'MIT',
                'is_archived': False,
                'is_fork': False,
                'default_branch': 'main',
                'topics': ['framework'],
            }

        mock_gh.get_repository.side_effect = mock_repo_side_effect
        mock_gh.get_languages.return_value = {'Python': 80000}
        mock_gh.get_contributors.return_value = [{'username': 'dev', 'contributions': 30, 'avatar_url': '', 'profile_url': ''}]
        mock_gh.get_commits.return_value = [{'sha': 'c1', 'date': now.isoformat(), 'message': 'init', 'author': 'dev'}]
        mock_gh.get_issues.return_value = [{'number': 1, 'title': 'bug', 'state': 'open', 'created_at': now.isoformat(), 'closed_at': None}]
        mock_gh.get_pull_requests.return_value = [{'number': 10, 'title': 'feat', 'state': 'merged', 'created_at': now.isoformat(), 'merged_at': now.isoformat(), 'closed_at': None}]

        comp_data = RepositoryService.compare_repositories(['org1/repo1', 'org2/repo2'], window='90d')

        self.assertEqual(comp_data['analysis_window'], '90d')
        self.assertEqual(len(comp_data['repositories']), 2)

        for repo_entry in comp_data['repositories']:
            # Verify no synthetic pr_score = 80 fake fallbacks
            self.assertIsNotNone(repo_entry['health_score'])
            self.assertGreater(repo_entry['health_score'], 0)
            self.assertEqual(repo_entry['analysis_window'], '90d')
            self.assertIn('data_coverage', repo_entry)
            self.assertEqual(repo_entry['data_coverage']['commits_analyzed'], 1)


class CommitVelocityAnalyticsTests(TestCase):
    """Verifies that active-day and calendar-day averages are accurately calculated and distinguished."""

    def test_active_day_vs_calendar_day_averages(self):
        now = datetime.now(timezone.utc)
        # 10 commits all made on 1 single active day, in a 30-day window
        single_day = (now - timedelta(days=2)).isoformat()
        commits = [
            {'sha': f'c{i}', 'date': single_day, 'message': f'Commit {i}', 'author': 'alice'}
            for i in range(10)
        ]

        stats_30d = AnalyticsEngine.calculate_commit_statistics(commits, window_days=30)
        self.assertEqual(stats_30d['total_analyzed'], 10)
        self.assertEqual(stats_30d['active_days_count'], 1)
        self.assertEqual(stats_30d['commits_per_active_day'], 10.0)
        self.assertEqual(stats_30d['commits_per_calendar_day'], 0.3)

        # In a 90-day window, calendar day average should be 10 / 90 = 0.1
        stats_90d = AnalyticsEngine.calculate_commit_statistics(commits, window_days=90)
        self.assertEqual(stats_90d['commits_per_active_day'], 10.0)
        self.assertEqual(stats_90d['commits_per_calendar_day'], 0.1)


class SecurityAndPostTests(TestCase):
    """Verifies CSRF requirements for state-changing refresh and .env safety."""

    def test_gitignore_protects_env(self):
        gitignore_path = Path(settings.BASE_DIR) / '.gitignore'
        self.assertTrue(gitignore_path.exists())
        content = gitignore_path.read_text(encoding='utf-8')
        self.assertIn('.env', content)
        self.assertIn('db.sqlite3', content)

    @patch('dashboard.services.analysis_service.AnalysisService.run_analysis')
    def test_post_refresh_triggers_refresh(self, mock_run_analysis):
        mock_run_analysis.return_value = {
            'repo': MagicMock(full_name='org/repo', owner='org', name='repo'),
            'health_score': 85,
            'health_tier': 'Excellent',
            'components': {},
            'pillar_breakdowns': {},
            'commit_stats': {},
            'issue_stats': {},
            'pr_stats': {},
            'contrib_stats': {},
            'language_stats': {},
            'data_coverage': {},
            'chart_payloads': {},
            'analysis_window': '30d',
            'is_cached': False,
            'analyzed_at': datetime.now(timezone.utc),
        }
        client = Client(enforce_csrf_checks=False)
        response = client.post(reverse('analyze'), {'repo': 'org/repo', 'window': '30d', 'refresh': 'true'})
        self.assertEqual(response.status_code, 200)
        mock_run_analysis.assert_called_with('org', 'repo', window='30d', force_refresh=True)

    def test_post_refresh_requires_csrf_protection(self):
        """Verifies state-changing POST requests require CSRF token when checks are enforced."""
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse('analyze'), {'repo': 'org/repo', 'window': '30d', 'refresh': 'true'})
        self.assertEqual(response.status_code, 403)


class PullRequestWindowCutoffTests(TestCase):
    """Ensures GitHubService.get_pull_requests strictly respects date cutoffs and excludes old PRs."""

    @patch('dashboard.services.github_service.GitHubService._paginate')
    def test_pull_request_since_cutoff_excludes_older_prs(self, mock_paginate):
        now = datetime.now(timezone.utc)
        cutoff_dt = now - timedelta(days=30)
        cutoff_iso = cutoff_dt.isoformat()

        # Mock PRs in descending chronological order
        mock_paginate.return_value = [
            {'number': 101, 'title': 'Recent PR', 'state': 'open', 'created_at': (now - timedelta(days=5)).isoformat(), 'closed_at': None, 'merged_at': None},
            {'number': 102, 'title': 'Mid PR', 'state': 'closed', 'created_at': (now - timedelta(days=20)).isoformat(), 'closed_at': (now - timedelta(days=19)).isoformat(), 'merged_at': None},
            {'number': 103, 'title': 'Old PR Beyond Window', 'state': 'merged', 'created_at': (now - timedelta(days=45)).isoformat(), 'closed_at': None, 'merged_at': (now - timedelta(days=40)).isoformat()},
            {'number': 104, 'title': 'Very Old PR', 'state': 'merged', 'created_at': (now - timedelta(days=90)).isoformat(), 'closed_at': None, 'merged_at': None},
        ]

        gh_service = GitHubService()
        prs = gh_service.get_pull_requests('org', 'repo', limit=100, since=cutoff_iso)

        # Should only contain PRs within the 30-day window
        self.assertEqual(len(prs), 2)
        pr_numbers = [p['pr_number'] for p in prs]
        self.assertIn(101, pr_numbers)
        self.assertIn(102, pr_numbers)
        self.assertNotIn(103, pr_numbers)
        self.assertNotIn(104, pr_numbers)


class HistoricalWindowSeparationTests(TestCase):
    """Verifies that multiple analyses across different windows remain separate and immutable."""

    def test_snapshots_preserve_window_integrity(self):
        now = datetime.now(timezone.utc)
        repo = Repository.objects.create(
            owner='testorg',
            name='multisnap',
            full_name='testorg/multisnap',
            url='https://github.com/testorg/multisnap',
            stars=100,
            forks=20,
            open_issues=5,
            created_at=now,
            updated_at=now,
        )

        # Snapshot for 30d
        snap_30d = RepositoryAnalysis.objects.create(
            repository=repo,
            analysis_window='30d',
            stars=100,
            forks=20,
            open_issues=5,
            health_score=85,
            health_tier='Excellent',
            activity_score=90,
            issue_score=80,
            pr_score=85,
            contributor_score=75,
            maintenance_score=90,
            commits_count=15,
            contributors_count=5,
            prs_count=4,
            data_coverage={'window': '30d', 'commits_analyzed': 15},
            snapshot_payload={'window': '30d', 'commits_analyzed': 15},
        )

        # Snapshot for 90d
        snap_90d = RepositoryAnalysis.objects.create(
            repository=repo,
            analysis_window='90d',
            stars=100,
            forks=20,
            open_issues=5,
            health_score=78,
            health_tier='Good',
            activity_score=75,
            issue_score=70,
            pr_score=80,
            contributor_score=80,
            maintenance_score=90,
            commits_count=45,
            contributors_count=12,
            prs_count=18,
            data_coverage={'window': '90d', 'commits_analyzed': 45},
            snapshot_payload={'window': '90d', 'commits_analyzed': 45},
        )

        # Verify snapshots remain separate
        self.assertEqual(repo.analyses.count(), 2)
        analyses_30d = repo.analyses.filter(analysis_window='30d')
        analyses_90d = repo.analyses.filter(analysis_window='90d')

        self.assertEqual(analyses_30d.count(), 1)
        self.assertEqual(analyses_30d.first().commits_count, 15)

        self.assertEqual(analyses_90d.count(), 1)
        self.assertEqual(analyses_90d.first().commits_count, 45)

        # Check immutability: older snapshot was not modified by the creation of the newer one
        self.assertEqual(snap_30d.analysis_window, '30d')
        self.assertEqual(snap_30d.health_score, 85)


class TestDataIntegrityCases(TestCase):
    """
    Explicit regression validations for Phase 25 Data-Integrity Checks (Cases 1 - 6):
      Case 1 & 2: 30D vs 365D analysis isolation and immutability.
      Case 3: Comparison across 3 repos strictly enforces identical window (90D).
      Case 4: Missing PR telemetry does not invent synthetic metrics.
      Case 5: 30 contributors labeled as analyzed sample, not total population.
      Case 6: 100 commits labeled as analyzed sample limit, not annual total.
    """

    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.mock_repo_payload = {
            'owner': 'integrity',
            'name': 'cases-repo',
            'full_name': 'integrity/cases-repo',
            'description': 'Data integrity audit repo',
            'stars': 500,
            'forks': 80,
            'open_issues': 10,
            'pushed_at': self.now.isoformat(),
            'updated_at': self.now.isoformat(),
            'created_at': (self.now - timedelta(days=600)).isoformat(),
            'license': 'Apache-2.0',
            'is_archived': False,
            'is_fork': False,
            'default_branch': 'main',
            'topics': ['python', 'analytics'],
        }

    @patch('dashboard.services.analysis_service.GitHubService')
    def test_case_1_and_case_2_window_isolation_and_immutability(self, MockGitHubService):
        """
        CASE 1: Analyze repo for 30D, then analyze for 365D. The 30D result must remain unchanged.
        CASE 2: Analyze repo for 365D, then analyze for 30D. The 365D result must remain unchanged.
        """
        mock_gh = MockGitHubService.return_value
        mock_gh.get_repository.return_value = self.mock_repo_payload
        mock_gh.get_languages.return_value = {'Python': 90000}
        mock_gh.get_contributors.return_value = [{'username': 'maintainer', 'contributions': 60, 'avatar_url': '', 'profile_url': ''}]

        # 30D data: 6 commits
        commits_30d = [
            {'sha': f'sha30_{i}', 'date': (self.now - timedelta(days=i * 4)).isoformat(), 'message': f'Commit {i}', 'author': 'maintainer'}
            for i in range(6)
        ]
        mock_gh.get_commits.return_value = commits_30d
        mock_gh.get_issues.return_value = [{'number': 1, 'title': 'Issue 1', 'state': 'open', 'created_at': self.now.isoformat(), 'closed_at': None}]
        mock_gh.get_pull_requests.return_value = [{'number': 10, 'title': 'PR 10', 'state': 'merged', 'created_at': self.now.isoformat(), 'merged_at': self.now.isoformat(), 'closed_at': None}]

        service = AnalysisService()
        result_30d_initial = service.run_analysis('integrity', 'cases-repo', window='30d', force_refresh=True)
        initial_30d_commits = result_30d_initial['data_coverage']['commits_analyzed']
        initial_30d_score = result_30d_initial['health_score']
        self.assertEqual(initial_30d_commits, 6)

        # 365D data: 50 commits spanning entire year
        commits_365d = [
            {'sha': f'sha365_{i}', 'date': (self.now - timedelta(days=i * 7)).isoformat(), 'message': f'Commit {i}', 'author': 'maintainer'}
            for i in range(50)
        ]
        mock_gh.get_commits.return_value = commits_365d
        result_365d_initial = service.run_analysis('integrity', 'cases-repo', window='365d', force_refresh=True)
        initial_365d_commits = result_365d_initial['data_coverage']['commits_analyzed']
        initial_365d_score = result_365d_initial['health_score']
        self.assertEqual(initial_365d_commits, 50)

        # CASE 1: Retrieve 30D result again. It MUST remain completely unchanged.
        reconstructed_30d = service.run_analysis('integrity', 'cases-repo', window='30d', force_refresh=False)
        self.assertEqual(reconstructed_30d['analysis_window'], '30d')
        self.assertEqual(reconstructed_30d['data_coverage']['commits_analyzed'], initial_30d_commits)
        self.assertEqual(reconstructed_30d['health_score'], initial_30d_score)

        # CASE 2: Retrieve 365D result again. It MUST remain completely unchanged.
        reconstructed_365d = service.run_analysis('integrity', 'cases-repo', window='365d', force_refresh=False)
        self.assertEqual(reconstructed_365d['analysis_window'], '365d')
        self.assertEqual(reconstructed_365d['data_coverage']['commits_analyzed'], initial_365d_commits)
        self.assertEqual(reconstructed_365d['health_score'], initial_365d_score)

    @patch('dashboard.services.analysis_service.GitHubService')
    def test_case_3_comparison_across_three_repos_enforces_90d(self, MockGitHubService):
        """
        CASE 3: Compare Repo A, Repo B, Repo C using 90D. All must strictly use 90D.
        """
        mock_gh = MockGitHubService.return_value

        def repo_factory(owner, repo):
            return {
                'owner': owner,
                'name': repo,
                'full_name': f'{owner}/{repo}',
                'stars': 150,
                'forks': 30,
                'open_issues': 5,
                'pushed_at': self.now.isoformat(),
                'updated_at': self.now.isoformat(),
                'created_at': (self.now - timedelta(days=400)).isoformat(),
                'license': 'MIT',
                'is_archived': False,
                'is_fork': False,
                'default_branch': 'main',
                'topics': ['web'],
            }

        mock_gh.get_repository.side_effect = repo_factory
        mock_gh.get_languages.return_value = {'TypeScript': 50000}
        mock_gh.get_contributors.return_value = [{'username': 'core', 'contributions': 25, 'avatar_url': '', 'profile_url': ''}]
        mock_gh.get_commits.return_value = [{'sha': 'c1', 'date': self.now.isoformat(), 'message': 'c1', 'author': 'core'}]
        mock_gh.get_issues.return_value = [{'number': 1, 'title': 'bug', 'state': 'open', 'created_at': self.now.isoformat(), 'closed_at': None}]
        mock_gh.get_pull_requests.return_value = [{'number': 5, 'title': 'fix', 'state': 'merged', 'created_at': self.now.isoformat(), 'merged_at': self.now.isoformat(), 'closed_at': None}]

        comp = RepositoryService.compare_repositories(['org/repo-a', 'org/repo-b', 'org/repo-c'], window='90d')
        self.assertIsNotNone(comp)
        self.assertEqual(comp['analysis_window'], '90d')
        self.assertEqual(len(comp['repositories']), 3)

        for repo_entry in comp['repositories']:
            self.assertEqual(repo_entry['analysis_window'], '90d')
            self.assertEqual(repo_entry['data_coverage']['analysis_window'], '90d')

    @patch('dashboard.services.analysis_service.GitHubService')
    def test_case_4_zero_pr_telemetry_does_not_invent_fake_pr_metrics(self, MockGitHubService):
        """
        CASE 4: Remove/zero PR telemetry. Comparison must NOT invent fake PR metrics or arbitrary counts.
        """
        mock_gh = MockGitHubService.return_value
        mock_gh.get_repository.return_value = self.mock_repo_payload
        mock_gh.get_languages.return_value = {'Python': 50000}
        mock_gh.get_contributors.return_value = [{'username': 'author', 'contributions': 10, 'avatar_url': '', 'profile_url': ''}]
        mock_gh.get_commits.return_value = [{'sha': 'c1', 'date': self.now.isoformat(), 'message': 'c1', 'author': 'author'}]
        mock_gh.get_issues.return_value = [{'number': 1, 'title': 'bug', 'state': 'open', 'created_at': self.now.isoformat(), 'closed_at': None}]
        # PR telemetry is empty
        mock_gh.get_pull_requests.return_value = []

        comp = RepositoryService.compare_repositories(['integrity/cases-repo', 'integrity/cases-repo-2'], window='90d')
        self.assertIsNotNone(comp)
        repo_entry = comp['repositories'][0]

        # Verify PR count is 0 and merge rate is 0.0 - no invented PR counts
        self.assertEqual(repo_entry['prs_count'], 0)
        self.assertEqual(repo_entry['pr_merge_rate'], 0.0)
        self.assertEqual(repo_entry['data_coverage']['prs_analyzed'], 0)

    def test_case_5_contributor_sample_transparency(self):
        """
        CASE 5: Only 30 contributors are fetched. UI / data coverage must clearly state
        '30 analyzed contributors' (sample limit: 30), not claim '30 total contributors'.
        """
        contributors_30 = [{'username': f'user_{i}', 'contributions': 100 - i * 2} for i in range(30)]
        stats = AnalyticsEngine.calculate_contributor_statistics(contributors_30)

        # Must record analyzed sample size accurately
        self.assertEqual(stats['total_recorded'], 30)
        self.assertGreater(stats['hhi'], 0)
        # Verify coverage dictionary ceiling metadata
        service = AnalysisService()
        cov = service._build_coverage_payload('90d', commits_count=100, issues_count=50, prs_count=20, contribs_count=30, languages_count=3)
        self.assertEqual(cov['contributors_analyzed'], 30)
        self.assertEqual(cov['sample_limits']['contributors'], 30)

    def test_case_6_commit_sample_transparency(self):
        """
        CASE 6: 100 commits are fetched. UI / data coverage must not claim
        '100 total commits in the year' unless verified; it must report analyzed sample limit.
        """
        now = datetime.now(timezone.utc)
        commits_100 = [
            {'sha': f'c_{i}', 'date': (now - timedelta(days=i * 3)).isoformat(), 'message': f'msg {i}', 'author': 'dev'}
            for i in range(100)
        ]
        stats = AnalyticsEngine.calculate_commit_statistics(commits_100, window_days=365)
        self.assertEqual(stats['total_analyzed'], 100)

        service = AnalysisService()
        cov = service._build_coverage_payload('365d', commits_count=100, issues_count=10, prs_count=5, contribs_count=10, languages_count=2)
        self.assertEqual(cov['commits_analyzed'], 100)
        self.assertEqual(cov['sample_limits']['commits'], 100)
        self.assertEqual(cov['analysis_window'], '365d')

