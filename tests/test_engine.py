"""Engine tests for reno-forge."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine  # noqa: E402

SAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")

BATHROOM = """Project: Bathroom floor retile

Type: bathroom
Total area: 60 sqft
Budget: $1,450
Tax: 8.25%
Contingency: 10%

Scope:
- Remove existing vinyl tile: 60 sqft
- Install cement backer board: 60 sqft
- Install 12x12 porcelain tile: 60 sqft
- Grout and clean the floor: 60 sqft

Materials:
- Porcelain tile 12x12 @ $2.35 /sqft
- Cement board 3x4 @ $14.50 /sheet
- Thinset mortar 25 lb @ $18.00 /bag
- Grout premixed 5 lb @ $12.00 /tub

Tools:
- Wet tile saw
- Notched trowel
- Grout float
"""


def sample(name):
    with open(os.path.join(SAMPLES, name), encoding="utf-8") as fh:
        return fh.read()


class ParseTests(unittest.TestCase):
    def test_extract_qty_units(self):
        self.assertEqual(engine.extract_qty("Install tile: 60 sqft")[:2], (60.0, "sqft"))
        self.assertEqual(engine.extract_qty("Baseboard: 18 linear ft")[:2], (18.0, "lf"))
        self.assertEqual(engine.extract_qty("Tile 12x12")[:2], (None, None))
        self.assertEqual(engine.extract_qty("Screws 800")[:2], (800.0, None))
        self.assertEqual(engine.extract_qty("Area: 6 sqm")[:2], (6.0, "sqm"))

    def test_material_line_parsing(self):
        row = engine.parse_material_line("Porcelain tile 12x12 @ $2.35 /sqft")
        self.assertEqual(row["name"], "Porcelain tile 12x12")
        self.assertEqual(row["price"], 2.35)
        self.assertEqual(row["basis"], "sqft")
        self.assertIsNone(row["qty"])

        row2 = engine.parse_material_line("Cement board 3x4 @ $14.50 /sheet")
        self.assertEqual(row2["name"], "Cement board 3x4")
        self.assertEqual(row2["basis"], "sheet")

    def test_brief_fields(self):
        brief = engine.parse_brief(BATHROOM)
        self.assertEqual(brief["project_name"], "Bathroom floor retile")
        self.assertEqual(brief["project_type"], "bathroom")
        self.assertEqual(brief["area_sqft"], 60.0)
        self.assertEqual(brief["budget"], 1450.0)
        self.assertAlmostEqual(brief["tax_pct"], 0.0825)
        self.assertAlmostEqual(brief["contingency_pct"], 0.10)
        self.assertEqual(len(brief["scope_items"]), 4)

    def test_demo_lines_are_flagged(self):
        brief = engine.parse_brief(BATHROOM)
        demo = [s for s in brief["scope_items"] if s["demo"]]
        self.assertEqual(len(demo), 1)


class TakeoffTests(unittest.TestCase):
    def setUp(self):
        self.result = engine.analyse(BATHROOM)
        self.rows = {r["material_id"]: r for r in self.result["takeoff"]["rows"]}

    def test_tile_quantity_comes_from_scope(self):
        tile = self.rows["tile"]
        self.assertEqual(tile["need"], 60.0)
        self.assertEqual(tile["need_unit"], "sqft")
        self.assertIn("scope", tile["need_source"])
        self.assertEqual(tile["packs_to_buy"], 6)          # 66 sqft with waste / 12 sqft boxes
        self.assertAlmostEqual(tile["cost"], 60 * 1.10 * 2.35, places=2)

    def test_container_price_basis_uses_pack_count(self):
        board = self.rows["backer"]
        self.assertEqual(board["packs_to_buy"], 6)
        self.assertAlmostEqual(board["cost"], 6 * 14.50, places=2)

    def test_companion_material_follows_the_tile_area(self):
        thinset = self.rows["thinset"]
        self.assertEqual(thinset["need"], 60.0)
        self.assertIn("companion", thinset["need_source"])

    def test_missing_price_is_flagged(self):
        result = engine.analyse("Project: Test\n\nMaterials:\n- Some tile\n")
        ids = [f["id"] for f in result["findings"]]
        self.assertIn("missing_price", ids)

    def test_no_area_is_flagged(self):
        result = engine.analyse("Project: Test\n\nMaterials:\n- Some tile @ $2.00 /sqft\n")
        ids = [f["id"] for f in result["findings"]]
        self.assertIn("no_area", ids)


class CostTests(unittest.TestCase):
    def test_total_includes_tax_and_contingency(self):
        result = engine.analyse(BATHROOM)
        cost = result["cost"]
        expected = (cost["material_total"] + cost["labor"]) * 1.10 * 1.0825
        self.assertAlmostEqual(cost["total"], expected, places=2)
        self.assertLess(cost["total"], cost["budget"])

    def test_over_budget_is_flagged(self):
        result = engine.analyse(BATHROOM.replace("Budget: $1,450", "Budget: $100"))
        ids = [f["id"] for f in result["findings"]]
        self.assertIn("budget_exceeded", ids)
        self.assertLessEqual(result["score"]["axes"]["cost"]["score"], 45)


class ScheduleTests(unittest.TestCase):
    def test_schedule_has_steps_and_cure_waits(self):
        result = engine.analyse(BATHROOM)
        sched = result["schedule"]
        self.assertGreaterEqual(len(sched["tasks"]), 5)
        self.assertTrue(any(t["cure_after"] > 0 for t in sched["tasks"]))
        for i in range(1, len(sched["tasks"])):
            self.assertGreaterEqual(sched["tasks"][i]["start_h"],
                                    sched["tasks"][i - 1]["start_h"])

    def test_start_date_produces_a_finish_date(self):
        result = engine.analyse(BATHROOM.replace("Total area: 60 sqft",
                                                        "Total area: 60 sqft\nStart: 2026-11-23"))
        self.assertEqual(result["schedule"]["start_date"], "2026-11-23")
        self.assertIsNotNone(result["schedule"]["finish_date"])


class SafetyTests(unittest.TestCase):
    def test_wet_surface_without_waterproofing_is_capped(self):
        brief = BATHROOM.replace("Type: bathroom", "Type: bathroom\nScope:\n- Remove existing vinyl tile: 60 sqft\n- Install shower tile: 60 sqft")
        result = engine.analyse(brief)
        ids = [f["id"] for f in result["findings"]]
        self.assertIn("no_waterproofing", ids)
        self.assertLessEqual(result["score"]["axes"]["safety"]["score"], 30)
        self.assertLessEqual(result["score"]["overall"], 45)

    def test_deck_without_footings_is_flagged(self):
        result = engine.analyse(sample("backyard_deck.txt"))
        ids = [f["id"] for f in result["findings"]]
        self.assertIn("no_footings", ids)
        self.assertLessEqual(result["score"]["overall"], 55)


class CalibrationTests(unittest.TestCase):
    def test_sample_scores_are_in_range(self):
        expectations = {
            "bathroom_retile.txt": (85, 100, "ready_to_build"),
            "bedroom_repaint.txt": (70, 100, None),
            "basement_drywall.txt": (70, 100, None),
            "living_room_floor.txt": (40, 80, None),
            "kitchen_cabinets.txt": (30, 75, None),
            "backyard_deck.txt": (20, 60, None),
        }
        for name, (low, high, verdict) in expectations.items():
            result = engine.analyse(sample(name))
            score = result["score"]["overall"]
            self.assertTrue(low <= score <= high,
                            "%s scored %.1f, expected %s-%s" % (name, score, low, high))
            if verdict:
                self.assertEqual(result["score"]["verdict"], verdict)


class ExportTests(unittest.TestCase):
    def test_markdown_export(self):
        result = engine.analyse(BATHROOM)
        md = engine.to_markdown(result)
        self.assertIn("# Bathroom floor retile", md)
        self.assertIn("## Materials takeoff", md)
        self.assertIn("## Fix", md.replace("## Prioritised fix plan", "## Fix"))

    def test_csv_export(self):
        result = engine.analyse(BATHROOM)
        csv_text = engine.to_csv(result)
        lines = csv_text.strip().splitlines()
        self.assertEqual(lines[0].split(",")[0], "material")
        self.assertGreater(len(lines), 3)


class RobustnessTests(unittest.TestCase):
    def test_empty_brief(self):
        result = engine.analyse("")
        self.assertEqual(result["takeoff"]["count"], 0)
        self.assertTrue(result["findings"])

    def test_garbage_brief_does_not_crash(self):
        result = engine.analyse("?!?! 12345 ...")
        self.assertIn("score", result)

    def test_unknown_profile_falls_back(self):
        result = engine.analyse(BATHROOM, profile="does_not_exist")
        self.assertEqual(result["score"]["profile"], "general")


if __name__ == "__main__":
    unittest.main(verbosity=2)
