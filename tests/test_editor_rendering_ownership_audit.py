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
        self.assertIn("TimelinePaintPassPlanner", owners)
        self.assertIn("TimelineInputHitTargets", owners)
        self.assertIn("TimelineWaveformSource", owners)
        self.assertIn("STTPreviewLaneLayout", owners)
        self.assertIn("SubtitleTextEditQmlOverlayGate", owners)
        self.assertIn("VideoControlBarQmlGate", owners)
        self.assertIn("VideoSubtitleOverlayQmlGate", owners)
        self.assertIn("TimelineSceneGraphLayerGate", owners)
        self.assertIn("TimelinePaintOrder", owners)

    def test_editor_rendering_ownership_audit_covers_paint_surface_inventory(self):
        report = audit_editor_rendering_ownership()

        inventory = {item["owner"]: item["backend"] for item in report["inventory"]}
        self.assertEqual(inventory["TimelinePaintMixin"], "qwidget-2d-painter-owner")
        self.assertEqual(inventory["TimelinePaintPassPlanner"], "qwidget-2d-plan-only")
        self.assertEqual(inventory["TimelineInputHitTargets"], "qwidget-2d-input-only")
        self.assertEqual(inventory["TimelineWaveformSource"], "waveform-data-source")
        self.assertEqual(inventory["STTPreviewLaneLayout"], "qwidget-2d-layout-only")
        self.assertEqual(inventory["SubtitleTextEditQmlOverlayGate"], "explicit-diagnostic-gate")
        self.assertEqual(inventory["VideoControlBarQmlGate"], "explicit-scenegraph-gate")
        self.assertEqual(inventory["VideoSubtitleOverlayQmlGate"], "explicit-diagnostic-gate")
        self.assertEqual(inventory["TimelineSceneGraphLayerGate"], "explicit-scenegraph-gate")
        self.assertEqual(inventory["TimelinePaintOrder"], "qwidget-2d-painter-owner")


if __name__ == "__main__":
    unittest.main()
