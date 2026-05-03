<!--
Document-Version: 03.12.00
Phase: PHASE2
Last-Updated: 2026-05-03
Updated-By: Codex with 대표님
This-Update: v03.12.00 release sync after cut-boundary pioneer/follower, restart reset, and Whisper hard-cut alignment work
GitHub-Publish: no
-->
# ACTION_QUEUE v2

meta:
  app: 03.12.00
  next: 03.12.01
  phase: PHASE2
  commit: user_explicit_only
  done: remove_from_this_file
  confirm: keep_in_check_list
  skip_run_all: [PHASE3, iPad]
  routine_change_docs:
    policy: minimal_only
    update_immediately:
      - config.py_APP_VERSION_if_code_behavior_changes
      - ACTION_ITEMS.md_only_if_queue_changes
      - check_list.md_only_if_user_confirmation_needed
      - current_RELEASE_v*.md_only_for_removed_defs_classes_helpers_ui_actions_signals_slots_or_nondeferrable_risk
      - AGENTS.md_only_if_rules_or_handoff_facts_change
      - File_structure.txt_only_if_files_added_removed_moved_or_roles_change
      - README.md_only_if_public_usage_install_docs_cannot_wait
    defer_to_release:
      - broad_doc_version_sync
      - routine_release_notes
      - README_latest_release_summary
      - full_file_structure_refresh
      - handoff_prompt_refresh
  refactor_request_rule:
    trigger: only_if_user_explicitly_requests_refactoring
    action_queue_item: false
    run_all: excluded
    preserve_existing_features: true
    suspected_unused_files:
      verify_before_action: [static_refs, dynamic_imports, subprocess_entrypoints, tests, windows_paths]
      first_action: move_to_codex_work_for_retention
      note_required: true
      delete_only_after_user_approval: true
    document_removed_defs_classes_helpers_ui_actions_signals_slots: current_RELEASE_v*.md
  release:
    trigger_ko: ["릴리즈하자", "릴리즈 하자"]
    version_rule: increment_middle_component_and_reset_patch_to_00
    example: "03.02.00 -> 03.03.00"
    release_note:
      create_new_file: true
      filename_template: "RELEASE_v{new_release_version}.md"
      middle_version_bump_requires_new_note: true
      keep_previous_release_notes: true
    update_docs: [File_structure.txt, ACTION_ITEMS.md, AGENTS.md, check_list.md, README.md, "RELEASE_v{new_release_version}.md"]
    update_requirements_if_needed: [requirements-mac.txt, requirements-windows.txt]
    verify_before_commit: true
    commit_push_main: true
    final_handoff_prompt: true
  no_touch: ["dataset/video_preview_cache/"]
  root_no: ["create_all*", "_backup*", "STRUCTURE.txt", "requirements.txt"]
  scratch:
    dir: .codex_work/
    purpose: codex_only_local_memory_reduce_tokens_speed_up_dev
    use_for: [long_action_items, decomposed_task_files, chat_context_notes, important_project_facts, file_maps, test_plans, source_summaries, url_summaries, open_source_notes, analysis_artifacts, reusable_history]
    action_items_may_link_to: true
    final_source: false
    commit: never
    cleanup: only_if_obsolete_or_user_asks
  req: [requirements-mac.txt, requirements-windows.txt]
  win: [paths_ko_space_backslash, subprocess, ffmpeg, ffprobe, faster_whisper_worker, PyQt6_DLL]
  qt_widget_lifecycle:
    rebuild_layouts: detach_persistent_widgets_before_replacing_or_orphaning_old_layout
    deleted_cpp_wrappers: guard_runtimeerror_and_recreate_widget
    persistent_panel_widgets_require: [recreation_helper, repeated_rebuild_regression_test]
  docs:
    ACTION_ITEMS.md: queue_only
    check_list.md: ko_ux_scenario_pass_fail_only
    AGENTS.md: rules_handoff
    File_structure.txt: structure_only
    RELEASE_v*.md: versioned_release_notes_history_removals_summary
    README.md: latest_release_only

now: null

later:
  PHASE2-D-PAGE3B:
    status: deferred
    src:
      - /Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/ACTION_ITEMS_PAGE_3B_ROUGHCUT_EDITOR.md
      - /Users/u_mo_c/Library/Mobile Documents/com~apple~CloudDocs/ai_subtitle_editor_interface_overview.png
    keep: [roughcut_mvp, legacy_qtable_fallback, edl_guide_srt_render_verify_recover, v1_state_load]
    llm: separate_roughcut_llm_settings_prompt_config_with_local_fallback_done
    no_touch: ["dataset/video_preview_cache/"`]
    base: [ui/roughcut/roughcut_widget.py, ui/roughc`ut/roughcut_table.py, ui/roughcut/roughcut_preview.py, ui/roughcut/roughcut_state.py, core/roughcut/models.py, core/roughcut/pipeline.py]
    checklist: [CP-18, CP-19, CP-26]

parking:
  PHASE3_iPad:
    [P3-SF1, P3-SF2, P3-SF3, P3-API1, P3-API2, P3-API3, P3-API4, P3-API5, iPad-1, iPad-2, iPad-3, iPad-4, iPad-5, iPad-6, iPad-7]
