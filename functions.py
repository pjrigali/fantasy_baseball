import os
import csv
import requests
from datetime import datetime, timedelta
from pybaseball import playerid_lookup


def get_weeks(start_dt, end_dt) -> list:

    if isinstance(start_dt, str):
        start_dt = datetime.strptime(start_dt, '%Y-%m-%d')
    if isinstance(end_dt, str):
        end_dt = datetime.strptime(end_dt, '%Y-%m-%d')

    # Find the first Monday on or after the start_date
    days_to_monday = (7 - start_dt.weekday()) % 7  # Monday is weekday 0
    first_monday = start_dt + timedelta(days=days_to_monday)

    # Generate all Mondays up to the end_date
    weeks = []
    while first_monday <= end_dt:
        weeks.append((first_monday, first_monday + timedelta(days=6)))
        first_monday += timedelta(days=7)
    return weeks


def read_csv(file_name: str) -> list:
    temp = []
    with open(file_name, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=',')
        for i in reader:
            d = {}
            for k, v in i.items():
                if k.startswith('\ufeff'):
                    k = k.replace('\ufeff', '')
                if k.startswith('"') and k.endswith('"'):
                    k = k.replace('"', '')
                d[k] = v
            temp.append(d)
    return temp


def write_csv(file_path: str, data: list, sort_cols: bool = True) -> None:
    file_exists = os.path.exists(file_path)

    with open(file_path, mode='a', encoding='utf-8', newline='') as file:
        cols = set()
        for r in data:
            for k, v in r.items():
                if k not in cols:
                    cols.add(k)
        cols = list(cols)

        if sort_cols: 
            cols.sort()

        writer = csv.DictWriter(file, fieldnames=cols)
        
        if not file_exists:
            writer.writeheader()

        writer.writerows(data)
    return None


def update_player_map() -> list:
    players = read_csv(file_name=BB_DATA_LOCATION + 'league_teams_players.csv')
    existing_players = read_csv(file_name=BB_DATA_LOCATION + 'player_map.csv')
    player_name_set = set(i['full_name'] for i in existing_players)
    player_lst = []
    for i in players:
        if i['player_name'] not in player_name_set:
            player_name_set.add(i['player_name'])
            player_lst.append(i)

    temp = []
    for i in player_lst:
        if 'Jr.' in i['player_name'] or 'II' in i['player_name']:
            i['player_name'] = i['player_name'].replace(' Jr.', '').replace('II', '')

        player_name_lst = i['player_name'].split(' ')
        if len(player_name_lst) == 2:
            first, last = player_name_lst[0], player_name_lst[1]
        elif len(player_name_lst) > 2:
            first, second = player_name_lst[0], ' '.join(player_name_lst[1:])
        else:
            print(i['player_name'])

        player_id_lookup = playerid_lookup(last=last, first=first)
        statcast_player_id = ''
        if not player_id_lookup.empty:
            statcast_player_id = str(player_id_lookup['key_mlbam'][0])
        elif len(player_id_lookup) > 1:
            print(i['player_name'])
        
        temp.append({'full_name': i['player_name'], 'first_name': first, 'last_name': last, 'espn_player_id': i['player_id'], 'statcast_player_id': statcast_player_id, 'player_pro_team': i['player_pro_team'], 'player_eligible_slots': i['player_eligible_slots']})

    write_csv(file_path=BB_DATA_LOCATION + 'player_map.csv', data=temp)

    return temp


def json_parsing(obj, key):
    """Recursively pull values of specified key from nested JSON."""
    arr = []

    def extract(obj, arr, key):
        """Return all matching values in an object."""
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


# Collect Game Logs and Game stats.
def get_pitcher_game_logs(playerId: int, year: int = 2025) -> list:
    url = f"https://site.web.api.espn.com/apis/common/v3/sports/baseball/mlb/athletes/{playerId}/gamelog?region=us&lang=en&contentorigin=espn&season={year}&category=pitching"
    response = requests.get(url, headers=ESPN_HEADERS).json()

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
                d = dict(zip(['IP', 'H', 'R', 'ER', 'HR', 'BB', 'K', 'GB', 'FB', 'P', 'TBF', 'GSC', 'DEC', 'REL', 'ERA'], j['stats']))

                for k, v in d.items():
                    if k in ('IP', 'GSC', 'ERA'):
                        d[k] = float(v)
                    elif k in ('H', 'R', 'ER', 'HR', 'BB', 'K', 'GB', 'FB', 'P', 'TBF'):
                        d[k] = int(v)
                if d['IP'] == 0.0:
                    d['IP'] = 1.0
                d['WHIP'] = round((d['BB'] + d['H']) / d['IP'], 2)
                d['K/9'] = round((d['K'] / d['IP']) * 9, 2)
                
                game_log.append(game_log.append({'playerId': playerId, 'year': year} | game_info[j['eventId']] | d))
    return game_log


def get_batter_game_logs(playerId: int, year: int = 2025) -> list:
    url = f"https://site.web.api.espn.com/apis/common/v3/sports/baseball/mlb/athletes/{playerId}/gamelog?region=us&lang=en&contentorigin=espn&season={year}&category=batting"
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
                d = dict(zip(['AB', 'R', 'H', '2B', '3B', 'HR', 'RBI', 'BB', 'HBP', 'SO', 'SB', 'CS', 'AVG', 'OBP', 'SLG', 'OPS'], j['stats']))

                for k, v in d.items():
                    if k in ('AVG', 'OBP', 'SLG', 'OPS'):
                        d[k] = float(v)
                    else:
                        d[k] = int(v)

                game_log.append({'playerId': playerId, 'year': year} | game_info[j['eventId']] | d)
    return game_log


def remove_none(lst: list) -> list:
    """i mean im sure theres a simpler way."""
    return [i for i in lst if i != None]