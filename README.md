# Fantasy Baseball Data Processing

This project consolidates various data collection and analysis tools for fantasy baseball, originally distributed across multiple Jupyter notebooks, into a unified Python module `mlb_processing.py`.

## Features

The `mlb_processing.py` module provides functionalities for:

### Data Collection
-   **MLB Schedule**: Scrapes official MLB schedules for specific date ranges.
-   **ESPN Integration**: Fetches player game logs (batters and pitchers), daily lineups, league rosters, team metadata, and transaction logs.
-   **Historical Data**: Scrapes historical MLB player statistics from ESPN.
-   **Rotowire Lineups**: Scrapes daily projected lineups from Rotowire.

### Analysis
-   **Batter Consistency**: Calculates "Consistency Ratios" for players based on their contribution frequency (R, RBI, SB, HR).
-   **Team Aggregates**: Computes weekly and daily team performance averages across key statistics.
-   **Pitcher Regression**: Performs OLS regression analysis on pitcher performance (ERA vs K/BB ratio).
-   **Matchup Analysis**: Visualizes correlations between different player statistics.

## Setup

1.  **Dependencies**: Ensure the following Python libraries are installed:
    ```bash
    pip install requests beautifulsoup4 numpy pandas statsmodels seaborn espn_api
    ```
2.  **Configuration**: A `config.ini` file is required in the root directory (or parent directories) with your ESPN API credentials:
    ```ini
    [BASEBALL]
    BB_LEAGUE_ID = <Your League ID>
    BB_SWID = <Your SWID>
    BB_ESPN_2 = <Your ESPN_S2>
    ```

## Usage

Import the module in your scripts or notebooks:

```python
import fantasy_baseball.mlb_processing as mp

# 1. Load Configuration
config = mp.load_config()

# 2. Initialize League
league = mp.setup_league(config, year=2025)

# 3. Fetch Data
rosters = mp.get_league_rosters(league)
print(f"Loaded {len(rosters)} players.")

# 4. Analyze Batter Consistency
consistency, avg = mp.analyze_roster_batters(league, team_id=2)

# 5. Access Data Lake
print(f"Data stored at: {mp.DATA_PATH}") 
```

## Data Storage

Data is stored in a centralized data lake:
-   **Location**: `main/.data_lake/01_bronze/fantasy_baseball`
-   The module accesses this path via the `DATA_PATH` constant.

## File Structure

-   `mlb_processing.py`: Core logic module.
-   `functions.py`: Helper utility functions.
-   `universal.py`: Universal constants and mappings.
-   `archive/`: Deprecated Jupyter notebooks and summaries.
