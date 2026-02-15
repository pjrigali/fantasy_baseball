import os
import sys
import pandas as pd
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp

def main():
    print("--- Creating Matchup Period Mapping ---")
    
    # 1. Load config
    try:
        config = mp.load_config()
    except Exception as e:
        print(f"Error loading config: {e}")
        return

    # 2. Setup League
    league = mp.setup_league(config, year=2025)
    
    # 3. Build Matchup Map using Heuristic
    # (Since API mapping was incomplete/weird)
    
    # Get Settings
    # final_sp = league.settings.final_scoring_period # This might be 0 if not set?
    # Inspect settings from API showed 167.
    params = {'view': 'mSettings'}
    data = league.espn_request.league_get(params=params)
    status = data.get('status', {})
    schedule_settings = data.get('settings', {}).get('scheduleSettings', {})
    
    final_sp = status.get('finalScoringPeriod', 167) 
    
    # Check length of matchupPeriods map to get TRUE total (Reg + Playoff)
    mp_dict = schedule_settings.get('matchupPeriods', {})
    if mp_dict:
        total_matchups = len(mp_dict)
    else:
        # Fallback to count + 2 assumption if map is empty (unlikely)
        total_matchups = schedule_settings.get('matchupPeriodCount', 18) + 2
        
    reg_season_count = league.settings.reg_season_count
    
    print(f"Details: Final SP={final_sp}, Total Matchups={total_matchups} (derived), Reg Season={reg_season_count}")
    
    # Heuristic Logic from update_daily_stats_matchup.py
    # Distribute SPs evenly among Matchups
    mp_map = {}
    
    # If standard 2025 season length is ~24 weeks (167 days), distribute:
    days_per_matchup = final_sp // total_matchups
    remainder = final_sp % total_matchups
    
    sp_counter = 1
    generated_map = []
    
    for mp_id in range(1, total_matchups + 1):
        days = days_per_matchup
        if mp_id <= remainder:
            days += 1
            
        for _ in range(days):
            if sp_counter <= final_sp:
                mp_map[sp_counter] = mp_id
                
                # Calculate Date (Assuming SP 1 = March 27, 2025)
                # Note: This is an approximation.
                game_date = datetime(2025, 3, 27).date() + timedelta(days=(sp_counter - 1))
                
                generated_map.append({
                    'matchup_period': mp_id,
                    'scoring_period': sp_counter,
                    'date': game_date.strftime("%Y-%m-%d")
                })
                sp_counter += 1
                
    # Generate DataFrame
    df = pd.DataFrame(generated_map)
    
    # Add Start/End Dates for Matchup
    mp_agg = df.groupby('matchup_period')['date'].agg(['min', 'max']).reset_index()
    mp_agg.columns = ['matchup_period', 'matchup_start_date', 'matchup_end_date']
    
    final_df = pd.merge(df, mp_agg, on='matchup_period', how='left')
    
    # Save
    os.makedirs(mp.DATA_PATH, exist_ok=True)
    save_path = os.path.join(mp.DATA_PATH, "matchup_period_map_2025.csv")
    final_df.to_csv(save_path, index=False)
    print(f"Mapping saved to {save_path}")
    print(final_df.head(10))
    print(final_df.tail(10))

if __name__ == "__main__":
    main()
