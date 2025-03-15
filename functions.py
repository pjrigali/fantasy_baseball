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
