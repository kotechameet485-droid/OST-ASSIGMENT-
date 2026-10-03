"""
Tests for GitHub API Service layer with mocked HTTP responses.
Verifies pagination, error handling, rate limits, timeouts, and data normalization.
"""

from unittest.mock import patch, MagicMock
from django.test import TestCase
import requests

from dashboard.services.github_service import (
    GitHubService,
    GitHubRepoNotFoundError,
    GitHubRateLimitExceededError,
    GitHubInvalidRepoError,
    GitHubAPIError,
)


class GitHubServiceTests(TestCase):
    """Unit tests for GitHub REST API client."""

    def setUp(self):
        self.service = GitHubService()

    @patch('requests.Session.get')
    def test_get_repository_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': 10270250,
            'full_name': 'facebook/react',
            'description': 'The library for web and native user interfaces.',
            'html_url': 'https://github.com/facebook/react',
            'stargazers_count': 225000,
            'forks_count': 45000,
            'watchers_count': 6700,
            'open_issues_count': 1100,
            'created_at': '2013-05-24T16:15:54Z',
            'updated_at': '2026-10-02T10:00:00Z',
            'pushed_at': '2026-10-02T09:30:00Z',
            'default_branch': 'main',
            'license': {'name': 'MIT License', 'spdx_id': 'MIT'},
            'subscribers_count': 6700,
            'archived': False,
            'fork': False,
            'topics': ['javascript', 'react', 'ui'],
        }
        mock_get.return_value = mock_response

        data = self.service.get_repository('facebook', 'react')
        self.assertEqual(data['full_name'], 'facebook/react')
        self.assertEqual(data['stars'], 225000)
        self.assertEqual(data['forks'], 45000)
        self.assertEqual(data['license'], 'MIT License')
        self.assertEqual(data['license_spdx'], 'MIT')
        self.assertIn('react', data['topics'])

    @patch('requests.Session.get')
    def test_get_repository_not_found(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = '{"message": "Not Found"}'
        mock_get.return_value = mock_response

        with self.assertRaises(GitHubRepoNotFoundError):
            self.service.get_repository('nonexistent-owner', 'nonexistent-repo')

    @patch('requests.Session.get')
    def test_get_repository_rate_limit(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.headers = {'x-ratelimit-remaining': '0', 'x-ratelimit-reset': '1893456000'}
        mock_response.text = 'API rate limit exceeded'
        mock_get.return_value = mock_response

        with self.assertRaises(GitHubRateLimitExceededError):
            self.service.get_repository('facebook', 'react')

    @patch('requests.Session.get')
    def test_get_languages(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'JavaScript': 1200000,
            'TypeScript': 600000,
            'HTML': 50000,
        }
        mock_get.return_value = mock_response

        langs = self.service.get_languages('facebook', 'react')
        self.assertIn('JavaScript', langs)
        self.assertEqual(langs['JavaScript'], 1200000)

    @patch('requests.Session.get')
    def test_connection_failure(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("Network down")
        with self.assertRaises(GitHubAPIError):
            self.service.get_repository('facebook', 'react')

    @patch('requests.Session.get')
    def test_timeout_failure(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("Read timeout")
        with self.assertRaises(GitHubAPIError):
            self.service.get_repository('facebook', 'react')

    @patch('requests.Session.get')
    def test_unauthorized_401(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = 'Bad credentials'
        mock_get.return_value = mock_response

        with self.assertRaises(GitHubAPIError) as ctx:
            self.service.get_repository('facebook', 'react')
        self.assertIn("authentication failed", str(ctx.exception).lower())

    @patch('requests.Session.get')
    def test_server_error_500(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'
        mock_get.return_value = mock_response

        with self.assertRaises(GitHubAPIError) as ctx:
            self.service.get_repository('facebook', 'react')
        self.assertIn("experiencing service difficulties", str(ctx.exception).lower())

    @patch('requests.Session.get')
    def test_malformed_json_response(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON string")
        mock_get.return_value = mock_response

        with self.assertRaises(GitHubAPIError) as ctx:
            self.service.get_repository('facebook', 'react')
        self.assertIn("unparseable response", str(ctx.exception).lower())

    # Pagination Tests (Section 4)
    @patch('requests.Session.get')
    def test_pagination_multiple_pages_commits(self, mock_get):
        """Verify pagination iterates across multiple pages until limit is reached."""
        page1 = [
            {'sha': f'sha1_{i}', 'commit': {'message': f'msg {i}', 'author': {'name': 'Author', 'date': '2026-09-01T00:00:00Z'}}}
            for i in range(100)
        ]
        page2 = [
            {'sha': f'sha2_{i}', 'commit': {'message': f'msg2 {i}', 'author': {'name': 'Author', 'date': '2026-08-01T00:00:00Z'}}}
            for i in range(50)
        ]

        resp1 = MagicMock(status_code=200)
        resp1.json.return_value = page1
        resp2 = MagicMock(status_code=200)
        resp2.json.return_value = page2

        mock_get.side_effect = [resp1, resp2]

        commits = self.service.get_commits('facebook', 'react', limit=150)
        self.assertEqual(len(commits), 150)
        self.assertEqual(mock_get.call_count, 2)

    @patch('requests.Session.get')
    def test_pagination_stops_on_empty_page(self, mock_get):
        """Verify pagination terminates cleanly when an empty page is returned."""
        page1 = [
            {'sha': 'sha_1', 'commit': {'message': 'Commit 1', 'author': {'name': 'Author', 'date': '2026-09-01T00:00:00Z'}}}
        ]
        resp1 = MagicMock(status_code=200)
        resp1.json.return_value = page1
        resp2 = MagicMock(status_code=200)
        resp2.json.return_value = []

        mock_get.side_effect = [resp1, resp2]

        commits = self.service.get_commits('facebook', 'react', limit=50)
        self.assertEqual(len(commits), 1)

    @patch('requests.Session.get')
    def test_issues_pagination_filters_prs(self, mock_get):
        """Verify get_issues strictly filters out pull requests from the issue endpoint."""
        issues_payload = [
            {'number': 101, 'title': 'Real Issue', 'state': 'open', 'created_at': '2026-09-01T00:00:00Z'},
            {'number': 102, 'title': 'PR in Issues Endpoint', 'state': 'open', 'pull_request': {'url': 'http://...'}, 'created_at': '2026-09-01T00:00:00Z'},
            {'number': 103, 'title': 'Another Real Issue', 'state': 'closed', 'created_at': '2026-09-01T00:00:00Z'},
        ]
        resp = MagicMock(status_code=200)
        resp.json.return_value = issues_payload
        mock_get.return_value = resp

        issues = self.service.get_issues('facebook', 'react', limit=50)
        self.assertEqual(len(issues), 2)
        issue_numbers = [i['issue_number'] for i in issues]
        self.assertIn(101, issue_numbers)
        self.assertIn(103, issue_numbers)
        self.assertNotIn(102, issue_numbers)

    @patch('requests.Session.get')
    def test_pull_requests_merged_state(self, mock_get):
        """Verify pull requests with merged_at timestamp receive 'merged' state."""
        prs_payload = [
            {'number': 201, 'title': 'Open PR', 'state': 'open', 'created_at': '2026-09-01T00:00:00Z'},
            {'number': 202, 'title': 'Merged PR', 'state': 'closed', 'merged_at': '2026-09-02T00:00:00Z', 'created_at': '2026-09-01T00:00:00Z'},
            {'number': 203, 'title': 'Closed PR', 'state': 'closed', 'merged_at': None, 'created_at': '2026-09-01T00:00:00Z'},
        ]
        resp = MagicMock(status_code=200)
        resp.json.return_value = prs_payload
        mock_get.return_value = resp

        prs = self.service.get_pull_requests('facebook', 'react', limit=10)
        self.assertEqual(len(prs), 3)
        self.assertEqual(prs[0]['state'], 'open')
        self.assertEqual(prs[1]['state'], 'merged')
        self.assertEqual(prs[2]['state'], 'closed')
