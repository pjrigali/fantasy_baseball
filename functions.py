import os
import csv
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