import datetime


def get_league_rosters(L, today_dt: datetime.date = None) -> list:
    """
    L: League Object

    Returns
    """
    if today_dt:
        today_dt = str(today_dt)

    league_teams_players = []
    for team in L.teams:
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
                # 'player_stats': player.stats,
                'player_total_points': player.total_points,
                }
            league_teams_players.append(player_dct)
        
    return league_teams_players


def get_league_teams(L, today_dt: datetime.date = None) -> list:
    """
    Inputs
    L: League Object

    Returns
    """
    if today_dt:
        today_dt = str(today_dt)

    league_teams = []
    for team in L.teams:
        team_dct = {
            'date': today_dt,
            'team_division_id': team.division_id,
            'team_division_name': team.division_name,
            'team_final_standing': team.final_standing,
            'team_logo_url': team.logo_url,
            'team_losses': team.losses,
            # 'team_owners': team.owners,
            'team_owner_display_name': team.owners[0]['displayName'],
            'team_owner_first_name': team.owners[0]['firstName'],
            'team_owner_last_name': team.owners[0]['lastName'],
            'team_owner_id': team.owners[0]['id'],
            # 'team_roster': team.roster,
            # 'team_schedule': team.schedule,
            'team_standing': team.standing,
            'team_abbrev': team.team_abbrev,
            'team_id': team.team_id,
            'team_name': team.team_name,
            'team_ties': team.ties,
            'team_wins': team.wins
            }
        league_teams.append(team_dct)
    return league_teams