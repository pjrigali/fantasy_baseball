# Section H — Opportunity Graph (Lineup Dependency)

Flags structural opportunity changes — lineup promotions and bullpen-role cascades — that raise a player's value before their own stats move.

## Batters — Lineup Promotion / Top-of-Order

- Flag = moved up >=1 lineup slot in last 7d, or >=60% of starts batting in the top 3. Flagged: **37** (of which 24 were promotions).

| Precision | Recall | F1 | Lift | tp | fp | fn |
|-----------|--------|----|------|----|----|----|
| 0.71 | 0.50 | 0.59 | 1.42 | 17 | 7 | 17 |

## Pitchers — Saves Opportunity Cascade

- Joined to closers-depth chart by name; **118** of 122 pitcher pickups had bullpen-role context.
- Flag = closer/setup/high-leverage role or >=1 recent save+hold. Flagged: **31**.

| Precision | Recall | F1 | Lift | tp | fp | fn |
|-----------|--------|----|------|----|----|----|
| 0.62 | 0.42 | 0.50 | 1.24 | 13 | 8 | 18 |

## Platoon Detection — Limitation

The data lake has no per-game batter-handedness or opposing-pitcher-hand splits, so platoon-partner opportunity (a partner hitting the IL freeing full-time at-bats) cannot be derived. Deferred until handedness splits are collected.
