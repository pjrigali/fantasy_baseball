import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

BASE_PATH = r'c:\Users\peter\Desktop\vscode\main\.data_lake\01_Bronze\fantasy_baseball'

print("Loading data...")
stats_df = pd.read_csv(f'{BASE_PATH}\\stats_mlb_daily_2025.csv')
player_map_df = pd.read_csv(f'{BASE_PATH}\\player_map.csv')

# Preprocess
stats_df['date'] = pd.to_datetime(stats_df['date'])
player_map_df['espn_player_id'] = player_map_df['espn_player_id'].astype(str)
player_map_df['statcast_player_id'] = player_map_df['statcast_player_id'].astype(str).str.replace(r'\.0$', '', regex=True)
stats_df['playerId'] = stats_df['playerId'].astype(str)

print("Merging data...")
stats_merged = stats_df.merge(player_map_df, left_on='playerId', right_on='statcast_player_id', how='left')

# Value Calculation
batter_stats = ['R', 'HR', 'RBI', 'SB']
pitcher_positive = ['QS', 'SVHD', 'K']

def calculate_daily_value(df):
    df['Daily_Value'] = 0.0
    
    # Standardize against the day's performance (Vectorized)
    for col in batter_stats + pitcher_positive:
        if col in df.columns:
            mean = df[col].mean()
            std = df[col].std()
            if std == 0: std = 1
            df[f'z_{col}'] = (df[col] - mean) / std
            df['Daily_Value'] += df[f'z_{col}'].fillna(0)
    
    # ERA/WHIP proxies
    # WHIP Proxy = H + BB
    if 'H' in df.columns and 'BB' in df.columns: # for batters these are different, check pitcher columns
        # Pitcher columns: P_H, P_BB (if they exist) or just H/BB if mapped correctly. 
        # Check columns in stats_df. 
        # based on previous `head`, stats_df has P_H, P_BB.
        whip_val = df['P_H'] + df['P_BB']
        mean = whip_val.mean()
        std = whip_val.std()
        if std == 0: std = 1
        df['Daily_Value'] -= ((whip_val - mean) / std).fillna(0)
        
    if 'ER' in df.columns:
        mean = df['ER'].mean()
        std = df['ER'].std()
        if std == 0: std = 1
        df['Daily_Value'] -= ((df['ER'] - mean) / std).fillna(0)
        
    return df

print("Calculating daily values...")
# Group by date to normalize per day
daily_stats = stats_merged.groupby('date').apply(calculate_daily_value).reset_index(drop=True)

# Time Series Analysis
player_daily = daily_stats[['date', 'espn_player_id', 'Daily_Value']].copy()
player_daily = player_daily.groupby(['date', 'espn_player_id']).sum().reset_index()
pivot_df = player_daily.pivot(index='date', columns='espn_player_id', values='Daily_Value').fillna(0)

windows = [3, 5, 7, 10, 14, 21, 28]
print("\nCorrelations (Past vs Future 7 Days):")
best_corr = -1
best_window = 3

for w in windows:
    rolling_past = pivot_df.rolling(window=w).mean()
    
    # Future 7 days (shift -7? No, rolling(7).mean().shift(-7) gets mean of t to t+6. shift(-8) gets t+1 to t+7?
    # Simple way: 
    # rolling_future = pivot_df.shift(-1).rolling(window=7).mean().shift(-6)? No.
    # We want Average of (t+1, ..., t+7).
    # pivot_df.rolling(7).mean() is avg(t-6, ..., t).
    # So pivot_df.rolling(7).mean().shift(-7) is avg(t+1, ..., t+7).
    
    # Validating shift:
    # t=0. shift(-7) puts t=7 value at t=0. 
    # rolling(7) at t=7 is avg(1..7). 
    # So rolling(7).shift(-7) at t=0 gives avg(1..7). Correct.
    
    rolling_future = pivot_df.rolling(window=7).mean().shift(-7)
    
    past_flat = rolling_past.stack()
    future_flat = rolling_future.stack()
    
    combined = pd.concat([past_flat, future_flat], axis=1).dropna()
    combined.columns = ['past', 'future']
    
    if len(combined) > 0:
        corr = combined['past'].corr(combined['future'])
        print(f"Window {w} days: {corr:.4f}")
        if corr > best_corr:
            best_corr = corr
            best_window = w

print(f"\nOptimal Window: {best_window}")
