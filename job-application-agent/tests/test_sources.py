import unittest
from unittest.mock import MagicMock

from jobagent.sources import fetch_all, fetch_remoteok, fetch_remotive


def _mock_response(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


class FetchRemotiveTests(unittest.TestCase):
    def test_normalizes_jobs(self):
        session = MagicMock()
        session.get.return_value = _mock_response(
            {
                "jobs": [
                    {
                        "id": 1,
                        "title": "AI Prompt Engineer",
                        "company_name": "Acme",
                        "url": "https://remotive.com/1",
                        "candidate_required_location": "Worldwide",
                        "description": "<p>Work with <b>LLMs</b></p>",
                        "tags": ["ai", "remote"],
                    }
                ]
            }
        )
        jobs = fetch_remotive(search="prompt", session=session)
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job.source, "remotive")
        self.assertEqual(job.external_id, "1")
        self.assertEqual(job.title, "AI Prompt Engineer")
        self.assertIn("Work with LLMs", job.description)
        self.assertTrue(job.remote)


class FetchRemoteOkTests(unittest.TestCase):
    def test_skips_legal_header_row(self):
        session = MagicMock()
        session.get.return_value = _mock_response(
            [
                {"legal": "https://remoteok.com/terms"},
                {
                    "id": "42",
                    "position": "QA Tester",
                    "company": "Beta Inc",
                    "url": "https://remoteok.com/remote-jobs/42",
                    "location": "Remote",
                    "description": "Manual + automated testing.",
                    "tags": ["qa"],
                },
            ]
        )
        jobs = fetch_remoteok(session=session)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].external_id, "42")
        self.assertEqual(jobs[0].title, "QA Tester")


class FetchAllTests(unittest.TestCase):
    def test_collects_errors_without_raising(self):
        session = MagicMock()
        session.get.side_effect = Exception("network down")
        jobs, errors = fetch_all(sources=["remotive", "remoteok"], session=session)
        self.assertEqual(jobs, [])
        self.assertEqual(len(errors), 2)

    def test_unknown_source_reported(self):
        jobs, errors = fetch_all(sources=["not-a-real-source"], session=MagicMock())
        self.assertEqual(jobs, [])
        self.assertIn("Unknown source", errors[0])


if __name__ == "__main__":
    unittest.main()
