"""
GitHub API Service for OpenSourceLens.
Provides abstraction over GitHub REST API with robust error handling,
validation, and rate-limiting support.
"""

import re
import logging
from typing import Dict, Any, List, Optional, Tuple
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class GitHubAPIError(Exception):
    """Base exception for all GitHub API service errors."""
    pass


class GitHubInvalidRepoError(GitHubAPIError):
    """Raised when repository input string fails format validation."""
    pass


class GitHubRepoNotFoundError(GitHubAPIError):
    """Raised when repository does not exist on GitHub (HTTP 404)."""
    pass


class GitHubRateLimitExceededError(GitHubAPIError):
    """Raised when GitHub API rate limit is exceeded (HTTP 403 / 429)."""
    pass


class GitHubService:
    """
    Service client for interacting with the public GitHub REST API.
    """

    REPO_REGEX = re.compile(r'^[a-zA-Z0-9_\-\.]+\/[a-zA-Z0-9_\-\.]+$')

    def __init__(self, token: Optional[str] = None):
        self.base_url = getattr(settings, 'GITHUB_API_BASE_URL', 'https://api.github.com')
        self.token = token or getattr(settings, 'GITHUB_TOKEN', '')
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
            # Remove trailing .git if present
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

    def _handle_response(self, response: requests.Response, repo_str: str) -> Dict[str, Any]:
        """
        Centralized HTTP error response handler for GitHub API requests.
        """
        if response.status_code == 200:
            return response.json()

        if response.status_code == 404:
            logger.warning(f"Repository not found: {repo_str}")
            raise GitHubRepoNotFoundError(
                f"Repository '{repo_str}' was not found on GitHub. "
                "Please verify the repository name and make sure it is public."
            )

        if response.status_code in (403, 429):
            rate_limit_remaining = response.headers.get('x-ratelimit-remaining', '0')
            if rate_limit_remaining == '0' or 'rate limit' in response.text.lower():
                logger.error("GitHub API rate limit exceeded.")
                raise GitHubRateLimitExceededError(
                    "GitHub API rate limit exceeded. "
                    "Please configure a GITHUB_TOKEN in your .env file or wait before retrying."
                )

        logger.error(f"GitHub API error {response.status_code}: {response.text}")
        raise GitHubAPIError(
            f"We couldn't retrieve repository data right now (GitHub API status {response.status_code}). "
            "Please try again later."
        )

    def get_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        """
        Retrieves core repository metadata from GitHub.
        """
        repo_str = f"{owner}/{repo}"
        url = f"{self.base_url}/repos/{owner}/{repo}"
        try:
            response = self.session.get(url, timeout=12)
            data = self._handle_response(response, repo_str)

            license_name = None
            if data.get('license') and isinstance(data['license'], dict):
                license_name = data['license'].get('name') or data['license'].get('spdx_id')

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
                'subscribers_count': data.get('subscribers_count', 0),
                'network_count': data.get('network_count', 0),
                'is_archived': data.get('archived', False),
                'is_fork': data.get('fork', False),
            }
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
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()
            return {}
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch languages for {owner}/{repo}: {e}")
            return {}

    def get_contributors(self, owner: str, repo: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Retrieves top contributors for the repository.
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/contributors?per_page={limit}"
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    return [
                        {
                            'username': item.get('login'),
                            'contributions': item.get('contributions', 0),
                            'avatar_url': item.get('avatar_url'),
                            'profile_url': item.get('html_url'),
                        }
                        for item in data
                    ]
            return []
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch contributors for {owner}/{repo}: {e}")
            return []

    def get_recent_commits(self, owner: str, repo: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Retrieves recent commit metadata for backward compatibility.
        """
        return self.get_commits(owner, repo, limit=limit)

    def get_commits(self, owner: str, repo: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieves commits for the repository (up to limit).
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/commits?per_page={min(limit, 100)}"
        try:
            response = self.session.get(url, timeout=12)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    results = []
                    for c in data:
                        commit_info = c.get('commit', {}) or {}
                        author_info = commit_info.get('author') or {}
                        committer_info = commit_info.get('committer') or {}
                        date_str = author_info.get('date') or committer_info.get('date')
                        results.append({
                            'sha': c.get('sha', '')[:7],
                            'message': (commit_info.get('message') or '').split('\n')[0][:120],
                            'author': author_info.get('name') or 'Unknown',
                            'date': date_str,
                        })
                    return results
            return []
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch commits for {owner}/{repo}: {e}")
            return []

    def get_issues(self, owner: str, repo: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retrieves recent issues (both open and closed) excluding pull requests.
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/issues?state=all&per_page={min(limit, 100)}"
        try:
            response = self.session.get(url, timeout=12)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    issues = []
                    for item in data:
                        # GitHub includes PRs in the issues endpoint; filter them out
                        if item.get('pull_request') is not None:
                            continue
                        issues.append({
                            'issue_number': item.get('number'),
                            'title': (item.get('title') or '')[:200],
                            'state': item.get('state', 'open'),
                            'created_at': item.get('created_at'),
                            'closed_at': item.get('closed_at'),
                        })
                    return issues
            return []
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch issues for {owner}/{repo}: {e}")
            return []

    def get_pull_requests(self, owner: str, repo: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retrieves recent pull requests with resolution state (open, closed, merged).
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls?state=all&per_page={min(limit, 100)}"
        try:
            response = self.session.get(url, timeout=12)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    prs = []
                    for item in data:
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
            return []
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch pull requests for {owner}/{repo}: {e}")
            return []
