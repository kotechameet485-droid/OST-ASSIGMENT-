"""
Repository Service for OpenSourceLens.
Provides business logic for catalog browsing, search & filtering,
historical audit logs, and objective multi-repository comparison.
"""

import json
import logging
from typing import List, Dict, Any, Optional

from django.db.models import Q, Count
from dashboard.models import Repository, RepositoryAnalysis
from dashboard.analytics.analytics_engine import AnalyticsEngine, format_metric_number
from dashboard.services.github_service import GitHubService

logger = logging.getLogger(__name__)


class RepositoryService:
    """
    Handles repository catalog search, audit history, and comparative intelligence.
    """

    @classmethod
    def get_history_catalog(
        cls,
        query: str = '',
        sort_by: str = 'recent',
        window_filter: str = '',
        lang_filter: str = '',
        tier_filter: str = ''
    ) -> List[Dict[str, Any]]:
        """
        Retrieves repositories from the database with annotations for:
        - Latest health score
        - Previous health score
        - Score difference / change (+X / -Y / 'First analysis')
        - Total snapshots count (via Count annotation to prevent N+1 queries)
        - Formatted star counts
        - Server-side filtering by search query, language, analysis window, and health tier
        """
        repos = Repository.objects.annotate(analyses_total_count=Count('analyses')).prefetch_related('languages', 'analyses').all()

        if query:
            clean_q = query.strip()
            repos = repos.filter(
                Q(full_name__icontains=clean_q) |
                Q(description__icontains=clean_q) |
                Q(owner__icontains=clean_q) |
                Q(language__icontains=clean_q)
            )

        if lang_filter:
            repos = repos.filter(language__iexact=lang_filter.strip())

        if window_filter:
            repos = repos.filter(analyses__analysis_window=window_filter.strip()).distinct()

        # Base database sorting
        if sort_by == 'stars':
            repos = repos.order_by('-stars')
        elif sort_by == 'name':
            repos = repos.order_by('name')
        else:  # 'recent'
            repos = repos.order_by('-fetched_at')

        catalog_items: List[Dict[str, Any]] = []

        for r in repos:
            # Prefetched analyses sorted descending
            all_analyses = sorted(r.analyses.all(), key=lambda a: a.analyzed_at, reverse=True)
            if window_filter:
                all_analyses = [a for a in all_analyses if a.analysis_window == window_filter]

            latest_analysis = all_analyses[0] if len(all_analyses) > 0 else None
            previous_analysis = all_analyses[1] if len(all_analyses) > 1 else None

            # Optional health tier filtering
            if tier_filter and latest_analysis:
                if latest_analysis.health_tier.lower() != tier_filter.lower():
                    continue
            elif tier_filter and not latest_analysis:
                continue

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
                'analyses_count': getattr(r, 'analyses_total_count', len(all_analyses)),
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
        Uses select_related and prefetch_related for optimal query performance.
        """
        full_name = f"{owner}/{repo}"
        repository = Repository.objects.prefetch_related('analyses', 'languages').filter(full_name__iexact=full_name).first()
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
    def compare_repositories(
        cls,
        raw_candidates: List[str],
        window: str = '90d'
    ) -> Optional[Dict[str, Any]]:
        """
        Compares 2 or 3 public GitHub repositories across health metrics,
        commit velocity, issues, pull requests, and maintainer concentration.
        Always runs full, genuine AnalysisService pipeline if complete analysis
        is missing, guaranteeing identical methodology and zero invented metrics.
        Strictly presents objective comparisons without 'winner' or 'best' declarations.
        """
        if len(raw_candidates) < 2:
            return None

        from dashboard.services.analysis_service import AnalysisService
        analysis_service = AnalysisService()
        parsed_repos = []

        for raw in raw_candidates[:3]:
            try:
                owner, repo_name = GitHubService.validate_and_normalize(raw)
                full_name = f"{owner}/{repo_name}"

                # Always execute full analysis pipeline (reuses fresh cache if available)
                analysis_context = analysis_service.run_analysis(
                    owner=owner,
                    repo_name=repo_name,
                    window=window,
                    force_refresh=False
                )

                repo_d = analysis_context['repo']
                health_d = analysis_context['health']
                cov_d = analysis_context.get('coverage', {})
                c_stats = analysis_context.get('commit_stats', {})
                iss_stats = analysis_context.get('issue_stats', {})
                pr_stats = analysis_context.get('pr_stats', {})
                contrib_stats = analysis_context.get('contributor_stats', {})

                parsed_repos.append({
                    'name': repo_d['full_name'],
                    'owner': repo_d['owner'],
                    'repo': repo_d['name'],
                    'stars': repo_d['stars'],
                    'stars_formatted': format_metric_number(repo_d['stars']),
                    'forks': repo_d['forks'],
                    'forks_formatted': format_metric_number(repo_d['forks']),
                    'open_issues': repo_d['open_issues'],
                    'open_issues_formatted': format_metric_number(repo_d['open_issues']),
                    'health_score': health_d['total_score'],
                    'health_tier': health_d['health_tier'],
                    'activity_score': health_d['scores']['activity'],
                    'issue_score': health_d['scores']['issue_management'],
                    'pr_score': health_d['scores']['pr_activity'],
                    'contributor_score': health_d['scores']['contributor_diversity'],
                    'maintenance_score': health_d['scores']['maintenance'],
                    'primary_language': repo_d.get('language') or 'Not specified',
                    'license': repo_d.get('license') or 'Not specified',
                    'commits_count': c_stats.get('total_analyzed', 0),
                    'issues_count': iss_stats.get('total_analyzed', 0),
                    'prs_count': pr_stats.get('total_analyzed', 0),
                    'contributors_count': contrib_stats.get('total_recorded', 0),
                    'commits_per_active_day': c_stats.get('commits_per_active_day', 0.0),
                    'commits_per_calendar_day': c_stats.get('commits_per_calendar_day', 0.0),
                    'issue_resolution_rate': iss_stats.get('resolution_rate', 0.0),
                    'pr_merge_rate': pr_stats.get('merge_rate', 0.0),
                    'hhi': contrib_stats.get('hhi', 'N/A'),
                    'analysis_window': window,
                    'window_label': cov_d.get('window_label', 'Last 90 Days'),
                    'data_coverage': cov_d,
                })
            except Exception as e:
                logger.warning(f"Could not load full repository analysis for comparison on '{raw}': {e}")

        if len(parsed_repos) < 2:
            return None

        comparison_results = AnalyticsEngine.compare_repositories(parsed_repos)
        chart_payload = {
            'labels': comparison_results['chart_labels'],
            'stars': comparison_results['stars_data'],
            'forks': comparison_results['forks_data'],
            'health': comparison_results['health_data'],
        }
        comparison_chart_json = json.dumps(chart_payload)

        return {
            'comparison': comparison_results,
            'chart_json': comparison_chart_json,
            'comparison_chart_data': chart_payload,
            'repositories': parsed_repos,
            'window': window,
            'analysis_window': window,
        }

