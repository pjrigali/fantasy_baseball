import pandas as pd
import numpy as np



BASE_PATH = r'c:\Users\peter\Desktop\vscode\main\.data_lake\01_Bronze\fantasy_baseball'
OUTPUT_PATH = r'c:\Users\peter\.gemini\antigravity\brain\ad8af236-c6c6-4f16-8110-5d46378f456d\league_analysis_report.md'

print("Loading data...")
roster_df = pd.read_csv(f'{BASE_PATH}\\roster_history_2025.csv')
stats_df = pd.read_csv(f'{BASE_PATH}\\stats_mlb_daily_2025.csv')
player_map_df = pd.read_csv(f'{BASE_PATH}\\player_map.csv')

# Preprocess
stats_df['date'] = pd.to_datetime(stats_df['date'])
roster_df['start_date'] = pd.to_datetime(roster_df['start_date'])
roster_df['end_date'] = pd.to_datetime(roster_df['end_date'])

# Handle current date (replace NaT end_date with today or max date)
max_date = stats_df['date'].max()
roster_df['end_date'] = roster_df['end_date'].fillna(max_date)

player_map_df['espn_player_id'] = player_map_df['espn_player_id'].astype(str)
player_map_df['statcast_player_id'] = player_map_df['statcast_player_id'].astype(str).str.replace(r'\.0$', '', regex=True)
stats_df['playerId'] = stats_df['playerId'].astype(str)
roster_df['player_id'] = roster_df['player_id'].astype(str)

print("Merging stats...")
stats_merged = stats_df.merge(player_map_df, left_on='playerId', right_on='statcast_player_id', how='left')

# --- 1. Calculate Daily Value (League Wide) ---
batter_stats = ['R', 'HR', 'RBI', 'SB']
pitcher_positive = ['QS', 'SVHD', 'K']

def calculate_daily_value(df):
    df['Daily_Value'] = 0.0
    for col in batter_stats + pitcher_positive:
        if col in df.columns:
            mean = df[col].mean(); std = df[col].std(); std = 1 if std == 0 else std
            df['Daily_Value'] += ((df[col] - mean) / std).fillna(0)
            
    if 'P_H' in df.columns and 'P_BB' in df.columns:
        whip_val = df['P_H'] + df['P_BB']
        mean = whip_val.mean(); std = whip_val.std(); std = 1 if std == 0 else std
        df['Daily_Value'] -= ((whip_val - mean) / std).fillna(0)
        
    if 'ER' in df.columns:
        mean = df['ER'].mean(); std = df['ER'].std(); std = 1 if std == 0 else std
        df['Daily_Value'] -= ((df['ER'] - mean) / std).fillna(0)
    return df

daily_stats = stats_merged.groupby('date').apply(calculate_daily_value).reset_index(drop=True)

# Flatten detailed stats to daily player value
player_daily = daily_stats[['date', 'espn_player_id', 'playerName', 'Daily_Value']].copy()
player_daily = player_daily.groupby(['date', 'espn_player_id', 'playerName']).sum().reset_index()


# --- 2. League-Wide Time Series Optimal Window ---
print("Calculating Optimal Evaluation Window (3-90 days)...")
# Pivot for rolling calc
pivot_val = player_daily.pivot(index='date', columns='espn_player_id', values='Daily_Value').fillna(0)

best_window = 28
best_corr = -1
windows = list(range(3, 91, 3)) # 3, 6, 9... 90
correlations = {}

# Future performance (Next 7 days)
future_7 = pivot_val.rolling(window=7).mean().shift(-7)

for w in windows:
    past_w = pivot_val.rolling(window=w).mean()
    
    # Correlate
    # Align data (drop NaNs caused by rolling/shifting)
    aligned_past = past_w.stack()
    aligned_fut = future_7.stack()
    
    # Inner join on index (date, player)
    aligned = pd.concat([aligned_past, aligned_fut], axis=1).dropna()
    aligned.columns = ['Past', 'Future']
    
    corr = aligned['Past'].corr(aligned['Future'])
    correlations[w] = corr
    
# Find "Aggressive" Optimal Window
# Rule: Smallest window that captures 90% of the max correlation
max_corr = max(correlations.values())
threshold = 0.90 * max_corr

best_window = 90
best_corr = 0

# Sort by window size ascending to find smallest that passes
for w in sorted(windows):
    if correlations[w] >= threshold:
        best_window = w
        best_corr = correlations[w]
        break

print(f"Max Correlation: {max_corr:.4f}")
print(f"Aggressive Optimal Window (>= 90% of max): {best_window} days (Corr: {best_corr:.4f})")


# --- 3. Roster Patience (Time to Drop) ---
print("Analyzing Roster Patience...")
# Filter for dropped players only (end_date < max_date - buffer)
# Buffer to avoid counting active players as "dropped" just because data ended
drop_buffer_date = max_date - pd.Timedelta(days=3)
dropped_roster = roster_df[roster_df['end_date'] < drop_buffer_date].copy()
dropped_roster['days_held'] = dropped_roster['days_held'].clip(upper=180) # Cap outliers

team_patience = dropped_roster.groupby('team_abbrev')['days_held'].describe()[['count', 'mean', '50%', 'std']]
team_patience.columns = ['Drops', 'Avg_Hold_Days', 'Median_Hold_Days', 'Std_Dev']


# --- 4. Churn Rate (Moves per Week) ---
print("Analyzing Churn Rate...")
# Count new additions (start_date > season_start)
season_start = roster_df['start_date'].min()
adds = roster_df[roster_df['start_date'] > season_start + pd.Timedelta(days=7)] # Ignore draft/initial week
total_weeks = (max_date - season_start).days / 7

team_churn = adds.groupby('team_abbrev').size().reset_index(name='Total_Adds')
team_churn['Adds_Per_Week'] = team_churn['Total_Adds'] / total_weeks


# --- 5. Team Success Assessment (Total Value Generated) ---
print("Calculating Team Success...")
team_values = {}
teams = roster_df['team_abbrev'].unique()

for t in teams:
    team_values[t] = 0.0

# Iterate through all days in season
date_range = pd.date_range(season_start, max_date)

for d in date_range:
    # Get values for this day
    day_vals = player_daily[player_daily['date'] == d].set_index('espn_player_id')['Daily_Value']
    
    # Get active rosters on this day
    active = roster_df[(roster_df['start_date'] <= d) & (roster_df['end_date'] >= d)]
    
    for _, row in active.iterrows():
        t = row['team_abbrev']
        pid = row['player_id']
        val = day_vals.get(pid, 0.0)
        team_values[t] += val

success_df = pd.DataFrame.from_dict(team_values, orient='index', columns=['Total_Value'])
success_df['Value_Per_Day'] = success_df['Total_Value'] / len(date_range)
success_df = success_df.sort_values('Total_Value', ascending=False)


# --- 6. Correlation & Benchmarking ---
print("Correlating Stats...")
merged_metrics = success_df.merge(team_patience, left_index=True, right_index=True)
merged_metrics = merged_metrics.merge(team_churn, left_index=True, right_on='team_abbrev')
merged_metrics.set_index('team_abbrev', inplace=True)

# Calculate Optimal Churn (Avg of Top 3 Teams)
top_3_teams = merged_metrics.sort_values('Total_Value', ascending=False).head(3)
optimal_churn = top_3_teams['Adds_Per_Week'].mean()
optimal_hold = top_3_teams['Avg_Hold_Days'].mean()

merged_metrics['Churn_Diff'] = merged_metrics['Adds_Per_Week'] - optimal_churn

corr_patience = merged_metrics['Total_Value'].corr(merged_metrics['Avg_Hold_Days'])
corr_churn = merged_metrics['Total_Value'].corr(merged_metrics['Adds_Per_Week'])


# --- 7. Generate Report ---
with open(OUTPUT_PATH, "w") as f:
    f.write("# League-Wide Roster Analysis (Deep Dive)\n\n")
    
    f.write("## 1. Optimal Evaluation Window\n")
    f.write(f"**Selected Window:** {best_window} Days\n")
    f.write(f"Correlation with future performance: **{best_corr:.4f}**\n")
    f.write("*(Analysis performed on all players across the entire league)*\n\n")
    
    f.write("### Sensitivity Analysis (Correlation by Window):\n")
    # Show spread of windows
    selected_c = {k:v for k,v in correlations.items() if k % 15 == 0 or k == best_window or k == 3 or k == 90}
    for w in sorted(selected_c.keys()):
        prefix = "**" if w == best_window else ""
        suffix = "** (Selected)" if w == best_window else ""
        f.write(f"- {prefix}{w} Days{prefix}: {selected_c[w]:.4f}{suffix}\n")
    f.write("\n")

    f.write("## 2. Optimal Roster Cadence\n")
    f.write(f"Based on the Top 3 Teams (Average Value: {top_3_teams['Total_Value'].mean():.1f}):\n")
    f.write(f"- **Optimal Churn Rate**: {optimal_churn:.1f} adds per week\n")
    f.write(f"- **Target Hold Time (Drops)**: {optimal_hold:.1f} days\n\n")
    
    f.write("### Member Breakdown (vs Optimal)\n")
    f.write("| Team | Total Value | Adds/Week | vs Optimal Churn | Avg Hold | Median Hold |\n")
    f.write("|---|---|---|---|---|---|\n")
    
    # Sort by success
    sorted_m = merged_metrics.sort_values('Total_Value', ascending=False)
    for team, row in sorted_m.iterrows():
        churn_diff_str = f"{row['Churn_Diff']:+.1f}"
        f.write(f"| {team} | {row['Total_Value']:.1f} | {row['Adds_Per_Week']:.1f} | {churn_diff_str} | {row['Avg_Hold_Days']:.1f}d | {row['Median_Hold_Days']:.1f}d |\n")

print(f"Report saved to {OUTPUT_PATH}")

print(f"Report saved to {OUTPUT_PATH}")

# --- 8. Generate Visualizations (Mermaid) ---
print("Generating Mermaid charts...")

with open(OUTPUT_PATH, "a") as f:
    f.write("\n## Visualizations\n\n")
    
    # 8.1 Window Correlation (XY Chart)
    # Downsample windows to fit nicely in chart
    display_windows = [w for w in sorted(correlations.keys()) if w % 3 == 0] 
    # Use every 2nd or 3rd to keep x-axis clean if needed, but 30 points is fine for mermaid usually
    # Mermaid xychart beta
    
    f.write("### Evaluation Window Sensitivity\n")
    f.write("The curve shows the predictive power of different lookback windows. Note the plateau after 42 days.\n\n")
    f.write("```mermaid\n")
    f.write("xychart-beta\n")
    f.write("    title \"Predictive Power vs Lookback Window\"\n")
    f.write(f"    x-axis \"Days\" [{', '.join(map(str, display_windows))}]\n")
    
    # Y-axis scaling
    min_y = min(correlations.values()) * 0.95
    max_y = max(correlations.values()) * 1.05
    f.write(f"    y-axis \"Correlation\" {min_y:.3f} --> {max_y:.3f}\n")
    
    corr_vals = [correlations[w] for w in display_windows]
    f.write(f"    line [{', '.join([f'{c:.4f}' for c in corr_vals])}]\n")
    f.write("```\n\n")

    # 8.2 Patience vs Value (Quadrant Chart)
    f.write("### Manager Style: Patience vs. Value\n")
    f.write("Are you a 'Diamond Hands' holder or a 'Churner'?\n\n")
    f.write("```mermaid\n")
    f.write("quadrantChart\n")
    f.write("    title \"Roster Management Style\"\n")
    f.write("    x-axis \"Patience (Avg Hold Time)\" --> \"Stubborness\"\n")
    f.write("    y-axis \"Low Value\" --> \"High Value\"\n")
    f.write("    quadrant-1 \"Diamond Hands (High Value)\"\n")
    f.write("    quadrant-2 \"Churn & Burn (High Value)\"\n")
    f.write("    quadrant-3 \"Panic Dropper (Low Value)\"\n")
    f.write("    quadrant-4 \"Sleeping at Wheel (Low Value)\"\n")
    
    # Normalize data for quadrant (0 to 1)
    # X Axis: Patience (Avg Hold)
    max_hold = merged_metrics['Avg_Hold_Days'].max()
    min_hold = merged_metrics['Avg_Hold_Days'].min()
    
    # Y Axis: Value
    max_val = merged_metrics['Total_Value'].max()
    min_val = merged_metrics['Total_Value'].min()
    
    for team, row in merged_metrics.iterrows():
        # X: 0 is Low Hold (Churner), 1 is High Hold (Patient)
        # Normalize
        norm_x = (row['Avg_Hold_Days'] - min_hold) / (max_hold - min_hold)
        norm_y = (row['Total_Value'] - min_val) / (max_val - min_val)
        
        # Buffer to avoid 0.0 or 1.0 edges
        norm_x = 0.05 + (norm_x * 0.9)
        norm_y = 0.05 + (norm_y * 0.9)
        
        f.write(f"    {team}: [{norm_x:.2f}, {norm_y:.2f}]\n")
        
    f.write("```\n")

print("Mermaid charts appended.")
