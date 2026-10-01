# Changelog

## 1.0.0 – 2026-10-01
First release. Ports DSROmniRoll Standalone v1.01 to the 2018-05-22 `DarkSoulsRemastered.exe` build (SHA-256 `D18512DB…614E`).

- Relocated all bridge and payload hooks to the launch build: XInput thunk, input/vector hooks, exact and alternate roll-flag sites, roll commit, animation-submit trace table and the axis-query CALL sites. This fixes `FATAL: DSR+0x82F790 is not the expected FF 25 XInput jump thunk`.
- Relocated the bridge's axis-query forwarders, `0x1A3700` → `0x19A6A0` and `0x1A3750` → `0x19A6F0`. This fixes the crash (`0xC000001D` at `+0x1A370C`) on Continue or when loading a save.
- Corrected the `PlayerIns` struct offsets: PlayerCtrl `+0x68` → `+0x48`, PadManipulator `+0x70` → `+0x50`. This fixes every locked-on roll going forward.
- Relocated the `.data` globals: WorldChrMan, SessionManager, MenuMan.
- Added the PowerShell patcher (hash-checked, with backup and `-Restore`) and an optional `-AllowSessionAttempt` switch.

Known limitations: the IsShowMenu menu bypass isn't ported (the mod logs a warning and works without it). Controller play hasn't been tested on this build yet.
