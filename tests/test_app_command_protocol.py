import unittest

from core.automation.app_command_protocol import (
    APP_COMMAND_RESULT_SCHEMA,
    APP_COMMAND_SCHEMA,
    build_command_payload,
    build_command_result,
    decode_command_payload,
    decode_command_result,
    encode_command_payload,
    encode_command_result,
    normalize_command_payload,
)


class AppCommandProtocolTests(unittest.TestCase):
    def test_normalize_command_payload_coerces_names_and_paths(self):
        payload = normalize_command_payload(
            {
                "command": "queue_files",
                "paths": [" /tmp/a.mp4 ", "", "/tmp/b.wav"],
            }
        )

        self.assertEqual(payload["schema"], APP_COMMAND_SCHEMA)
        self.assertEqual(payload["command"], "queue-files")
        self.assertEqual(payload["paths"], ["/tmp/a.mp4", "/tmp/b.wav"])
        self.assertEqual(payload["path"], "/tmp/a.mp4")

    def test_normalize_command_payload_promotes_start_multiclip_path_to_folder(self):
        payload = normalize_command_payload(
            {
                "command": "start_multiclip",
                "path": " /tmp/demo ",
            }
        )

        self.assertEqual(payload["command"], "start-multiclip")
        self.assertEqual(payload["folder"], "/tmp/demo")

    def test_encode_and_decode_payload_roundtrip(self):
        payload = build_command_payload("open-project", path="/tmp/demo.json")

        decoded = decode_command_payload(encode_command_payload(payload))

        self.assertEqual(decoded["command"], "open-project")
        self.assertEqual(decoded["path"], "/tmp/demo.json")

    def test_encode_and_decode_result_roundtrip(self):
        result = build_command_result(
            "status",
            ok=True,
            accepted=True,
            data={"editor_open": True},
        )

        decoded = decode_command_result(encode_command_result(result))

        self.assertEqual(decoded["schema"], APP_COMMAND_RESULT_SCHEMA)
        self.assertTrue(decoded["ok"])
        self.assertTrue(decoded["data"]["editor_open"])


if __name__ == "__main__":
    unittest.main()
