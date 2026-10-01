"""Read-only live memory helpers for DarkSoulsRemastered.exe.

python mem.py dump <out.bin>          dump the mapped image (base 0x140000000)
python mem.py rtti [lo hi]            name .data singletons via RTTI (default whole .data)
python mem.py q <rva|addr> [n]        hex/qword view
"""
import ctypes, ctypes.wintypes as wt, struct, subprocess, sys

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
k32.OpenProcess.restype = wt.HANDLE
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                  ctypes.POINTER(ctypes.c_size_t)]
BASE, SIZE = 0x140000000, 0x4869400
DATA_LO, DATA_HI = 0x1a9c000, 0x1d81788


def pid():
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq DarkSoulsRemastered.exe', '/FO', 'CSV', '/NH'],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        if 'DarkSoulsRemastered' in line:
            return int(line.split('","')[1])
    sys.exit('game not running')


H = None


def read(addr, n):
    global H
    if H is None:
        H = k32.OpenProcess(0x410, False, pid())
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(H, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def q(addr):
    b = read(addr, 8)
    return struct.unpack('<Q', b)[0] if b and len(b) == 8 else None


def rtti_name(obj):
    """MSVC x64 RTTI: obj->vtable, vtable[-1] = COL; COL+0xC = TypeDescriptor rva; TD+0x10 = name."""
    vt = q(obj)
    if not vt or not (BASE <= vt < BASE + SIZE):
        return None
    col = q(vt - 8)
    if not col or not (BASE <= col < BASE + SIZE):
        return None
    hdr = read(col, 0x18)
    if not hdr or struct.unpack_from('<I', hdr, 0)[0] != 1:
        return None
    td = BASE + struct.unpack_from('<I', hdr, 0xC)[0]
    nm = read(td + 0x10, 128)
    if not nm or not nm.startswith(b'.?A'):
        return None
    return nm.split(b'\0')[0].decode(errors='replace')


def cmd_dump(out):
    buf = bytearray(SIZE)
    bad = 0
    for off in range(0, SIZE, 0x10000):
        n = min(0x10000, SIZE - off)
        b = read(BASE + off, n)
        if b is None:
            for p in range(off, off + n, 0x1000):
                pb = read(BASE + p, 0x1000)
                if pb:
                    buf[p:p + len(pb)] = pb
                else:
                    bad += 1
        else:
            buf[off:off + len(b)] = b
    open(out, 'wb').write(buf)
    print(f'dumped {SIZE:#x} bytes, unreadable pages {bad}')


def cmd_rtti(lo=DATA_LO, hi=DATA_HI):
    blob = read(BASE + lo, hi - lo) or b''
    for i in range(0, len(blob) - 7, 8):
        p = struct.unpack_from('<Q', blob, i)[0]
        if p < 0x10000 or BASE <= p < BASE + SIZE or p > 0x7fffffffffff:
            continue
        nm = rtti_name(p)
        if nm:
            print(f'{lo + i:#x} -> {p:#x} {nm}')


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'dump':
        cmd_dump(a[1])
    elif a[0] == 'rtti':
        cmd_rtti(*(int(x, 16) for x in a[1:3])) if len(a) > 1 else cmd_rtti()
    elif a[0] == 'q':
        addr = int(a[1], 16)
        addr = addr + BASE if addr < BASE else addr
        n = int(a[2], 16) if len(a) > 2 else 0x40
        b = read(addr, n)
        for o in range(0, len(b or b''), 16):
            print(f'{addr + o:#x} {b[o:o + 16].hex(" ")}')
