import unittest
from datetime import date

from zene_core.cogs.amlich import _normalize_hours, _render

HOURS_STRING = "Dần (3-5h), Mão (5-7h), Tỵ (9-11h), Thân (15-17h), Tuất (19-21h), Hợi (21-23h)"


class AmLichTests(unittest.TestCase):
    def test_auspicious_hours_string_is_split_into_lines(self) -> None:
        lines = _normalize_hours(HOURS_STRING)
        self.assertEqual(len(lines), 6)
        self.assertEqual(lines[0], "Dần (3-5h)")
        self.assertTrue(all(len(line) > 3 for line in lines))

    def test_auspicious_hours_other_shapes(self) -> None:
        self.assertEqual(_normalize_hours({"hours": HOURS_STRING})[0], "Dần (3-5h)")
        self.assertEqual(
            _normalize_hours([{"hour_name": "Dần", "time_range": "3-5h"}]),
            ["Dần 3-5h"],
        )
        self.assertEqual(_normalize_hours(""), [])

    def test_render_keeps_hours_on_single_lines(self) -> None:
        embed = _render(date(2026, 10, 15))
        field = next(f for f in embed.fields if "Giờ Hoàng Đạo" in f.name)
        parts = [line for line in field.value.splitlines() if line.strip()]
        self.assertGreaterEqual(len(parts), 4)
        self.assertTrue(all(len(line) > 3 for line in parts))
        self.assertNotIn("\nD\n", field.value)
