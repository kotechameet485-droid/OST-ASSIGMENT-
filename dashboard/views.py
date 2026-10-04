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
    GitHubAuthenticationError,
    GitHubForbiddenError,
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
    then renders the intelligence dashboard. Supports POST with CSRF for refresh.
    """
    raw_repo = ""
    window = "90d"
    force_refresh = False

    if request.method == 'POST':
        form = RepositorySearchForm(request.POST)
        if form.is_valid():
            raw_repo = form.cleaned_data['repository']
            window = form.cleaned_data.get('window') or '90d'
            force_refresh = request.POST.get('refresh', '').lower() in ('true', '1', 'yes')
        else:
            # Check for direct refresh POST payload
            raw_repo = (request.POST.get('repository') or request.POST.get('repo') or '').strip()
            window = request.POST.get('window', '90d').strip().lower()
            force_refresh = request.POST.get('refresh', '').lower() in ('true', '1', 'yes')
            if not raw_repo:
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, error)
                return redirect('home')
    else:
        raw_repo = (request.GET.get('repo') or request.GET.get('repository') or '').strip()
        window = request.GET.get('window', '90d').strip().lower()
        force_refresh = request.GET.get('refresh', '').lower() in ('true', '1', 'yes')
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
            owner,
            repo_name,
            window=window,
            force_refresh=force_refresh
        )
    except GitHubRepoNotFoundError as e:
        messages.error(request, str(e))
        return redirect('home')
    except GitHubAuthenticationError as e:
        logger.error(f"Authentication failure for {repo_str}: {e}")
        return render(request, 'errors/401.html', {'error': str(e)}, status=401)
    except GitHubForbiddenError as e:
        logger.warning(f"Forbidden/private repo {repo_str}: {e}")
        return render(request, 'errors/403.html', {'error': str(e), 'repo_str': repo_str}, status=403)
    except GitHubRateLimitExceededError as e:
        logger.warning(f"Rate limit reached without stored snapshot for {repo_str}: {e}")
        stored_repos = []
        try:
            stored_repos = Repository.objects.prefetch_related('analyses').order_by('-fetched_at')[:6]
        except Exception:
            pass

        return render(request, 'rate_limit.html', {
            'repo_name': repo_str,
            'window': window,
            'rate_limit_info': {
                'message': str(e),
                'reset_timestamp': e.reset_timestamp,
                'reset_time_str': getattr(e, 'reset_time_str', 'Shortly'),
                'reset_in_minutes': getattr(e, 'reset_in_minutes', 0),
                'reset_in_seconds': getattr(e, 'reset_in_seconds', 60),
                'is_authenticated': getattr(e, 'is_authenticated', False),
                'limit': getattr(e, 'limit', 60),
            },
            'stored_repos': stored_repos,
        }, status=429)
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
    Displays the catalog of previously analyzed repositories saved in the database,
    with server-side search, sorting, health scores, filters, and standard Django pagination.
    """
    from django.core.paginator import Paginator

    query = request.GET.get('q', '').strip()
    sort_by = request.GET.get('sort', 'recent').strip().lower()
    window_filter = request.GET.get('window', '').strip()
    lang_filter = request.GET.get('lang', '').strip()
    tier_filter = request.GET.get('tier', '').strip()
    page_number = request.GET.get('page')

    repo_list = RepositoryService.get_history_catalog(
        query=query,
        sort_by=sort_by,
        window_filter=window_filter,
        lang_filter=lang_filter,
        tier_filter=tier_filter
    )

    paginator = Paginator(repo_list, 15)  # 15 repositories per page
    page_obj = paginator.get_page(page_number)

    available_languages = list(
        Repository.objects.exclude(language__in=['', 'Not specified'])
        .values_list('language', flat=True)
        .distinct()
        .order_by('language')
    )

    return render(request, 'history.html', {
        'page_obj': page_obj,
        'repo_list': page_obj.object_list,
        'query': query,
        'sort_by': sort_by,
        'window': window_filter,
        'window_filter': window_filter,
        'lang': lang_filter,
        'language': lang_filter,
        'lang_filter': lang_filter,
        'tier': tier_filter,
        'tier_filter': tier_filter,
        'tiers': ['Excellent', 'Good', 'Moderate', 'At Risk'],
        'languages': available_languages,
        'available_languages': available_languages,
        'total_count': paginator.count,
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
    window = request.GET.get('window', '90d').strip().lower()

    raw_candidates = [r for r in [repo1_input, repo2_input, repo3_input] if r]

    comparison_results = None
    comparison_chart_json = None
    comparison_chart_data = None

    if len(raw_candidates) >= 2:
        comp_data = RepositoryService.compare_repositories(raw_candidates, window=window)
        if comp_data:
            comparison_results = comp_data['comparison']
            comparison_chart_json = comp_data['chart_json']
            comparison_chart_data = comp_data.get('comparison_chart_data')

    return render(request, 'compare.html', {
        'form': form,
        'candidates': raw_candidates,
        'comparison': comparison_results,
        'chart_json': comparison_chart_json,
        'comparison_chart_data': comparison_chart_data,
        'window': window,
        'analysis_window': window,
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
