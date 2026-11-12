# Brief: Studio Control iOS - one device module (SwiftUI)

You write ONE (or two) device file(s) for a native iPhone app (SwiftUI, iOS 16+, Swift 5 language mode,
Xcode 16/26). There is NO Swift compiler here; the code is compiled later on a GitHub macOS runner.
So write conservative, simple, compile-safe Swift. Double-check every API name, every optional,
every `try`/`await`, every type conversion (Int vs Int64 vs UInt16 vs Double), closures capturing self
in @MainActor classes, and SwiftUI view builder rules (no `let` statements with side effects inside
`body`, every `if` branch returns a View, max ~10 direct children per ViewBuilder -> use Group/Section).

## Reference implementation (source of truth for the protocols)
`/tmp/claude-0/-home-claude/777f24ec-5a9c-531d-87b5-cc5c9fc70e93/scratchpad/ios/sc.py` (Python/Tkinter,
12.7k lines). Your task names the line range of your module. Port the device protocol EXACTLY (same
commands, bytes, URLs, headers, OIDs, JSON keys, defaults, timing). Do not invent protocol details.
If something cannot work on iOS (e.g. UDP broadcast needs a special Apple entitlement; raw audio
metering), leave it out and say so in your report. Settings defaults (IP, port, user) = the Python defaults.

## Core API you MUST use (read these files first, do NOT edit them)
/home/claude/studio-ios/Sources/Core/Net.swift        TCPConnection, UDPExchange, HTTPClient, makeURL, Data(hex:), .hex, pause()
/home/claude/studio-ios/Sources/Core/Crypto.swift     Crypto.sha256/sha1/md5, aesCBC, aesECB, aesCTR, aesCCMDecrypt, random
/home/claude/studio-ios/Sources/Core/SNMP.swift       SNMPClient(host:community:).get/getNext/walk/set
/home/claude/studio-ios/Sources/Core/Store.swift      SecureStore.loadCodable/saveCodable (settings as Codable struct)
/home/claude/studio-ios/Sources/Core/DeviceModel.swift  base class DeviceModel (@MainActor ObservableObject)
/home/claude/studio-ios/Sources/Core/UI.swift         DevicePage, StatusCard, ActionTile, TileGrid, ValueRow, LevelBar,
                                                      PowerToggleRow, SettingsSheet, FieldRow, intBinding, Color(hex:)
/home/claude/studio-ios/Sources/App/StudioApp.swift   how models/views are registered (class + view names are fixed there)

## What to write: Sources/Devices/<Name>.swift containing
1. `struct <Name>Settings: Codable` with defaults (use `var x: T = default` so decoding old data works;
   add `init(from:)` with `decodeIfPresent` for every key so new keys never break old saved settings).
2. A protocol client (struct/class, async/await) - pure networking, no UI.
3. `@MainActor final class <Name>Model: DeviceModel` with
   - `init()` calling `super.init(id: "<id>", title: "...", subtitle: "...", symbol: "<SF Symbol>", tint: Color(hex: ...))`
   - `@Published var settings = <Name>Settings()` + override `loadSettings()` (SecureStore.loadCodable(..., "<id>"))
     and `saveSettings()`
   - override `isConfigured` (e.g. `!settings.ip.trimmed.isEmpty`), `pollInterval` if needed
   - override `refresh()` using `await refreshSafely { ... }`; set `summary` (short tile text, German)
   - actions as methods using `perform("German log text") { ... }` (then refresh)
   - override `disconnect()` if you keep a connection open
   - scene support only where the task says so (`supportsScene`, `scene(_ on:)`)
4. `struct <Name>View: View { @ObservedObject var model: <Name>Model; var body: some View { DevicePage(model: model, settings: { <Name>SettingsView(model: model) }) { Section(...) {...} ... } } }`
   Design: native iOS look (inset grouped list, SF Symbols, ActionTile grids in a Section, Toggles,
   Sliders with onEditingChanged to send only on release, Pickers). German UI texts (ASCII umlauts are
   NOT required in UI strings - use real umlauts in UI text; code comments ASCII only).
5. `struct <Name>SettingsView: View` using `SettingsSheet(title:onSave:)` + `FieldRow`, editing a local
   `@State var s: <Name>Settings` initialised from model.settings (init(model:) { _s = State(initialValue: model.settings) }),
   onSave -> `model.settings = s; model.saveSettings()`.

## Rules
- Only Foundation, SwiftUI, Network, CryptoKit, CommonCrypto, UIKit. No third-party packages.
- No global names that could collide: prefix helpers with the device name, or nest them.
- Never block the main thread (no sleep loops without await; use `await pause(x)`).
- Keep a persistent TCP connection only if the protocol needs it; reconnect on failure; guard concurrent
  commands (serialize with a simple `isSending` flag or an actor).
- `Color(hex: 0xRRGGBB)` exists. SF Symbols must exist in iOS 16 (use common ones: projector? -> use
  "videoprojector" (iOS 16+), "powerplug", "mic.fill", "rectangle.on.rectangle", "network", "wifi.router",
  "printer.fill", "rectangle.grid.2x2.fill", "speedometer", "server.rack").
- Code comments ASCII only. File header comment: name, "Autor: T. Pfeiffer".
- When done, re-read your whole file once purely as a compiler would (types, optionals, missing awaits,
  `try` on throwing calls, `self.` in escaping closures, exhaustive switches) and fix.

## Report (< 250 words)
File(s) written, features, what you could NOT port (and why), protocol points you are unsure of.
