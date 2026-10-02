/**
 * OpenSourceLens Client Application Script
 * Provides client-side validation, loading animations, sample auto-filling, and UI enhancements.
 */

document.addEventListener('DOMContentLoaded', function () {
    const searchForm = document.getElementById('repoSearchForm');
    const searchInput = document.getElementById('repoSearchInput');
    const validationError = document.getElementById('clientValidationError');
    const loadingOverlay = document.getElementById('analysisLoadingOverlay');
    const loadingRepoName = document.getElementById('loadingRepoName');
    const sampleButtons = document.querySelectorAll('.sample-repo-btn');

    // Repo validation regex (owner/repo) or github.com/owner/repo
    const repoRegex = /^(?:https?:\/\/)?(?:www\.)?github\.com\/([a-zA-Z0-9_\-\.]+)\/([a-zA-Z0-9_\-\.]+)|\b([a-zA-Z0-9_\-\.]+)\/([a-zA-Z0-9_\-\.]+)\b$/;

    // Initialize Bootstrap tooltips if any
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Sample Repo Buttons click handler
    sampleButtons.forEach(button => {
        button.addEventListener('click', function () {
            const targetRepo = this.getAttribute('data-repo');
            if (searchInput) {
                searchInput.value = targetRepo;
                searchInput.focus();
                if (validationError) {
                    validationError.classList.add('d-none');
                }
            }
        });
    });

    // Keyboard shortcut: pressing '/' focuses repository search input
    document.addEventListener('keydown', function (e) {
        if (e.key === '/' && document.activeElement !== searchInput && searchInput) {
            e.preventDefault();
            searchInput.focus();
            searchInput.select();
        }
    });

    // Form submission & loading state orchestration
    if (searchForm && searchInput) {
        searchForm.addEventListener('submit', function (e) {
            const val = searchInput.value.trim();

            if (!val || !repoRegex.test(val)) {
                e.preventDefault();
                if (validationError) {
                    validationError.classList.remove('d-none');
                }
                searchInput.classList.add('is-invalid');
                searchInput.focus();
                return false;
            }

            // Valid input - clear error
            if (validationError) {
                validationError.classList.add('d-none');
            }
            searchInput.classList.remove('is-invalid');

            // Trigger loading state
            if (loadingOverlay) {
                if (loadingRepoName) {
                    loadingRepoName.innerText = val.replace(/https?:\/\/github\.com\//, '');
                }
                loadingOverlay.classList.remove('d-none');

                // Simulate realistic pipeline step progression for user feedback
                setTimeout(() => {
                    const step1 = document.getElementById('step-validate');
                    if (step1) {
                        step1.classList.add('text-success');
                        step1.querySelector('.os-step-icon').innerHTML = '<i class="bi bi-check-circle-fill text-success"></i>';
                    }
                    const step2 = document.getElementById('step-connect');
                    if (step2) {
                        step2.classList.remove('text-muted');
                        step2.classList.add('text-primary');
                        step2.querySelector('.os-step-icon').innerHTML = '<i class="bi bi-arrow-repeat spin text-primary"></i>';
                    }
                }, 600);

                setTimeout(() => {
                    const step2 = document.getElementById('step-connect');
                    if (step2) {
                        step2.querySelector('.os-step-icon').innerHTML = '<i class="bi bi-check-circle-fill text-success"></i>';
                    }
                    const step3 = document.getElementById('step-data');
                    if (step3) {
                        step3.classList.remove('text-muted');
                        step3.classList.add('text-primary');
                        step3.querySelector('.os-step-icon').innerHTML = '<i class="bi bi-arrow-repeat spin text-primary"></i>';
                    }
                }, 1300);

                setTimeout(() => {
                    const step3 = document.getElementById('step-data');
                    if (step3) {
                        step3.querySelector('.os-step-icon').innerHTML = '<i class="bi bi-check-circle-fill text-success"></i>';
                    }
                    const step4 = document.getElementById('step-analytics');
                    if (step4) {
                        step4.classList.remove('text-muted');
                        step4.classList.add('text-primary');
                        step4.querySelector('.os-step-icon').innerHTML = '<i class="bi bi-arrow-repeat spin text-primary"></i>';
                    }
                }, 2100);
            }
        });

        // Clear error on input typing
        searchInput.addEventListener('input', function () {
            if (validationError && !validationError.classList.contains('d-none')) {
                validationError.classList.add('d-none');
                searchInput.classList.remove('is-invalid');
            }
        });
    }
});
