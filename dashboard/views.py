"""
Views for OpenSourceLens Dashboard.
Connects HTTP requests to GitHubService, ORM persistence, AnalyticsEngine,
and responsive templates.
"""

import json
import logging
from datetime import datetime, timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound, HttpResponseServerError, HttpResponseBadRequest
from django.utils.dateparse import parse_datetime, parse_date
from django.db import transaction
from django.db.models import Q

from dashboard.forms import RepositorySearchForm, RepositoryCompareForm
from dashboard.services.github_service import (
    GitHubService,
    GitHubAPIError,
    GitHubInvalidRepoError,
    GitHubRepoNotFoundError,
    GitHubRateLimitExceededError,
)
from dashboard.models import (
    Repository,
    Language,
    Contributor,
    CommitActivity,
    Issue,
    PullRequest,
    RepositoryAnalysis,
)
from dashboard.analytics.analytics_engine import AnalyticsEngine, format_metric_number

logger = logging.getLogger(__name__)


def home_view(request: HttpRequest) -> HttpResponse:
    """
    Renders the OpenSourceLens homepage with repository search form,
    quick-sample repositories, and feature overview.
    """
    form = RepositorySearchForm()
    recent_repos = []
    try:
        recent_repos = Repository.objects.prefetch_related('analyses').order_by('-fetched_at')[:6]
    except Exception as e:
        logger.warning(f"Could not load recent repos from database: {e}")

    return render(request, 'home.html', {
        'form': form,
        'recent_repos': recent_repos,
    })


def analyze_view(request: HttpRequest) -> HttpResponse:
    """
    Validates repository input, fetches real-time data from GitHub API,
    persists records to PostgreSQL, computes Pandas analytics, and renders dashboard.
    """
    raw_repo = ""
    if request.method == 'POST':
        form = RepositorySearchForm(request.POST)
        if form.is_valid():
            raw_repo = form.cleaned_data['repository']
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)
            return redirect('home')
    else:
        raw_repo = request.GET.get('repo', '').strip()
        if not raw_repo:
            return redirect('home')

    # Step 1: Validate repository format
    try:
        owner, repo_name = GitHubService.validate_and_normalize(raw_repo)
    except GitHubInvalidRepoError as e:
        messages.error(request, str(e))
        return redirect('home')

    repo_str = f"{owner}/{repo_name}"
    service = GitHubService()

    # Step 2: Fetch data from GitHub API (Metadata, Languages, Contributors, Commits, Issues, PRs)
    try:
        repo_data = service.get_repository(owner, repo_name)
        languages_raw = service.get_languages(owner, repo_name)
        contributors_raw = service.get_contributors(owner, repo_name, limit=12)
        commits_raw = service.get_commits(owner, repo_name, limit=100)
        issues_raw = service.get_issues(owner, repo_name, limit=50)
        prs_raw = service.get_pull_requests(owner, repo_name, limit=50)
    except GitHubRepoNotFoundError as e:
        messages.error(request, str(e))
        return redirect('home')
    except GitHubRateLimitExceededError as e:
        messages.error(request, str(e))
        return redirect('home')
    except GitHubAPIError as e:
        messages.error(request, str(e))
        return redirect('home')
    except Exception as e:
        logger.exception(f"Unexpected error while analyzing {repo_str}: {e}")
        messages.error(request, "An unexpected error occurred while contacting GitHub. Please try again.")
        return redirect('home')

    # Step 3: Compute analytics and transparent health score via Pandas
    language_stats = AnalyticsEngine.calculate_language_statistics(languages_raw)
    language_dist = AnalyticsEngine.calculate_language_distribution(languages_raw)
    commit_stats = AnalyticsEngine.calculate_commit_statistics(commits_raw)
    issue_stats = AnalyticsEngine.calculate_issue_statistics(issues_raw, total_repo_open_issues=repo_data['open_issues'])
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

    # Step 4: Persist or update repository and snapshots in PostgreSQL database
    repo_obj = None
    try:
        with transaction.atomic():
            created_dt = parse_datetime(repo_data['created_at']) if repo_data.get('created_at') else None
            updated_dt = parse_datetime(repo_data['updated_at']) if repo_data.get('updated_at') else None

            repo_obj, _ = Repository.objects.update_or_create(
                full_name=repo_data['full_name'],
                defaults={
                    'owner': repo_data['owner'],
                    'name': repo_data['name'],
                    'description': repo_data['description'],
                    'url': repo_data['url'],
                    'stars': repo_data['stars'],
                    'forks': repo_data['forks'],
                    'watchers': repo_data['watchers'],
                    'open_issues': repo_data['open_issues'],
                    'created_at': created_dt,
                    'updated_at': updated_dt,
                    'default_branch': repo_data['default_branch'],
                    'license': repo_data['license'],
                }
            )

            # Update languages in DB
            Language.objects.filter(repository=repo_obj).delete()
            for lang in language_stats:
                Language.objects.create(
                    repository=repo_obj,
                    language=lang['language'],
                    bytes=lang['bytes'],
                    percentage=lang['percentage'],
                )

            # Update top contributors in DB
            if contributors_raw:
                for c in contributors_raw:
                    Contributor.objects.update_or_create(
                        repository=repo_obj,
                        username=c['username'],
                        defaults={
                            'contributions': c['contributions'],
                            'avatar_url': c.get('avatar_url'),
                            'profile_url': c.get('profile_url'),
                        }
                    )

            # Update commit activities in DB
            if commits_raw:
                # Group commits by date
                daily_counts = {}
                for c in commits_raw:
                    date_str = c.get('date')
                    if date_str:
                        d = date_str[:10]
                        daily_counts[d] = daily_counts.get(d, 0) + 1
                for d_str, cnt in daily_counts.items():
                    p_date = parse_date(d_str)
                    if p_date:
                        CommitActivity.objects.update_or_create(
                            repository=repo_obj,
                            date=p_date,
                            defaults={'commit_count': cnt}
                        )

            # Update issues in DB
            if issues_raw:
                for iss in issues_raw:
                    Issue.objects.update_or_create(
                        repository=repo_obj,
                        issue_number=iss['issue_number'],
                        defaults={
                            'title': iss['title'],
                            'state': iss['state'],
                            'created_at': parse_datetime(iss['created_at']) or datetime.now(timezone.utc),
                            'closed_at': parse_datetime(iss['closed_at']) if iss.get('closed_at') else None,
                        }
                    )

            # Update PRs in DB
            if prs_raw:
                for pr in prs_raw:
                    PullRequest.objects.update_or_create(
                        repository=repo_obj,
                        pr_number=pr['pr_number'],
                        defaults={
                            'title': pr.get('title', ''),
                            'state': pr['state'],
                            'created_at': parse_datetime(pr['created_at']) or datetime.now(timezone.utc),
                            'closed_at': parse_datetime(pr.get('closed_at')) if pr.get('closed_at') else None,
                            'merged_at': parse_datetime(pr.get('merged_at')) if pr.get('merged_at') else None,
                        }
                    )

            # Create historical analysis snapshot
            RepositoryAnalysis.objects.create(
                repository=repo_obj,
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
            )
    except Exception as e:
        logger.warning(f"Database persistence warning (continuing to show dashboard): {e}")

    # Fetch historical health score trend for this repository
    health_trend = {'labels': [], 'scores': [], 'stars': [], 'has_trend': False}
    if repo_obj:
        try:
            past_analyses = repo_obj.analyses.order_by('analyzed_at')
            health_trend = AnalyticsEngine.calculate_historical_trend(past_analyses)
        except Exception as e:
            logger.warning(f"Could not load historical trend: {e}")

    # Step 5: Format metrics for stat display cards
    formatted_metrics = {
        'stars': format_metric_number(repo_data['stars']),
        'forks': format_metric_number(repo_data['forks']),
        'watchers': format_metric_number(repo_data['watchers']),
        'open_issues': format_metric_number(repo_data['open_issues']),
        'subscribers': format_metric_number(repo_data.get('subscribers_count', 0)),
        'commits_analyzed': format_metric_number(commit_stats['total_analyzed']),
        'contributors_recorded': format_metric_number(contributor_stats['total_recorded']),
    }

    # Step 6: Prepare JSON payloads for Chart.js canvas renderings
    chart_payloads = {
        'commit_trend': json.dumps({
            'labels_30d': commit_stats['trend_labels_30d'],
            'data_30d': commit_stats['trend_data_30d'],
            'labels_90d': commit_stats['trend_labels_90d'],
            'data_90d': commit_stats['trend_data_90d'],
            'labels_6m': commit_stats['trend_labels_6m'],
            'data_6m': commit_stats['trend_data_6m'],
        }),
        'issues_trend': json.dumps({
            'labels': issue_stats['trend_labels'],
            'opened': issue_stats['opened_trend'],
            'closed': issue_stats['closed_trend'],
        }),
        'prs_status': json.dumps({
            'labels': pr_stats['chart_labels'],
            'data': pr_stats['chart_data'],
        }),
        'languages': json.dumps({
            'labels': language_dist['chart_labels'],
            'data': language_dist['chart_data'],
            'colors': language_dist['chart_colors'],
        }),
        'contributors': json.dumps({
            'labels': contributor_stats['chart_labels'],
            'data': contributor_stats['chart_data'],
        }),
        'health_trend': json.dumps({
            'labels': health_trend['labels'],
            'scores': health_trend['scores'],
            'stars': health_trend['stars'],
        }),
    }

    return render(request, 'dashboard.html', {
        'repo': repo_data,
        'metrics': formatted_metrics,
        'languages': language_stats,
        'language_dist': language_dist,
        'health': health_metrics,
        'contributors': contributors_raw,
        'contributor_stats': contributor_stats,
        'commit_stats': commit_stats,
        'issue_stats': issue_stats,
        'pr_stats': pr_stats,
        'health_trend': health_trend,
        'chart_payloads': chart_payloads,
    })


def history_view(request: HttpRequest) -> HttpResponse:
    """
    Displays the catalog of previously analyzed repositories saved in PostgreSQL,
    with search, sorting, and health scores.
    """
    query = request.GET.get('q', '').strip()
    sort_by = request.GET.get('sort', 'recent').strip().lower()

    repos = Repository.objects.prefetch_related('languages', 'analyses').all()

    if query:
        repos = repos.filter(
            Q(full_name__icontains=query) |
            Q(description__icontains=query) |
            Q(owner__icontains=query)
        )

    # Sorting
    if sort_by == 'stars':
        repos = repos.order_by('-stars')
    elif sort_by == 'name':
        repos = repos.order_by('name')
    else:  # 'recent'
        repos = repos.order_by('-fetched_at')

    # Annotate latest analysis snapshot to each repository
    repo_list = []
    for r in repos:
        latest_analysis = r.analyses.order_by('-analyzed_at').first()
        repo_list.append({
            'repo': r,
            'latest_analysis': latest_analysis,
            'analyses_count': r.analyses.count(),
        })

    # If sorted by health score, sort in memory by latest_analysis score
    if sort_by == 'health':
        repo_list.sort(
            key=lambda x: x['latest_analysis'].health_score if x['latest_analysis'] else 0,
            reverse=True
        )

    return render(request, 'history.html', {
        'repo_list': repo_list,
        'query': query,
        'sort_by': sort_by,
        'total_count': len(repo_list),
    })


def history_detail_view(request: HttpRequest, owner: str, repo: str) -> HttpResponse:
    """
    Displays historical audit log and time-series trend of health scores
    and metrics over multiple analyses for a specific repository.
    """
    full_name = f"{owner}/{repo}"
    repository = get_object_or_404(Repository, full_name__iexact=full_name)
    analyses = repository.analyses.order_by('-analyzed_at')

    trend_data = AnalyticsEngine.calculate_historical_trend(repository.analyses.order_by('analyzed_at'))
    trend_json = json.dumps(trend_data)

    return render(request, 'history_detail.html', {
        'repository': repository,
        'analyses': analyses,
        'trend': trend_data,
        'trend_json': trend_json,
    })


def compare_view(request: HttpRequest) -> HttpResponse:
    """
    Compares 2 or 3 public GitHub repositories across health metrics,
    commit velocity, pull requests, issues, and language statistics.
    Strictly presents objective comparison without 'winner' or 'best' labels.
    """
    form = RepositoryCompareForm(request.GET or None)
    repos_to_compare = []

    repo1_input = request.GET.get('repo1', '').strip()
    repo2_input = request.GET.get('repo2', '').strip()
    repo3_input = request.GET.get('repo3', '').strip()

    raw_candidates = [r for r in [repo1_input, repo2_input, repo3_input] if r]

    comparison_results = None
    comparison_chart_json = None

    if len(raw_candidates) >= 2:
        service = GitHubService()
        parsed_repos = []

        for raw in raw_candidates:
            try:
                owner, repo_name = GitHubService.validate_and_normalize(raw)
                full_name = f"{owner}/{repo_name}"

                # Check if repository and analysis exist in DB
                db_repo = Repository.objects.filter(full_name__iexact=full_name).first()
                latest_analysis = db_repo.analyses.order_by('-analyzed_at').first() if db_repo else None

                if db_repo and latest_analysis:
                    # Use existing data
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
                        'primary_language': primary_lang.language if primary_lang else 'Not specified',
                        'license': db_repo.license or 'Not specified',
                        'commits_count': latest_analysis.commits_count,
                        'contributors_count': latest_analysis.contributors_count,
                    })
                else:
                    # Fetch live metadata and quick score
                    r_data = service.get_repository(owner, repo_name)
                    langs_data = service.get_languages(owner, repo_name)
                    contribs_data = service.get_contributors(owner, repo_name, limit=5)
                    health = AnalyticsEngine.calculate_health_score(r_data, langs_data, contribs_data)
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
                    })
            except Exception as e:
                messages.warning(request, f"Could not load repository '{raw}': {e}")

        if len(parsed_repos) >= 2:
            comparison_results = AnalyticsEngine.compare_repositories(parsed_repos)
            comparison_chart_json = json.dumps({
                'labels': comparison_results['chart_labels'],
                'stars': comparison_results['stars_data'],
                'forks': comparison_results['forks_data'],
                'health': comparison_results['health_data'],
            })

    return render(request, 'compare.html', {
        'form': form,
        'candidates': raw_candidates,
        'comparison': comparison_results,
        'chart_json': comparison_chart_json,
    })


def about_view(request: HttpRequest) -> HttpResponse:
    """
    Displays the OpenSourceLens platform architecture and methodology.
    """
    return render(request, 'about.html')


# Custom Error Handlers
def error_400_view(request: HttpRequest, exception=None) -> HttpResponseBadRequest:
    return render(request, 'errors/400.html', status=400)


def error_404_view(request: HttpRequest, exception=None) -> HttpResponseNotFound:
    return render(request, 'errors/404.html', status=404)


def error_500_view(request: HttpRequest) -> HttpResponseServerError:
    return render(request, 'errors/500.html', status=500)
