# How the launch-build port works

This document explains the original DSROmniRoll Standalone v1.01, why it fails on the 2018-05-22 build of `DarkSoulsRemastered.exe`, how each address and offset was found, and how to repeat the process for another build. All addresses are RVAs (offsets from the module base, `0x140000000` for the game).

| Build | `DarkSoulsRemastered.exe` SHA-256 | Notes |
|---|---|---|
| **Target** (what the mod was written for) | `A45AAA36DD2F6CC151670A639EA5547043CF38EA79FF4178B963C6ED71F98D7B` | |
| **Launch** (what this patch supports) | `D18512DBA28E50A7F86C8D603EA972C85ECEF18A1455E85921110B24A95D614E` | PE timestamp `0x5B045F22` |

---

## 1. What the original mod is

`d3d11.dll` (100,352 bytes, SHA-256 `978FCBDE…0163`) is a proxy DLL that the game loads instead of the system `d3d11.dll`. It has two parts:

1. **Bridge:** the DLL itself, called the "device-agnostic input bridge" in its log. It:
   - forwards the real Direct3D 11 exports;
   - maps the payload;
   - hooks XInput and keyboard movement;
   - adds relays that redirect locked-on rolls.
2. **Embedded payload:** a complete PE image stored inside the bridge's `.rdata` at **file offset `0x5640`**. It's the "legacy gameplay payload": SizeOfImage `0x37000`, entry point `0x14A0`, no import table. The bridge maps it at runtime, and the payload installs the actual gameplay hooks.

The bridge also patches about ten instructions inside the payload after mapping it. Those are logged as "Neutralized legacy probe-reset instruction", "Extended legacy … window to 96 frames", and so on. Before each patch it verifies the payload bytes, so **the payload can't be edited freely**: any byte the bridge verifies must stay as it is. One region is verified as a whole: payload `+0xC340`, `0x8A` bytes, which contains the immediates `0x37A040`/`0x37A120`/`0x37A170`.

### Runtime flow

| Step | What happens |
|---|---|
| Bridge start | Validates the game's **XInputGetState jump thunk** (`FF 25 rel32`, a jump through the import table) and swaps the import-table slot for its own XInput function. That function can build an XInput state from keyboard movement. |
| Payload start | Installs a Winsock deny hook (offline guard). Waits for `SessionManager` to report "no session". Waits until the protected (Arxan) game code is decrypted in memory, detected by two probe functions changing bytes. |
| Payload hooks | Input hook, raw-XInput rear-vector hook, pre-correction vector probe, the **exact roll-direction write** (`mov byte [rdi+93h],1 ; or byte [rdi+1C4h],1`), and the roll-commit hook. Each one byte-checks the original instructions and installs a hand-assembled trampoline that replays them. |
| Bridge relays | The game has seven more "roll accepted" writes (`[rdi+94h]`, `+95h`, `+96h`, `+AEh` …). The bridge routes them through a relay that, when locked on (`[PadManipulator+220h]` holds a target handle), turns them into the forward-roll flag plus a **direction lease**. |
| Direction source | The bridge hooks the two **axis-query CALL sites** that produce the game's merged movement vector (keyboard or stick) and caches that vector for one frame. During an accepted roll, the payload asks for "XInput". The bridge answers from that cache, which is why keyboard works. |
| Commit | The payload rotates the roll to the leased direction (the "roll-scoped Havok yaw hold") and counts the commit. |

The payload finds the player every 50 ms through a pointer chain:

```
[DSR + WorldChrMan] + 0x68  -> PlayerIns
PlayerIns + <PadManipulator slot>   (lock-on target handle at +0x220)
PlayerIns + <PlayerCtrl slot>       (+0x28 Havok character, +0x48 ActionCtrl)
```

The bridge reads the cached PadManipulator pointer to know whether you're locked on.

---

## 2. Why it fails on the launch build

Everything above is pinned to the target build:
- about 30 code addresses in the bridge and payload;
- three `.data` globals;
- two struct offsets in `PlayerIns`.

The launch build was compiled from slightly different code, so functions moved by different amounts. The first check to fail is the XInput thunk at `0x82F790`, which is where the original FATAL comes from.

### Arxan: the exe on disk is not the code that runs

DSR's executable is protected with Arxan. **1,699 pages of `.text` differ between the file on disk and the running process**, because whole functions are stored encrypted and decrypted at runtime. Signature searches against the exe file therefore fail for sites that exist at runtime. The roll functions at `0x38F0E0`, `0x38F162`, `0x38F455` and `0x38F8C0` are random bytes on disk.

**All matching in this port was done against a memory dump of the running game.**

---

## 3. Method

The tools are in `tools/`: `mem.py` reads the running game's memory without changing it, and `port_omniroll.py` builds the patch.

1. **List every hardcoded game address.**
   - Disassemble the bridge's `.text` and the payload's `.text` with capstone.
   - Collect immediates and displacements used together with the loaded game base. The game base is stored at `bridge+0x1A028` and `payload+0x130D8`.
   - Also scan both images' data for tables of RVAs. The bridge has three: trace sites at `+0x18358`, seven roll-flag sites at `+0x183A0`, and CALL rel32 templates at `+0x183CA`.
2. **Rebuild the expected bytes for each site.** Every hook checks the original bytes with a `cmp byte ptr [rsi+N], imm` chain, or with a template passed to a hook installer. Reading those chains gives a byte signature per site.
3. **Dump the running game:** `python tools/mem.py dump runtime.bin`, taken after the payload logs that protected code is unpacked.
4. **Search the signatures** in the dump near the old address. Most sites match exactly, once each, with a consistent shift for each function group.
   - Generic prologues (`48 8B C4 …`) are only accepted when they sit at the same shift as their neighbours.
   - The roll-flag function was checked structurally: all of its `c6 87 XX 00 00 00 01 80 8f c4 01 00 00 01` writes jump to one shared join.
5. **Name the `.data` globals with RTTI:** `python tools/mem.py rtti`.
   - For every pointer in `.data`, it follows object → vtable → `vtable[-1]` (complete object locator) → type descriptor → class name.
   - That identified `FrpgSessionManagerImp`, `MenuMan`, and, once a save is loaded, `WorldChrManImp`.
6. **Check struct offsets live.** With a save loaded, walk the payload's pointer chain and name each object with RTTI. A field that names the wrong class, or no class, is a shifted struct.
7. **Patch and self-check.**
   - `port_omniroll.py` rewrites each value only inside a decoded instruction, and asserts the exact number of hits.
   - It asserts the old bytes of every data patch.
   - It then re-disassembles and fails if any game-sized constant near a game-base load is neither ported nor on an explicit "left alone" list.

---

## 4. Site map

| Purpose | Target RVA | Launch RVA | Shift |
|---|---|---|---|
| XInputGetState `FF 25` thunk | `0x82F790` | `0x81F85C` | −0xFF34 |
| Input hook (function prologue) | `0x396860` | `0x38DB40` | −0x8D20 |
| Unpack probe / callable function | `0x397E00` | `0x38F0E0` | −0x8D20 |
| Raw XInput rear-vector hook | `0x397E82` | `0x38F162` | −0x8D20 |
| Pre-correction vector probe | `0x398175` | `0x38F455` | −0x8D20 |
| Unpack probe function | `0x3985E0` | `0x38F8C0` | −0x8D20 |
| Axis-query CALL sites | `0x3989C4` / `0x3989D1` | `0x38FCA4` / `0x38FCB1` | −0x8D20 |
| Axis-query callees (called by the bridge's forwarders) | `0x1A3700` / `0x1A3750` | `0x19A6A0` / `0x19A6F0` | −0x9060 |
| Exact roll-direction write (`+93h`) | `0x398E4F` | `0x39011F` | −0x8D30 |
| Seven alternate roll-flag writes | `0x398FD4 … 0x3990B5` | `0x3902A4 … 0x390385` | −0x8D30 |
| Roll-flag join | `0x3991A1` | `0x390471` | −0x8D30 |
| Animation-submit traces | `0x37A040` / `0x37A120` / `0x37A170` | `0x3712A0` / `0x371380` / `0x3713D0` | −0x8DA0 |
| Roll commit | `0x385550` | `0x37C780` | −0x8DD0 |
| `WorldChrManImp*` | `0x1C77E50` | `0x1CEE830` | +0x769E0 |
| `FrpgSessionManagerImp*` | `0x1C7D010` | `0x1CF39F0` | +0x769E0 |
| `MenuMan*` | `0x1C88D98` | `0x1CFF7C8` | +0x76A30 |
| IsShowMenu | `0x71AC10` | not found | optional |

The trace-site immediates inside the payload are **not** changed, because the bridge verifies those payload bytes and disables the traces itself. Only the bridge's own trace-site table is relocated.

The two CALL sites are also listed in a bridge template as raw `E8 rel32` bytes. Those were updated to the launch build's bytes: `E8 F7 A9 E0 FF` and `E8 3A AA E0 FF`.

### PlayerIns layout

| Field | Target | Launch |
|---|---|---|
| `PlayerIns → PlayerCtrl` | `+0x68` | `+0x48` |
| `PlayerIns → PadManipulator` | `+0x70` | `+0x50` |

`WorldChrMan+0x68 → PlayerIns`, `PadManipulator+0x220` (lock-on target handle) and `PlayerCtrl+0x48` (`ActionCtrl`) are unchanged.

Patched instructions (payload VAs): `0x18000ACFF` `lea rdi,[rsi+70h]` → `50h`; `0x18000AD2D`, `0x18000F420` and `0x18000FC25`: `+68h` → `+48h`.

---

## 5. The three failures and how each was diagnosed

**1. `FATAL: DSR+0x82F790 is not the expected FF 25 XInput jump thunk.`**
- The import table shows that `XINPUT1_3` ordinal 2 (XInputGetState) is reached through `jmp [rip+…]` at `0x81F85C`.
- The check uses five displacements (`0x82F790`, `…791`, `…792`, and `…796` twice), not one. Patching only the visible `90 F7 82 00` would have passed the check and then read the import-table slot from the wrong place.

**2. Crash on Continue: `0xC000001D` (illegal instruction) at `DSR+0x1A370C`.**
- From the Windows Application event log: six identical crashes.
- The two CALL sites only run once a character is in the world. The bridge's replacement stubs forwarded to `base+0x1A3700` / `base+0x1A3750`, the target build's callees, which are mid-instruction bytes on the launch build.
- The real callees come from decoding the launch build's `E8` rel32 at the CALL sites.
- The address sweep was then extended to every base-relative constant, which led to the self-check in `port_omniroll.py`.

**3. Every locked-on roll goes forward.**
- The bridge stats showed:
  - `scope-failures` equal to `scope-samples`: the bridge never knew the player was locked on;
  - `captures=0` even though keyboard axes were being sampled;
  - `payload-arm-seq=0`.
- The bridge's lock reader uses the payload's cached PadManipulator pointer, and that pointer was never set.
- A live RTTI walk showed `PlayerIns+0x48 = PlayerCtrl` and `+0x50 = PadManipulator` on this build, 0x20 earlier than the payload expects. After the fix, a test run showed `lock-changes=15 captures=47 keyboard-only-hits=47 payload-arm-seq=47 commit-seq=28`, and the rolls followed the keys.

---

## 6. Telemetry reference (bridge log)

| Stat | Meaning |
|---|---|
| `BRIDGE-STATS scope-samples / scope-failures` | Lock-state reads, and how many failed. Failures are expected only before a character is loaded. |
| `BRIDGE-STATS lock-state / lock-changes` | Current lock state, and how many times it has changed. |
| `BRIDGE-STATS game-calls / success` | How often the game polled XInput, and how many polls succeeded. `success=0` just means no controller is connected. |
| `NATIVE-INPUT-STATS axis1/axis2-samples, last-raw` | Movement vectors captured at the CALL sites. `last-raw=(23169,23169)` is a diagonal. |
| `NATIVE-INPUT-STATS captures, keyboard-only-hits, provider-hits` | Rolls that received a captured direction. |
| `ROLL-WRITE-STATS late-total / locked / unlocked` | Hits per alternate roll-flag site. |
| `ROLL-WRITE-STATS payload-arm-seq / commit-seq` | Rolls armed with a direction, and rolls committed with it. |

---

## 7. Porting to another build

1. Install the original mod and launch once. Note the first `FATAL` or `ERROR` in the logs.
2. If the payload shuts the game down before you can dump memory, build a test copy with the SessionManager wait made endless.
   - The wait is `cmp eax, 0C8h` at payload `0x180002C09` (file offset `0x7649`); raise the immediate.
   - The public `port_omniroll.py` has no switch for this, so make the change in a copy.
3. Run `python tools/mem.py dump runtime.bin`. Search each site's signature (section 3, step 2) near the target RVA, and record the shift.
4. With a save loaded, run `python tools/mem.py rtti` and walk `WorldChrMan → PlayerIns` to check the struct slots.
5. Change the tables at the top of `tools/port_omniroll.py`:
   - the hashes;
   - `BRIDGE_CODE`, `PAYLOAD_CODE`, `BRIDGE_DATA`, `PAYLOAD_STRUCT`;
   - `EXPECTED_CODE_HITS`.
6. Rebuild: `python tools/port_omniroll.py --orig <original> --out d3d11.dll --emit-ps1 patcher/Patch-OmniRoll.ps1`. The base-relative self-check has to pass.
7. Test in game in this order:
   1. the title screen logs show READY and no errors;
   2. Continue loads without a crash;
   3. the stats increase while you do locked-on rolls.

`tools/mem.py` hardcodes the launch build's image size and `.data` range (`SIZE`, `DATA_LO`, `DATA_HI`). Update them from the PE section table for another build.
