"""
Database models for OpenSourceLens.
Defines relational schemas for Repository, Contributor, CommitActivity,
Issue, PullRequest, Language, and historical RepositoryAnalysis snapshots.
"""

from django.db import models


class Repository(models.Model):
    """
    Stores core metadata and overall statistics for a GitHub repository.
    Includes rich metadata captured from the GitHub REST API.
    """
    owner = models.CharField(max_length=255, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    full_name = models.CharField(max_length=512, unique=True, db_index=True)
    description = models.TextField(blank=True, null=True)
    url = models.URLField(max_length=500)
    stars = models.PositiveIntegerField(default=0, db_index=True)
    forks = models.PositiveIntegerField(default=0)
    watchers = models.PositiveIntegerField(default=0)
    open_issues = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(db_index=True)
    updated_at = models.DateTimeField(db_index=True)
    pushed_at = models.DateTimeField(blank=True, null=True, db_index=True)
    default_branch = models.CharField(max_length=100, default='main')
    license = models.CharField(max_length=255, blank=True, null=True)
    license_spdx = models.CharField(max_length=100, blank=True, null=True)
    language = models.CharField(max_length=100, blank=True, null=True)
    size = models.PositiveIntegerField(default=0, help_text="Repository size in KB")
    topics = models.JSONField(default=list, blank=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    is_fork = models.BooleanField(default=False)
    has_issues = models.BooleanField(default=True)
    has_wiki = models.BooleanField(default=False)
    has_pages = models.BooleanField(default=False)
    subscribers_count = models.PositiveIntegerField(default=0)
    network_count = models.PositiveIntegerField(default=0)
    fetched_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        verbose_name = 'Repository'
        verbose_name_plural = 'Repositories'
        ordering = ['-stars', 'name']
        indexes = [
            models.Index(fields=['owner', 'name']),
            models.Index(fields=['-fetched_at']),
        ]

    def __str__(self):
        return self.full_name


class Contributor(models.Model):
    """
    Stores contributor statistics associated with a repository.
    """
    repository = models.ForeignKey(
        Repository,
        on_delete=models.CASCADE,
        related_name='contributors'
    )
    username = models.CharField(max_length=255, db_index=True)
    contributions = models.PositiveIntegerField(default=0)
    avatar_url = models.URLField(max_length=500, blank=True, null=True)
    profile_url = models.URLField(max_length=500, blank=True, null=True)

    class Meta:
        verbose_name = 'Contributor'
        verbose_name_plural = 'Contributors'
        ordering = ['-contributions']
        unique_together = ('repository', 'username')
        indexes = [
            models.Index(fields=['repository', '-contributions']),
        ]

    def __str__(self):
        return f"{self.username} ({self.repository.full_name})"


class CommitActivity(models.Model):
    """
    Stores periodic commit frequency data for a repository.
    """
    repository = models.ForeignKey(
        Repository,
        on_delete=models.CASCADE,
        related_name='commit_activities'
    )
    date = models.DateField(db_index=True)
    commit_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Commit Activity'
        verbose_name_plural = 'Commit Activities'
        ordering = ['-date']
        unique_together = ('repository', 'date')
        indexes = [
            models.Index(fields=['repository', '-date']),
        ]

    def __str__(self):
        return f"{self.repository.full_name} - {self.date}: {self.commit_count} commits"


class Issue(models.Model):
    """
    Stores issues fetched from a repository for tracking issue resolution health.
    Pull requests are explicitly separated from issues.
    """
    STATE_CHOICES = (
        ('open', 'Open'),
        ('closed', 'Closed'),
    )

    repository = models.ForeignKey(
        Repository,
        on_delete=models.CASCADE,
        related_name='issues'
    )
    issue_number = models.PositiveIntegerField()
    title = models.CharField(max_length=500)
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default='open', db_index=True)
    created_at = models.DateTimeField(db_index=True)
    closed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = 'Issue'
        verbose_name_plural = 'Issues'
        ordering = ['-created_at']
        unique_together = ('repository', 'issue_number')
        indexes = [
            models.Index(fields=['repository', 'state']),
            models.Index(fields=['repository', '-created_at']),
        ]

    def __str__(self):
        return f"#{self.issue_number} - {self.title[:50]} ({self.state})"


class PullRequest(models.Model):
    """
    Stores pull requests fetched from a repository for tracking review velocity.
    """
    STATE_CHOICES = (
        ('open', 'Open'),
        ('closed', 'Closed'),
        ('merged', 'Merged'),
    )

    repository = models.ForeignKey(
        Repository,
        on_delete=models.CASCADE,
        related_name='pull_requests'
    )
    pr_number = models.PositiveIntegerField()
    title = models.CharField(max_length=500, blank=True, default='')
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default='open', db_index=True)
    created_at = models.DateTimeField(db_index=True)
    closed_at = models.DateTimeField(blank=True, null=True)
    merged_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = 'Pull Request'
        verbose_name_plural = 'Pull Requests'
        ordering = ['-created_at']
        unique_together = ('repository', 'pr_number')
        indexes = [
            models.Index(fields=['repository', 'state']),
            models.Index(fields=['repository', '-created_at']),
        ]

    def __str__(self):
        return f"PR #{self.pr_number} ({self.state}) - {self.repository.full_name}"


class Language(models.Model):
    """
    Stores programming languages breakdown by byte counts for a repository.
    """
    repository = models.ForeignKey(
        Repository,
        on_delete=models.CASCADE,
        related_name='languages'
    )
    language = models.CharField(max_length=100)
    bytes = models.BigIntegerField(default=0)
    percentage = models.FloatField(default=0.0)

    class Meta:
        verbose_name = 'Language'
        verbose_name_plural = 'Languages'
        ordering = ['-bytes']
        unique_together = ('repository', 'language')
        indexes = [
            models.Index(fields=['repository', '-bytes']),
        ]

    def __str__(self):
        return f"{self.language} ({self.percentage:.1f}%) - {self.repository.full_name}"


class RepositoryAnalysis(models.Model):
    """
    Stores historical analysis snapshots for trend tracking and history audits.
    Maintains complete audit trails across varying evaluation windows.
    """
    repository = models.ForeignKey(
        Repository,
        on_delete=models.CASCADE,
        related_name='analyses'
    )
    analyzed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    analysis_window = models.CharField(max_length=20, default='90d')
    stars = models.PositiveIntegerField(default=0)
    forks = models.PositiveIntegerField(default=0)
    open_issues = models.PositiveIntegerField(default=0)
    health_score = models.PositiveIntegerField(default=0)
    health_tier = models.CharField(max_length=50, default='Good')
    activity_score = models.PositiveIntegerField(default=0)
    issue_score = models.PositiveIntegerField(default=0)
    pr_score = models.PositiveIntegerField(default=0)
    contributor_score = models.PositiveIntegerField(default=0)
    maintenance_score = models.PositiveIntegerField(default=0)
    commits_count = models.PositiveIntegerField(default=0)
    contributors_count = models.PositiveIntegerField(default=0)
    prs_count = models.PositiveIntegerField(default=0)
    issue_resolution_rate = models.FloatField(default=0.0)
    pr_merge_rate = models.FloatField(default=0.0)
    data_coverage = models.JSONField(default=dict, blank=True)
    snapshot_payload = models.JSONField(default=dict, blank=True, help_text="Complete isolated analytics payload for this snapshot")

    class Meta:
        verbose_name = 'Repository Analysis'
        verbose_name_plural = 'Repository Analyses'
        ordering = ['-analyzed_at']
        indexes = [
            models.Index(fields=['repository', '-analyzed_at']),
        ]

    def __str__(self):
        return f"{self.repository.full_name} Analysis ({self.analyzed_at.strftime('%Y-%m-%d %H:%M')}) - Score {self.health_score}"
