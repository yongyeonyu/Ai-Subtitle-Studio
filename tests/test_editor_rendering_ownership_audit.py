import unittest

from tools.audit_editor_rendering_ownership import audit_editor_rendering_ownership


class EditorRenderingOwnershipAuditTests(unittest.TestCase):
    def test_editor_rendering_ownership_audit_passes(self):
        report = audit_editor_rendering_ownership()

        self.assertTrue(report["ok"], report["issues"])
        owners = {item["owner"] for item in report["inventory"]}
        self.assertIn("TimelineCanvas", owners)
        self.assertIn("TimelineInlineTextEdit", owners)
        self.assertIn("GpuRenderingGate", owners)


if __name__ == "__main__":
    unittest.main()
