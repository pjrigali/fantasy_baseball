import sys
import os
import pandas as pd
import numpy as np

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fantasy_baseball.mlb_processing as mp

def calculate_z_scores(df, categories, ascending_categories):
    """
    Calculates Z-scores for the specified categories.
    
    Args:
        df: DataFrame containing player stats.
        categories: List of column names to calculate Z-scores for.
        ascending_categories: List of column names where lower is better (e.g., ERA, WHIP).
        
    Returns:
        DataFrame with Z-score columns and a 'Total_Z' column.
    """
    z_score_df = df.copy()
    z_cols = []
    
    for cat in categories:
        mean = df[cat].mean()
        std = df[cat].std()
        z_col = f"z_{cat}"
        z_cols.append(z_col)
        
        # Avoid division by zero
        if std == 0:
            z_score_df[z_col] = 0
        else:
            z_score_df[z_col] = (df[cat] - mean) / std
        
        # Invert Z-score for categories where lower is better
        if cat in ascending_categories:
            z_score_df[z_col] = z_score_df[z_col] * -1
            
    z_score_df['Total_Z'] = z_score_df[z_cols].sum(axis=1)
    return z_score_df

def main():
    # Load Data
    data_path = os.path.join(mp.DATA_PATH, 'daily_player_stats_2025.csv')
    if not os.path.exists(data_path):
        print(f"Error: File not found at {data_path}")
        return

    print(f"Loading data from {data_path}...")
    df = pd.read_csv(data_path)

    # 1. Aggregate Stats by Player
    # Grouping by teamId ensures players are associated with their current fantasy team
    # Note: If a player was traded, this might split their stats or assign them to the last team.
    # ideally we want to see who is CURRENTLY on the roster.
    # The daily stats file has 'teamId' for each day.
    # We should probably fetch current rosters to know who is eligible for keeping, 
    # OR assume the user wants to know who performed best for each team *during* the season.
    # Given the request "keepers that each league team should keep", we need CURRENT rosters.
    # The 'teamId' in daily stats is historical.
    # However, 'update_daily_stats.py' runs for the whole season.
    # Let's aggregate by playerId first to get total performance value, 
    # THEN map to current team if possible, or use the most frequent teamId as a proxy.
    
    # Aggregation Rules
    agg_rules = {
        'playerName': 'first',
        'teamId': lambda x: x.mode()[0] if not x.mode().empty else x.iloc[-1], # Most frequent team or last
        'team_abbrev': 'last',
        'b_or_p': 'first',
        'R': 'sum',
        'HR': 'sum',
        'RBI': 'sum',
        'SB': 'sum',
        'H': 'sum',
        'AB': 'sum',
        'B_BB': 'sum', # Batting Walks
        'HBP': 'sum',
        'SF': 'sum',
        'TB': 'sum', # Total Bases
        'PA': 'sum', # Plate Appearances
        'ER': 'sum',
        'OUTS': 'sum', # Outs (IP * 3)
        'P_BB': 'sum', # Pitching Walks
        'P_H': 'sum', # Pitching Hits
        'K': 'sum', # Strikeouts
        'QS': 'sum',
        'SVHD': 'sum'
    }
    
    # Ensure columns exist before aggregating (fill missing with 0 for safety)
    for col in agg_rules.keys():
        if col not in df.columns and col not in ['playerName', 'teamId', 'team_abbrev', 'b_or_p']:
             df[col] = 0
             
    print("Aggregating daily stats...")
    player_stats = df.groupby('playerId').agg(agg_rules)
    
    # 2. Calculate Rate Stats
    # Batting: OPS
    player_stats['OBP'] = (player_stats['H'] + player_stats['B_BB'] + player_stats['HBP']) / player_stats['PA']
    player_stats['SLG'] = player_stats['TB'] / player_stats['AB']
    player_stats['OPS'] = player_stats['OBP'] + player_stats['SLG']
    
    # Pitching: ERA, WHIP, K/9
    player_stats['IP'] = player_stats['OUTS'] / 3.0
    player_stats['ERA'] = (player_stats['ER'] * 9) / player_stats['IP']
    player_stats['WHIP'] = (player_stats['P_BB'] + player_stats['P_H']) / player_stats['IP']
    player_stats['K/9'] = (player_stats['K'] * 9) / player_stats['IP']
    
    # Handle NaNs/Infs usually caused by 0 denominator
    player_stats = player_stats.replace([np.inf, -np.inf], np.nan).fillna(0)

    # 3. Filter and Rank Batters
    # Minimum PA threshold to be relevant (e.g., 200 PA) to avoid skewing Z-scores
    min_pa = 200
    batters = player_stats[(player_stats['b_or_p'] == 'batter') & (player_stats['PA'] >= min_pa)].copy()
    
    batting_cats = ['R', 'HR', 'RBI', 'SB', 'OPS']
    # Calculate Z-Scores
    batters_z = calculate_z_scores(batters, batting_cats, [])
    
    # 4. Filter and Rank Pitchers
    # Minimum IP threshold (e.g., 50 IP)
    min_ip = 50
    pitchers = player_stats[(player_stats['b_or_p'] == 'pitcher') & (player_stats['IP'] >= min_ip)].copy()
    
    pitching_cats = ['ERA', 'WHIP', 'K/9', 'QS', 'SVHD']
    ascending_cats = ['ERA', 'WHIP']
    pitchers_z = calculate_z_scores(pitchers, pitching_cats, ascending_cats)
    
    # 5. Combine and Select Top 5 Per Team
    all_ranked = pd.concat([batters_z, pitchers_z])
    
    print("\n--- Top 5 Keepers Per Team ---")
    teams = all_ranked['teamId'].unique()
    
    # We need a team map for names if possible, but we'll use ID/Abbrev for now.
    # Try to load team map from config/league if we wanted, but let's stick to valid data.
    
    results = []
    
    for team_id in teams:
        team_df = all_ranked[all_ranked['teamId'] == team_id]
        if team_df.empty:
            continue
            
        # Sort by Total Z-score descending
        top_5 = team_df.sort_values(by='Total_Z', ascending=False).head(5)
        
        # Normalize columns for output
        for index, row in top_5.iterrows():
            pos = 'Batter' if row['b_or_p'] == 'batter' else 'Pitcher'
            
            # Create a display string for key stats
            if pos == 'Batter':
                stats_str = f"R:{row['R']:.0f}/HR:{row['HR']:.0f}/RBI:{row['RBI']:.0f}/SB:{row['SB']:.0f}/OPS:{row['OPS']:.3f}"
            else:
                stats_str = f"ERA:{row['ERA']:.2f}/WHIP:{row['WHIP']:.2f}/K9:{row['K/9']:.2f}/QS:{row['QS']:.0f}/SVHD:{row['SVHD']:.0f}"
                
            results.append({
                'Team ID': team_id,
                'Team': row['team_abbrev'],
                'Player': row['playerName'],
                'Position': pos,
                'Total Value (Z)': round(row['Total_Z'], 2),
                'Key Stats': stats_str
            })

    results_df = pd.DataFrame(results)
    
    # Sort for final display: Team, then Value
    results_df = results_df.sort_values(by=['Team ID', 'Total Value (Z)'], ascending=[True, False])
    
    output_path = os.path.join(mp.DATA_PATH, 'projected_keepers_2026.csv')
    print(f"Saving results to {output_path}...")
    results_df.to_csv(output_path, index=False)
    
    # Print preview
    print(results_df.to_string(index=False))

if __name__ == "__main__":
    main()
