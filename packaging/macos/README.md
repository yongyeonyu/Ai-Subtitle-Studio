# macOS App Store Packaging

This branch targets macOS only. The production package should be a signed,
sandboxed `.app` bundle with the Python/PyQt payload and any compiled native
helpers that are still part of the source-app line.

Current packaging goals:

- macOS 14 or later, Apple Silicon first.
- Python/PyQt runtime bundled inside `AI Subtitle Studio.app`.
- Optional compiled `.so`/`.dylib` helpers copied into app resources when they
  exist.
- Local beta distribution through a signed `.app` inside a `.dmg`.
- Double-click `.command` wrappers for local build and update testing.
- App Sandbox enabled with user-selected file read/write access.
- Network client entitlement for optional local/remote model calls.
- Audio input entitlement for optional dictation/STT workflows.

Release checklist:

1. Build the Python app payload with the chosen bundler.
2. Copy compiled native helpers into `Contents/Resources/native` when present.
3. Apply `AI Subtitle Studio.entitlements`.
4. Sign every nested binary before signing the outer app bundle.
5. Run `codesign --verify --deep --strict`.
6. Run notarization or App Store upload validation.

Local beta DMG:

```bash
packaging/macos/build_beta_dmg.sh
```

Double-click alternatives:

- `Build Beta DMG.command`: builds, signs locally, validates, and creates the
  beta DMG under `dist/macos/`.
- `Install or Update AI Subtitle Studio.command`: installs the newest local DMG
  into `/Applications/AI Subtitle Studio.app`.

For a safe local updater test without touching `/Applications`:

```bash
TARGET_APP="$HOME/Applications/AI Subtitle Studio.app" \
  packaging/macos/install_or_update_app.sh
```

Scripts:

- `build_app_bundle.sh`: prepares the `.app` skeleton, copies the Python
  compatibility payload, and copies compiled native helper binaries when they
  exist.
- `sign_app_bundle.sh`: signs nested binaries and the outer app bundle. Use
  `CODESIGN_IDENTITY="Apple Distribution: ..."` for real release signing; the
  default ad-hoc identity is only for local smoke checks.
- `validate_app_bundle.sh`: validates Info.plist, bundle layout, payload
  presence, and strict code-signing state when signed.
- `create_dmg.sh`: creates a compressed beta DMG with the app bundle and an
  `/Applications` shortcut.
- `validate_dmg.sh`: verifies the DMG, mounts it read-only, and validates the
  contained app bundle.
- `build_beta_dmg.sh`: runs bundle build, signing, validation, DMG creation, and
  optional notarization when `NOTARY_KEYCHAIN_PROFILE` is set.
- `install_or_update_app.sh`: local batch-style updater for `.app`, `.dmg`, or
  `.zip` inputs. Set `TARGET_APP` or `TARGET_APP_PATH` to test in a custom
  location.
- `notarize_dmg.sh`: Developer ID notarization flow for beta DMG distribution.
- `notarize_app_bundle.sh`: Developer ID notarization flow using
  `xcrun notarytool` and `stapler`. Set `NOTARY_KEYCHAIN_PROFILE`.
- `build_app_store_pkg.sh`: creates a signed Mac App Store `.pkg` with
  `productbuild`. Set `INSTALLER_IDENTITY`.
- `upload_app_store_build.sh`: validates or uploads the `.pkg` to App Store
  Connect with `xcrun altool`. Set `ASC_API_KEY`/`ASC_API_ISSUER` or
  `ASC_USERNAME`/`ASC_PASSWORD`.

Apple references checked for this workflow:

- App notarization uses `notarytool` and `stapler` from Xcode.
- App Store Connect build upload supports `xcrun altool --validate-app` and
  `xcrun altool --upload-app` for macOS packages.
