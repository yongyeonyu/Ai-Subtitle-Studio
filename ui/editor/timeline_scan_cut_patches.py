# Version: 03.13.05
# Phase: PHASE2
"""Scan-cut patch installers for EditorTimelineVideoMixin."""

from ui.editor.timeline_scan_cut_relative_base import install_scan_cut_relative_base
from ui.editor.timeline_scan_cut_relative_refine import install_scan_cut_relative_refinements
from ui.editor.timeline_scan_cut_resume import install_scan_cut_resume_patch


def install_scan_cut_patches(EditorTimelineVideoMixin):
    install_scan_cut_relative_base(EditorTimelineVideoMixin)
    install_scan_cut_relative_refinements(EditorTimelineVideoMixin)
    install_scan_cut_resume_patch(EditorTimelineVideoMixin)
