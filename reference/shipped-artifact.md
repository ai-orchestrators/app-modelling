# Shipped-artifact path: a built package

Model what actually ships. Use it on our own builds before launch, and on a client-owned app when the source is lost.

**Only on an artifact we or the client own.** Never on a third party's app.

## Contents
- Web build output
- Reading the results
- Android package
- iOS package
- Electron app
- When this is not enough
- What to write in the model

## Web build output

Run the bundled scanner on the build folder (`dist`, `build`, `.next`, `out`):

```bash
python3 scripts/bundle_scan.py dist
python3 scripts/bundle_scan.py dist --json > /tmp/bundle.json
```

It reports:

| Finding | Why it matters |
|---|---|
| Source map files and `sourceMappingURL` comments, inline maps included | They hand the original source to anyone who asks |
| Secret-shaped strings, masked | A server key in a client bundle is public |
| Public env names baked in | Shows what config the client build depends on |
| Hosts the bundle names | Every outside service the app calls, including ones nobody remembers adding |

It reads files as text, follows no symlinks, contacts nothing and writes nothing.

It exits 1 on source maps or secret-shaped strings. It also exits 1 with `INCOMPLETE` when it had to skip a file or scanned nothing. A skipped file has not been cleared, so check each one listed by hand.

## Reading the results

**Every hit is a lead, not a verdict.** Open the file at the line given.

- A public key that is meant to be public (a Supabase anon key, a Stripe publishable key, an analytics ID) is fine. Note it and move on.
- A secret, service-role or private key is not fine. If it shipped in any build, rotate it. Removing it from the bundle is not enough, because the old build is already out.
- A host nobody can explain gets a row under Uncertain.

Source maps are a choice, not always a fault. If the client wants them public for error tracking, record that decision. The default is off for production.

## Android package

An APK or AAB is a zip. List it without unpacking:

```bash
unzip -l app-release.apk | head -60
```

Record the size, the native libraries by CPU type under `lib/`, and anything under `assets/` that looks like config or data.

`AndroidManifest.xml` inside an APK is binary. If the Android build tools are installed, read it with:

```bash
aapt2 dump badging app-release.apk
aapt2 dump permissions app-release.apk
```

If `aapt2` is not on the PATH, record "manifest not read, aapt2 not installed" under Uncertain. Do not install tools from here.

Check every permission against a feature in the model. A permission with no feature behind it is a store-review risk and a finding.

## iOS package

An IPA is a zip with the app under `Payload/`.

```bash
unzip -l App.ipa | head -60
unzip -p App.ipa 'Payload/*.app/Info.plist' > /tmp/Info.plist && plutil -p /tmp/Info.plist
```

`plutil` ships with macOS. Record the bundle ID, version, minimum OS, URL schemes, and every `NS...UsageDescription` key. Each usage description must match a real feature, in plain words a reviewer will accept.

## Electron app

The app code is in `resources/app.asar`, or an unpacked `resources/app/` folder. If it is unpacked, run `bundle_scan.py` on that folder. Then treat the JavaScript inside as source and follow the source path, reading only.

Reading a packed `.asar` needs a tool that is not installed by default. Record that under Uncertain and ask before adding one.

## When this is not enough

Some jobs need more than a scan: a full module graph of a minified bundle, mapping a bundle position back to original source, or reading compiled code. Those need a dedicated reverse-engineering tool.

This skill does not ship one. Stop and tell the project owner what the job needs and why. Do not install one without their say-so, and never point one at an app we do not own.

## What to write in the model

Under `## Shipped artifact`:

1. What was scanned: path, build date or commit, size.
2. Findings table: finding, file and line, checked by opening it (yes or no), verdict.
3. Permissions or usage descriptions against features, for mobile.
4. Anything rotated or to rotate.
