import matplotlib; matplotlib.use('Agg')
import os, numpy as np, pandas as pd
import matplotlib.pyplot as plt

SEASON = 2025
ROLLING_WINDOW = 30
MIN_GAMES = 60
STREAK_THRESHOLD = 0.25
MIN_STREAK_LEN = 5
PHASE_GAMES = 3
RAMP_WINDOW = 5
SLOPE_THRESHOLD = 0.03
LEAD_WINDOW = 7
RAMP_LOOKBACK = 5
RAMP_LOOKAHEAD = 15

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
    df.loc[mask, 'Daily_Value'] += sign * ((sub[col] - dm) / ds).fillna(0)

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
    records, streak_id, i = [], 0, 0
    while i < len(labels):
        if labels[i] != 0:
            j = i
            while j < len(labels) and labels[j] == labels[i]: j += 1
            length = j - i
            if length >= MIN_STREAK_LEN:
                stype = 'hot' if labels[i] == 1 else 'cold'
                for k in range(length):
                    records.append({'espn_player_id': pid, 'game_idx': int(game_idx[i+k]),
                                    'streak_id': f"{pid}_{streak_id}", 'streak_type': stype,
                                    'pos_in_streak': k+1, 'streak_length': length})
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
streak_records = streak_records.merge(
    qualified[['espn_player_id', 'game_idx', 'deviation', 'playerName']],
    on=['espn_player_id', 'game_idx'], how='left'
)

# --- Ramp signal ---
_x = np.arange(RAMP_WINDOW, dtype=float)
def _rolling_slope(series):
    return series.rolling(RAMP_WINDOW, min_periods=RAMP_WINDOW).apply(
        lambda y: np.polyfit(_x, y, 1)[0], raw=True
    )

qualified['dev_slope'] = (
    qualified.sort_values(['espn_player_id', 'game_idx'])
    .groupby('espn_player_id')['deviation']
    .transform(_rolling_slope)
)
qualified['hot_ramp'] = ((qualified['deviation'] > 0) & (qualified['deviation'] < STREAK_THRESHOLD) & (qualified['dev_slope'] > SLOPE_THRESHOLD))
qualified['cold_ramp'] = ((qualified['deviation'] < 0) & (qualified['deviation'] > -STREAK_THRESHOLD) & (qualified['dev_slope'] < -SLOPE_THRESHOLD))
print(f"Hot ramp signals: {qualified['hot_ramp'].sum()}, Cold: {qualified['cold_ramp'].sum()}")

# --- Precision vs threshold ---
def compute_hit_rate(streak_type, slope_thresh):
    streak_starts = (
        streak_records[(streak_records['streak_type'] == streak_type) & (streak_records['pos_in_streak'] == 1)]
        [['espn_player_id', 'game_idx']].rename(columns={'game_idx': 'streak_start'})
    )
    sign = 1 if streak_type == 'hot' else -1
    signals = qualified[
        (qualified['deviation'].between(0, STREAK_THRESHOLD) if streak_type == 'hot'
         else qualified['deviation'].between(-STREAK_THRESHOLD, 0)) &
        (qualified['dev_slope'].abs() > slope_thresh) &
        (np.sign(qualified['dev_slope']) == sign)
    ][['espn_player_id', 'game_idx']].copy()
    if signals.empty: return np.nan, 0
    merged = signals.merge(streak_starts, on='espn_player_id', how='left')
    merged['gap'] = merged['streak_start'] - merged['game_idx']
    hit = merged[(merged['gap'] > 0) & (merged['gap'] <= LEAD_WINDOW)]
    hit_flags = signals.merge(
        hit.groupby(['espn_player_id', 'game_idx'])['gap'].min().reset_index(),
        on=['espn_player_id', 'game_idx'], how='left'
    )['gap'].notna()
    return hit_flags.mean(), len(signals)

thresholds = np.linspace(0.01, 0.10, 25)
results = {}
for t in thresholds:
    hp, hn = compute_hit_rate('hot', t)
    cp, cn = compute_hit_rate('cold', t)
    results[t] = {'hot_precision': hp, 'hot_n': hn, 'cold_precision': cp, 'cold_n': cn}
res_df = pd.DataFrame(results).T

hot_starts  = streak_records[(streak_records['streak_type']=='hot')  & (streak_records['pos_in_streak']==1)]
cold_starts = streak_records[(streak_records['streak_type']=='cold') & (streak_records['pos_in_streak']==1)]
baseline_hot  = len(hot_starts)  / len(qualified) * LEAD_WINDOW
baseline_cold = len(cold_starts) / len(qualified) * LEAD_WINDOW

plt.style.use('fivethirtyeight')
fig, axes = plt.subplots(1, 2, figsize=(13, 4), sharey=False)
for ax, stype, color, baseline in [
    (axes[0], 'hot', 'seagreen', baseline_hot),
    (axes[1], 'cold', 'firebrick', baseline_cold),
]:
    ax.plot(thresholds, res_df[f'{stype}_precision'], color=color, linewidth=2, label='Signal precision')
    ax2 = ax.twinx()
    ax2.bar(thresholds, res_df[f'{stype}_n'], width=0.003, alpha=0.2, color=color)
    ax2.set_ylabel('# Signals', fontsize=8)
    ax.axhline(baseline, color='black', linestyle='--', linewidth=1, label=f'Baseline ({baseline:.2f})')
    ax.set_title(f'{"Hot" if stype=="hot" else "Cold"} Ramp — Precision vs Slope Threshold')
    ax.set_xlabel('Slope Threshold'); ax.set_ylabel('Hit Rate'); ax.legend(fontsize=8, loc='upper left')
fig.suptitle('Early Ramp Signal Precision vs Slope Threshold', fontsize=12)
plt.tight_layout()
plt.savefig(r'C:\Users\peter.rigali\Desktop\acn_repo\fantasy_baseball\ramp_precision.png', dpi=150, bbox_inches='tight')
print('Saved precision chart.')

hp, hn = compute_hit_rate('hot', SLOPE_THRESHOLD)
cp, cn = compute_hit_rate('cold', SLOPE_THRESHOLD)
print(f"Hot  ramp at {SLOPE_THRESHOLD}: {hp:.1%} (n={hn})  baseline={baseline_hot:.1%}")
print(f"Cold ramp at {SLOPE_THRESHOLD}: {cp:.1%} (n={cn})  baseline={baseline_cold:.1%}")

# --- Event study ---
def build_ramp_windows(ramp_col):
    dev_lookup = qualified.set_index(['espn_player_id', 'game_idx'])['deviation']
    windows = []
    for _, row in qualified[qualified[ramp_col]][['espn_player_id', 'game_idx']].iterrows():
        pid, g0 = row['espn_player_id'], row['game_idx']
        entry = {}
        for t in range(-RAMP_LOOKBACK, RAMP_LOOKAHEAD + 1):
            try:    entry[t] = dev_lookup.loc[(pid, g0 + t)]
            except: entry[t] = np.nan
        windows.append(entry)
    return pd.DataFrame(windows)

hot_ramp_windows  = build_ramp_windows('hot_ramp')
cold_ramp_windows = build_ramp_windows('cold_ramp')
t_vals = list(range(-RAMP_LOOKBACK, RAMP_LOOKAHEAD + 1))

fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
for ax, windows, color, title in [
    (axes[0], hot_ramp_windows,  'seagreen',  f'Hot Ramp  (n={len(hot_ramp_windows):,})'),
    (axes[1], cold_ramp_windows, 'firebrick', f'Cold Ramp (n={len(cold_ramp_windows):,})'),
]:
    m = windows[t_vals].mean()
    s = windows[t_vals].sem()
    ax.plot(t_vals, m.values, color=color, linewidth=2.5)
    ax.fill_between(t_vals, (m-s).values, (m+s).values, color=color, alpha=0.2)
    ax.axvline(0, color='black', linewidth=1.2, linestyle='--', alpha=0.7, label='Signal day (t=0)')
    ax.axhline(0, color='black', linewidth=0.7, linestyle=':', alpha=0.5)
    ax.axhline( STREAK_THRESHOLD, color=color, linewidth=0.8, linestyle=':', alpha=0.6, label='Streak threshold')
    ax.axhline(-STREAK_THRESHOLD, color=color, linewidth=0.8, linestyle=':', alpha=0.6)
    ax.set_title(title); ax.set_xlabel('Games relative to signal day')
    ax.set_ylabel('Mean deviation'); ax.legend(fontsize=8)
fig.suptitle(f'Average Trajectory After Early Ramp Signal (slope > {SLOPE_THRESHOLD}/game)', fontsize=12)
plt.tight_layout()
plt.savefig(r'C:\Users\peter.rigali\Desktop\acn_repo\fantasy_baseball\ramp_event_study.png', dpi=150, bbox_inches='tight')
print('Saved event study.')

# --- Watchlist ---
latest_game = qualified.groupby('espn_player_id')['game_idx'].max().reset_index()
latest_stats = qualified.merge(latest_game, on=['espn_player_id', 'game_idx'])
id_to_name = qualified.drop_duplicates('espn_player_id').set_index('espn_player_id')['playerName']

for ramp_col, label, asc in [('hot_ramp', 'HOT', False), ('cold_ramp', 'COLD', True)]:
    watch = latest_stats[latest_stats[ramp_col]][['espn_player_id','game_idx','season_mean','rolling_avg','deviation','dev_slope']].copy()
    watch['Player'] = watch['espn_player_id'].map(id_to_name)
    watch = watch.sort_values('dev_slope', ascending=asc)[['Player','game_idx','season_mean','rolling_avg','deviation','dev_slope']]
    watch.columns = ['Player','Games Played','Season Mean','Rolling Avg','Deviation','Slope/Game']
    print(f"\n=== {label} RAMP WATCHLIST ({len(watch)} players) ===")
    print(watch.to_string(index=False, float_format=lambda x: f'{x:.3f}'))
