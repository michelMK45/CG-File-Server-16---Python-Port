// cgfs16_rmlui.cpp
// -----------------
// Phase 1 of the RmlUi migration: toasts + the stadium-loading panel, ported
// off the hand-rolled D3D11 quad/text renderer (formerly DrawToast11/
// DrawOverlay11 in cgfs16_overlay.cpp, now removed). See the plan at
// C:\Users\Miguel\.claude\plans\lazy-tumbling-balloon.md.
//
// The RenderInterface/SystemInterface here are carried over unchanged from
// the Phase 0 proof of concept (already validated in-game) — only the
// document content (now loose files under resources/rmlui/, see
// CgfsRmlFileInterface below) and the per-frame data sync are new. Both
// screens share one Rml::Context (two documents), driven by a single
// per-frame entry point so Context::Update()/Render() — which act on every
// document in the context — only run once per frame even when both screens
// are visible at once.
//
// RMLUI_STATIC_LIB must be defined before including any RmlUi header, since
// we link RmlUi Core as a static .lib merged into this DLL rather than
// consuming it as a separate DLL (RmlUi's own CMake sets this automatically
// for CMake-based consumers via a PUBLIC compile definition, but we build
// with a direct cl.exe invocation, so it has to be defined here instead).
#define RMLUI_STATIC_LIB
#include <RmlUi/Core.h>

#include "cgfs16_rmlui.h"
#include "cgfs16_rmlui_menu.h"

#include <objbase.h>     // CoInitializeEx (WIC, via LoadWICTexture, needs COM on this thread)
#include <d3dcompiler.h>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <cmath>

#pragma comment(lib, "d3dcompiler.lib")

// Both declared (non-static) in cgfs16_overlay.cpp so this translation unit
// can share the one %TEMP%\cgfs16_overlay.log file and the existing WIC
// texture loader instead of duplicating either.
void Log(const char *fmt, ...);
bool LoadWICTexture(ID3D11Device *dev, const wchar_t *path,
    ID3D11Texture2D **outTex, ID3D11ShaderResourceView **outSRV,
    int *outW, int *outH, bool premultiplyAlpha);

// Plain scalar/index-based accessors into OverlayShared, defined right next
// to the real struct in cgfs16_overlay.cpp. Deliberately not a shared struct
// type or pointer across the translation-unit boundary (that would either
// duplicate OverlayShared's full layout here — one more place to drift out of
// sync on a future field change — or require moving it into a shared header,
// a bigger change than this phase needs) — just narrow, read-only getters.
// MAX_TOASTS/MAX_IMG must match the same constants in cgfs16_overlay.cpp/d3d_injector.py.
#define MAX_TOASTS 6
#define MAX_IMG 512
bool RmlOverlay_ToastVisible(int slot);
bool RmlOverlay_ToastWarning(int slot);
const wchar_t *RmlOverlay_ToastTitle(int slot);
const wchar_t *RmlOverlay_ToastBody(int slot);
bool RmlOverlay_StadiumPanelVisible();
int RmlOverlay_ProgressX100();
const wchar_t *RmlOverlay_StadiumName();
const wchar_t *RmlOverlay_DetailText();
const wchar_t *RmlOverlay_ImagePath();
const wchar_t *RmlOverlay_PanelTitle();
const wchar_t *RmlOverlay_ContentDir();
bool RmlOverlay_MenuVisible();

// ---------------------------------------------------------------------------
// wchar_t -> UTF-8 helper (shared struct strings are wide; Rml::String is UTF-8)
// ---------------------------------------------------------------------------
static Rml::String WideToUtf8(const wchar_t *s) {
    if (!s || !s[0]) return Rml::String();
    int len = WideCharToMultiByte(CP_UTF8, 0, s, -1, nullptr, 0, nullptr, nullptr);
    if (len <= 0) return Rml::String();
    std::string out(len - 1, '\0'); // len includes the null terminator
    WideCharToMultiByte(CP_UTF8, 0, s, -1, out.data(), len, nullptr, nullptr);
    return Rml::String(out);
}

// ---------------------------------------------------------------------------
// RML + RCSS for both screens now live as loose files on disk
// (resources/rmlui/toast.rml, resources/rmlui/stadium_panel.rml) instead of
// being embedded as C++ string literals — Python hands over the containing
// directory once after injection (rmlui_content_dir in OverlayShared /
// RmlOverlay_ContentDir() below), so these documents can be tweaked and
// re-tested (relaunch FIFA) without recompiling this DLL. See
// CgfsRmlFileInterface + EnsureInit() below for how they get loaded. Colors
// in those files use RCSS's #RRGGBBAA convention (alpha LAST) — NOT this
// codebase's usual D3D 0xAARRGGBB DWORD convention used elsewhere in
// cgfs16_overlay.cpp; double-check this when copying a color value across
// from the old hand-rolled renderer.
// ---------------------------------------------------------------------------
static const char kToastDocFile[] = "toast.rml";
static const char kStadiumDocFile[] = "stadium_panel.rml";

// ---------------------------------------------------------------------------
// D3D11 shader — origin: Phase 0 POC, unchanged. Vertex layout matches
// Rml::Vertex's memory layout exactly (float2 position, 4x UNORM8
// premultiplied color, float2 tex_coord), so RmlUi's vertex spans are
// uploaded to the GPU with no per-vertex CPU-side conversion.
// ---------------------------------------------------------------------------
static const char kRmlShaderSrc[] = R"(
// CssTransform is the CSS `transform` property's matrix (RenderInterface::
// SetTransform), identity when no transform is active on the current
// element — applied in the SAME pixel-space Translation already operates
// in, BEFORE the existing viewport-normalize step, mirroring the order
// RmlUi's own reference GL3 backend uses (RenderInterface_GL3::SetTransform:
// transform = projection * cssMatrix, applied to `pos + translate` — here
// the "projection" part stays the separate manual viewport-normalize below
// instead of being folded into one matrix, since that's already proven and
// unrelated to CSS transforms). Declared column_major explicitly to match
// Rml::Matrix4f's default ColumnMajorMatrix4f storage byte-for-byte (see
// SetTransform() below) — do not remove the qualifier, D3DCompile's default
// packing is not guaranteed to match without it.
cbuffer Transform : register(b0) {
    float2 Translation;
    float2 ViewportSize;
    column_major float4x4 CssTransform;
};
Texture2D g_tex : register(t0);
SamplerState g_samp : register(s0);
struct VS_IN  { float2 pos : POSITION; float4 col : COLOR; float2 uv : TEXCOORD; };
struct VS_OUT { float4 pos : SV_POSITION; float4 col : COLOR; float2 uv : TEXCOORD; };
VS_OUT VSMain(VS_IN v) {
    VS_OUT o;
    float2 translated = v.pos + Translation;
    float4 transformed = mul(CssTransform, float4(translated, 0, 1));
    float2 p = transformed.xy;
    float2 clip = float2(p.x / ViewportSize.x * 2.0 - 1.0, 1.0 - p.y / ViewportSize.y * 2.0);
    o.pos = float4(clip, 0, 1);
    o.col = v.col;
    o.uv = v.uv;
    return o;
}
float4 PSMain(VS_OUT v) : SV_TARGET {
    return v.col * g_tex.Sample(g_samp, v.uv);
}

// ── Box-shadow blur (Phase B) ────────────────────────────────────────────
// Separable Gaussian, applied as two full-viewport passes (horizontal then
// vertical, driven from C++ — see ApplyBlur) reusing VSMain/the same quad
// geometry, just this pixel shader instead of PSMain. A fixed BLUR_MAX_
// RADIUS=40 kernel comfortably covers this design's whole sigma range
// (box-shadow blur-radius values of 6-25px => sigma 3-12.5px, gaussian
// kernel radius ~3*sigma) computed per-pixel in a dynamic loop (SM4.0
// supports this) rather than RmlUi's own GL3 backend's per-vertex
// interpolated-array-of-taps technique — mathematically equivalent, and
// simpler to get right in HLSL for a 4-vertex fullscreen quad where the
// per-vertex-vs-per-pixel cost difference is negligible. Deliberately no
// adaptive downscaling for large sigma (see the Phase 3 plan's approved
// scope reduction) — this only ever blurs a handful of small,
// infrequently-regenerated menu-chrome shadows, not a general feature.
#define BLUR_MAX_RADIUS 40
cbuffer BlurParams : register(b1) {
    float2 BlurTexelOffset; // (1/width, 0) horizontal pass, (0, 1/height) vertical pass
    int BlurRadius;         // <= BLUR_MAX_RADIUS, computed from sigma on the C++ side
    float BlurPad;          // unused, keeps the cbuffer 16-byte aligned
    float4 BlurWeights[BLUR_MAX_RADIUS + 1]; // weights[i] in .x; .yzw unused (see the C++ upload comment on why)
};
float4 PSBlur(VS_OUT v) : SV_TARGET {
    float4 color = g_tex.Sample(g_samp, v.uv) * BlurWeights[0].x;
    for (int i = 1; i <= BlurRadius; i++) {
        float2 o = BlurTexelOffset * (float)i;
        color += g_tex.Sample(g_samp, v.uv + o) * BlurWeights[i].x;
        color += g_tex.Sample(g_samp, v.uv - o) * BlurWeights[i].x;
    }
    return color;
}
)";

// ---------------------------------------------------------------------------
// CgfsRmlRenderInterface — the one interface RmlUi strictly requires.
// Origin: Phase 0 POC (already validated in-game), unchanged except
// LoadTexture, which the POC's embedded-only test content never exercised.
// ---------------------------------------------------------------------------
class CgfsRmlRenderInterface : public Rml::RenderInterface {
public:
    bool EnsureDeviceResources(ID3D11Device *dev) {
        if (m_resourcesReady) return true;
        if (!dev) return false;

        ID3DBlob *vsBlob = nullptr, *psBlob = nullptr, *err = nullptr;
        HRESULT hr = D3DCompile(kRmlShaderSrc, sizeof(kRmlShaderSrc) - 1,
            nullptr, nullptr, nullptr, "VSMain", "vs_4_0", 0, 0, &vsBlob, &err);
        if (FAILED(hr)) {
            Log("[RmlOverlay] VS compile hr=0x%08X: %s", (unsigned)hr, err ? (char*)err->GetBufferPointer() : "?");
            if (err) err->Release();
            return false;
        }
        hr = D3DCompile(kRmlShaderSrc, sizeof(kRmlShaderSrc) - 1,
            nullptr, nullptr, nullptr, "PSMain", "ps_4_0", 0, 0, &psBlob, &err);
        if (FAILED(hr)) {
            Log("[RmlOverlay] PS compile hr=0x%08X: %s", (unsigned)hr, err ? (char*)err->GetBufferPointer() : "?");
            vsBlob->Release();
            if (err) err->Release();
            return false;
        }

        dev->CreateVertexShader(vsBlob->GetBufferPointer(), vsBlob->GetBufferSize(), nullptr, &m_vs);
        dev->CreatePixelShader(psBlob->GetBufferPointer(), psBlob->GetBufferSize(), nullptr, &m_ps);

        ID3DBlob *psBlurBlob = nullptr;
        hr = D3DCompile(kRmlShaderSrc, sizeof(kRmlShaderSrc) - 1,
            nullptr, nullptr, nullptr, "PSBlur", "ps_4_0", 0, 0, &psBlurBlob, &err);
        if (FAILED(hr)) {
            Log("[RmlOverlay] PSBlur compile hr=0x%08X: %s", (unsigned)hr, err ? (char*)err->GetBufferPointer() : "?");
            if (err) err->Release();
        } else {
            dev->CreatePixelShader(psBlurBlob->GetBufferPointer(), psBlurBlob->GetBufferSize(), nullptr, &m_psBlur);
            psBlurBlob->Release();
        }

        D3D11_INPUT_ELEMENT_DESC ied[] = {
            {"POSITION", 0, DXGI_FORMAT_R32G32_FLOAT,   0, 0,  D3D11_INPUT_PER_VERTEX_DATA, 0},
            {"COLOR",    0, DXGI_FORMAT_R8G8B8A8_UNORM, 0, 8,  D3D11_INPUT_PER_VERTEX_DATA, 0},
            {"TEXCOORD", 0, DXGI_FORMAT_R32G32_FLOAT,   0, 12, D3D11_INPUT_PER_VERTEX_DATA, 0},
        };
        dev->CreateInputLayout(ied, 3, vsBlob->GetBufferPointer(), vsBlob->GetBufferSize(), &m_il);
        vsBlob->Release();
        psBlob->Release();

        D3D11_BUFFER_DESC cbd = {};
        cbd.ByteWidth = 80; // 4 floats (Translation.xy + ViewportSize.xy) + 16 floats (CssTransform)
        cbd.Usage = D3D11_USAGE_DYNAMIC;
        cbd.BindFlags = D3D11_BIND_CONSTANT_BUFFER;
        cbd.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
        dev->CreateBuffer(&cbd, nullptr, &m_cbuf);

        // BlurParams (register b1) — see the cbuffer's own field comments
        // in kRmlShaderSrc. 16 bytes (offset/radius/pad) + (BLUR_MAX_RADIUS+1)
        // float4 weights.
        D3D11_BUFFER_DESC cbdBlur = {};
        cbdBlur.ByteWidth = 16 + (40 + 1) * 16; // must track BLUR_MAX_RADIUS in kRmlShaderSrc
        cbdBlur.Usage = D3D11_USAGE_DYNAMIC;
        cbdBlur.BindFlags = D3D11_BIND_CONSTANT_BUFFER;
        cbdBlur.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
        dev->CreateBuffer(&cbdBlur, nullptr, &m_blurCbuf);

        // Premultiplied-alpha blend — matches RmlUi's vertex/texture color convention.
        D3D11_BLEND_DESC bsd = {};
        bsd.RenderTarget[0].BlendEnable = TRUE;
        bsd.RenderTarget[0].SrcBlend = D3D11_BLEND_ONE;
        bsd.RenderTarget[0].DestBlend = D3D11_BLEND_INV_SRC_ALPHA;
        bsd.RenderTarget[0].BlendOp = D3D11_BLEND_OP_ADD;
        bsd.RenderTarget[0].SrcBlendAlpha = D3D11_BLEND_ONE;
        bsd.RenderTarget[0].DestBlendAlpha = D3D11_BLEND_INV_SRC_ALPHA;
        bsd.RenderTarget[0].BlendOpAlpha = D3D11_BLEND_OP_ADD;
        bsd.RenderTarget[0].RenderTargetWriteMask = D3D11_COLOR_WRITE_ENABLE_ALL;
        dev->CreateBlendState(&bsd, &m_bs);

        // BlendMode::Replace (CompositeLayers) — blend disabled, straight overwrite.
        D3D11_BLEND_DESC bsdReplace = bsd;
        bsdReplace.RenderTarget[0].BlendEnable = FALSE;
        dev->CreateBlendState(&bsdReplace, &m_bsReplace);

        // Clip-mask stencil-write pass (RenderToClipMask) — the mask
        // geometry itself must not paint visible color, only stencil bits.
        D3D11_BLEND_DESC bsdNoColor = bsd;
        bsdNoColor.RenderTarget[0].RenderTargetWriteMask = 0;
        dev->CreateBlendState(&bsdNoColor, &m_bsNoColorWrite);

        D3D11_RASTERIZER_DESC rsdOn = {};
        rsdOn.FillMode = D3D11_FILL_SOLID;
        rsdOn.CullMode = D3D11_CULL_NONE;
        rsdOn.DepthClipEnable = FALSE;
        rsdOn.ScissorEnable = TRUE;
        dev->CreateRasterizerState(&rsdOn, &m_rsScissorOn);
        D3D11_RASTERIZER_DESC rsdOff = rsdOn;
        rsdOff.ScissorEnable = FALSE;
        dev->CreateRasterizerState(&rsdOff, &m_rsScissorOff);

        D3D11_DEPTH_STENCIL_DESC dsd = {};
        dsd.DepthEnable = FALSE;
        dev->CreateDepthStencilState(&dsd, &m_dss);

        // Clip mask (RenderToClipMask/EnableClipMask) — see the field
        // comments on m_dssClipWrite/m_dssClipTest above for the "1 =
        // visible" invariant these two states implement together.
        D3D11_DEPTH_STENCIL_DESC dsdClipWrite = {};
        dsdClipWrite.DepthEnable = FALSE;
        dsdClipWrite.StencilEnable = TRUE;
        dsdClipWrite.StencilReadMask = 0xFF;
        dsdClipWrite.StencilWriteMask = 0xFF;
        dsdClipWrite.FrontFace.StencilFunc = D3D11_COMPARISON_ALWAYS;
        dsdClipWrite.FrontFace.StencilPassOp = D3D11_STENCIL_OP_REPLACE;
        dsdClipWrite.FrontFace.StencilFailOp = D3D11_STENCIL_OP_KEEP;
        dsdClipWrite.FrontFace.StencilDepthFailOp = D3D11_STENCIL_OP_KEEP;
        dsdClipWrite.BackFace = dsdClipWrite.FrontFace;
        dev->CreateDepthStencilState(&dsdClipWrite, &m_dssClipWrite);

        D3D11_DEPTH_STENCIL_DESC dsdClipTest = {};
        dsdClipTest.DepthEnable = FALSE;
        dsdClipTest.StencilEnable = TRUE;
        dsdClipTest.StencilReadMask = 0xFF;
        dsdClipTest.StencilWriteMask = 0x00; // read-only — never modifies the mask while just testing against it
        dsdClipTest.FrontFace.StencilFunc = D3D11_COMPARISON_EQUAL;
        dsdClipTest.FrontFace.StencilPassOp = D3D11_STENCIL_OP_KEEP;
        dsdClipTest.FrontFace.StencilFailOp = D3D11_STENCIL_OP_KEEP;
        dsdClipTest.FrontFace.StencilDepthFailOp = D3D11_STENCIL_OP_KEEP;
        dsdClipTest.BackFace = dsdClipTest.FrontFace;
        dev->CreateDepthStencilState(&dsdClipTest, &m_dssClipTest);

        D3D11_SAMPLER_DESC sd = {};
        sd.Filter = D3D11_FILTER_MIN_MAG_MIP_LINEAR;
        sd.AddressU = D3D11_TEXTURE_ADDRESS_CLAMP;
        sd.AddressV = D3D11_TEXTURE_ADDRESS_CLAMP;
        sd.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
        dev->CreateSamplerState(&sd, &m_samp);

        // 1x1 white texture, bound whenever RmlUi hands us texture==0 (flat-
        // colored geometry) so one shader permutation covers both cases.
        UINT whitePixel = 0xFFFFFFFF;
        D3D11_TEXTURE2D_DESC wtd = {};
        wtd.Width = 1; wtd.Height = 1; wtd.MipLevels = 1; wtd.ArraySize = 1;
        wtd.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
        wtd.SampleDesc.Count = 1;
        wtd.Usage = D3D11_USAGE_IMMUTABLE;
        wtd.BindFlags = D3D11_BIND_SHADER_RESOURCE;
        D3D11_SUBRESOURCE_DATA wsd = {};
        wsd.pSysMem = &whitePixel;
        wsd.SysMemPitch = 4;
        dev->CreateTexture2D(&wtd, &wsd, &m_whiteTex);
        if (m_whiteTex) dev->CreateShaderResourceView(m_whiteTex, nullptr, &m_whiteSRV);

        m_resourcesReady = m_vs && m_ps && m_psBlur && m_il && m_cbuf && m_blurCbuf && m_bs && m_bsReplace && m_bsNoColorWrite &&
                            m_rsScissorOn && m_rsScissorOff && m_dss && m_dssClipWrite && m_dssClipTest &&
                            m_samp && m_whiteSRV;
        if (!m_resourcesReady)
            Log("[RmlOverlay] EnsureDeviceResources: one or more resources failed to create");
        return m_resourcesReady;
    }

    void BeginFrame(ID3D11Device *dev, ID3D11DeviceContext *ctx, float vpW, float vpH) {
        m_dev = dev;
        m_ctx = ctx;
        m_vpW = vpW;
        m_vpH = vpH;
    }

    // Called by RmlOverlay_RenderFrame right where it binds the swapchain
    // backbuffer as the render target (after BeginFrame — the backbuffer
    // RTV doesn't exist yet that early, it's created just before
    // Context::Render() runs). Non-owning: the caller creates and releases
    // this RTV itself every frame: this pointer must not outlive that.
    void SetBaseRenderTarget(ID3D11RenderTargetView *rtv) {
        m_baseRTV = rtv;
        EnsureStencilBuffer();
        if (m_ctx && m_baseRTV) m_ctx->OMSetRenderTargets(1, &m_baseRTV, m_stencilDSV);
    }

    void EndFrame() {
        // Defensive resets, not expected to ever matter in practice: every
        // PushLayer this frame should already be matched by a PopLayer
        // (RmlUi's own contract), and EnableClipMask(false) should already
        // have run before the document finishes rendering. Guards against a
        // stuck state silently carrying into next frame if some path ever
        // doesn't unwind cleanly.
        m_layerStack.clear();
        m_clipMaskEnabled = false;
        m_baseRTV = nullptr;
        m_dev = nullptr;
        m_ctx = nullptr;
    }

    Rml::CompiledGeometryHandle CompileGeometry(Rml::Span<const Rml::Vertex> vertices, Rml::Span<const int> indices) override {
        if (!m_dev || vertices.empty() || indices.empty()) return 0;
        auto *g = new GeometryData();

        D3D11_BUFFER_DESC vbd = {};
        vbd.ByteWidth = (UINT)(vertices.size() * sizeof(Rml::Vertex));
        vbd.Usage = D3D11_USAGE_IMMUTABLE;
        vbd.BindFlags = D3D11_BIND_VERTEX_BUFFER;
        D3D11_SUBRESOURCE_DATA vsd = {};
        vsd.pSysMem = vertices.data();
        if (FAILED(m_dev->CreateBuffer(&vbd, &vsd, &g->vb))) { delete g; return 0; }

        D3D11_BUFFER_DESC ibd = {};
        ibd.ByteWidth = (UINT)(indices.size() * sizeof(int));
        ibd.Usage = D3D11_USAGE_IMMUTABLE;
        ibd.BindFlags = D3D11_BIND_INDEX_BUFFER;
        D3D11_SUBRESOURCE_DATA isd = {};
        isd.pSysMem = indices.data();
        if (FAILED(m_dev->CreateBuffer(&ibd, &isd, &g->ib))) { g->vb->Release(); delete g; return 0; }

        g->indexCount = (UINT)indices.size();
        return reinterpret_cast<Rml::CompiledGeometryHandle>(g);
    }

    void RenderGeometry(Rml::CompiledGeometryHandle geometry, Rml::Vector2f translation, Rml::TextureHandle texture) override {
        if (!m_ctx || !geometry) return;
        auto *g = reinterpret_cast<GeometryData*>(geometry);
        if (!g->vb || !g->ib) return;

        struct { float tx, ty, vw, vh; float transform[16]; } cb;
        cb.tx = translation.x; cb.ty = translation.y; cb.vw = m_vpW; cb.vh = m_vpH;
        // Rml::Matrix4f's raw data() layout is ColumnMajorMatrix4f in this
        // build (the default when RMLUI_MATRIX_ROW_MAJOR isn't defined, per
        // Config.h) — a direct memcpy matches the shader's `column_major`
        // qualifier byte-for-byte, no transposition needed. This is the
        // same raw layout RmlUi's own GL3 backend uploads via
        // glUniformMatrix4fv(..., transpose=false, transform.data()).
        memcpy(cb.transform, m_cssTransform.data(), sizeof(cb.transform));
        D3D11_MAPPED_SUBRESOURCE ms = {};
        if (SUCCEEDED(m_ctx->Map(m_cbuf, 0, D3D11_MAP_WRITE_DISCARD, 0, &ms))) {
            memcpy(ms.pData, &cb, sizeof(cb));
            m_ctx->Unmap(m_cbuf, 0);
        }

        ID3D11ShaderResourceView *srv = m_whiteSRV;
        if (texture) {
            auto *t = reinterpret_cast<TextureData*>(texture);
            if (t->srv) srv = t->srv;
        }

        UINT stride = sizeof(Rml::Vertex), offset = 0;
        m_ctx->IASetVertexBuffers(0, 1, &g->vb, &stride, &offset);
        m_ctx->IASetIndexBuffer(g->ib, DXGI_FORMAT_R32_UINT, 0);
        m_ctx->IASetInputLayout(m_il);
        m_ctx->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
        m_ctx->VSSetShader(m_vs, nullptr, 0);
        m_ctx->VSSetConstantBuffers(0, 1, &m_cbuf);
        m_ctx->PSSetShader(m_ps, nullptr, 0);
        m_ctx->PSSetShaderResources(0, 1, &srv);
        m_ctx->PSSetSamplers(0, 1, &m_samp);
        m_ctx->OMSetBlendState(m_bs, nullptr, 0xFFFFFFFF);
        // While a clip mask is active, every normal geometry draw must be
        // masked by it (RenderInterface.h: "applies exclusively to all
        // other functions that render with a geometry handle") — ref=1
        // matches the "1 = visible" invariant m_dssClipWrite establishes.
        if (m_clipMaskEnabled) m_ctx->OMSetDepthStencilState(m_dssClipTest, 1);
        else m_ctx->OMSetDepthStencilState(m_dss, 0);
        m_ctx->RSSetState(m_scissorEnabled ? m_rsScissorOn : m_rsScissorOff);

        m_ctx->DrawIndexed(g->indexCount, 0, 0);
    }

    void ReleaseGeometry(Rml::CompiledGeometryHandle geometry) override {
        if (!geometry) return;
        auto *g = reinterpret_cast<GeometryData*>(geometry);
        if (g->vb) g->vb->Release();
        if (g->ib) g->ib->Release();
        delete g;
    }

    Rml::TextureHandle LoadTexture(Rml::Vector2i &texture_dimensions, const Rml::String &source) override {
        texture_dimensions = Rml::Vector2i(0, 0);
        Log("[RmlOverlay] LoadTexture called for '%s' (m_dev=%p)", source.c_str(), (void*)m_dev);
        if (!m_dev || source.empty()) return 0;

        int wlen = MultiByteToWideChar(CP_UTF8, 0, source.c_str(), -1, nullptr, 0);
        if (wlen <= 0) return 0;
        std::wstring wpath((size_t)wlen, L'\0');
        MultiByteToWideChar(CP_UTF8, 0, source.c_str(), -1, wpath.data(), wlen);

        auto *t = new TextureData();
        int w = 0, h = 0;
        if (!LoadWICTexture(m_dev, wpath.c_str(), &t->tex, &t->srv, &w, &h, /*premultiplyAlpha=*/true) || !t->srv) {
            Log("[RmlOverlay] LoadTexture failed for '%s'", source.c_str());
            delete t;
            return 0;
        }
        Log("[RmlOverlay] LoadTexture ok for '%s' (%dx%d)", source.c_str(), w, h);
        texture_dimensions = Rml::Vector2i(w, h);
        return reinterpret_cast<Rml::TextureHandle>(t);
    }

    Rml::TextureHandle GenerateTexture(Rml::Span<const Rml::byte> source, Rml::Vector2i source_dimensions) override {
        if (!m_dev) return 0;
        int w = source_dimensions.x, h = source_dimensions.y;
        if (w <= 0 || h <= 0) return 0;

        // No row flip: verified against RmlUi's own official GL3 backend
        // (Backends/RmlUi_Renderer_GL3.cpp, Gfx::CreateTexture) — it uploads
        // source_data straight through with glTexImage2D, no flip. RmlUi's
        // generated data (glyph atlases) is already top-down; an earlier
        // version of this file flipped it "to match OpenGL's bottom-left
        // origin", which was wrong and scrambled every glyph (each quad's UV
        // rect ended up sampling a mirrored, wrong region of the atlas).
        D3D11_TEXTURE2D_DESC td = {};
        td.Width = (UINT)w;
        td.Height = (UINT)h;
        td.MipLevels = 1;
        td.ArraySize = 1;
        td.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
        td.SampleDesc.Count = 1;
        td.Usage = D3D11_USAGE_IMMUTABLE;
        td.BindFlags = D3D11_BIND_SHADER_RESOURCE;
        D3D11_SUBRESOURCE_DATA sd = {};
        sd.pSysMem = source.data();
        sd.SysMemPitch = (UINT)(w * 4);

        auto *t = new TextureData();
        if (FAILED(m_dev->CreateTexture2D(&td, &sd, &t->tex))) { delete t; return 0; }
        m_dev->CreateShaderResourceView(t->tex, nullptr, &t->srv);
        return reinterpret_cast<Rml::TextureHandle>(t);
    }

    void ReleaseTexture(Rml::TextureHandle texture) override {
        if (!texture) return;
        auto *t = reinterpret_cast<TextureData*>(texture);
        if (t->srv) t->srv->Release();
        if (t->tex) t->tex->Release();
        delete t;
    }

    void EnableScissorRegion(bool enable) override { m_scissorEnabled = enable; }

    void SetScissorRegion(Rml::Rectanglei region) override {
        m_currentScissor.left = region.Left();
        m_currentScissor.top = region.Top();
        m_currentScissor.right = region.Right();
        m_currentScissor.bottom = region.Bottom();
        if (!m_ctx) return;
        m_ctx->RSSetScissorRects(1, &m_currentScissor);
    }

    // CSS `transform` (e.g. skewX() on .tab/.brand-badge) — previously
    // silently ignored (this class had no override at all, so the
    // Rml::RenderInterface base's no-op default ran instead; confirmed via
    // grep before adding this). Just stores the matrix; RenderGeometry
    // uploads it every draw call alongside Translation/ViewportSize.
    void SetTransform(const Rml::Matrix4f *transform) override {
        m_cssTransform = transform ? *transform : Rml::Matrix4f::Identity();
    }

    // ── Layer stack (box-shadow support, Phase A) ───────────────────────
    // See the m_layerPool/m_layerStack/m_baseRTV field comments above for
    // the handle-numbering scheme (0 = base, 1..MAX_LAYERS = pool slots).
    Rml::LayerHandle PushLayer() override {
        if (!m_ctx || !EnsureLayerPool()) return 0;
        int slot = (int)m_layerStack.size(); // depth-based pool slot: nesting never needs two layers at the same depth alive simultaneously in this design
        if (slot >= MAX_LAYERS) {
            Log("[RmlOverlay] PushLayer: layer pool exhausted (depth=%d)", slot);
            return 0;
        }
        LayerData &layer = m_layerPool[slot];
        const float clearColor[4] = {0.f, 0.f, 0.f, 0.f};
        m_ctx->ClearRenderTargetView(layer.rtv, clearColor);
        m_ctx->OMSetRenderTargets(1, &layer.rtv, m_stencilDSV);
        Rml::LayerHandle handle = (Rml::LayerHandle)(slot + 1);
        m_layerStack.push_back(handle);
        return handle;
    }

    void PopLayer() override {
        if (!m_ctx || m_layerStack.empty()) return;
        m_layerStack.pop_back();
        RebindTopLayer();
    }

    // Blends/replaces source onto destination, applying `filters` (this
    // design only ever compiles/passes the "blur" filter — see
    // CompileFilter) to the source layer's content first.
    void CompositeLayers(Rml::LayerHandle source, Rml::LayerHandle destination, Rml::BlendMode blend_mode,
                          Rml::Span<const Rml::CompiledFilterHandle> filters) override {
        if (!m_ctx) return;
        ID3D11ShaderResourceView *srcSRV = LayerSRV(source);
        if (!srcSRV) return;

        for (Rml::CompiledFilterHandle fh : filters) {
            auto *f = reinterpret_cast<CompiledFilter*>(fh);
            if (f) ApplyBlur(f->sigma, source);
        }
        srcSRV = LayerSRV(source); // re-fetch: same texture, but explicit rather than assuming the pointer is still valid after ApplyBlur

        ID3D11RenderTargetView *dstRTV = LayerRTV(destination);
        if (!dstRTV) return;
        m_ctx->OMSetRenderTargets(1, &dstRTV, m_stencilDSV);
        BlitFullscreen(srcSRV, blend_mode == Rml::BlendMode::Replace);

        // If the destination isn't the current top of stack, restore it —
        // mirrors the reference GL3 backend's own CompositeLayers, which
        // makes the same restoration for the same reason (composite can
        // target a layer other than the active render target).
        RebindTopLayer();
    }

    Rml::TextureHandle SaveLayerAsTexture() override {
        if (!m_dev || !m_ctx || m_layerStack.empty()) return 0;
        ID3D11Texture2D *srcTex = LayerTex(m_layerStack.back());
        if (!srcTex) return 0;

        int w = (int)(m_currentScissor.right - m_currentScissor.left);
        int h = (int)(m_currentScissor.bottom - m_currentScissor.top);
        if (w <= 0 || h <= 0) return 0;

        D3D11_TEXTURE2D_DESC td = {};
        td.Width = (UINT)w;
        td.Height = (UINT)h;
        td.MipLevels = 1;
        td.ArraySize = 1;
        td.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
        td.SampleDesc.Count = 1;
        td.Usage = D3D11_USAGE_DEFAULT;
        td.BindFlags = D3D11_BIND_SHADER_RESOURCE;

        auto *t = new TextureData();
        if (FAILED(m_dev->CreateTexture2D(&td, nullptr, &t->tex))) { delete t; return 0; }
        if (FAILED(m_dev->CreateShaderResourceView(t->tex, nullptr, &t->srv))) { t->tex->Release(); delete t; return 0; }

        D3D11_BOX box = {};
        box.left = (UINT)(std::max)(0L, m_currentScissor.left);
        box.top = (UINT)(std::max)(0L, m_currentScissor.top);
        box.front = 0; box.back = 1;
        box.right = box.left + (UINT)w;
        box.bottom = box.top + (UINT)h;
        m_ctx->CopySubresourceRegion(t->tex, 0, 0, 0, 0, srcTex, 0, &box);

        return reinterpret_cast<Rml::TextureHandle>(t);
    }

    // ── Clip mask (stencil-based) ────────────────────────────────────────
    void EnableClipMask(bool enable) override { m_clipMaskEnabled = enable; }

    void RenderToClipMask(Rml::ClipMaskOperation operation, Rml::CompiledGeometryHandle geometry, Rml::Vector2f translation) override {
        if (!m_ctx || !EnsureStencilBuffer() || !geometry) return;
        auto *g = reinterpret_cast<GeometryData*>(geometry);
        if (!g->vb || !g->ib) return;

        // Full-buffer clear on Set/SetInverse ("clearing any existing clip
        // mask", per RenderInterface.h's own doc comment on this method).
        // Intersect deliberately approximated as identical to Set: a
        // mathematically correct intersect needs a second stencil bit-plane
        // + an extra AND pass, and nothing in this document's actual RCSS
        // ever nests two clip-masked regions (only #hero-img-wrap's
        // rounded-corner overflow clip and box-shadow's inverse-clip exist
        // here, never both active on the same element at once) — real
        // complexity for a code path this codebase never exercises. If a
        // future document design nests clip masks, revisit this.
        UINT8 clearValue = (operation == Rml::ClipMaskOperation::SetInverse) ? 1 : 0;
        m_ctx->ClearDepthStencilView(m_stencilDSV, D3D11_CLEAR_STENCIL, 1.0f, clearValue);

        UINT8 writeRef = (operation == Rml::ClipMaskOperation::SetInverse) ? 0 : 1;

        struct { float tx, ty, vw, vh; float transform[16]; } cb;
        cb.tx = translation.x; cb.ty = translation.y; cb.vw = m_vpW; cb.vh = m_vpH;
        memcpy(cb.transform, m_cssTransform.data(), sizeof(cb.transform));
        D3D11_MAPPED_SUBRESOURCE ms = {};
        if (SUCCEEDED(m_ctx->Map(m_cbuf, 0, D3D11_MAP_WRITE_DISCARD, 0, &ms))) {
            memcpy(ms.pData, &cb, sizeof(cb));
            m_ctx->Unmap(m_cbuf, 0);
        }

        UINT stride = sizeof(Rml::Vertex), offset = 0;
        m_ctx->IASetVertexBuffers(0, 1, &g->vb, &stride, &offset);
        m_ctx->IASetIndexBuffer(g->ib, DXGI_FORMAT_R32_UINT, 0);
        m_ctx->IASetInputLayout(m_il);
        m_ctx->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
        m_ctx->VSSetShader(m_vs, nullptr, 0);
        m_ctx->VSSetConstantBuffers(0, 1, &m_cbuf);
        m_ctx->PSSetShader(m_ps, nullptr, 0);
        m_ctx->PSSetShaderResources(0, 1, &m_whiteSRV);
        m_ctx->PSSetSamplers(0, 1, &m_samp);
        m_ctx->OMSetBlendState(m_bsNoColorWrite, nullptr, 0xFFFFFFFF); // stencil-only write, no visible color
        m_ctx->OMSetDepthStencilState(m_dssClipWrite, writeRef);
        m_ctx->RSSetState(m_scissorEnabled ? m_rsScissorOn : m_rsScissorOff);
        m_ctx->DrawIndexed(g->indexCount, 0, 0);
    }

    // ── Filters (Phase B — box-shadow blur) ─────────────────────────────
    // Only "blur" is handled: nothing in this document's RCSS ever
    // requests opacity/drop-shadow/grayscale/etc. filters, so those
    // branches (which GL3's reference backend does implement) aren't
    // needed here — matches GL3's own fallback of logging and returning an
    // invalid handle for anything else it doesn't recognize either.
    Rml::CompiledFilterHandle CompileFilter(const Rml::String &name, const Rml::Dictionary &parameters) override {
        if (name == "blur") {
            auto *f = new CompiledFilter();
            f->sigma = Rml::Get(parameters, "sigma", 1.0f);
            return reinterpret_cast<Rml::CompiledFilterHandle>(f);
        }
        Log("[RmlOverlay] CompileFilter: unsupported filter '%s' (only \"blur\" is implemented)", name.c_str());
        return 0;
    }

    void ReleaseFilter(Rml::CompiledFilterHandle filter) override {
        delete reinterpret_cast<CompiledFilter*>(filter);
    }

private:
    struct GeometryData {
        ID3D11Buffer *vb = nullptr;
        ID3D11Buffer *ib = nullptr;
        UINT indexCount = 0;
    };
    struct TextureData {
        ID3D11Texture2D *tex = nullptr;
        ID3D11ShaderResourceView *srv = nullptr;
    };

    // ── Layer-pool / clip-mask helpers ──────────────────────────────────
    ID3D11ShaderResourceView *LayerSRV(Rml::LayerHandle h) const {
        if (h == 0) return nullptr; // base layer has no texture view — it's the swapchain
        int slot = (int)h - 1;
        return (slot >= 0 && slot < MAX_LAYERS) ? m_layerPool[slot].srv : nullptr;
    }
    ID3D11RenderTargetView *LayerRTV(Rml::LayerHandle h) const {
        if (h == 0) return m_baseRTV;
        int slot = (int)h - 1;
        return (slot >= 0 && slot < MAX_LAYERS) ? m_layerPool[slot].rtv : nullptr;
    }
    ID3D11Texture2D *LayerTex(Rml::LayerHandle h) const {
        if (h == 0) return nullptr; // SaveLayerAsTexture is never called on the base layer in this design
        int slot = (int)h - 1;
        return (slot >= 0 && slot < MAX_LAYERS) ? m_layerPool[slot].tex : nullptr;
    }

    // Rebinds whatever the stack's current top is (or the base layer if the
    // stack is empty) as the active render target — used by PopLayer and by
    // CompositeLayers when it needs to restore the render target after
    // rendering into a non-top destination layer.
    void RebindTopLayer() {
        if (!m_ctx) return;
        ID3D11RenderTargetView *rtv = m_layerStack.empty() ? m_baseRTV : LayerRTV(m_layerStack.back());
        if (rtv) m_ctx->OMSetRenderTargets(1, &rtv, m_stencilDSV);
    }

    // Lazily (re)creates the viewport-sized layer pool. Called from
    // PushLayer, so a resize is picked up the next time a layer is needed
    // rather than requiring an explicit resize hook.
    bool EnsureLayerPool() {
        int w = (std::max)(1, (int)m_vpW), h = (std::max)(1, (int)m_vpH);
        if (m_layerPoolW == w && m_layerPoolH == h && m_layerPool[0].tex) return true;
        if (!m_dev) return false;
        for (int i = 0; i < MAX_LAYERS; i++) {
            if (m_layerPool[i].srv) m_layerPool[i].srv->Release();
            if (m_layerPool[i].rtv) m_layerPool[i].rtv->Release();
            if (m_layerPool[i].tex) m_layerPool[i].tex->Release();
            m_layerPool[i] = LayerData{};
        }
        D3D11_TEXTURE2D_DESC td = {};
        td.Width = (UINT)w;
        td.Height = (UINT)h;
        td.MipLevels = 1;
        td.ArraySize = 1;
        td.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
        td.SampleDesc.Count = 1;
        td.Usage = D3D11_USAGE_DEFAULT;
        td.BindFlags = D3D11_BIND_RENDER_TARGET | D3D11_BIND_SHADER_RESOURCE;
        bool ok = true;
        for (int i = 0; i < MAX_LAYERS; i++) {
            if (FAILED(m_dev->CreateTexture2D(&td, nullptr, &m_layerPool[i].tex))) { ok = false; break; }
            if (FAILED(m_dev->CreateRenderTargetView(m_layerPool[i].tex, nullptr, &m_layerPool[i].rtv))) { ok = false; break; }
            if (FAILED(m_dev->CreateShaderResourceView(m_layerPool[i].tex, nullptr, &m_layerPool[i].srv))) { ok = false; break; }
        }
        if (!ok) {
            Log("[RmlOverlay] EnsureLayerPool: failed to create layer pool at %dx%d", w, h);
            return false;
        }
        m_layerPoolW = w; m_layerPoolH = h;
        return true;
    }

    // Lazily (re)creates the viewport-sized stencil buffer. Called both from
    // SetBaseRenderTarget (every frame — cheap no-op once sized correctly)
    // and from RenderToClipMask, so it's guaranteed to exist before either
    // could need it.
    bool EnsureStencilBuffer() {
        int w = (std::max)(1, (int)m_vpW), h = (std::max)(1, (int)m_vpH);
        if (m_stencilW == w && m_stencilH == h && m_stencilDSV) return true;
        if (!m_dev) return false;
        if (m_stencilDSV) { m_stencilDSV->Release(); m_stencilDSV = nullptr; }
        if (m_stencilTex) { m_stencilTex->Release(); m_stencilTex = nullptr; }
        D3D11_TEXTURE2D_DESC td = {};
        td.Width = (UINT)w;
        td.Height = (UINT)h;
        td.MipLevels = 1;
        td.ArraySize = 1;
        td.Format = DXGI_FORMAT_D24_UNORM_S8_UINT;
        td.SampleDesc.Count = 1;
        td.Usage = D3D11_USAGE_DEFAULT;
        td.BindFlags = D3D11_BIND_DEPTH_STENCIL;
        if (FAILED(m_dev->CreateTexture2D(&td, nullptr, &m_stencilTex))) {
            Log("[RmlOverlay] EnsureStencilBuffer: CreateTexture2D failed at %dx%d", w, h);
            return false;
        }
        if (FAILED(m_dev->CreateDepthStencilView(m_stencilTex, nullptr, &m_stencilDSV))) {
            Log("[RmlOverlay] EnsureStencilBuffer: CreateDepthStencilView failed");
            m_stencilTex->Release(); m_stencilTex = nullptr;
            return false;
        }
        m_stencilW = w; m_stencilH = h;
        return true;
    }

    // Draws a full-viewport textured quad (reusing the existing
    // CompileGeometry/RenderGeometry pipeline — see the field comment on
    // m_blitQuad) with identity transform/translation, opaque-white vertex
    // color (so the pixel shader's `vertexColor * textureSample` is a pure
    // passthrough of the source texture), into whatever render target is
    // currently bound. `replaceBlend` selects BlendMode::Replace
    // (blend-disabled overwrite) vs the default premultiplied-alpha blend.
    // `ps`, if given, overrides the pixel shader (used by ApplyBlur to draw
    // with PSBlur instead of the default textured-passthrough PSMain);
    // `extraCB`, if given, is additionally bound at register b1 for that
    // custom shader's own parameters (BlurParams for PSBlur).
    void BlitFullscreen(ID3D11ShaderResourceView *srv, bool replaceBlend, ID3D11PixelShader *ps = nullptr, ID3D11Buffer *extraCB = nullptr) {
        if (!m_ctx || !srv) return;
        int w = (std::max)(1, (int)m_vpW), h = (std::max)(1, (int)m_vpH);
        if (m_blitQuadW != w || m_blitQuadH != h || !m_blitQuad) {
            if (m_blitQuad) { ReleaseGeometry(m_blitQuad); m_blitQuad = 0; }
            Rml::Vertex verts[4];
            verts[0].position = {0.f, 0.f};       verts[0].tex_coord = {0.f, 0.f};
            verts[1].position = {(float)w, 0.f};  verts[1].tex_coord = {1.f, 0.f};
            verts[2].position = {(float)w, (float)h}; verts[2].tex_coord = {1.f, 1.f};
            verts[3].position = {0.f, (float)h};  verts[3].tex_coord = {0.f, 1.f};
            for (auto &v : verts) v.colour = Rml::ColourbPremultiplied(255, 255, 255, 255);
            int indices[6] = {0, 1, 2, 0, 2, 3};
            m_blitQuad = CompileGeometry(Rml::Span<const Rml::Vertex>(verts, 4), Rml::Span<const int>(indices, 6));
            m_blitQuadW = w; m_blitQuadH = h;
        }
        if (!m_blitQuad) return;

        // Full-viewport blit needs an identity transform regardless of
        // whatever CSS transform was active on the element that triggered
        // this composite — save/restore around the call so it can't leak
        // into whatever RenderGeometry call comes after.
        Rml::Matrix4f savedTransform = m_cssTransform;
        m_cssTransform = Rml::Matrix4f::Identity();

        ID3D11BlendState *savedBS = replaceBlend ? m_bsReplace : m_bs;
        auto *g = reinterpret_cast<GeometryData*>(m_blitQuad);
        struct { float tx, ty, vw, vh; float transform[16]; } cb = {0.f, 0.f, m_vpW, m_vpH, {}};
        memcpy(cb.transform, m_cssTransform.data(), sizeof(cb.transform));
        D3D11_MAPPED_SUBRESOURCE ms = {};
        if (SUCCEEDED(m_ctx->Map(m_cbuf, 0, D3D11_MAP_WRITE_DISCARD, 0, &ms))) {
            memcpy(ms.pData, &cb, sizeof(cb));
            m_ctx->Unmap(m_cbuf, 0);
        }
        UINT stride = sizeof(Rml::Vertex), offset = 0;
        m_ctx->IASetVertexBuffers(0, 1, &g->vb, &stride, &offset);
        m_ctx->IASetIndexBuffer(g->ib, DXGI_FORMAT_R32_UINT, 0);
        m_ctx->IASetInputLayout(m_il);
        m_ctx->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
        m_ctx->VSSetShader(m_vs, nullptr, 0);
        m_ctx->VSSetConstantBuffers(0, 1, &m_cbuf);
        m_ctx->PSSetShader(ps ? ps : m_ps, nullptr, 0);
        m_ctx->PSSetShaderResources(0, 1, &srv);
        m_ctx->PSSetSamplers(0, 1, &m_samp);
        if (extraCB) m_ctx->PSSetConstantBuffers(1, 1, &extraCB);
        m_ctx->OMSetBlendState(savedBS, nullptr, 0xFFFFFFFF);
        m_ctx->OMSetDepthStencilState(m_clipMaskEnabled ? m_dssClipTest : m_dss, 1);
        m_ctx->RSSetState(m_rsScissorOff);
        m_ctx->DrawIndexed(g->indexCount, 0, 0);

        m_cssTransform = savedTransform;
    }

    // Lazily (re)creates the viewport-sized blur scratch target.
    bool EnsureBlurScratch() {
        int w = (std::max)(1, (int)m_vpW), h = (std::max)(1, (int)m_vpH);
        if (m_blurScratchW == w && m_blurScratchH == h && m_blurScratchTex) return true;
        if (!m_dev) return false;
        if (m_blurScratchSRV) { m_blurScratchSRV->Release(); m_blurScratchSRV = nullptr; }
        if (m_blurScratchRTV) { m_blurScratchRTV->Release(); m_blurScratchRTV = nullptr; }
        if (m_blurScratchTex) { m_blurScratchTex->Release(); m_blurScratchTex = nullptr; }
        D3D11_TEXTURE2D_DESC td = {};
        td.Width = (UINT)w;
        td.Height = (UINT)h;
        td.MipLevels = 1;
        td.ArraySize = 1;
        td.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
        td.SampleDesc.Count = 1;
        td.Usage = D3D11_USAGE_DEFAULT;
        td.BindFlags = D3D11_BIND_RENDER_TARGET | D3D11_BIND_SHADER_RESOURCE;
        if (FAILED(m_dev->CreateTexture2D(&td, nullptr, &m_blurScratchTex))) return false;
        if (FAILED(m_dev->CreateRenderTargetView(m_blurScratchTex, nullptr, &m_blurScratchRTV))) return false;
        if (FAILED(m_dev->CreateShaderResourceView(m_blurScratchTex, nullptr, &m_blurScratchSRV))) return false;
        m_blurScratchW = w; m_blurScratchH = h;
        return true;
    }

    // Computes normalized Gaussian weights for the given sigma (same
    // formula as RmlUi's own GL3 backend's SetBlurWeights — ported
    // directly rather than re-derived) and uploads them to m_blurCbuf
    // along with the per-pass texel offset. Returns the tap radius used
    // (kernel covers roughly +/- 3 sigma, clamped to BLUR_MAX_RADIUS).
    int UploadBlurWeights(float sigma, bool horizontal) {
        int radius = (std::min)(BLUR_MAX_RADIUS, (std::max)(0, (int)ceilf(sigma * 3.f)));
        float weights[BLUR_MAX_RADIUS + 1] = {};
        float normalization = 0.f;
        for (int i = 0; i <= radius; i++) {
            if (fabsf(sigma) < 0.1f) weights[i] = (i == 0) ? 1.f : 0.f;
            else weights[i] = expf(-(float)(i * i) / (2.f * sigma * sigma)) / (sqrtf(2.f * 3.14159265f) * sigma);
            normalization += (i == 0 ? 1.f : 2.f) * weights[i];
        }
        if (normalization > 0.f) for (int i = 0; i <= radius; i++) weights[i] /= normalization;

        struct { float ox, oy; int radius; float pad; float w[BLUR_MAX_RADIUS + 1][4]; } cb = {};
        cb.ox = horizontal ? (1.f / (std::max)(1.f, m_vpW)) : 0.f;
        cb.oy = horizontal ? 0.f : (1.f / (std::max)(1.f, m_vpH));
        cb.radius = radius;
        for (int i = 0; i <= radius; i++) cb.w[i][0] = weights[i];

        D3D11_MAPPED_SUBRESOURCE ms = {};
        if (m_ctx && SUCCEEDED(m_ctx->Map(m_blurCbuf, 0, D3D11_MAP_WRITE_DISCARD, 0, &ms))) {
            memcpy(ms.pData, &cb, sizeof(cb));
            m_ctx->Unmap(m_blurCbuf, 0);
        }
        return radius;
    }

    // Blurs the given layer's texture in place: horizontal pass writes
    // layer -> m_blurScratch, vertical pass writes m_blurScratch -> back
    // into the same layer's own render target. Only one scratch buffer is
    // needed (vs. GL3's ping-pong pair) because this design's fixed-
    // resolution simplification (see the Phase 3 plan) never needs more
    // than these exact two passes — no iterative downscale/upscale steps
    // that would need alternating between two same-sized buffers.
    void ApplyBlur(float sigma, Rml::LayerHandle layer) {
        if (!m_ctx || !m_psBlur || !EnsureBlurScratch()) return;
        ID3D11ShaderResourceView *srcSRV = LayerSRV(layer);
        ID3D11RenderTargetView *srcRTV = LayerRTV(layer);
        if (!srcSRV || !srcRTV) return;

        // These two passes process the whole layer's pixel content (a blur
        // filter implementation detail) — not "rendering to destination"
        // the way RenderInterface.h's clip-mask doc comment means for
        // CompositeLayers itself. Bypass whatever clip mask is currently
        // active (it was very likely just set up by GeometryBoxShadow.cpp
        // to mask the *shadow shape* draw that happens right before this,
        // per the call sequence in the Phase 3 plan) so these full-buffer
        // blur passes aren't accidentally clipped to that unrelated
        // region, leaving stale/uninitialized scratch-buffer content
        // outside it. Restored before returning so the *next* thing that
        // runs — CompositeLayers' own final blit-to-destination, which
        // legitimately should respect the mask per that same doc comment —
        // still sees the correct state.
        bool savedClipMask = m_clipMaskEnabled;
        m_clipMaskEnabled = false;

        UploadBlurWeights(sigma, /*horizontal=*/true);
        m_ctx->OMSetRenderTargets(1, &m_blurScratchRTV, nullptr);
        BlitFullscreen(srcSRV, /*replaceBlend=*/true, m_psBlur, m_blurCbuf);

        UploadBlurWeights(sigma, /*horizontal=*/false);
        m_ctx->OMSetRenderTargets(1, &srcRTV, nullptr);
        BlitFullscreen(m_blurScratchSRV, /*replaceBlend=*/true, m_psBlur, m_blurCbuf);

        m_clipMaskEnabled = savedClipMask;
    }

    ID3D11Device *m_dev = nullptr;
    ID3D11DeviceContext *m_ctx = nullptr;
    float m_vpW = 0.f, m_vpH = 0.f;
    bool m_scissorEnabled = false;
    // Current CSS `transform` matrix (RenderInterface::SetTransform), reset
    // to identity between elements that don't have one — RmlUi calls
    // SetTransform(nullptr) itself for that case (see ElementStyle.cpp),
    // not something this class has to detect on its own.
    Rml::Matrix4f m_cssTransform = Rml::Matrix4f::Identity();

    bool m_resourcesReady = false;
    ID3D11VertexShader *m_vs = nullptr;
    ID3D11PixelShader *m_ps = nullptr;
    ID3D11InputLayout *m_il = nullptr;
    ID3D11Buffer *m_cbuf = nullptr;
    ID3D11BlendState *m_bs = nullptr;
    ID3D11RasterizerState *m_rsScissorOn = nullptr;
    ID3D11RasterizerState *m_rsScissorOff = nullptr;
    ID3D11DepthStencilState *m_dss = nullptr;
    ID3D11SamplerState *m_samp = nullptr;
    ID3D11Texture2D *m_whiteTex = nullptr;
    ID3D11ShaderResourceView *m_whiteSRV = nullptr;

    // ── Box-shadow support, Phase A: layer stack + stencil clip mask ───────
    // See C:\Users\Miguel\.claude\plans\delegated-yawning-sunrise.md for the
    // full design. Layer handle 0 is reserved by RmlUi's own contract for
    // "the base layer" — mapped here to m_baseRTV (this frame's real
    // swapchain backbuffer view, set once per frame by SetBaseRenderTarget,
    // called from RmlOverlay_RenderFrame right where the backbuffer RTV is
    // bound) rather than a pooled slot. PushLayer() handles are 1-based
    // indices into m_layerPool.
    struct LayerData {
        ID3D11Texture2D *tex = nullptr;
        ID3D11RenderTargetView *rtv = nullptr;
        ID3D11ShaderResourceView *srv = nullptr;
    };
    static const int MAX_LAYERS = 6;
    LayerData m_layerPool[MAX_LAYERS] = {};
    int m_layerPoolW = 0, m_layerPoolH = 0; // dimensions the pool was last (re)built at
    std::vector<Rml::LayerHandle> m_layerStack; // empty = currently rendering to the base layer
    ID3D11RenderTargetView *m_baseRTV = nullptr; // non-owning; valid only between SetBaseRenderTarget() and EndFrame()

    // Extra pipeline objects needed for compositing (blitting one layer's
    // texture onto another) and for disabling color writes during a
    // clip-mask stencil-write pass — both reuse the existing VSMain/PSMain
    // shader and geometry pipeline, just with different fixed-function
    // state, so no new shader programs are needed for Phase A.
    ID3D11BlendState *m_bsReplace = nullptr;      // blend disabled — straight overwrite, for BlendMode::Replace
    ID3D11BlendState *m_bsNoColorWrite = nullptr; // color writes off — for the clip-mask stencil-write pass
    Rml::CompiledGeometryHandle m_blitQuad = 0;   // reused full-viewport quad for CompositeLayers' blit
    int m_blitQuadW = 0, m_blitQuadH = 0;         // dimensions m_blitQuad was last built at

    // Stencil-based clip mask (RenderInterface::EnableClipMask/
    // RenderToClipMask) — used both by box-shadow's inverse-clip and, it
    // turns out, by plain `overflow: hidden` on any border-radius'd element
    // (confirmed in Source/Core/ElementUtilities.cpp: rounded overflow
    // clipping goes through this same RenderToClipMask path, not a plain
    // scissor rect — #hero-img-wrap in menu.rml is exactly this case, so
    // this was silently never clipping correctly before this either).
    ID3D11Texture2D *m_stencilTex = nullptr;
    ID3D11DepthStencilView *m_stencilDSV = nullptr;
    int m_stencilW = 0, m_stencilH = 0;
    // Invariant maintained by RenderToClipMask: stencil value 1 = pixel is
    // within the active clip region, 0 = clipped out. One "always pass,
    // write ref" state (parameterized by ref at bind time: ref=1 for Set's
    // covered area, ref=0 for SetInverse's covered area) and one "equal
    // ref=1, read-only" state used by RenderGeometry/the compositing blit
    // while a mask is active.
    ID3D11DepthStencilState *m_dssClipWrite = nullptr;
    ID3D11DepthStencilState *m_dssClipTest = nullptr;
    bool m_clipMaskEnabled = false;

    // SetScissorRegion doesn't otherwise remember the rect anywhere —
    // SaveLayerAsTexture() needs it (RmlUi's contract: extract exactly the
    // active scissor region as the new texture's bounds).
    D3D11_RECT m_currentScissor = {};

    // ── Box-shadow support, Phase B: blur ───────────────────────────────
    ID3D11PixelShader *m_psBlur = nullptr;
    ID3D11Buffer *m_blurCbuf = nullptr; // register b1 — see kRmlShaderSrc's BlurParams comment
    static const int BLUR_MAX_RADIUS = 40; // must track kRmlShaderSrc's #define
    // One viewport-sized scratch target: ApplyBlur's horizontal pass
    // writes source-layer -> here, then the vertical pass writes
    // here -> back into the source layer (which CompositeLayers then
    // blits from as usual) — see ApplyBlur's own comment for why only one
    // scratch buffer is needed instead of GL3's ping-pong pair.
    ID3D11Texture2D *m_blurScratchTex = nullptr;
    ID3D11RenderTargetView *m_blurScratchRTV = nullptr;
    ID3D11ShaderResourceView *m_blurScratchSRV = nullptr;
    int m_blurScratchW = 0, m_blurScratchH = 0;

    struct CompiledFilter {
        float sigma = 1.f;
    };
};

// ---------------------------------------------------------------------------
// CgfsRmlSystemInterface — only GetElapsedTime/LogMessage overridden; the
// rest (clipboard, cursor, on-screen keyboard) keep RmlUi's usable defaults.
// Origin: Phase 0 POC, unchanged.
// ---------------------------------------------------------------------------
class CgfsRmlSystemInterface : public Rml::SystemInterface {
public:
    CgfsRmlSystemInterface() {
        QueryPerformanceFrequency(&m_freq);
        QueryPerformanceCounter(&m_start);
    }

    double GetElapsedTime() override {
        LARGE_INTEGER now;
        QueryPerformanceCounter(&now);
        return double(now.QuadPart - m_start.QuadPart) / double(m_freq.QuadPart);
    }

    bool LogMessage(Rml::Log::Type /*type*/, const Rml::String &message) override {
        Log("[RmlUi] %s", message.c_str());
        return true;
    }

private:
    LARGE_INTEGER m_freq = {};
    LARGE_INTEGER m_start = {};
};

// ---------------------------------------------------------------------------
// CgfsRmlFileInterface — loads the .rml/.rcss documents from disk. Not
// RmlUi's built-in default file interface (Source/Core/FileInterfaceDefault.cpp):
// that one calls plain fopen() on the narrow-char path as-is, which on
// Windows goes through the process ANSI codepage rather than UTF-8, so a
// resources path containing non-ASCII characters (accented folder/user
// names — common on this project's userbase) could fail to open even though
// the file exists. _wfopen keeps this consistent with the rest of the DLL,
// which always goes through wide-char Win32 APIs for file paths.
// ---------------------------------------------------------------------------
class CgfsRmlFileInterface : public Rml::FileInterface {
public:
    Rml::FileHandle Open(const Rml::String &path) override {
        int wlen = MultiByteToWideChar(CP_UTF8, 0, path.c_str(), -1, nullptr, 0);
        if (wlen <= 0) return 0;
        std::wstring wpath((size_t)wlen, L'\0');
        MultiByteToWideChar(CP_UTF8, 0, path.c_str(), -1, wpath.data(), wlen);
        FILE *f = _wfopen(wpath.c_str(), L"rb");
        if (!f) Log("[RmlOverlay] FileInterface::Open failed for '%s'", path.c_str());
        return reinterpret_cast<Rml::FileHandle>(f);
    }
    void Close(Rml::FileHandle file) override {
        if (file) fclose(reinterpret_cast<FILE*>(file));
    }
    size_t Read(void *buffer, size_t size, Rml::FileHandle file) override {
        return file ? fread(buffer, 1, size, reinterpret_cast<FILE*>(file)) : 0;
    }
    bool Seek(Rml::FileHandle file, long offset, int origin) override {
        return file && fseek(reinterpret_cast<FILE*>(file), offset, origin) == 0;
    }
    size_t Tell(Rml::FileHandle file) override {
        return file ? (size_t)ftell(reinterpret_cast<FILE*>(file)) : 0;
    }
};

// ---------------------------------------------------------------------------
// Module state
// ---------------------------------------------------------------------------
static CgfsRmlRenderInterface *g_renderIf = nullptr;
static CgfsRmlSystemInterface *g_systemIf = nullptr;
static CgfsRmlFileInterface   *g_fileIf = nullptr;
static Rml::Context           *g_context = nullptr;
static bool                    g_initDone = false;
static bool                    g_initFailed = false;

// Toast document + cached per-slot elements (avoids a GetElementById scan every frame).
static Rml::ElementDocument *g_toastDoc = nullptr;
static Rml::Element         *g_toastSlot[MAX_TOASTS] = {};
static Rml::Element         *g_toastTitle[MAX_TOASTS] = {};
static Rml::Element         *g_toastBody[MAX_TOASTS] = {};
static bool                  g_toastSlotShown[MAX_TOASTS] = {};

// Stadium-loading document + cached elements.
static Rml::ElementDocument *g_stadiumDoc = nullptr;
static Rml::Element         *g_stadiumTitle = nullptr;
static Rml::Element         *g_stadiumName = nullptr;
static Rml::Element         *g_stadiumDetail = nullptr;
static Rml::Element         *g_stadiumImg = nullptr;
static Rml::Element         *g_stadiumFill = nullptr;
static wchar_t                g_stadiumImgPathLoaded[MAX_IMG] = {};

static bool EnsureInit(ID3D11Device *dev, int vpW, int vpH) {
    if (g_initDone) return true;
    if (g_initFailed) return false;

    // WIC (used by LoadWICTexture, for the stadium preview <img>) needs COM
    // initialized on the calling thread. The old DrawOverlay11/DrawMenuOverlay11
    // each had their own lazy CoInitializeEx guard on this same render thread;
    // this is that same pattern for this file, since DrawOverlay11 (the only
    // *other* COM-initializing call that could still run before this one, e.g.
    // if a stadium loads before the F12 menu is ever opened) was removed as
    // part of this migration. Without this, CoCreateInstance(CLSID_WICImagingFactory)
    // fails with CO_E_NOTINITIALIZED and the preview image silently never loads.
    static bool s_comInit = false;
    if (!s_comInit) {
        s_comInit = true;
        HRESULT cohr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
        Log("[RmlOverlay] CoInitializeEx hr=0x%08X", (unsigned)cohr);
    }

    g_renderIf = new CgfsRmlRenderInterface();
    if (!g_renderIf->EnsureDeviceResources(dev)) {
        Log("[RmlOverlay] EnsureDeviceResources failed");
        g_initFailed = true;
        return false;
    }
    g_systemIf = new CgfsRmlSystemInterface();
    g_fileIf = new CgfsRmlFileInterface();

    Rml::SetSystemInterface(g_systemIf);
    Rml::SetRenderInterface(g_renderIf);
    Rml::SetFileInterface(g_fileIf);

    if (!Rml::Initialise()) {
        Log("[RmlOverlay] Rml::Initialise failed");
        g_initFailed = true;
        return false;
    }

    if (!Rml::LoadFontFace("C:\\Windows\\Fonts\\segoeui.ttf")) {
        Log("[RmlOverlay] LoadFontFace failed for C:\\Windows\\Fonts\\segoeui.ttf");
    }

    // Content dir is needed here (not just for documents below) because the
    // Phase 3 headline fonts (Teko/Rajdhani) ship as loose .ttf files under
    // resources/rmlui/fonts/, not as Windows system fonts like Segoe UI.
    const wchar_t *contentDirW = RmlOverlay_ContentDir();
    if (!contentDirW || !contentDirW[0]) {
        Log("[RmlOverlay] rmlui_content_dir is empty — resources/rmlui/ was not "
            "found/handed over by Python. Toasts and the stadium-loading panel "
            "will not render.");
        g_initFailed = true;
        return false;
    }
    {
        // Teko is a variable-weight font (google/fonts ships no static Teko
        // weight instances) — loaded once, RmlUi/FreeType renders it at
        // whatever weight its default named instance is; that's an accepted
        // simplification (see the Phase 3 plan notes), not a bug, since
        // Teko's condensed shape is the point, not a specific 600-vs-700
        // distinction. Rajdhani ships proper static Regular/SemiBold/Bold
        // files, so those load as distinct weights the normal way (matches
        // how segoeui.ttf/segoeuib.ttf would if this DLL ever needed a bold
        // Segoe UI face).
        Rml::String contentDir = WideToUtf8(contentDirW);
        static const char *const kHeadlineFonts[] = {
            "\\fonts\\Teko-Variable.ttf",
            "\\fonts\\Rajdhani-SemiBold.ttf",
            "\\fonts\\Rajdhani-Bold.ttf",
        };
        for (const char *rel : kHeadlineFonts) {
            Rml::String path = contentDir + rel;
            if (!Rml::LoadFontFace(path)) {
                Log("[RmlOverlay] LoadFontFace failed for '%s'", path.c_str());
            }
        }
    }

    g_context = Rml::CreateContext("cgfs16_overlay", Rml::Vector2i(vpW, vpH));
    if (!g_context) {
        Log("[RmlOverlay] CreateContext failed");
        g_initFailed = true;
        return false;
    }
    Rml::String contentDir = WideToUtf8(contentDirW);
    Rml::String toastPath = contentDir + "\\" + kToastDocFile;
    Rml::String stadiumPath = contentDir + "\\" + kStadiumDocFile;

    // Load the (still dev-gated, Phase 2 WIP) menu document FIRST so it
    // renders below the toast/stadium docs, preserving the existing
    // "menu -> stadium loading -> toasts, toasts always on top" draw order
    // with no extra code (RmlUi renders attached documents in load order).
    // A failure here only disables the F6 dev preview — it must not break
    // the already-shipped toast/stadium-panel rendering below.
    if (!RmlMenu_Load(g_context, contentDir))
        Log("[RmlOverlay] RmlMenu_Load failed — F6 dev menu preview unavailable");

    g_toastDoc = g_context->LoadDocument(toastPath);
    g_stadiumDoc = g_context->LoadDocument(stadiumPath);
    if (!g_toastDoc || !g_stadiumDoc) {
        Log("[RmlOverlay] LoadDocument failed (toast='%s' -> %p, stadium='%s' -> %p)",
            toastPath.c_str(), (void*)g_toastDoc, stadiumPath.c_str(), (void*)g_stadiumDoc);
        g_initFailed = true;
        return false;
    }

    char idBuf[16];
    for (int i = 0; i < MAX_TOASTS; ++i) {
        snprintf(idBuf, sizeof(idBuf), "toast%d", i);
        g_toastSlot[i] = g_toastDoc->GetElementById(idBuf);
        if (g_toastSlot[i]) {
            g_toastTitle[i] = g_toastSlot[i]->QuerySelector(".title");
            g_toastBody[i] = g_toastSlot[i]->QuerySelector(".body");
        }
    }
    g_stadiumTitle = g_stadiumDoc->GetElementById("title");
    g_stadiumName = g_stadiumDoc->GetElementById("name");
    g_stadiumDetail = g_stadiumDoc->GetElementById("detail");
    g_stadiumImg = g_stadiumDoc->GetElementById("preview-img");
    g_stadiumFill = g_stadiumDoc->GetElementById("progress-fill");

    // Both documents start hidden; RmlOverlay_RenderFrame shows/hides them
    // per frame based on the shared-memory visibility flags.

    Log("[RmlOverlay] Init ok");
    g_initDone = true;
    return true;
}

static void SyncToasts(bool stadiumPanelVisible, bool &outAnyToast) {
    outAnyToast = false;

    // Shift the whole stack down below the stadium panel when it's also
    // showing, same as the old renderer (kStadOverlayH=140 + a small gap).
    g_toastDoc->SetProperty("top", stadiumPanelVisible ? "168px" : "20px");

    for (int i = 0; i < MAX_TOASTS; ++i) {
        if (!g_toastSlot[i]) continue;
        bool visible = RmlOverlay_ToastVisible(i);
        if (visible) outAnyToast = true;
        if (visible != g_toastSlotShown[i]) {
            g_toastSlot[i]->SetClass("shown", visible);
            g_toastSlotShown[i] = visible;
        }
        if (!visible) continue;

        g_toastSlot[i]->SetClass("warning", RmlOverlay_ToastWarning(i));
        if (g_toastTitle[i]) g_toastTitle[i]->SetInnerRML(WideToUtf8(RmlOverlay_ToastTitle(i)));
        if (g_toastBody[i]) g_toastBody[i]->SetInnerRML(WideToUtf8(RmlOverlay_ToastBody(i)));
    }
}

static void SyncStadiumPanel() {
    const wchar_t *panelTitle = RmlOverlay_PanelTitle();
    Rml::String titleText = (panelTitle && panelTitle[0]) ? WideToUtf8(panelTitle) : Rml::String("Loading Stadium");
    if (g_stadiumTitle) g_stadiumTitle->SetInnerRML(titleText);

    if (g_stadiumName) g_stadiumName->SetInnerRML(WideToUtf8(RmlOverlay_StadiumName()));
    if (g_stadiumDetail) g_stadiumDetail->SetInnerRML(WideToUtf8(RmlOverlay_DetailText()));

    int progress = RmlOverlay_ProgressX100();
    float pct = (std::max)(0.f, (std::min)(100.f, (float)progress / 100.f));
    if (g_stadiumFill) {
        char buf[16];
        snprintf(buf, sizeof(buf), "%.1f%%", pct);
        g_stadiumFill->SetProperty("width", buf);
    }

    const wchar_t *imgPath = RmlOverlay_ImagePath();
    if (wcscmp(imgPath, g_stadiumImgPathLoaded) != 0) {
        wcscpy_s(g_stadiumImgPathLoaded, imgPath);
        if (g_stadiumImg) {
            if (imgPath[0]) {
                Rml::String utf8Path = WideToUtf8(imgPath);
                Log("[RmlOverlay] stadium preview src -> '%s' (element=%p)", utf8Path.c_str(), (void*)g_stadiumImg);
                g_stadiumImg->SetAttribute("src", utf8Path);
                g_stadiumImg->SetProperty("display", "block");
            } else {
                Log("[RmlOverlay] stadium preview src -> (empty)");
                g_stadiumImg->SetProperty("display", "none");
            }
        } else {
            Log("[RmlOverlay] stadium preview img element is null (GetElementById('preview-img') failed?)");
        }
    }
}

void RmlOverlay_RenderFrame(IDXGISwapChain *sc, ID3D11Device *dev, ID3D11DeviceContext *ctx) {
    if (!sc || !dev || !ctx) return;

    bool stadiumVisible = RmlOverlay_StadiumPanelVisible();

    bool anyToastRaw = false;
    for (int i = 0; i < MAX_TOASTS && !anyToastRaw; ++i)
        anyToastRaw = RmlOverlay_ToastVisible(i);
    bool menuVisible = RmlOverlay_MenuVisible();
    // RmlMenu_DocShown() covers the brief window right after menuVisible
    // flips to 0 where #panel's close-out zoom animation is still playing —
    // without it, this early-return would skip RmlMenu_Sync on the very
    // first closed frame, starving that animation of frames and leaving
    // #panel permanently Shown() in RmlUi's own bookkeeping (see
    // RmlMenu_DocShown's header comment for the full failure chain).
    if (!stadiumVisible && !anyToastRaw && !menuVisible && !RmlMenu_DocShown()) return;

    DXGI_SWAP_CHAIN_DESC scd = {};
    sc->GetDesc(&scd);
    int vpW = (int)scd.BufferDesc.Width;
    int vpH = (int)scd.BufferDesc.Height;
    if (vpW <= 0 || vpH <= 0) return;

    if (!EnsureInit(dev, vpW, vpH)) return;

    // BeginFrame goes here, before ANY element/attribute mutation below — not
    // just before Update() as a prior version of this function assumed.
    // SetAttribute("src", ...) on an <img> synchronously triggers RmlUi's
    // internal texture load (RenderInterface::LoadTexture) right then and
    // there, not deferred to Update(): confirmed via log (`LoadTexture called
    // ... m_dev=0000000000000000`) showing it fired from inside SyncStadiumPanel(),
    // before BeginFrame had run when it was still called right before Update().
    g_renderIf->BeginFrame(dev, ctx, (float)vpW, (float)vpH);

    if (g_context->GetDimensions() != Rml::Vector2i(vpW, vpH))
        g_context->SetDimensions(Rml::Vector2i(vpW, vpH));

    bool anyToast = false;
    SyncToasts(stadiumVisible, anyToast);
    if (stadiumVisible) SyncStadiumPanel();
    RmlMenu_Sync(vpW, vpH, scd.OutputWindow);

    if (g_toastDoc) {
        // Right-align: 360px wide stack, 20px margin from the viewport edge.
        // Computed here (not RCSS `right:`) to mirror the stadium panel's
        // proven-correct approach below rather than relying on an untested
        // property/width interaction.
        char leftBuf[16];
        snprintf(leftBuf, sizeof(leftBuf), "%dpx", vpW - 360 - 20);
        g_toastDoc->SetProperty("left", leftBuf);
        if (anyToast) g_toastDoc->Show(Rml::ModalFlag::None, Rml::FocusFlag::None); else g_toastDoc->Hide();
    }
    if (g_stadiumDoc) {
        if (stadiumVisible) {
            // Right-align: 460px wide panel, 20px margin from the viewport edge.
            char leftBuf[16];
            snprintf(leftBuf, sizeof(leftBuf), "%dpx", vpW - 460 - 20);
            g_stadiumDoc->SetProperty("left", leftBuf);
            g_stadiumDoc->Show(Rml::ModalFlag::None, Rml::FocusFlag::None);
        } else {
            g_stadiumDoc->Hide();
        }
    }

    g_context->Update();

    ID3D11Texture2D *bb = nullptr;
    if (FAILED(sc->GetBuffer(0, __uuidof(ID3D11Texture2D), (void**)&bb))) return;
    ID3D11RenderTargetView *rtv = nullptr;
    dev->CreateRenderTargetView(bb, nullptr, &rtv);
    bb->Release();
    if (!rtv) return;

    // ── Save D3D11 state — the same 12-item pattern validated in Phase 0
    // (the existing 11-item pattern used elsewhere in this DLL, plus the
    // index buffer, since RmlUi's RenderGeometry uses DrawIndexed and
    // nothing else in this DLL ever binds one).
    ID3D11RenderTargetView *oldRTV[8] = {};
    ID3D11DepthStencilView *oldDSV = nullptr;
    ctx->OMGetRenderTargets(8, oldRTV, &oldDSV);
    D3D11_VIEWPORT oldVP = {};
    UINT nVP = 1;
    ctx->RSGetViewports(&nVP, &oldVP);
    ID3D11BlendState *oldBS = nullptr;
    float oldBF[4] = {};
    UINT oldSM = 0;
    ctx->OMGetBlendState(&oldBS, oldBF, &oldSM);
    ID3D11RasterizerState *oldRS = nullptr;
    ctx->RSGetState(&oldRS);
    ID3D11DepthStencilState *oldDSS = nullptr;
    UINT oldSRef = 0;
    ctx->OMGetDepthStencilState(&oldDSS, &oldSRef);
    ID3D11VertexShader *oldVS = nullptr;
    ctx->VSGetShader(&oldVS, nullptr, nullptr);
    ID3D11PixelShader *oldPS = nullptr;
    ctx->PSGetShader(&oldPS, nullptr, nullptr);
    ID3D11InputLayout *oldIL = nullptr;
    ctx->IAGetInputLayout(&oldIL);
    D3D11_PRIMITIVE_TOPOLOGY oldTopo;
    ctx->IAGetPrimitiveTopology(&oldTopo);
    ID3D11ShaderResourceView *oldSRV = nullptr;
    ctx->PSGetShaderResources(0, 1, &oldSRV);
    ID3D11SamplerState *oldSamp = nullptr;
    ctx->PSGetSamplers(0, 1, &oldSamp);
    ID3D11Buffer *oldVBuf = nullptr;
    UINT oldVBStride = 0, oldVBOffset = 0;
    ctx->IAGetVertexBuffers(0, 1, &oldVBuf, &oldVBStride, &oldVBOffset);
    ID3D11Buffer *oldIB = nullptr;
    DXGI_FORMAT oldIBFormat = DXGI_FORMAT_UNKNOWN;
    UINT oldIBOffset = 0;
    ctx->IAGetIndexBuffer(&oldIB, &oldIBFormat, &oldIBOffset);

    // Binds rtv (+ the box-shadow clip-mask stencil buffer) as the render
    // target and remembers rtv for PopLayer() to restore whenever the
    // layer stack unwinds back to the base — see the field comment on
    // m_baseRTV in CgfsRmlRenderInterface for its non-owning-pointer
    // lifetime (valid only until EndFrame(), called below before rtv is
    // released).
    g_renderIf->SetBaseRenderTarget(rtv);
    D3D11_VIEWPORT vp = {0.f, 0.f, (float)vpW, (float)vpH, 0.f, 1.f};
    ctx->RSSetViewports(1, &vp);
    D3D11_RECT fullRect = {0, 0, (LONG)vpW, (LONG)vpH};
    ctx->RSSetScissorRects(1, &fullRect);

    g_context->Render();
    g_renderIf->EndFrame();

    // ── Restore D3D11 state ──────────────────────────────────────────────
    ctx->OMSetRenderTargets(8, oldRTV, oldDSV);
    ctx->RSSetViewports(1, &oldVP);
    ctx->OMSetBlendState(oldBS, oldBF, oldSM);
    ctx->RSSetState(oldRS);
    ctx->OMSetDepthStencilState(oldDSS, oldSRef);
    ctx->VSSetShader(oldVS, nullptr, 0);
    ctx->PSSetShader(oldPS, nullptr, 0);
    ctx->IASetInputLayout(oldIL);
    ctx->IASetVertexBuffers(0, 1, &oldVBuf, &oldVBStride, &oldVBOffset);
    ctx->IASetIndexBuffer(oldIB, oldIBFormat, oldIBOffset);
    ctx->IASetPrimitiveTopology(oldTopo);
    ctx->PSSetShaderResources(0, 1, &oldSRV);
    ctx->PSSetSamplers(0, 1, &oldSamp);
    for (auto *r : oldRTV) if (r) r->Release();
    if (oldDSV) oldDSV->Release();
    if (oldBS) oldBS->Release();
    if (oldRS) oldRS->Release();
    if (oldDSS) oldDSS->Release();
    if (oldVS) oldVS->Release();
    if (oldPS) oldPS->Release();
    if (oldIL) oldIL->Release();
    if (oldVBuf) oldVBuf->Release();
    if (oldIB) oldIB->Release();
    if (oldSRV) oldSRV->Release();
    if (oldSamp) oldSamp->Release();
    rtv->Release();
}

// Rml::Shutdown() is deliberately never called — DllMain's DLL_PROCESS_DETACH
// path explicitly avoids any cleanup while the process is dying (other game
// threads may still be executing through the hook), matching the existing
// documented policy for the rest of this DLL.
