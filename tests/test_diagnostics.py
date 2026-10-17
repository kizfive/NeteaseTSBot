import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
import httpx

from backend import diagnostics, main


class DeploymentDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_offline_voice_is_not_reported_as_a_teamspeak_connection(self):
        voice = SimpleNamespace(get_status=AsyncMock(side_effect=RuntimeError("password=private")))
        checks = await diagnostics._voice_checks(voice, "")
        self.assertEqual("error", checks[0]["status"])
        self.assertEqual("warning", checks[1]["status"])
        self.assertNotIn("private", json.dumps(checks))

    async def test_older_voice_and_unapplied_revisions_do_not_report_ready(self):
        voice = SimpleNamespace(get_status=AsyncMock(return_value=SimpleNamespace(config_revision="old")))
        checks = await diagnostics._voice_checks(voice, "new")
        self.assertEqual("warning", next(item for item in checks if item["id"] == "teamspeak")["status"])
        self.assertEqual("warning", next(item for item in checks if item["id"] == "voice_config")["status"])

    async def test_report_requires_real_teamspeak_state_but_not_optional_netease(self):
        voice = SimpleNamespace(get_status=AsyncMock(return_value=SimpleNamespace(config_revision="current", teamspeak_connected=True)))
        with (
            patch.object(diagnostics, "settings_payload", return_value={"apply_pending": False}),
            patch.object(diagnostics, "get_value", return_value="http://music.invalid"),
            patch.object(diagnostics, "voice_config_revision", return_value="current"),
            patch.object(diagnostics, "_netease_check", AsyncMock(return_value=diagnostics._check("netease", "Music", "warning", "Unavailable", required=False))),
        ):
            result = await diagnostics.run_diagnostics(Mock(), voice)
            self.assertTrue(result["ready"])
            voice.get_status.return_value.teamspeak_connected = False
            result = await diagnostics.run_diagnostics(Mock(), voice)
            self.assertFalse(result["ready"])

    async def test_music_check_rejects_html_arbitrary_json_and_redirects(self):
        for status_code, data in [(200, {}), (200, {"code": 401, "data": {}}), (302, {"code": 200, "data": {}})]:
            client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(status_code, json=data)))
            with patch.object(diagnostics.httpx, "AsyncClient", return_value=client):
                result = await diagnostics._netease_check("http://user:private@music.invalid")
            self.assertEqual("warning", result["status"])
            self.assertNotIn("private", json.dumps(result))

    async def test_music_check_accepts_expected_api_response(self):
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"code": 200, "data": {"showKeyword": "music"}})))
        with patch.object(diagnostics.httpx, "AsyncClient", return_value=client):
            result = await diagnostics._netease_check("http://music.invalid")
        self.assertEqual("success", result["status"])

    async def test_diagnostics_requires_admin_before_probing_services(self):
        with (
            patch.object(main, "require_admin", side_effect=HTTPException(status_code=401)),
            patch.object(main, "run_diagnostics", AsyncMock()) as probe,
        ):
            with self.assertRaises(HTTPException):
                await main.admin_diagnostics(Mock(), Mock())
            probe.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
