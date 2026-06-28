# Mac App Store Submission Readiness

This document tracks the non-code and release-proof material needed before AI Subtitle Studio can be treated as a Mac App Store submission candidate.

## Current Status

- Status: blocked until owner-approved packaging/signing/validation is run.
- Source app version: `04.01.00`.
- Bundle identifier: `com.soseolgayumossi.aisubtitlestudio`.
- Category: `public.app-category.video`.
- Minimum macOS: `14.0`.
- Runtime direction: Python/PyQt6 source app packaged as a sandboxed macOS app.
- Submission target: Mac App Store `.pkg` built from a signed, sandboxed `.app`.
- Separate distribution track: Developer ID beta `.dmg` is opt-in local/beta distribution evidence, not Mac App Store submission proof.

## Distribution Track Boundary

- Mac App Store package: primary submission target. Required evidence is signed `.app`, strict `codesign`, signed `.pkg`, `pkgutil --check-signature`, sandbox smoke, App Store Connect validation, and completed non-code metadata.
- Developer ID beta DMG: separate opt-in track for beta distribution. It can help owner testing, but it must not be counted as App Store submission readiness.
- Normal source-app pytest/QA: useful runtime confidence, but not App Store submission proof by itself.

## Code-Side Gates

- Signed `.app` with Apple Distribution identity: pending.
- Strict `codesign --verify --deep --strict`: pending.
- Signed Mac App Store `.pkg` with installer identity: pending.
- `pkgutil --check-signature`: pending.
- Sandboxed smoke for launch, user-selected file access, audio/STT, model/network access, save/reopen, and export: pending.
- App Store Connect validation: pending.

## Entitlement Explanation Draft

- App Sandbox: required for Mac App Store distribution and enabled in `packaging/macos/AI Subtitle Studio.entitlements`.
- User-selected read/write: needed so editors can open, save, and export owner-selected media, subtitle, and project files.
- App-scope bookmarks: needed so user-approved file locations can survive app relaunches.
- Network client: needed for optional local or remote model calls.
- Audio input: needed for optional dictation and STT workflows.
- Temporary exception entitlements: none currently present.

## App Store Connect Owner Inputs

- Privacy policy URL: owner input required.
- App privacy data type answers: owner input required.
- Export compliance answers: owner input required.
- Support URL: owner input required.
- App screenshots: owner input required.
- App review notes: owner input required.
- Age rating answers: owner input required.
- Release notes: owner input required.

## Submission Contents Audit

- Latest audit: `output/manual_verification/latest/app_store_submission_contents_audit_20260628/app_store_readiness_audit.md`
- Submission content status: blocked.
- Pending owner-input items: `8/8`.
- Drafted item count: `8`.
- The audit itemizes each non-code submission field with `status`, `draft`, `owner_decision_required`, and `acceptance_gate` so metadata work stays separate from packaging/signing/upload proof.

## Non-Code Submission Metadata Draft

- Privacy policy URL: pending owner URL.
- App privacy data type answers: pending owner confirmation for media files, audio/STT workflows, optional network/model calls, diagnostics, and any analytics/crash collection policy.
- Export compliance answers: pending owner confirmation for encryption/export answers.
- Screenshots: pending App Store screenshot set after the signed/sandboxed app candidate exists.
- Support URL: pending owner URL.
- App review notes: pending sandbox entitlement explanation, model/network behavior notes, and test-account or fixture notes if needed.
- Age rating answers: pending owner confirmation.
- Release notes: source release note exists at `RELEASE_v04.01.00.md`; App Store release-note copy still needs owner approval before submission.

## Official References

- App Store Connect build upload: <https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/>
- App privacy: <https://developer.apple.com/help/app-store-connect/manage-app-information/manage-app-privacy>
- Export compliance: <https://developer.apple.com/help/app-store-connect/manage-app-information/overview-of-export-compliance>
- Screenshots and previews: <https://developer.apple.com/help/app-store-connect/manage-app-information/upload-app-previews-and-screenshots>
- App Sandbox information: <https://developer.apple.com/help/app-store-connect/reference/app-uploads/app-sandbox-information>

## Owner-Approved Command Sequence

These commands are not part of normal source-app development. Run them only after owner approval for packaging/signing/upload validation.

```bash
CODESIGN_IDENTITY="Apple Distribution: ..." packaging/macos/build_app_bundle.sh
CODESIGN_IDENTITY="Apple Distribution: ..." packaging/macos/sign_app_bundle.sh
packaging/macos/validate_app_bundle.sh
INSTALLER_IDENTITY="3rd Party Mac Developer Installer: ..." packaging/macos/build_app_store_pkg.sh
ASC_API_KEY="..." ASC_API_ISSUER="..." packaging/macos/upload_app_store_build.sh validate
```
