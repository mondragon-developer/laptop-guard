# Release process

Version is defined in `guard_runtime/version.py`. Update the version and the public notes together.

1. Push a `release/*` branch or open a PR to `master`. GitHub builds Windows x64, macOS Apple Silicon and macOS Intel on native runners. All three must pass.
2. Each job runs the hardware-free tests, builds the application, copies only the app and public guide into an isolated folder, runs the packaged `--check`, and creates a ZIP plus SHA-256 checksum. It does not arm the app or capture real webcam frames.
3. Download the artifacts from the successful commit. Review the included instructions and release notes, and test on real devices with OS permissions granted. CI does not validate physical input suppression, sound or camera access.
4. Create a draft release with the version tag targeting that exact commit and attach all three ZIPs plus their checksums. Review before publishing. Alternatively, pushing a version tag runs all builds and creates a draft only if that release does not already exist. Existing complete releases and their assets are preserved; an incomplete release requires review instead of automatic replacement.

To validate an existing tag with the current workflow, run **Release packages → Run workflow** from `master` and enter the tag in `release_tag`. This rebuilds the tagged source with the current workflow and checks the existing release without replacing its files or changing draft/prerelease status. Re-running an old tag-triggered job uses the old workflow, so use this manual entry point after workflow fixes. Network/authentication failures stop release creation instead of being treated as a missing release.

Locally, build with `python -m PyInstaller laptop_guard.spec --clean --noconfirm`, then run `python tools/package_release.py --target windows-x64` (or `macos-apple-silicon` / `macos-intel` on that architecture). Files go to ignored `release-artifacts/`. Do not ZIP the project or `dist/` wholesale: a local checkout can contain personal settings, logs and videos.

The portable Windows release does not create a startup shortcut. Its automatic watcher is opt-in and must be started after signing in. The existing personal laptop installation has its own startup shortcut, independent of the public ZIP.

The macOS app is ad-hoc signed by PyInstaller, not Developer ID signed or notarized. Windows builds have no Authenticode publisher certificate. A future signed release requires the owner's signing identities and Apple notarization account; no certificate or account is created by this workflow.
