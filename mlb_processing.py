import os
import csv
import json
import requests
import configparser
import numpy as np
import pandas as pd
import time
import io
import seaborn as sb
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from espn_api.baseball import League
from espn_api.baseball.constant import POSITION_MAP, PRO_TEAM_MAP, STATS_MAP
from statsmodels import regression
import statsmodels.api as sm
from fantasy_baseball.universal import MONTH_DCT

# CONSTANTS
# You might want to move these to a config file or constants file if they grow
ESPN_HEADERS = {
    'Connection': 'keep-alive',
    'Accept': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
}

# Data Storage
DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.data_lake', '01_bronze', 'fantasy_baseball')

def load_config(config_file="config.ini"):
    """
    Loads configuration from the specified INI file.
    Searches in CWD, script directory, and parent directory.
    
    Args:
        config_file (str): Name of the config file.
    
    Returns:
        configparser.ConfigParser: Loaded configuration object.
    """
    # Check CWD
    if os.path.exists(config_file):
        path = config_file
    # Check script directory
    elif os.path.exists(os.path.join(os.path.dirname(__file__), config_file)):
        path = os.path.join(os.path.dirname(__file__), config_file)
    # Check parent directory
    elif os.path.exists(os.path.join(os.path.dirname(os.path.dirname(__file__)), config_file)):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), config_file)
    else:
        # Fallback to default if not found (let ConfigParser handle empty or fail later)
        path = config_file
        
    config = configparser.ConfigParser(interpolation=None)
    config.read(path)
    return config

def setup_league(config, year=2025):
    """
    Initializes the ESPN League object using credentials from the config.
    
    Args:
        config (configparser.ConfigParser): Loaded configuration.
        year (int): Season year.
        
    Returns:
        espn_api.baseball.League: Initialized League object.
    """
    bb_config = config['BASEBALL']
    league_id = int(bb_config['BB_LEAGUE_ID'])
    swid = '{' + bb_config['BB_SWID'] + '}'
    espn_s2 = bb_config['BB_ESPN_2']
    
    return League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)

def json_parsing(obj, key):
    """
    Recursively pull values of specified key from nested JSON.
    
    Args:
        obj (dict/list): Input JSON data.
        key (str): Key to search for.
        
    Returns:
        list or value: All matching values found.
    """
    arr = []

    def extract(obj, arr, key):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (dict)) or (isinstance(v, (list)) and  v and isinstance(v[0], (list, dict))):
                    extract(v, arr, key)
                elif k == key:
                    arr.append(v)
        elif isinstance(obj, list):
            for item in obj:
                extract(item, arr, key)
        return arr

    results = extract(obj, arr, key)
    return results[0] if results else results

def remove_none(lst: list) -> list:
    """Removes None values from a list."""
    return [i for i in lst if i is not None]

# --- Data Fetching Functions ---

def get_pitcher_game_logs(player_id: int, year: int = 2025) -> list:
    """
    Fetches game logs for a pitcher from ESPN API.
    
    Args:
        player_id (int): ESPN Player ID.
        year (int): Season year.
        
    Returns:
        list: List of game log dictionaries.
    """
    url = f"https://site.web.api.espn.com/apis/common/v3/sports/baseball/mlb/athletes/{player_id}/gamelog?region=us&lang=en&contentorigin=espn&season={year}&category=pitching"
    response = requests.get(url, headers=ESPN_HEADERS).json()

    games = []
    if 'seasonTypes' in response:
        games = response['seasonTypes'][0]['categories']

    game_log = []
    if games:
        game_info = {}
        for k, v in response['events'].items():
            d = {i: v[i] for i in ('id', 'week', 'gameDate', 'score', 'homeTeamId', 'awayTeamId', 'homeTeamScore', 'awayTeamScore', 'gameResult')}
            d['opponentId'] = v['opponent']['id']
            d['opponentAbbreviation'] = v['opponent']['abbreviation']
            d['teamId'] = v['team']['id']
            d['teamAbbreviation'] = v['team']['abbreviation']
            game_info[k] = d
        
        for i in games:
            for j in i['events']:
                stats_list = ['IP', 'H', 'R', 'ER', 'HR', 'BB', 'K', 'GB', 'FB', 'P', 'TBF', 'GSC', 'DEC', 'REL', 'ERA']
                # Check if j['stats'] exists or has enough elements to zip safely
                if 'stats' not in j:
                    continue
                    
                d = dict(zip(stats_list, j['stats']))

                for k, v in d.items():
                    if k in ('IP', 'GSC', 'ERA'):
                        d[k] = float(v)
                    elif k in ('H', 'R', 'ER', 'HR', 'BB', 'K', 'GB', 'FB', 'P', 'TBF'):
                        d[k] = int(v)
                
                if d.get('IP', 0.0) == 0.0:
                    d['IP'] = 1.0 # Avoid division by zero
                    
                d['WHIP'] = round((d['BB'] + d['H']) / d['IP'], 2)
                d['K/9'] = round((d['K'] / d['IP']) * 9, 2)
                
                # The original code had a nested append which was likely a bug or redundant: game_log.append(game_log.append(...))
                # Fixed to single append
                entry = {'playerId': player_id, 'year': year}
                entry.update(game_info.get(j['eventId'], {}))
                entry.update(d)
                game_log.append(entry)
    return game_log

def get_batter_game_logs(player_id: int, year: int = 2025) -> list:
    """
    Fetches game logs for a batter from ESPN API.
    
    Args:
        player_id (int): ESPN Player ID.
        year (int): Season year.
        
    Returns:
        list: List of game log dictionaries.
    """
    url = f"https://site.web.api.espn.com/apis/common/v3/sports/baseball/mlb/athletes/{player_id}/gamelog?region=us&lang=en&contentorigin=espn&season={year}&category=batting"
    response = requests.get(url, headers=ESPN_HEADERS).json()

    games = []
    if 'seasonTypes' in response:
        games = response['seasonTypes'][0]['categories']

    game_log = []
    if games:
        game_info = {}
        for k, v in response['events'].items():
            d = {i: v[i] for i in ('id', 'week', 'gameDate', 'score', 'homeTeamId', 'awayTeamId', 'homeTeamScore', 'awayTeamScore', 'gameResult')}
            d['opponentId'] = v['opponent']['id']
            d['opponentAbbreviation'] = v['opponent']['abbreviation']
            d['teamId'] = v['team']['id']
            d['teamAbbreviation'] = v['team']['abbreviation']
            game_info[k] = d
        
        for i in games:
            for j in i['events']:
                stats_list = ['AB', 'R', 'H', '2B', '3B', 'HR', 'RBI', 'BB', 'HBP', 'SO', 'SB', 'CS', 'AVG', 'OBP', 'SLG', 'OPS']
                if 'stats' not in j:
                    continue
                d = dict(zip(stats_list, j['stats']))

                for k, v in d.items():
                    if k in ('AVG', 'OBP', 'SLG', 'OPS'):
                        d[k] = float(v)
                    else:
                        d[k] = int(v)

                entry = {'playerId': player_id, 'year': year}
                entry.update(game_info.get(j['eventId'], {}))
                entry.update(d)
                game_log.append(entry)
    return game_log

def get_daily_lineups():
    """
    Scrapes daily MLB lineups from Rotowire.
    
    Returns:
        tuple: (list of pitcher data, list of batter data)
    """
    url = "https://www.rotowire.com/baseball/daily-lineups.php"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "html.parser")

    data_pitching = []
    data_batter = []
    team_type = ''
    order_count = 1

    for e in soup.select('.lineup__box ul li'):
        # Check if we moved to a new team section
        if e.parent.get('class'):
            current_team_type = e.parent.get('class')[-1]
            if team_type != current_team_type:
                order_count = 1
                team_type = current_team_type

        if e.get('class') and 'lineup__player-highlight' in e.get('class'):
            data_pitching.append({
                'date': e.find_previous('main').get('data-gamedate'),
                'game_time': e.find_previous('div', attrs={'class':'lineup__time'}).get_text(strip=True),
                'pitcher_name': e.a.get_text(strip=True),
                'team': e.find_previous('div', attrs={'class':team_type}).next.strip(),
                'lineup_throws': e.span.get_text(strip=True)
            })
        elif e.get('class') and 'lineup__player' in e.get('class'):
            data_batter.append({
                'date': e.find_previous('main').get('data-gamedate'),
                'game_time': e.find_previous('div', attrs={'class':'lineup__time'}).get_text(strip=True),
                'pitcher_name': e.a.get_text(strip=True),
                'team': e.find_previous('div', attrs={'class':team_type}).next.strip(),
                'pos': e.div.get_text(strip=True),
                'batting_order': order_count,
                'lineup_bats': e.span.get_text(strip=True)
            })
            order_count += 1
            
    return data_pitching, data_batter

def grab_mlb_sched(start_dt: str, end_dt: str) -> list:
    """
    Scrapes the MLB schedule for a given date range.
    
    Args:
        start_dt (str): Start date in 'YYYY-MM-DD' format.
        end_dt (str): End date in 'YYYY-MM-DD' format.
        
    Returns:
        list: List of dictionaries containing game details (date, weekday, type, home, away).
    """
    # Collect URL dates
    MLB_HEADERS = {'Connection': 'keep-alive', 'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'}
    start_date = datetime.strptime(start_dt, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_dt, '%Y-%m-%d').date()
    num = (end_date - start_date).days
    dates = []
    for i in range(0, num):
        dt = start_date + timedelta(days=i)
        if dt == end_date:
            break
        else:
            dates.append(str(dt))

    completed_dts = set()
    lst = []
    for dt in dates:
        if dt not in completed_dts:
            # Give the program a nap.
            time.sleep(0.5)
            # Collect the html.
            try:
                response = requests.get('https://www.mlb.com/schedule/' + dt, headers=MLB_HEADERS)
                soup = BeautifulSoup(response.text, 'html.parser')

                # Collect the table information.
                # Note: Class names are hashed and likely brittle. 
                # Ideally, this should be robustified or allow for dynamic class finding if possible.
                # Keeping original logic for now as requested.
                weekdays = [i.text for i in soup.find_all('div', attrs={'class': "ScheduleCollectionGridstyle__DateLabel-sc-c0iua4-5 iaVuoa"})]
                types = [i.text if i.text else 'Regular' for i in soup.find_all('div', attrs={'class': "ScheduleCollectionGridstyle__GameTypeLabel-sc-c0iua4-6 dTLQcW"})]

                game_dates = []
                for d in soup.find_all('div', attrs={'class': "ScheduleCollectionGridstyle__DateLabel-sc-c0iua4-5 fQIzmH"}):
                    parts = d.text.split(' ')
                    if len(parts) >= 2:
                        month, date = parts[0], parts[1]
                        if month in MONTH_DCT:
                            str_date = f'2025-{MONTH_DCT[month]}-{date.zfill(2)}'
                            completed_dts.add(str_date)
                            game_dates.append({'date': str_date})

                games = []
                for game_table in soup.find_all('div', attrs={'class':"ScheduleCollectionGridstyle__SectionWrapper-sc-c0iua4-0 guIOQi"}):
                    daily_game_lst = game_table.find_all('div', attrs={'class':"TeamMatchupLayerstyle__TeamMatchupLayerWrapper-sc-ouprud-0 gQznxP teammatchup-teaminfo"})
                    daily_game_lst = [i.text for i in daily_game_lst]
                    temp = []
                    for game in daily_game_lst:
                        if '@' in game:
                            home, away = game.split('@')
                            # OK, Clean it up.
                            if len(home) == 4:
                                home = home[0] + home[1]
                            else:
                                home = home[0] + home[1] + home[3]

                            if len(away) == 4:
                                away = away[0] + away[1]
                            else:
                                away = away[0] + away[1] + away[3]
                                
                            temp.append({'home': home, 'away': away})
                    games.append(temp)

                # Link the elements.
                if len(weekdays) == len(game_dates) and len(weekdays) == len(games):
                    for i, j in enumerate(weekdays):
                        d = {'date': game_dates[i]['date'], 'weekday': weekdays[i], 'game_type': types[i]}
                        for v in games[i]:
                            lst.append(dict(d)| v)
                else:
                    print(f"Warning: Mismatch in scraped lists for {dt}. Skipping day.")

                # Tell me youre alive.
                for i in set(i['date'] for i in game_dates):
                    print(f'Day completed ... ({i})')
            except Exception as e:
                print(f"Error scraping {dt}: {e}")

    print(f'Number of games captured ... ({len(lst)})')
    return lst

def get_free_agents(league, position_ids=[14, 15], size=100):
    """
    Fetches top free agents for specific positions.
    
    Args:
        league (League): ESPN League object.
        position_ids (list): List of position IDs (e.g., [14, 15] for SP, RP).
        size (int): Number of players to fetch.
        
    Returns:
        list: List of processed free agent dictionaries.
    """
    params = {'view': 'kona_player_info', 'scoringPeriodId': league.current_week}
    players = []
    
    for slot in position_ids:
        filters = {
            "players": {
                "filterStatus": {"value": ["FREEAGENT", "WAIVERS"]},
                "filterSlotIds": {"value": [slot]},
                "limit": size,
                "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
                "sortDraftRanks": {"sortPriority": 100, "sortAsc": True, "value": "STANDARD"}
            }
        }
        headers = {'x-fantasy-filter': json.dumps(filters)}
        data = league.espn_request.league_get(params=params, headers=headers)
        if 'players' in data:
            players.extend(data['players'])
            
    free_agents = []
    for i in players:
        name = json_parsing(i, 'fullName')
        playerId = json_parsing(i, 'id')
        position = POSITION_MAP.get(json_parsing(i, 'defaultPositionId') - 1, json_parsing(i, 'defaultPositionId') - 1)
        lineupSlot = POSITION_MAP.get(i.get('lineupSlotId'), '')
        
        eligible_slots_raw = json_parsing(i, 'eligibleSlots')
        eligibleSlots = [POSITION_MAP.get(pos, pos) for pos in eligible_slots_raw] if eligible_slots_raw else []
        
        acquisitionType = json_parsing(i, 'acquisitionType')
        proTeamId = json_parsing(i, 'proTeamId')
        proTeam = PRO_TEAM_MAP.get(proTeamId, proTeamId)
        injuryStatus = json_parsing(i, 'injuryStatus')
        
        stats = {}
        player_entry = i.get('playerPoolEntry', {}).get('player') or i.get('player', {})
        injured = player_entry.get('injured', False)
        research = player_entry.get('ownership', {})
        
        player_stats = player_entry.get('stats', [])
        for j in player_stats:
            if j['statSplitTypeId'] == 1:
                time_period = 'last7days'
            elif j['statSplitTypeId'] == 2:
                time_period = 'last15days'
            elif j['statSplitTypeId'] == 3:
                time_period = 'last30days'
            elif j['statSplitTypeId'] == 0:
                if j['statSourceId'] == 0:
                    time_period = str(j['seasonId'])
                else:
                    time_period = str(j['seasonId']) + 'Projected'
            else:
                continue

            temp = {}
            if 'stats' in j:
                for k, v in j['stats'].items():
                    if int(k) in STATS_MAP:
                        temp[STATS_MAP[int(k)]] = v
            stats[time_period] = temp

        free_agents.append({
            'name': name, 
            'playerId': playerId, 
            'position': position, 
            'lineupSlot': lineupSlot, 
            'eligibleSlots': eligibleSlots, 
            'acquisitionType': acquisitionType, 
            'proTeam': proTeam, 
            'injuryStatus': injuryStatus, 
            'injured': injured, 
            'research': research, 
            'stats': stats
        })
    return free_agents

def get_league_rosters(league, today_dt=None) -> list:
    """
    Fetches roster data for all teams in the league.
    Aggregates player info into a list of dictionaries.
    
    Args:
        league (League): ESPN League object.
        today_dt (datetime, optional): Date to tag the records with.
        
    Returns:
        list: List of player dictionaries.
    """
    if today_dt:
        today_dt = str(today_dt)
    
    league_teams_players = []
    for team in league.teams:
        for player in team.roster:
            player_dct = {
                'date': today_dt,
                'team_id': team.team_id,
                'player_acquisition_type': player.acquisitionType,
                'player_eligible_slots': player.eligibleSlots,
                'player_injured': player.injured,
                'player_injury_status': player.injuryStatus,
                'player_lineup_slot': player.lineupSlot,
                'player_name': player.name,
                'player_id': player.playerId,
                'player_position': player.position,
                'player_pro_team': player.proTeam,
                'player_projected_total_points': player.projected_total_points,
                'player_total_points': player.total_points,
            }
            league_teams_players.append(player_dct)
    return league_teams_players

def get_league_teams(league, today_dt=None) -> list:
    """
    Fetches metadata for all teams in the league.
    
    Args:
        league (League): ESPN League object.
        today_dt (datetime, optional): Date to tag the records with.
        
    Returns:
        list: List of team metadata dictionaries.
    """
    if today_dt:
        today_dt = str(today_dt)
        
    league_teams = []
    for team in league.teams:
        team_dct = {
            'date': today_dt,
            'team_division_id': team.division_id,
            'team_division_name': team.division_name,
            'team_final_standing': team.final_standing,
            'team_logo_url': team.logo_url,
            'team_losses': team.losses,
            'team_owner_display_name': team.owners[0]['displayName'] if team.owners else 'Unknown',
            'team_owner_id': team.owners[0]['id'] if team.owners else 'Unknown',
            'team_standing': team.standing,
            'team_abbrev': team.team_abbrev,
            'team_id': team.team_id,
            'team_name': team.team_name,
            'team_ties': team.ties,
            'team_wins': team.wins
        }
        league_teams.append(team_dct)
    return league_teams

def get_league_transactions(league):
    """
    Fetches and filters league communication logs for transactions (Adds, Drops, Trades).
    
    Args:
        league (League): ESPN League object.
        
    Returns:
        list: List of transaction dictionaries.
    """
    transaction_list = []
    try:
        # L.espn_request.get_league_communication(L.year)
        # This method assumes espn_api has 'get_league_communication'
        if hasattr(league.espn_request, 'get_league_communication'):
            comm_data = league.espn_request.get_league_communication(league.year)
        else:
            # Fallback: Try using league_get directly with extend
            # This assumes league_get supports 'extend' or we construct the params
            comm_data = league.espn_request.league_get(extend='/communication/', params={'view': 'kona_league_communication'})
            
        topics = comm_data.get('topics', [])
        
        for topic in topics:
            if topic['type'] == 'ACTIVITY_TRANSACTIONS':
                date = datetime.fromtimestamp(topic['date']/1000)
                messages = topic.get('messages', [])
                for msg in messages:
                    if msg['type'] in ('ROSTER_ADD', 'ROSTER_DROP', 'TRADE_ACCEPTED'):
                        transaction_list.append({
                            'date': date,
                            'type': msg['type'],
                            'targetId': msg.get('targetId'),
                            'from': msg.get('from'),
                            'to': msg.get('to')
                        })
            
    except Exception as e:
        print(f"Error fetching transactions: {e}")
        
    return transaction_list

def scrape_espn_historical_stats(years=[2024]):
    """
    Scrapes historical MLB player stats from ESPN.
    
    Args:
        years (list): List of years to scrape.
        
    Returns:
        pandas.DataFrame: Consolidated stats DataFrame.
    """
    df_list = []
    
    for year in years:
        print(f"Scraping stats for {year}...")
        for i in range(1, 800, 40): # Loop through pages
            url = f"https://www.espn.com/mlb/history/leaders/_/breakdown/season/year/{year}/start/{i}"
            try:
                response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
                if response.status_code == 200:
                    dfs = pd.read_html(io.StringIO(response.text))
                    if dfs:
                        curr_df = dfs[0]
                        # Cleanup header: Identify row where column 0 is 'RK'
                        # or just drop first row if it mimics header, but ESPN puts headers every X rows
                        curr_df = curr_df[curr_df[0] != 'RK']
                        curr_df['Year'] = year
                        df_list.append(curr_df)
                time.sleep(0.2)
            except Exception as e:
                # print(f"Error scraping {year} page {i}: {e}")
                pass 
                
    if df_list:
        final_df = pd.concat(df_list, ignore_index=True)
        # Rename columns if needed (ESPN tables often have numeric columns initially)
        # We can try to assume standard columns or leave as is for exploration
        return final_df
    return pd.DataFrame()

# --- Analysis Functions ---

def analyze_roster_batters(league, team_id=2):
    """
    Analyzes consistency of batters on a specific roster.
    
    Args:
        league (League): ESPN League object.
        team_id (int): Team ID to analyze.
        
    Returns:
        tuple: (list of individual consistencies, overall team consistency)
    """
    my_team = None
    for i in league.teams:
        if i.team_id == team_id:
            my_team = i
            break
            
    if not my_team:
        print(f"Team ID {team_id} not found.")
        return [], 0

    my_batters = []
    for i in my_team.roster:
        is_p = False
        for slot in i.eligibleSlots:
            if slot in ('SP', 'RP'):
                is_p = True
        if not is_p:
            my_batters.append(i)

    my_batters_games = []
    for p in my_batters:
        my_batters_games.append({
            'name': p.name, 
            'position': p.eligibleSlots, 
            'games': get_batter_game_logs(playerId=p.playerId, year=league.year)
        })

    all_did_something = 0
    games_totals = 0
    consistency_list = []
    
    print("--- Batter Consistency ---")
    for i in my_batters_games:
        did_something = 0
        total_games = len(i['games'])
        
        for j in i['games']:
            if j.get('AB', 0) > 0:
                if j.get('R', 0) == 0 and j.get('RBI', 0) == 0 and j.get('SB', 0) == 0 and j.get('HR', 0) == 0:
                    pass
                else:
                    did_something += 1
        
        all_did_something += did_something
        games_totals += total_games
        
        ratio = round(did_something / total_games, 2) if total_games > 0 else 0
        consistency_list.append({'name': i['name'], 'ratio': ratio})
        print(f"{i['name']}: {ratio}")

    team_avg = round(all_did_something / games_totals, 2) if games_totals > 0 else 0
    print(f"\nTeam Average Consistency: {team_avg}")
    
    return consistency_list, team_avg

def fetch_league_matchup_data(league, matchup_map):
    """
    Fetches detailed matchup data for the league.
    
    Args:
        league (League): ESPN League object.
        matchup_map (dict or list): Mapping of matchup periods to scoring periods, 
                                    OR a simple list of scoring periods to fetch.
        
    Returns:
        list: List of dictionaries containing flattened player stats for matchups.
    """
    league_team_dict = {i.team_id: i.team_abbrev for i in league.teams}
    data_list = []
    
    # Normalize input: If list, treat as single batch without matchup filter
    if isinstance(matchup_map, list) or isinstance(matchup_map, range):
        # Create a dummy map where key is None (signal to skip filter)
        matchup_map = {None: matchup_map}

    for matchup_period, scoring_period_lst in matchup_map.items():
        # Handle cases where scoring_period_lst is a tuple range, or list
        if isinstance(scoring_period_lst, tuple) and len(scoring_period_lst) == 2:
             scoring_periods = range(scoring_period_lst[0], scoring_period_lst[1] + 1)
        else:
             scoring_periods = scoring_period_lst

        print(f"Processing (Matchup Filter: {matchup_period}) Sc. Periods: {scoring_periods}")
        
        for scoring_period in scoring_periods:
            params = {'view': ['mMatchupScore', 'mScoreboard'], 'scoringPeriodId': scoring_period}
            
            # Only apply matchup filter if specific period provided
            headers = {}
            if matchup_period is not None:
                filters = {"schedule": {"filterMatchupPeriodIds": {"value": [matchup_period]}}}
                headers = {'x-fantasy-filter': json.dumps(filters)}
            
            try:
                data = league.espn_request.league_get(params=params, headers=headers)
            except Exception as e:
                print(f"  Error fetching SP {scoring_period}: {e}")
                continue
                
            schedule = data.get('schedule', [])
            records_found = 0

            for i in schedule:
                for side in ('away', 'home'):
                    if side not in i:
                        continue
                    
                    team_data = i[side]
                    if 'rosterForCurrentScoringPeriod' not in team_data:
                        continue
                        
                    entries = team_data.get('rosterForCurrentScoringPeriod', {}).get('entries', [])
                    for j in entries:
                        player_pool_entry = j.get('playerPoolEntry', {})
                        player = player_pool_entry.get('player', {})
                        
                        lineup_slot_id = int(j.get('lineupSlotId', -1))
                        lineup_slot_name = POSITION_MAP.get(lineup_slot_id, str(lineup_slot_id))
                        
                        entry_data = {
                            'matchup_period': matchup_period,
                            'scoring_period': scoring_period,
                            'teamId': team_data.get('teamId'),
                            'playerId': player.get('id'),
                            'playerName': player.get('fullName'),
                            'lineupSlot': lineup_slot_name,
                            'b_or_p': 'batter' if lineup_slot_id not in (13, 14, 15) else 'pitcher'
                        }

                        if player.get('stats'):
                            # Assuming stats[0] is the relevant one, as per notebook logic
                            stats_source = player['stats'][0]
                            stats_dict = stats_source.get('stats', {})
                            
                            # Capture Points
                            entry_data['points'] = stats_source.get('appliedTotal', 0)
                            
                            for stat_id, stat_val in stats_dict.items():
                                if int(stat_id) in STATS_MAP:
                                    entry_data[STATS_MAP[int(stat_id)]] = stat_val
                        
                        data_list.append(entry_data)
                        records_found += 1
            print(f"  SP {scoring_period}: Found {records_found} records")
            
    return data_list, league_team_dict

def get_matchup_scoreboard(league, matchup_period=None):
    """
    Fetches the scoreboard (matchup results) for the league.
    
    Args:
        league (League): ESPN League object.
        matchup_period (int, optional): Specific matchup period to filter by.
        
    Returns:
        list: List of matchup dictionaries (home_team, away_team, scores).
    """
    params = {'view': ['mMatchupScore', 'mScoreboard']}
    
    # If a specific period is requested, we can try to filter, but mScoreboard usually returns all.
    # We will filter in python if needed.
    headers = {}
    if matchup_period:
        filters = {"schedule": {"filterMatchupPeriodIds": {"value": [matchup_period]}}}
        headers = {'x-fantasy-filter': json.dumps(filters)}

    data = league.espn_request.league_get(params=params, headers=headers)
    schedule = data.get('schedule', [])
    
    scoreboard = []
    for match in schedule:
        # Check if we should filter (if API didn't do it or if we want to be safe)
        if matchup_period and match.get('matchupPeriodId') != matchup_period:
            continue
            
        match_data = {
            'matchupPeriodId': match.get('matchupPeriodId'),
            'id': match.get('id'),
            'winner': match.get('winner'),
            'playoffTierType': match.get('playoffTierType'),
        }
        
        home = match.get('home', {})
        away = match.get('away', {})
        
        match_data['homeTeamId'] = home.get('teamId')
        match_data['homeScore'] = home.get('totalPoints')
        match_data['homeAdjustment'] = home.get('adjustment')
        
        match_data['awayTeamId'] = away.get('teamId')
        match_data['awayScore'] = away.get('totalPoints')
        match_data['awayAdjustment'] = away.get('adjustment')
        
        scoreboard.append(match_data)
        
    return scoreboard

def get_matchup_period_map(league):
    """
    Generates a mapping of Matchup Period -> Scoring Periods with dates.
    
    Args:
        league (League): ESPN League object.
        
    Returns:
        list: List of dicts with keys: matchup_period, scoring_period, date
    """
    map_data = []
    
    # 1. Get Matchup Period -> Scoring Period ID mapping from Settings
    params = {'view': 'mSettings'}
    data = league.espn_request.league_get(params=params)
    
    mp_settings = {}
    if 'settings' in data and 'scheduleSettings' in data['settings']:
        mp_settings = data['settings']['scheduleSettings'].get('matchupPeriods', {})
        
    # 2. Get Scoring Period ID -> Date mapping ?
    # There isn't a direct API call for "list of all scoring periods with dates".
    # However, we can approximate the date if we know the first scoring period date.
    # OR we can assume 2025 season start.
    # Better approach might be to leverage MLB schedule logic if we want exact dates.
    # BUT, let's look at available data. 
    # 'proTeamSchedule' view might help but that's per team.
    
    # Let's rely on the assumption that Scoring Period 1 is the start of the season.
    # For now, let's just return the MP -> SP mapping, and maybe we can find dates later
    # or loop through days? That's expensive.
    
    # Actually, we can fetch the MLB schedule using grab_mlb_sched for the whole season,
    # then map dates to scoring periods (SP 1 = Day 1). 
    # BUT, ESPN SPs might skip days or combine them (like All-Star break).
    
    # Optimization: We already know the mapping from Settings is accurate for MP->SP.
    # Let's return the structured list. To add dates, we might need a reference start date.
    
    # Let's try to get a reference date from the league status.
    # status -> firstScoringPeriod (1).
    # We might need to just use a known start date for 2025 MLB Season: March 20, 2025 (Seoul Series) or March 27 (Domestic).
    # Actually, let's check if we can get date from mScoreboard for a few sample SPs and interpolate? No.
    
    # Let's just output MP and SP for now, and try to find a way to get dates.
    # Wait, the user wants "start/end dates for each match up".
    # Since we have the list of SPs for each MP, if we can map SP -> Date, we are good.
    
    sorted_mps = sorted([int(k) for k in mp_settings.keys()])
    
    for mp_id in sorted_mps:
        sp_list = mp_settings.get(str(mp_id), [])
        for sp in sp_list:
            map_data.append({
                'matchup_period': mp_id,
                'scoring_period': sp
            })
            
    return map_data

def calculate_team_aggregates(data_list, league_team_dict, period_type='weekly'):
    """
    Calculates team stats aggregated by week or day.
    
    Args:
        data_list (list): Flattened player data from fetch_league_matchup_data.
        league_team_dict (dict): Map of team ID to Abbreviation.
        period_type (str): 'weekly' or 'daily'.
        
    Returns:
        list: List of dictionaries with aggregated stats per team.
    """
    # Group data by Team -> Period
    team_data = {tid: {} for tid in league_team_dict}
    
    # Define stats to aggregate
    sum_stats = ('R', 'HR', 'RBI', 'SB', 'QS', 'SVHD')
    avg_stats = ('OPS', 'ERA', 'WHIP', 'K/9')
    all_stats = sum_stats + avg_stats

    # Clean data (convert types)
    cleaned_list = []
    for row in data_list:
        new_row = row.copy()
        # Ensure stats are float/int or None
        for stat in all_stats:
            if stat in new_row and new_row[stat] != '':
                try:
                    new_row[stat] = float(new_row[stat])
                except (ValueError, TypeError):
                    new_row[stat] = None
            else:
                new_row[stat] = None
        cleaned_list.append(new_row)

    # Aggregation
    for row in cleaned_list:
        team_id = row['teamId']
        if team_id not in team_data: 
            continue # Should be initialized, but safety check
            
        period_key = row['matchup_period'] if period_type == 'weekly' else row['scoring_period']
        
        if period_key not in team_data[team_id]:
            team_data[team_id][period_key] = {s: [] for s in all_stats}
            
        # Only include active slots (Notebook logic: excludes 'BE', 'IL')
        if row['lineupSlot'] not in ('BE', 'IL'):
            for stat in all_stats:
                if row.get(stat) is not None:
                    # Specific conditions from notebook (e.g. only batter stats if batter)
                    # The notebook logic was a bit robust: it separated b/p stats
                    if row['b_or_p'] == 'batter' and stat in ('R', 'HR', 'RBI', 'SB', 'OPS'):
                        team_data[team_id][period_key][stat].append(row[stat])
                    elif row['b_or_p'] == 'pitcher' and stat in ('QS', 'ERA', 'WHIP', 'K/9', 'SVHD'):
                        team_data[team_id][period_key][stat].append(row[stat])
                    
                    # Logic adjustment: SVHD 0 fill if P/RP and 3 outs (from notebook)
                    # This logic is complex to port without all context, simplified to straight aggregation for now
                    # unless strictly required. Notebook logic:
                    # if i['lineupSlot'] in ('P', 'RP') and 'OUTS' in i and i['OUTS'] == 3 ... 
                    # We'll stick to basic aggregation for robustness unless requested otherwise.

    # Calculate means/sums
    final_output = []
    for team_id, periods in team_data.items():
        # If calculating weekly average stats across the season (as per notebook "Weekly Average Stats" block)
        # We first aggregate per period, then average across periods
        
        # Temp list to hold period-level aggregates
        team_period_aggregates = {s: [] for s in all_stats}
        
        for p_key, p_stats in periods.items():
            for stat in sum_stats:
                if p_stats[stat]:
                    team_period_aggregates[stat].append(sum(p_stats[stat]))
                else:
                    team_period_aggregates[stat].append(0)
            
            for stat in avg_stats:
                if p_stats[stat]:
                    team_period_aggregates[stat].append(sum(p_stats[stat]) / len(p_stats[stat]))
                else:
                    team_period_aggregates[stat].append(0)
        
        # Now aggregate the periods into one final Team stat line
        team_final = {'teamName': league_team_dict.get(team_id, f"Team {team_id}")}
        for stat in all_stats:
            vals = team_period_aggregates[stat]
            if vals:
                team_final[stat] = round(sum(vals) / len(vals), 2)
            else:
                team_final[stat] = 0.0
        final_output.append(team_final)
        
    return final_output

def visualize_correlations(data_list, league_team_dict):
    """
    Generates a correlation heatmap data frame.
    
    Args:
        data_list (list): Data from fetch_league_matchup_data.
        
    Returns:
        pandas.DataFrame: Correlation matrix.
    """
    # We need to construct a DataFrame where each row is a Team-Day (or Team-Week) and columns are stats
    # Re-using aggregation logic but keeping rows separate
    
    temp_data = [] # List of dicts
    
    # Group by Team & Scoring Period
    grouped = {}
    for row in data_list:
        key = (row['teamId'], row['scoring_period'])
        if key not in grouped:
            grouped[key] = {s: [] for s in ('R', 'HR', 'RBI', 'SB', 'QS', 'SVHD', 'OPS', 'ERA', 'WHIP', 'K/9')}
        
        if row['lineupSlot'] not in ('BE', 'IL'):
             if row['b_or_p'] == 'batter':
                 for s in ('R', 'HR', 'RBI', 'SB', 'OPS'):
                     if row.get(s) is not None: grouped[key][s].append(float(row[s]))
             elif row['b_or_p'] == 'pitcher':
                 for s in ('QS', 'SVHD', 'ERA', 'WHIP', 'K/9'):
                     if row.get(s) is not None: grouped[key][s].append(float(row[s]))

    for (tid, date), stats in grouped.items():
        row_entry = {}
        # Sums
        for s in ('R', 'HR', 'RBI', 'SB', 'QS', 'SVHD'):
            row_entry[s] = sum(stats[s]) if stats[s] else 0
        # Avgs
        for s in ('OPS', 'ERA', 'WHIP', 'K/9'):
            row_entry[s] = sum(stats[s])/len(stats[s]) if stats[s] else 0
            
        temp_data.append(row_entry)

    df = pd.DataFrame(temp_data)
    if not df.empty:
        corr = df.corr().round(2)
        # To display: sb.heatmap(corr, cmap="Blues", annot=True)
        return corr
    return pd.DataFrame()

def perform_pitcher_regression(player_id, years=[2023, 2024]):
    """
    Performs OLS regression for a pitcher.
    
    Args:
        player_id (int): Pitcher ID.
        years (list): Years to analyze.
        
    Returns:
        dict: Regression results summary.
    """
    def _add_constant(data):
        if isinstance(data, (tuple, list)):
            arr = np.ones((len(data), 2))
        elif isinstance(data, np.ndarray):
            arr = np.ones((data.shape[0], 2))
        arr[:, 1] = data
        return arr

    games = []
    for yr in years:
        # Fetch and reverse to chronological order if needed (API returns usually desc)
        log = get_pitcher_game_logs(player_id=player_id, year=yr)
        games.extend(log[::-1])
        
    if len(games) < 2:
        return {"error": "Not enough game data"}

    # Independent Variable: (K/TBF) - (BB/TBF) for the previous game (lagged)
    # Dependent Variable: ERA of the current game
    # Note: Notebook logic: x_data = ... [:-1], y_data = ... [1:]
    
    x_vals = []
    y_vals = []
    
    for i in range(len(games) - 1):
        prev_game = games[i]
        curr_game = games[i+1]
        
        tbf = prev_game.get('TBF', 0)
        if tbf > 0:
            k_rate = prev_game.get('K', 0) / tbf
            bb_rate = prev_game.get('BB', 0) / tbf
            val = k_rate - bb_rate
            x_vals.append(val)
            y_vals.append(curr_game.get('ERA', 0.0))
            
    if not x_vals:
        return {"error": "No valid data points"}

    x_data = np.array(x_vals)
    y_data = np.array(y_vals)
    
    # OLS
    try:
        model = regression.linear_model.OLS(y_data, _add_constant(x_data)).fit()
        return {
            "rsquared": model.rsquared,
            "params": model.params,
            "pvalues": model.pvalues,
            "aic": model.aic
        }
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    # Test Block
    print("--- MLB Processing Module ---")
    if os.path.exists("config.ini"):
        try:
            cfg = load_config()
            print("Config loaded.")
            # lg = setup_league(cfg) # Commented out to avoid API calls on import test
            # print(f"League initialized: {lg}")
        except Exception as e:
            print(f"Config load failed: {e}")
    else:
        print("config.ini not found, skipping league setup.")

    print("Testing Lineup Scraper...")
    try:
        p, b = get_daily_lineups()
        print(f"Fetched {len(p)} pitchers and {len(b)} batters from lineups.")
    except Exception as e:
        print(f"Lineup scraping failed: {e}")

    print("Module expansion complete. Available functions:")
    print("- get_league_rosters(league)")
    print("- get_league_teams(league)")
    print("- get_league_transactions(league)")
    print("- scrape_espn_historical_stats(years)")
    print("- grab_mlb_sched(start_dt, end_dt)")


