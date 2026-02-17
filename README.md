# Fantasy Baseball Data Processing

This project consolidates various data collection, analysis tools, and reporting scripts for ensuring domination in the fantasy baseball league.

## File Overview

### Core Module
*   **`mlb_processing.py`**: The central library containing shared logic for data fetching, processing, and league configuration. Used by almost all other scripts.

### Analysis & Reporting
*   **`generate_roster_recommendations.py`**:  Evaluates current roster vs. free agents to suggest optimal add/drops based on sliding performance windows.
*   **`analyze_draft_strategy.py`**: Retrospective analysis of the draft, identifying value picks ("steals") and early-round "busts" by comparing draft position to actual season value.
*   **`analyze_impact_categories.py`**: Calculates "Impact Values" (Z-scores) for every player to determine who actually contributed to winning categories.
*   **`analyze_keepers.py`**: Evaluates potential keeper selections for the upcoming season.
*   **`analyze_league_rosters.py`**: Break down of roster construction and management styles across the entire league.
*   **`run_ts_analysis.py`**: Performs time-series analysis to determine optimal "lookback windows" for predicting future performance.

### Data Collection (ETL)
*   **`fetch_stats_mlb_daily.py`**: Fetches detailed daily game logs from the official MLB API.
*   **`fetch_stats_espn_daily.py`**: Fetches daily player stats from ESPN.
*   **`fetch_draft_espn_season.py`**: Retrieves draft results for a specific season.
*   **`fetch_rosters_espn_current.py`**: Snapshots the currently active rosters for all teams.
*   **`fetch_transactions_espn_season.py`**: Downloads the full transaction log (adds, drops, trades) for the season.
*   **`fetch_scoreboard_espn_matchup.py`**: Retrieves weekly matchup scores and results.
*   **`fetch_stats_mlb_scrape.py`**: Scraper for bulk historical MLB data.

### Data Processing & Dashboards
*   **`process_dashboard_data.py`**: The engine behind the **Fantasy Baseball Dashboard**. Collects daily snapshots, detects trends, and generates the HTML report published to the website.
*   **`create_roster_history.py`**: Reconstructs daily roster states from transaction logs to allow for "who was on my team on this day" analysis.
*   **`process_stats_espn_matchup.py`**: Aggregates raw stats into matchup-level data.
*   **`generate_schedule_espn_matchup.py`**: Generates the league schedule for analysis.

### Jupyter Notebooks
*   **`analyze_roster_churn.ipynb`**: Deep dive into roster turnover rates and the "Optimal Evaluation Window" logic.
*   **`draft_strategy_2026.ipynb`**: Workspace for planning the 2026 draft strategy.

## Setup & Configuration

1.  **Dependencies**:
    ```bash
    pip install requests beautifulsoup4 numpy pandas statsmodels seaborn espn_api
    ```
2.  **Configuration**: Ensure `config.ini` is present in the root with ESPN credentials.

## Data Storage
Data is stored in the **Data Lake**: `main/.data_lake/01_bronze/fantasy_baseball`

