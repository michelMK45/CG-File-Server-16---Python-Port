# D3D Overlay — Technical Documentation

The D3D overlay is a stadium loading notification that renders directly on top of FIFA 16's fullscreen D3D11 output, bypassing Windows limitations that prevent regular windowed UI from appearing over exclusive-fullscreen DirectX applications.

---

## Architecture Overview

```
Python (app.py)
    │
    ├── D3DOverlayInjector (d3d_injector.py)
    │       │
    │       ├── Named shared memory  Local\CGFS16_Overlay_v1
    │       │       visible, progress, stadium_name, detail_text, image_path
    │       │
    │       └── cgfs16_inject.exe  ──→  CreateRemoteThread(LoadLibraryW)
    │                                          │
    │                                          ▼
    │                               cgfs16_overlay.dll  (injected into FIFA)
    │                                          │
    │                                    HookThread
    │                                          │
    │                              Temp D3D11 device+SwapChain
    │                              → vtable[8] = IDXGISwapChain::Present address
    │                              → inline detour (phase 1)
    │                                          │
    │                                   HookedPresent (every frame)
    │                                          │
    │                                    DrawOverlay11
    │                                   ┌────────────────────┐
    │                                   │ Colored quads (bg) │
    │                                   │ GDI text textures  │
    │                                   │ WIC image texture  │
    │                                   └────────────────────┘
    │
    └── Tkinter modal (fallback if DLL unavailable or injection fails)
```

---

## Hook Strategy

FIFA 16 uses a **dxgi.dll proxy** (Reshade. Works as well without reshade). A naive vtable scan on a temp device gets the proxy's Present, not FIFA's real one. The hook uses a two-phase approach to avoid this and to avoid RIP-relative instruction issues in trampolines:

### Phase 1 — Inline detour on the proxy's Present body
- The first 14 bytes of the proxy `dxgi.dll`'s `Present` function body are replaced with an absolute indirect jump (`FF 25 00000000 [8-byte address]`) that redirects to `HookedPresent`.
- This fires on the very first `Present` call.

### Phase 2 — vtable hook on FIFA's real SwapChain
- On the first call, the inline detour is removed (original bytes restored).
- `g_OrigPresent` is set to the now-clean proxy function pointer.
- FIFA's actual `IDXGISwapChain` vtable slot 8 is patched to point to `HookedPresent`.
- All subsequent frames go through the vtable hook with zero trampoline overhead.

This approach avoids:
- RIP-relative instruction issues (no copied bytes are executed from a trampoline).
- `IDXGISurface1::GetDC` crashes (not implemented by DXVK/proxy; never called).

---

## Rendering

Every frame that `HookedPresent` fires with `visible = 1`, `DrawOverlay11` runs:

1. **Get backbuffer RTV** — `sc->GetBuffer` + `CreateRenderTargetView`.
2. **Save full D3D11 state** — RTVs, viewports, blend/raster/DS states, shaders, IL, topology, SRVs, samplers.
3. **Colored quads pass** — draws the panel background, top accent bar, borders, progress track and fill using a POSITION+COLOR vertex shader compiled at runtime via D3DCompile.
4. **Text pass** — three GDI-rendered textures (title, stadium name, detail) uploaded as `DXGI_FORMAT_B8G8R8A8_UNORM` immutable textures, drawn as textured quads with a POSITION+TEXCOORD shader.
5. **Image pass** — stadium preview loaded via WIC (`IWICImagingFactory`), converted to BGRA32, cached as a D3D11 texture, drawn aspect-corrected inside the image box.
6. **Restore state** — all saved D3D11 objects released and restored.

### Panel Layout (1920×1080 reference)

```
                                         ┌───────────────────────────────────────────────────┐
                                         │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
                                         │  ┌──────────┐  Loading Stadium                    │
                                         │  │  PREVIEW │  Stadium Name                       │
                                         │  │  IMAGE   │  Detail / progress message          │
                                         │  └──────────┘                                     │
                                         │              [══════════════░░░░░░░░░░░░░░░░░░░░] │
                                         └───────────────────────────────────────────────────┘
                                                                              top-right, 20 px margin
                                                                              460 × 140 px
```

- **Image box**: 110 × 88 px, aspect-ratio corrected.
- **Text column**: starts at x+136 px, max width 312 px with ellipsis trimming.
- **Progress bar**: maps `progress_x100 / 100 / 100` (0–1) to bar fill width.

---

## GDI Text Rendering

`IDXGISurface1::GetDC` is not available on the proxy/DXVK backend. Text is instead rendered through a pure-GDI offscreen path:

1. Create a 32-bpp top-down `DIBSection` (`BI_RGB`, BGRA).
2. Select a `LOGFONTW` (Segoe UI) and call `DrawTextW` with `DT_END_ELLIPSIS`.
3. `GdiFlush()`.
4. GDI writes RGB but leaves alpha = 0. Post-process: set each pixel's alpha to `max(R, G, B)` (luminance threshold).
5. Upload as an immutable D3D11 texture and cache until the text content changes.

---

## WIC Image Loading

Stadium preview images are loaded once per path change:

1. `CoCreateInstance(CLSID_WICImagingFactory)` — COM is initialized once per render thread via `CoInitializeEx(COINIT_MULTITHREADED)`.
2. `CreateDecoderFromFilename` — supports PNG, JPG, BMP, and any other WIC-registered codec.
3. `IWICFormatConverter` → `GUID_WICPixelFormat32bppBGRA`.
4. Pixels copied into a `std::vector<BYTE>` and uploaded as an immutable `DXGI_FORMAT_B8G8R8A8_UNORM` texture.
5. The loaded path is cached in `g_previewLoadedPath`; a new load only happens when `image_path` in shared memory changes.

---

## Shared Memory IPC

Named shared memory `Local\CGFS16_Overlay_v1` is created by the Python host before injection. The DLL maps it on attach and reads it every frame.

**C++ struct (`OverlayShared`):**

```cpp
struct OverlayShared {
    volatile LONG visible;         // 0 = hide, 1 = show
    volatile LONG progress_x100;   // progress * 100  (0–10000)
    wchar_t stadium_name[256];
    wchar_t detail_text[256];
    wchar_t image_path[512];       // absolute path to preview image
};
```

**Python counterpart (`_OverlayShared`):**

```python
class _OverlayShared(ctypes.Structure):
    _fields_ = [
        ("visible",       ctypes.c_long),
        ("progress_x100", ctypes.c_long),
        ("stadium_name",  ctypes.c_wchar * 256),
        ("detail_text",   ctypes.c_wchar * 256),
        ("image_path",    ctypes.c_wchar * 512),
    ]
```

`visible` is written **last** (after all other fields are set) so the DLL never reads a partially-updated frame.

---

## Python API (`D3DOverlayInjector`)

```python
from server16_py.d3d_injector import D3DOverlayInjector

inj = D3DOverlayInjector(dll_path="bin/cgfs16_overlay.dll")

inj.inject(fifa_pid)                    # injects once; safe to call repeatedly
inj.show("Camp Nou", "Copying...", 0.0, image_path="C:/path/stadium.png")
inj.update(65.0, "Writing memory")     # update progress/detail mid-load
inj.hide()                             # hides immediately
inj.reset_injected()                   # call when FIFA process exits
inj.destroy()                          # unmap shared memory on app exit
```

---

## Fallback Behaviour

`_show_stadium_loading_modal()` in `app.py` follows this priority:

1. **Checkbox unchecked** → do nothing.
2. **D3D overlay** → inject DLL and show. Returns here if successful.
3. **Tkinter modal** → fallback when the DLL is missing, injection fails, or FIFA is not running.

The Tkinter modal is never removed; it remains as a working fallback.

---

## Build

Run `build_exe.bat` from the repository root for a full build (C++ compilation + PyInstaller). It auto-detects Visual Studio via `vswhere.exe`.

To compile only the C++ components manually:

```powershell
# From repository root (x64 Developer Command Prompt, or call vcvarsall first):
cl /nologo /O2 /W3 /LD /EHsc /std:c++17 `
    server16_py\d3d_overlay\cgfs16_overlay.cpp `
    /Fe:bin\cgfs16_overlay.dll /Fd:bin\cgfs16_overlay.pdb `
    /link d3d11.lib dxgi.lib d3dcompiler.lib user32.lib gdi32.lib ole32.lib

cl /nologo /O2 /W3 /EHsc /std:c++17 `
    server16_py\d3d_overlay\cgfs16_inject.cpp `
    /Fe:bin\cgfs16_inject.exe `
    /link kernel32.lib
```

**Dependencies (all system libraries, no third-party):** `d3d11`, `dxgi`, `d3dcompiler`, `user32`, `gdi32`, `ole32`, `kernel32`.

---

## Files

| File | Purpose |
|---|---|
| `server16_py/d3d_overlay/cgfs16_overlay.cpp` | DLL source — hook, rendering, IPC |
| `server16_py/d3d_overlay/cgfs16_inject.cpp` | Injector exe source — `CreateRemoteThread(LoadLibraryW)` |
| `server16_py/d3d_injector.py` | Python IPC driver — shared memory, subprocess injection |
| `bin/cgfs16_overlay.dll` | Compiled DLL — injected into FIFA at runtime |
| `bin/cgfs16_inject.exe` | Compiled injector x64 — runs `LoadLibraryW` in FIFA's process |
| `build_exe.bat` | Full build script — compiles C++ then runs PyInstaller |
| `Server16Python.spec` | PyInstaller spec — bundles `bin/` DLL and EXE into the dist package |
