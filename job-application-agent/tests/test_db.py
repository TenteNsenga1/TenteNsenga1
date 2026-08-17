import tempfile
import unittest
from pathlib import Path

from jobagent import db


class DbTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test.db"
        db.init_db(self.db_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _job(self, external_id="1", **overrides):
        defaults = dict(
            source="remotive",
            external_id=external_id,
            title="Prompt Engineer",
            company="Acme",
            url="https://example.com/1",
        )
        defaults.update(overrides)
        return db.Job(**defaults)

    def test_upsert_dedupes(self):
        with db.connect(self.db_path) as conn:
            id1, new1 = db.upsert_job(conn, self._job())
            id2, new2 = db.upsert_job(conn, self._job())
        self.assertTrue(new1)
        self.assertFalse(new2)
        self.assertEqual(id1, id2)

    def test_set_status_records_applied_at(self):
        with db.connect(self.db_path) as conn:
            job_id, _ = db.upsert_job(conn, self._job())
            db.set_status(conn, job_id, "applied")
            row = db.get_job(conn, job_id)
        self.assertEqual(row["status"], "applied")
        self.assertIsNotNone(row["applied_at"])

    def test_set_status_rejects_unknown_status(self):
        with db.connect(self.db_path) as conn:
            job_id, _ = db.upsert_job(conn, self._job())
            with self.assertRaises(ValueError):
                db.set_status(conn, job_id, "bogus")

    def test_list_jobs_filters_by_status_and_score(self):
        with db.connect(self.db_path) as conn:
            db.upsert_job(conn, self._job(external_id="1", status="scored", fit_score=5))
            db.upsert_job(conn, self._job(external_id="2", status="scored", fit_score=1))
            db.upsert_job(conn, self._job(external_id="3", status="excluded", fit_score=-100))
            rows = db.list_jobs(conn, status="scored", min_fit_score=2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["external_id"], "1")

    def test_status_counts(self):
        with db.connect(self.db_path) as conn:
            db.upsert_job(conn, self._job(external_id="1", status="scored"))
            db.upsert_job(conn, self._job(external_id="2", status="scored"))
            db.upsert_job(conn, self._job(external_id="3", status="applied"))
            counts = db.status_counts(conn)
        self.assertEqual(counts["scored"], 2)
        self.assertEqual(counts["applied"], 1)


if __name__ == "__main__":
    unittest.main()
