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

def main():
    bronze_path = r"c:\Users\peter\Desktop\vscode\main\.data_lake\01_bronze\fantasy_baseball"
    batters_path = os.path.join(bronze_path, "player_batter_projections_2026.csv")
    pitchers_path = os.path.join(bronze_path, "player_pitcher_projections_2026.csv")
    draft_path = os.path.join(bronze_path, "draft_results_espn_2026.csv")
    out_md_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "league_roster_evaluation_2026.md")
    
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
    df_pitchers['SVHD'] = df_pitchers['SV']
    
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
    
    keep_cols_b = ['Name', 'Team', 'Pos', 'Type', 'Total_Z_Batter'] + batter_z_cols + batter_cats
    keep_cols_p = ['Name', 'Team', 'Pos', 'Type', 'Total_Z_Pitcher'] + pitcher_z_cols + pitcher_cats
    
    master_proj = pd.concat([batters_z[keep_cols_b], pitchers_z[keep_cols_p]], ignore_index=True)
    master_proj['Total_Z'] = master_proj['Total_Z_Batter'].fillna(0) + master_proj['Total_Z_Pitcher'].fillna(0)
    
    # Merge with Draft Results
    df_draft['player_name_clean'] = df_draft['player_name'].apply(clean_name)
    df_draft['drafted'] = True
    
    master_proj['Name_Clean'] = master_proj['Name'].str.replace(' Jr.', '', regex=False).str.replace(' II', '', regex=False).str.strip()
    df_draft['Name_Clean'] = df_draft['player_name_clean'].str.replace(' Jr.', '', regex=False).str.replace(' II', '', regex=False).str.strip()
    
    roster_merged = pd.merge(master_proj, df_draft[['Name_Clean', 'team_id', 'team_name', 'drafted']], 
                             on='Name_Clean', how='left')
                             
    with pd.option_context('future.no_silent_downcasting', True):
        roster_merged['drafted'] = roster_merged['drafted'].fillna(False).infer_objects(copy=False)
        roster_merged['team_id'] = roster_merged['team_id'].fillna(-1).infer_objects(copy=False)
    
    all_z_cols = batter_z_cols + pitcher_z_cols
    team_totals = roster_merged[roster_merged['drafted'] == True].groupby('team_name')[all_z_cols].sum()
    team_ranks = team_totals.rank(ascending=False) # 1 is best
    team_overall = team_totals.sum(axis=1).sort_values(ascending=False)

    md_content = ["# ⚾ 2026 League Roster Evaluation\n"]
    md_content.append("*Projected strength analysis based on drafted rosters and 2026 projections.*\n")
    
    md_content.append("## Power Rankings (Total Projected Z-Score)")
    for i, (t_name, score) in enumerate(team_overall.items(), 1):
        md_content.append(f"{i}. **{t_name}** ({score:.2f})")
    md_content.append("\n---\n")

    for team_name in team_overall.index:
        team_id = df_draft[df_draft['team_name'] == team_name]['team_id'].iloc[0]
        my_ranks = team_ranks.loc[team_name].sort_values(ascending=True) # 1 is best
        
        md_content.append(f"## Team: {team_name}")
        md_content.append(f"**Overall League Rank:** {team_overall.index.get_loc(team_name) + 1}\n")
        
        strongest_cats = my_ranks.head(3)
        weakest_cats = my_ranks.tail(3)
        
        md_content.append("### 💪 Top Strengths")
        for cat, rank in strongest_cats.items():
            md_content.append(f"- **{cat.replace('Z_', '')}** (Rank: {int(rank)})")
            
        md_content.append("\n### 📉 Biggest Weaknesses")
        for cat, rank in weakest_cats.items():
            md_content.append(f"- **{cat.replace('Z_', '')}** (Rank: {int(rank)})")
            
        md_content.append("\n### 🌟 Best Projected Players")
        team_roster = roster_merged[roster_merged['team_id'] == team_id].sort_values('Total_Z', ascending=False)
        for _, row in team_roster.head(3).iterrows():
            md_content.append(f"- **{row['Name']}** ({row['Pos']}) - *Total Z: {row['Total_Z']:.2f}*")
            
        md_content.append("\n### ✂️ Drop Candidates")
        worst_players = team_roster.tail(3).sort_values('Total_Z', ascending=True)
        for _, row in worst_players.iterrows():
            md_content.append(f"- **{row['Name']}** ({row['Pos']}) - *Total Z: {row['Total_Z']:.2f}*")
            
        md_content.append("\n---\n")

    with open(out_md_path, "w", encoding='utf-8') as f:
        f.write("\n".join(md_content))
        
    print(f"Evaluation complete! Wrote results to {out_md_path}")

if __name__ == "__main__":
    main()
