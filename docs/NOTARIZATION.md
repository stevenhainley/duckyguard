# Signing and notarizing DuckyGuard (when an Apple Developer ID exists)

Today the app ships unsigned (ad-hoc signature only), so users must use the
Gatekeeper override in `docs/INSTALL.md`. With a paid Apple Developer Program
membership ($99/year) the steps below make the app open with no warning and
let TCC remember its permissions across updates.

## One-time setup

1. Enroll at developer.apple.com and create a **Developer ID Application**
   certificate in Xcode (Settings, Accounts, Manage Certificates) or in the
   developer portal. Install it in the login keychain.
2. Create an app-specific password at appleid.apple.com, then store the
   notarization credentials once:
   ```bash
   xcrun notarytool store-credentials "duckyguard-notary" \
     --apple-id "<apple id email>" --team-id "<TEAMID>" --password "<app-specific password>"
   ```
3. Find the signing identity name:
   ```bash
   security find-identity -v -p codesigning | grep "Developer ID Application"
   ```

## Entitlements

DuckyGuard embeds a Python runtime that loads compiled extension modules, so
the hardened runtime needs these entitlements (`packaging/entitlements.plist`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>com.apple.security.cs.allow-unsigned-executable-memory</key><true/>
  <key>com.apple.security.cs.disable-library-validation</key><true/>
</dict></plist>
```

No sandbox entitlement: an App Sandbox app cannot create a CGEvent tap, so
DuckyGuard cannot be sandboxed (and therefore cannot be in the Mac App Store
in its current form).

## Build, sign, notarize, staple

```bash
./packaging/build.sh                       # unsigned dist/DuckyGuard.app + DMG
IDENTITY="Developer ID Application: Steven Hainley (TEAMID)"

# Sign every Mach-O inside out, then the bundle, with the hardened runtime.
codesign --force --options runtime --timestamp --entitlements packaging/entitlements.plist \
  --sign "$IDENTITY" --deep dist/DuckyGuard.app
codesign --verify --deep --strict --verbose=2 dist/DuckyGuard.app

# Rebuild the DMG from the signed app (build.sh does this; or run its dmg step), then:
xcrun notarytool submit dist/DuckyGuard-2.0.0.dmg --keychain-profile "duckyguard-notary" --wait
xcrun stapler staple dist/DuckyGuard-2.0.0.dmg
xcrun stapler staple dist/DuckyGuard.app
spctl --assess --type open --context context:primary-signature -v dist/DuckyGuard-2.0.0.dmg
```

`--deep` is discouraged by Apple for complex bundles; if notarization rejects
a nested binary, sign the Python framework and each `.so` under
`Contents/Resources/lib` explicitly first, then the main executable.

## After signing

- `docs/INSTALL.md`: remove the Gatekeeper section.
- Permissions: TCC ties grants to the signing identity. Users upgrading from
  the unsigned build will have to re-grant Input Monitoring and Accessibility
  once. Say so in the release notes.
- Launch at login can move from the LaunchAgent plist to `SMAppService` (macOS
  13+), which shows DuckyGuard by name in System Settings, Login Items.
- Updates: a signed app can safely add an in-app updater (Sparkle with
  EdDSA-signed appcasts). Until then the opt-in check only shows a notice.
