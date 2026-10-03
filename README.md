# OpenSourceLens 🔍
### Open-Source Project Intelligence & Repository Health Analytics Platform

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.0+-092E20?style=flat&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-4169E1?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Pandas](https://img.shields.io/badge/Pandas-2.2+-150458?style=flat&logo=pandas&logoColor=white)](https://pandas.pydata.org/)
[![Chart.js](https://img.shields.io/badge/Chart.js-4.4-FF6384?style=flat&logo=chartdotjs&logoColor=white)](https://www.chartjs.org/)
[![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?style=flat&logo=bootstrap&logoColor=white)](https://getbootstrap.com/)
[![Tests](https://img.shields.io/badge/Tests-63%20Passed-success?style=flat&logo=pytest&logoColor=white)](#testing)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**OpenSourceLens** is a production-grade open-source project intelligence and health analytics platform built as part of the **Open Source Technologies (OST)** engineering curriculum. It transforms raw telemetry from the public GitHub REST API into actionable engineering metrics, evaluating repository activity, triage responsiveness, code integration, maintainer diversity, and hygiene through a transparent, reproducible, multi-signal methodology.

---

## Table of Contents

- [Problem Statement](#problem-statement)
- [Solution](#solution)
- [Features](#features)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [GitHub API Integration](#github-api-integration)
- [Database Schema](#database-schema)
- [Analytics Methodology](#analytics-methodology)
- [Health Score Formula](#health-score-formula)
- [Data Coverage](#data-coverage)
- [Installation](#installation)
- [Environment Variables](#environment-variables)
- [PostgreSQL Setup](#postgresql-setup)
- [Running the Project](#running-the-project)
- [Testing](#testing)
- [Collaborative Git Workflow](#collaborative-git-workflow)
- [Troubleshooting](#troubleshooting)
- [Screenshots](#screenshots)
- [API / Error Handling](#api--error-handling)
- [Security Considerations](#security-considerations)
- [OST Syllabus Mapping](#ost-syllabus-mapping)
- [Future Scope](#future-scope)
- [License](#license)


---

## Problem Statement

Evaluating open-source software libraries is a critical challenge for software engineering teams, academic researchers, and enterprise architects:

1. **Superficial Vanity Metrics:** GitHub stars, fork counts, and watcher counts do not reflect codebase maintainability, backlog responsiveness, or bus-factor risks.
2. **Opaque Black-Box Ratings:** Existing repository evaluation tools often output arbitrary scores without disclosing their underlying formula or data limits.
3. **Data Sampling Without Transparency:** Most tools analyze only a small recent sample of commits or issues while presenting the results as repository-wide truth.
4. **Maintenance Stagnation:** Projects frequently fall into unmaintained states despite high historical popularity, creating unseen security and supply-chain vulnerabilities.

---

## Solution

**OpenSourceLens** delivers an objective, mathematically grounded engineering dashboard that:
- Ingests public telemetry directly from the GitHub REST API using **reusable pagination**, **configurable time windows** (30d, 90d, 180d, 365d), and **strict HTTP timeouts**.
- Processes time-series dataframes using **Pandas** to calculate robust non-distorted statistics (such as median issue resolution times and commit velocity).
- Quantifies community maintainer concentration using the **Herfindahl-Hirschman Index ($HHI = \sum share_i^2$)**.
- Evaluates project sustainability through a deterministic, transparent **5-Pillar Health Score** (0–100) with clear driving factors.
- Provides complete **data coverage transparency** on every card and chart, explicitly stating sample limits and avoiding misleading generalizations.
- Persists historical snapshots in **PostgreSQL** inside atomic database transactions for longitudinal health trend tracking and objective side-by-side repository comparison.

---

## Features

| Category | Capability | Description |
| :--- | :--- | :--- |
| **Telemetry Ingestion** | **Paginated API Client** | Paginates through commits, issues, pull requests, and contributors up to safe configured ceilings. |
| **Configurable Scope** | **Time Windows** | Supports filtering analysis to 30 Days, 90 Days, 6 Months, or 1 Year with explicit cutoff timestamps. |
| **Caching & Sync** | **Smart Freshness Cache** | Reuses local database snapshots within 60-minute freshness window, with explicit user-triggered refresh option. |
| **Time-Series Velocity** | **Commit Analytics** | Daily, weekly, and monthly velocity charts, average commits/day, peak activity, and days since latest commit. |
| **Triage Health** | **Issue Analytics** | Sample resolution rate, median resolution days (resilient to outliers), stale backlog counter (>90d), and opened vs. closed trends. |
| **Turnaround Metrics** | **Pull Request Analytics** | Merge rate, median merge turnaround in hours/days, and state breakdown (merged, open, closed). |
| **Community Health** | **Contributor Concentration** | Top 1 and Top 5 contributor shares, full leaderboard, and Herfindahl-Hirschman Index ($HHI$) maintainer dependency indicator. |
| **Tech Composition** | **Language Breakdown** | Byte counts, normalized percentages summing cleanly to 100.0%, and interactive Donut distribution. |
| **Historical Auditing** | **Health Snapshot Timeline** | Stores immutable analytical snapshots over time; visualizes score progression over multiple runs. |
| **Multi-Repo Benchmarking**| **Comparative Analysis** | Side-by-side comparison matrix for 2 or 3 projects with objective comparative charts and neutral commentary. |
| **UX & Resilience** | **Developer Design System** | Clean Slate/Charcoal/Blue aesthetic, truthful multi-step loading indicators, and dedicated empty/error states. |

---

## Architecture

The system follows a strict, maintainable separation of concerns with thin controllers, a dedicated service orchestration layer, atomic persistence, and a decoupled statistical engine:

```text
                                  Browser
                                     │
                                     ▼
                            Django Views Layer
                     (home, analyze, history, compare)
                                     │
                                     ▼
                              AnalysisService
                     (caching, orchestration, transactions)
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
             GitHubService     AnalyticsEngine   RepositoryService
          (REST API Client,      (Pandas Math,    (History queries,
           Pagination, Retry)    Health Model)    Compare matrix)
                    │                │                │
                    └────────────────┼────────────────┘
                                     ▼
                            Persistence Layer
                          (PostgreSQL / SQLite)
               ┌─────────────────────┼─────────────────────┐
               ▼                     ▼                     ▼
          Repository          Child Entities      RepositoryAnalysis
      (Metadata, Topics,     (Languages, Issues,     (Immutable
       SPDX, Star counts)     PRs, Contributors)      Historical Snapshot)
                                     │
                                     ▼
                           Interactive UI Layer
                 (Chart.js, Bootstrap 5.3, Vanilla CSS)
```

---

## Technology Stack

- **Backend:** Python 3.11+, Django 5.0+ (MVT Architecture, CSRF, ORM Transactions)
- **Database:** PostgreSQL 16+ (Primary Production Storage via `psycopg` 3.x), SQLite (Development & Isolated Automated Testing)
- **Data Analytics:** Pandas 2.2+ (Vectorized datetime operations, quantile medians, grouping, distribution math)
- **External Integration:** GitHub REST API v3 (Session-managed HTTP requests, pagination, bearer token support)
- **Frontend / Presentation:** HTML5, Vanilla CSS Design System, Bootstrap 5.3 Grid, Bootstrap Icons 1.11+
- **Data Visualization:** Chart.js 4.4+ (Responsive line, bar, and doughnut charts with unified tooltip styling)
- **Quality Assurance:** Django Test Framework, Python `unittest.mock` (63 Unit and Integration Tests, zero external network dependency)

---

## Project Structure

```text
OpenSourceLens/
│
├── config/                          # Django project configuration
│   ├── settings.py                  # Database settings, logging, API timeouts, caching
│   ├── urls.py                      # Main URL routing configuration
│   ├── asgi.py                      # ASGI entrypoint
│   └── wsgi.py                      # WSGI production entrypoint
│
├── dashboard/                       # Core application
│   ├── analytics/
│   │   ├── __init__.py
│   │   └── analytics_engine.py      # Pandas data processing, statistics, HHI, 5 pillars
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── github_service.py        # GitHub REST client, pagination, error handling
│   │   ├── analysis_service.py      # Ingestion coordinator, cache verification, DB sync
│   │   └── repository_service.py    # History catalog, historical detail, comparison
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   └── formatting.py            # Metric and byte size formatters (1.2K, 3.4M, MB/GB)
│   │
│   ├── migrations/                  # Schema migrations
│   │   ├── 0001_initial.py
│   │   ├── 0002_pullrequest_closed_at_...py
│   │   └── 0003_repository_has_issues_...py
│   │
│   ├── models.py                    # Relational schema (Repository, Issue, PR, Analysis)
│   ├── forms.py                     # RepositorySearchForm and RepositoryCompareForm
│   ├── views.py                     # Thin request/response view controllers
│   ├── urls.py                      # Dashboard application route definitions
│   └── admin.py                     # Django Admin registration
│
├── templates/                       # Semantic HTML5 Templates
│   ├── base.html                    # Universal master shell, navbar, footer, Chart.js
│   ├── home.html                    # Search hero, scope selector, truthful loading steps
│   ├── dashboard.html               # Multi-level analytical dashboard with coverage banners
│   ├── history.html                 # Searchable, sortable repository history catalog
│   ├── history_detail.html          # Historical health audit log & progression timeline
│   ├── compare.html                 # Multi-repository comparative matrix & dual charts
│   ├── about.html                   # Methodology documentation, limits, OST syllabus mapping
│   └── errors/                      # Branded error pages
│       ├── 400.html                 # Bad Request error view
│       ├── 404.html                 # Resource Not Found error view
│       └── 500.html                 # Internal Server Error view
│
├── static/
│   ├── css/
│   │   └── style.css                # Polished developer-tool CSS design system
│   └── js/
│       └── app.js                   # Form validation, loading progress, keyboard navigation
│
├── tests/                           # Complete automated test suite (63 Tests)
│   ├── test_validation.py           # Input regex and repository format validation
│   ├── test_github_service.py       # Mocked GitHub API, pagination, rate-limit, timeout tests
│   ├── test_models.py               # Database constraints, foreign keys, cascade, transactions
│   ├── test_analytics.py            # Pandas computations, median resilience, HHI, health math
│   └── test_views.py                # View lifecycles, caching, configurable windows, edge cases
│
├── .env.example                     # Environment variable template
├── .gitignore                       # Git ignore rules (excludes .env, db.sqlite3, pycache)
├── manage.py                        # Django CLI entrypoint
├── requirements.txt                 # Pinned project dependencies
└── README.md                        # Platform engineering documentation
```

---

## GitHub API Integration

### Reusable Pagination Engine
The GitHub service implements an autonomous `_paginate()` method that iterates through GitHub API pages (`?page=X&per_page=Y`) until:
1. The requested limit is reached (e.g. 100 commits or issues).
2. The endpoint returns no more records or returns a page with fewer items than `per_page`.
3. An API error occurs or the safe internal ceiling (`max_pages=10`) is reached.

### Resilient Error Handling
All external requests to GitHub are bounded by a configurable timeout (`12s` default). The client maps HTTP statuses to typed domain exceptions:
- **HTTP 404:** `GitHubRepoNotFoundError` — Returns a helpful message instructing the user to verify repository visibility.
- **HTTP 401:** `GitHubAPIError` — Flags bad or expired `GITHUB_TOKEN` credentials.
- **HTTP 403 / 429:** `GitHubRateLimitExceededError` — Reads `x-ratelimit-reset` headers and outputs the exact UTC time when limits refresh.
- **HTTP 500 / 502 / 503:** `GitHubAPIError` — Handles transient upstream GitHub server outages gracefully.
- **Network Timeouts / Drops:** `GitHubTimeoutError` / `GitHubAPIError` — Informs user of network failure without exposing raw tracebacks.

### In-Memory and Relational Caching
To prevent redundant API queries, analyses are cached for 60 minutes (`ANALYSIS_CACHE_FRESHNESS_MINUTES`). When a user analyzes a repository, the platform checks if an analysis matching the selected time window already exists within the freshness threshold. Users can bypass the cache at any time using the **Refresh Analysis** action (`?refresh=true`).

---

## Database Schema

The database model separates current repository state from historical analysis snapshots:

```text
┌─────────────────────────────────┐
│           Repository            │
├─────────────────────────────────┤
│ id (PK)                         │
│ full_name (Unique, Indexed)     │
│ owner, name                     │
│ stars, forks, watchers          │
│ open_issues, default_branch     │
│ license, license_spdx           │
│ language, size, topics (JSON)   │
│ is_archived, is_fork            │
│ has_issues, has_wiki, has_pages │
│ created_at, updated_at, pushed_at│
│ fetched_at                      │
└───────────────┬─────────────────┘
                │ 1:N
        ┌───────┴───────┬────────────────┬────────────────┬───────────────┐
        ▼               ▼                ▼                ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌───────────────────┐
│   Language   │ │ Contributor  │ │CommitActivity│ │    Issue     │ │    PullRequest    │
├──────────────┤ ├──────────────┤ ├──────────────┤ ├──────────────┤ ├───────────────────┤
│ repository_id│ │ repository_id│ │ repository_id│ │ repository_id│ │ repository_id     │
│ language     │ │ username     │ │ date         │ │ issue_number │ │ pr_number         │
│ bytes        │ │ contributions│ │ commit_count │ │ title, state │ │ title, state      │
│ percentage   │ │ avatar_url   │ └──────────────┘ │ created_at   │ │ created_at        │
└──────────────┘ └──────────────┘                  │ closed_at    │ │ closed_at         │
                                                   └──────────────┘ │ merged_at         │
                                                                    └───────────────────┘
                                        │ 1:N
                                        ▼
                        ┌─────────────────────────────────┐
                        │       RepositoryAnalysis        │
                        ├─────────────────────────────────┤
                        │ id (PK)                         │
                        │ repository_id (FK)              │
                        │ health_score, health_tier       │
                        │ activity_score, issue_score     │
                        │ pr_score, contributor_score     │
                        │ maintenance_score               │
                        │ stars, forks, open_issues       │
                        │ commit_count, contributors_count│
                        │ prs_count                       │
                        │ issue_resolution_rate           │
                        │ pr_merge_rate                   │
                        │ analysis_window (30d/90d/etc)   │
                        │ data_coverage (JSON)            │
                        │ analyzed_at (Timestamp)         │
                        └─────────────────────────────────┘
```

### Constraints & Indexes
- Unique constraints prevent duplicate entries (`(repository, username)`, `(repository, issue_number)`, `(repository, pr_number)`, `(repository, date)`).
- Foreign keys use `on_delete=models.CASCADE` to ensure clean orphan removal when a repository is deleted.
- Analysis writes are wrapped in `transaction.atomic()` to guarantee that snapshots and child entity tables are committed consistently.

---

## Analytics Methodology

The analytics engine uses **Pandas** for all data normalization:

1. **Commit Analytics:**
   - Datetime parsing converts ISO timestamps into UTC time-series indices.
   - Computes daily activity frequency, 7-day rolling velocity, and days elapsed since latest commit.
2. **Issue Management:**
   - Resolves true issue tickets separately from pull requests.
   - Calculates **median resolution days** rather than average to prevent historical outlier tickets (e.g. issues open for 3 years) from distorting metrics.
   - Evaluates old unresolved backlog count (>90 days old).
3. **Pull Request Turnaround:**
   - Quantifies merge throughput: $\text{Merge Rate} = (\text{Merged PRs} / \text{Analyzed PRs}) \times 100$.
   - Computes median turnaround hours between PR creation and merge events.
4. **Contributor Concentration (Herfindahl-Hirschman Index):**
   - Measures community maintainer dependency using the economic HHI formula:
     $$\text{HHI} = \sum_{i=1}^{N} \left(\frac{\text{Contributions}_i}{\sum \text{Contributions}} \times 100\right)^2$$
   - Categorized objectively:
     - $\text{HHI} \le 1,500$: *Well-distributed maintainer base*
     - $1,500 < \text{HHI} \le 2,500$: *Moderate maintainer concentration*
     - $\text{HHI} > 2,500$: *High maintainer concentration*
5. **Language Composition:**
   - Normalizes raw byte counts into rounded percentages ensuring $\sum P_i = 100.0\%$.

---

## Health Score Formula

The OpenSourceLens **Health Score** is a composite metric (0–100) structured around five deterministic engineering pillars:

$$\text{Health Score} = 0.25 \times S_{\text{activity}} + 0.20 \times S_{\text{issue}} + 0.20 \times S_{\text{pr}} + 0.15 \times S_{\text{contributor}} + 0.20 \times S_{\text{maintenance}}$$

| Pillar | Weight | Signals Evaluated | Formula / Logic |
| :--- | :---: | :--- | :--- |
| **Activity** | **25%** | Commit recency, commit velocity, weekly frequency | - **Recency:** $\le 3\text{d} \to 95$, $\le 7\text{d} \to 90$, $\le 30\text{d} \to 80$, $>180\text{d} \to 30$<br>- **Velocity:** Scaled up to 100 based on average commits per active day. |
| **Issue Management** | **20%** | Sample resolution rate, median close days, backlog age | - **Resolution Rate:** Up to 50 pts.<br>- **Median Close Time:** $\le 3\text{d} \to 30\text{ pts}$, $\le 14\text{d} \to 20\text{ pts}$, $>60\text{d} \to 5\text{ pts}$.<br>- **Backlog:** Penalty applied for old open issues (>90d). |
| **PR Activity** | **20%** | Merge rate, merge turnaround speed, open volume | - **Merge Rate:** Scaled up to 60 pts.<br>- **Turnaround:** $\le 24\text{h} \to 40\text{ pts}$, $\le 7\text{d} \to 30\text{ pts}$, $>30\text{d} \to 10\text{ pts}$. |
| **Contributor Diversity** | **15%** | Contributor volume, maintainer concentration (HHI) | - **Base:** Evaluates recorded contributor count.<br>- **Concentration:** Low HHI ($<1500$) receives full marks; single-maintainer dominance ($>5000$) receives lower resilience scores. |
| **Maintenance & Hygiene** | **20%** | License presence, project description, archive status | - Valid OSI-compliant license detected (+35 pts).<br>- Clear repository description (+20 pts).<br>- Project topics defined (+15 pts).<br>- Active non-archived, non-forked status (+30 pts). |

### Score Categories
- **85–100:** *Excellent* — Highly active, structured triage, resilient community.
- **70–84:** *Good* — Consistent development with manageable issue backlogs.
- **50–69:** *Moderate* — Slower review turnaround or higher maintainer dependency.
- **0–49:** *At Risk* — Stagnant commit activity or lack of active maintenance.

> **Methodology Note:** These categories are analytical indicators defined by OpenSourceLens for comparative research and should not be interpreted as absolute software-quality verdicts.

---

## Data Coverage

To guarantee transparency, OpenSourceLens explicitly documents analysis scope on every dashboard view:

```text
┌────────────────────────────────────────────────────────────────────────┐
│  DATA COVERAGE TRANSPARENCY                                            │
│  Scope: Last 90 Days  │  Commits: 100 Analyzed  │  Issues: 84 Analyzed │
│  Pull Requests: 100 Analyzed  │  Contributors: Top 30 Recorded        │
└────────────────────────────────────────────────────────────────────────┘
```

- When telemetry is scarce (e.g. 0 commits in window or 0 issues open), the platform displays dedicated notice cards (e.g., *"Insufficient issue history for monthly comparison"*), preventing distorted charts.

---

## Installation

### Prerequisites
- Python 3.11 or newer
- PostgreSQL 14+ (or SQLite for development)
- Git

### 1. Clone Repository & Create Virtual Environment
```bash
git clone https://github.com/your-username/OpenSourceLens.git
cd OpenSourceLens
python -m venv venv

# Windows
.\venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## Environment Variables

Copy `.env.example` to create your local `.env`:

```bash
cp .env.example .env
```

Configure settings in `.env`:

```env
# Application Settings
DEBUG=True
SECRET_KEY=django-insecure-opensourcelens-production-grade-key-2026-secure
ALLOWED_HOSTS=127.0.0.1,localhost

# GitHub REST API Token (Optional: increases rate limit from 60 to 5,000 requests/hr)
GITHUB_TOKEN=

# Database Settings (PostgreSQL Primary)
DB_ENGINE=django.db.backends.postgresql
DB_NAME=opensourcelens
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_HOST=127.0.0.1
DB_PORT=5432

# SQLite Development Fallback (Set to True for offline/quick local dev)
USE_SQLITE=False

# Cache Freshness Threshold (Minutes)
ANALYSIS_CACHE_FRESHNESS_MINUTES=60

# GitHub Request Timeout (Seconds)
GITHUB_API_TIMEOUT=12
```

---

## PostgreSQL Setup

### 1. Create PostgreSQL Database
Using `psql` or pgAdmin:

```sql
CREATE DATABASE opensourcelens;
CREATE USER postgres WITH PASSWORD 'your_postgres_password';
GRANT ALL PRIVILEGES ON DATABASE opensourcelens TO postgres;
```

### 2. Run Database Migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

---

## Running the Project

Start the local development server:

```bash
python manage.py runserver
```

Open your browser to: **`http://127.0.0.1:8000/`**

### Available Routes:
- `/` — Homepage with search bar, configurable time windows, and quick-sample repositories.
- `/analyze/` — Deep repository intelligence dashboard.
- `/history/` — Searchable catalog of analyzed repositories with score changes.
- `/history/<owner>/<repo>/` — Historical health audit log & progression timeline.
- `/compare/` — Multi-repository side-by-side benchmarking.
- `/about/` — Complete methodology, limitations, and OST syllabus documentation.

---

## Testing

The project includes an automated test suite with **63 test cases** covering every layer of the system. Tests use Python's `unittest.mock` to mock external GitHub API calls and run against an isolated SQLite test database with zero external network or database dependencies.

Run the test suite:

```bash
python manage.py test
```

### Test Coverage Highlights:
- **`tests/test_validation.py` (7 tests):** Format validation for `owner/repo` formats, URLs, and edge-case syntax.
- **`tests/test_github_service.py` (12 tests):** Pagination pagination cycles, HTTP 404, HTTP 401, HTTP 403/429 rate limit reset parsing, HTTP 500 server errors, request timeouts, and malformed JSON.
- **`tests/test_models.py` (9 tests):** Database relationships, cascading deletes, unique constraints, and atomic transaction rollback.
- **`tests/test_analytics.py` (17 tests):** Pandas time-series grouping, outlier-resilient median close times, HHI concentration calculations, and zero-division edge cases.
- **`tests/test_views.py` (18 tests):** View lifecycles, caching verification, force refresh (`?refresh=true`), configurable window parameters (`30d`, `90d`, `180d`, `365d`), error redirects, and edge-case repositories (0 issues, 0 PRs, single contributor, archived, and forked repos).

```text
Found 63 test(s).
System check identified no issues (0 silenced).
...............................................................
----------------------------------------------------------------------
Ran 63 tests in 0.422s

OK
```


---

## Collaborative Git Workflow

OpenSourceLens is configured for structured, safe multi-developer collaboration between team members and student contributors.

### 1. Repository Setup & Clone
Each collaborator clones the central repository:

```bash
git clone https://github.com/kotechameet485-droid/OST-ASSIGMENT-.git
cd OST-ASSIGMENT-
```

Verify the configured remote:
```bash
git remote -v
# origin  https://github.com/kotechameet485-droid/OST-ASSIGMENT-.git (fetch)
# origin  https://github.com/kotechameet485-droid/OST-ASSIGMENT-.git (push)
```

### 2. Feature-Branch Collaboration Model
**Important Rule:** Developers must **never** commit directly to the `main` branch. All development takes place in isolated feature branches:

```text
main (Protected, stable production code)
 │
 ├── feature/api-improvements      (Developer 1)
 ├── feature/analytics-engine      (Developer 2)
 ├── feature/dashboard-redesign    (Developer 3)
 └── fix/timeout-handling          (Bugfix)
```

#### Step-by-Step Developer Flow:
1. **Sync Local `main` with Remote:**
   ```bash
   git checkout main
   git pull origin main
   ```
2. **Create a Dedicated Branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make Local Changes & Run Tests:**
   ```bash
   # Ensure all tests pass before committing
   python manage.py test
   ```
4. **Stage & Commit Changes:**
   ```bash
   git add .
   git commit -m "feat: implement descriptive feature title"
   ```
5. **Push Feature Branch to GitHub:**
   ```bash
   git push -u origin feature/your-feature-name
   ```
6. **Open a GitHub Pull Request (PR):**
   - Navigate to `https://github.com/kotechameet485-droid/OST-ASSIGMENT-`
   - Click **Compare & pull request**
   - Provide a clear summary of changes and verify that CI/tests pass
   - Request review from a teammate
7. **Merge & Clean Up:**
   - Once approved, merge into `main` via GitHub
   - Switch back to `main` locally and pull the fresh merge:
     ```bash
     git checkout main
     git pull origin main
     git branch -d feature/your-feature-name
     ```

### 3. Branch Naming Standard
Use structured, descriptive branch prefixes:
- `feature/...` — New analytical modules or functionality (e.g. `feature/github-pagination`, `feature/hhi-metric`)
- `fix/...` — Bug fixes or resilience patches (e.g. `fix/rate-limit-reset`, `fix/timeout-handling`)
- `refactor/...` — Architecture or code cleanup (e.g. `refactor/analysis-service`)
- `test/...` — Test suite expansions (e.g. `test/edge-case-repositories`)
- `ui/...` — Design, CSS, or template enhancements (e.g. `ui/dashboard-dark-accents`)
- `docs/...` — Documentation updates (e.g. `docs/setup-guide`)

### 4. Commit Message Standard
Follow Conventional Commits guidelines with clear, meaningful descriptions:
```text
feat: add reusable pagination engine to GitHubService
fix: handle GitHub API 403 rate limits with reset timestamp
refactor: extract analysis business logic into AnalysisService
test: add test coverage for 0-issue and 0-PR repositories
ui: polish health score 5-pillar driver breakdown cards
docs: document collaborative git workflow and troubleshooting
chore: update .gitignore rules for environment files
```
*Avoid vague messages such as "update", "changes", "fix bugs", "final", or "wip".*

### 5. Managing Collaborator Permissions (Repository Owner)
To allow teammates to push feature branches and collaborate on GitHub:
1. The repository owner opens `https://github.com/kotechameet485-droid/OST-ASSIGMENT-`
2. Navigate to **Settings** $\to$ **Collaborators** $\to$ **Add people**
3. Enter the teammate's GitHub username or email address and send the invite
4. The collaborator accepts the invite via email or notifications to receive repository write access

---

## Troubleshooting

### 1. Django Doesn't Start or Reports Migration Issues
Run Django's built-in system integrity verification:
```bash
python manage.py check
```
If the database needs updating, apply migrations:
```bash
python manage.py migrate
```

### 2. Port 8000 Is Already in Use (Port Conflict)
If another application or previous server process is listening on port 8000:
- **On Windows:**
  ```powershell
  netstat -ano | findstr :8000
  ```
- **Alternative:** Simply start Django on another port:
  ```bash
  python manage.py runserver 8001
  ```
  Then access OpenSourceLens at `http://127.0.0.1:8001/`.

### 3. GitHub Authentication in IDE (`Sign in failed: Error: No auth flow succeeded`)
If your IDE displays an authentication error banner, understand the critical difference between the three distinct authentication layers:
1. **IDE GitHub Extension Authentication:** An editor-level OAuth flow used for cloud settings sync and GitHub Copilot/extension features. This **does not** impact Git command-line operations or Django functionality.
2. **Git Command-Line Authentication:** Used by Git on your machine (`git push`, `git pull`). Git uses your OS Credential Manager or GitHub Personal Access Token.
3. **Django GitHub API Token (`GITHUB_TOKEN` in `.env`):** A server-side token used strictly by Python code to call the public GitHub REST API with a higher rate limit (5,000 requests/hr vs. 60/hr).

**Resolution Steps for IDE Authentication:**
- Git itself operates independently of the IDE extension. You can always run Git commands directly in the terminal:
  ```bash
  git config --global user.name "Your Name"
  git config --global user.email "your.email@example.com"
  ```
- If the GitHub CLI (`gh`) is installed on your system, authenticate safely:
  ```bash
  gh auth login
  # Choose: GitHub.com -> HTTPS -> Login with a web browser
  ```

### 4. Port Forwarding Messages (`Unable to forward localhost:8000` / `No forwarded ports`)
- **Local Development:** When developing locally on your own machine (Windows / macOS / Linux), port forwarding is **not required**. Django binds directly to your local loopback address:
  👉 Open **`http://127.0.0.1:8000/`** directly in your browser.
- **Remote / Cloud Environments:** If developing inside a remote container, Codespace, or SSH session, configure port forwarding in your IDE's Ports tab to forward port `8000` to your local machine.

---


## Screenshots

| View | Purpose |
| :--- | :--- |
| **Search & Discovery (`/`)** | Hero search with analysis window selector (30D, 90D, 6M, 1Y) and quick sample pills. |
| **Repository Header & Pillars (`/analyze/`)** | High-level metadata badges and 5-pillar health score breakdown with drivers. |
| **Time-Series Velocity (`/analyze/`)** | Interactive Chart.js commit activity graph with 30D / 90D / 6M / 1Y range toggles. |
| **Triage & Turnaround (`/analyze/`)** | Side-by-side cards for Issue Management and Pull Request status distribution. |
| **Community & Concentration (`/analyze/`)** | Contributor leaderboard with avatar icons, contribution counts, and HHI rating. |
| **Technology Breakdown (`/analyze/`)** | Normalized language composition with Doughnut chart and byte table. |
| **Repository Comparison (`/compare/`)** | Objective side-by-side comparative matrix and comparative bar charts. |
| **Historical Audit Log (`/history/`)** | Searchable audit trail showing health score changes over time. |

---

## API / Error Handling

The application provides graceful, user-friendly error experiences without raw stack trace leaks:

- **Repository Not Found (404):** Redirects to home with an informative notification: *"Repository 'owner/repo' was not found on GitHub. Please verify the name and ensure it is public."*
- **Rate Limit Exceeded (403/429):** Calculates and displays the exact time of limit reset: *"GitHub API rate limit reached. Rate limit resets at 14:30:00 UTC. Please configure a GITHUB_TOKEN."*
- **Network Timeout:** Returns: *"GitHub request timed out. Please try again."*
- **Custom HTTP Error Pages:** Dedicated templates for `400.html` (Bad Request), `404.html` (Page Not Found), and `500.html` (Server Error) maintaining consistent branding and clear navigation.

---

## Security Considerations

- **Secrets Management:** Sensitive configuration (`SECRET_KEY`, `GITHUB_TOKEN`, database passwords) is isolated in `.env` files and excluded from Git version control via `.gitignore`.
- **Server-Side Token Isolation:** GitHub tokens are never passed to templates or exposed to browser JavaScript.
- **CSRF & XSS Protection:** Django's CSRF middleware is enforced on all state-altering requests. JSON chart payloads are serialized safely with template escaping.
- **SQL Injection Defense:** All database queries utilize Django ORM parameterized queries with `select_related()` and `prefetch_related()`.
- **Database Transactions:** Analysis persistence is protected by `transaction.atomic()` to prevent partially saved or corrupted records.

---

## OST Syllabus Mapping

This project directly demonstrates core principles of the **Open Source Technologies (OST)** academic curriculum:

| OST Syllabus Topic | OpenSourceLens Implementation | Academic Concept Demonstrated |
| :--- | :--- | :--- |
| **1. Git & Version Control** | Git commits, branch workflows, and clean commit history. | Distributed version control, patch tracking, and source control hygiene. |
| **2. GitHub Ecosystem** | Ingestion of public repositories via GitHub REST API v3. | Open-source ecosystem collaboration, public issue tracking, and PR review workflows. |
| **3. Backend Web Framework** | Django 5.0+ Model-View-Template (MVT) architecture. | URL routing, thin controllers, service layer decoupling, and forms validation. |
| **4. Relational Database** | PostgreSQL 16 schema with foreign keys, indexes, and transactions. | ACID transactions, database normalization, relational integrity, and query optimization. |
| **5. Data Science & Analytics** | Pandas dataframes, datetime arithmetic, and quantile medians. | Exploratory data analysis, statistical aggregation, and outlier mitigation. |
| **6. Frontend & Responsive UI** | Bootstrap 5.3, semantic HTML5, and accessible Vanilla CSS design system. | Responsive design, modern developer tool aesthetics, and UI component hierarchies. |
| **7. Interactive Visualization** | Chart.js 4.4 Canvas rendering with dynamic range filtering. | Visual communication of time-series data, distributions, and comparative metrics. |
| **8. CRUD & Data Lifecycle** | Repository history catalog, detail inspection, and snapshot updates. | Create, Read, Update, and Delete operations with atomic persistence. |
| **9. Automated Quality Assurance** | 63 automated tests using `unittest` and `unittest.mock`. | Unit testing, integration testing, edge-case coverage, and mocking external services. |
| **10. Open Source Licensing** | SPDX license detection, project documentation check, and MIT License. | Open-source governance, copyleft vs. permissive licensing, and project sustainability. |

---

## Future Scope

1. **GitHub GraphQL API Integration:** Reducing round-trip network requests for deep issue/PR thread analysis.
2. **CI/CD Pipeline Telemetry:** Inspecting GitHub Actions workflow success rates and average test execution times.
3. **Automated Weekly Email Reports:** Subscribing to tracked repositories for automated maintainability alerts.
4. **Dependencies & Vulnerability Scanning:** Correlating repository dependencies with open CVE databases.

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details. Built for educational and analytical purposes as part of the Open Source Technologies (OST) curriculum.
