"""
Views for OpenSourceLens Dashboard.
Connects HTTP requests to AnalysisService, RepositoryService, forms,
and responsive presentation templates.
Follows thin-controller and service-layer separation principles.
"""

import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseNotFound,
    HttpResponseServerError,
    HttpResponseBadRequest,
)

from dashboard.forms import RepositorySearchForm, RepositoryCompareForm
from dashboard.services.github_service import (
    GitHubService,
    GitHubAPIError,
    GitHubInvalidRepoError,
    GitHubRepoNotFoundError,
    GitHubRateLimitExceededError,
    GitHubTimeoutError,
)
from dashboard.services.analysis_service import AnalysisService
from dashboard.services.repository_service import RepositoryService
from dashboard.models import Repository

logger = logging.getLogger(__name__)


def home_view(request: HttpRequest) -> HttpResponse:
    """
    Renders the OpenSourceLens homepage with repository search form,
    analysis window selector, quick-sample repositories, and feature overview.
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
    Validates repository input and window, invokes AnalysisService to handle
    API ingestion, caching, Pandas analytics, and database synchronization,
    then renders the intelligence dashboard.
    """
    raw_repo = ""
    window = "90d"
    force_refresh = request.GET.get('refresh', '').lower() in ('true', '1', 'yes')

    if request.method == 'POST':
        form = RepositorySearchForm(request.POST)
        if form.is_valid():
            raw_repo = form.cleaned_data['repository']
            window = form.cleaned_data.get('window') or '90d'
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)
            return redirect('home')
    else:
        raw_repo = (request.GET.get('repo') or request.GET.get('repository') or '').strip()
        window = request.GET.get('window', '90d').strip().lower()
        if not raw_repo:
            return redirect('home')

    # Step 1: Validate repository format
    try:
        owner, repo_name = GitHubService.validate_and_normalize(raw_repo)
    except GitHubInvalidRepoError as e:
        messages.error(request, str(e))
        return redirect('home')

    repo_str = f"{owner}/{repo_name}"

    # Step 2: Run complete analysis pipeline
    analysis_svc = AnalysisService()
    try:
        context = analysis_svc.run_analysis(
            owner=owner,
            repo_name=repo_name,
            window=window,
            force_refresh=force_refresh
        )
    except GitHubRepoNotFoundError as e:
        messages.error(request, str(e))
        return redirect('home')
    except GitHubRateLimitExceededError as e:
        messages.error(request, str(e))
        return redirect('home')
    except GitHubTimeoutError as e:
        messages.error(request, str(e))
        return redirect('home')
    except GitHubAPIError as e:
        messages.error(request, str(e))
        return redirect('home')
    except Exception as e:
        logger.exception(f"Unexpected error while analyzing {repo_str}: {e}")
        messages.error(request, "An unexpected error occurred while processing repository analytics. Please try again.")
        return redirect('home')

    return render(request, 'dashboard.html', context)


def history_view(request: HttpRequest) -> HttpResponse:
    """
    Displays the catalog of previously analyzed repositories saved in PostgreSQL,
    with search, sorting, health scores, and score change indicators.
    """
    query = request.GET.get('q', '').strip()
    sort_by = request.GET.get('sort', 'recent').strip().lower()

    repo_list = RepositoryService.get_history_catalog(query=query, sort_by=sort_by)

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
    history_data = RepositoryService.get_history_detail(owner=owner, repo=repo)
    if not history_data:
        full_name = f"{owner}/{repo}"
        return get_object_or_404(Repository, full_name__iexact=full_name)

    return render(request, 'history_detail.html', history_data)


def compare_view(request: HttpRequest) -> HttpResponse:
    """
    Compares 2 or 3 public GitHub repositories across health metrics,
    commit velocity, pull requests, issues, and language statistics.
    Strictly presents objective comparison without 'winner' or 'best' labels.
    """
    form = RepositoryCompareForm(request.GET or None)

    repo1_input = request.GET.get('repo1', '').strip()
    repo2_input = request.GET.get('repo2', '').strip()
    repo3_input = request.GET.get('repo3', '').strip()

    raw_candidates = [r for r in [repo1_input, repo2_input, repo3_input] if r]

    comparison_results = None
    comparison_chart_json = None

    if len(raw_candidates) >= 2:
        comp_data = RepositoryService.compare_repositories(raw_candidates)
        if comp_data:
            comparison_results = comp_data['comparison']
            comparison_chart_json = comp_data['chart_json']

    return render(request, 'compare.html', {
        'form': form,
        'candidates': raw_candidates,
        'comparison': comparison_results,
        'chart_json': comparison_chart_json,
    })


def about_view(request: HttpRequest) -> HttpResponse:
    """
    Displays the OpenSourceLens platform architecture, methodology,
    mathematical formulas, and analytical limitations.
    """
    return render(request, 'about.html')


# Custom Error Handlers
def error_400_view(request: HttpRequest, exception=None) -> HttpResponseBadRequest:
    """Custom 400 Bad Request error handler."""
    return render(request, 'errors/400.html', status=400)


def error_404_view(request: HttpRequest, exception=None) -> HttpResponseNotFound:
    """Custom 404 Not Found error handler."""
    return render(request, 'errors/404.html', status=404)


def error_500_view(request: HttpRequest) -> HttpResponseServerError:
    """Custom 500 Internal Server Error handler."""
    return render(request, 'errors/500.html', status=500)
