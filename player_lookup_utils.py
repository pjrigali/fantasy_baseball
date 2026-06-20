"""
Description:
    DEPRECATED shim. The two-file identity system (player_map.csv legacy schema +
    player_lookup.csv) has been replaced by a single source of truth,
    player_map.csv, loaded through player_map_utils.py. This module now forwards
    its old helpers to player_map_utils so any un-migrated consumer keeps working,
    while emitting a DeprecationWarning. Update imports to:

        from fantasy_baseball.player_map_utils import (
            get_mlbam_id, get_espn_id, get_mlb_name, get_b_or_p,
            espn_id_to_mlbam, mlbam_to_record,
        )

Source Data:
    - data-lake/01_Bronze/fantasy_baseball/player_map.csv (via player_map_utils)

Outputs:
    - In-memory helpers; no files written.
"""

import warnings

from fantasy_baseball.player_map_utils import (  # noqa: F401
    get_archive_name,
    get_espn_name,
    get_b_or_p,
    get_espn_id,
    get_statcast_id,
)

warnings.warn(
    "player_lookup_utils is deprecated; import from "
    "fantasy_baseball.player_map_utils instead (backed by the canonical "
    "player_map.csv).",
    DeprecationWarning,
    stacklevel=2,
)
