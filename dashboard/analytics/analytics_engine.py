"""
Analytics Engine for OpenSourceLens.
Utilizes Python & Pandas for statistical analysis, time-series aggregation,
language distributions, issue resolution rates, PR merge velocities,
contributor concentrations, and transparent repository health metrics calculation.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import pandas as pd


def format_metric_number(val: Optional[int]) -> str:
    """
    Formats large integer values to readable representations (e.g. 245K, 1.2M).
    """
    if val is None:
        return "0"
    try:
        val = int(val)
    except (ValueError, TypeError):
        return str(val)

    if val >= 1_000_000:
        return f"{val / 1_000_000:.1f}M".replace(".0M", "M")
    if val >= 1_000:
        return f"{val / 1_000:.1f}K".replace(".0K", "K")
    return str(val)


def format_byte_size(num_bytes: int) -> str:
    """
    Formats byte counts to KB, MB, or GB.
    """
    if not num_bytes:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}".replace(".0 ", " ")
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


class AnalyticsEngine:
    """
    Statistical and health computation engine backed by Pandas.
    """

    # Language visual color mapping for developer-focused UI
    LANGUAGE_COLORS = {
        'JavaScript': '#f1e05a',
        'TypeScript': '#3178c6',
        'Python': '#3572A5',
        'HTML': '#e34c26',
        'CSS': '#563d7c',
        'Rust': '#dea584',
        'Go': '#00ADD8',
        'C++': '#f34b7d',
        'C': '#555555',
        'Java': '#b07219',
        'C#': '#178600',
        'PHP': '#4F5D95',
        'Ruby': '#701516',
        'Swift': '#F05138',
        'Kotlin': '#A97BFF',
        'Shell': '#89e051',
        'Vue': '#41b883',
        'Dart': '#00B4AB',
    }

    @classmethod
    def calculate_language_statistics(cls, languages_dict: Dict[str, int]) -> List[Dict[str, Any]]:
        """
        Processes language byte counts into Pandas DataFrame to compute exact percentages.
        Maintains backward compatibility with Stage 1 tests and views.
        """
        if not languages_dict:
            return []

        df = pd.DataFrame(list(languages_dict.items()), columns=['language', 'bytes'])
        total_bytes = int(df['bytes'].sum())

        if total_bytes == 0:
            return []

        df['percentage'] = (df['bytes'] / total_bytes) * 100.0
        df = df.sort_values(by='bytes', ascending=False)

        results = []
        for _, row in df.iterrows():
            lang_name = str(row['language'])
            b_count = int(row['bytes'])
            results.append({
                'language': lang_name,
                'bytes': b_count,
                'bytes_formatted': format_byte_size(b_count),
                'percentage': round(float(row['percentage']), 1),
                'color': cls.LANGUAGE_COLORS.get(lang_name, '#94a3b8'),
            })
        return results

    @classmethod
    def calculate_language_distribution(cls, languages_dict: Dict[str, int]) -> Dict[str, Any]:
        """
        Extended language analysis returning primary language, total count,
        formatted total bytes, and Chart.js chart payloads.
        """
        items = cls.calculate_language_statistics(languages_dict)
        total_bytes = sum(item['bytes'] for item in items)
        primary_lang = items[0]['language'] if items else 'Not specified'

        return {
            'items': items,
            'primary_language': primary_lang,
            'language_count': len(items),
            'total_bytes': total_bytes,
            'total_bytes_formatted': format_byte_size(total_bytes),
            'chart_labels': [item['language'] for item in items],
            'chart_data': [item['percentage'] for item in items],
            'chart_colors': [item['color'] for item in items],
        }

    @classmethod
    def calculate_commit_statistics(cls, commits: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculates commit frequency, averages, days since latest commit,
        and time-series datasets (30d, 90d, 6m) for Chart.js.
        """
        if not commits:
            return {
                'total_analyzed': 0,
                'commits_per_day_avg': 0.0,
                'max_commits_day': 0,
                'min_commits_day': 0,
                'days_since_latest': None,
                'top_authors': [],
                'trend_labels_30d': [],
                'trend_data_30d': [],
                'trend_labels_90d': [],
                'trend_data_90d': [],
                'trend_labels_6m': [],
                'trend_data_6m': [],
                'recent_commits': [],
            }

        df = pd.DataFrame(commits)
        now = datetime.now(timezone.utc)

        # Parse commit dates safely in UTC
        df['datetime'] = pd.to_datetime(df['date'], errors='coerce', utc=True)
        df = df.dropna(subset=['datetime'])

        if df.empty:
            return {
                'total_analyzed': len(commits),
                'commits_per_day_avg': 0.0,
                'max_commits_day': 0,
                'min_commits_day': 0,
                'days_since_latest': None,
                'top_authors': [],
                'trend_labels_30d': [],
                'trend_data_30d': [],
                'trend_labels_90d': [],
                'trend_data_90d': [],
                'trend_labels_6m': [],
                'trend_data_6m': [],
                'recent_commits': commits[:10],
            }

        df = df.sort_values(by='datetime', ascending=False)
        latest_dt = df['datetime'].iloc[0]
        days_since_latest = max(0, (now - latest_dt).days)

        # Extract days, weeks, and months cleanly
        df['day'] = df['datetime'].dt.date
        naive_dt = df['datetime'].dt.tz_convert(None)
        df['week'] = naive_dt.dt.to_period('W').apply(lambda r: r.start_time.date())
        df['month'] = naive_dt.dt.to_period('M').apply(lambda r: str(r))

        daily_counts = df.groupby('day').size()
        avg_per_day = round(float(daily_counts.mean()), 1) if not daily_counts.empty else 0.0
        max_per_day = int(daily_counts.max()) if not daily_counts.empty else 0
        min_per_day = int(daily_counts.min()) if not daily_counts.empty else 0

        # Top commit authors
        author_series = df['author'].value_counts()
        top_authors = [{'author': k, 'count': int(v)} for k, v in author_series.items()][:6]

        # 30-Day Daily Trend
        cutoff_30d = (now - timedelta(days=30)).date()
        df_30d = df[df['day'] >= cutoff_30d]
        daily_30d = df_30d.groupby('day').size().to_dict()
        # Build consecutive days
        trend_labels_30d = []
        trend_data_30d = []
        for i in range(29, -1, -1):
            d = (now - timedelta(days=i)).date()
            trend_labels_30d.append(d.strftime('%b %d'))
            trend_data_30d.append(int(daily_30d.get(d, 0)))

        # 90-Day Weekly Trend
        cutoff_90d = (now - timedelta(days=90)).date()
        df_90d = df[df['day'] >= cutoff_90d]
        weekly_90d = df_90d.groupby('week').size().to_dict()
        all_weeks = sorted(list(weekly_90d.keys()))
        trend_labels_90d = [w.strftime('%b %d') for w in all_weeks]
        trend_data_90d = [int(weekly_90d[w]) for w in all_weeks]

        # 6-Month Monthly Trend
        monthly_series = df.groupby('month').size().sort_index()
        trend_labels_6m = [datetime.strptime(m, '%Y-%m').strftime('%b %Y') for m in monthly_series.index[-6:]]
        trend_data_6m = [int(v) for v in monthly_series.values[-6:]]

        return {
            'total_analyzed': len(df),
            'commits_per_day_avg': avg_per_day,
            'max_commits_day': max_per_day,
            'min_commits_day': min_per_day,
            'days_since_latest': days_since_latest,
            'top_authors': top_authors,
            'trend_labels_30d': trend_labels_30d,
            'trend_data_30d': trend_data_30d,
            'trend_labels_90d': trend_labels_90d,
            'trend_data_90d': trend_data_90d,
            'trend_labels_6m': trend_labels_6m,
            'trend_data_6m': trend_data_6m,
            'recent_commits': commits[:10],
        }

    @classmethod
    def calculate_issue_statistics(cls, issues: List[Dict[str, Any]], total_repo_open_issues: int = 0) -> Dict[str, Any]:
        """
        Calculates total issues, open vs closed, resolution rate,
        average issue resolution time, old unresolved issues (>90 days),
        and monthly opened vs closed chart datasets.
        """
        if not issues:
            return {
                'total_analyzed': 0,
                'open_count': total_repo_open_issues,
                'closed_count': 0,
                'resolution_rate': 0.0,
                'avg_resolution_days': None,
                'old_unresolved_count': 0,
                'trend_labels': [],
                'opened_trend': [],
                'closed_trend': [],
            }

        df = pd.DataFrame(issues)
        total_analyzed = len(df)
        open_count = int((df['state'] == 'open').sum()) if 'state' in df.columns else 0
        closed_count = int((df['state'] == 'closed').sum()) if 'state' in df.columns else 0

        # Safe Resolution Rate calculation
        resolution_rate = round((closed_count / total_analyzed) * 100.0, 1) if total_analyzed > 0 else 0.0

        # Average resolution time for closed issues
        avg_resolution_days = None
        df['created_dt'] = pd.to_datetime(df['created_at'], errors='coerce', utc=True)
        df['closed_dt'] = pd.to_datetime(df['closed_at'], errors='coerce', utc=True)

        closed_df = df[(df['state'] == 'closed') & df['created_dt'].notnull() & df['closed_dt'].notnull()]
        if not closed_df.empty:
            deltas = (closed_df['closed_dt'] - closed_df['created_dt']).dt.total_seconds() / 86400.0
            avg_days = deltas[deltas >= 0].mean()
            if pd.notnull(avg_days):
                avg_resolution_days = round(float(avg_days), 1)

        # Old unresolved issues (> 90 days)
        now = datetime.now(timezone.utc)
        open_df = df[df['state'] == 'open']
        old_unresolved = 0
        if not open_df.empty and 'created_dt' in open_df.columns:
            age_days = (now - open_df['created_dt']).dt.total_seconds() / 86400.0
            old_unresolved = int((age_days > 90).sum())

        # Monthly Opened vs Closed Trend
        naive_created = df['created_dt'].dt.tz_convert(None)
        naive_closed = df['closed_dt'].dt.tz_convert(None)
        df['month_created'] = naive_created.dt.to_period('M').astype(str)
        df['month_closed'] = naive_closed.dt.to_period('M').astype(str)

        all_months = sorted(list(set(df['month_created'].dropna().unique()) | set(df['month_closed'].dropna().unique())))[-6:]
        opened_by_month = df.groupby('month_created').size().to_dict()
        closed_by_month = df[df['state'] == 'closed'].groupby('month_closed').size().to_dict()

        trend_labels = []
        opened_trend = []
        closed_trend = []

        for m in all_months:
            if m and m != 'NaT':
                try:
                    label = datetime.strptime(m, '%Y-%m').strftime('%b %Y')
                    trend_labels.append(label)
                    opened_trend.append(int(opened_by_month.get(m, 0)))
                    closed_trend.append(int(closed_by_month.get(m, 0)))
                except Exception:
                    pass

        return {
            'total_analyzed': total_analyzed,
            'open_count': open_count,
            'closed_count': closed_count,
            'resolution_rate': resolution_rate,
            'avg_resolution_days': avg_resolution_days,
            'old_unresolved_count': old_unresolved,
            'trend_labels': trend_labels,
            'opened_trend': opened_trend,
            'closed_trend': closed_trend,
        }

    @classmethod
    def calculate_pr_statistics(cls, prs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculates PR merge rate, average merge duration, state breakdown,
        and Chart.js distribution datasets.
        """
        if not prs:
            return {
                'total_analyzed': 0,
                'open_count': 0,
                'closed_count': 0,
                'merged_count': 0,
                'merge_rate': 0.0,
                'avg_merge_time_display': 'N/A',
                'avg_merge_hours': None,
                'chart_labels': ['Merged', 'Open', 'Closed (Unmerged)'],
                'chart_data': [0, 0, 0],
            }

        df = pd.DataFrame(prs)
        total_analyzed = len(df)
        open_count = int((df['state'] == 'open').sum()) if 'state' in df.columns else 0
        closed_count = int((df['state'] == 'closed').sum()) if 'state' in df.columns else 0
        merged_count = int((df['state'] == 'merged').sum()) if 'state' in df.columns else 0

        # Safe Merge Rate calculation
        merge_rate = round((merged_count / total_analyzed) * 100.0, 1) if total_analyzed > 0 else 0.0

        # Average Merge Time calculation
        df['created_dt'] = pd.to_datetime(df['created_at'], errors='coerce', utc=True)
        df['merged_dt'] = pd.to_datetime(df.get('merged_at'), errors='coerce', utc=True)

        merged_df = df[(df['state'] == 'merged') & df['created_dt'].notnull() & df['merged_dt'].notnull()]
        avg_merge_display = "N/A"
        avg_merge_hours = None

        if not merged_df.empty:
            deltas_hours = (merged_df['merged_dt'] - merged_df['created_dt']).dt.total_seconds() / 3600.0
            valid_deltas = deltas_hours[deltas_hours >= 0]
            if not valid_deltas.empty:
                mean_hours = float(valid_deltas.mean())
                avg_merge_hours = round(mean_hours, 1)
                if mean_hours < 24:
                    avg_merge_display = f"{mean_hours:.1f} hrs"
                else:
                    avg_merge_display = f"{mean_hours / 24.0:.1f} days"

        return {
            'total_analyzed': total_analyzed,
            'open_count': open_count,
            'closed_count': closed_count,
            'merged_count': merged_count,
            'merge_rate': merge_rate,
            'avg_merge_time_display': avg_merge_display,
            'avg_merge_hours': avg_merge_hours,
            'chart_labels': ['Merged', 'Open', 'Closed (Unmerged)'],
            'chart_data': [merged_count, open_count, closed_count],
        }

    @classmethod
    def calculate_contributor_statistics(cls, contributors: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculates contributor leaderboard, contribution shares,
        and distribution concentration (Top 1, Top 5, Top 10 share percentages).
        """
        if not contributors:
            return {
                'total_recorded': 0,
                'total_contributions': 0,
                'top_contributor': None,
                'top1_share': 0.0,
                'top5_share': 0.0,
                'top10_share': 0.0,
                'leaderboard': [],
                'chart_labels': [],
                'chart_data': [],
            }

        df = pd.DataFrame(contributors)
        total_contributions = int(df['contributions'].sum()) if 'contributions' in df.columns else 0
        total_recorded = len(contributors)

        top1_share = 0.0
        top5_share = 0.0
        top10_share = 0.0

        if total_contributions > 0:
            top1_sum = int(df['contributions'].iloc[:1].sum())
            top5_sum = int(df['contributions'].iloc[:5].sum())
            top10_sum = int(df['contributions'].iloc[:10].sum())

            top1_share = round((top1_sum / total_contributions) * 100.0, 1)
            top5_share = round((top5_sum / total_contributions) * 100.0, 1)
            top10_share = round((top10_sum / total_contributions) * 100.0, 1)

        # Leaderboard with individual share percentages
        leaderboard = []
        chart_labels = []
        chart_data = []

        for idx, c in enumerate(contributors):
            cnt = int(c.get('contributions', 0))
            share = round((cnt / total_contributions) * 100.0, 1) if total_contributions > 0 else 0.0
            leaderboard.append({
                'rank': idx + 1,
                'username': c.get('username', 'Unknown'),
                'contributions': cnt,
                'share_percentage': share,
                'avatar_url': c.get('avatar_url') or '',
                'profile_url': c.get('profile_url') or '',
            })
            if idx < 7:
                chart_labels.append(c.get('username', f'User {idx+1}'))
                chart_data.append(cnt)

        return {
            'total_recorded': total_recorded,
            'total_contributions': total_contributions,
            'top_contributor': leaderboard[0] if leaderboard else None,
            'top1_share': top1_share,
            'top5_share': top5_share,
            'top10_share': top10_share,
            'leaderboard': leaderboard,
            'chart_labels': chart_labels,
            'chart_data': chart_data,
        }

    @classmethod
    def calculate_health_score(
        cls,
        repo_data: Dict[str, Any],
        languages_data: Optional[Any] = None,
        contributors: Optional[List[Dict[str, Any]]] = None,
        commit_stats: Optional[Dict[str, Any]] = None,
        issue_stats: Optional[Dict[str, Any]] = None,
        pr_stats: Optional[Dict[str, Any]] = None,
        contrib_stats: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Refined 5-Pillar Health Score using real analytics telemetry:
          - Activity: 25% (Commit recency, frequency, release cadence)
          - Issue Management: 20% (Resolution rate, backlog scale, resolution velocity)
          - PR Activity: 20% (Merge rate, review velocity, open throughput)
          - Contributor Diversity: 15% (Maintainer base depth, distribution concentration)
          - Maintenance & Hygiene: 20% (License, documentation clarity, repository status)
        """
        scores = {}
        rationale = []

        # 1. Activity (25% Weight)
        days_since_commit = None
        if commit_stats and commit_stats.get('days_since_latest') is not None:
            days_since_commit = commit_stats['days_since_latest']
        else:
            pushed_at_str = repo_data.get('pushed_at') or repo_data.get('updated_at')
            if pushed_at_str:
                try:
                    pushed_dt = datetime.fromisoformat(pushed_at_str.replace('Z', '+00:00'))
                    days_since_commit = (datetime.now(timezone.utc) - pushed_dt).days
                except Exception:
                    days_since_commit = 30

        if days_since_commit is None:
            activity_score = 65
        elif days_since_commit <= 3:
            activity_score = 98
            rationale.append("High commit frequency: Code pushed within the last 3 days.")
        elif days_since_commit <= 14:
            activity_score = 90
            rationale.append("Active commits in the last two weeks.")
        elif days_since_commit <= 45:
            activity_score = 78
            rationale.append("Steady activity within the last 45 days.")
        elif days_since_commit <= 180:
            activity_score = 55
            rationale.append("Moderate inactivity: No pushes in several months.")
        else:
            activity_score = 30
            rationale.append("Stagnant codebase: Over 6 months since latest commit.")

        if commit_stats and commit_stats.get('commits_per_day_avg', 0) > 2.0:
            activity_score = min(100, activity_score + 2)

        scores['activity'] = activity_score

        # 2. Issue Management (20% Weight)
        issue_score = 75
        if issue_stats and issue_stats.get('total_analyzed', 0) > 0:
            res_rate = issue_stats['resolution_rate']
            if res_rate >= 80:
                issue_score = 95
                rationale.append(f"Strong issue resolution rate ({res_rate}% closed).")
            elif res_rate >= 60:
                issue_score = 85
                rationale.append(f"Healthy issue resolution velocity ({res_rate}% closed).")
            elif res_rate >= 40:
                issue_score = 72
                rationale.append(f"Moderate issue triage ({res_rate}% closed).")
            else:
                issue_score = 55
                rationale.append(f"Low issue resolution rate ({res_rate}% closed).")

            if issue_stats.get('old_unresolved_count', 0) > 15:
                issue_score = max(40, issue_score - 8)
                rationale.append("Accumulation of issues unresolved for >90 days.")
        else:
            stars = repo_data.get('stars', 0)
            open_issues = repo_data.get('open_issues', 0)
            if stars > 0:
                ratio = open_issues / stars
                if ratio < 0.05:
                    issue_score = 88
                elif ratio < 0.15:
                    issue_score = 75
                else:
                    issue_score = 62
            else:
                issue_score = 70

        scores['issue_management'] = min(100, max(0, issue_score))

        # 3. PR Activity (20% Weight)
        if repo_data.get('is_archived'):
            pr_score = 25
            rationale.append("Repository is archived (read-only).")
        elif pr_stats and pr_stats.get('total_analyzed', 0) > 0:
            m_rate = pr_stats['merge_rate']
            if m_rate >= 70:
                pr_score = 92
                rationale.append(f"High pull request merge efficiency ({m_rate}% merged).")
            elif m_rate >= 50:
                pr_score = 82
                rationale.append(f"Active pull request turnaround ({m_rate}% merged).")
            elif m_rate >= 30:
                pr_score = 70
            else:
                pr_score = 55
                rationale.append(f"Low merge rate ({m_rate}%), indicating backlog review bottlenecks.")
        else:
            pr_score = 80
            rationale.append("Repository actively open to community contributions.")

        scores['pr_activity'] = min(100, max(0, pr_score))

        # 4. Contributor Diversity (15% Weight)
        contrib_count = len(contributors or [])
        contrib_score = 70
        if contrib_count >= 15:
            contrib_score = 95
            rationale.append("Broad community maintainer distribution (15+ active contributors).")
        elif contrib_count >= 8:
            contrib_score = 86
            rationale.append("Established contributor base (8+ contributors).")
        elif contrib_count >= 3:
            contrib_score = 72
        elif contrib_count >= 1:
            contrib_score = 60
            rationale.append("Small contributor group; potential single maintainer dependency.")
        else:
            contrib_score = 50

        if contrib_stats and contrib_stats.get('top1_share', 0) > 80.0:
            contrib_score = max(45, contrib_score - 10)
            rationale.append(f"High maintainer concentration: Top contributor authors {contrib_stats['top1_share']}% of contributions.")

        scores['contributor_diversity'] = min(100, max(0, contrib_score))

        # 5. Maintenance & Hygiene (20% Weight)
        maintenance_score = 50
        has_license = repo_data.get('license') and repo_data.get('license') != 'Not specified'
        has_desc = bool(repo_data.get('description'))
        if has_license:
            maintenance_score += 25
            rationale.append(f"Documented open-source license: {repo_data.get('license')}.")
        else:
            rationale.append("No official open-source license detected.")

        if has_desc:
            maintenance_score += 25
        else:
            rationale.append("Missing descriptive metadata for project purpose.")

        if repo_data.get('is_archived'):
            maintenance_score = max(20, maintenance_score - 40)

        scores['maintenance'] = min(100, max(0, maintenance_score))

        # Weighted calculation
        total_score = round(
            (scores['activity'] * 0.25) +
            (scores['issue_management'] * 0.20) +
            (scores['pr_activity'] * 0.20) +
            (scores['contributor_diversity'] * 0.15) +
            (scores['maintenance'] * 0.20)
        )

        if total_score >= 85:
            health_tier = "Excellent"
            tier_badge = "success"
        elif total_score >= 70:
            health_tier = "Good"
            tier_badge = "primary"
        elif total_score >= 50:
            health_tier = "Moderate"
            tier_badge = "warning"
        else:
            health_tier = "At Risk"
            tier_badge = "danger"

        return {
            'total_score': total_score,
            'health_tier': health_tier,
            'tier_badge': tier_badge,
            'scores': scores,
            'components': [
                {
                    'name': 'Activity',
                    'weight': '25%',
                    'score': scores['activity'],
                    'description': 'Commit recency, push frequency, and active development cadence',
                },
                {
                    'name': 'Issue Management',
                    'weight': '20%',
                    'score': scores['issue_management'],
                    'description': 'Resolution rate, triage responsiveness, and issue backlog control',
                },
                {
                    'name': 'PR Activity',
                    'weight': '20%',
                    'score': scores['pr_activity'],
                    'description': 'Pull request merge efficiency and review turnaround',
                },
                {
                    'name': 'Contributor Diversity',
                    'weight': '15%',
                    'score': scores['contributor_diversity'],
                    'description': 'Maintainer distribution and community resilience',
                },
                {
                    'name': 'Maintenance & Hygiene',
                    'weight': '20%',
                    'score': scores['maintenance'],
                    'description': 'License clarity, documentation, repository status',
                },
            ],
            'rationale': rationale,
        }

    @classmethod
    def calculate_historical_trend(cls, analyses) -> Dict[str, Any]:
        """
        Extracts chronological health scores and metric trends for history charts.
        """
        if not analyses:
            return {
                'labels': [],
                'scores': [],
                'stars': [],
                'forks': [],
                'has_trend': False,
            }

        items = list(analyses)
        items.sort(key=lambda x: x.analyzed_at)

        labels = [item.analyzed_at.strftime('%b %d, %H:%M') for item in items]
        scores = [item.health_score for item in items]
        stars = [item.stars for item in items]
        forks = [item.forks for item in items]

        return {
            'labels': labels,
            'scores': scores,
            'stars': stars,
            'forks': forks,
            'has_trend': len(items) > 1,
        }

    @classmethod
    def compare_repositories(cls, repos_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compiles objective comparative metrics for 2 or 3 repositories.
        Strictly presents metric differences without 'winner' or 'best' labels.
        """
        if not repos_data:
            return {'repositories': [], 'chart_labels': [], 'chart_datasets': []}

        table_rows = [
            {'key': 'stars', 'label': 'GitHub Stars'},
            {'key': 'forks', 'label': 'Forks'},
            {'key': 'open_issues', 'label': 'Open Issues'},
            {'key': 'health_score', 'label': 'Health Score (0–100)'},
            {'key': 'activity_score', 'label': 'Activity Score (25%)'},
            {'key': 'issue_score', 'label': 'Issue Mgmt Score (20%)'},
            {'key': 'pr_score', 'label': 'PR Activity Score (20%)'},
            {'key': 'contributor_score', 'label': 'Diversity Score (15%)'},
            {'key': 'maintenance_score', 'label': 'Maintenance Score (20%)'},
            {'key': 'primary_language', 'label': 'Primary Language'},
            {'key': 'license', 'label': 'License'},
        ]

        chart_labels = [r['name'] for r in repos_data]
        stars_data = [r.get('stars', 0) for r in repos_data]
        forks_data = [r.get('forks', 0) for r in repos_data]
        health_data = [r.get('health_score', 0) for r in repos_data]

        return {
            'repositories': repos_data,
            'table_rows': table_rows,
            'chart_labels': chart_labels,
            'stars_data': stars_data,
            'forks_data': forks_data,
            'health_data': health_data,
        }
