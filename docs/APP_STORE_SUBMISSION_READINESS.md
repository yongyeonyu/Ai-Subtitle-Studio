# Mac App Store Submission Readiness

This document tracks the release-proof and owner-input material needed before
AI Subtitle Studio can be treated as a Mac App Store submission candidate.

## Current Status

- Status: blocked. Owner approval for App Store packaging/signing/upload/metadata execution was granted on 2026-06-28 and reconfirmed on 2026-06-29, but distribution identities, signed `.pkg`, strict signature proof, App Store validation, and owner metadata values are still incomplete.
- Source app version: `04.01.27`.
- Bundle identifier: `com.soseolgayumossi.aisubtitlestudio`.
- Category: `public.app-category.video`.
- Minimum macOS: `14.0`.
- Runtime direction: Python/PyQt6 source app packaged as a sandboxed macOS app.
- Submission target: Mac App Store `.pkg` built from a signed, sandboxed `.app`.
- Separate distribution track: Developer ID beta `.dmg` is opt-in local/beta distribution evidence, not Mac App Store submission proof.

## Readiness Definition

The app is ready to submit only when all of these proof surfaces exist:

1. Signed sandboxed `.app` using the correct Apple Distribution identity.
2. Strict `codesign --verify --deep --strict --verbose=2` output for that exact app.
3. Signed Mac App Store `.pkg` using the installer identity.
4. `pkgutil --check-signature` output for that exact package.
5. Sandboxed smoke proof for launch, user-selected media open, audio/STT, optional network/model access, save/reopen, SRT export, rendered subtitle output, and quit/cleanup.
6. App Store Connect or Transporter validation output for the exact package.
7. Owner-approved App Store metadata values JSON, privacy answers, export compliance, review notes, screenshots, support URL, App Store Connect listing metadata, and release notes.

Source-app pytest, quick QA, release notes, and documentation updates are useful
confidence signals, but none of them is App Store submission proof by itself.

## Launch Plan

### Phase 0. Owner Inputs

- Confirm App Store Connect app record, team, bundle ID, SKU, primary locale, category, pricing/free status, and availability.
- Provide or approve support URL, privacy policy URL, marketing URL, screenshots, app subtitle, keywords, description, promotional text, review notes, age rating answers, and release-note copy.
- Confirm App Privacy answers for local media, audio/STT, optional network/model calls, diagnostics, crash/analytics policy, and user data retention.
- Confirm Export Compliance answers, including encryption/network behavior.

Exit gate: every owner-input item and App Store Connect listing metadata field is approved, has evidence, and is either populated or explicitly marked not applicable by `tools/check_app_store_owner_metadata_values.py`.

### Phase 1. Source-App Baseline

- Run a current source quick QA before building packages.
- Preserve subtitle quality gates and UI/UX behavior.
- Record baseline in `docs/quality_validation/test_result.md` or `output/manual_verification/latest/`.
- Latest source quick QA baseline: `output/manual_verification/latest/qa_suite_quick_v040117_20260629_0929/suite_result.md` -> `profile=quick`, `scenario_count=1`, `passed=1`, `failed=0`, scenario `editor_compact_macau`.

Exit gate: source-app baseline passes, and no runtime work is hidden inside packaging.

### Phase 2. Sandboxed App Bundle

- Build the app bundle with `packaging/macos/build_app_bundle.sh`.
- Sign nested binaries and the outer app with `packaging/macos/sign_app_bundle.sh`.
- Use `packaging/macos/AI Subtitle Studio.entitlements`.
- Verify strict codesign.
- Smoke launch and editor workflows under sandbox constraints.

Exit gate: exact `.app` path, signing identity, entitlements, strict verification, and sandbox smoke artifact are recorded.

### Phase 3. Mac App Store Package

- Build the signed package with `packaging/macos/build_app_store_pkg.sh` using `INSTALLER_IDENTITY`.
- Run `pkgutil --check-signature`.
- Keep the `.pkg` artifact path and signature output tied together in the report.

Exit gate: package signature is valid and points to the same app candidate from Phase 2.

### Phase 4. App Store Connect Validation

- Run `packaging/macos/upload_app_store_build.sh validate` or Transporter validation.
- Upload approval has been granted by the owner for this App Store lane; do not upload until validation succeeds for the exact signed `.pkg`. Upload mode also requires `AI_SUBTITLE_STUDIO_APP_STORE_UPLOAD_CONFIRMED=1`, `APP_STORE_READINESS_JSON`, exact `.pkg` binding, no readiness blockers, and all submission gates true.
- Preserve validation output under `output/manual_verification/latest/`.

Exit gate: validation succeeds for the exact `.pkg` candidate.

### Phase 5. Submission Assembly

- Attach screenshots, release notes, privacy answers, export compliance, sandbox entitlement explanation, and review notes.
- Check that metadata does not overclaim speed, native migration, App Store readiness, or unsupported format behavior.
- Submission approval has been granted for this App Store lane; submit only after the exact signed `.pkg`, validation output, and owner metadata package are complete.

Exit gate: App Store Connect submission is owner-approved and all non-code material is complete.

### Phase 6. Review / Release

- Track Apple review messages separately from local QA.
- If rejected, create a narrow fix item with the exact rejection text, owner file, proof command, and rollback plan.
- After approval, update `docs/release_notes/` and `docs/HANDOFF.md` with the release state.

## Current Blockers

- Signed `.app`: local Apple Development smoke exists; Apple Distribution submission signing is still missing.
- Signed `.pkg`: missing.
- Strict App Store-candidate codesign output: missing.
- Package signature output from `pkgutil --check-signature`: missing.
- Sandboxed workflow smoke: missing.
- App Store Connect validation artifact: missing.
- Apple Distribution signing identity: not configured in local proof.
- Installer signing identity: not configured in local proof.
- Privacy answers: owner input required.
- Export compliance answers: owner input required.
- Screenshots: owner input required.
- Support URL: owner input required.
- Review notes: owner input required.
- Age rating and release-note copy: owner input required.
- App Store Connect listing metadata values: owner input required for app name confirmation, subtitle, keywords, description, promotional text, marketing URL, app record, pricing, and availability.
- Owner metadata values JSON: missing; current values preflight `ready=false`.

## Latest Owner-Input Package

- `output/manual_verification/latest/app_store_metadata_owner_input_package_v040126_20260629_1228/app_store_metadata_owner_input_package.md`

Latest package state: `status=blocked`, `not_submission_proof=true`,
`owner_input_complete=false`, `app_store_submission_ready=false`, pending
owner-input metadata `8/8`, pending App Store Connect metadata `8`, owner
values preflight `false`, forbidden-claim scan `pass` with `0` matches, app
version `04.01.26` from the previous G0 package refresh, upload confirmation guard present, and sanitized source
readiness snapshot with overall stoplight `red`.
This package is a collection/checklist artifact only; it does not replace signed
package proof, sandbox smoke, App Store Connect validation, upload/submission,
or owner-approved metadata values JSON. Because the source app is now
`04.01.27`, the G0 owner-input package must be refreshed before any package or
upload readiness claim can bind to the current app version.

## Owner Metadata Values Preflight

- Helper: `tools/check_app_store_owner_metadata_values.py`
- Required schema: `ai_subtitle_studio.app_store_owner_metadata_values.v1`
- Required proof: field values, owner approval evidence, app-version match, public URL owner-control confirmation, App Store Connect record bundle binding, signed-candidate screenshot binding, and forbidden-copy scan pass.
- Forbidden imported-copy examples include `App Store ready`, `offline-only`, `100% accurate`, `validated`, `commercial NLE replacement`, `full NLE`, `native NLE`, and `real-time editing`.
- This preflight can clear the owner metadata gate only; it is not signed package, sandbox smoke, validation, upload, or submission proof.

## Latest Source-App Baseline

- `output/manual_verification/latest/qa_suite_quick_v040117_20260629_0929/suite_result.md`

Latest baseline state: `profile=quick`, `scenario_count=1`, `passed=1`,
`failed=0`, scenario `editor_compact_macau`. This is source-app editor workflow
baseline only. It is not sandbox smoke, signed app/package proof, App Store
Connect validation, upload/submission proof, owner metadata completion, full QA,
real-media STT quality, or roughcut proof.

## Latest Audit Evidence

- `output/manual_verification/latest/app_store_readiness_audit_20260627/app_store_readiness_audit.md`
- `output/manual_verification/latest/app_store_readiness_target_lock_20260628/app_store_readiness_audit.md`
- `output/manual_verification/latest/app_store_submission_contents_audit_20260628/app_store_readiness_audit.md`
- `output/manual_verification/latest/app_store_readiness_gate_refresh_20260628/app_store_readiness_audit.md`
- `output/manual_verification/latest/app_store_readiness_v040100_20260628/app_store_readiness_audit.md`
- `output/manual_verification/latest/app_store_owner_approval_readiness_after_packaging_fix_20260628_2250/app_store_readiness_audit.md`
- `output/manual_verification/latest/app_store_owner_approval_identity_check_20260629_0026/app_store_readiness_audit.md`
- `output/manual_verification/latest/app_store_v040101_identity_check_20260629_0036/app_store_readiness_audit.md`
- `output/manual_verification/latest/app_store_identity_metadata_blocker_v040115_20260629_0907/app_store_readiness_audit.md`
- `output/manual_verification/latest/app_store_metadata_owner_input_package_v040116_20260629_0921/app_store_metadata_owner_input_package.md`
- `output/manual_verification/latest/app_store_owner_approval_packaging_20260628_2220/`
- `output/manual_verification/latest/app_store_upload_preflight_guard_v040125_20260629_1200/app_store_readiness_audit.md`
- `output/manual_verification/latest/app_store_metadata_owner_input_package_v040125_20260629_1200/app_store_metadata_owner_input_package.md`
- `output/manual_verification/latest/app_store_owner_metadata_values_preflight_v040126_20260629_1228/app_store_readiness_audit.md`
- `output/manual_verification/latest/app_store_metadata_owner_input_package_v040126_20260629_1228/app_store_metadata_owner_input_package.md`

Latest known state: `status=blocked`, `local_packaging_ready=true`,
`app_store_submission_ready=false`, overall stoplight `red`, blocker count
`25`. Version lock and packaging template gates are green; signed-artifact
proof, sandbox smoke, App Store Connect validation, signing identities, and
owner metadata remain red. Current blocker groups are `signed_artifacts=3`,
`sandbox_smoke=1`, `app_store_connect=1`, `signing_identities=4`, and
`owner_metadata=16`. App Store Connect auth is configured in the local
environment, but validation output is still missing. The latest local identity
check still lacks Apple Distribution and 3rd Party Mac Developer Installer
identities, all `8` non-code submission metadata items remain
`owner_input_required`, and all `8` App Store Connect metadata fields remain
pending. Upload mode is guarded by a separate preflight helper and will not run
from approval alone.

## Owner-Approved Command Sequence

These commands are not part of normal source-app development. Run them only
after owner approval for the corresponding packaging/signing/validation step.

```bash
AI_SUBTITLE_STUDIO_QA_USE_SOURCE=1 ./venv/bin/python tools/qa_suite_runner.py quick
CODESIGN_IDENTITY="Apple Distribution: ..." packaging/macos/build_app_bundle.sh
CODESIGN_IDENTITY="Apple Distribution: ..." packaging/macos/sign_app_bundle.sh
packaging/macos/validate_app_bundle.sh
INSTALLER_IDENTITY="3rd Party Mac Developer Installer: ..." packaging/macos/build_app_store_pkg.sh
ASC_API_KEY="..." ASC_API_ISSUER="..." packaging/macos/upload_app_store_build.sh validate
AI_SUBTITLE_STUDIO_APP_STORE_UPLOAD_CONFIRMED=1 APP_STORE_READINESS_JSON="output/manual_verification/latest/app_store_owner_metadata_values_preflight_v040126_20260629_1228/app_store_readiness_audit.json" ASC_API_KEY="..." ASC_API_ISSUER="..." packaging/macos/upload_app_store_build.sh upload
```

## Official References

- App Store Connect build upload: <https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/>
- App privacy: <https://developer.apple.com/help/app-store-connect/manage-app-information/manage-app-privacy>
- Export compliance: <https://developer.apple.com/help/app-store-connect/manage-app-information/overview-of-export-compliance>
- Screenshots and previews: <https://developer.apple.com/help/app-store-connect/manage-app-information/upload-app-previews-and-screenshots>
- App Sandbox information: <https://developer.apple.com/help/app-store-connect/reference/app-uploads/app-sandbox-information>
