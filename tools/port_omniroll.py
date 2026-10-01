"""Port DSROmniRoll Standalone v1.01 (d3d11.dll) to the 2018-05-22 DarkSoulsRemastered.exe build.

This is the source of truth for the port: every byte the patch changes is derived and checked here.

usage:
  python port_omniroll.py --orig <original d3d11.dll> --out <patched d3d11.dll> [--emit-ps1 <Patch-OmniRoll.ps1>]

  --orig      the original DSROmniRoll Standalone v1.01 d3d11.dll (SHA-256 978FCBDE...0163)
  --out       where to write the patched DLL
  --emit-ps1  also regenerate the PowerShell patcher from Patch-OmniRoll.template.ps1 (next to this script)

Site map (original target build RVA -> this build RVA), verified against a runtime memory dump, because Arxan
decrypts most of .text only at runtime:
  XInputGetState jmp thunk   0x82F790 -> 0x81F85C   (-0xFF34)
  roll direction/vector fns  0x396860, 0x397E00, 0x397E82, 0x398175, 0x3985E0, 0x3989C4/D1  (-0x8D20)
  axis-query callees         0x1A3700 -> 0x19A6A0, 0x1A3750 -> 0x19A6F0  (bridge forwarders)
  roll-flag commit function  0x398E4F, 0x3991A1, 0x398FD4..0x3990B5 table  (-0x8D30)
  animation submit traces    0x37A040/120/170  (-0x8DA0)
  roll commit                0x385550 -> 0x37C780 (-0x8DD0)
  .data singletons           WorldChrMan 0x1C77E50, SessionManager 0x1C7D010 (+0x769E0), MenuMan 0x1C88D98 (+0x76A30)
  PlayerIns struct           PlayerCtrl +0x68 -> +0x48, PadManipulator +0x70 -> +0x50
  IsShowMenu 0x71AC10: not located; the bridge logs a warning and runs without its menu bypass.
See docs/HOW_IT_WORKS.md for how each entry was found.
"""
import argparse, hashlib, os, struct
import capstone

ORIG_SHA256 = '978fcbded962c9e7214e4a03e8caf115c986e7831547962f88f149fd82020163'
EXE_SHA256 = 'd18512dba28e50a7f86c8d603ea972c85ecef18a1455e85921110b24a95d614e'
PAYLOAD_FILE_OFF = 0x5640          # embedded payload PE inside d3d11.dll
BASE = 0x180000000

# (va, raw, size) per section
BRIDGE_SECS = [(0x1000, 0x400, 0x5200), (0x7000, 0x5600, 0x12c00), (0x1a000, 0x18200, 0x200)]
PAYLOAD_SECS = [(0x1000, 0x400, 0xf200), (0x11000, 0xf600, 0x1600), (0x13000, 0x10c00, 0x200)]
BRIDGE_TEXT = (0x1000, 0x400, 0x51c0)
PAYLOAD_TEXT = (0x1000, 0x400, 0xf0ef)


def file_off(va, secs, extra=0):
    rva = va - BASE
    for sva, raw, size in secs:
        if sva <= rva < sva + size:
            return extra + raw + rva - sva
    raise ValueError(hex(va))


def u32(v):
    return struct.pack('<I', v & 0xffffffff)


# code immediates/displacements to relocate: old value -> new value
BRIDGE_CODE = {
    0x82F790: 0x81F85C, 0x82F791: 0x81F85D, 0x82F792: 0x81F85E, 0x82F796: 0x81F862,
    0x3989C4: 0x38FCA4, 0x3989D1: 0x38FCB1,
    **{0x398E4F + i: 0x39011F + i for i in range(7)},
    0x3991A1: 0x390471,
    0x1C88D98: 0x1CFF7C8,
    # original callees of the two axis-query CALL sites, forwarded to by the bridge's replacement stubs
    0x1A3700: 0x19A6A0, 0x1A3750: 0x19A6F0,
}
PAYLOAD_CODE = {
    0x396860: 0x38DB40, 0x397E00: 0x38F0E0, 0x397E82: 0x38F162, 0x398175: 0x38F455, 0x3985E0: 0x38F8C0,
    0x398E4F: 0x39011F,
    0x385550: 0x37C780,
    0x1C77E50: 0x1CEE830, 0x1C7D010: 0x1CF39F0,
    # 0x37A040/120/170 stay: the bridge verifies that payload code byte-for-byte and neuters those traces itself
}
EXPECTED_CODE_HITS = {'bridge': 20, 'payload': 12}

# base-relative constants deliberately left alone (see docstring)
KNOWN_UNPORTED = {0x71AC10, 0x319B000, 0x37A040, 0x37A120, 0x37A170}
GAME_BASE_SLOTS = {'bridge': 0x18001A028, 'payload': 0x1800130D8}

# bridge .rdata tables: (va, old bytes, new bytes, note)
BRIDGE_DATA = [
    (0x180018358, b''.join(map(u32, (0x37A040, 0x37A120, 0x37A170))),
     b''.join(map(u32, (0x3712A0, 0x371380, 0x3713D0))), 'animation submit trace sites'),
    (0x1800183A0, b''.join(map(u32, (0x398FD4, 0x399001, 0x39902A, 0x399060, 0x399079, 0x399099, 0x3990B5))),
     b''.join(map(u32, (0x3902A4, 0x3902D1, 0x3902FA, 0x390330, 0x390349, 0x390369, 0x390385))),
     'exact roll-flag commit sites'),
    (0x1800183CA, bytes.fromhex('e837ade0ff e87aade0ff'.replace(' ', '')),
     bytes.fromhex('e8f7a9e0ff e83aaae0ff'.replace(' ', '')), 'axis-query CALL rel32 templates'),
]

# PlayerIns header is 0x20 shorter in this build: PlayerCtrl +0x68 -> +0x48, PadManipulator +0x70 -> +0x50
# (WorldChrMan+0x68 -> PlayerIns is unchanged; inner PlayerCtrl/PadManipulator offsets are unchanged)
PAYLOAD_STRUCT = [
    (0x18000ACFF, '488d7e70', '488d7e50', 'resolver: PlayerIns->PadManipulator'),
    (0x18000AD2D, '488d5e68', '488d5e48', 'resolver: PlayerIns->PlayerCtrl'),
    (0x18000F420, '4883c768', '4883c748', 'PlayerIns->PlayerCtrl'),
    (0x18000FC25, '4883c668', '4883c648', 'PlayerIns->PlayerCtrl'),
]

# log text only, so the log names the address actually hooked
LOG_STRINGS = [(b'DSR+0x82F790', b'DSR+0x81F85C')]


def relocate_code(d, name, text, extra, table):
    va0, raw, size = text
    off0 = extra + raw
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    hits = 0
    for x in md.disasm(bytes(d[off0:off0 + size]), BASE + va0):
        ib = x.bytes
        for old, new in table.items():
            k = ib.find(u32(old))
            if k < 0:
                continue
            off = off0 + (x.address - BASE - va0) + k
            d[off:off + 4] = u32(new)
            hits += 1
            print(f'{name:7} {x.address:#x} {old:#09x} -> {new:#09x}  {x.mnemonic} {x.op_str}')
    assert hits == EXPECTED_CODE_HITS[name], f'{name}: {hits} code relocations, expected {EXPECTED_CODE_HITS[name]}'


def check_base_relative(d, name, text, extra, ported):
    """Fail if code near a game-base load still uses a game-sized constant that is neither ported nor known."""
    va0, raw, size = text
    off0 = extra + raw
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    ins = list(md.disasm(bytes(d[off0:off0 + size]), BASE + va0))
    base_near = set()
    for i, x in enumerate(ins):
        for op in x.operands:
            if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP \
                    and x.address + x.size + op.mem.disp == GAME_BASE_SLOTS[name]:
                base_near.update(range(max(0, i - 3), min(len(ins), i + 7)))
    bad = []
    for i in sorted(base_near):
        x = ins[i]
        for op in x.operands:
            v = op.imm if op.type == capstone.x86.X86_OP_IMM else \
                op.mem.disp if op.type == capstone.x86.X86_OP_MEM and op.mem.base != capstone.x86.X86_REG_RIP else None
            if v is not None and 0x10000 <= v < 0x4869400 and v not in ported and v not in KNOWN_UNPORTED:
                bad.append(f'{x.address:#x} {x.mnemonic} {x.op_str}')
    assert not bad, f'{name}: unported base-relative constants:\n  ' + '\n  '.join(bad)
    print(f'{name}: base-relative self-check ok ({len(base_near)} instructions near game-base loads)')


def port(orig):
    d = bytearray(orig)
    relocate_code(d, 'bridge', BRIDGE_TEXT, 0, BRIDGE_CODE)
    relocate_code(d, 'payload', PAYLOAD_TEXT, PAYLOAD_FILE_OFF, PAYLOAD_CODE)
    for va, old, new, note in BRIDGE_DATA:
        off = file_off(va, BRIDGE_SECS)
        assert bytes(d[off:off + len(old)]) == old, note
        d[off:off + len(new)] = new
        print(f'bridge  {va:#x} data  {note}')
    for va, old, new, note in PAYLOAD_STRUCT:
        off = file_off(va, PAYLOAD_SECS, PAYLOAD_FILE_OFF)
        old, new = bytes.fromhex(old), bytes.fromhex(new)
        assert bytes(d[off:off + len(old)]) == old, note
        d[off:off + len(new)] = new
        print(f'payload {va:#x} {old.hex()} -> {new.hex()}  {note}')
    check_base_relative(d, 'bridge', BRIDGE_TEXT, 0, set(BRIDGE_CODE.values()))
    check_base_relative(d, 'payload', PAYLOAD_TEXT, PAYLOAD_FILE_OFF, set(PAYLOAD_CODE.values()))
    for old, new in LOG_STRINGS:
        d = d.replace(old, new)
    return bytes(d)


def diff_runs(a, b, gap=4):
    """Contiguous changed-byte runs (merging runs closer than `gap`) as (offset, old, new)."""
    changed = [i for i in range(len(a)) if a[i] != b[i]]
    groups = []
    for i in changed:
        if groups and i - groups[-1][1] <= gap:
            groups[-1][1] = i
        else:
            groups.append([i, i])
    return [(s, a[s:e + 1], b[s:e + 1]) for s, e in groups]


def emit_ps1(orig, patched, out_path):
    here = os.path.dirname(os.path.abspath(__file__))
    tpl = open(os.path.join(here, 'Patch-OmniRoll.template.ps1'), encoding='utf-8').read()
    rows = ',\n'.join(f"    @(0x{o:05X}, '{old.hex().upper()}', '{new.hex().upper()}')"
                      for o, old, new in diff_runs(orig, patched))
    out = (tpl.replace('@@PATCH_TABLE@@', rows)
              .replace('@@ORIG_SHA256@@', ORIG_SHA256.upper())
              .replace('@@PATCHED_SHA256@@', hashlib.sha256(patched).hexdigest().upper())
              .replace('@@EXE_SHA256@@', EXE_SHA256.upper()))
    assert '@@' not in out, 'unfilled template marker'
    with open(out_path, 'w', encoding='utf-8-sig', newline='\r\n') as f:   # BOM: PowerShell 5.1 reads UTF-8 safely
        f.write(out)
    print(f'wrote {out_path} ({len(diff_runs(orig, patched))} patch runs)')


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--orig', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--emit-ps1')
    a = ap.parse_args()
    orig = open(a.orig, 'rb').read()
    h = hashlib.sha256(orig).hexdigest()
    assert h == ORIG_SHA256, f'{a.orig} is not DSROmniRoll Standalone v1.01 (SHA-256 {h})'
    patched = port(orig)
    open(a.out, 'wb').write(patched)
    print(f'wrote {a.out}  SHA-256 {hashlib.sha256(patched).hexdigest().upper()}')
    if a.emit_ps1:
        emit_ps1(orig, patched, a.emit_ps1)


if __name__ == '__main__':
    main()
