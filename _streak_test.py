import matplotlib; matplotlib.use('Agg')
import os, numpy as np, pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

SEASON = 2025
ROLLING_WINDOW = 30
MIN_GAMES = 60
STREAK_THRESHOLD = 0.25
MIN_STREAK_LEN = 5
PHASE_GAMES = 3
LOOKBACK = 10
LOOKAHEAD = 20

PROJECT_ROOT = r'C:\Users\peter.rigali\Desktop\acn_repo'
BASE_PATH = os.path.join(PROJECT_ROOT, 'data-lake', '01_Bronze', 'fantasy_baseball')

stats_df = pd.read_csv(os.path.join(BASE_PATH, f'stats_mlb_daily_{SEASON}.csv'))
player_map_df = pd.read_csv(os.path.join(BASE_PATH, 'player_map.csv'))
stats_df['date'] = pd.to_datetime(stats_df['date'])
stats_df['playerId'] = stats_df['playerId'].astype(str)
player_map_df['espn_player_id'] = player_map_df['espn_player_id'].astype(str)
player_map_df['statcast_player_id'] = player_map_df['statcast_player_id'].astype(str).str.replace(r'\.0$', '', regex=True)
stats_merged = stats_df.merge(player_map_df, left_on='playerId', right_on='statcast_player_id', how='left')

batter_stats = ['R', 'HR', 'RBI', 'SB']

def _add_daily_zscore(df, col, mask, sign=1.0):
    if col not in df.columns: return
    sub = df.loc[mask]
    dm = sub.groupby('date')[col].transform('mean')
    ds = sub.groupby('date')[col].transform('std').replace(0, np.nan).fillna(1)
    z = ((sub[col] - dm) / ds).fillna(0)
    df.loc[mask, 'Daily_Value'] += sign * z

daily = stats_merged.copy()
daily['Daily_Value'] = 0.0
mask_b = daily['b_or_p'] == 'batter'
for col in batter_stats:
    _add_daily_zscore(daily, col, mask_b)
daily = daily[mask_b].copy()

player_daily = (
    daily[['date', 'espn_player_id', 'playerName', 'Daily_Value']]
    .groupby(['date', 'espn_player_id', 'playerName']).sum().reset_index()
    .dropna(subset=['Daily_Value'])
)
player_daily = player_daily.sort_values(['espn_player_id', 'date'])
player_daily['game_idx'] = player_daily.groupby('espn_player_id').cumcount()
games_played = player_daily.groupby('espn_player_id')['game_idx'].max().rename('games_played')
player_daily = player_daily.join(games_played, on='espn_player_id')

qualified = player_daily[player_daily['games_played'] >= MIN_GAMES].copy()
season_mean = qualified.groupby('espn_player_id')['Daily_Value'].mean().rename('season_mean')
qualified = qualified.join(season_mean, on='espn_player_id')
qualified['rolling_avg'] = (
    qualified.groupby('espn_player_id')['Daily_Value']
    .transform(lambda x: x.rolling(ROLLING_WINDOW, min_periods=10).mean())
)
qualified['deviation'] = qualified['rolling_avg'] - qualified['season_mean']

def find_streaks(pid, player_df):
    dev = player_df['deviation'].values
    game_idx = player_df['game_idx'].values
    labels = np.where(dev > STREAK_THRESHOLD, 1, np.where(dev < -STREAK_THRESHOLD, -1, 0))
    records = []
    streak_id = 0
    i = 0
    while i < len(labels):
        if labels[i] != 0:
            j = i
            while j < len(labels) and labels[j] == labels[i]:
                j += 1
            length = j - i
            if length >= MIN_STREAK_LEN:
                stype = 'hot' if labels[i] == 1 else 'cold'
                for k in range(length):
                    records.append({
                        'espn_player_id': pid,
                        'game_idx': int(game_idx[i + k]),
                        'streak_id': f"{pid}_{streak_id}",
                        'streak_type': stype,
                        'pos_in_streak': k + 1,
                        'streak_length': length,
                    })
                streak_id += 1
            i = j
        else:
            i += 1
    return pd.DataFrame(records)

sorted_q = qualified.sort_values(['espn_player_id', 'game_idx'])
streak_records = pd.concat(
    [find_streaks(pid, grp) for pid, grp in sorted_q.groupby('espn_player_id')],
    ignore_index=True
)

def assign_phase(row):
    if row['pos_in_streak'] <= PHASE_GAMES: return 'start'
    if row['pos_in_streak'] > row['streak_length'] - PHASE_GAMES: return 'end'
    return 'mid'

streak_records['phase'] = streak_records.apply(assign_phase, axis=1)
streak_records = streak_records.merge(
    qualified[['espn_player_id', 'game_idx', 'deviation', 'playerName']],
    on=['espn_player_id', 'game_idx'], how='left'
)

print(f"Total qualifying streaks: {streak_records['streak_id'].nunique()}")
print(streak_records.groupby(['streak_type', 'phase']).size().unstack(fill_value=0))

streak_lengths = streak_records.drop_duplicates('streak_id')[['streak_id', 'streak_type', 'streak_length']]

plt.style.use('fivethirtyeight')

# Chart 1: Streak length distribution
fig, axes = plt.subplots(1, 2, figsize=(13, 4), sharey=True)
for ax, stype, color in zip(axes, ['hot', 'cold'], ['seagreen', 'firebrick']):
    lengths = streak_lengths[streak_lengths['streak_type'] == stype]['streak_length']
    ax.hist(lengths, bins=range(MIN_STREAK_LEN, lengths.max() + 2), color=color, alpha=0.75, edgecolor='white')
    ax.axvline(lengths.median(), color='black', linestyle='--', linewidth=1.2, label=f'Median: {lengths.median():.0f}g')
    ax.axvline(lengths.mean(),   color='black', linestyle=':',  linewidth=1.2, label=f'Mean: {lengths.mean():.1f}g')
    ax.set_title(f'{"Hot" if stype == "hot" else "Cold"} Streak Lengths  (n={len(lengths)})')
    ax.set_xlabel('Streak Length (games)')
    ax.set_ylabel('Count')
    ax.legend(fontsize=8)
fig.suptitle('Distribution of Streak Lengths — Qualified Batters (2025)', fontsize=12)
plt.tight_layout()
plt.savefig(r'C:\Users\peter.rigali\Desktop\acn_repo\fantasy_baseball\streak_distribution.png', dpi=150, bbox_inches='tight')
print('Saved distribution.')

# Chart 2: Survival curve
max_len = streak_lengths['streak_length'].max()
fig, ax = plt.subplots(figsize=(10, 5))
for stype, color, label in [('hot', 'seagreen', 'Hot'), ('cold', 'firebrick', 'Cold')]:
    lengths = streak_lengths[streak_lengths['streak_type'] == stype]['streak_length'].values
    survival = [np.mean(lengths >= n) for n in range(MIN_STREAK_LEN, max_len + 1)]
    x = list(range(MIN_STREAK_LEN, max_len + 1))
    ax.plot(x, survival, color=color, linewidth=2, label=label)
    ax.fill_between(x, survival, alpha=0.12, color=color)
ax.axhline(0.5, color='black', linestyle='--', linewidth=0.8, alpha=0.5, label='50% survival')
ax.set_title('Streak Survival Curve — P(streak lasts >= N games)')
ax.set_xlabel('Streak Length (games)')
ax.set_ylabel('Proportion of Streaks Surviving')
ax.legend()
plt.tight_layout()
plt.savefig(r'C:\Users\peter.rigali\Desktop\acn_repo\fantasy_baseball\streak_survival.png', dpi=150, bbox_inches='tight')
print('Saved survival.')

# Chart 3: Event study
def build_event_windows(streak_records, qualified, anchor='start'):
    dev_lookup = qualified.set_index(['espn_player_id', 'game_idx'])['deviation']
    windows = []
    for sid, grp in streak_records.groupby('streak_id'):
        grp = grp.sort_values('pos_in_streak')
        stype = grp['streak_type'].iloc[0]
        pid = grp['espn_player_id'].iloc[0]
        if anchor == 'start':
            anchor_game = grp[grp['pos_in_streak'] == 1]['game_idx'].iloc[0]
        else:
            anchor_game = grp[grp['pos_in_streak'] == grp['streak_length'].max()]['game_idx'].iloc[0]
        row = {'streak_id': sid, 'streak_type': stype}
        for t in range(-LOOKBACK, LOOKAHEAD + 1):
            g = anchor_game + t
            try: row[t] = dev_lookup.loc[(pid, g)]
            except KeyError: row[t] = np.nan
        windows.append(row)
    return pd.DataFrame(windows)

start_windows = build_event_windows(streak_records, qualified, anchor='start')
end_windows   = build_event_windows(streak_records, qualified, anchor='end')
t_vals = list(range(-LOOKBACK, LOOKAHEAD + 1))

fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
for ax, windows, title in [
    (axes[0], start_windows, 'Anchored on Streak START (t=0 = first game)'),
    (axes[1], end_windows,   'Anchored on Streak END   (t=0 = last game)'),
]:
    for stype, color, label in [('hot', 'seagreen', 'Hot'), ('cold', 'firebrick', 'Cold')]:
        sub = windows[windows['streak_type'] == stype][t_vals]
        mean_traj = sub.mean()
        sem_traj  = sub.sem()
        ax.plot(t_vals, mean_traj.values, color=color, linewidth=2, label=label)
        ax.fill_between(t_vals, (mean_traj - sem_traj).values, (mean_traj + sem_traj).values, color=color, alpha=0.15)
    ax.axvline(0, color='black', linewidth=1.2, linestyle='--', alpha=0.7, label='Anchor (t=0)')
    ax.axhline(0, color='black', linewidth=0.7, linestyle=':', alpha=0.5)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel('Games relative to anchor')
    ax.set_ylabel('Mean deviation from season avg')
    ax.legend(fontsize=8)
fig.suptitle('Event Study: Deviation Trajectory Around Streak Start vs End', fontsize=12)
plt.tight_layout()
plt.savefig(r'C:\Users\peter.rigali\Desktop\acn_repo\fantasy_baseball\streak_event_study.png', dpi=150, bbox_inches='tight')
print('Saved event study.')
