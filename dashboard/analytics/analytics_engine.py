"""
Analytics Engine for OpenSourceLens.
Utilizes Python & Pandas for statistical analysis, time-series aggregation,
language distributions, issue resolution rates, PR merge velocities,
contributor concentrations (including Herfindahl-Hirschman Index),
and transparent repository health metrics calculation.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import numpy as np
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
    Formats byte counts to B, KB, MB, GB, or TB.
    """
    if not num_bytes or num_bytes < 0:
        return "0 B"
    num = float(num_bytes)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(num) < 1024.0:
            return f"{num:.1f} {unit}".replace(".0 ", " ")
        num /= 1024.0
    return f"{num:.1f} TB"


class AnalyticsEngine:
    """
    Statistical and health computation engine backed by Pandas.
    Provides transparent multi-signal health scoring, safe mathematical divisions,
    median-based duration calculations, and time-series aggregations.
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
        'Scala': '#c22d40',
        'Elixir': '#6e4a7e',
        'Lua': '#000080',
        'R': '#198CE7',
    }

    # Analytical score tier classifications
    TIER_EXCELLENT = "Excellent"
    TIER_GOOD = "Good"
    TIER_MODERATE = "Moderate"
    TIER_AT_RISK = "At Risk"

    METHODOLOGY_DISCLAIMER = (
        "These categories and scores are defined by OpenSourceLens for analytical "
        "visualization and should not be interpreted as universal software-quality standards."
    )

    @classmethod
    def calculate_language_statistics(cls, languages_dict: Dict[str, int]) -> List[Dict[str, Any]]:
        """
        Processes language byte counts into Pandas DataFrame to compute exact percentages.
        Normalizes percentages safely to sum to 100.0%.
        """
        if not languages_dict:
            return []

        clean_items = [
            (str(k), int(v)) for k, v in languages_dict.items()
            if isinstance(v, (int, float)) and v > 0
        ]
        if not clean_items:
            return []

        df = pd.DataFrame(clean_items, columns=['language', 'bytes'])
        total_bytes = int(df['bytes'].sum())

        if total_bytes == 0:
            return []

        df['percentage'] = (df['bytes'] / total_bytes) * 100.0
        df = df.sort_values(by='bytes', ascending=False)

        results = []
        accumulated_pct = 0.0
        rows = list(df.iterrows())

        for idx, (_, row) in enumerate(rows):
            lang_name = str(row['language'])
            b_count = int(row['bytes'])
            pct = round(float(row['percentage']), 1)

            # Ensure rounding sums sensibly for the last item
            if idx == len(rows) - 1 and len(rows) > 1:
                pct = round(max(0.0, 100.0 - accumulated_pct), 1)
            else:
                accumulated_pct += pct

            results.append({
                'language': lang_name,
                'bytes': b_count,
                'bytes_formatted': format_byte_size(b_count),
                'percentage': pct,
                'color': cls.LANGUAGE_COLORS.get(lang_name, '#64748b'),
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
    def calculate_commit_statistics(
        cls,
        commits: List[Dict[str, Any]],
        analysis_window: str = '90d',
        window_days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Calculates commit frequency, averages, days since latest commit,
        and time-series datasets across 30d, 90d, 6m, and 1y for Chart.js.
        Handles empty datasets, single records, missing timestamps, and duplicates safely.
        Supports window_days parameter directly for explicit calendar day spans.
        """
        window_days_map = {'30d': 30, '90d': 90, '180d': 180, '365d': 365}
        if window_days is not None:
            calendar_days = int(window_days)
        else:
            calendar_days = window_days_map.get(str(analysis_window).lower(), 90)

        empty_res = {
            'total_analyzed': 0,
            'commits_per_day_avg': 0.0,
            'commits_per_active_day': 0.0,
            'commits_per_calendar_day': 0.0,
            'active_days_count': 0,
            'calendar_days_count': calendar_days,
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
            'trend_labels_1y': [],
            'trend_data_1y': [],
            'recent_commits': [],
            'has_sufficient_data': False,
        }

        if not commits:
            return empty_res

        df = pd.DataFrame(commits)
        if df.empty or 'date' not in df.columns:
            return empty_res

        # Drop duplicate commits by sha if available
        if 'sha' in df.columns:
            df = df.drop_duplicates(subset=['sha'])

        now = datetime.now(timezone.utc)

        # Parse commit dates safely in UTC
        df['datetime'] = pd.to_datetime(df['date'], errors='coerce', utc=True)
        df = df.dropna(subset=['datetime'])

        if df.empty:
            return {
                **empty_res,
                'total_analyzed': len(commits),
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
        avg_per_active_day = round(float(daily_counts.mean()), 1) if not daily_counts.empty else 0.0
        avg_per_calendar_day = round(float(len(df)) / max(1, calendar_days), 1)
        active_days_count = len(daily_counts)
        max_per_day = int(daily_counts.max()) if not daily_counts.empty else 0
        min_per_day = int(daily_counts.min()) if not daily_counts.empty else 0

        # Top commit authors
        author_series = df['author'].value_counts() if 'author' in df.columns else pd.Series()
        top_authors = [
            {'author': str(k), 'count': int(v)}
            for k, v in author_series.items()
        ][:8]

        # 30-Day Daily Trend
        cutoff_30d = (now - timedelta(days=30)).date()
        df_30d = df[df['day'] >= cutoff_30d]
        daily_30d = df_30d.groupby('day').size().to_dict()
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
        trend_labels_6m = []
        trend_data_6m = []
        for m in monthly_series.index[-6:]:
            try:
                trend_labels_6m.append(datetime.strptime(m, '%Y-%m').strftime('%b %Y'))
                trend_data_6m.append(int(monthly_series[m]))
            except Exception:
                pass

        # 1-Year Monthly Trend
        trend_labels_1y = []
        trend_data_1y = []
        for m in monthly_series.index[-12:]:
            try:
                trend_labels_1y.append(datetime.strptime(m, '%Y-%m').strftime('%b %Y'))
                trend_data_1y.append(int(monthly_series[m]))
            except Exception:
                pass

        return {
            'total_analyzed': len(df),
            'commits_per_day_avg': avg_per_active_day,
            'commits_per_active_day': avg_per_active_day,
            'commits_per_calendar_day': avg_per_calendar_day,
            'active_days_count': active_days_count,
            'calendar_days_count': calendar_days,
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
            'trend_labels_1y': trend_labels_1y,
            'trend_data_1y': trend_data_1y,
            'recent_commits': commits[:10],
            'has_sufficient_data': len(df) >= 3,
        }

    @classmethod
    def calculate_issue_statistics(
        cls,
        issues: List[Dict[str, Any]],
        total_repo_open_issues: int = 0
    ) -> Dict[str, Any]:
        """
        Calculates total issues, open vs closed, resolution rate,
        median resolution time (robust to extreme outliers), average resolution time,
        old unresolved issues (>90 days), and monthly opened vs closed chart datasets.
        """
        empty_res = {
            'total_analyzed': 0,
            'open_count': total_repo_open_issues,
            'closed_count': 0,
            'resolution_rate': 0.0,
            'median_resolution_days': None,
            'avg_resolution_days': None,
            'old_unresolved_count': 0,
            'trend_labels': [],
            'opened_trend': [],
            'closed_trend': [],
            'has_sufficient_data': False,
        }

        if not issues:
            return empty_res

        df = pd.DataFrame(issues)
        if df.empty:
            return empty_res

        total_analyzed = len(df)
        open_count = int((df['state'] == 'open').sum()) if 'state' in df.columns else 0
        closed_count = int((df['state'] == 'closed').sum()) if 'state' in df.columns else 0

        # Sample Resolution Rate calculation
        resolution_rate = round((closed_count / total_analyzed) * 100.0, 1) if total_analyzed > 0 else 0.0

        # Resolution time analysis for closed issues
        median_resolution_days = None
        avg_resolution_days = None
        df['created_dt'] = pd.to_datetime(df['created_at'], errors='coerce', utc=True)
        df['closed_dt'] = pd.to_datetime(df.get('closed_at'), errors='coerce', utc=True)

        closed_df = df[(df['state'] == 'closed') & df['created_dt'].notnull() & df['closed_dt'].notnull()]
        if not closed_df.empty:
            deltas = (closed_df['closed_dt'] - closed_df['created_dt']).dt.total_seconds() / 86400.0
            valid_deltas = deltas[deltas >= 0]
            if not valid_deltas.empty:
                med_val = float(valid_deltas.median())
                avg_val = float(valid_deltas.mean())
                median_resolution_days = round(med_val, 1)
                avg_resolution_days = round(avg_val, 1)

        # Old unresolved issues (> 90 days age)
        now = datetime.now(timezone.utc)
        open_df = df[df['state'] == 'open']
        old_unresolved = 0
        if not open_df.empty and 'created_dt' in open_df.columns:
            age_days = (now - open_df['created_dt']).dt.total_seconds() / 86400.0
            old_unresolved = int((age_days > 90).sum())

        # Monthly Opened vs Closed Trend
        trend_labels: List[str] = []
        opened_trend: List[int] = []
        closed_trend: List[int] = []

        valid_created = df['created_dt'].dropna()
        if not valid_created.empty:
            naive_created = valid_created.dt.tz_convert(None)
            df.loc[naive_created.index, 'month_created'] = naive_created.dt.to_period('M').astype(str)

        valid_closed = df['closed_dt'].dropna()
        if not valid_closed.empty:
            naive_closed = valid_closed.dt.tz_convert(None)
            df.loc[naive_closed.index, 'month_closed'] = naive_closed.dt.to_period('M').astype(str)

        all_months = sorted(list(
            set(df.get('month_created', pd.Series()).dropna().unique()) |
            set(df.get('month_closed', pd.Series()).dropna().unique())
        ))[-6:]

        opened_by_month = df.groupby('month_created').size().to_dict() if 'month_created' in df.columns else {}
        closed_by_month = (
            df[df['state'] == 'closed'].groupby('month_closed').size().to_dict()
            if 'month_closed' in df.columns else {}
        )

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
            'median_resolution_days': median_resolution_days,
            'avg_resolution_days': avg_resolution_days,
            'old_unresolved_count': old_unresolved,
            'trend_labels': trend_labels,
            'opened_trend': opened_trend,
            'closed_trend': closed_trend,
            'has_sufficient_data': total_analyzed >= 3,
        }

    @classmethod
    def calculate_pr_statistics(cls, prs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculates PR merge rate, median & average merge turnaround durations,
        state breakdown, and Chart.js distribution datasets.
        """
        empty_res = {
            'total_analyzed': 0,
            'open_count': 0,
            'closed_count': 0,
            'merged_count': 0,
            'merge_rate': 0.0,
            'closure_rate': 0.0,
            'median_merge_hours': None,
            'avg_merge_hours': None,
            'avg_merge_time_display': 'N/A',
            'chart_labels': ['Merged', 'Open', 'Closed (Unmerged)'],
            'chart_data': [0, 0, 0],
            'has_sufficient_data': False,
        }

        if not prs:
            return empty_res

        df = pd.DataFrame(prs)
        if df.empty:
            return empty_res

        total_analyzed = len(df)
        open_count = int((df['state'] == 'open').sum()) if 'state' in df.columns else 0
        closed_count = int((df['state'] == 'closed').sum()) if 'state' in df.columns else 0
        merged_count = int((df['state'] == 'merged').sum()) if 'state' in df.columns else 0

        merge_rate = round((merged_count / total_analyzed) * 100.0, 1) if total_analyzed > 0 else 0.0
        closure_rate = round((closed_count / total_analyzed) * 100.0, 1) if total_analyzed > 0 else 0.0

        # Merge duration analysis
        df['created_dt'] = pd.to_datetime(df['created_at'], errors='coerce', utc=True)
        df['merged_dt'] = pd.to_datetime(df.get('merged_at'), errors='coerce', utc=True)

        merged_df = df[(df['state'] == 'merged') & df['created_dt'].notnull() & df['merged_dt'].notnull()]
        avg_merge_display = "N/A"
        avg_merge_hours = None
        median_merge_hours = None

        if not merged_df.empty:
            deltas_hours = (merged_df['merged_dt'] - merged_df['created_dt']).dt.total_seconds() / 3600.0
            valid_deltas = deltas_hours[deltas_hours >= 0]
            if not valid_deltas.empty:
                med_h = float(valid_deltas.median())
                mean_h = float(valid_deltas.mean())
                median_merge_hours = round(med_h, 1)
                avg_merge_hours = round(mean_h, 1)

                # Format display using median to be robust against long-open outliers
                if med_h < 24:
                    avg_merge_display = f"{med_h:.1f} hrs"
                else:
                    avg_merge_display = f"{med_h / 24.0:.1f} days"

        return {
            'total_analyzed': total_analyzed,
            'open_count': open_count,
            'closed_count': closed_count,
            'merged_count': merged_count,
            'merge_rate': merge_rate,
            'closure_rate': closure_rate,
            'median_merge_hours': median_merge_hours,
            'avg_merge_hours': avg_merge_hours,
            'avg_merge_time_display': avg_merge_display,
            'chart_labels': ['Merged', 'Open', 'Closed (Unmerged)'],
            'chart_data': [merged_count, open_count, closed_count],
            'has_sufficient_data': total_analyzed >= 3,
        }

    @classmethod
    def calculate_contributor_statistics(cls, contributors: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculates contributor leaderboard, contribution shares,
        and distribution concentration metrics:
          - Top 1, Top 5, Top 10 share percentages
          - Herfindahl-Hirschman Index (HHI = sum(share_i^2))
        """
        empty_res = {
            'total_recorded': 0,
            'total_contributions': 0,
            'top_contributor': None,
            'top1_share': 0.0,
            'top5_share': 0.0,
            'top10_share': 0.0,
            'hhi': 0.0,
            'concentration_label': 'N/A',
            'leaderboard': [],
            'chart_labels': [],
            'chart_data': [],
            'has_sufficient_data': False,
        }

        if not contributors:
            return empty_res

        df = pd.DataFrame(contributors)
        if df.empty or 'contributions' not in df.columns:
            return empty_res

        total_contributions = int(df['contributions'].sum())
        total_recorded = len(contributors)

        top1_share = 0.0
        top5_share = 0.0
        top10_share = 0.0
        hhi = 0.0

        if total_contributions > 0:
            top1_sum = int(df['contributions'].iloc[:1].sum())
            top5_sum = int(df['contributions'].iloc[:5].sum())
            top10_sum = int(df['contributions'].iloc[:10].sum())

            top1_share = round((top1_sum / total_contributions) * 100.0, 1)
            top5_share = round((top5_sum / total_contributions) * 100.0, 1)
            top10_share = round((top10_sum / total_contributions) * 100.0, 1)

            # Compute Herfindahl-Hirschman Index: sum of (percentage_share)^2
            shares = (df['contributions'] / total_contributions) * 100.0
            hhi = round(float((shares ** 2).sum()), 1)

        # Categorize HHI concentration neutrally (Based on analyzed contributors returned by GitHub)
        if hhi >= 2500:
            concentration_label = "High maintainer concentration"
        elif hhi >= 1500:
            concentration_label = "Moderate maintainer concentration"
        else:
            concentration_label = "Well-distributed maintainer base"

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
            'hhi': hhi,
            'concentration_label': concentration_label,
            'methodology_note': 'Based on analyzed contributors returned by GitHub API.',
            'leaderboard': leaderboard,
            'chart_labels': chart_labels,
            'chart_data': chart_data,
            'has_sufficient_data': total_recorded > 0,
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
        Deterministic, transparent 5-Pillar Health Score using multiple telemetry signals:
          - Activity: 25% (Commit recency, push frequency, release cadence)
          - Issue Management: 20% (Resolution rate, median resolution days, backlog ratio)
          - PR Activity: 20% (Merge rate, review velocity, open throughput)
          - Contributor Diversity: 15% (Maintainer base depth, HHI concentration)
          - Maintenance & Hygiene: 20% (License, description, repository status, metadata)

        Every pillar is normalized to 0-100 before weighting.
        """
        scores: Dict[str, int] = {}
        rationale: List[str] = []
        pillar_breakdowns: Dict[str, List[str]] = {
            'activity': [],
            'issue_management': [],
            'pr_activity': [],
            'contributor_diversity': [],
            'maintenance': [],
        }

        # ---------------------------------------------------------------------
        # 1. Activity (25% Weight)
        # Multi-signal evaluation (Total: 0-100 normalized):
        #   - Recency (40 pts): Days since latest commit / push
        #   - Frequency (30 pts): Commit velocity across the analysis window
        #   - Consistency (15 pts): Distribution of active commit days
        #   - Trend (15 pts): Volume in recent 30-day window vs prior periods
        # ---------------------------------------------------------------------
        days_since_commit = None
        if commit_stats and commit_stats.get('days_since_latest') is not None:
            days_since_commit = commit_stats['days_since_latest']
        else:
            pushed_at_str = repo_data.get('pushed_at') or repo_data.get('updated_at')
            if pushed_at_str:
                try:
                    pushed_dt = datetime.fromisoformat(str(pushed_at_str).replace('Z', '+00:00'))
                    days_since_commit = max(0, (datetime.now(timezone.utc) - pushed_dt).days)
                except Exception:
                    days_since_commit = 30

        # Signal 1: Recency (Max 40 pts)
        if days_since_commit is None:
            recency_pts = 26
            pillar_breakdowns['activity'].append("Recency (26/40 pts): Estimated from repository metadata.")
        elif days_since_commit <= 3:
            recency_pts = 40
            pillar_breakdowns['activity'].append(f"Recency (40/40 pts): Pushed {days_since_commit}d ago (active development).")
            rationale.append("Active commits within the last 3 days.")
        elif days_since_commit <= 14:
            recency_pts = 34
            pillar_breakdowns['activity'].append(f"Recency (34/40 pts): Pushed {days_since_commit}d ago (regular cadence).")
            rationale.append("Active commits in the last two weeks.")
        elif days_since_commit <= 45:
            recency_pts = 26
            pillar_breakdowns['activity'].append(f"Recency (26/40 pts): Pushed {days_since_commit}d ago (steady activity).")
        elif days_since_commit <= 180:
            recency_pts = 16
            pillar_breakdowns['activity'].append(f"Recency (16/40 pts): Pushed {days_since_commit}d ago (inactivity).")
            rationale.append("Inactivity: Over 45 days since latest commit.")
        else:
            recency_pts = 6
            pillar_breakdowns['activity'].append(f"Recency (6/40 pts): Stagnant ({days_since_commit}d since latest commit).")
            rationale.append("Stagnant codebase: Over 6 months since latest commit.")

        # Signal 2: Frequency (Max 30 pts)
        if commit_stats:
            c_cal_avg = commit_stats.get('commits_per_calendar_day', 0.0)
            c_act_avg = commit_stats.get('commits_per_active_day', commit_stats.get('commits_per_day_avg', 0.0))
            total_commits = commit_stats.get('total_analyzed', 0)

            if total_commits >= 50 or c_cal_avg >= 1.0 or c_act_avg >= 3.0:
                freq_pts = 30
                pillar_breakdowns['activity'].append(f"Frequency (30/30 pts): High commit velocity ({c_act_avg}/active day, {c_cal_avg}/cal day).")
            elif total_commits >= 20 or c_cal_avg >= 0.3 or c_act_avg >= 1.5:
                freq_pts = 24
                pillar_breakdowns['activity'].append(f"Frequency (24/30 pts): Steady commit cadence ({c_act_avg}/active day).")
            elif total_commits >= 5 or c_cal_avg >= 0.1:
                freq_pts = 16
                pillar_breakdowns['activity'].append(f"Frequency (16/30 pts): Moderate commit volume ({total_commits} analyzed).")
            elif total_commits > 0:
                freq_pts = 10
                pillar_breakdowns['activity'].append(f"Frequency (10/30 pts): Low commit volume ({total_commits} analyzed).")
            else:
                freq_pts = 5
                pillar_breakdowns['activity'].append("Frequency (5/30 pts): Minimal or zero commits in window.")
        else:
            if days_since_commit is not None and days_since_commit <= 3:
                freq_pts = 25
            elif days_since_commit is not None and days_since_commit <= 14:
                freq_pts = 20
            elif days_since_commit is not None and days_since_commit <= 45:
                freq_pts = 14
            else:
                freq_pts = 5
            pillar_breakdowns['activity'].append(f"Frequency ({freq_pts}/30 pts): Estimated from repository activity cadence.")

        # Signal 3: Consistency (Max 15 pts) - Active commit days spread
        if commit_stats:
            active_days = commit_stats.get('active_days_count', 0)
            if active_days >= 15:
                cons_pts = 15
                pillar_breakdowns['activity'].append(f"Consistency (15/15 pts): Commits distributed across {active_days} active days.")
            elif active_days >= 7:
                cons_pts = 12
                pillar_breakdowns['activity'].append(f"Consistency (12/15 pts): Commits distributed across {active_days} active days.")
            elif active_days >= 3:
                cons_pts = 8
                pillar_breakdowns['activity'].append(f"Consistency (8/15 pts): Commits across {active_days} active days.")
            elif active_days >= 1:
                cons_pts = 4
                pillar_breakdowns['activity'].append(f"Consistency (4/15 pts): Commits concentrated on {active_days} day(s).")
            else:
                cons_pts = 2
                pillar_breakdowns['activity'].append("Consistency (2/15 pts): Insufficient active day spread.")
        else:
            if days_since_commit is not None and days_since_commit <= 7:
                cons_pts = 12
            elif days_since_commit is not None and days_since_commit <= 30:
                cons_pts = 8
            else:
                cons_pts = 3
            pillar_breakdowns['activity'].append(f"Consistency ({cons_pts}/15 pts): Estimated from repository update cadence.")

        # Signal 4: Recent Trend (Max 15 pts) - 30-day activity presence
        if commit_stats:
            trend_30d_data = commit_stats.get('trend_data_30d', [])
            recent_30d_sum = sum(trend_30d_data) if trend_30d_data else 0
            if recent_30d_sum >= 10:
                trend_pts = 15
                pillar_breakdowns['activity'].append(f"Trend (15/15 pts): Strong 30-day commit volume ({recent_30d_sum} commits).")
            elif recent_30d_sum >= 3:
                trend_pts = 11
                pillar_breakdowns['activity'].append(f"Trend (11/15 pts): Moderate recent commit volume ({recent_30d_sum} commits).")
            elif recent_30d_sum >= 1:
                trend_pts = 7
                pillar_breakdowns['activity'].append(f"Trend (7/15 pts): Low recent commit volume ({recent_30d_sum} commits).")
            else:
                trend_pts = 3
                pillar_breakdowns['activity'].append("Trend (3/15 pts): No commits recorded in latest 30 days.")
        else:
            if days_since_commit is not None and days_since_commit <= 7:
                trend_pts = 12
            elif days_since_commit is not None and days_since_commit <= 30:
                trend_pts = 8
            else:
                trend_pts = 3
            pillar_breakdowns['activity'].append(f"Trend ({trend_pts}/15 pts): Estimated from recent repository push.")

        activity_score = recency_pts + freq_pts + cons_pts + trend_pts
        scores['activity'] = int(min(100, max(0, round(activity_score))))

        # ---------------------------------------------------------------------
        # 2. Issue Management (20% Weight)
        # Signals: Resolution rate, median resolution days, backlog ratio, old unresolved.
        # ---------------------------------------------------------------------
        issue_score = 75
        if issue_stats and issue_stats.get('total_analyzed', 0) > 0:
            res_rate = issue_stats['resolution_rate']
            if res_rate >= 80:
                base_issue = 94
                pillar_breakdowns['issue_management'].append(f"Resolution rate: {res_rate}% closed (high turnaround).")
                rationale.append(f"Strong issue resolution rate ({res_rate}% closed).")
            elif res_rate >= 60:
                base_issue = 84
                pillar_breakdowns['issue_management'].append(f"Resolution rate: {res_rate}% closed (healthy).")
                rationale.append(f"Healthy issue resolution velocity ({res_rate}% closed).")
            elif res_rate >= 40:
                base_issue = 70
                pillar_breakdowns['issue_management'].append(f"Resolution rate: {res_rate}% closed (moderate).")
                rationale.append(f"Moderate issue triage ({res_rate}% closed).")
            else:
                base_issue = 52
                pillar_breakdowns['issue_management'].append(f"Resolution rate: {res_rate}% closed (low).")
                rationale.append(f"Low issue resolution rate ({res_rate}% closed).")

            # Factor in median resolution duration
            med_days = issue_stats.get('median_resolution_days')
            if med_days is not None:
                if med_days <= 5.0:
                    base_issue = min(100, base_issue + 4)
                    pillar_breakdowns['issue_management'].append(f"Turnaround: Rapid median close time ({med_days} days).")
                elif med_days > 45.0:
                    base_issue = max(30, base_issue - 4)
                    pillar_breakdowns['issue_management'].append(f"Turnaround: Extended median close time ({med_days} days).")

            # Old unresolved issues penalty
            old_count = issue_stats.get('old_unresolved_count', 0)
            if old_count > 15:
                base_issue = max(35, base_issue - 8)
                pillar_breakdowns['issue_management'].append(f"Backlog age: {old_count} issues open for >90 days.")
                rationale.append("Accumulation of issues unresolved for >90 days.")

            issue_score = base_issue
        else:
            # Fallback to repo-wide open issues to stars scale
            stars = repo_data.get('stars', 0)
            open_issues = repo_data.get('open_issues', 0)
            if stars > 0:
                ratio = open_issues / stars
                if ratio < 0.05:
                    issue_score = 88
                    pillar_breakdowns['issue_management'].append("Backlog: Low open issue to star ratio.")
                elif ratio < 0.15:
                    issue_score = 75
                    pillar_breakdowns['issue_management'].append("Backlog: Balanced issue backlog.")
                else:
                    issue_score = 62
                    pillar_breakdowns['issue_management'].append("Backlog: Elevated open issue count relative to stars.")
            else:
                issue_score = 70
                pillar_breakdowns['issue_management'].append("Backlog: Baseline triage indicator.")

        scores['issue_management'] = int(min(100, max(0, round(issue_score))))

        # ---------------------------------------------------------------------
        # 3. PR Activity (20% Weight)
        # Signals: Merge rate, review turnaround velocity, open throughput.
        # ---------------------------------------------------------------------
        if repo_data.get('is_archived'):
            pr_score = 25
            pillar_breakdowns['pr_activity'].append("Status: Repository is archived (read-only, no PR intake).")
            rationale.append("Repository is archived (read-only).")
        elif pr_stats and pr_stats.get('total_analyzed', 0) > 0:
            m_rate = pr_stats['merge_rate']
            if m_rate >= 70:
                base_pr = 92
                pillar_breakdowns['pr_activity'].append(f"Merge rate: {m_rate}% merged (efficient intake).")
                rationale.append(f"High pull request merge efficiency ({m_rate}% merged).")
            elif m_rate >= 50:
                base_pr = 82
                pillar_breakdowns['pr_activity'].append(f"Merge rate: {m_rate}% merged (steady review cadence).")
                rationale.append(f"Active pull request turnaround ({m_rate}% merged).")
            elif m_rate >= 30:
                base_pr = 70
                pillar_breakdowns['pr_activity'].append(f"Merge rate: {m_rate}% merged.")
            else:
                base_pr = 54
                pillar_breakdowns['pr_activity'].append(f"Merge rate: {m_rate}% merged (indicates backlog bottlenecks).")
                rationale.append(f"Low merge rate ({m_rate}%), indicating backlog review bottlenecks.")

            # Turnaround duration factor
            med_hours = pr_stats.get('median_merge_hours')
            if med_hours is not None:
                if med_hours <= 48.0:
                    base_pr = min(100, base_pr + 4)
                    pillar_breakdowns['pr_activity'].append(f"Turnaround: Fast median merge velocity ({med_hours} hrs).")
                elif med_hours > 360.0:  # > 15 days
                    base_pr = max(35, base_pr - 4)
                    pillar_breakdowns['pr_activity'].append(f"Turnaround: Slower review turnaround (median {med_hours / 24:.1f} days).")

            pr_score = base_pr
        else:
            pr_score = 80
            pillar_breakdowns['pr_activity'].append("Community status: Open to external contributions.")
            rationale.append("Repository actively open to community contributions.")

        scores['pr_activity'] = int(min(100, max(0, round(pr_score))))

        # ---------------------------------------------------------------------
        # 4. Contributor Diversity (15% Weight)
        # Signals: Contributor count, maintainer concentration (HHI), top contributor share.
        # ---------------------------------------------------------------------
        contrib_count = len(contributors or [])
        if contrib_count >= 15:
            contrib_score = 94
            pillar_breakdowns['contributor_diversity'].append(f"Maintainer base: Broad community ({contrib_count}+ contributors).")
            rationale.append("Broad community maintainer distribution (15+ active contributors).")
        elif contrib_count >= 8:
            contrib_score = 85
            pillar_breakdowns['contributor_diversity'].append(f"Maintainer base: Established base ({contrib_count} contributors).")
            rationale.append("Established contributor base (8+ contributors).")
        elif contrib_count >= 3:
            contrib_score = 72
            pillar_breakdowns['contributor_diversity'].append(f"Maintainer base: Modest group ({contrib_count} contributors).")
        elif contrib_count >= 1:
            contrib_score = 58
            pillar_breakdowns['contributor_diversity'].append("Maintainer base: Single or very small maintainer group.")
            rationale.append("Small contributor group; potential single maintainer dependency.")
        else:
            contrib_score = 50
            pillar_breakdowns['contributor_diversity'].append("Maintainer base: Limited data returned.")

        # Concentration adjustment based on HHI / Top 1 share
        if contrib_stats:
            top1 = contrib_stats.get('top1_share', 0.0)
            hhi = contrib_stats.get('hhi', 0.0)
            if top1 > 80.0 or hhi >= 4000:
                contrib_score = max(45, contrib_score - 10)
                pillar_breakdowns['contributor_diversity'].append(
                    f"Concentration: High maintainer dependency (Top contributor authors {top1}% of sample)."
                )
                rationale.append(f"High maintainer concentration: Top contributor authors {top1}% of contributions.")
            elif hhi < 1500 and contrib_count >= 5:
                contrib_score = min(100, contrib_score + 3)
                pillar_breakdowns['contributor_diversity'].append("Concentration: Well-distributed author share (HHI < 1500).")

        scores['contributor_diversity'] = int(min(100, max(0, round(contrib_score))))

        # ---------------------------------------------------------------------
        # 5. Maintenance & Hygiene (20% Weight)
        # Directly normalized to 0-100 based on standard GitHub metadata fields:
        #   - Open-Source License: 30 pts (Documented open-source license)
        #   - Repository Status: 25 pts (Active/unarchived: 25 pts; Archived: 0 pts)
        #   - Project Description: 20 pts (Clear scope & purpose documented)
        #   - Discoverability / Topics: 15 pts (>=2 topics: 15 pts; 1 topic: 8 pts; 0: 0 pts)
        #   - Default Branch Hygiene: 10 pts ('main' or 'master': 10 pts; custom: 5 pts)
        # Total Maximum = 30 + 25 + 20 + 15 + 10 = 100 points.
        # ---------------------------------------------------------------------
        maintenance_score = 0
        has_license = bool(repo_data.get('license') and repo_data.get('license') not in ('Not specified', 'NOASSERTION', None))
        has_desc = bool(repo_data.get('description') and str(repo_data.get('description')).strip())
        is_archived = bool(repo_data.get('is_archived', False))
        topics = repo_data.get('topics') or []
        default_branch = repo_data.get('default_branch', 'main')

        # 1. License (30 pts)
        if has_license:
            maintenance_score += 30
            pillar_breakdowns['maintenance'].append(f"License (30/30 pts): Documented open-source license ({repo_data.get('license')}).")
        else:
            pillar_breakdowns['maintenance'].append("License (0/30 pts): No official open-source license detected.")
            rationale.append("No official open-source license detected.")

        # 2. Repository Status (25 pts)
        if not is_archived:
            maintenance_score += 25
            pillar_breakdowns['maintenance'].append("Repository Status (25/25 pts): Repository is active and maintainable.")
        else:
            pillar_breakdowns['maintenance'].append("Repository Status (0/25 pts): Repository is archived (read-only).")
            rationale.append("Repository is archived (read-only).")

        # 3. Project Description (20 pts)
        if has_desc:
            maintenance_score += 20
            pillar_breakdowns['maintenance'].append("Description (20/20 pts): Project purpose clearly documented.")
        else:
            pillar_breakdowns['maintenance'].append("Description (0/20 pts): Missing descriptive metadata.")
            rationale.append("Missing descriptive metadata for project purpose.")

        # 4. Discoverability / Topics (15 pts)
        if len(topics) >= 2:
            maintenance_score += 15
            pillar_breakdowns['maintenance'].append(f"Topics (15/15 pts): {len(topics)} topic tags defined.")
        elif len(topics) == 1:
            maintenance_score += 8
            pillar_breakdowns['maintenance'].append("Topics (8/15 pts): 1 topic tag defined.")
        else:
            pillar_breakdowns['maintenance'].append("Topics (0/15 pts): No discoverability topic tags defined.")

        # 5. Default Branch Hygiene (10 pts)
        if default_branch in ('main', 'master'):
            maintenance_score += 10
            pillar_breakdowns['maintenance'].append(f"Branch Hygiene (10/10 pts): Standard default branch '{default_branch}'.")
        else:
            maintenance_score += 5
            pillar_breakdowns['maintenance'].append(f"Branch Hygiene (5/10 pts): Custom default branch '{default_branch}'.")

        scores['maintenance'] = int(min(100, max(0, round(maintenance_score))))

        # ---------------------------------------------------------------------
        # Weighted Overall Calculation
        # Activity: 25%, Issue: 20%, PR: 20%, Contributor: 15%, Maintenance: 20%
        # ---------------------------------------------------------------------
        raw_total = (
            (scores['activity'] * 0.25) +
            (scores['issue_management'] * 0.20) +
            (scores['pr_activity'] * 0.20) +
            (scores['contributor_diversity'] * 0.15) +
            (scores['maintenance'] * 0.20)
        )
        total_score = int(round(raw_total))

        if total_score >= 85:
            health_tier = cls.TIER_EXCELLENT
            tier_badge = "success"
        elif total_score >= 70:
            health_tier = cls.TIER_GOOD
            tier_badge = "primary"
        elif total_score >= 50:
            health_tier = cls.TIER_MODERATE
            tier_badge = "warning"
        else:
            health_tier = cls.TIER_AT_RISK
            tier_badge = "danger"

        return {
            'total_score': total_score,
            'health_tier': health_tier,
            'tier_badge': tier_badge,
            'disclaimer': cls.METHODOLOGY_DISCLAIMER,
            'scores': scores,
            'components': [
                {
                    'name': 'Activity',
                    'weight': '25%',
                    'score': scores['activity'],
                    'description': 'Commit recency, push frequency, and active development cadence',
                    'signals': pillar_breakdowns['activity'],
                },
                {
                    'name': 'Issue Management',
                    'weight': '20%',
                    'score': scores['issue_management'],
                    'description': 'Resolution rate, median resolution days, and issue backlog control',
                    'signals': pillar_breakdowns['issue_management'],
                },
                {
                    'name': 'PR Activity',
                    'weight': '20%',
                    'score': scores['pr_activity'],
                    'description': 'Pull request merge efficiency, velocity, and turnaround',
                    'signals': pillar_breakdowns['pr_activity'],
                },
                {
                    'name': 'Contributor Diversity',
                    'weight': '15%',
                    'score': scores['contributor_diversity'],
                    'description': 'Maintainer distribution and community resilience',
                    'signals': pillar_breakdowns['contributor_diversity'],
                },
                {
                    'name': 'Maintenance & Hygiene',
                    'weight': '20%',
                    'score': scores['maintenance'],
                    'description': 'License clarity, documentation, discoverability, repository status',
                    'signals': pillar_breakdowns['maintenance'],
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
                'activity_scores': [],
                'issue_scores': [],
                'pr_scores': [],
                'contributor_scores': [],
                'maintenance_scores': [],
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
            'activity_scores': [getattr(item, 'activity_score', 0) for item in items],
            'issue_scores': [getattr(item, 'issue_score', 0) for item in items],
            'pr_scores': [getattr(item, 'pr_score', 0) for item in items],
            'contributor_scores': [getattr(item, 'contributor_score', 0) for item in items],
            'maintenance_scores': [getattr(item, 'maintenance_score', 0) for item in items],
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
            {'key': 'hhi', 'label': 'Maintainer Concentration (HHI)'},
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
