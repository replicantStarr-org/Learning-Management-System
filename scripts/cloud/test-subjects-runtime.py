"""Run inside the Subjects backend image for the cloud deployment, checks some basic functionality."""
import os
import unittest
from unittest.mock import patch

os.environ.update(CLOUD_DEPLOYMENT="true", DEPLOYMENT_PROFILE="default", AI_MODE_ENABLED="false",
                  MCP_ENABLED="false", RAG_ENABLED="false", MULTI_AGENT_ENABLED="false")
from app import create_app


class CloudSubjectsTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app().test_client()

    def test_flags_are_server_enforced(self):
        for path in ("/subjects/1/summary", "/subjects/questions", "/mcp/query/tag", "/rag/ingest", "/multi-agent/workflow"):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, json={}).status_code, 403)

    def test_runtime_config_is_public_configuration_only(self):
        response = self.client.get("/config")
        self.assertEqual(response.json["profile"], "default")
        self.assertTrue(all(value is False for value in response.json["flags"].values()))
        self.assertNotIn("JWT_SECRET", response.text)
        self.assertNotIn("OPENAI_API_KEY", response.text)

    def test_cloud_blocks_cross_origin_mutations(self):
        response = self.client.post("/api/v1/subjects", base_url="https://cloud.example",
                                    headers={"Origin": "https://attacker.example"}, json={})
        self.assertEqual(response.status_code, 403)

    def test_same_origin_api_remains_usable(self):
        with patch("routes.api.list_subjects", return_value=[]):
            response = self.client.get("/api/v1/subjects", base_url="https://cloud.example")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, [])
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_redirects_are_relative(self):
        with patch("routes.subjects.create_subject", return_value={"subject_id": 123, "code": "TEST"}):
            response = self.client.post("/subjects", data={})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.headers["HX-Redirect"], "/subject.html?id=123")


if __name__ == "__main__":
    unittest.main()
