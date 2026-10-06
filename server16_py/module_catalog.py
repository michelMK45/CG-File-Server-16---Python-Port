from __future__ import annotations

# Dashboard "Modules" card: the ini names ([<name>] Modules=0/1 in FSW/settings.ini),
# grouped by the category label shown above each group. One source for the card
# layout (app_ui), the translated labels (app_localization) and the names loaded
# from settings.ini (app_settings), so a new module only has to be added here.
MODULE_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("stadium", ("Stadium", "EntranceCam", "Goalposts", "StadiumNet")),
    ("ui", ("TvLogo", "ScoreBoard", "StadiumName", "Movies")),
    ("sound", ("Chants", "AwayChants", "AwayClubSong", "TeamEntrance", "TournamentEntrance")),
    ("game", ("Ball", "Adboard", "Referee", "Wipe")),
    ("other", ("Autorun", "DiscordRPC")),
)

# ini name -> locale slug: label key is "module.<slug>", tooltip key is
# "tooltip.module.<slug>" (see module_label_key / module_tooltip_key).
MODULE_SLUGS: dict[str, str] = {
    "Stadium": "stadium",
    "EntranceCam": "entrance_cam",
    "Goalposts": "goalposts",
    "StadiumNet": "stadiumnet",
    "TvLogo": "tvlogo",
    "ScoreBoard": "scoreboard",
    "StadiumName": "stadium_name",
    "Movies": "movies",
    "Chants": "chants",
    "AwayChants": "away_chants",
    "AwayClubSong": "away_club_song",
    "TeamEntrance": "team_entrance",
    "TournamentEntrance": "tournament_entrance",
    "Ball": "ball",
    "Adboard": "adboard",
    "Referee": "referee",
    "Wipe": "wipe",
    "Autorun": "autorun",
    "DiscordRPC": "discord_rpc",
}

# DiscordRPC is not read from this list: its state also lives in settings.json
# (see SettingsMixin._load_module_states), so it is handled on its own there.
INI_MODULE_NAMES: tuple[str, ...] = tuple(
    name for _category, names in MODULE_CATEGORIES for name in names if name != "DiscordRPC"
)


def module_label_key(name: str) -> str:
    return f"module.{MODULE_SLUGS[name]}"


def module_tooltip_key(name: str) -> str:
    return f"tooltip.module.{MODULE_SLUGS[name]}"


def module_category_key(category: str) -> str:
    return f"module.category.{category}"
