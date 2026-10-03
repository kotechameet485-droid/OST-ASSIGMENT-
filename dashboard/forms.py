"""
Forms for OpenSourceLens Dashboard.
Handles repository search validation.
"""

from django import forms
from dashboard.services.github_service import GitHubService, GitHubInvalidRepoError


class RepositorySearchForm(forms.Form):
    """
    Search form for entering and validating GitHub repositories.
    Supports configurable analysis windows (30d, 90d, 180d, 365d).
    """
    WINDOW_CHOICES = (
        ('30d', 'Last 30 Days'),
        ('90d', 'Last 90 Days'),
        ('180d', 'Last 6 Months'),
        ('365d', 'Last 1 Year'),
    )

    repository = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg os-search-input',
            'placeholder': 'github.com/owner/repository (e.g. facebook/react)',
            'aria-label': 'GitHub Repository Input',
            'autocomplete': 'off',
            'spellcheck': 'false',
            'id': 'repoSearchInput',
        }),
        error_messages={
            'required': 'Please enter a GitHub repository (e.g. facebook/react).',
        }
    )
    window = forms.ChoiceField(
        choices=WINDOW_CHOICES,
        required=False,
        initial='90d',
        widget=forms.Select(attrs={
            'class': 'form-select form-select-lg os-window-select font-monospace',
            'id': 'analysisWindowSelect',
            'aria-label': 'Analysis Scope Window',
        })
    )

    def clean_repository(self):
        data = self.cleaned_data.get('repository', '').strip()
        try:
            owner, repo = GitHubService.validate_and_normalize(data)
            return f"{owner}/{repo}"
        except GitHubInvalidRepoError as e:
            raise forms.ValidationError(str(e))

    def clean_window(self):
        val = self.cleaned_data.get('window', '90d')
        if val not in dict(self.WINDOW_CHOICES):
            return '90d'
        return val


class RepositoryCompareForm(forms.Form):
    """
    Form for entering up to three public repositories for side-by-side comparison.
    """
    repo1 = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control font-monospace',
            'placeholder': 'e.g. facebook/react',
            'id': 'compareRepo1',
        })
    )
    repo2 = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control font-monospace',
            'placeholder': 'e.g. vuejs/core',
            'id': 'compareRepo2',
        })
    )
    repo3 = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control font-monospace',
            'placeholder': 'e.g. angular/angular (optional)',
            'id': 'compareRepo3',
        })
    )

    def clean_repo1(self):
        val = self.cleaned_data.get('repo1', '').strip()
        try:
            owner, repo = GitHubService.validate_and_normalize(val)
            return f"{owner}/{repo}"
        except GitHubInvalidRepoError as e:
            raise forms.ValidationError(str(e))

    def clean_repo2(self):
        val = self.cleaned_data.get('repo2', '').strip()
        try:
            owner, repo = GitHubService.validate_and_normalize(val)
            return f"{owner}/{repo}"
        except GitHubInvalidRepoError as e:
            raise forms.ValidationError(str(e))

    def clean_repo3(self):
        val = self.cleaned_data.get('repo3', '').strip()
        if not val:
            return ""
        try:
            owner, repo = GitHubService.validate_and_normalize(val)
            return f"{owner}/{repo}"
        except GitHubInvalidRepoError as e:
            raise forms.ValidationError(str(e))

