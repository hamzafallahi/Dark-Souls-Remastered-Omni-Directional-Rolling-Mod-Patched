# DSROmniRoll – Launch-Build Port

A compatibility patch that makes **DSROmniRoll Standalone v1.01** (omnidirectional rolling for *Dark Souls Remastered*, [Nexus Mods #1378](https://www.nexusmods.com/darksoulsremastered/mods/1378)) work on the **2018-05-22 build** of `DarkSoulsRemastered.exe`.

On that build the original mod fails in one of three ways:

| Symptom | Cause |
|---|---|
| Game closes at startup; `DSROmniRoll_v1.01_Bridge.log` says `FATAL: DSR+0x82F790 is not the expected FF 25 XInput jump thunk` and an error message displays: `The system does not meet the minimum DX11 / Shader Model 5.0 GPU requirement to run the application`  | Every game address in the mod is for a newer build |
| With only that address fixed, the game crashes when you press **Continue** or load a save | Two more hardcoded game functions |
| With the crash fixed, **every roll goes forward**, whatever direction you press | The player data layout is 0x20 bytes shorter on this build |

This patch moves all of the mod's hooks to the matching code in the launch build and corrects the player-data offsets. After that, locked-on rolls follow your input.

## Requirements

- `DarkSoulsRemastered.exe` built **2018-05-22**, SHA-256
  `D18512DBA28E50A7F86C8D603EA972C85ECEF18A1455E85921110B24A95D614E`.
  (Check with PowerShell: `Get-FileHash DarkSoulsRemastered.exe`.)
  If your exe is the build the original mod supports (SHA-256 `A45AAA36…`, listed in its `CHECKSUMS_SHA256.txt`), you don't need this patch. Use the original mod as is.
- **DSROmniRoll Standalone v1.01** from Nexus Mods #1378, the zip containing `d3d11.dll` with SHA-256
  `978FCBDED962C9E7214E4A03E8CAF115C986E7831547962F88F149FD82020163`.
- Windows 10/11. The patcher uses Windows PowerShell, which is built in, so you don't need Python.

## Install

1. Install the original mod: put its `d3d11.dll` and `DSROmniRoll.ini` next to `DarkSoulsRemastered.exe`.
2. Copy `patcher\Patch-OmniRoll.bat` and `patcher\Patch-OmniRoll.ps1` into the same folder.
3. Double-click **`Patch-OmniRoll.bat`**.

The patcher:
- checks the exe and DLL hashes and refuses anything it doesn't recognize;
- saves the original as `d3d11.dll.orig`;
- patches `d3d11.dll` and checks the result hash (`A6CA05D7…0BBE`).

**Prebuilt option:** you can copy it over the mod's `d3d11.dll` instead of running the patcher. Its hash is in `prebuilt\SHA256.txt`.

### If the game closes right after startup

If the game closes and `DSROmniRoll_OFFLINE_GUARD_TRIGGERED.txt` appears next to the exe, the mod's offline guard has detected a session attempt. To let the game keep running, run this from a terminal in the game folder:

```
Patch-OmniRoll.bat -AllowSessionAttempt
```

It sets `TerminateOnSessionAttempt=0` in `DSROmniRoll.ini` and saves the old ini as `DSROmniRoll.ini.bak`. The mod's socket blocking (`BlockSockets=1`) stays on.

## Uninstall

- Run `Patch-OmniRoll.bat -Restore` to put the original DLL back.
- Or delete `d3d11.dll` and `DSROmniRoll.ini` to remove the mod completely.

## Mouse & keyboard and controller

- **Mouse & keyboard (tested):** locked-on rolls go in all 8 directions (W/A/S/D and the diagonals). Unlocked rolls are vanilla, since the game already rolls the way you move.
- **Controller (XInput, not yet tested on this build):** the original mod rolls at any analog angle on a controller. All of its XInput hooks are ported, and they install and report ready on this build, but no one has tested this patch with a physical controller yet. If you do, please report back (see *Reporting*).

## Playing

- Stay **offline**. The original mod's author asks for this, and its offline guard enforces it.
- Don't combine this standalone `d3d11.dll` with DS Mod Loader or ModEngine2 variants of the mod.

## Troubleshooting

The mod writes two logs next to the exe: `DSROmniRoll.log` (payload) and `DSROmniRoll_v1.01_Bridge.log` (bridge).

**A healthy start** shows these lines in the logs, with no `ERROR` or `FATAL` lines:
- in `DSROmniRoll.log`: `READY: raw XInput rear-half direction …`;
- in `DSROmniRoll_v1.01_Bridge.log`: `READY v1.01: …` and `Installed launch-safe device-agnostic input capture at the two native axis-query CALL sites`.

The only expected warning is `IsShowMenu entry did not match; menu bypass disabled …`. That one optional feature isn't ported yet, and rolling works without it.

**The bridge log prints stats lines every few seconds.** After some locked-on rolls, look for:

| Stat | Healthy value |
|---|---|
| `BRIDGE-STATS lock-changes=` | goes up when you lock and unlock |
| `NATIVE-INPUT-STATS captures=` / `keyboard-only-hits=` | goes up with each keyboard roll |
| `ROLL-WRITE-STATS payload-arm-seq=` / `commit-seq=` | goes up with each redirected roll |

**If the game crashes**, open Event Viewer → Windows Logs → Application and find the newest *Application Error* for `DarkSoulsRemastered.exe`. Include its **Exception code** and **Fault offset** in your report.

## Reporting

Open an issue with:
- your exe SHA-256;
- whether you use keyboard or controller;
- both log files;
- any crash code and offset.

Controller test reports are especially welcome.

## How it works

See [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md): the original mod's structure, why it breaks on this build, how every address was found, and how to port it to another build with the tools in `tools/`.

## Credits

- **DSROmniRoll** and all of its rolling logic: the original author, [Nexus Mods #1378](https://www.nexusmods.com/darksoulsremastered/mods/1378). This project only relocates its hooks for another game build. Please endorse the original.
- Launch-build port, patcher and documentation: **Hamza Fallahi**.
- The reverse engineering and the patch tooling were done with x64dbg, HxD, and a lot of help from Gemini xD.

## License

The patcher, the tools and the documentation in this repository are MIT-licensed (see [LICENSE](LICENSE)).

The original DSROmniRoll mod, and the patched `d3d11.dll` derived from it, are **not** covered by that license. They remain the original author's work.
