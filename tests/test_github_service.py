"""
Tests for GitHub API Service layer with mocked HTTP responses.
"""

from unittest.mock import patch, MagicMock
from django.test import TestCase
import requests

from dashboard.services.github_service import (
    GitHubService,
    GitHubRepoNotFoundError,
    GitHubRateLimitExceededError,
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
        }
        mock_get.return_value = mock_response

        data = self.service.get_repository('facebook', 'react')
        self.assertEqual(data['full_name'], 'facebook/react')
        self.assertEqual(data['stars'], 225000)
        self.assertEqual(data['forks'], 45000)
        self.assertEqual(data['license'], 'MIT License')

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
        mock_response.headers = {'x-ratelimit-remaining': '0'}
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
