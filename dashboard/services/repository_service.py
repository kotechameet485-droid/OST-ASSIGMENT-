"""
Repository Service for OpenSourceLens.
Provides business logic for catalog browsing, search & filtering,
historical audit logs, and objective multi-repository comparison.
"""

import json
import logging
from typing import List, Dict, Any, Optional

from django.db.models import Q
from dashboard.models import Repository, RepositoryAnalysis
from dashboard.analytics.analytics_engine import AnalyticsEngine, format_metric_number
from dashboard.services.github_service import GitHubService

logger = logging.getLogger(__name__)


class RepositoryService:
    """
    Handles repository catalog search, audit history, and comparative intelligence.
    """

    @classmethod
    def get_history_catalog(cls, query: str = '', sort_by: str = 'recent') -> List[Dict[str, Any]]:
        """
        Retrieves repositories from the database with annotations for:
        - Latest health score
        - Previous health score
        - Score difference / change (+X / -Y / 'First analysis')
        - Total snapshots count
        - Formatted star counts
        """
        repos = Repository.objects.prefetch_related('languages', 'analyses').all()

        if query:
            clean_q = query.strip()
            repos = repos.filter(
                Q(full_name__icontains=clean_q) |
                Q(description__icontains=clean_q) |
                Q(owner__icontains=clean_q) |
                Q(language__icontains=clean_q)
            )

        # Base database sorting
        if sort_by == 'stars':
            repos = repos.order_by('-stars')
        elif sort_by == 'name':
            repos = repos.order_by('name')
        else:  # 'recent'
            repos = repos.order_by('-fetched_at')

        catalog_items: List[Dict[str, Any]] = []

        for r in repos:
            analyses_qs = r.analyses.order_by('-analyzed_at')
            all_analyses = list(analyses_qs[:2])
            latest_analysis = all_analyses[0] if len(all_analyses) > 0 else None
            previous_analysis = all_analyses[1] if len(all_analyses) > 1 else None

            health_change = None
            if latest_analysis and previous_analysis:
                diff = latest_analysis.health_score - previous_analysis.health_score
                health_change = {
                    'value': diff,
                    'is_positive': diff > 0,
                    'is_negative': diff < 0,
                    'is_neutral': diff == 0,
                    'display': f"+{diff}" if diff > 0 else str(diff),
                }

            catalog_items.append({
                'repo': r,
                'latest_analysis': latest_analysis,
                'previous_analysis': previous_analysis,
                'health_change': health_change,
                'analyses_count': r.analyses.count(),
                'primary_language': r.language or 'Not specified',
            })

        # Memory sort for computed properties
        if sort_by == 'health':
            catalog_items.sort(
                key=lambda x: x['latest_analysis'].health_score if x['latest_analysis'] else -1,
                reverse=True
            )

        return catalog_items

    @classmethod
    def get_history_detail(cls, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves the complete audit trail and historical trend for a repository.
        """
        full_name = f"{owner}/{repo}"
        repository = Repository.objects.filter(full_name__iexact=full_name).first()
        if not repository:
            return None

        analyses = repository.analyses.order_by('-analyzed_at')
        trend_data = AnalyticsEngine.calculate_historical_trend(repository.analyses.order_by('analyzed_at'))

        return {
            'repository': repository,
            'analyses': analyses,
            'trend': trend_data,
            'trend_json': json.dumps(trend_data),
        }

    @classmethod
    def compare_repositories(cls, raw_candidates: List[str]) -> Optional[Dict[str, Any]]:
        """
        Compares 2 or 3 public GitHub repositories across health metrics,
        commit velocity, issues, pull requests, and maintainer concentration.
        Uses existing database snapshots if available, or pulls live telemetry.
        Strictly presents objective comparisons without 'winner' or 'best' declarations.
        """
        if len(raw_candidates) < 2:
            return None

        service = GitHubService()
        parsed_repos = []

        for raw in raw_candidates[:3]:
            try:
                owner, repo_name = GitHubService.validate_and_normalize(raw)
                full_name = f"{owner}/{repo_name}"

                db_repo = Repository.objects.filter(full_name__iexact=full_name).first()
                latest_analysis = db_repo.analyses.order_by('-analyzed_at').first() if db_repo else None

                if db_repo and latest_analysis:
                    primary_lang = db_repo.languages.order_by('-bytes').first()
                    parsed_repos.append({
                        'name': db_repo.full_name,
                        'owner': db_repo.owner,
                        'repo': db_repo.name,
                        'stars': db_repo.stars,
                        'stars_formatted': format_metric_number(db_repo.stars),
                        'forks': db_repo.forks,
                        'forks_formatted': format_metric_number(db_repo.forks),
                        'open_issues': db_repo.open_issues,
                        'open_issues_formatted': format_metric_number(db_repo.open_issues),
                        'health_score': latest_analysis.health_score,
                        'health_tier': latest_analysis.health_tier,
                        'activity_score': latest_analysis.activity_score,
                        'issue_score': latest_analysis.issue_score,
                        'pr_score': latest_analysis.pr_score,
                        'contributor_score': latest_analysis.contributor_score,
                        'maintenance_score': latest_analysis.maintenance_score,
                        'primary_language': primary_lang.language if primary_lang else db_repo.language or 'Not specified',
                        'license': db_repo.license or 'Not specified',
                        'commits_count': latest_analysis.commits_count,
                        'contributors_count': latest_analysis.contributors_count,
                        'hhi': latest_analysis.data_coverage.get('hhi', 'N/A') if latest_analysis.data_coverage else 'N/A',
                    })
                else:
                    # Fetch live metadata and quick score
                    r_data = service.get_repository(owner, repo_name)
                    langs_data = service.get_languages(owner, repo_name)
                    contribs_data = service.get_contributors(owner, repo_name, limit=15)
                    c_stats = AnalyticsEngine.calculate_contributor_statistics(contribs_data)
                    health = AnalyticsEngine.calculate_health_score(
                        repo_data=r_data,
                        languages_data=langs_data,
                        contributors=contribs_data,
                        contrib_stats=c_stats,
                    )
                    lang_dist = AnalyticsEngine.calculate_language_distribution(langs_data)

                    parsed_repos.append({
                        'name': r_data['full_name'],
                        'owner': r_data['owner'],
                        'repo': r_data['name'],
                        'stars': r_data['stars'],
                        'stars_formatted': format_metric_number(r_data['stars']),
                        'forks': r_data['forks'],
                        'forks_formatted': format_metric_number(r_data['forks']),
                        'open_issues': r_data['open_issues'],
                        'open_issues_formatted': format_metric_number(r_data['open_issues']),
                        'health_score': health['total_score'],
                        'health_tier': health['health_tier'],
                        'activity_score': health['scores']['activity'],
                        'issue_score': health['scores']['issue_management'],
                        'pr_score': health['scores']['pr_activity'],
                        'contributor_score': health['scores']['contributor_diversity'],
                        'maintenance_score': health['scores']['maintenance'],
                        'primary_language': lang_dist['primary_language'],
                        'license': r_data['license'],
                        'commits_count': 0,
                        'contributors_count': len(contribs_data),
                        'hhi': c_stats.get('hhi', 'N/A'),
                    })
            except Exception as e:
                logger.warning(f"Could not load repository '{raw}' for comparison: {e}")

        if len(parsed_repos) < 2:
            return None

        comparison_results = AnalyticsEngine.compare_repositories(parsed_repos)
        comparison_chart_json = json.dumps({
            'labels': comparison_results['chart_labels'],
            'stars': comparison_results['stars_data'],
            'forks': comparison_results['forks_data'],
            'health': comparison_results['health_data'],
        })

        return {
            'comparison': comparison_results,
            'chart_json': comparison_chart_json,
            'repositories': parsed_repos,
        }
