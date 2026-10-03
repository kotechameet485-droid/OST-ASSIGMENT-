"""
Tests for Pandas analytics engine and health scoring methodology.
Expanded for Stage 2 Advanced Repository Analytics.
"""

from datetime import datetime, timezone, timedelta
from django.test import TestCase
from dashboard.analytics.analytics_engine import (
    AnalyticsEngine,
    format_metric_number,
    format_byte_size,
)


class AnalyticsEngineTests(TestCase):
    """Test data processing and health metric calculations."""

    def test_format_metric_number(self):
        self.assertEqual(format_metric_number(500), "500")
        self.assertEqual(format_metric_number(1200), "1.2K")
        self.assertEqual(format_metric_number(245000), "245K")
        self.assertEqual(format_metric_number(1500000), "1.5M")
        self.assertEqual(format_metric_number(0), "0")
        self.assertEqual(format_metric_number(None), "0")

    def test_format_byte_size(self):
        self.assertEqual(format_byte_size(512), "512 B")
        self.assertEqual(format_byte_size(2048), "2 KB")
        self.assertEqual(format_byte_size(2097152), "2 MB")

    def test_calculate_language_statistics(self):
        languages = {
            'JavaScript': 80000,
            'TypeScript': 20000,
        }
        stats = AnalyticsEngine.calculate_language_statistics(languages)
        self.assertEqual(len(stats), 2)
        self.assertEqual(stats[0]['language'], 'JavaScript')
        self.assertEqual(stats[0]['percentage'], 80.0)
        self.assertEqual(stats[1]['language'], 'TypeScript')
        self.assertEqual(stats[1]['percentage'], 20.0)

    def test_calculate_language_distribution(self):
        languages = {
            'Python': 75000,
            'HTML': 25000,
        }
        dist = AnalyticsEngine.calculate_language_distribution(languages)
        self.assertEqual(dist['primary_language'], 'Python')
        self.assertEqual(dist['language_count'], 2)
        self.assertEqual(dist['total_bytes'], 100000)
        self.assertEqual(len(dist['chart_labels']), 2)

    def test_calculate_commit_statistics(self):
        now = datetime.now(timezone.utc)
        commits = [
            {'sha': '1', 'author': 'Alice', 'date': (now - timedelta(days=1)).isoformat()},
            {'sha': '2', 'author': 'Bob', 'date': (now - timedelta(days=1)).isoformat()},
            {'sha': '3', 'author': 'Alice', 'date': (now - timedelta(days=5)).isoformat()},
            {'sha': '4', 'author': 'Charlie', 'date': (now - timedelta(days=10)).isoformat()},
        ]
        c_stats = AnalyticsEngine.calculate_commit_statistics(commits)
        self.assertEqual(c_stats['total_analyzed'], 4)
        self.assertEqual(c_stats['days_since_latest'], 1)
        self.assertEqual(c_stats['max_commits_day'], 2)
        self.assertGreater(c_stats['commits_per_day_avg'], 0)
        self.assertEqual(len(c_stats['top_authors']), 3)
        self.assertEqual(c_stats['top_authors'][0]['author'], 'Alice')
        self.assertEqual(c_stats['top_authors'][0]['count'], 2)

    def test_calculate_commit_statistics_empty(self):
        c_stats = AnalyticsEngine.calculate_commit_statistics([])
        self.assertEqual(c_stats['total_analyzed'], 0)
        self.assertEqual(c_stats['commits_per_day_avg'], 0.0)
        self.assertIsNone(c_stats['days_since_latest'])

    def test_calculate_issue_statistics(self):
        now = datetime.now(timezone.utc)
        issues = [
            {
                'issue_number': 1,
                'title': 'Bug 1',
                'state': 'closed',
                'created_at': (now - timedelta(days=10)).isoformat(),
                'closed_at': (now - timedelta(days=5)).isoformat(),
            },
            {
                'issue_number': 2,
                'title': 'Bug 2',
                'state': 'open',
                'created_at': (now - timedelta(days=100)).isoformat(),
                'closed_at': None,
            },
            {
                'issue_number': 3,
                'title': 'Feature 3',
                'state': 'closed',
                'created_at': (now - timedelta(days=2)).isoformat(),
                'closed_at': (now - timedelta(days=1)).isoformat(),
            },
        ]
        i_stats = AnalyticsEngine.calculate_issue_statistics(issues)
        self.assertEqual(i_stats['total_analyzed'], 3)
        self.assertEqual(i_stats['open_count'], 1)
        self.assertEqual(i_stats['closed_count'], 2)
        self.assertEqual(i_stats['resolution_rate'], 66.7)
        self.assertEqual(i_stats['old_unresolved_count'], 1)  # >90 days
        self.assertIsNotNone(i_stats['avg_resolution_days'])

    def test_calculate_issue_statistics_zero_division(self):
        i_stats = AnalyticsEngine.calculate_issue_statistics([])
        self.assertEqual(i_stats['total_analyzed'], 0)
        self.assertEqual(i_stats['resolution_rate'], 0.0)
        self.assertIsNone(i_stats['avg_resolution_days'])

    def test_calculate_pr_statistics(self):
        now = datetime.now(timezone.utc)
        prs = [
            {
                'pr_number': 10,
                'title': 'Feature A',
                'state': 'merged',
                'created_at': (now - timedelta(days=3)).isoformat(),
                'merged_at': (now - timedelta(days=1)).isoformat(),
            },
            {
                'pr_number': 11,
                'title': 'Fix B',
                'state': 'open',
                'created_at': (now - timedelta(days=1)).isoformat(),
                'merged_at': None,
            },
            {
                'pr_number': 12,
                'title': 'Refactor C',
                'state': 'closed',
                'created_at': (now - timedelta(days=5)).isoformat(),
                'merged_at': None,
            },
            {
                'pr_number': 13,
                'title': 'Docs D',
                'state': 'merged',
                'created_at': (now - timedelta(hours=10)).isoformat(),
                'merged_at': (now - timedelta(hours=2)).isoformat(),
            },
        ]
        p_stats = AnalyticsEngine.calculate_pr_statistics(prs)
        self.assertEqual(p_stats['total_analyzed'], 4)
        self.assertEqual(p_stats['merged_count'], 2)
        self.assertEqual(p_stats['open_count'], 1)
        self.assertEqual(p_stats['closed_count'], 1)
        self.assertEqual(p_stats['merge_rate'], 50.0)
        self.assertEqual(p_stats['avg_merge_hours'], 28.0)
        self.assertIn("1.2 days", p_stats['avg_merge_time_display'])

    def test_calculate_pr_statistics_empty(self):
        p_stats = AnalyticsEngine.calculate_pr_statistics([])
        self.assertEqual(p_stats['total_analyzed'], 0)
        self.assertEqual(p_stats['merge_rate'], 0.0)
        self.assertEqual(p_stats['avg_merge_time_display'], 'N/A')

    def test_calculate_contributor_statistics(self):
        contributors = [
            {'username': 'lead', 'contributions': 600},
            {'username': 'dev2', 'contributions': 200},
            {'username': 'dev3', 'contributions': 100},
            {'username': 'dev4', 'contributions': 50},
            {'username': 'dev5', 'contributions': 50},
        ]
        c_stats = AnalyticsEngine.calculate_contributor_statistics(contributors)
        self.assertEqual(c_stats['total_recorded'], 5)
        self.assertEqual(c_stats['total_contributions'], 1000)
        self.assertEqual(c_stats['top1_share'], 60.0)
        self.assertEqual(c_stats['top5_share'], 100.0)
        self.assertEqual(c_stats['top_contributor']['username'], 'lead')

    def test_calculate_contributor_statistics_empty(self):
        c_stats = AnalyticsEngine.calculate_contributor_statistics([])
        self.assertEqual(c_stats['total_recorded'], 0)
        self.assertEqual(c_stats['top1_share'], 0.0)
        self.assertIsNone(c_stats['top_contributor'])

    def test_calculate_health_score_healthy_repo(self):
        repo_data = {
            'stars': 100000,
            'open_issues': 500,
            'pushed_at': '2026-10-01T12:00:00Z',
            'updated_at': '2026-10-01T12:00:00Z',
            'is_archived': False,
            'license': 'MIT License',
            'description': 'Production grade UI framework.',
        }
        contributors = [{'username': f'user{i}', 'contributions': 100} for i in range(12)]
        health = AnalyticsEngine.calculate_health_score(repo_data, contributors=contributors)

        self.assertGreaterEqual(health['total_score'], 80)
        self.assertIn(health['health_tier'], ['Good', 'Excellent'])
        self.assertEqual(len(health['components']), 5)

    def test_calculate_health_score_archived_repo(self):
        repo_data = {
            'stars': 100,
            'open_issues': 50,
            'pushed_at': '2020-01-01T00:00:00Z',
            'updated_at': '2020-01-01T00:00:00Z',
            'is_archived': True,
            'license': None,
            'description': '',
        }
        health = AnalyticsEngine.calculate_health_score(repo_data)
        self.assertLess(health['total_score'], 60)

    def test_compare_repositories(self):
        repo_a = {
            'name': 'facebook/react',
            'stars': 225000,
            'forks': 45000,
            'open_issues': 1000,
            'health_score': 88,
            'activity_score': 95,
            'issue_score': 85,
            'pr_score': 90,
            'contributor_score': 95,
            'maintenance_score': 100,
            'primary_language': 'JavaScript',
            'license': 'MIT License',
        }
        repo_b = {
            'name': 'vuejs/core',
            'stars': 45000,
            'forks': 8000,
            'open_issues': 300,
            'health_score': 86,
            'activity_score': 90,
            'issue_score': 85,
            'pr_score': 88,
            'contributor_score': 85,
            'maintenance_score': 100,
            'primary_language': 'TypeScript',
            'license': 'MIT License',
        }
        comp = AnalyticsEngine.compare_repositories([repo_a, repo_b])
        self.assertEqual(len(comp['repositories']), 2)
        self.assertEqual(len(comp['chart_labels']), 2)
        self.assertEqual(comp['stars_data'], [225000, 45000])
        self.assertEqual(comp['health_data'], [88, 86])

    def test_hhi_maintainer_concentration(self):
        """Verify HHI calculation correctly identifies high vs low concentration."""
        # 1. Monopoly maintainer (HHI = 10000)
        single = [{'username': 'solo', 'contributions': 100}]
        stats_single = AnalyticsEngine.calculate_contributor_statistics(single)
        self.assertEqual(stats_single['hhi'], 10000.0)
        self.assertEqual(stats_single['top1_share'], 100.0)
        self.assertEqual(stats_single['concentration_label'], "High maintainer concentration")

        # 2. Evenly distributed maintainers (HHI = 10 * 10^2 = 1000)
        equal_contribs = [{'username': f'dev_{i}', 'contributions': 10} for i in range(10)]
        stats_equal = AnalyticsEngine.calculate_contributor_statistics(equal_contribs)
        self.assertEqual(stats_equal['hhi'], 1000.0)
        self.assertEqual(stats_equal['concentration_label'], "Well-distributed maintainer base")

    def test_median_issue_resolution_time_handles_outliers(self):
        """Verify median resolution days is resilient against extreme outlier tickets."""
        now = datetime.now(timezone.utc)
        issues = [
            {'state': 'closed', 'created_at': (now - timedelta(days=2)).isoformat(), 'closed_at': now.isoformat()},
            {'state': 'closed', 'created_at': (now - timedelta(days=2)).isoformat(), 'closed_at': now.isoformat()},
            {'state': 'closed', 'created_at': (now - timedelta(days=2)).isoformat(), 'closed_at': now.isoformat()},
            # Massive outlier ticket open for 500 days
            {'state': 'closed', 'created_at': (now - timedelta(days=500)).isoformat(), 'closed_at': now.isoformat()},
        ]
        stats = AnalyticsEngine.calculate_issue_statistics(issues)
        # Median is 2.0 days while average is distorted to ~126.5 days
        self.assertEqual(stats['median_resolution_days'], 2.0)
        self.assertGreater(stats['avg_resolution_days'], 100.0)

    def test_commit_statistics_duplicate_shas(self):
        """Verify duplicate commit records are safely de-duplicated."""
        now = datetime.now(timezone.utc)
        commits = [
            {'sha': 'c1', 'author': 'Dev', 'date': now.isoformat()},
            {'sha': 'c1', 'author': 'Dev', 'date': now.isoformat()},
            {'sha': 'c2', 'author': 'Dev', 'date': now.isoformat()},
        ]
        stats = AnalyticsEngine.calculate_commit_statistics(commits)
        self.assertEqual(stats['total_analyzed'], 2)

    def test_single_record_edge_cases(self):
        """Verify analytics engine computes safely with exactly 1 record without dividing by zero."""
        now = datetime.now(timezone.utc)
        c_stats = AnalyticsEngine.calculate_commit_statistics([{'sha': 'x', 'author': 'A', 'date': now.isoformat()}])
        self.assertEqual(c_stats['total_analyzed'], 1)

        i_stats = AnalyticsEngine.calculate_issue_statistics([{'state': 'open', 'created_at': now.isoformat()}])
        self.assertEqual(i_stats['total_analyzed'], 1)
        self.assertEqual(i_stats['resolution_rate'], 0.0)

        p_stats = AnalyticsEngine.calculate_pr_statistics([{'state': 'merged', 'created_at': now.isoformat(), 'merged_at': now.isoformat()}])
        self.assertEqual(p_stats['total_analyzed'], 1)
        self.assertEqual(p_stats['merge_rate'], 100.0)

        l_stats = AnalyticsEngine.calculate_language_statistics({'Python': 100})
        self.assertEqual(len(l_stats), 1)
        self.assertEqual(l_stats[0]['percentage'], 100.0)
