"""
GitHub API Service for OpenSourceLens.
Provides abstraction over GitHub REST API with robust error handling,
validation, rate-limiting support, timeouts, and pagination.
"""

import re
import json
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
    pass


class GitHubRateLimitExceededError(GitHubAPIError):
    """Raised when GitHub API rate limit is exceeded (HTTP 403 / 429)."""
    def __init__(self, message: str, reset_timestamp: Optional[int] = None, status_code: int = 403):
        super().__init__(message, status_code=status_code)
        self.reset_timestamp = reset_timestamp


class GitHubTimeoutError(GitHubAPIError):
    """Raised when a GitHub API request times out."""
    pass


# Aliases for convenience
GitHubRateLimitError = GitHubRateLimitExceededError


class GitHubService:
    """
    Service client for interacting with the public GitHub REST API.
    Provides robust pagination, timeouts, error normalization, and rate-limit detection.
    """

    REPO_REGEX = re.compile(r'^[a-zA-Z0-9_\-\.]+\/[a-zA-Z0-9_\-\.]+$')

    def __init__(self, token: Optional[str] = None):
        self.base_url = getattr(settings, 'GITHUB_API_BASE_URL', 'https://api.github.com').rstrip('/')
        self.token = token or getattr(settings, 'GITHUB_TOKEN', '')
        self.timeout = getattr(settings, 'GITHUB_API_TIMEOUT', 12)
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'OpenSourceLens-OST-App',
        })
        if self.token:
            self.session.headers.update({'Authorization': f'Bearer {self.token}'})

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
            logger.error("GitHub API unauthorized (401). Invalid token.")
            raise GitHubAPIError(
                "GitHub API authentication failed (HTTP 401). "
                "Please verify your GITHUB_TOKEN configuration."
            )

        if response.status_code in (403, 429):
            rate_limit_remaining = response.headers.get('x-ratelimit-remaining', '')
            reset_ts = response.headers.get('x-ratelimit-reset')
            reset_str = ""
            if reset_ts:
                try:
                    reset_dt = datetime.fromtimestamp(int(reset_ts), tz=timezone.utc)
                    reset_str = f" Rate limit resets at {reset_dt.strftime('%H:%M:%S UTC')}."
                except Exception:
                    pass

            if rate_limit_remaining == '0' or 'rate limit' in response.text.lower() or response.status_code == 429:
                logger.error(f"GitHub API rate limit exceeded.{reset_str}")
                raise GitHubRateLimitExceededError(
                    f"GitHub API rate limit reached.{reset_str} "
                    "Please configure a GITHUB_TOKEN in your .env file or wait before retrying."
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
                response = self.session.get(url, params=query_params, timeout=self.timeout)
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
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout requesting page {page} for {endpoint}")
                if page == 1:
                    raise GitHubTimeoutError("GitHub request timed out. Please try again.")
                break
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failure on page {page} for {endpoint}: {e}")
                if page == 1:
                    raise GitHubAPIError(
                        "We couldn't retrieve repository data due to a network connection failure."
                    )
                break

        return results[:limit]

    def get_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        """
        Retrieves core repository metadata from GitHub.
        """
        repo_str = f"{owner}/{repo}"
        url = f"{self.base_url}/repos/{owner}/{repo}"
        try:
            response = self.session.get(url, timeout=self.timeout)
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
        except requests.exceptions.Timeout:
            logger.error(f"Timeout requesting {url}")
            raise GitHubTimeoutError("GitHub request timed out. Please try again.")
        except requests.exceptions.RequestException as e:
            logger.exception(f"Connection error requesting {url}: {e}")
            raise GitHubAPIError(
                "We couldn't retrieve repository data right now due to a network connection failure. "
                "Please verify your internet connection and try again."
            )

    def get_languages(self, owner: str, repo: str) -> Dict[str, int]:
        """
        Retrieves programming language byte breakdown for the repository.
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/languages"
        try:
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code == 200:
                return response.json()
            return {}
        except requests.exceptions.RequestException as e:
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
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieves pull requests with resolution state (open, closed, merged) across pages.
        """
        endpoint = f"/repos/{owner}/{repo}/pulls"
        params = {'state': 'all'}
        raw_items = self._paginate(endpoint, params=params, limit=limit, per_page=100)
        prs = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            raw_state = item.get('state', 'open')
            merged_at = item.get('merged_at')
            state = 'merged' if merged_at else raw_state
            prs.append({
                'pr_number': item.get('number'),
                'title': (item.get('title') or '')[:200],
                'state': state,
                'created_at': item.get('created_at'),
                'closed_at': item.get('closed_at'),
                'merged_at': merged_at,
            })
        return prs
