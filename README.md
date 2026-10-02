# OpenSourceLens 🔍
### Open-Source Project Intelligence & Advanced Health Analytics Platform

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.1-092E20?style=flat&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-4169E1?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Pandas](https://img.shields.io/badge/Pandas-2.2+-150458?style=flat&logo=pandas&logoColor=white)](https://pandas.pydata.org/)
[![Chart.js](https://img.shields.io/badge/Chart.js-4.4-FF6384?style=flat&logo=chartdotjs&logoColor=white)](https://www.chartjs.org/)
[![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?style=flat&logo=bootstrap&logoColor=white)](https://getbootstrap.com/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

OpenSourceLens is an open-source project intelligence and health analytics platform built as part of the **Open Source Technologies (OST)** coursework. It enables developers, engineering managers, students, and open-source contributors to evaluate any public GitHub repository, transform raw telemetry into actionable metrics, and assess sustainability and maintainability through a transparent, reproducible health score.

---

## 📑 Table of Contents

- [Stage 2 Architecture](#-stage-2-architecture)
- [Stage 2 Features Overview](#-stage-2-features-overview)
- [Analytical Modules & Mathematical Formulations](#-analytical-modules--mathematical-formulations)
  - [1. Commit Analytics & Time-Series Velocity](#1-commit-analytics--time-series-velocity)
  - [2. Issue Analytics & Backlog Resolution](#2-issue-analytics--backlog-resolution)
  - [3. Pull Request Analytics & Turnaround](#3-pull-request-analytics--turnaround)
  - [4. Contributor Distribution & Concentration](#4-contributor-distribution--concentration)
  - [5. Technology & Language Analytics](#5-technology--language-analytics)
- [Refined 5-Pillar Health Score Methodology](#-refined-5-pillar-health-score-methodology)
- [Repository Comparison Module (/compare/)](#-repository-comparison-module-compare)
- [Repository History & Historical Health Timeline](#-repository-history--historical-health-timeline)
- [Directory Structure](#-directory-structure)
- [Quick Start Guide](#-quick-start-guide)
- [Database Configuration & PostgreSQL Setup](#-database-configuration--postgresql-setup)
- [Running Automated Tests (37 Tests)](#-running-automated-tests-37-tests)
- [OST Academic Alignment & Viva Guide](#-ost-academic-alignment--viva-guide)

---

## 🏛 Stage 2 Architecture

The platform processes raw GitHub REST telemetry into time-series dataframes, executes statistical transformations using **Pandas**, stores normalized snapshots in **PostgreSQL**, and renders interactive **Chart.js** canvases within a clean developer design system:

```text
                         OpenSourceLens
                               │
                ┌──────────────┴──────────────┐
                ↓                             ↓
        Repository Analysis             Repository History
                │                             │
                ↓                             ↓
           GitHub API                  Historical Analyses
                │                             │
                └──────────────┬──────────────┘
                               ↓
                       Analytics Engine (Pandas)
                               │
              ┌────────────────┼────────────────┐
              ↓                ↓                ↓
           Commits           Issues             PRs
              ↓                ↓                ↓
           Trends          Resolution        Merge Rate
              │                │                │
              └────────────────┼────────────────┘
                               ↓
                         Contributors
                               ↓
                       Health Metrics (5 Pillars)
                               ↓
                    Interactive Dashboard
                               ↓
                  History + Comparison (/compare/)
```

---

## 🌟 Stage 2 Features Overview

1. **Commit Analytics & Time-Series Velocity:**
   - 30-Day daily commit frequency, 90-day weekly distribution, and 6-month monthly trends.
   - Calculates average commits/day, single-day maximums, and days since latest commit.
2. **Issue Analytics & Resolution Rates:**
   - Evaluates active triage health: `Resolution Rate = (Closed / Total Analyzed) × 100`.
   - Computes average resolution time in days and flags stale issues (>90 days old).
   - Monthly opened vs closed comparison bar chart.
3. **Pull Request Turnaround & Merge Velocities:**
   - Calculates `Merge Rate = (Merged PRs / Total PRs Analyzed) × 100`.
   - Computes average turnaround duration in hours/days.
   - Doughnut visualization of merged, open, and closed (unmerged) pull requests.
4. **Contributor Leaderboard & Maintainer Distribution:**
   - Contributor leaderboard with contribution volume, avatar, and percentage share.
   - Analyzes concentration risk (Top 1 and Top 5 contributor shares) as an analytical indicator.
5. **Enhanced Language Analysis:**
   - Primary language detection, byte formatting, and percentage breakdown.
   - Responsive multi-colored Doughnut chart and detail table.
6. **Multi-Repository Comparison (`/compare/`):**
   - Side-by-side comparison matrix for 2 or 3 public GitHub repositories.
   - Comparative bar charts for stars, forks, and health scores.
   - Strictly objective comparison—no biased "winner" or "best" labels.
7. **Historical Health Progression (`/history/` and `/history/<owner>/<repo>/`):**
   - Searchable, sortable catalog of analyzed repositories.
   - Historical health score timeline for repositories evaluated over time.

---

## 📐 Analytical Modules & Mathematical Formulations

### 1. Commit Analytics & Time-Series Velocity
Aggregates commits into daily, weekly, and monthly buckets using Pandas:
- **Average Commits per Active Day:**
  $$\text{Avg Commits/Day} = \frac{\sum_{i=1}^{N} \text{Commits}_i}{\text{Active Days}}$$
- **Recency Penalty/Bonus:** Calculated from `days_since_latest_commit`:
  - $\le 3\text{ days}$: Top score (98/100)
  - $\le 14\text{ days}$: Healthy (90/100)
  - $\le 45\text{ days}$: Moderate (78/100)
  - $> 180\text{ days}$: Stagnant penalty (30/100)

### 2. Issue Analytics & Backlog Resolution
- **Resolution Rate:**
  $$\text{Resolution Rate} = \left(\frac{\text{Closed Issues}}{\text{Total Issues Analyzed}}\right) \times 100$$
- **Average Resolution Time:**
  $$\text{Avg Duration} = \frac{1}{K}\sum_{j=1}^{K} (\text{closed\_at}_j - \text{created\_at}_j)$$
- **Old Unresolved Issues:**
  $$\text{Count}(\text{created\_at} < \text{Now} - 90\text{ days } \land \text{state} = \text{'open'})$$

### 3. Pull Request Analytics & Turnaround
- **PR Merge Rate:**
  $$\text{Merge Rate} = \left(\frac{\text{Merged PRs}}{\text{Total PRs Analyzed}}\right) \times 100$$
- **Turnaround Velocity:** Calculated as mean duration between PR creation and merge event:
  $$\text{Turnaround} = \frac{1}{M}\sum_{m=1}^{M} (\text{merged\_at}_m - \text{created\_at}_m)$$

### 4. Contributor Distribution & Concentration
- **Top 1 Share:**
  $$\text{Top 1 Share} = \left(\frac{\text{Contributions}_{\text{top 1}}}{\sum \text{Contributions}}\right) \times 100$$
- **Top 5 Share:**
  $$\text{Top 5 Share} = \left(\frac{\sum_{i=1}^{5}\text{Contributions}_i}{\sum \text{Contributions}}\right) \times 100$$

---

## ⚖ Refined 5-Pillar Health Score Methodology

The overall health score (0–100) is deterministically weighted across 5 observable signals:

| Pillar | Weight | Telemetry Input | Normalization Rationale |
| :--- | :---: | :--- | :--- |
| **Activity** | **25%** | Days since latest commit, commit frequency | Measures active codebase stewardship. Pushes within 3 days receive 98/100. |
| **Issue Management** | **20%** | Resolution rate, backlog age (>90d) | Evaluates maintainer responsiveness to bug reports and community feedback. |
| **PR Activity** | **20%** | PR merge rate, merge turnaround velocity | Measures review velocity and integration of external contributions. |
| **Contributor Diversity** | **15%** | Contributor count, Top 1 maintainer share | Evaluates community depth and resilience to single-maintainer burnout. |
| **Maintenance & Hygiene** | **20%** | Open-source license, description, archive state | Confirms legal clarity, documentation purpose, and active repository status. |

### Scoring Formula:
$$\text{Health Score} = \text{round}\Big(0.25 \times S_{\text{act}} + 0.20 \times S_{\text{iss}} + 0.20 \times S_{\text{pr}} + 0.15 \times S_{\text{div}} + 0.20 \times S_{\text{maint}}\Big)$$

---

## ⚔ Repository Comparison Module (`/compare/`)

Access `/compare/` to benchmark public repositories side-by-side:
- Compare 2 or 3 projects simultaneously (e.g. `facebook/react` vs `vuejs/core` vs `angular/angular`).
- Objective side-by-side metric matrix: Stars, Forks, Open Issues, Health Score, Component Pillar Scores, Primary Language, and License.
- Visual comparative bar charts for direct visual comparison.
- Strict adherence to objective metric presentation: NO biased "winner", "loser", or "#1" language.

---

## 📈 Repository History & Historical Health Timeline

- **Catalog (`/history/`):** Full audit of previously analyzed repositories with search filtering and sorting (recently analyzed, health score, star count, alphabetical).
- **Historical Timeline (`/history/<owner>/<repo>/`):** Evaluates score progression across multiple evaluation runs over time with Chart.js time-series plots.

---

## 📂 Directory Structure

```text
OpenSourceLens/
├── config/                     # Django project configuration
│   ├── settings.py             # Settings, PostgreSQL connection, resilient fallback
│   ├── urls.py                 # Root URL router
│   ├── asgi.py
│   └── wsgi.py
├── dashboard/                  # Core analytics application
│   ├── analytics/
│   │   ├── __init__.py
│   │   └── analytics_engine.py # Pandas processing, commit/issue/PR/health math
│   ├── services/
│   │   ├── __init__.py
│   │   └── github_service.py   # GitHub REST API client (commits, issues, PRs)
│   ├── migrations/             # Database migrations
│   │   ├── 0001_initial.py
│   │   └── 0002_pullrequest_closed_at_pullrequest_title_and_more.py
│   ├── models.py               # Repository, Contributor, CommitActivity, Issue, PR, RepositoryAnalysis
│   ├── views.py                # Views for Home, Analyze, History, Detail, Compare, About
│   ├── forms.py                # Search and Comparison form validation
│   ├── urls.py                 # Application URL endpoints
│   └── admin.py                # Django admin registration
├── static/
│   ├── css/style.css           # Developer analytics design system
│   └── js/app.js               # Validation, multi-step loading overlay, shortcuts
├── templates/
│   ├── base.html               # Shared navbar, Chart.js 4.4, footer
│   ├── home.html               # Search hero and quick-select pills
│   ├── dashboard.html          # Interactive multi-level analytics dashboard
│   ├── history.html            # Searchable repository catalog
│   ├── history_detail.html     # Historical audit log and health timeline
│   ├── compare.html            # Multi-repository comparative matrix & charts
│   ├── about.html              # System architecture and methodology docs
│   └── errors/                 # Error templates (400, 404, 500)
├── tests/                      # Automated test suite (37 tests)
│   ├── test_validation.py      # Input format & regex tests
│   ├── test_github_service.py  # Mocked API client tests
│   ├── test_models.py          # ORM relationships & cascade checks
│   ├── test_analytics.py       # Pandas data processing & scoring tests
│   └── test_views.py           # View integration & comparison tests
├── .env                        # Environment secrets (ignored by Git)
├── .gitignore                  # Git ignore rules
├── manage.py                   # Django management CLI
└── README.md                   # Project documentation
```

---

## 🚀 Quick Start Guide

### 1. Set Up Environment & Install Dependencies
```bash
cd d:\sem5\OST\assi
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
```env
DEBUG=True
SECRET_KEY=django-insecure-opensourcelens-ost-project-key-2026-super-secure
ALLOWED_HOSTS=127.0.0.1,localhost

# GitHub Personal Access Token (Optional: increases API limit to 5,000/hr)
GITHUB_TOKEN=

# Database Configuration (PostgreSQL)
DB_ENGINE=django.db.backends.postgresql
DB_NAME=opensourcelens
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_HOST=127.0.0.1
DB_PORT=5432
```

### 3. Run Migrations & Start Server
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
```

Open: **`http://127.0.0.1:8000/`**

---

## 🧪 Running Automated Tests (37 Tests)

Run the full automated test suite:

```bash
python manage.py test tests
```

Output:
```text
Found 37 test(s).
System check identified no issues (0 silenced).
.....................................
----------------------------------------------------------------------
Ran 37 tests in 0.135s

OK
```

---

## 🎓 OST Academic Alignment & Viva Guide

### Frequently Asked Viva Questions:
1. **Why Django for the backend?**
   - Provides a clean Model-View-Template (MVT) architecture, built-in ORM with SQL transaction management, form validation, and robust security against CSRF/XSS.
2. **Why PostgreSQL?**
   - Real-world relational database storing complex relations: Repositories $\to$ Languages, Contributors, Issues, Pull Requests, Commit Activities, and Analysis snapshots.
3. **Why Pandas?**
   - Ideal for vectorized time-series aggregation, datetime arithmetic (turnaround duration), grouping, and percentage distributions without raw SQL loops.
4. **Why not judge projects as "Best" or "Winner"?**
   - OpenSourceLens provides objective engineering telemetry. Metrics like high contributor concentration or low merge rate indicate community dynamics rather than moral judgments.
5. **How are GitHub API limits respected?**
   - Service inspects `x-ratelimit-remaining` headers, handles 403s with user-friendly notices, and supports optional Bearer token authentication for 5,000 requests/hour.
