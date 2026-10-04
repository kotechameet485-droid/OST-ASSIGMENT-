/**
 * OpenSourceLens Client Application Script
 * Provides client-side validation, multi-step loading experience,
 * sample auto-filling, and resilient error recovery.
 */

(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        initSearchForm();
        initSampleButtons();
        initKeyboardShortcuts();
        initTooltips();
    });

    /**
     * Initializes repository search form submission and loading orchestrations.
     */
    function initSearchForm() {
        var searchForm = document.getElementById('repoSearchForm');
        var searchInput = document.getElementById('repoSearchInput');
        var validationError = document.getElementById('clientValidationError');
        var loadingOverlay = document.getElementById('analysisLoadingOverlay');
        var loadingRepoName = document.getElementById('loadingRepoName');

        if (!searchForm || !searchInput) {
            return;
        }

        // Repository validation regex: supports owner/repo and https://github.com/owner/repo
        var repoRegex = /^(?:https?:\/\/)?(?:www\.)?github\.com\/([a-zA-Z0-9_\-\.]+)\/([a-zA-Z0-9_\-\.]+)|\b([a-zA-Z0-9_\-\.]+)\/([a-zA-Z0-9_\-\.]+)\b$/;

        var isSubmitting = false;

        searchForm.addEventListener('submit', function (e) {
            if (isSubmitting) {
                e.preventDefault();
                return false;
            }

            var rawValue = (searchInput.value || '').trim();

            if (!rawValue || !repoRegex.test(rawValue)) {
                e.preventDefault();
                if (validationError) {
                    validationError.classList.remove('d-none');
                }
                searchInput.classList.add('is-invalid');
                searchInput.focus();
                return false;
            }

            // Input is valid: clear errors and lock submission
            isSubmitting = true;
            if (validationError) {
                validationError.classList.add('d-none');
            }
            searchInput.classList.remove('is-invalid');

            // Disable submit button immediately to prevent double submissions
            var submitBtn = searchForm.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Analyzing...';
            }

            // Trigger truthful pipeline step progression
            if (loadingOverlay) {
                var cleanName = rawValue.replace(/^https?:\/\/github\.com\//, '');
                if (loadingRepoName) {
                    loadingRepoName.textContent = cleanName;
                }
                loadingOverlay.classList.remove('d-none');

                initLoadingStatusCycler();
            }
        });

        // Also protect any in-page refresh forms from double-clicking
        var refreshForms = document.querySelectorAll('form[action*="analyze"]');
        refreshForms.forEach(function (form) {
            if (form === searchForm) return;
            form.addEventListener('submit', function (e) {
                var btn = form.querySelector('button[type="submit"]');
                if (btn && btn.disabled) {
                    e.preventDefault();
                    return false;
                }
                if (btn) {
                    btn.disabled = true;
                    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Refreshing...';
                }
            });
        });

        // Clear error styling on user input
        searchInput.addEventListener('input', function () {
            if (validationError && !validationError.classList.contains('d-none')) {
                validationError.classList.add('d-none');
                searchInput.classList.remove('is-invalid');
            }
        });
    }

    /**
     * Cycles informative pipeline status messages without claiming premature completion.
     */
    function initLoadingStatusCycler() {
        var statusEl = document.getElementById('loadingStatusText');
        if (!statusEl) return;

        var messages = [
            'Connecting to GitHub REST API and validating endpoints...',
            'Fetching repository metadata, languages, and activity...',
            'Streaming paginated commits, issues, and pull requests...',
            'Executing Pandas calculations and 5-pillar health scoring...',
            'Synchronizing dataset and finalizing analysis snapshot...'
        ];

        var index = 0;
        setInterval(function () {
            index = (index + 1) % messages.length;
            if (statusEl) {
                statusEl.textContent = messages[index];
            }
        }, 1800);
    }

    /**
     * Auto-populates sample repositories on button click.
     */
    function initSampleButtons() {
        var sampleButtons = document.querySelectorAll('.sample-repo-btn');
        var searchInput = document.getElementById('repoSearchInput');
        var validationError = document.getElementById('clientValidationError');

        if (!sampleButtons.length || !searchInput) return;

        sampleButtons.forEach(function (button) {
            button.addEventListener('click', function () {
                var targetRepo = this.getAttribute('data-repo');
                if (targetRepo) {
                    searchInput.value = targetRepo;
                    searchInput.focus();
                    if (validationError) {
                        validationError.classList.add('d-none');
                    }
                    searchInput.classList.remove('is-invalid');
                }
            });
        });
    }

    /**
     * Keyboard shortcut: '/' focuses the repository search bar.
     */
    function initKeyboardShortcuts() {
        var searchInput = document.getElementById('repoSearchInput');
        if (!searchInput) return;

        document.addEventListener('keydown', function (e) {
            if (e.key === '/' && document.activeElement !== searchInput) {
                // Avoid interfering with inputs in other sections
                var tag = (document.activeElement.tagName || '').toLowerCase();
                if (tag !== 'input' && tag !== 'textarea' && tag !== 'select') {
                    e.preventDefault();
                    searchInput.focus();
                    searchInput.select();
                }
            }
        });
    }

    /**
     * Safely initializes Bootstrap tooltips if bootstrap is loaded.
     */
    function initTooltips() {
        if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
            var tooltipElements = document.querySelectorAll('[data-bs-toggle="tooltip"]');
            tooltipElements.forEach(function (el) {
                try {
                    new bootstrap.Tooltip(el);
                } catch (err) {
                    // Suppress harmless tooltip initialization warnings
                }
            });
        }
    }
})();
