"""
Analysis Service for OpenSourceLens.
Coordinates GitHub REST API ingestion, database synchronization,
Pandas analytics computation, caching, and historical snapshot generation.
Uses atomic database transactions to ensure consistency.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple

from django.conf import settings
from django.db import transaction
from django.utils.dateparse import parse_datetime, parse_date

from dashboard.models import (
    Repository,
    Language,
    Contributor,
    CommitActivity,
    Issue,
    PullRequest,
    RepositoryAnalysis,
)
from dashboard.services.github_service import (
    GitHubService,
    GitHubAPIError,
    GitHubInvalidRepoError,
    GitHubRepoNotFoundError,
    GitHubRateLimitExceededError,
)
from dashboard.analytics.analytics_engine import AnalyticsEngine, format_metric_number

logger = logging.getLogger(__name__)


class AnalysisService:
    """
    Central orchestration service for repository intelligence.
    """

    WINDOW_MAPPINGS = {
        '30d': {'days': 30, 'label': 'Last 30 Days'},
        '90d': {'days': 90, 'label': 'Last 90 Days'},
        '180d': {'days': 180, 'label': 'Last 6 Months'},
        '365d': {'days': 365, 'label': 'Last 1 Year'},
    }

    def __init__(self, github_service: Optional[GitHubService] = None):
        self.github_service = github_service or GitHubService()
        self.freshness_minutes = getattr(settings, 'ANALYSIS_CACHE_FRESHNESS_MINUTES', 60)

    def _get_window_cutoff(self, window_key: str) -> Tuple[datetime, str]:
        """
        Calculates the UTC cutoff timestamp and human-readable label for the given window.
        """
        config = self.WINDOW_MAPPINGS.get(window_key, self.WINDOW_MAPPINGS['90d'])
        cutoff = datetime.now(timezone.utc) - timedelta(days=config['days'])
        return cutoff, config['label']

    def is_cached_fresh(self, repo_obj: Repository, window: str) -> bool:
        """
        Determines whether the repository has a recently computed analysis snapshot.
        """
        if not repo_obj or not repo_obj.fetched_at:
            return False

        # Verify a snapshot exists matching the requested window
        latest_analysis = repo_obj.analyses.filter(analysis_window=window).order_by('-analyzed_at').first()
        if not latest_analysis or not latest_analysis.analyzed_at:
            return False

        now = datetime.now(timezone.utc)
        age_seconds = (now - latest_analysis.analyzed_at).total_seconds()
        return age_seconds <= (self.freshness_minutes * 60)

    def run_analysis(
        self,
        owner: str,
        repo_name: str,
        window: str = '90d',
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Executes a complete repository analysis:
        1. Checks database freshness unless force_refresh is requested.
        2. Ingests data from GitHub REST API with real pagination.
        3. Normalizes and computes Pandas metrics.
        4. Synchronizes database tables inside transaction.atomic().
        5. Returns structured dashboard payload with coverage transparency.
        """
        full_name = f"{owner}/{repo_name}"
        window = window if window in self.WINDOW_MAPPINGS else '90d'
        cutoff_dt, window_label = self._get_window_cutoff(window)
        cutoff_iso = cutoff_dt.isoformat()

        # Check existing database state for caching
        db_repo = Repository.objects.filter(full_name__iexact=full_name).first()
        is_reused_from_cache = False

        if db_repo and not force_refresh and self.is_cached_fresh(db_repo, window):
            logger.info(f"Reusing fresh cached analysis for {full_name} ({window})")
            return self._build_dashboard_context_from_db(db_repo, window, window_label)

        # Step 1: Fetch fresh data from GitHub REST API
        logger.info(f"Ingesting fresh data from GitHub for {full_name} (Window: {window})")
        repo_data = self.github_service.get_repository(owner, repo_name)
        languages_raw = self.github_service.get_languages(owner, repo_name)
        contributors_raw = self.github_service.get_contributors(owner, repo_name, limit=30)
        commits_raw = self.github_service.get_commits(owner, repo_name, limit=100, since=cutoff_iso)
        issues_raw = self.github_service.get_issues(owner, repo_name, limit=100, since=cutoff_iso)
        prs_raw = self.github_service.get_pull_requests(owner, repo_name, limit=100, since=cutoff_iso)

        # Step 2: Run Pandas Analytics & Health Scoring
        language_stats = AnalyticsEngine.calculate_language_statistics(languages_raw)
        language_dist = AnalyticsEngine.calculate_language_distribution(languages_raw)
        commit_stats = AnalyticsEngine.calculate_commit_statistics(commits_raw, analysis_window=window)
        issue_stats = AnalyticsEngine.calculate_issue_statistics(
            issues_raw,
            total_repo_open_issues=repo_data['open_issues']
        )
        pr_stats = AnalyticsEngine.calculate_pr_statistics(prs_raw)
        contributor_stats = AnalyticsEngine.calculate_contributor_statistics(contributors_raw)

        health_metrics = AnalyticsEngine.calculate_health_score(
            repo_data=repo_data,
            languages_data=languages_raw,
            contributors=contributors_raw,
            commit_stats=commit_stats,
            issue_stats=issue_stats,
            pr_stats=pr_stats,
            contrib_stats=contributor_stats,
        )

        coverage_summary = {
            'window': window,
            'window_label': window_label,
            'commits_analyzed': commit_stats['total_analyzed'],
            'issues_analyzed': issue_stats['total_analyzed'],
            'prs_analyzed': pr_stats['total_analyzed'],
            'contributors_recorded': contributor_stats['total_recorded'],
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }

        # Step 3: Compute trend and assemble initial dashboard payload
        past_analyses = db_repo.analyses.order_by('analyzed_at') if db_repo else RepositoryAnalysis.objects.none()
        health_trend = AnalyticsEngine.calculate_historical_trend(past_analyses)

        dashboard_payload = self._assemble_dashboard_payload(
            repo_data=repo_data,
            language_stats=language_stats,
            language_dist=language_dist,
            health_metrics=health_metrics,
            contributors_raw=contributors_raw,
            contributor_stats=contributor_stats,
            commit_stats=commit_stats,
            issue_stats=issue_stats,
            pr_stats=pr_stats,
            health_trend=health_trend,
            coverage_summary=coverage_summary,
            window=window,
            from_cache=False,
            issues_raw=issues_raw,
            prs_raw=prs_raw,
        )

        # Step 4: Atomic Database Synchronization & Snapshot Storage
        repo_obj = self._synchronize_database(
            repo_data=repo_data,
            language_stats=language_stats,
            contributors_raw=contributors_raw,
            commits_raw=commits_raw,
            issues_raw=issues_raw,
            prs_raw=prs_raw,
            health_metrics=health_metrics,
            commit_stats=commit_stats,
            issue_stats=issue_stats,
            pr_stats=pr_stats,
            contributor_stats=contributor_stats,
            coverage_summary=coverage_summary,
            window=window,
            snapshot_payload=dashboard_payload,
        )

        # Step 5: Refresh Historical Trend with the freshly saved snapshot
        past_analyses = repo_obj.analyses.order_by('analyzed_at')
        fresh_health_trend = AnalyticsEngine.calculate_historical_trend(past_analyses)
        dashboard_payload['health_trend'] = fresh_health_trend
        if 'chart_payloads' in dashboard_payload:
            dashboard_payload['chart_payloads']['health_trend'] = {
                'labels': fresh_health_trend['labels'],
                'scores': fresh_health_trend['scores'],
                'stars': fresh_health_trend['stars'],
                'activity_scores': fresh_health_trend.get('activity_scores', []),
                'issue_scores': fresh_health_trend.get('issue_scores', []),
                'pr_scores': fresh_health_trend.get('pr_scores', []),
                'contributor_scores': fresh_health_trend.get('contributor_scores', []),
                'maintenance_scores': fresh_health_trend.get('maintenance_scores', []),
            }

        return dashboard_payload

    def _synchronize_database(
        self,
        repo_data: Dict[str, Any],
        language_stats: list,
        contributors_raw: list,
        commits_raw: list,
        issues_raw: list,
        prs_raw: list,
        health_metrics: Dict[str, Any],
        commit_stats: Dict[str, Any],
        issue_stats: Dict[str, Any],
        pr_stats: Dict[str, Any],
        contributor_stats: Dict[str, Any],
        coverage_summary: Dict[str, Any],
        window: str,
        snapshot_payload: Optional[Dict[str, Any]] = None,
    ) -> Repository:
        """
        Synchronizes all repository entities inside an isolated atomic database transaction.
        Prunes stale child records belonging to the current analysis so old window data does not linger.
        Stores an immutable snapshot_payload on the created RepositoryAnalysis record.
        """
        with transaction.atomic():
            created_dt = parse_datetime(repo_data['created_at']) if repo_data.get('created_at') else None
            updated_dt = parse_datetime(repo_data['updated_at']) if repo_data.get('updated_at') else None
            pushed_dt = parse_datetime(repo_data.get('pushed_at')) if repo_data.get('pushed_at') else None

            # Primary Repository record
            repo_obj, _ = Repository.objects.update_or_create(
                full_name=repo_data['full_name'],
                defaults={
                    'owner': repo_data.get('owner', repo_data['full_name'].split('/')[0]),
                    'name': repo_data.get('name', repo_data['full_name'].split('/')[1]),
                    'description': repo_data.get('description') or '',
                    'url': repo_data.get('url') or f"https://github.com/{repo_data['full_name']}",
                    'stars': repo_data.get('stars', 0),
                    'forks': repo_data.get('forks', 0),
                    'watchers': repo_data.get('watchers', 0),
                    'open_issues': repo_data.get('open_issues', 0),
                    'created_at': created_dt or datetime.now(timezone.utc),
                    'updated_at': updated_dt or datetime.now(timezone.utc),
                    'pushed_at': pushed_dt,
                    'default_branch': repo_data.get('default_branch', 'main'),
                    'license': repo_data.get('license') or 'Not specified',
                    'license_spdx': repo_data.get('license_spdx', 'NOASSERTION'),
                    'language': repo_data.get('language') or 'Not specified',
                    'size': repo_data.get('size', 0),
                    'topics': repo_data.get('topics', []),
                    'is_archived': repo_data.get('is_archived', False),
                    'is_fork': repo_data.get('is_fork', False),
                    'has_issues': repo_data.get('has_issues', True),
                    'has_wiki': repo_data.get('has_wiki', False),
                    'has_pages': repo_data.get('has_pages', False),
                    'subscribers_count': repo_data.get('subscribers_count', 0),
                    'network_count': repo_data.get('network_count', 0),
                }
            )

            # Synchronize languages: delete stale, create fresh
            Language.objects.filter(repository=repo_obj).delete()
            languages_to_create = [
                Language(
                    repository=repo_obj,
                    language=lang['language'],
                    bytes=lang['bytes'],
                    percentage=lang['percentage'],
                )
                for lang in language_stats
            ]
            Language.objects.bulk_create(languages_to_create)

            # Synchronize top contributors: update existing, remove stale
            if contributors_raw is not None:
                active_usernames = {c['username'] for c in contributors_raw if c.get('username')}
                Contributor.objects.filter(repository=repo_obj).exclude(username__in=active_usernames).delete()
                for c in contributors_raw:
                    Contributor.objects.update_or_create(
                        repository=repo_obj,
                        username=c['username'],
                        defaults={
                            'contributions': c.get('contributions', 0),
                            'avatar_url': c.get('avatar_url'),
                            'profile_url': c.get('profile_url'),
                        }
                    )

            # Synchronize commit activities: clean up stale days outside the window
            if commits_raw is not None:
                daily_counts = {}
                for c in commits_raw:
                    date_str = c.get('date')
                    if date_str:
                        d = date_str[:10]
                        daily_counts[d] = daily_counts.get(d, 0) + 1
                current_dates = set()
                for d_str, cnt in daily_counts.items():
                    p_date = parse_date(d_str)
                    if p_date:
                        current_dates.add(p_date)
                        CommitActivity.objects.update_or_create(
                            repository=repo_obj,
                            date=p_date,
                            defaults={'commit_count': cnt}
                        )
                CommitActivity.objects.filter(repository=repo_obj).exclude(date__in=current_dates).delete()

            # Synchronize issues: update/create current, and remove stale issues not present in current analysis
            if issues_raw is not None:
                current_issue_numbers = {
                    (iss.get('issue_number') or iss.get('number'))
                    for iss in issues_raw
                    if (iss.get('issue_number') or iss.get('number')) is not None
                }
                Issue.objects.filter(repository=repo_obj).exclude(issue_number__in=current_issue_numbers).delete()
                for iss in issues_raw:
                    i_num = iss.get('issue_number') or iss.get('number')
                    if not i_num:
                        continue
                    c_at = iss.get('created_at')
                    cls_at = iss.get('closed_at')
                    Issue.objects.update_or_create(
                        repository=repo_obj,
                        issue_number=i_num,
                        defaults={
                            'title': iss.get('title', ''),
                            'state': iss.get('state', 'open'),
                            'created_at': parse_datetime(c_at) if isinstance(c_at, str) else (c_at or datetime.now(timezone.utc)),
                            'closed_at': parse_datetime(cls_at) if isinstance(cls_at, str) else cls_at,
                        }
                    )

            # Synchronize pull requests: update/create current, and remove stale PRs not in current analysis
            if prs_raw is not None:
                current_pr_numbers = {
                    (pr.get('pr_number') or pr.get('number'))
                    for pr in prs_raw
                    if (pr.get('pr_number') or pr.get('number')) is not None
                }
                PullRequest.objects.filter(repository=repo_obj).exclude(pr_number__in=current_pr_numbers).delete()
                for pr in prs_raw:
                    p_num = pr.get('pr_number') or pr.get('number')
                    if not p_num:
                        continue
                    c_at = pr.get('created_at')
                    cls_at = pr.get('closed_at')
                    m_at = pr.get('merged_at')
                    PullRequest.objects.update_or_create(
                        repository=repo_obj,
                        pr_number=p_num,
                        defaults={
                            'title': pr.get('title', ''),
                            'state': pr.get('state', 'open'),
                            'created_at': parse_datetime(c_at) if isinstance(c_at, str) else (c_at or datetime.now(timezone.utc)),
                            'closed_at': parse_datetime(cls_at) if isinstance(cls_at, str) else cls_at,
                            'merged_at': parse_datetime(m_at) if isinstance(m_at, str) else m_at,
                        }
                    )

            # Create immutable Historical Analysis Snapshot
            json_safe_payload = {}
            if snapshot_payload:
                import json
                from django.core.serializers.json import DjangoJSONEncoder
                json_safe_payload = json.loads(json.dumps(snapshot_payload, cls=DjangoJSONEncoder))

            RepositoryAnalysis.objects.create(
                repository=repo_obj,
                analysis_window=window,
                stars=repo_data['stars'],
                forks=repo_data['forks'],
                open_issues=repo_data['open_issues'],
                health_score=health_metrics['total_score'],
                health_tier=health_metrics['health_tier'],
                activity_score=health_metrics['scores']['activity'],
                issue_score=health_metrics['scores']['issue_management'],
                pr_score=health_metrics['scores']['pr_activity'],
                contributor_score=health_metrics['scores']['contributor_diversity'],
                maintenance_score=health_metrics['scores']['maintenance'],
                commits_count=commit_stats['total_analyzed'],
                contributors_count=contributor_stats['total_recorded'],
                prs_count=pr_stats['total_analyzed'],
                issue_resolution_rate=issue_stats['resolution_rate'],
                pr_merge_rate=pr_stats['merge_rate'],
                data_coverage=coverage_summary,
                snapshot_payload=json_safe_payload,
            )

        return repo_obj

    def _build_dashboard_context_from_db(
        self,
        repo_obj: Repository,
        window: str,
        window_label: str
    ) -> Dict[str, Any]:
        """
        Reconstructs the dashboard analytics payload from existing database records.
        Prioritizes the immutable snapshot_payload stored on RepositoryAnalysis for this window.
        If a legacy record lacks snapshot_payload, filters child models strictly by the window cutoff.
        """
        # Step 1: Check for stored snapshot payload for this window
        latest_analysis = repo_obj.analyses.filter(analysis_window=window).order_by('-analyzed_at').first()
        if latest_analysis and latest_analysis.snapshot_payload:
            payload = dict(latest_analysis.snapshot_payload)
            payload['is_cached'] = True
            payload['current_window'] = window
            payload['analysis_window'] = window
            if 'coverage' in payload and 'data_coverage' not in payload:
                payload['data_coverage'] = payload['coverage']
            elif 'data_coverage' in payload and 'coverage' not in payload:
                payload['coverage'] = payload['data_coverage']
            if 'health' in payload and isinstance(payload['health'], dict):
                h = payload['health']
                payload.setdefault('health_score', h.get('total_score', latest_analysis.health_score))
                payload.setdefault('health_tier', h.get('health_tier', latest_analysis.health_tier))
                payload.setdefault('components', h.get('components', {}))
                payload.setdefault('pillar_breakdowns', h.get('pillar_breakdowns', {}))
            payload['analyzed_at'] = latest_analysis.analyzed_at

            # Recalculate historical trend dynamically across all snapshots
            past_analyses = repo_obj.analyses.order_by('analyzed_at')
            health_trend = AnalyticsEngine.calculate_historical_trend(past_analyses)
            payload['health_trend'] = health_trend
            if 'chart_payloads' in payload and isinstance(payload['chart_payloads'], dict):
                chart_payloads = dict(payload['chart_payloads'])
                chart_payloads['health_trend'] = {
                    'labels': health_trend['labels'],
                    'scores': health_trend['scores'],
                    'stars': health_trend['stars'],
                    'activity_scores': health_trend.get('activity_scores', []),
                    'issue_scores': health_trend.get('issue_scores', []),
                    'pr_scores': health_trend.get('pr_scores', []),
                    'contributor_scores': health_trend.get('contributor_scores', []),
                    'maintenance_scores': health_trend.get('maintenance_scores', []),
                }
                payload['chart_payloads'] = chart_payloads
            return payload

        # Step 2: Fallback reconstruction for legacy snapshots (Strict window cutoff filtering)
        cutoff_dt, _ = self._get_window_cutoff(window)
        cutoff_date = cutoff_dt.date()

        repo_data = {
            'owner': repo_obj.owner,
            'name': repo_obj.name,
            'full_name': repo_obj.full_name,
            'description': repo_obj.description or '',
            'url': repo_obj.url,
            'stars': repo_obj.stars,
            'forks': repo_obj.forks,
            'watchers': repo_obj.watchers,
            'open_issues': repo_obj.open_issues,
            'created_at': repo_obj.created_at.isoformat() if repo_obj.created_at else '',
            'updated_at': repo_obj.updated_at.isoformat() if repo_obj.updated_at else '',
            'pushed_at': repo_obj.pushed_at.isoformat() if repo_obj.pushed_at else '',
            'default_branch': repo_obj.default_branch,
            'license': repo_obj.license or 'Not specified',
            'license_spdx': repo_obj.license_spdx,
            'language': repo_obj.language,
            'size': repo_obj.size,
            'topics': repo_obj.topics,
            'is_archived': repo_obj.is_archived,
            'is_fork': repo_obj.is_fork,
            'has_issues': repo_obj.has_issues,
            'has_wiki': repo_obj.has_wiki,
            'has_pages': repo_obj.has_pages,
            'subscribers_count': repo_obj.subscribers_count,
            'network_count': repo_obj.network_count,
        }

        # Query child records
        languages_db = repo_obj.languages.all()
        lang_dict = {l.language: l.bytes for l in languages_db}
        language_stats = AnalyticsEngine.calculate_language_statistics(lang_dict)
        language_dist = AnalyticsEngine.calculate_language_distribution(lang_dict)

        contributors_db = repo_obj.contributors.all()
        contributors_raw = [
            {
                'username': c.username,
                'contributions': c.contributions,
                'avatar_url': c.avatar_url,
                'profile_url': c.profile_url,
            }
            for c in contributors_db
        ]
        contributor_stats = AnalyticsEngine.calculate_contributor_statistics(contributors_raw)

        # Commits: strictly filter by window cutoff date
        commits_db = repo_obj.commit_activities.filter(date__gte=cutoff_date)
        commits_reconstructed = []
        for ca in commits_db:
            for _ in range(ca.commit_count):
                commits_reconstructed.append({
                    'sha': 'cached',
                    'message': 'Recorded commit',
                    'author': 'Contributor',
                    'date': ca.date.isoformat(),
                })
        commit_stats = AnalyticsEngine.calculate_commit_statistics(commits_reconstructed, analysis_window=window)

        # Issues & PRs: strictly filter by window cutoff datetime
        issues_db = repo_obj.issues.filter(created_at__gte=cutoff_dt)
        issues_raw = [
            {
                'issue_number': i.issue_number,
                'title': i.title,
                'state': i.state,
                'created_at': i.created_at.isoformat() if i.created_at else None,
                'closed_at': i.closed_at.isoformat() if i.closed_at else None,
            }
            for i in issues_db
        ]
        issue_stats = AnalyticsEngine.calculate_issue_statistics(issues_raw, total_repo_open_issues=repo_obj.open_issues)

        prs_db = repo_obj.pull_requests.filter(created_at__gte=cutoff_dt)
        prs_raw = [
            {
                'pr_number': p.pr_number,
                'title': p.title,
                'state': p.state,
                'created_at': p.created_at.isoformat() if p.created_at else None,
                'closed_at': p.closed_at.isoformat() if p.closed_at else None,
                'merged_at': p.merged_at.isoformat() if p.merged_at else None,
            }
            for p in prs_db
        ]
        pr_stats = AnalyticsEngine.calculate_pr_statistics(prs_raw)

        health_metrics = AnalyticsEngine.calculate_health_score(
            repo_data=repo_data,
            languages_data=lang_dict,
            contributors=contributors_raw,
            commit_stats=commit_stats,
            issue_stats=issue_stats,
            pr_stats=pr_stats,
            contrib_stats=contributor_stats,
        )

        coverage_summary = {
            'window': window,
            'window_label': window_label,
            'commits_analyzed': commit_stats['total_analyzed'],
            'issues_analyzed': issue_stats['total_analyzed'],
            'prs_analyzed': pr_stats['total_analyzed'],
            'contributors_recorded': contributor_stats['total_recorded'],
            'generated_at': repo_obj.fetched_at.isoformat() if repo_obj.fetched_at else '',
            'reused_from_cache': True,
        }

        health_trend = AnalyticsEngine.calculate_historical_trend(repo_obj.analyses.order_by('analyzed_at'))

        return self._assemble_dashboard_payload(
            repo_data=repo_data,
            language_stats=language_stats,
            language_dist=language_dist,
            health_metrics=health_metrics,
            contributors_raw=contributors_raw,
            contributor_stats=contributor_stats,
            commit_stats=commit_stats,
            issue_stats=issue_stats,
            pr_stats=pr_stats,
            health_trend=health_trend,
            coverage_summary=coverage_summary,
            window=window,
            from_cache=True,
            issues_raw=issues_raw,
            prs_raw=prs_raw,
        )

    def _assemble_dashboard_payload(
        self,
        repo_data: Dict[str, Any],
        language_stats: list,
        language_dist: Dict[str, Any],
        health_metrics: Dict[str, Any],
        contributors_raw: list,
        contributor_stats: Dict[str, Any],
        commit_stats: Dict[str, Any],
        issue_stats: Dict[str, Any],
        pr_stats: Dict[str, Any],
        health_trend: Dict[str, Any],
        coverage_summary: Dict[str, Any],
        window: str,
        from_cache: bool = False,
        issues_raw: Optional[list] = None,
        prs_raw: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        Assembles all formatted metrics and JSON payloads for the template render.
        """
        formatted_metrics = {
            'stars': format_metric_number(repo_data.get('stars', 0)),
            'forks': format_metric_number(repo_data.get('forks', 0)),
            'watchers': format_metric_number(repo_data.get('watchers', 0)),
            'open_issues': format_metric_number(repo_data.get('open_issues', 0)),
            'subscribers': format_metric_number(repo_data.get('subscribers_count', 0)),
            'commits_analyzed': format_metric_number(commit_stats['total_analyzed']),
            'contributors_recorded': format_metric_number(contributor_stats['total_recorded']),
            'prs_analyzed': format_metric_number(pr_stats['total_analyzed']),
        }

        chart_payloads = {
            'commit_trend': {
                'labels_30d': commit_stats['trend_labels_30d'],
                'data_30d': commit_stats['trend_data_30d'],
                'labels_90d': commit_stats['trend_labels_90d'],
                'data_90d': commit_stats['trend_data_90d'],
                'labels_6m': commit_stats['trend_labels_6m'],
                'data_6m': commit_stats['trend_data_6m'],
                'labels_1y': commit_stats.get('trend_labels_1y', []),
                'data_1y': commit_stats.get('trend_data_1y', []),
            },
            'issues_trend': {
                'labels': issue_stats['trend_labels'],
                'opened': issue_stats['opened_trend'],
                'closed': issue_stats['closed_trend'],
            },
            'prs_status': {
                'labels': pr_stats['chart_labels'],
                'data': pr_stats['chart_data'],
            },
            'languages': {
                'labels': language_dist['chart_labels'],
                'data': language_dist['chart_data'],
                'colors': language_dist['chart_colors'],
            },
            'contributors': {
                'labels': contributor_stats['chart_labels'],
                'data': contributor_stats['chart_data'],
            },
            'health_trend': {
                'labels': health_trend['labels'],
                'scores': health_trend['scores'],
                'stars': health_trend['stars'],
                'activity_scores': health_trend.get('activity_scores', []),
                'issue_scores': health_trend.get('issue_scores', []),
                'pr_scores': health_trend.get('pr_scores', []),
                'contributor_scores': health_trend.get('contributor_scores', []),
                'maintenance_scores': health_trend.get('maintenance_scores', []),
            },
        }

        return {
            'repo': repo_data,
            'metrics': formatted_metrics,
            'languages': language_stats,
            'language_dist': language_dist,
            'health': health_metrics,
            'health_score': health_metrics.get('total_score', 0),
            'health_tier': health_metrics.get('health_tier', 'Moderate'),
            'components': health_metrics.get('components', {}),
            'pillar_breakdowns': health_metrics.get('pillar_breakdowns', {}),
            'analyzed_at': datetime.now(timezone.utc),
            'contributors': contributors_raw,
            'contributor_stats': contributor_stats,
            'commit_stats': commit_stats,
            'issue_stats': issue_stats,
            'pr_stats': pr_stats,
            'health_trend': health_trend,
            'chart_payloads': chart_payloads,
            'coverage': coverage_summary,
            'data_coverage': coverage_summary,
            'issues_sample': issues_raw or [],
            'prs_sample': prs_raw or [],
            'current_window': window,
            'analysis_window': window,
            'is_cached': from_cache,
        }
