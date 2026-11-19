"""API tests for reno-forge."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as reno  # noqa: E402

SAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.tmp.close()
        reno.DB_PATH = self.tmp.name
        reno.app.config["TESTING"] = True
        self.client = reno.app.test_client()

    def tearDown(self):
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def brief(self):
        with open(os.path.join(SAMPLES, "bathroom_retile.txt"), encoding="utf-8") as fh:
            return fh.read()

    def test_health(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ok")

    def test_profiles(self):
        resp = self.client.get("/api/profiles")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.get_json()), 5)

    def test_samples(self):
        resp = self.client.get("/api/samples")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.get_json()), 6)

    def test_analyze(self):
        resp = self.client.post("/api/analyze", json={"brief": self.brief(), "profile": "general"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("score", data)
        self.assertIn("takeoff", data)
        self.assertIn("schedule", data)
        self.assertIn("findings", data)
        self.assertGreater(data["score"]["overall"], 50)

    def test_analyze_requires_a_brief(self):
        resp = self.client.post("/api/analyze", json={"brief": "  "})
        self.assertEqual(resp.status_code, 400)

    def test_run_lifecycle(self):
        created = self.client.post("/api/runs", json={"brief": self.brief(), "profile": "general"})
        self.assertEqual(created.status_code, 201)
        run_id = created.get_json()["id"]

        listed = self.client.get("/api/runs")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.get_json()), 1)

        fetched = self.client.get("/api/runs/%d" % run_id)
        self.assertEqual(fetched.status_code, 200)
        self.assertIn("result", fetched.get_json())

        patched = self.client.patch("/api/runs/%d" % run_id, json={"self_rating": 4, "notes": "good"})
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.get_json()["self_rating"], 4)

        deleted = self.client.delete("/api/runs/%d" % run_id)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(len(self.client.get("/api/runs").get_json()), 0)

    def test_export_formats(self):
        for fmt, marker in (("md", "# Bathroom floor retile"), ("csv", "material,need"),
                            ("json", '"score"')):
            resp = self.client.post("/api/export", json={"brief": self.brief(), "format": fmt})
            self.assertEqual(resp.status_code, 200)
            self.assertIn(marker, resp.get_data(as_text=True))

    def test_index_page_is_served(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("reno-forge", resp.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
