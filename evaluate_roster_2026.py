import os
import sys
import pandas as pd
import numpy as np
import re

def clean_name(name):
    return re.sub(r'\s+', ' ', str(name).replace('\xa0', ' ').replace('\u00a0', ' ')).strip()

def parse_player_col(df, player_col='Player'):
    names, teams, positions = [], [], []
    for raw in df[player_col]:
        raw = clean_name(raw)
        raw_clean = re.sub(r'\s+(IL\d+|NRI|MiLB|DFA|RET|FA)$', '', raw)
        match = re.match(r'^(.+?)\s*\((.+?)\s*-\s*(.+?)\)$', raw_clean)
        if match:
            names.append(match.group(1).strip())
            teams.append(match.group(2).strip())
            positions.append(match.group(3).strip())
        else:
            fa_match = re.match(r'^(.+?)\s*\((.+?)\)\s*(?:FA|RET)?$', raw)
            if fa_match:
                names.append(fa_match.group(1).strip())
                teams.append('FA')
                positions.append(fa_match.group(2).strip())
            else:
                names.append(raw_clean)
                teams.append('UNK')
                positions.append('UNK')
    df['Name'] = names
    df['Team'] = teams
    df['Pos'] = positions
    return df

def calculate_z_scores(df, categories, invert_categories=None):
    if invert_categories is None:
        invert_categories = []
    result = df.copy()
    z_cols = []
    for cat in categories:
        z_col = f'Z_{cat}'
        z_cols.append(z_col)
        mean = result[cat].mean()
        std = result[cat].std()
        if std == 0:
            result[z_col] = 0
        else:
            result[z_col] = (result[cat] - mean) / std
            if cat in invert_categories:
                result[z_col] = result[z_col] * -1
    result[f'Total_Z_{df["Type"].iloc[0]}'] = result[z_cols].sum(axis=1)
    return result, z_cols

def get_role(row):
    if row.get('Type') == 'Pitcher': return 'Pitcher'
    return 'Batter'

def main():
    target_team_id = 2 # Datalickmyballs
    
    bronze_path = r"c:\Users\peter\Desktop\vscode\main\.data_lake\01_bronze\fantasy_baseball"
    batters_path = os.path.join(bronze_path, "player_batter_projections_2026.csv")
    pitchers_path = os.path.join(bronze_path, "player_pitcher_projections_2026.csv")
    draft_path = os.path.join(bronze_path, "draft_results_espn_2026.csv")
    
    if not (os.path.exists(batters_path) and os.path.exists(pitchers_path) and os.path.exists(draft_path)):
        print("Missing required CSV files in data lake.")
        return
    
    # Load and parse
    df_batters = pd.read_csv(batters_path)
    df_pitchers = pd.read_csv(pitchers_path)
    df_draft = pd.read_csv(draft_path)
    
    df_batters = parse_player_col(df_batters)
    df_pitchers = parse_player_col(df_pitchers)
    
    # Pitcher derived stats
    df_pitchers['K_per_9'] = np.where(df_pitchers['IP'] > 0, df_pitchers['K'] / df_pitchers['IP'] * 9, 0)
    
    def estimate_qs(row):
        if row['GS'] < 5: return 0
        ip_per_start = row['IP'] / row['GS'] if row['GS'] > 0 else 0
        if ip_per_start < 5.5: return 0
        if row['ERA'] <= 3.0: rate = 0.70
        elif row['ERA'] <= 3.5: rate = 0.60
        elif row['ERA'] <= 4.0: rate = 0.48
        elif row['ERA'] <= 4.5: rate = 0.35
        else: rate = 0.20
        return round(row['GS'] * rate)
        
    df_pitchers['QS'] = df_pitchers.apply(estimate_qs, axis=1)
    df_pitchers['SVHD'] = df_pitchers['SV'] # Simulating since SVHD isn't strictly provided differently
    
    df_batters['Type'] = 'Batter'
    df_pitchers['Type'] = 'Pitcher'
        
    # Calculate Z-Scores
    MIN_AB = 100
    batters_qualified = df_batters[df_batters['AB'] >= MIN_AB].copy()
    batter_cats = ['R', 'HR', 'RBI', 'SB', 'OPS']
    batters_z, batter_z_cols = calculate_z_scores(batters_qualified, batter_cats)
    
    MIN_IP = 30
    pitchers_qualified = df_pitchers[df_pitchers['IP'] >= MIN_IP].copy()
    pitcher_cats = ['ERA', 'WHIP', 'K_per_9', 'QS', 'SVHD']
    pitcher_invert = ['ERA', 'WHIP']
    pitchers_z, pitcher_z_cols = calculate_z_scores(pitchers_qualified, pitcher_cats, pitcher_invert)
    
    # Standardize column naming so they can be merged effectively
    keep_cols_b = ['Name', 'Team', 'Pos', 'Type', 'Total_Z_Batter'] + batter_z_cols + batter_cats
    keep_cols_p = ['Name', 'Team', 'Pos', 'Type', 'Total_Z_Pitcher'] + pitcher_z_cols + pitcher_cats
    
    master_proj = pd.concat([batters_z[keep_cols_b], pitchers_z[keep_cols_p]], ignore_index=True)
    master_proj['Total_Z'] = master_proj['Total_Z_Batter'].fillna(0) + master_proj['Total_Z_Pitcher'].fillna(0)
    
    # Merge with Draft Results
    df_draft['player_name_clean'] = df_draft['player_name'].apply(clean_name)
    df_draft['drafted'] = True
    
    # Match players 
    master_proj['Name_Clean'] = master_proj['Name'].str.replace(' Jr.', '', regex=False).str.replace(' II', '', regex=False).str.strip()
    df_draft['Name_Clean'] = df_draft['player_name_clean'].str.replace(' Jr.', '', regex=False).str.replace(' II', '', regex=False).str.strip()
    
    roster_merged = pd.merge(master_proj, df_draft[['Name_Clean', 'team_id', 'team_name', 'drafted']], 
                             on='Name_Clean', how='left')
                             
    roster_merged['drafted'] = roster_merged['drafted'].fillna(False)
    roster_merged['team_id'] = roster_merged['team_id'].fillna(-1)
    
    # Group by team to find weaknesses
    all_z_cols = batter_z_cols + pitcher_z_cols
    team_totals = roster_merged[roster_merged['drafted'] == True].groupby('team_name')[all_z_cols].sum()
    
    # Rank teams in each category
    team_ranks = team_totals.rank(ascending=False) # 1 is best
    
    if len(df_draft[df_draft['team_id'] == target_team_id]) == 0:
        print(f"Error: Team ID {target_team_id} not found in draft results.")
        return
        
    my_team_name = df_draft[df_draft['team_id'] == target_team_id]['team_name'].iloc[0]
    my_ranks = team_ranks.loc[my_team_name]
    
    print(f"==========================================")
    print(f" ROSTER EVALUATION FOR: {my_team_name}")
    print(f"==========================================\n")
    
    print("Team Category Ranks (1 = Best, 10 = Worst):")
    print(my_ranks.sort_values(ascending=False).to_frame(name='Rank'))
    
    weakest_cats = my_ranks.nlargest(3).index.tolist()
    print(f"\n*** Your 3 Weakest Categories: {', '.join([c.replace('Z_', '') for c in weakest_cats])} ***")
    
    # Who to drop?
    print("\n---------------------------------------------------------")
    print(" DROP CANDIDATES (Your lowest projected players)")
    print("---------------------------------------------------------")
    my_players = roster_merged[roster_merged['team_id'] == target_team_id].copy()
    my_batters = my_players[my_players['Type'] == 'Batter'].sort_values('Total_Z', ascending=True).head(4)
    my_pitchers = my_players[my_players['Type'] == 'Pitcher'].sort_values('Total_Z', ascending=True).head(4)
    
    # Format cols for printing
    b_print_cols = ['Name', 'Total_Z'] + batter_z_cols
    p_print_cols = ['Name', 'Total_Z'] + pitcher_z_cols
    
    print("Batters:")
    print(my_batters[b_print_cols].round(2).to_string(index=False))
    print("\nPitchers:")
    print(my_pitchers[p_print_cols].round(2).to_string(index=False))
    
    # Who to pick up?
    print("\n---------------------------------------------------------")
    print(" PICKUP SUGGESTIONS (Top Free Agents in your weak categories)")
    print("---------------------------------------------------------")
    free_agents = roster_merged[roster_merged['drafted'] == False].copy()
    
    for w_cat in weakest_cats:
        print(f"\n+++ Targeting {w_cat.replace('Z_', '')} +++")
        if w_cat in batter_z_cols:
            fa_subset = free_agents[free_agents['Type'] == 'Batter']
            target_cols = ['Name', 'Total_Z', w_cat]
        else:
            fa_subset = free_agents[free_agents['Type'] == 'Pitcher']
            target_cols = ['Name', 'Total_Z', w_cat]
            
        top_fa = fa_subset.sort_values(w_cat, ascending=False).head(5)
        print(top_fa[target_cols].round(2).to_string(index=False))

if __name__ == "__main__":
    main()
