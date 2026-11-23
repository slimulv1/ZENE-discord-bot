import unittest
from datetime import date

from zene_core.cogs.amlich import _conflict_lines, _normalize_hours, _render

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

    def test_conflict_covers_full_cycle(self) -> None:
        conflict = {
            "conflict_chi": "Mùi",
            "conflicting_ages": [
                {"age": 59, "can_chi": "Đinh Mùi*"},
                {"age": 23, "can_chi": "Quý Mùi*"},
            ],
        }
        lines = _conflict_lines(conflict, 2026)
        self.assertEqual(
            lines,
            [
                "Tuổi 11 : Ất Mùi",
                "Tuổi 23 : Quý Mùi (*)",
                "Tuổi 35 : Tân Mùi",
                "Tuổi 47 : Kỷ Mùi",
                "Tuổi 59 : Đinh Mùi (*)",
                "Tuổi 71 : Ất Mùi",
                "Tuổi 83 : Quý Mùi",
                "Tuổi 95 : Tân Mùi",
            ],
        )

    def test_library_confirmed_ages_are_marked(self) -> None:
        lines = _conflict_lines(
            {
                "conflict_chi": "Mùi",
                "conflicting_ages": [
                    {"can_chi": "Đinh Mùi*", "age": 59},
                    {"can_chi": "Quý Mùi*", "age": 23},
                ],
            },
            2026,
        )
        self.assertIn("Tuổi 23 : Quý Mùi (*)", lines)
        self.assertIn("Tuổi 59 : Đinh Mùi (*)", lines)
        # 83 is also Quý Mùi but is NOT the age the library confirmed.
        self.assertIn("Tuổi 83 : Quý Mùi", lines)
        self.assertNotIn("Tuổi 83 : Quý Mùi (*)", lines)
        self.assertNotIn("Tuổi 11 : Ất Mùi (*)", lines)

    def test_rule_b_age_is_appended(self) -> None:
        lines = _conflict_lines(
            {
                "conflict_chi": "Dậu",
                "conflicting_ages": [
                    {"age": 8, "can_chi": "Đinh Dậu*"},
                    {"age": 26, "can_chi": "Kỷ Mão"},
                ],
            },
            2026,
        )
        self.assertIn("Tuổi 26 : Kỷ Mão (*) [xung phụ]", lines)

    def test_no_library_conflict_returns_no_lines(self) -> None:
        self.assertEqual(_conflict_lines({"conflict_chi": "Mùi", "conflicting_ages": []}, 2026), [])

    def test_ages_use_lunar_year_near_tet(self) -> None:
        # Solar 10-02-2026 is still lunar year 2025 (Ất Tỵ).
        embed = _render(date(2026, 2, 10))
        field = next(f for f in embed.fields if "Tuổi Xung" in f.name)
        self.assertIn("Tuổi 8 : Đinh Dậu (*)", field.value)
        self.assertNotIn("Tuổi 9 : Đinh Dậu", field.value)

    def test_render_conflict_field(self) -> None:
        # Solar 23-11-2026 = lunar 15-10-2026 in the reported screenshot.
        embed = _render(date(2026, 11, 23))
        field = next(f for f in embed.fields if "Tuổi Xung" in f.name)
        self.assertIn("(Lục xung - cùng chi)", field.name)
        self.assertIn("Tuổi 11 : Ất Mùi", field.value)
        self.assertIn("Tuổi 23 : Quý Mùi (*)", field.value)
        self.assertIn("Tuổi 59 : Đinh Mùi (*)", field.value)
        self.assertNotIn("Tuổi 83 : Quý Mùi (*)", field.value)
        self.assertIn("Tuổi 95 : Tân Mùi", field.value)
        self.assertIn("(*) Xung theo Nạp Âm", field.value)

    def test_leap_month_is_labelled(self) -> None:
        # Solar 25-07-2025 = lunar 1/6/2025, leap month.
        self.assertIn("nhuận", _render(date(2025, 7, 25)).title)
        self.assertNotIn("nhuận", _render(date(2026, 11, 23)).title)

    def test_render_keeps_hours_on_single_lines(self) -> None:
        embed = _render(date(2026, 10, 15))
        field = next(f for f in embed.fields if "Giờ Hoàng Đạo" in f.name)
        parts = [line for line in field.value.splitlines() if line.strip()]
        self.assertGreaterEqual(len(parts), 4)
        self.assertTrue(all(len(line) > 3 for line in parts))
        self.assertNotIn("\nD\n", field.value)
