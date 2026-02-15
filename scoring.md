# Fantasy Baseball League Scoring System (2025)

## Overview
- **League Type**: Head-to-Head Each Category
- **Matchup Format**: 5x5 Categories
- **Tie Breaker**: Standard

## Scoring Categories

### Batting (5 Categories)
*   **Runs (R)**: Total runs scored.
*   **Home Runs (HR)**: Total home runs hit.
*   **Runs Batted In (RBI)**: Total runs batted in.
*   **Stolen Bases (SB)**: Total bases stolen.
*   **On-Base Plus Slugging (OPS)**: (OBP + SLG).

### Pitching (5 Categories)
*   **Strikeouts per 9 Innings (K/9)**: (K * 9) / IP.
*   **Quality Starts (QS)**: Starts lasting at least 6 innings with 3 or fewer earned runs allowed.
*   **Saves + Holds (SVHD)**: Total saves plus total holds.
*   **Earned Run Average (ERA)**: (Earned Runs * 9) / IP. (Lower is better)
*   **Walks plus Hits per Innings Pitched (WHIP)**: (BB + H) / IP. (Lower is better)

## Note on Data Collection
The `daily_player_stats_2025.csv` file contains a `points` column which is `0.0`. This is expected behavior for a Categories league, as players accumulate stats directly rather than fantasy points.
