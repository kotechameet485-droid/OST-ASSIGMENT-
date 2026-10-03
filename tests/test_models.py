"""
Tests for OpenSourceLens database models, relationships, and constraints.
Verifies unique constraints, cascade deletion, transaction rollbacks,
and historical snapshot preservation.
"""

from datetime import datetime, timezone, date
from django.test import TestCase
from django.db import IntegrityError, transaction
from dashboard.models import (
    Repository,
    Contributor,
    CommitActivity,
    Issue,
    PullRequest,
    Language,
    RepositoryAnalysis,
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
            license_spdx='MIT',
            language='JavaScript',
            size=120000,
            topics=['javascript', 'react'],
        )

    def test_repository_creation(self):
        self.assertEqual(str(self.repo), 'facebook/react')
        self.assertEqual(self.repo.stars, 225000)
        self.assertEqual(self.repo.license_spdx, 'MIT')
        self.assertEqual(Repository.objects.count(), 1)

    def test_repository_full_name_uniqueness(self):
        with self.assertRaises(IntegrityError):
            Repository.objects.create(
                owner='facebook',
                name='react',
                full_name='facebook/react',
                url='https://github.com/facebook/react',
                created_at=self.now,
                updated_at=self.now,
            )

    def test_language_relationship_and_uniqueness(self):
        lang = Language.objects.create(
            repository=self.repo,
            language='JavaScript',
            bytes=1500000,
            percentage=75.5,
        )
        self.assertEqual(self.repo.languages.count(), 1)
        self.assertIn('JavaScript', str(lang))

        # Duplicate language for same repo should trigger IntegrityError
        with self.assertRaises(IntegrityError):
            Language.objects.create(
                repository=self.repo,
                language='JavaScript',
                bytes=200000,
                percentage=24.5,
            )

    def test_contributor_relationship_and_uniqueness(self):
        contributor = Contributor.objects.create(
            repository=self.repo,
            username='zpao',
            contributions=1800,
        )
        self.assertEqual(self.repo.contributors.count(), 1)
        self.assertEqual(contributor.username, 'zpao')

        # Duplicate contributor username for same repo
        with self.assertRaises(IntegrityError):
            Contributor.objects.create(
                repository=self.repo,
                username='zpao',
                contributions=500,
            )

    def test_commit_activity_uniqueness(self):
        today = date.today()
        CommitActivity.objects.create(
            repository=self.repo,
            date=today,
            commit_count=10,
        )
        self.assertEqual(self.repo.commit_activities.count(), 1)

        with self.assertRaises(IntegrityError):
            CommitActivity.objects.create(
                repository=self.repo,
                date=today,
                commit_count=5,
            )

    def test_issue_and_pr_relationships_and_uniqueness(self):
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

        # Duplicate issue number
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Issue.objects.create(
                    repository=self.repo,
                    issue_number=101,
                    title='Duplicate issue',
                    created_at=self.now,
                )

        # Duplicate PR number
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PullRequest.objects.create(
                    repository=self.repo,
                    pr_number=202,
                    created_at=self.now,
                )

    def test_cascade_delete(self):
        Language.objects.create(
            repository=self.repo,
            language='TypeScript',
            bytes=500000,
            percentage=25.0,
        )
        Contributor.objects.create(
            repository=self.repo,
            username='alice',
            contributions=10,
        )
        self.assertEqual(Language.objects.count(), 1)
        self.assertEqual(Contributor.objects.count(), 1)

        self.repo.delete()
        self.assertEqual(Repository.objects.count(), 0)
        self.assertEqual(Language.objects.count(), 0)
        self.assertEqual(Contributor.objects.count(), 0)

    def test_historical_snapshot_preservation(self):
        """Verify multiple snapshots accumulate chronologically without overwriting past analyses."""
        snap1 = RepositoryAnalysis.objects.create(
            repository=self.repo,
            health_score=80,
            activity_score=85,
            analysis_window='90d',
        )
        snap2 = RepositoryAnalysis.objects.create(
            repository=self.repo,
            health_score=85,
            activity_score=90,
            analysis_window='90d',
        )
        self.assertEqual(self.repo.analyses.count(), 2)
        analyses = list(self.repo.analyses.order_by('analyzed_at'))
        self.assertEqual(analyses[0].health_score, 80)
        self.assertEqual(analyses[1].health_score, 85)

    def test_transaction_rollback_on_failure(self):
        """Verify transaction rollback prevents partial state persistence if an error occurs."""
        initial_count = Repository.objects.count()

        try:
            with transaction.atomic():
                Repository.objects.create(
                    owner='test',
                    name='failed_repo',
                    full_name='test/failed_repo',
                    url='http://...',
                    created_at=self.now,
                    updated_at=self.now,
                )
                # Intentionally trigger an error
                raise RuntimeError("Simulated failure during transaction")
        except RuntimeError:
            pass

        # Verify failed_repo was rolled back completely
        self.assertEqual(Repository.objects.count(), initial_count)
        self.assertFalse(Repository.objects.filter(full_name='test/failed_repo').exists())
