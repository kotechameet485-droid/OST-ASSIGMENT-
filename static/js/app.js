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

        searchForm.addEventListener('submit', function (e) {
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

            // Input is valid: clear errors
            if (validationError) {
                validationError.classList.add('d-none');
            }
            searchInput.classList.remove('is-invalid');

            // Trigger truthful pipeline step progression
            if (loadingOverlay) {
                var cleanName = rawValue.replace(/^https?:\/\/github\.com\//, '');
                if (loadingRepoName) {
                    loadingRepoName.textContent = cleanName;
                }
                loadingOverlay.classList.remove('d-none');

                orchestrateLoadingSteps();
            }
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
     * Advances multi-step pipeline animation to reflect real backend work phases.
     */
    function orchestrateLoadingSteps() {
        var steps = [
            { id: 'step-connect', delay: 400 },
            { id: 'step-meta', delay: 1000 },
            { id: 'step-commits', delay: 1700 },
            { id: 'step-issues', delay: 2400 },
            { id: 'step-analytics', delay: 3100 },
            { id: 'step-save', delay: 3700 }
        ];

        steps.forEach(function (s) {
            setTimeout(function () {
                var el = document.getElementById(s.id);
                if (!el) return;

                // Mark previous active elements complete
                var prev = el.previousElementSibling;
                if (prev) {
                    prev.classList.remove('text-primary');
                    prev.classList.add('text-success');
                    var prevIcon = prev.querySelector('.os-step-icon');
                    if (prevIcon) {
                        prevIcon.innerHTML = '<i class="bi bi-check-circle-fill text-success"></i>';
                    }
                }

                // Activate current element
                el.classList.remove('text-muted');
                el.classList.add('text-primary');
                var icon = el.querySelector('.os-step-icon');
                if (icon) {
                    icon.innerHTML = '<i class="bi bi-arrow-repeat spin text-primary"></i>';
                }
            }, s.delay);
        });
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
