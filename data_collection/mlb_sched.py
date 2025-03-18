import requests
from bs4 import BeautifulSoup
import datetime
import time
from fantasy_baseball.functions import write_csv
from fantasy_baseball.universal import MONTH_DCT


def grab_mlb_sched(start_dt: str, end_dt: str) -> list:
    # Collect URL dates
    MLB_HEADERS = {'Connection': 'keep-alive', 'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'}
    start_dt = datetime.datetime.strptime(start_dt, '%Y-%m-%d').date()
    end_dt = datetime.datetime.strptime(end_dt, '%Y-%m-%d').date()
    num = (end_dt - start_dt).days
    dates = []
    for i in range(0, num):
        dt = start_dt + datetime.timedelta(days=i)
        if dt == end_dt:
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
            response = requests.get('https://www.mlb.com/schedule/' + dt, headers=MLB_HEADERS)
            soup = BeautifulSoup(response.text, 'html.parser')

            # Collect the table information.
            weekdays = [i.text for i in soup.find_all('div', attrs={'class': "ScheduleCollectionGridstyle__DateLabel-sc-c0iua4-5 iaVuoa"})]
            types = [i.text if i.text else 'Regular' for i in soup.find_all('div', attrs={'class': "ScheduleCollectionGridstyle__GameTypeLabel-sc-c0iua4-6 dTLQcW"})]

            game_dates = []
            for d in soup.find_all('div', attrs={'class': "ScheduleCollectionGridstyle__DateLabel-sc-c0iua4-5 fQIzmH"}):
                month, date = d.text.split(' ')
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
            for i, j in enumerate(weekdays):
                d = {'date': game_dates[i]['date'], 'weekday': weekdays[i], 'game_type': types[i]}
                for v in games[i]:
                    lst.append(dict(d)| v)

            # Tell me youre alive.
            for i in set(i['date'] for i in game_dates):
                print(f'Day completed ... ({i})')

    print(f'Number of games capture ... ({len(lst)})')
    return lst

if __name__ == '__main__':
    START_DATE = '2025-02-01'
    END_DATE = '2025-09-29'
    lst = grab_mlb_sched(start_dt=START_DATE, end_dt=END_DATE)
    write_csv(file_path='C:\\Users\\peter\\Desktop\\vscode\\main\\fantasy_baseball\\.data\\' + '2025_sched.csv', data=lst)