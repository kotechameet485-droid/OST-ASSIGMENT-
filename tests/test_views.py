"""
End-to-end integration tests for OpenSourceLens views.
Expanded for Stage 2 Advanced Repository Analytics.
"""

from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from dashboard.models import Repository, RepositoryAnalysis


class ViewIntegrationTests(TestCase):
    """Test full HTTP request/response lifecycles."""

    def setUp(self):
        self.client = Client()

    def test_home_view_status_code(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')
        self.assertContains(response, 'OpenSourceLens')
        self.assertContains(response, 'Understand Any')

    def test_history_view_empty_and_populated(self):
        # Empty history
        response = self.client.get(reverse('history'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'history.html')
        self.assertContains(response, 'No Repositories Found')

        # Populated history
        repo = Repository.objects.create(
            owner='pallets',
            name='flask',
            full_name='pallets/flask',
            description='A simple framework for building web applications.',
            url='https://github.com/pallets/flask',
            stars=67000,
            forks=16000,
            watchers=2100,
            open_issues=12,
            created_at='2010-04-06T11:11:59Z',
            updated_at='2026-10-01T12:00:00Z',
            default_branch='main',
            license='BSD 3-Clause',
        )
        RepositoryAnalysis.objects.create(
            repository=repo,
            stars=67000,
            forks=16000,
            open_issues=12,
            health_score=86,
            health_tier='Excellent',
        )

        response = self.client.get(reverse('history'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'pallets/flask')
        self.assertContains(response, '86 / 100')

    def test_history_view_search_and_sort(self):
        r1 = Repository.objects.create(
            owner='facebook', name='react', full_name='facebook/react',
            url='https://github.com/facebook/react', stars=225000, forks=45000,
            open_issues=1000, created_at='2013-05-24T16:15:54Z', updated_at='2026-10-01T12:00:00Z',
        )
        r2 = Repository.objects.create(
            owner='vuejs', name='core', full_name='vuejs/core',
            url='https://github.com/vuejs/core', stars=45000, forks=8000,
            open_issues=200, created_at='2013-05-24T16:15:54Z', updated_at='2026-10-01T12:00:00Z',
        )
        RepositoryAnalysis.objects.create(repository=r1, health_score=90)
        RepositoryAnalysis.objects.create(repository=r2, health_score=82)

        # Search filter
        response = self.client.get(reverse('history') + '?q=react')
        self.assertContains(response, 'facebook/react')
        self.assertNotContains(response, 'vuejs/core')

        # Sort by stars
        response_sort = self.client.get(reverse('history') + '?sort=stars')
        self.assertEqual(response_sort.status_code, 200)

    def test_history_detail_view(self):
        repo = Repository.objects.create(
            owner='django', name='django', full_name='django/django',
            url='https://github.com/django/django', stars=80000, forks=32000,
            open_issues=150, created_at='2012-01-01T00:00:00Z', updated_at='2026-10-01T12:00:00Z',
        )
        RepositoryAnalysis.objects.create(repository=repo, health_score=88, activity_score=90)
        RepositoryAnalysis.objects.create(repository=repo, health_score=90, activity_score=92)

        response = self.client.get(reverse('history_detail', kwargs={'owner': 'django', 'repo': 'django'}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'history_detail.html')
        self.assertContains(response, 'Historical Health Score Progression')
        self.assertContains(response, 'django/django')

    def test_compare_view_empty_and_valid(self):
        # Empty comparison
        response = self.client.get(reverse('compare'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'compare.html')
        self.assertContains(response, 'Select Repositories to Compare')

        # Valid comparison with 2 repos in DB
        r1 = Repository.objects.create(
            owner='pallets', name='flask', full_name='pallets/flask',
            url='https://github.com/pallets/flask', stars=67000, forks=16000,
            open_issues=12, created_at='2010-04-06T11:11:59Z', updated_at='2026-10-01T12:00:00Z',
            license='BSD-3-Clause',
        )
        r2 = Repository.objects.create(
            owner='django', name='django', full_name='django/django',
            url='https://github.com/django/django', stars=80000, forks=32000,
            open_issues=150, created_at='2012-01-01T00:00:00Z', updated_at='2026-10-01T12:00:00Z',
            license='BSD-3-Clause',
        )
        RepositoryAnalysis.objects.create(repository=r1, health_score=85, activity_score=90)
        RepositoryAnalysis.objects.create(repository=r2, health_score=88, activity_score=92)

        response = self.client.get(reverse('compare') + '?repo1=pallets/flask&repo2=django/django')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Comparative Metrics Matrix')
        self.assertContains(response, 'pallets/flask')
        self.assertContains(response, 'django/django')

    def test_about_view(self):
        response = self.client.get(reverse('about'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'about.html')
        self.assertContains(response, 'System Data Pipeline')

    @patch('dashboard.services.github_service.GitHubService.get_pull_requests')
    @patch('dashboard.services.github_service.GitHubService.get_issues')
    @patch('dashboard.services.github_service.GitHubService.get_commits')
    @patch('dashboard.services.github_service.GitHubService.get_contributors')
    @patch('dashboard.services.github_service.GitHubService.get_languages')
    @patch('dashboard.services.github_service.GitHubService.get_repository')
    def test_analyze_view_successful_flow(
        self, mock_repo, mock_langs, mock_contrib, mock_commits, mock_issues, mock_prs
    ):
        mock_repo.return_value = {
            'id': 12345,
            'owner': 'facebook',
            'name': 'react',
            'full_name': 'facebook/react',
            'description': 'React UI library',
            'url': 'https://github.com/facebook/react',
            'stars': 225000,
            'forks': 45000,
            'watchers': 6700,
            'open_issues': 1100,
            'created_at': '2013-05-24T16:15:54Z',
            'updated_at': '2026-10-02T10:00:00Z',
            'pushed_at': '2026-10-02T09:30:00Z',
            'default_branch': 'main',
            'license': 'MIT License',
            'subscribers_count': 6700,
            'is_archived': False,
            'is_fork': False,
        }
        mock_langs.return_value = {'JavaScript': 1000000, 'HTML': 50000}
        mock_contrib.return_value = [{'username': 'gaearon', 'contributions': 2000, 'avatar_url': '', 'profile_url': ''}]
        mock_commits.return_value = [
            {'sha': 'a1b2c3d', 'author': 'Dan', 'message': 'Fix commit', 'date': '2026-10-01T12:00:00Z'}
        ]
        mock_issues.return_value = [
            {'issue_number': 1, 'title': 'Issue 1', 'state': 'open', 'created_at': '2026-09-01T00:00:00Z', 'closed_at': None}
        ]
        mock_prs.return_value = [
            {'pr_number': 10, 'title': 'PR 10', 'state': 'merged', 'created_at': '2026-09-01T00:00:00Z', 'closed_at': None, 'merged_at': '2026-09-02T00:00:00Z'}
        ]

        response = self.client.post(reverse('analyze'), {'repository': 'facebook/react'})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard.html')
        self.assertContains(response, 'facebook/react')
        self.assertContains(response, '225K')
        self.assertContains(response, '5-Pillar Health Score Breakdown')
        self.assertContains(response, 'Commit Activity & Time-Series Velocity')
        self.assertContains(response, 'Issue Analytics')
        self.assertContains(response, 'Pull Request Analytics')

        # Verify DB records created
        self.assertTrue(Repository.objects.filter(full_name='facebook/react').exists())
        self.assertTrue(RepositoryAnalysis.objects.filter(repository__full_name='facebook/react').exists())

    def test_analyze_invalid_input_redirects_home(self):
        response = self.client.post(reverse('analyze'), {'repository': 'facebook'})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('home'))

    @patch('dashboard.services.github_service.GitHubService.get_pull_requests')
    @patch('dashboard.services.github_service.GitHubService.get_issues')
    @patch('dashboard.services.github_service.GitHubService.get_commits')
    @patch('dashboard.services.github_service.GitHubService.get_contributors')
    @patch('dashboard.services.github_service.GitHubService.get_languages')
    @patch('dashboard.services.github_service.GitHubService.get_repository')
    def test_analyze_view_with_window_parameter(
        self, mock_repo, mock_langs, mock_contrib, mock_commits, mock_issues, mock_prs
    ):
        mock_repo.return_value = {
            'id': 12346, 'owner': 'pallets', 'name': 'flask', 'full_name': 'pallets/flask',
            'stars': 68000, 'forks': 16000, 'open_issues': 20, 'created_at': '2010-04-06T11:11:59Z',
            'updated_at': '2026-10-01T12:00:00Z', 'pushed_at': '2026-10-01T12:00:00Z',
            'default_branch': 'main', 'license': 'BSD-3-Clause', 'is_archived': False, 'is_fork': False,
        }
        mock_langs.return_value = {'Python': 500000}
        mock_contrib.return_value = [{'username': 'mitsuhiko', 'contributions': 1500}]
        mock_commits.return_value = [{'sha': 'f1', 'author': 'Armin', 'message': 'Flask commit', 'date': '2026-09-15T00:00:00Z'}]
        mock_issues.return_value = []
        mock_prs.return_value = []

        response = self.client.post(reverse('analyze'), {'repository': 'pallets/flask', 'window': '180d'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'pallets/flask')
        # Check that analysis window was recorded in snapshot
        analysis = RepositoryAnalysis.objects.filter(repository__full_name='pallets/flask').latest('analyzed_at')
        self.assertEqual(analysis.analysis_window, '180d')

    @patch('dashboard.services.github_service.GitHubService.get_pull_requests')
    @patch('dashboard.services.github_service.GitHubService.get_issues')
    @patch('dashboard.services.github_service.GitHubService.get_commits')
    @patch('dashboard.services.github_service.GitHubService.get_contributors')
    @patch('dashboard.services.github_service.GitHubService.get_languages')
    @patch('dashboard.services.github_service.GitHubService.get_repository')
    def test_analyze_view_caching_and_force_refresh(
        self, mock_repo, mock_langs, mock_contrib, mock_commits, mock_issues, mock_prs
    ):
        mock_repo.return_value = {
            'id': 12347, 'owner': 'django', 'name': 'django', 'full_name': 'django/django',
            'stars': 80000, 'forks': 32000, 'open_issues': 100, 'created_at': '2012-01-01T00:00:00Z',
            'updated_at': '2026-10-01T12:00:00Z', 'pushed_at': '2026-10-01T12:00:00Z',
            'default_branch': 'main', 'license': 'BSD-3-Clause', 'is_archived': False, 'is_fork': False,
        }
        mock_langs.return_value = {'Python': 900000}
        mock_contrib.return_value = [{'username': 'carljm', 'contributions': 800}]
        mock_commits.return_value = [{'sha': 'd1', 'author': 'Carl', 'message': 'Django commit', 'date': '2026-09-20T00:00:00Z'}]
        mock_issues.return_value = []
        mock_prs.return_value = []

        # 1. First call fetches from GitHub
        response1 = self.client.post(reverse('analyze'), {'repository': 'django/django'})
        self.assertEqual(response1.status_code, 200)
        self.assertEqual(mock_repo.call_count, 1)

        # 2. Second call within cache window reuses cached analysis without hitting API
        response2 = self.client.get(reverse('analyze') + '?repository=django/django')
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(mock_repo.call_count, 1)  # Still 1, reused cache

        # 3. Force refresh triggers new API fetch
        response3 = self.client.get(reverse('analyze') + '?repository=django/django&refresh=true')
        self.assertEqual(response3.status_code, 200)
        self.assertEqual(mock_repo.call_count, 2)  # Fetched again

    @patch('dashboard.services.github_service.GitHubService.get_repository')
    def test_analyze_view_rate_limit_error_handling(self, mock_repo):
        from dashboard.services.github_service import GitHubRateLimitError
        mock_repo.side_effect = GitHubRateLimitError("GitHub API rate limit exceeded.", reset_timestamp=1791234567)

        response = self.client.post(reverse('analyze'), {'repository': 'facebook/react'}, follow=True)
        self.assertEqual(response.status_code, 429)
        self.assertTemplateUsed(response, 'rate_limit.html')
        self.assertContains(response, 'Rate Limit', status_code=429)

    @patch('dashboard.services.github_service.GitHubService.get_repository')
    def test_analyze_view_timeout_error_handling(self, mock_repo):
        from dashboard.services.github_service import GitHubTimeoutError
        mock_repo.side_effect = GitHubTimeoutError("GitHub request timed out.")

        response = self.client.post(reverse('analyze'), {'repository': 'facebook/react'}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')
        self.assertContains(response, 'timed out')

    @patch('dashboard.services.github_service.GitHubService.get_repository')
    def test_analyze_view_not_found_error_handling(self, mock_repo):
        from dashboard.services.github_service import GitHubAPIError
        mock_repo.side_effect = GitHubAPIError("Repository 'nonexistent/repo' not found on GitHub.", status_code=404)

        response = self.client.post(reverse('analyze'), {'repository': 'nonexistent/repo'}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')
        self.assertContains(response, 'not found')


class EdgeCaseRepositoryTests(TestCase):
    """
    Test suite for edge case repositories explicitly mandated in Section 46:
    - Repository with 0 issues
    - Repository with 0 PRs
    - Repository with 1 contributor
    - Repository with many contributors
    - Repository with no recent commits
    - Archived repository
    - Forked repository
    - Very new repository
    - facebook/react, pallets/flask, django/django benchmarks
    """

    def setUp(self):
        self.client = Client()

    @patch('dashboard.services.github_service.GitHubService.get_pull_requests')
    @patch('dashboard.services.github_service.GitHubService.get_issues')
    @patch('dashboard.services.github_service.GitHubService.get_commits')
    @patch('dashboard.services.github_service.GitHubService.get_contributors')
    @patch('dashboard.services.github_service.GitHubService.get_languages')
    @patch('dashboard.services.github_service.GitHubService.get_repository')
    def test_repository_with_zero_issues_and_zero_prs(
        self, mock_repo, mock_langs, mock_contrib, mock_commits, mock_issues, mock_prs
    ):
        mock_repo.return_value = {
            'id': 99001, 'owner': 'clean', 'name': 'minimal', 'full_name': 'clean/minimal',
            'stars': 100, 'forks': 5, 'open_issues': 0, 'created_at': '2025-01-01T00:00:00Z',
            'updated_at': '2026-09-01T00:00:00Z', 'pushed_at': '2026-09-01T00:00:00Z',
            'default_branch': 'main', 'license': 'MIT', 'is_archived': False, 'is_fork': False,
        }
        mock_langs.return_value = {'Python': 10000}
        mock_contrib.return_value = [{'username': 'cleaner', 'contributions': 10}]
        mock_commits.return_value = [{'sha': 'c0', 'author': 'Dev', 'message': 'init', 'date': '2026-09-01T00:00:00Z'}]
        mock_issues.return_value = []
        mock_prs.return_value = []

        response = self.client.post(reverse('analyze'), {'repository': 'clean/minimal'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Insufficient issue history')
        self.assertContains(response, 'No pull request activity recorded')
        self.assertContains(response, 'clean/minimal')

    @patch('dashboard.services.github_service.GitHubService.get_pull_requests')
    @patch('dashboard.services.github_service.GitHubService.get_issues')
    @patch('dashboard.services.github_service.GitHubService.get_commits')
    @patch('dashboard.services.github_service.GitHubService.get_contributors')
    @patch('dashboard.services.github_service.GitHubService.get_languages')
    @patch('dashboard.services.github_service.GitHubService.get_repository')
    def test_repository_with_single_contributor(
        self, mock_repo, mock_langs, mock_contrib, mock_commits, mock_issues, mock_prs
    ):
        mock_repo.return_value = {
            'id': 99002, 'owner': 'solo', 'name': 'project', 'full_name': 'solo/project',
            'stars': 42, 'forks': 2, 'open_issues': 1, 'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2026-09-01T00:00:00Z', 'pushed_at': '2026-09-01T00:00:00Z',
            'default_branch': 'main', 'license': 'Apache-2.0', 'is_archived': False, 'is_fork': False,
        }
        mock_langs.return_value = {'Rust': 50000}
        mock_contrib.return_value = [{'username': 'lone_coder', 'contributions': 500}]
        mock_commits.return_value = [{'sha': 's1', 'author': 'lone_coder', 'message': 'commit', 'date': '2026-09-01T00:00:00Z'}]
        mock_issues.return_value = [{'issue_number': 1, 'title': 'Solo issue', 'state': 'open', 'created_at': '2026-09-01T00:00:00Z', 'closed_at': None}]
        mock_prs.return_value = []

        response = self.client.post(reverse('analyze'), {'repository': 'solo/project'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'solo/project')
        self.assertContains(response, 'lone_coder')
        self.assertContains(response, 'High maintainer concentration')

    @patch('dashboard.services.github_service.GitHubService.get_pull_requests')
    @patch('dashboard.services.github_service.GitHubService.get_issues')
    @patch('dashboard.services.github_service.GitHubService.get_commits')
    @patch('dashboard.services.github_service.GitHubService.get_contributors')
    @patch('dashboard.services.github_service.GitHubService.get_languages')
    @patch('dashboard.services.github_service.GitHubService.get_repository')
    def test_repository_with_many_contributors(
        self, mock_repo, mock_langs, mock_contrib, mock_commits, mock_issues, mock_prs
    ):
        mock_repo.return_value = {
            'id': 99003, 'owner': 'big', 'name': 'ecosystem', 'full_name': 'big/ecosystem',
            'stars': 10000, 'forks': 2000, 'open_issues': 50, 'created_at': '2020-01-01T00:00:00Z',
            'updated_at': '2026-10-01T00:00:00Z', 'pushed_at': '2026-10-01T00:00:00Z',
            'default_branch': 'main', 'license': 'MIT', 'is_archived': False, 'is_fork': False,
        }
        mock_langs.return_value = {'Go': 80000, 'Shell': 20000}
        # 30 contributors
        mock_contrib.return_value = [{'username': f'dev_{i}', 'contributions': 10} for i in range(30)]
        mock_commits.return_value = [{'sha': f'm{i}', 'author': f'dev_{i}', 'message': f'msg {i}', 'date': '2026-09-01T00:00:00Z'} for i in range(10)]
        mock_issues.return_value = [{'issue_number': 1, 'title': 'issue', 'state': 'closed', 'created_at': '2026-09-01T00:00:00Z', 'closed_at': '2026-09-02T00:00:00Z'}]
        mock_prs.return_value = [{'pr_number': 1, 'title': 'pr', 'state': 'merged', 'created_at': '2026-09-01T00:00:00Z', 'closed_at': None, 'merged_at': '2026-09-02T00:00:00Z'}]

        response = self.client.post(reverse('analyze'), {'repository': 'big/ecosystem'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'big/ecosystem')
        self.assertContains(response, 'Well-distributed maintainer base')

    @patch('dashboard.services.github_service.GitHubService.get_pull_requests')
    @patch('dashboard.services.github_service.GitHubService.get_issues')
    @patch('dashboard.services.github_service.GitHubService.get_commits')
    @patch('dashboard.services.github_service.GitHubService.get_contributors')
    @patch('dashboard.services.github_service.GitHubService.get_languages')
    @patch('dashboard.services.github_service.GitHubService.get_repository')
    def test_archived_and_forked_repository(
        self, mock_repo, mock_langs, mock_contrib, mock_commits, mock_issues, mock_prs
    ):
        mock_repo.return_value = {
            'id': 99004, 'owner': 'legacy', 'name': 'old-tool', 'full_name': 'legacy/old-tool',
            'stars': 500, 'forks': 50, 'open_issues': 10, 'created_at': '2015-01-01T00:00:00Z',
            'updated_at': '2021-01-01T00:00:00Z', 'pushed_at': '2020-05-01T00:00:00Z',
            'default_branch': 'master', 'license': 'GPL-3.0', 'is_archived': True, 'is_fork': True,
        }
        mock_langs.return_value = {'C': 40000}
        mock_contrib.return_value = [{'username': 'retired_dev', 'contributions': 100}]
        # No recent commits in months/years
        mock_commits.return_value = [{'sha': 'old1', 'author': 'dev', 'message': 'final commit', 'date': '2020-05-01T00:00:00Z'}]
        mock_issues.return_value = []
        mock_prs.return_value = []

        response = self.client.post(reverse('analyze'), {'repository': 'legacy/old-tool'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'legacy/old-tool')
        self.assertContains(response, 'Archived')
        self.assertContains(response, 'Fork')

    @patch('dashboard.services.github_service.GitHubService.get_pull_requests')
    @patch('dashboard.services.github_service.GitHubService.get_issues')
    @patch('dashboard.services.github_service.GitHubService.get_commits')
    @patch('dashboard.services.github_service.GitHubService.get_contributors')
    @patch('dashboard.services.github_service.GitHubService.get_languages')
    @patch('dashboard.services.github_service.GitHubService.get_repository')
    def test_very_new_repository(
        self, mock_repo, mock_langs, mock_contrib, mock_commits, mock_issues, mock_prs
    ):
        now_str = '2026-10-02T12:00:00Z'
        mock_repo.return_value = {
            'id': 99005, 'owner': 'fresh', 'name': 'starter', 'full_name': 'fresh/starter',
            'stars': 1, 'forks': 0, 'open_issues': 0, 'created_at': now_str,
            'updated_at': now_str, 'pushed_at': now_str,
            'default_branch': 'main', 'license': None, 'is_archived': False, 'is_fork': False,
        }
        mock_langs.return_value = {}
        mock_contrib.return_value = [{'username': 'founder', 'contributions': 1}]
        mock_commits.return_value = [{'sha': 'new1', 'author': 'founder', 'message': 'first commit', 'date': now_str}]
        mock_issues.return_value = []
        mock_prs.return_value = []

        response = self.client.post(reverse('analyze'), {'repository': 'fresh/starter'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'fresh/starter')
        self.assertContains(response, 'No language data returned by GitHub.')

