import unittest
from datetime import datetime
from unittest.mock import patch

import transport_helpers


class _FixedDateTime:
    @classmethod
    def now(cls):
        return datetime(2026, 1, 1, 0, 0)


class TransportHelpersRegressionTest(unittest.TestCase):
    def test_extract_route_stations_handles_recent_phrasing(self):
        origin, destination = transport_helpers.extract_route_stations("幫我查今天南港到嘉義最近的高鐵班次？")

        self.assertEqual((origin, destination), ("南港", "嘉義"))

    def test_timetable_rows_cover_both_directions(self):
        southbound_rows = transport_helpers._load_thsr_rows("southbound")
        northbound_rows = transport_helpers._load_thsr_rows("northbound")

        self.assertTrue(
            any("板橋" in row and "台中" in row for row in southbound_rows),
            "southbound timetable should include rows covering 板橋到台中",
        )
        self.assertTrue(
            any("台中" in row and "板橋" in row for row in northbound_rows),
            "northbound timetable should include rows covering 台中到板橋",
        )

    def test_build_thsr_reply_returns_trains_in_both_directions(self):
        with patch("transport_helpers.datetime", _FixedDateTime):
            southbound_reply = transport_helpers.build_thsr_reply("幫我查今天板橋到台中的高鐵？")
            northbound_reply = transport_helpers.build_thsr_reply("幫我查今天台中到板橋的高鐵？")

        self.assertIn("板橋到台中最近班次：", southbound_reply)
        self.assertIn("車次", southbound_reply)
        self.assertIn("台中到板橋最近班次：", northbound_reply)
        self.assertIn("車次", northbound_reply)


if __name__ == "__main__":
    unittest.main()