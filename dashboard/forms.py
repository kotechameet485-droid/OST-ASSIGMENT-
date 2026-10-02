"""
Forms for OpenSourceLens Dashboard.
Handles repository search validation.
"""

from django import forms
from dashboard.services.github_service import GitHubService, GitHubInvalidRepoError


class RepositorySearchForm(forms.Form):
    """
    Search form for entering and validating GitHub repositories.
    """
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

    def clean_repository(self):
        data = self.cleaned_data.get('repository', '').strip()
        try:
            owner, repo = GitHubService.validate_and_normalize(data)
            return f"{owner}/{repo}"
        except GitHubInvalidRepoError as e:
            raise forms.ValidationError(str(e))


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

