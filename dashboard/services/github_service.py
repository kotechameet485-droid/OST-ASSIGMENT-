"""
GitHub API Service for OpenSourceLens.
Provides abstraction over GitHub REST API with robust error handling,
validation, rate-limiting support, timeouts, and pagination.
"""

import re
import json
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class GitHubAPIError(Exception):
    """Base exception for all GitHub API service errors."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class GitHubInvalidRepoError(GitHubAPIError):
    """Raised when repository input string fails format validation."""
    pass


class GitHubRepoNotFoundError(GitHubAPIError):
    """Raised when repository does not exist on GitHub (HTTP 404)."""
    def __init__(self, message: str = "Repository not found on GitHub.", status_code: int = 404):
        super().__init__(message, status_code=status_code)


class GitHubAuthenticationError(GitHubAPIError):
    """Raised when GitHub API authentication fails (HTTP 401)."""
    def __init__(self, message: str = "GitHub API authentication failed (HTTP 401).", status_code: int = 401):
        super().__init__(message, status_code=status_code)


class GitHubForbiddenError(GitHubAPIError):
    """Raised when repository is private, restricted, or forbidden (HTTP 403 with quota remaining)."""
    def __init__(self, message: str = "Access to repository forbidden or private (HTTP 403).", status_code: int = 403):
        super().__init__(message, status_code=status_code)


class GitHubRateLimitExceededError(GitHubAPIError):
    """Raised when GitHub API rate limit is exceeded (HTTP 403 / 429 with 0 remaining)."""
    def __init__(
        self,
        message: str,
        reset_timestamp: Optional[int] = None,
        status_code: int = 403,
        is_authenticated: bool = False,
        remaining: int = 0,
        limit: int = 60,
        retry_after: Optional[int] = None,
    ):
        super().__init__(message, status_code=status_code)
        self.reset_timestamp = int(reset_timestamp) if reset_timestamp else None
        self.is_authenticated = is_authenticated
        self.remaining = remaining
        self.limit = limit
        self.retry_after = retry_after

        # Precompute human-friendly reset intervals
        now_ts = int(datetime.now(timezone.utc).timestamp())
        if self.reset_timestamp:
            try:
                self.reset_dt = datetime.fromtimestamp(self.reset_timestamp, tz=timezone.utc)
                self.reset_time_str = self.reset_dt.strftime('%H:%M:%S UTC')
                self.reset_in_seconds = max(0, int(self.reset_timestamp - now_ts))
                self.reset_in_minutes = max(0, int(round((self.reset_timestamp - now_ts) / 60.0)))
            except Exception:
                self.reset_dt = None
                self.reset_time_str = "Shortly"
                self.reset_in_seconds = retry_after or 60
                self.reset_in_minutes = max(1, (retry_after or 60) // 60)
        elif retry_after:
            self.reset_dt = datetime.fromtimestamp(now_ts + retry_after, tz=timezone.utc)
            self.reset_time_str = self.reset_dt.strftime('%H:%M:%S UTC')
            self.reset_in_seconds = retry_after
            self.reset_in_minutes = max(1, retry_after // 60)
        else:
            self.reset_dt = None
            self.reset_time_str = "Shortly"
            self.reset_in_seconds = 60
            self.reset_in_minutes = 1


class GitHubTimeoutError(GitHubAPIError):
    """Raised when a GitHub API request times out."""
    pass


class GitHubNetworkError(GitHubAPIError):
    """Raised on connection drops, DNS lookup failures, or socket errors."""
    pass


# Aliases for convenience
GitHubRateLimitError = GitHubRateLimitExceededError


class GitHubService:
    """
    Authoritative service client for interacting with the public GitHub REST API.
    Provides robust pagination, timeouts, error normalization, rate-limit detection,
    and safe exponential backoff retries.
    """

    REPO_REGEX = re.compile(r'^[a-zA-Z0-9_\-\.]+\/[a-zA-Z0-9_\-\.]+$')

    def __init__(self, token: Optional[str] = None):
        self.base_url = getattr(settings, 'GITHUB_API_BASE_URL', 'https://api.github.com').rstrip('/')
        raw_token = token if token is not None else getattr(settings, 'GITHUB_TOKEN', '')
        self.token = str(raw_token).strip() if raw_token else ''
        self.timeout = getattr(settings, 'GITHUB_API_TIMEOUT', 12)
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
            'User-Agent': 'OpenSourceLens-OST-App',
        })
        if self.token:
            self.session.headers.update({'Authorization': f'Bearer {self.token}'})

        # Log authentication presence without EVER logging secret values
        logger.info("GitHubService initialized (authenticated: %s)", bool(self.token))

    @property
    def is_authenticated(self) -> bool:
        """Returns True if a GitHub Personal Access Token is configured."""
        return bool(self.token)

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """
        Retrieves real-time rate limit metrics directly from GET /rate_limit.
        Returns structured diagnostic information without exposing token secrets.
        """
        url = f"{self.base_url}/rate_limit"
        try:
            response = self.session.get(url, timeout=min(5, self.timeout))
            if response.status_code == 200:
                data = response.json()
                core = data.get('resources', {}).get('core', {}) or data.get('rate', {})
                limit = int(core.get('limit', 5000 if self.token else 60))
                remaining = int(core.get('remaining', 0))
                reset_ts = int(core.get('reset', 0)) if core.get('reset') else None
                used = int(core.get('used', 0))

                reset_dt = datetime.fromtimestamp(reset_ts, tz=timezone.utc) if reset_ts else None
                now_dt = datetime.now(timezone.utc)
                reset_mins = max(0, int((reset_dt - now_dt).total_seconds() // 60)) if reset_dt else 0

                return {
                    'authenticated': bool(self.token),
                    'limit': limit,
                    'remaining': remaining,
                    'used': used,
                    'reset_timestamp': reset_ts,
                    'reset_at': reset_dt.strftime('%H:%M:%S UTC') if reset_dt else 'N/A',
                    'reset_in_minutes': reset_mins,
                    'is_rate_limited': remaining == 0,
                    'status': 'rate_limited' if remaining == 0 else 'ok',
                }
            elif response.status_code == 401:
                return {
                    'authenticated': False,
                    'error': 'invalid_token',
                    'message': 'Configured GITHUB_TOKEN is invalid or unauthorized (HTTP 401).',
                    'limit': 0,
                    'remaining': 0,
                    'is_rate_limited': False,
                    'status': 'auth_failed',
                }
        except Exception as e:
            logger.warning(f"Could not retrieve rate limit status from GitHub: {e}")

        return {
            'authenticated': bool(self.token),
            'limit': 5000 if self.token else 60,
            'remaining': 0 if not self.token else 5000,
            'reset_at': 'N/A',
            'reset_timestamp': None,
            'reset_in_minutes': 0,
            'is_rate_limited': False,
            'status': 'unknown',
        }

    @classmethod
    def validate_and_normalize(cls, raw_input: str) -> Tuple[str, str]:
        """
        Validates and extracts owner and repository name from raw input.
        Supports both 'owner/repo' and full 'https://github.com/owner/repo' format.
        
        Returns:
            Tuple[str, str]: (owner, repo)
            
        Raises:
            GitHubInvalidRepoError: If input format is invalid.
        """
        if not raw_input or not isinstance(raw_input, str):
            raise GitHubInvalidRepoError(
                "Repository input cannot be empty. Expected format: owner/repository"
            )

        cleaned = raw_input.strip()

        # Handle full GitHub URL formats
        url_match = re.search(r'github\.com[/:]([a-zA-Z0-9_\-\.]+)/([a-zA-Z0-9_\-\.]+)', cleaned)
        if url_match:
            owner, repo = url_match.group(1), url_match.group(2)
            if repo.endswith('.git'):
                repo = repo[:-4]
            return owner, repo

        # Handle raw owner/repo string
        if not cls.REPO_REGEX.match(cleaned):
            raise GitHubInvalidRepoError(
                "Invalid repository format. Expected: owner/repository (e.g. facebook/react)"
            )

        parts = cleaned.split('/')
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise GitHubInvalidRepoError(
                "Invalid repository format. Expected: owner/repository (e.g. facebook/react)"
            )

        return parts[0], parts[1]

    def _handle_response(self, response: requests.Response, repo_str: str) -> Any:
        """
        Centralized HTTP error response handler for GitHub API requests.
        Differentiates 401 authentication errors, 403 rate limits, 403 forbidden permissions,
        404 not found, 429 too many requests, and 5xx server errors.
        """
        if response.status_code == 200:
            try:
                return response.json()
            except (json.JSONDecodeError, ValueError) as err:
                logger.error(f"Malformed JSON from GitHub API for {repo_str}: {err}")
                raise GitHubAPIError("Received an unparseable response from GitHub API.")

        if response.status_code == 404:
            logger.warning(f"Repository not found: {repo_str}")
            raise GitHubRepoNotFoundError(
                f"Repository '{repo_str}' was not found on GitHub. "
                "Please verify the repository name and ensure it is public."
            )

        if response.status_code == 401:
            logger.error("GitHub API unauthorized (401). Invalid or expired token.")
            raise GitHubAuthenticationError(
                "GitHub API authentication failed (HTTP 401). "
                "Your configured GITHUB_TOKEN is invalid or has expired. "
                "Please update your token in .env or remove it to use unauthenticated access."
            )

        if response.status_code in (403, 429):
            rate_limit_remaining = response.headers.get('x-ratelimit-remaining')
            rate_limit_limit = int(response.headers.get('x-ratelimit-limit', 5000 if self.token else 60))
            reset_ts_raw = response.headers.get('x-ratelimit-reset')
            retry_after_raw = response.headers.get('retry-after')

            reset_ts = None
            if reset_ts_raw:
                try:
                    reset_ts = int(reset_ts_raw)
                except ValueError:
                    pass

            retry_after = None
            if retry_after_raw:
                try:
                    retry_after = int(retry_after_raw)
                except ValueError:
                    pass

            is_rate_limit = (
                rate_limit_remaining == '0'
                or response.status_code == 429
                or 'rate limit' in response.text.lower()
                or 'secondary rate limit' in response.text.lower()
            )

            if is_rate_limit:
                reset_dt = datetime.fromtimestamp(reset_ts, tz=timezone.utc) if reset_ts else None
                reset_str = f" Rate limit resets at {reset_dt.strftime('%H:%M:%S UTC')}." if reset_dt else ""

                if self.token:
                    msg = (
                        f"GitHub API rate limit reached (5,000 req/hr tier).{reset_str} "
                        "Please wait for your quota to reset before triggering live refreshes."
                    )
                else:
                    msg = (
                        f"GitHub API rate limit reached (60 req/hr unauthenticated tier).{reset_str} "
                        "Configure a personal access token (GITHUB_TOKEN) in your .env file to increase your limit to 5,000 req/hr."
                    )

                logger.error(f"GitHub API rate limit exceeded (authenticated: {bool(self.token)}).{reset_str}")
                raise GitHubRateLimitExceededError(
                    message=msg,
                    reset_timestamp=reset_ts,
                    status_code=response.status_code,
                    is_authenticated=bool(self.token),
                    remaining=0,
                    limit=rate_limit_limit,
                    retry_after=retry_after,
                )
            else:
                # 403 without rate limit: Access forbidden or private repository
                logger.warning(f"GitHub access forbidden for {repo_str} (HTTP 403, remaining: {rate_limit_remaining})")
                raise GitHubForbiddenError(
                    f"Access to repository '{repo_str}' was forbidden by GitHub (HTTP 403). "
                    "This repository may be private, archived with restricted access, or blocked."
                )

        if response.status_code in (500, 502, 503, 504):
            logger.error(f"GitHub server error {response.status_code}: {response.text[:200]}")
            raise GitHubAPIError(
                f"GitHub is temporarily experiencing service difficulties (HTTP {response.status_code}). "
                "Please try again shortly."
            )

        logger.error(f"GitHub API error {response.status_code}: {response.text[:200]}")
        raise GitHubAPIError(
            f"We couldn't retrieve repository data right now (GitHub API status {response.status_code}). "
            "Please try again later."
        )

    def _request_with_retry(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 2
    ) -> requests.Response:
        """
        Executes a GET request with limited retry/backoff for transient 5xx errors or connection timeouts.
        Never retries 4xx client errors (401, 403, 404, 422, rate-limits).
        """
        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                # If transient 5xx server error and retries remain, wait and retry
                if response.status_code in (500, 502, 503, 504) and attempt < max_retries:
                    logger.warning(f"Transient HTTP {response.status_code} from {url}, retrying attempt {attempt + 1}...")
                    time.sleep(0.4 * (attempt + 1))
                    continue
                return response
            except requests.exceptions.Timeout as e:
                last_exception = e
                if attempt < max_retries:
                    logger.warning(f"Timeout on {url}, retrying attempt {attempt + 1}...")
                    time.sleep(0.4 * (attempt + 1))
                    continue
                raise GitHubTimeoutError("GitHub request timed out. Please try again.")
            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt < max_retries:
                    logger.warning(f"Connection failure on {url}, retrying attempt {attempt + 1}...")
                    time.sleep(0.4 * (attempt + 1))
                    continue
                raise GitHubAPIError(
                    "We couldn't retrieve repository data right now due to a network connection failure. "
                    "Please verify your internet connection and try again."
                )
        if last_exception:
            raise last_exception

    def _paginate(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        per_page: int = 100,
        max_pages: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Reusable pagination engine for GitHub API endpoints.
        Paginates until limit is reached, no more items are returned,
        or max_pages threshold is exceeded.
        """
        results: List[Dict[str, Any]] = []
        page = 1
        query_params = dict(params or {})

        while len(results) < limit and page <= max_pages:
            batch_size = min(per_page, limit - len(results), 100)
            query_params['page'] = page
            query_params['per_page'] = batch_size

            url = f"{self.base_url}/{endpoint.lstrip('/')}"
            try:
                response = self._request_with_retry(url, params=query_params)
                if response.status_code != 200:
                    # If first page fails with error, trigger error handler
                    if page == 1:
                        self._handle_response(response, endpoint)
                    break

                data = response.json()
                if not isinstance(data, list) or not data:
                    break

                results.extend(data)

                # Stop if returned less than requested per_page
                if len(data) < batch_size:
                    break

                page += 1
            except (GitHubTimeoutError, GitHubAPIError):
                if page == 1:
                    raise
                break

        return results[:limit]

    def get_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        """
        Retrieves core repository metadata from GitHub.
        """
        repo_str = f"{owner}/{repo}"
        url = f"{self.base_url}/repos/{owner}/{repo}"
        response = self._request_with_retry(url)
        data = self._handle_response(response, repo_str)

        license_name = None
        license_spdx = None
        if data.get('license') and isinstance(data['license'], dict):
            license_name = data['license'].get('name')
            license_spdx = data['license'].get('spdx_id')

        return {
            'id': data.get('id'),
            'owner': owner,
            'name': repo,
            'full_name': data.get('full_name', repo_str),
            'description': data.get('description') or '',
            'url': data.get('html_url', f"https://github.com/{repo_str}"),
            'stars': data.get('stargazers_count', 0),
            'forks': data.get('forks_count', 0),
            'watchers': data.get('watchers_count', 0),
            'open_issues': data.get('open_issues_count', 0),
            'created_at': data.get('created_at'),
            'updated_at': data.get('updated_at'),
            'pushed_at': data.get('pushed_at'),
            'default_branch': data.get('default_branch', 'main'),
            'license': license_name or 'Not specified',
            'license_spdx': license_spdx or 'NOASSERTION',
            'language': data.get('language') or 'Not specified',
            'size': data.get('size', 0),
            'topics': data.get('topics', []) if isinstance(data.get('topics'), list) else [],
            'subscribers_count': data.get('subscribers_count', 0),
            'network_count': data.get('network_count', 0),
            'is_archived': data.get('archived', False),
            'is_fork': data.get('fork', False),
            'has_issues': data.get('has_issues', True),
            'has_wiki': data.get('has_wiki', False),
            'has_pages': data.get('has_pages', False),
        }

    def get_languages(self, owner: str, repo: str) -> Dict[str, int]:
        """
        Retrieves programming language byte breakdown for the repository.
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/languages"
        try:
            response = self._request_with_retry(url)
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            logger.warning(f"Failed to fetch languages for {owner}/{repo}: {e}")
            return {}

    def get_contributors(self, owner: str, repo: str, limit: int = 30) -> List[Dict[str, Any]]:
        """
        Retrieves top contributors for the repository using reusable pagination.
        """
        endpoint = f"/repos/{owner}/{repo}/contributors"
        raw_items = self._paginate(endpoint, limit=limit, per_page=min(limit, 100))
        return [
            {
                'username': item.get('login') or 'Unknown',
                'contributions': item.get('contributions', 0),
                'avatar_url': item.get('avatar_url'),
                'profile_url': item.get('html_url'),
            }
            for item in raw_items
            if isinstance(item, dict)
        ]

    def get_recent_commits(self, owner: str, repo: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Retrieves recent commit metadata for backward compatibility.
        """
        return self.get_commits(owner, repo, limit=limit)

    def get_commits(
        self,
        owner: str,
        repo: str,
        limit: int = 100,
        since: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves commits for the repository across pages, supporting configurable analysis window (since).
        """
        endpoint = f"/repos/{owner}/{repo}/commits"
        params: Dict[str, Any] = {}
        if since:
            params['since'] = since

        raw_items = self._paginate(endpoint, params=params, limit=limit, per_page=100)
        results = []
        for c in raw_items:
            if not isinstance(c, dict):
                continue
            commit_info = c.get('commit', {}) or {}
            author_info = commit_info.get('author') or {}
            committer_info = commit_info.get('committer') or {}
            date_str = author_info.get('date') or committer_info.get('date')
            results.append({
                'sha': c.get('sha', '')[:7],
                'message': (commit_info.get('message') or '').split('\n')[0][:120],
                'author': author_info.get('name') or committer_info.get('name') or 'Unknown',
                'date': date_str,
            })
        return results

    def get_issues(
        self,
        owner: str,
        repo: str,
        limit: int = 100,
        since: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves issues (both open and closed) across pages, strictly excluding pull requests.
        Supports filtering by date window via since parameter.
        """
        endpoint = f"/repos/{owner}/{repo}/issues"
        params: Dict[str, Any] = {'state': 'all'}
        if since:
            params['since'] = since

        # Over-fetch slightly to account for filtered PRs
        target_limit = limit
        raw_items = self._paginate(endpoint, params=params, limit=target_limit * 2, per_page=100)
        issues = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            # GitHub includes PRs in the issues endpoint; strictly filter them out
            if item.get('pull_request') is not None:
                continue
            issues.append({
                'issue_number': item.get('number'),
                'title': (item.get('title') or '')[:200],
                'state': item.get('state', 'open'),
                'created_at': item.get('created_at'),
                'closed_at': item.get('closed_at'),
            })
            if len(issues) >= target_limit:
                break
        return issues

    def get_pull_requests(
        self,
        owner: str,
        repo: str,
        limit: int = 100,
        since: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves pull requests with resolution state (open, closed, merged) across pages.
        Supports time-window filtering via the `since` parameter (ISO 8601 string).
        Ensures old pull requests outside the analysis window are not included.
        """
        endpoint = f"/repos/{owner}/{repo}/pulls"
        params: Dict[str, Any] = {'state': 'all', 'sort': 'created', 'direction': 'desc'}

        since_dt = None
        if since:
            try:
                cleaned = since.replace('Z', '+00:00')
                since_dt = datetime.fromisoformat(cleaned)
                if since_dt.tzinfo is None:
                    since_dt = since_dt.replace(tzinfo=timezone.utc)
            except Exception as e:
                logger.warning(f"Could not parse since parameter '{since}' as datetime: {e}")

        # Fetch with pagination, stopping if PRs fall outside the window
        raw_items = self._paginate(endpoint, params=params, limit=limit * 2, per_page=100)
        prs = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue

            created_at = item.get('created_at')
            if since_dt and created_at:
                try:
                    c_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    if c_dt.tzinfo is None:
                        c_dt = c_dt.replace(tzinfo=timezone.utc)
                    if c_dt < since_dt:
                        # Since PRs are sorted by created desc, subsequent PRs are also older
                        break
                except Exception:
                    pass

            raw_state = item.get('state', 'open')
            merged_at = item.get('merged_at')
            state = 'merged' if merged_at else raw_state
            prs.append({
                'pr_number': item.get('number'),
                'title': (item.get('title') or '')[:200],
                'state': state,
                'created_at': created_at,
                'closed_at': item.get('closed_at'),
                'merged_at': merged_at,
            })
            if len(prs) >= limit:
                break
        return prs

