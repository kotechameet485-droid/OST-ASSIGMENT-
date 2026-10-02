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
