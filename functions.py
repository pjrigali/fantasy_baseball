import os
import csv
from datetime import datetime, timedelta


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


