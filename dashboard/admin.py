"""
Django Admin registration for OpenSourceLens models.
Provides inspection tools for repositories, contributors, languages, issues, and PRs.
"""

from django.contrib import admin
from dashboard.models import (
    Repository,
    Contributor,
    CommitActivity,
    Issue,
    PullRequest,
    Language,
    RepositoryAnalysis,
)


class LanguageInline(admin.TabularInline):
    model = Language
    extra = 0
    readonly_fields = ('language', 'bytes', 'percentage')


class ContributorInline(admin.TabularInline):
    model = Contributor
    extra = 0
    readonly_fields = ('username', 'contributions')


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'stars', 'forks', 'open_issues', 'license', 'fetched_at')
    search_fields = ('owner', 'name', 'full_name', 'description')
    list_filter = ('license', 'default_branch', 'fetched_at')
    ordering = ('-stars',)
    inlines = [LanguageInline, ContributorInline]


@admin.register(Contributor)
class ContributorAdmin(admin.ModelAdmin):
    list_display = ('username', 'repository', 'contributions')
    search_fields = ('username', 'repository__full_name')
    list_filter = ('repository',)
    ordering = ('-contributions',)


@admin.register(CommitActivity)
class CommitActivityAdmin(admin.ModelAdmin):
    list_display = ('repository', 'date', 'commit_count')
    list_filter = ('date', 'repository')
    search_fields = ('repository__full_name',)


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ('issue_number', 'repository', 'title', 'state', 'created_at')
    list_filter = ('state', 'created_at')
    search_fields = ('title', 'repository__full_name', 'issue_number')


@admin.register(PullRequest)
class PullRequestAdmin(admin.ModelAdmin):
    list_display = ('pr_number', 'repository', 'state', 'created_at', 'merged_at')
    list_filter = ('state', 'created_at')
    search_fields = ('repository__full_name', 'pr_number')


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ('repository', 'language', 'bytes', 'percentage')
    list_filter = ('language',)
    search_fields = ('repository__full_name', 'language')


@admin.register(RepositoryAnalysis)
class RepositoryAnalysisAdmin(admin.ModelAdmin):
    list_display = ('repository', 'analyzed_at', 'health_score', 'health_tier', 'stars', 'forks')
    list_filter = ('health_tier', 'analyzed_at')
    search_fields = ('repository__full_name',)
    ordering = ('-analyzed_at',)

