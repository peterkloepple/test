# Review brief: Studio Control iOS v1.1.0 - bug check of one or two device files

Project: native iPhone app (SwiftUI, iOS 16+, Swift 5 mode) in /home/claude/studio-ios. It compiles on a
GitHub macOS runner and runs in the simulator with demo data, but has NEVER been tested against the real
devices. No Swift compiler here: every edit must be conservative and compile-safe. Read AGENT_BRIEF.md
(rules, core API) first. Reference implementation (source of truth for protocols): the Python app
/tmp/claude-0/-home-claude/777f24ec-5a9c-531d-87b5-cc5c9fc70e93/scratchpad/ios/sc.py (line ranges per device are in your task).

## Task for each of your files in Sources/Devices/
1. BUG REVIEW: read the whole Swift file and the matching Python module. Look for REAL defects that would
   show on the real device or for the user: wrong command/bytes/URL/header/OID/JSON key vs Python, wrong
   parsing, off-by-one, wrong units, state not updated after an action, UI showing stale/wrong value,
   toggles that fire the action again when the model updates them (feedback loops), races between poll and
   action, connection leaks, tasks not cancelled, missing timeout, blocking the main actor with long work,
   crashes (force unwrap, index out of range, division by zero), settings not saved/loaded, missing
   confirmation before a destructive action. Fix every confirmed defect with the smallest safe change.
   Do NOT refactor, restyle or rename. Do not touch loadDemo() except to keep it compiling.
2. QUICK ACTIONS: in the model class add
   `override var quickActions: [QuickAction] { ... }` (QuickAction is defined in Sources/Core/DeviceModel.swift:
   `QuickAction(id:title:symbol:destructive:run:)`, `run` is `() -> Void` called on the main actor; use the
   model's existing action methods inside, e.g. `{ [weak self] in self?.setPower(true) }`). 2-4 actions that
   make sense from the home screen WITHOUT confirmation dialogs (no reboot/cleaning/POFF), German titles
   with real umlauts, existing SF Symbols. Examples: Beamer "Einschalten"/"Ausschalten"/"Bild schwarz";
   Tapo "Alle an"/"Alle aus"; Mics "Alle stumm"/"Alle offen"; Speedtest "Messung starten";
   Fritz/Speedport/Switch/ClickShare/Printer: only harmless ones (e.g. "Aktualisieren", "Standby",
   "Dusentest" is NOT harmless). If an action needs a connection that only exists while the page is open,
   make the quick action connect first (or leave it out).
3. Only edit your own file(s). Do not edit Core/, App/, project.yml, workflow.
4. Re-read every changed region as a compiler would (types, optionals, try/await, self capture).

## Report (< 200 words, German or English)
Per file: bugs found + fixed (one line each, with why it mattered), quick actions added, anything you
suspect but could not verify without hardware.
