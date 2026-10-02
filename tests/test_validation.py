"""
Tests for repository input validation.
"""

from django.test import TestCase
from dashboard.services.github_service import GitHubService, GitHubInvalidRepoError
from dashboard.forms import RepositorySearchForm


class RepositoryValidationTests(TestCase):
    """Test repository name format validation and form cleaning."""

    def test_valid_repository_formats(self):
        valid_cases = [
            ("facebook/react", ("facebook", "react")),
            ("tensorflow/tensorflow", ("tensorflow", "tensorflow")),
            ("vuejs/core", ("vuejs", "core")),
            ("pallets/flask", ("pallets", "flask")),
            ("django/django", ("django", "django")),
            ("https://github.com/facebook/react", ("facebook", "react")),
            ("https://github.com/facebook/react.git", ("facebook", "react")),
            ("http://github.com/owner/repo", ("owner", "repo")),
        ]
        for raw, expected in valid_cases:
            with self.subTest(raw=raw):
                owner, repo = GitHubService.validate_and_normalize(raw)
                self.assertEqual((owner, repo), expected)

    def test_invalid_repository_formats(self):
        invalid_cases = [
            "facebook",
            "hello/world/test",
            "",
            "   ",
            "owner//repo",
            "/owner/repo",
            "owner/repo/",
            "invalid name with spaces/repo",
            "owner/name with spaces",
            "owner$",
        ]
        for raw in invalid_cases:
            with self.subTest(raw=raw):
                with self.assertRaises(GitHubInvalidRepoError):
                    GitHubService.validate_and_normalize(raw)

    def test_repository_search_form_valid(self):
        form = RepositorySearchForm(data={'repository': 'facebook/react'})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['repository'], 'facebook/react')

    def test_repository_search_form_invalid(self):
        form = RepositorySearchForm(data={'repository': 'facebook'})
        self.assertFalse(form.is_valid())
        self.assertIn('repository', form.errors)
