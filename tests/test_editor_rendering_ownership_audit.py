import unittest

from tools.audit_editor_rendering_ownership import audit_editor_rendering_ownership, render_markdown


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
        self.assertIn("TimelineSingleOwnerPlayheadInvalidation", owners)

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
        self.assertEqual(inventory["TimelineSingleOwnerPlayheadInvalidation"], "qwidget-2d-full-canvas-repaint")

    def test_single_owner_playhead_invalidation_stays_full_canvas_repaint(self):
        report = audit_editor_rendering_ownership()

        self.assertTrue(report["ok"], report["issues"])
        owners = {item["owner"] for item in report["inventory"]}
        self.assertIn("TimelineSingleOwnerPlayheadInvalidation", owners)
        gate = report["playhead_dirty_rect_candidate"]
        self.assertEqual(gate["status"], "hold_full_canvas_repaint")
        self.assertFalse(gate["runtime_change_allowed"])
        self.assertIn("fresh_macau_visual_smoke_no_residue", gate["required_before_experiment"])

    def test_render_markdown_includes_playhead_dirty_rect_gate(self):
        report = audit_editor_rendering_ownership()

        markdown = render_markdown(report)

        self.assertIn("Playhead Dirty-Rect Candidate Gate", markdown)
        self.assertIn("hold_full_canvas_repaint", markdown)
        self.assertIn("fresh_macau_visual_smoke_no_residue", markdown)


if __name__ == "__main__":
    unittest.main()
