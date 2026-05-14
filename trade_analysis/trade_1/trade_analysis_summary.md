# Trade Analysis Summary: Corbin Carroll for Bryan Woo
*Generated: 2026-05-14*

---

## Trade Proposal

| Side | Gives | Receives |
|------|-------|----------|
| Your Friend | Bryan Woo (SP, SEA) | Corbin Carroll (OF, ARI) |

---

## Scoring System (Friend's League)

**Batting:** TB +1 · BB +1 · R +1 · RBI +1 · SB +1 · K **-1**

**Pitching:** IP ×3 · ER -2 · W +2 · L -2 · SV +5 · BS -1 · K +1 · H -1 · BB -1 · QS **+5** · HD +2

---

## Roster Snapshot (for verification)

### His Team

#### Batters (Active)
| Slot | Player | Team | Pos |
|------|--------|------|-----|
| C | W. Contreras | MIL | C, DH |
| 1B | V. Guerrero Jr. | TOR | 1B, DH |
| 2B | O. Albies | ATL | 2B |
| 3B | M. Garcia | KC | 3B |
| SS | M. Betts | LAD | SS |
| OF | C. DeLauter | CLE | OF, DH |
| OF | A. Pages | LAD | OF |
| OF | F. Tatis Jr. | SD | OF, 2B |
| UTIL | C. Benge | NYM | OF |
| UTIL | M. Harris II | ATL | OF |
| UTIL | J. Naylor | SEA | 1B, DH |
| UTIL | V. Pasquantino | KC | 1B, DH |

#### Batters (Bench / IL)
| Slot | Player | Team | Note |
|------|--------|------|------|
| BE | L. Arraez | SF | |
| BE | B. Bichette | NYM | |
| BE | B. Eldridge | SF | |
| BE | G. Torres | DET | IL10 |
| IL | J. Wilson | OAK | IL10 |

#### Pitchers (Active)
| Slot | Player | Team | Role |
|------|--------|------|------|
| P | B. Baker | TB | RP |
| P | K. Bradish | BAL | SP (flagged) |
| P | N. Eovaldi | TEX | SP (DTD) |
| P | B. Garrett | MIA | SP |
| P | P. Sewald | ARI | RP |
| P | **B. Woo** | **SEA** | **SP** |
| P | P. Skenes | PIT | SP |
| P | R. Suarez | BOS | SP |
| P | L. Varland | TOR | RP |
| P | D. Williams | NYM | RP |

#### Pitchers (Bench / IL)
| Slot | Player | Team | Note |
|------|--------|------|------|
| BE | G. Kirby | SEA | SP |
| BE | P. Lambert | HOU | RP/SP |
| BE | P. Messick | CLE | SP |
| BE | P. Tolle | BOS | SP |
| IL | M. Abel | MIN | IL15 |
| IL | E. Diaz | LAD | IL60 |

---

### Opponent Team

#### Batters (Active)
| Slot | Player | Team | Pos |
|------|--------|------|-----|
| C | A. Rutschman | BAL | C |
| 1B | B. Harper | PHI | 1B |
| 2B | N. Hoerner | CHC | 2B |
| 3B | J. Ramirez | CLE | 3B, DH |
| SS | F. Lindor | NYM | SS (IL10) |
| OF | T. Friedl | CIN | OF |
| OF | J. Lee | SF | OF |
| OF | J. McNeil | OAK | 2B, OF |
| UTIL | **C. Carroll** | **ARI** | **OF** |
| UTIL | Y. Diaz | TB | DH, 1B |
| UTIL | X. Edwards | MIA | 2B, SS |
| UTIL | F. Freeman | LAD | 1B |

#### Batters (Bench / IL)
| Slot | Player | Note |
|------|--------|------|
| BE | N. Schanuel | |

#### Pitchers (Active)
| Slot | Player | Team | Role |
|------|--------|------|------|
| P | A. Chapman | BOS | RP |
| P | J. deGrom | TEX | SP |
| P | S. Gray | BOS | SP |
| P | M. King | SD | SP |
| P | R. Lopez | ATL | SP |
| P | S. McClanahan | TB | SP |
| P | D. Rasmussen | TB | SP |
| P | S. Strider | ATL | SP |
| P | Z. Wheeler | PHI | SP |
| P | G. Williams | CLE | SP |

#### Pitchers (Bench / IL)
| Slot | Player | Note |
|------|--------|------|
| BE | J. Cantillo | RP/SP |
| BE | M. Gore | SP |
| BE | M. Kelly | SP |
| BE | R. Nelson | SP/RP |
| IL | H. Brown | IL60 |
| IL | G. Crochet | IL15 |
| IL | J. Hader | IL60 |

---

## Methodology

### Data Sources

| File | Used For |
|------|----------|
| `stats_mlb_daily_2023.csv` | Carroll & Woo 2023 per-game box scores |
| `stats_mlb_daily_2024.csv` | Carroll & Woo 2024 per-game box scores |
| `stats_mlb_daily_2025.csv` | Carroll & Woo 2025 per-game box scores |
| `stats_mlb_daily_2026.csv` | Carroll & Woo 2026 YTD per-game box scores |
| `player_batter_projections_2026.csv` | Carroll 2026 full-season projection |
| `player_pitcher_projections_2026.csv` | Woo 2026 full-season projection |

Players are matched by player_id (`682998` = Carroll, `693433` = Woo). The daily files use `playerId` in 2023–2025 and `player_id` in 2026 — both are handled.

### Fantasy Point Calculation

All points calculated via the league's exact scoring weights applied directly to per-game box score totals:

```
Batter:  TB(1) + BB(1) + R(1) + RBI(1) + SB(1) - K(1)

Pitcher: OUTS(1) + ER(-2) + W(2) + L(-2) + SV(5) + BS(-1)
       + K(1) + H(-1) + BB(-1) + QS(5) + HD(2)
       [OUTS = outs recorded; each out = 1 pt = IP × 3 pts total]
```

QS uses the actual `QS` column from each daily stats file for all years (2023–2026). QS for the 2026 projection file is estimated at 65% of GS (QS not included in that file).

### Projection File Notes

- `player_batter_projections_2026.csv` — UTF-8 BOM encoding, non-breaking spaces (`\xa0`) in player names. TB derived as `H + 2B + 2×3B + 3×HR`.
- `player_pitcher_projections_2026.csv` — no QS column; estimated at 65% of GS.

---

## Results

### Corbin Carroll — Fantasy Points by Year

| Year | G | TB | BB | R | RBI | SB | K | PTS | PTS/G |
|------|---|----|----|---|-----|----|---|-----|-------|
| 2023 | 155 | 286 | 57 | 116 | 76 | 54 | 125 | 464 | 3.0 |
| 2024 | 158 | 252 | 73 | 121 | 74 | 35 | 130 | 425 | 2.7 |
| 2025 | 143 | 305 | 67 | 107 | 84 | 32 | 153 | 442 | 3.1 |
| **2026 YTD** | 39 | 68 | 21 | 25 | 20 | 4 | 39 | 99 | 2.5 |
| 2026 Proj | ~145 | 270 | 66 | 101 | 83 | 34 | 131 | **423** | 2.9 |

### Bryan Woo — Fantasy Points by Year

| Year | G | IP | ER | W | L | K | H | BB | QS | PTS | PTS/G |
|------|---|----|----|---|---|---|---|----|----|-----|-------|
| 2023 | 18 | 87.7 | 41 | 4 | 5 | 93 | 75 | 31 | 4 | 186 | 10.3 |
| 2024 | 22 | 121.3 | 39 | 9 | 3 | 101 | 96 | 13 | 10 | 340 | 15.5 |
| 2025 | 30 | 186.7 | 61 | 15 | 7 | 198 | 137 | 36 | 21 | 584 | 19.5 |
| **2026 YTD** | 9 | 53.0 | 23 | 3 | 2 | 47 | 43 | 10 | 6 | 139 | 15.4 |
| 2026 Proj | ~31 | 186.6 | 71 | 13 | 9 | 188 | 157 | 40 | ~20 | **517** | 16.7 |

### Head-to-Head by Year

| Year | Carroll | Woo | Woo Advantage |
|------|---------|-----|---------------|
| 2023 | 464 | 186 | -278 (Woo partial season) |
| 2024 | 425 | 340 | -85 |
| 2025 | 442 | 584 | **+142** |
| 2026 YTD | 99 | 139 | +40 |
| 2026 Pace | 411 | 478 | +67 |
| 2026 Proj | 423 | 517 | **+94** |

### Key Context

- **2023:** Woo's partial MLB debut season (18 starts vs Carroll's full 155 games) — not a fair comparison
- **2024:** Woo closed the gap significantly (+22 starts, 15.5 pts/start). Carroll had his worst season (.231 AVG)
- **2025:** Woo broke out as a true ace (2.94 ERA, 21 QS, 584 pts). Carroll bounced back (31 HR, 32 SB, 442 pts)
- **2026 trend:** Carroll's SB pace (4 in 39 G vs 32 in 143 G in 2025) is the biggest red flag. Woo is healthy and on a consistent 15+ pts/start pace
- **Roster context:** Friend has Bradish (flagged), Eovaldi (DTD), Abel (IL15), Diaz (IL60) — Woo is a linchpin of the rotation

### Verdict: **Decline the trade**

Woo projects ~94 points ahead of Carroll over a full season in this scoring format, and the trajectory confirms it — the gap has been widening as Woo accumulates starts. The friend's roster needs pitching, not outfield depth.

---

*Analysis script:* `fantasy_baseball/temp_trade_analysis/analyze_trade_carroll_woo.py`
