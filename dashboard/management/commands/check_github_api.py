"""
Django Management Command: check_github_api
Validates GitHub API authentication status, rate limits, and reset times.
Guaranteed to NEVER expose the secret GITHUB_TOKEN.
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from dashboard.services.github_service import GitHubService


class Command(BaseCommand):
    help = "Checks GitHub REST API connectivity, authentication validity, and rate limit quotas."

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== OpenSourceLens — GitHub API Diagnostic ==="))

        token_configured = bool(getattr(settings, 'GITHUB_TOKEN', '').strip())
        self.stdout.write(f"Token Configured:    {'YES' if token_configured else 'NO'}")

        service = GitHubService()
        status_info = service.get_rate_limit_status()

        is_auth = status_info.get('authenticated', False)
        status_str = status_info.get('status', 'unknown')
        limit = status_info.get('limit', 0)
        remaining = status_info.get('remaining', 0)
        reset_at = status_info.get('reset_at', 'N/A')
        reset_mins = status_info.get('reset_in_minutes', 0)

        if is_auth:
            self.stdout.write(self.style.SUCCESS("Authentication:      AUTHENTICATED (Bearer token active)"))
            self.stdout.write(f"Quota Ceiling:       {limit:,} requests / hour")
        else:
            self.stdout.write(self.style.WARNING("Authentication:      UNAUTHENTICATED (IP-based access)"))
            self.stdout.write(f"Quota Ceiling:       {limit:,} requests / hour")

        if remaining > 100:
            rem_style = self.style.SUCCESS
        elif remaining > 0:
            rem_style = self.style.WARNING
        else:
            rem_style = self.style.ERROR

        self.stdout.write(rem_style(f"Requests Remaining:  {remaining:,} / {limit:,}"))
        self.stdout.write(f"Quota Reset Time:    {reset_at} (in {reset_mins} minute{'s' if reset_mins != 1 else ''})")

        if status_str == 'rate_limited' or remaining == 0:
            self.stdout.write(self.style.ERROR("\n[ALERT] Rate limit is currently EXHAUSTED."))
            if not is_auth:
                self.stdout.write(self.style.NOTICE("Tip: Configure GITHUB_TOKEN in your local .env to upgrade to 5,000 req/hr."))
            else:
                self.stdout.write(f"Tip: Live requests will resume after {reset_at}. Stored snapshots remain fully available.")
        elif status_info.get('error') == 'invalid_token':
            self.stdout.write(self.style.ERROR("\n[ERROR] Configured GITHUB_TOKEN was rejected by GitHub (HTTP 401)."))
            self.stdout.write(self.style.NOTICE("Tip: Please check your personal access token at https://github.com/settings/tokens."))
        else:
            self.stdout.write(self.style.SUCCESS("\n[OK] GitHub API connection is healthy and operational."))

        self.stdout.write(self.style.MIGRATE_HEADING("==================================================\n"))
