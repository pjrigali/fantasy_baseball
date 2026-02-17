import pandas as pd
import numpy as np

BASE_PATH = r'c:\Users\peter\Desktop\vscode\main\.data_lake\01_Bronze\fantasy_baseball'
OUTPUT_PATH = r'c:\Users\peter\.gemini\antigravity\brain\ad8af236-c6c6-4f16-8110-5d46378f456d\roster_analysis_report.md'
WINDOW = 28
TEAM_ABBREV = 'PJR'

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

print("Merging data...")
stats_merged = stats_df.merge(player_map_df, left_on='playerId', right_on='statcast_player_id', how='left')

# Value Calculation
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

# Rolling Value
print(f"Calculating {WINDOW}-day rolling value...")
player_daily = daily_stats[['date', 'espn_player_id', 'playerName', 'Daily_Value']].copy()
# Aggregate multi-game days
player_daily = player_daily.groupby(['date', 'espn_player_id', 'playerName']).sum().reset_index()

# Pivot for rolling calc
pivot_val = player_daily.pivot(index='date', columns='espn_player_id', values='Daily_Value').fillna(0)
rolling_val = pivot_val.rolling(window=WINDOW).mean()

# Unstack back to long format
rolling_long = rolling_val.stack().reset_index()
rolling_long.columns = ['date', 'player_id', 'Rolling_Value']

# Add Player Names back
name_map = player_daily[['espn_player_id', 'playerName']].drop_duplicates()
rolling_long = rolling_long.merge(name_map, left_on='player_id', right_on='espn_player_id', how='left')

# Analyze PJR Roster - Weekly Checkpoints
print("Analyzing Roster moves (Weekly Checkpoints)...")

# Get list of Mondays in the season
season_start = stats_df['date'].min()
season_end = stats_df['date'].max()
mondays = pd.date_range(start=season_start, end=season_end, freq='W-MON')

recommendations = []

for check_date in mondays:
    # 1. Identify PJR Roster on this date
    # Overlap: start <= check_date <= end
    current_roster = roster_df[
        (roster_df['team_abbrev'] == TEAM_ABBREV) & 
        (roster_df['start_date'] <= check_date) & 
        (roster_df['end_date'] >= check_date)
    ]
    
    if current_roster.empty: continue
    
    # Get values for this date (from rolling_long)
    # rolling_long has 'date', 'player_id', 'Rolling_Value'
    day_stats = rolling_long[rolling_long['date'] == check_date]
    
    if day_stats.empty: continue
    
    # 2. Identify Available Free Agents on this date
    # Find all players rostered by ANYONE on this date
    all_rostered = roster_df[
        (roster_df['start_date'] <= check_date) & 
        (roster_df['end_date'] >= check_date)
    ]['player_id'].unique()
    
    # Potential FAs: Players in day_stats NOT in all_rostered
    # Filter day_stats for FAs
    fa_stats = day_stats[~day_stats['player_id'].isin(all_rostered)]
    
    # Top FAs
    top_fas = fa_stats.sort_values('Rolling_Value', ascending=False).head(20)
    
    # 3. Compare PJR Players to FAs
    for _, row in current_roster.iterrows():
        p_id = row['player_id']
        p_name = row['player_name']
        
        # Get my player's value
        my_stat = day_stats[day_stats['player_id'] == p_id]
        if my_stat.empty:
            my_val = -999 # No stats recently?
        else:
            my_val = my_stat['Rolling_Value'].values[0]
            
        # Find better FAs
        better = top_fas[top_fas['Rolling_Value'] > my_val + 0.75] # Higher threshold to be sure
        
        if not better.empty:
            # Pick top 2
            top_opts = []
            for _, fa_row in better.head(2).iterrows():
                fa_name = fa_row['playerName']
                fa_val = fa_row['Rolling_Value']
                top_opts.append(f"{fa_name} ({fa_val:.2f})")
            
            recommendations.append({
                'Date': check_date.strftime('%Y-%m-%d'),
                'My_Player': p_name,
                'My_Value': f"{my_val:.2f}",
                'Better_FA': ", ".join(top_opts)
            })

# Generate Report
print("Generating report...")
with open(OUTPUT_PATH, 'w') as f:
    f.write(f"# Roster Checkpoint Report for {TEAM_ABBREV}\n\n")
    f.write(f"**Evaluation Window:** {WINDOW} Days (Trailing)\n")
    f.write("**Methodology:** On every Monday, compared trailing 28-day performance of your roster vs. available Free Agents.\n")
    f.write("**Threshold:** FA Value must be > My Player Value + 0.75 Z-Score.\n\n")
    f.write("| Date | Drop Consideration | Value | Better Available Options (Value) |\n")
    f.write("|---|---|---|---|\n")
    
    if not recommendations:
        f.write("\nNo clear missed opportunities found based on the criteria.\n")
    
    for r in recommendations:
        f.write(f"| {r['Date']} | {r['My_Player']} | {r['My_Value']} | {r['Better_FA']} |\n")

print(f"Report saved to {OUTPUT_PATH}")
