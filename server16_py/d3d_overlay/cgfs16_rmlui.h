#pragma once
// cgfs16_rmlui.h
// ---------------
// RmlUi-based renderer for the toast notifications, the stadium-loading
// panel, and (see cgfs16_rmlui_menu.h) the F12 menu — all three ported off
// the hand-rolled D3D11 quad/text renderer this DLL used to carry
// (DrawToast11/DrawOverlay11/DrawMenuOverlay11, all now removed). See
// CLAUDE.md's migration notes / the plan at
// C:\Users\Miguel\.claude\plans\lazy-tumbling-balloon.md for the migration
// history.
#include <d3d11.h>
#include <dxgi.h>

// All three screens share one Rml::Context, so they're driven by a single
// per-frame entry point rather than independent ones — that keeps
// Context::Update()/Render() (which act on every document in the context) to
// one call each per frame. No-ops immediately (no device/RTV work at all)
// when the stadium panel, every toast slot, and the F12 menu are all
// currently hidden.
void RmlOverlay_RenderFrame(IDXGISwapChain *sc, ID3D11Device *dev, ID3D11DeviceContext *ctx);
