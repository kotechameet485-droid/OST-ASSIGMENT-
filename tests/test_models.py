"""
Tests for OpenSourceLens database models and relationships.
"""

from datetime import datetime, timezone
from django.test import TestCase
from dashboard.models import (
    Repository,
    Contributor,
    CommitActivity,
    Issue,
    PullRequest,
    Language,
)


class DatabaseModelTests(TestCase):
    """Test model creation, relationships, and queries."""

    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.repo = Repository.objects.create(
            owner='facebook',
            name='react',
            full_name='facebook/react',
            description='A declarative, efficient library for building UIs.',
            url='https://github.com/facebook/react',
            stars=225000,
            forks=45000,
            watchers=6700,
            open_issues=1100,
            created_at=self.now,
            updated_at=self.now,
            default_branch='main',
            license='MIT License',
        )

    def test_repository_creation(self):
        self.assertEqual(str(self.repo), 'facebook/react')
        self.assertEqual(self.repo.stars, 225000)
        self.assertEqual(Repository.objects.count(), 1)

    def test_language_relationship(self):
        lang = Language.objects.create(
            repository=self.repo,
            language='JavaScript',
            bytes=1500000,
            percentage=75.5,
        )
        self.assertEqual(self.repo.languages.count(), 1)
        self.assertIn('JavaScript', str(lang))

    def test_contributor_relationship(self):
        contributor = Contributor.objects.create(
            repository=self.repo,
            username='zpao',
            contributions=1800,
        )
        self.assertEqual(self.repo.contributors.count(), 1)
        self.assertEqual(contributor.username, 'zpao')

    def test_issue_and_pr_relationships(self):
        issue = Issue.objects.create(
            repository=self.repo,
            issue_number=101,
            title='Fix fiber reconcile bug',
            state='open',
            created_at=self.now,
        )
        pr = PullRequest.objects.create(
            repository=self.repo,
            pr_number=202,
            state='merged',
            created_at=self.now,
        )
        self.assertEqual(self.repo.issues.count(), 1)
        self.assertEqual(self.repo.pull_requests.count(), 1)

    def test_cascade_delete(self):
        Language.objects.create(
            repository=self.repo,
            language='TypeScript',
            bytes=500000,
            percentage=25.0,
        )
        self.assertEqual(Language.objects.count(), 1)
        self.repo.delete()
        self.assertEqual(Repository.objects.count(), 0)
        self.assertEqual(Language.objects.count(), 0)
