#pragma once
// cgfs16_rmlui_menu.h
// --------------------
// Phase 2 of the RmlUi migration: the real, interactive F12 menu (tabs,
// dashboard, item list, wizards, split-preview, hint bars) — replaced
// DrawMenuOverlay11 (formerly in cgfs16_overlay.cpp, deleted at cutover).
// See CLAUDE.md's migration notes / the "Phase 2" section of
// C:\Users\Miguel\.claude\plans\lazy-tumbling-balloon.md.
//
// Only included from cgfs16_rmlui.cpp / cgfs16_rmlui_menu.cpp, never from
// cgfs16_overlay.cpp directly — mirrors why cgfs16_rmlui.h itself stays
// RmlUi-type-free. RMLUI_STATIC_LIB must be defined before any RmlUi header
// is included in a given translation unit (RmlUi's own CMake sets this
// automatically for CMake-based consumers; we build with a direct cl.exe
// invocation, so every TU that includes this header needs it here too) —
// see cgfs16_rmlui.cpp's own top comment for the same requirement.
#ifndef RMLUI_STATIC_LIB
#define RMLUI_STATIC_LIB
#endif
#include <RmlUi/Core.h>

// Loads menu.rml from "<content_dir>\menu.rml" into the given context and
// caches its element pointers. Must be called once, from EnsureInit(), and
// (for the current draw-order invariant: menu below stadium-loading/toasts)
// BEFORE toast.rml/stadium_panel.rml are loaded into the same context.
// Returns false (and logs) on failure.
bool RmlMenu_Load(Rml::Context *context, const Rml::String &content_dir);

// Per-frame sync + show/hide, called every frame from RmlOverlay_RenderFrame
// alongside SyncToasts/SyncStadiumPanel. No-ops immediately (document stays
// hidden, nothing computed) while the menu is closed. outputWindow is the
// swapchain's output HWND (DXGI_SWAP_CHAIN_DESC::OutputWindow), passed as
// void* rather than HWND — this header is included before <windows.h> in
// cgfs16_rmlui_menu.cpp, so HWND isn't visible here yet — published to
// Python as viewport telemetry (RmlOverlay_SetMenuViewportTelemetry,
// formerly written by DrawMenuOverlay11 directly) for mouse coordinate
// transforms and menu-window focus detection.
void RmlMenu_Sync(int vpW, int vpH, void *outputWindow);
