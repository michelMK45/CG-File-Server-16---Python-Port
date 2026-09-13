from __future__ import annotations

import unittest

from server16_py.fifa_db import FifaDatabase


class LeagueLookupTests(unittest.TestCase):
    """FifaDatabase's league accessors are plain dict lookups over caches
    populated by connect() -- these tests set the caches directly so the
    filtering logic used by TeamPickerDialog is verifiable without a live
    32-bit DB bridge or a Tk event loop."""

    def setUp(self) -> None:
        self.db = FifaDatabase("C:/fake-fifa-root")
        self.db.team_cache = {
            "1": "Arsenal",
            "2": "Chelsea",
            "3": "Real Madrid",
            "4": "Barcelona",
        }
        self.db.league_cache = {
            "10": "Premier League",
            "20": "La Liga",
        }
        self.db.team_league_cache = {
            "1": "10",
            "2": "10",
            "3": "20",
            "4": "20",
        }

    def test_get_league_name_known_id(self) -> None:
        self.assertEqual(self.db.get_league_name("10"), "Premier League")

    def test_get_league_name_unknown_id_is_none(self) -> None:
        self.assertIsNone(self.db.get_league_name("999"))

    def test_get_team_league_id(self) -> None:
        self.assertEqual(self.db.get_team_league_id("3"), "20")
        self.assertIsNone(self.db.get_team_league_id("999"))

    def test_leagues_sorted_orders_by_name(self) -> None:
        self.assertEqual(
            self.db.leagues_sorted(),
            [("20", "La Liga"), ("10", "Premier League")],
        )

    def test_teams_in_league_returns_matching_ids_only(self) -> None:
        self.assertEqual(self.db.teams_in_league("10"), {"1", "2"})
        self.assertEqual(self.db.teams_in_league("20"), {"3", "4"})

    def test_teams_in_league_unknown_league_is_empty(self) -> None:
        self.assertEqual(self.db.teams_in_league("999"), set())

    def test_empty_caches_degrade_to_empty_results(self) -> None:
        empty_db = FifaDatabase("C:/fake-fifa-root")
        self.assertEqual(empty_db.leagues_sorted(), [])
        self.assertEqual(empty_db.teams_in_league("10"), set())
        self.assertIsNone(empty_db.get_league_name("10"))
        self.assertIsNone(empty_db.get_team_league_id("1"))


if __name__ == "__main__":
    unittest.main()
