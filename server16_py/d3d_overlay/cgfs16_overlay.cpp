/**
 * cgfs16_overlay.cpp  -  DXGI/D3D11 SwapChain::Present hook for FIFA 16
 *
 * FIFA 16 (FIFA Infinity mod) uses D3D11 + a dxgi.dll proxy.
 * We create a tiny D3D11 device+SwapChain to get the Present function address,
 * then install an inline (detour) hook on it.
 * The hook fires for every frame FIFA renders, regardless of which dxgi.dll proxy
 * is in use, because the proxy must call through to the real Present body.
 *
 * Overlay: D3D11 colored quads (VS/PS compiled at runtime).
 *   Text: GDI offscreen DIBSection -> D3D11 BGRA texture (no GetDC crash).
 *   Image: WIC -> D3D11 BGRA texture for stadium preview.
 */
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <objbase.h>     // CoInitializeEx, CoCreateInstance
#include <initguid.h>    // must precede wincodec.h to define GUIDs inline
#include <wincodec.h>    // WIC
#include <d3d11.h>
#include <dxgi.h>
#include <dxgi1_2.h>
#include <d3dcompiler.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <algorithm>
#include <vector>

#pragma comment(lib, "d3d11.lib")
#pragma comment(lib, "dxgi.lib")
#pragma comment(lib, "d3dcompiler.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "ole32.lib")

// ---------------------------------------------------------------------------
// Shared memory (same layout as Python _OverlayShared)
// ---------------------------------------------------------------------------
#define SHMEM_NAME  L"Local\\CGFS16_Overlay_v1"
#define MAX_STR     256
#define MAX_IMG     512

struct OverlayShared {
    volatile LONG visible;
    volatile LONG progress_x100;
    wchar_t stadium_name[MAX_STR];
    wchar_t detail_text[MAX_STR];
    wchar_t image_path[MAX_IMG];  // path to stadium preview image (PNG/JPG/BMP)
};

static HANDLE        g_hMap  = NULL;
static OverlayShared *g_data = NULL;

// ---------------------------------------------------------------------------
// Log -> %TEMP%\cgfs16_overlay.log
// ---------------------------------------------------------------------------
static char g_logPath[MAX_PATH] = {};
static CRITICAL_SECTION g_logCs;

static void InitLog() {
    InitializeCriticalSection(&g_logCs);
    char tmp[MAX_PATH] = {};
    GetTempPathA(MAX_PATH, tmp);
    snprintf(g_logPath, MAX_PATH, "%scgfs16_overlay.log", tmp);
    FILE *f = nullptr; fopen_s(&f, g_logPath, "w");
    if (f) { fprintf(f, "[DLL] log: %s\n", g_logPath); fclose(f); }
}
static void Log(const char *fmt, ...) {
    if (!g_logPath[0]) return;
    EnterCriticalSection(&g_logCs);
    FILE *f = nullptr; fopen_s(&f, g_logPath, "a");
    if (f) {
        va_list a; va_start(a, fmt);
        vfprintf(f, fmt, a); va_end(a);
        fputc('\n', f); fclose(f);
    }
    LeaveCriticalSection(&g_logCs);
}

// ---------------------------------------------------------------------------
// Hook state
// Strategy:
//   Phase 1 (inline): We patch the first 14 bytes of the proxy dxgi.dll's Present
//                     body so the VERY FIRST call reaches our hook.
//   Phase 2 (vtable): On that first call we restore the original bytes, save the
//                     real function pointer, and patch FIFA's actual IDXGISwapChain
//                     vtable slot 8. All subsequent calls go through the vtable
//                     hook with NO trampoline — we call the restored original fn.
// ---------------------------------------------------------------------------
typedef HRESULT (WINAPI *PFN_Present)(IDXGISwapChain*, UINT, UINT);

static uint8_t    *g_presentFnAddr       = nullptr;  // proxy Present body
static uint8_t     g_origPresentBytes[14]= {};        // saved original bytes
static uint8_t    *g_presentTrampoline   = nullptr;  // phase-1 trampoline (freed after switch)
static PFN_Present g_OrigPresent         = nullptr;  // = g_presentFnAddr after restore

static void      **g_fifaVtbl            = nullptr;  // FIFA's swapchain vtable
static bool        g_hookSwitched        = false;    // phase 1 -> phase 2 done

static CRITICAL_SECTION g_drawCs;
static LONG g_frameCount = 0;

// ---------------------------------------------------------------------------
// D3D11 overlay resources
// ---------------------------------------------------------------------------

// Combined shader: colored quads (VSMain/PSMain) + textured quads (VSTexMain/PSTexMain)
static const char kShaderSrc[] = R"(
// --- Colored quads ---
struct VS_IN  { float2 pos : POSITION; float4 col : COLOR; };
struct VS_OUT { float4 pos : SV_POSITION; float4 col : COLOR; };
VS_OUT VSMain(VS_IN v) {
    VS_OUT o; o.pos = float4(v.pos, 0, 1); o.col = v.col; return o;
}
float4 PSMain(VS_OUT v) : SV_TARGET { return v.col; }

// --- Textured quads ---
Texture2D g_tex : register(t0);
SamplerState g_samp : register(s0);
struct VS_IN_T  { float2 pos : POSITION; float2 uv : TEXCOORD; };
struct VS_OUT_T { float4 pos : SV_POSITION; float2 uv : TEXCOORD; };
VS_OUT_T VSTexMain(VS_IN_T v) {
    VS_OUT_T o; o.pos = float4(v.pos, 0, 1); o.uv = v.uv; return o;
}
float4 PSTexMain(VS_OUT_T v) : SV_TARGET { return g_tex.Sample(g_samp, v.uv); }
)";

// Colored quad resources
static ID3D11VertexShader    *g_vs  = nullptr;
static ID3D11PixelShader     *g_ps  = nullptr;
static ID3D11InputLayout     *g_il  = nullptr;
static ID3D11Buffer          *g_vb  = nullptr;
static ID3D11BlendState      *g_bs  = nullptr;
static ID3D11RasterizerState *g_rs  = nullptr;
static ID3D11DepthStencilState *g_dss = nullptr;

// Textured quad resources
static ID3D11VertexShader    *g_vsT  = nullptr;
static ID3D11PixelShader     *g_psT  = nullptr;
static ID3D11InputLayout     *g_ilT  = nullptr;
static ID3D11Buffer          *g_vbT  = nullptr;
static ID3D11SamplerState    *g_samp = nullptr;

// Colored quad vertex
struct Vtx11 { float x, y; float r, g, b, a; };

// Textured quad vertex
struct VtxT { float x, y, u, v; };

// ---------------------------------------------------------------------------
// Text textures (GDI -> D3D11)
// ---------------------------------------------------------------------------
struct TextTex {
    ID3D11Texture2D           *tex     = nullptr;
    ID3D11ShaderResourceView  *srv     = nullptr;
    int                        width   = 0;
    int                        height  = 0;
    wchar_t                    content[MAX_STR * 2] = {};
};

static TextTex g_ttTitle;    // "Loading Stadium" label
static TextTex g_ttName;     // stadium name
static TextTex g_ttDetail;   // detail / progress message

// ---------------------------------------------------------------------------
// Stadium preview image (WIC -> D3D11)
// ---------------------------------------------------------------------------
static ID3D11Texture2D          *g_previewTex          = nullptr;
static ID3D11ShaderResourceView *g_previewSRV          = nullptr;
static wchar_t                   g_previewLoadedPath[MAX_IMG] = {};
static int                       g_previewNatW          = 0;
static int                       g_previewNatH          = 0;

static bool InitD3D11Overlay(ID3D11Device *dev) {
    ID3DBlob *vsBlob = nullptr, *psBlob = nullptr, *err = nullptr;

    // ── Colored quads ──────────────────────────────────────────────────────
    HRESULT hr = D3DCompile(kShaderSrc, sizeof(kShaderSrc)-1,
        nullptr, nullptr, nullptr, "VSMain", "vs_4_0", 0, 0, &vsBlob, &err);
    if (FAILED(hr)) {
        Log("[D3D11] VS compile hr=0x%08X: %s", (unsigned)hr,
            err ? (char*)err->GetBufferPointer() : "?");
        if (err) err->Release(); return false;
    }
    hr = D3DCompile(kShaderSrc, sizeof(kShaderSrc)-1,
        nullptr, nullptr, nullptr, "PSMain", "ps_4_0", 0, 0, &psBlob, &err);
    if (FAILED(hr)) {
        Log("[D3D11] PS compile hr=0x%08X: %s", (unsigned)hr,
            err ? (char*)err->GetBufferPointer() : "?");
        vsBlob->Release(); if (err) err->Release(); return false;
    }

    dev->CreateVertexShader(vsBlob->GetBufferPointer(), vsBlob->GetBufferSize(), nullptr, &g_vs);
    dev->CreatePixelShader( psBlob->GetBufferPointer(), psBlob->GetBufferSize(), nullptr, &g_ps);

    D3D11_INPUT_ELEMENT_DESC ied[] = {
        {"POSITION",0,DXGI_FORMAT_R32G32_FLOAT,        0, 0,D3D11_INPUT_PER_VERTEX_DATA,0},
        {"COLOR",   0,DXGI_FORMAT_R32G32B32A32_FLOAT,  0, 8,D3D11_INPUT_PER_VERTEX_DATA,0},
    };
    dev->CreateInputLayout(ied, 2,
        vsBlob->GetBufferPointer(), vsBlob->GetBufferSize(), &g_il);
    vsBlob->Release(); psBlob->Release();

    D3D11_BUFFER_DESC bd = {};
    bd.ByteWidth      = sizeof(Vtx11) * 512;
    bd.Usage          = D3D11_USAGE_DYNAMIC;
    bd.BindFlags      = D3D11_BIND_VERTEX_BUFFER;
    bd.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
    dev->CreateBuffer(&bd, nullptr, &g_vb);

    D3D11_BLEND_DESC bsd = {};
    bsd.RenderTarget[0].BlendEnable            = TRUE;
    bsd.RenderTarget[0].SrcBlend              = D3D11_BLEND_SRC_ALPHA;
    bsd.RenderTarget[0].DestBlend             = D3D11_BLEND_INV_SRC_ALPHA;
    bsd.RenderTarget[0].BlendOp               = D3D11_BLEND_OP_ADD;
    bsd.RenderTarget[0].SrcBlendAlpha         = D3D11_BLEND_ONE;
    bsd.RenderTarget[0].DestBlendAlpha        = D3D11_BLEND_ZERO;
    bsd.RenderTarget[0].BlendOpAlpha          = D3D11_BLEND_OP_ADD;
    bsd.RenderTarget[0].RenderTargetWriteMask = D3D11_COLOR_WRITE_ENABLE_ALL;
    dev->CreateBlendState(&bsd, &g_bs);

    D3D11_RASTERIZER_DESC rsd = {};
    rsd.FillMode        = D3D11_FILL_SOLID;
    rsd.CullMode        = D3D11_CULL_NONE;
    rsd.DepthClipEnable = FALSE;
    dev->CreateRasterizerState(&rsd, &g_rs);

    D3D11_DEPTH_STENCIL_DESC dsd = {};
    dsd.DepthEnable = FALSE;
    dev->CreateDepthStencilState(&dsd, &g_dss);

    // ── Textured quads ─────────────────────────────────────────────────────
    ID3DBlob *vsTBlob = nullptr, *psTBlob = nullptr;
    hr = D3DCompile(kShaderSrc, sizeof(kShaderSrc)-1,
        nullptr, nullptr, nullptr, "VSTexMain", "vs_4_0", 0, 0, &vsTBlob, &err);
    if (FAILED(hr)) {
        Log("[D3D11] VSTexMain compile hr=0x%08X: %s", (unsigned)hr,
            err ? (char*)err->GetBufferPointer() : "?");
        if (err) err->Release();
        // Non-fatal: text/image just won't render
    } else {
        hr = D3DCompile(kShaderSrc, sizeof(kShaderSrc)-1,
            nullptr, nullptr, nullptr, "PSTexMain", "ps_4_0", 0, 0, &psTBlob, &err);
        if (SUCCEEDED(hr)) {
            dev->CreateVertexShader(vsTBlob->GetBufferPointer(), vsTBlob->GetBufferSize(), nullptr, &g_vsT);
            dev->CreatePixelShader( psTBlob->GetBufferPointer(), psTBlob->GetBufferSize(), nullptr, &g_psT);

            D3D11_INPUT_ELEMENT_DESC iedT[] = {
                {"POSITION",0,DXGI_FORMAT_R32G32_FLOAT, 0, 0,D3D11_INPUT_PER_VERTEX_DATA,0},
                {"TEXCOORD",0,DXGI_FORMAT_R32G32_FLOAT, 0, 8,D3D11_INPUT_PER_VERTEX_DATA,0},
            };
            dev->CreateInputLayout(iedT, 2,
                vsTBlob->GetBufferPointer(), vsTBlob->GetBufferSize(), &g_ilT);

            D3D11_BUFFER_DESC bdT = {};
            bdT.ByteWidth      = sizeof(VtxT) * 4;
            bdT.Usage          = D3D11_USAGE_DYNAMIC;
            bdT.BindFlags      = D3D11_BIND_VERTEX_BUFFER;
            bdT.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
            dev->CreateBuffer(&bdT, nullptr, &g_vbT);

            D3D11_SAMPLER_DESC sd = {};
            sd.Filter   = D3D11_FILTER_MIN_MAG_MIP_LINEAR;
            sd.AddressU = D3D11_TEXTURE_ADDRESS_CLAMP;
            sd.AddressV = D3D11_TEXTURE_ADDRESS_CLAMP;
            sd.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
            dev->CreateSamplerState(&sd, &g_samp);

            psTBlob->Release();
        } else {
            Log("[D3D11] PSTexMain compile hr=0x%08X", (unsigned)hr);
            if (err) err->Release();
        }
        vsTBlob->Release();
    }

    Log("[D3D11] overlay resources initialized (text=%s image=%s)",
        g_vsT ? "yes" : "no", g_vsT ? "yes" : "no");
    return g_vs && g_ps && g_il && g_vb && g_bs && g_rs && g_dss;
}

// pixel -> clip-space
static float PX(float x, float w) { return  x/w*2.f-1.f; }
static float PY(float y, float h) { return -y/h*2.f+1.f; }

static void PushQuad(Vtx11 *buf, int &n,
    float x,float y,float w,float h,float vpW,float vpH,DWORD col)
{
    float r=((col>>16)&0xFF)/255.f, g2=((col>>8)&0xFF)/255.f,
          b=((col)&0xFF)/255.f,     a=((col>>24)&0xFF)/255.f;
    float x0=PX(x,vpW),y0=PY(y,vpH),x1=PX(x+w,vpW),y1=PY(y+h,vpH);
    buf[n++]={x0,y0,r,g2,b,a}; buf[n++]={x1,y0,r,g2,b,a};
    buf[n++]={x0,y1,r,g2,b,a}; buf[n++]={x1,y1,r,g2,b,a};
}

// ---------------------------------------------------------------------------
// GDI text -> D3D11 texture
// fgColor is a COLORREF (0x00BBGGRR, use RGB(r,g,b) macro)
// maxPixW caps the texture width and enables ellipsis trimming
// ---------------------------------------------------------------------------
static void UpdateTextTex(ID3D11Device *dev, TextTex &tt,
    const wchar_t *text, int fontPx, bool bold, COLORREF fgColor, int maxPixW)
{
    if (tt.width > 0 && wcscmp(tt.content, text) == 0) return; // unchanged

    if (tt.tex) { tt.tex->Release(); tt.tex = nullptr; }
    if (tt.srv) { tt.srv->Release(); tt.srv = nullptr; }
    tt.width = tt.height = 0;
    tt.content[0] = L'\0';

    if (!text || !text[0]) return;

    LOGFONTW lf = {};
    lf.lfHeight  = -fontPx;
    lf.lfWeight  = bold ? FW_SEMIBOLD : FW_NORMAL;
    lf.lfQuality = ANTIALIASED_QUALITY;
    wcscpy_s(lf.lfFaceName, L"Segoe UI");
    HFONT hf = CreateFontIndirectW(&lf);
    if (!hf) return;

    // Measure text height
    HDC hdcMeas = CreateCompatibleDC(nullptr);
    SelectObject(hdcMeas, hf);
    RECT rcCalc = {0, 0, maxPixW, 2000};
    DrawTextW(hdcMeas, text, -1, &rcCalc,
              DT_LEFT | DT_SINGLELINE | DT_NOPREFIX | DT_CALCRECT);
    DeleteDC(hdcMeas);

    int bmpW = maxPixW;
    int bmpH = (rcCalc.bottom > 0) ? rcCalc.bottom : (fontPx + 4);

    // Create DIBSection (top-down, 32-bpp BGRA)
    BITMAPINFO bi = {};
    bi.bmiHeader.biSize        = sizeof(BITMAPINFOHEADER);
    bi.bmiHeader.biWidth       = bmpW;
    bi.bmiHeader.biHeight      = -bmpH;
    bi.bmiHeader.biPlanes      = 1;
    bi.bmiHeader.biBitCount    = 32;
    bi.bmiHeader.biCompression = BI_RGB;

    void *bits = nullptr;
    HDC hdc = CreateCompatibleDC(nullptr);
    HBITMAP hbm = CreateDIBSection(hdc, &bi, DIB_RGB_COLORS, &bits, nullptr, 0);
    if (!hbm) { DeleteDC(hdc); DeleteObject(hf); return; }
    HBITMAP hbmOld = (HBITMAP)SelectObject(hdc, hbm);

    memset(bits, 0, (size_t)bmpW * bmpH * 4);
    SelectObject(hdc, hf);
    SetBkMode(hdc, TRANSPARENT);
    SetTextColor(hdc, fgColor);
    RECT rc = {0, 0, bmpW, bmpH};
    DrawTextW(hdc, text, -1, &rc,
              DT_LEFT | DT_SINGLELINE | DT_NOPREFIX | DT_END_ELLIPSIS);
    GdiFlush();

    // GDI leaves alpha=0 in BGRA DIBs. Derive alpha from max(R,G,B).
    BYTE *px = (BYTE*)bits;
    for (int i = 0; i < bmpW * bmpH; i++) {
        BYTE b = px[0], g = px[1], r = px[2];
        px[3] = (std::max)({b, g, r});
        px += 4;
    }

    D3D11_TEXTURE2D_DESC td = {};
    td.Width            = (UINT)bmpW;
    td.Height           = (UINT)bmpH;
    td.MipLevels        = 1;
    td.ArraySize        = 1;
    td.Format           = DXGI_FORMAT_B8G8R8A8_UNORM;
    td.SampleDesc.Count = 1;
    td.Usage            = D3D11_USAGE_IMMUTABLE;
    td.BindFlags        = D3D11_BIND_SHADER_RESOURCE;

    D3D11_SUBRESOURCE_DATA srd = {};
    srd.pSysMem     = bits;
    srd.SysMemPitch = (UINT)(bmpW * 4);

    dev->CreateTexture2D(&td, &srd, &tt.tex);
    if (tt.tex) {
        dev->CreateShaderResourceView(tt.tex, nullptr, &tt.srv);
        tt.width  = bmpW;
        tt.height = bmpH;
    }
    wcscpy_s(tt.content, text);

    SelectObject(hdc, hbmOld);
    DeleteObject(hbm);
    DeleteObject(hf);
    DeleteDC(hdc);
}

// ---------------------------------------------------------------------------
// WIC -> D3D11 texture for stadium preview
// Returns true if the texture was (re)loaded successfully
// ---------------------------------------------------------------------------
static bool LoadPreviewImageWIC(ID3D11Device *dev, const wchar_t *path)
{
    if (g_previewTex) { g_previewTex->Release(); g_previewTex = nullptr; }
    if (g_previewSRV) { g_previewSRV->Release(); g_previewSRV = nullptr; }
    g_previewNatW = g_previewNatH = 0;

    IWICImagingFactory *wicF = nullptr;
    HRESULT hr = CoCreateInstance(CLSID_WICImagingFactory, nullptr,
        CLSCTX_INPROC_SERVER, __uuidof(IWICImagingFactory), (void**)&wicF);
    if (FAILED(hr)) { Log("[WIC] CoCreateInstance hr=0x%08X", (unsigned)hr); return false; }

    IWICBitmapDecoder *dec = nullptr;
    hr = wicF->CreateDecoderFromFilename(path, nullptr, GENERIC_READ,
        WICDecodeMetadataCacheOnDemand, &dec);
    if (FAILED(hr)) {
        Log("[WIC] CreateDecoderFromFilename hr=0x%08X", (unsigned)hr);
        wicF->Release(); return false;
    }

    IWICBitmapFrameDecode *frame = nullptr;
    dec->GetFrame(0, &frame);
    dec->Release();
    if (!frame) { wicF->Release(); return false; }

    IWICFormatConverter *conv = nullptr;
    wicF->CreateFormatConverter(&conv);
    hr = conv->Initialize(frame, GUID_WICPixelFormat32bppBGRA,
        WICBitmapDitherTypeNone, nullptr, 0.0, WICBitmapPaletteTypeCustom);
    frame->Release();
    if (FAILED(hr)) { if (conv) conv->Release(); wicF->Release(); return false; }

    UINT w = 0, h = 0;
    conv->GetSize(&w, &h);
    if (!w || !h) { conv->Release(); wicF->Release(); return false; }

    std::vector<BYTE> pixels((size_t)w * h * 4);
    conv->CopyPixels(nullptr, w * 4, (UINT)pixels.size(), pixels.data());
    conv->Release();
    wicF->Release();

    D3D11_TEXTURE2D_DESC td = {};
    td.Width            = w;
    td.Height           = h;
    td.MipLevels        = 1;
    td.ArraySize        = 1;
    td.Format           = DXGI_FORMAT_B8G8R8A8_UNORM;
    td.SampleDesc.Count = 1;
    td.Usage            = D3D11_USAGE_IMMUTABLE;
    td.BindFlags        = D3D11_BIND_SHADER_RESOURCE;

    D3D11_SUBRESOURCE_DATA srd = {};
    srd.pSysMem     = pixels.data();
    srd.SysMemPitch = w * 4;

    hr = dev->CreateTexture2D(&td, &srd, &g_previewTex);
    if (FAILED(hr)) { Log("[WIC] CreateTexture2D hr=0x%08X", (unsigned)hr); return false; }
    dev->CreateShaderResourceView(g_previewTex, nullptr, &g_previewSRV);
    g_previewNatW = (int)w;
    g_previewNatH = (int)h;
    Log("[WIC] loaded '%ls' %dx%d", path, w, h);
    return true;
}

// Draw a textured quad; requires g_vsT/g_psT/g_ilT/g_vbT/g_samp already bound.
static void DrawTexQuad(ID3D11DeviceContext *ctx,
    float x, float y, float w, float h, float vpW, float vpH,
    ID3D11ShaderResourceView *srv)
{
    if (!srv || !g_vbT) return;
    float x0=PX(x,vpW),y0=PY(y,vpH),x1=PX(x+w,vpW),y1=PY(y+h,vpH);
    VtxT verts[4] = {{x0,y0,0,0},{x1,y0,1,0},{x0,y1,0,1},{x1,y1,1,1}};
    D3D11_MAPPED_SUBRESOURCE ms={};
    if (SUCCEEDED(ctx->Map(g_vbT,0,D3D11_MAP_WRITE_DISCARD,0,&ms))) {
        memcpy(ms.pData,verts,sizeof(verts)); ctx->Unmap(g_vbT,0);
    }
    ctx->PSSetShaderResources(0,1,&srv);
    UINT stride=sizeof(VtxT),offset=0;
    ctx->IASetVertexBuffers(0,1,&g_vbT,&stride,&offset);
    ctx->Draw(4,0);
}

static void DrawOverlay11(IDXGISwapChain *sc, ID3D11Device *dev, ID3D11DeviceContext *ctx) {
    // ── Read shared memory ─────────────────────────────────────────────────
    wchar_t stadium[MAX_STR]={}, detail[MAX_STR]={}, imgPath[MAX_IMG]={};
    float pct=0.f;
    if (g_data) {
        wcsncpy_s(stadium, g_data->stadium_name, MAX_STR-1);
        wcsncpy_s(detail,  g_data->detail_text,  MAX_STR-1);
        wcsncpy_s(imgPath, g_data->image_path,   MAX_IMG-1);
        pct = (float)InterlockedCompareExchange(&g_data->progress_x100,0,0)/100.f;
    }

    DXGI_SWAP_CHAIN_DESC scd={}; sc->GetDesc(&scd);
    float vpW=(float)(scd.BufferDesc.Width?scd.BufferDesc.Width:1280);
    float vpH=(float)(scd.BufferDesc.Height?scd.BufferDesc.Height:720);

    ID3D11Texture2D *bb=nullptr;
    if (FAILED(sc->GetBuffer(0,__uuidof(ID3D11Texture2D),(void**)&bb))) return;
    ID3D11RenderTargetView *rtv=nullptr;
    dev->CreateRenderTargetView(bb,nullptr,&rtv);
    bb->Release();
    if (!rtv) return;

    // ── Init D3D resources once ────────────────────────────────────────────
    static bool s_init=false;
    if (!s_init) s_init=InitD3D11Overlay(dev);
    if (!g_vs||!g_ps||!g_il||!g_vb) { rtv->Release(); return; }

    // ── Init COM once (for WIC) on this thread ─────────────────────────────
    static bool s_comInit = false;
    if (!s_comInit) {
        s_comInit = true;
        HRESULT cohr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
        Log("[DrawOverlay] CoInitializeEx hr=0x%08X", (unsigned)cohr);
        // S_OK = initialized, S_FALSE = already init MTA, RPC_E_CHANGED_MODE = STA
        // All outcomes leave COM usable on this thread.
    }

    // ── Update text textures (GDI) ─────────────────────────────────────────
    // Panel constants: PW=460, M=20.  Text column starts at px+136 (after image area).
    // maxPixW for text = PW - 136 - 12 = 312 px
    const int kTextMaxW = 312;
    UpdateTextTex(dev, g_ttTitle,  L"Loading Stadium", 17, false, RGB(0x33,0x99,0xFF), kTextMaxW);
    UpdateTextTex(dev, g_ttName,   stadium,             16, true,  RGB(0xFF,0xFF,0xFF), kTextMaxW);
    UpdateTextTex(dev, g_ttDetail, detail,              13, false, RGB(0x99,0xBB,0xDD), kTextMaxW);

    // ── Update preview image (WIC) ─────────────────────────────────────────
    if (wcscmp(imgPath, g_previewLoadedPath) != 0) {
        wcscpy_s(g_previewLoadedPath, imgPath);
        if (imgPath[0] != L'\0') {
            LoadPreviewImageWIC(dev, imgPath);
        } else {
            if (g_previewTex) { g_previewTex->Release(); g_previewTex = nullptr; }
            if (g_previewSRV) { g_previewSRV->Release(); g_previewSRV = nullptr; }
            g_previewNatW = g_previewNatH = 0;
        }
    }

    // ── Save D3D state ─────────────────────────────────────────────────────
    ID3D11RenderTargetView *oldRTV[8]={}; ID3D11DepthStencilView *oldDSV=nullptr;
    ctx->OMGetRenderTargets(8,oldRTV,&oldDSV);
    D3D11_VIEWPORT oldVP={}; UINT nVP=1; ctx->RSGetViewports(&nVP,&oldVP);
    ID3D11BlendState *oldBS=nullptr; float oldBF[4]={}; UINT oldSM=0;
    ctx->OMGetBlendState(&oldBS,oldBF,&oldSM);
    ID3D11RasterizerState *oldRS=nullptr; ctx->RSGetState(&oldRS);
    ID3D11DepthStencilState *oldDSS=nullptr; UINT oldSRef=0;
    ctx->OMGetDepthStencilState(&oldDSS,&oldSRef);
    ID3D11VertexShader *oldVS=nullptr; ctx->VSGetShader(&oldVS,nullptr,nullptr);
    ID3D11PixelShader  *oldPS=nullptr; ctx->PSGetShader(&oldPS,nullptr,nullptr);
    ID3D11InputLayout  *oldIL=nullptr; ctx->IAGetInputLayout(&oldIL);
    D3D11_PRIMITIVE_TOPOLOGY oldTopo; ctx->IAGetPrimitiveTopology(&oldTopo);
    ID3D11ShaderResourceView *oldSRV=nullptr; ctx->PSGetShaderResources(0,1,&oldSRV);
    ID3D11SamplerState *oldSamp=nullptr; ctx->PSGetSamplers(0,1,&oldSamp);

    // ── Set overlay state (shared by both colored and textured draws) ───────
    ctx->OMSetRenderTargets(1,&rtv,nullptr);
    D3D11_VIEWPORT vp={0,0,vpW,vpH,0,1}; ctx->RSSetViewports(1,&vp);
    ctx->OMSetBlendState(g_bs,nullptr,0xFFFFFFFF);
    ctx->RSSetState(g_rs);
    ctx->OMSetDepthStencilState(g_dss,0);
    ctx->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLESTRIP);

    // ── Layout constants ────────────────────────────────────────────────────
    // Panel: 460 x 140, top-right margin 20 px
    const float PW=460.f, PH=140.f, M=20.f;
    const float px=vpW-PW-M, py=M;
    // Image box: 110 x 88 at (px+12, py+16)
    const float IX=px+12.f, IY=py+16.f, IW=110.f, IH=88.f;
    // Text column start
    const float TX=px+136.f;

    // ── Colored quads pass ─────────────────────────────────────────────────
    ctx->VSSetShader(g_vs,nullptr,0);
    ctx->PSSetShader(g_ps,nullptr,0);
    ctx->IASetInputLayout(g_il);
    UINT stride=sizeof(Vtx11),offset=0;
    ctx->IASetVertexBuffers(0,1,&g_vb,&stride,&offset);

    Vtx11 verts[128]; int n=0;
    auto R=[&](float x,float y,float w,float h,DWORD col){
        PushQuad(verts,n,x,y,w,h,vpW,vpH,col);
    };
    // Panel background + borders
    R(px,   py,      PW,  3.f,   0xFF3399FF);  // top accent bar
    R(px,   py+3.f,  PW,  PH-3.f,0xEE101828); // background
    R(px,   py+PH-1.f,PW, 1.f,   0xFF3399FF);  // bottom border
    R(px,   py,      1.f, PH,    0xFF3399FF);  // left border
    R(px+PW-1.f,py,  1.f, PH,    0xFF3399FF);  // right border
    // Image placeholder area (dark inset, shown when no image or while loading)
    R(IX,   IY,      IW,  IH,    0xFF0C1420);  // dark background for image
    // Progress track + fill
    float tx2=TX, ty2=py+PH-22.f, tw2=PW-136.f-12.f, th2=10.f;
    R(tx2,ty2,tw2,th2,0xFF222C3C);
    float f=(std::max)(0.f,(std::min)(1.f,pct/100.f));
    if (f>0.f) R(tx2,ty2,tw2*f,th2,0xFF3399FF);

    D3D11_MAPPED_SUBRESOURCE ms={};
    if (SUCCEEDED(ctx->Map(g_vb,0,D3D11_MAP_WRITE_DISCARD,0,&ms))){
        memcpy(ms.pData,verts,n*sizeof(Vtx11)); ctx->Unmap(g_vb,0);
    }
    for(int i=0;i<n;i+=4) ctx->Draw(4,i);

    // ── Textured quads pass (text + image) ─────────────────────────────────
    if (g_vsT && g_psT && g_ilT && g_vbT && g_samp) {
        ctx->VSSetShader(g_vsT,nullptr,0);
        ctx->PSSetShader(g_psT,nullptr,0);
        ctx->IASetInputLayout(g_ilT);
        ctx->PSSetSamplers(0,1,&g_samp);

        // Stadium preview image (aspect-corrected within IW x IH)
        if (g_previewSRV && g_previewNatW > 0 && g_previewNatH > 0) {
            float imgR = (float)g_previewNatW / (float)g_previewNatH;
            float boxR = IW / IH;
            float dw, dh;
            if (imgR >= boxR) { dw=IW; dh=IW/imgR; }
            else              { dh=IH; dw=IH*imgR;  }
            DrawTexQuad(ctx, IX+(IW-dw)/2.f, IY+(IH-dh)/2.f, dw, dh, vpW, vpH, g_previewSRV);
        }

        // Title "Loading Stadium"
        if (g_ttTitle.srv)
            DrawTexQuad(ctx, TX, py+14.f, (float)g_ttTitle.width, (float)g_ttTitle.height, vpW, vpH, g_ttTitle.srv);
        // Stadium name
        if (g_ttName.srv && stadium[0])
            DrawTexQuad(ctx, TX, py+36.f, (float)g_ttName.width, (float)g_ttName.height, vpW, vpH, g_ttName.srv);
        // Detail text
        if (g_ttDetail.srv && detail[0])
            DrawTexQuad(ctx, TX, py+58.f, (float)g_ttDetail.width, (float)g_ttDetail.height, vpW, vpH, g_ttDetail.srv);
    }

    // ── Restore D3D state ──────────────────────────────────────────────────
    ctx->OMSetRenderTargets(8,oldRTV,oldDSV);
    ctx->RSSetViewports(1,&oldVP);
    ctx->OMSetBlendState(oldBS,oldBF,oldSM);
    ctx->RSSetState(oldRS);
    ctx->OMSetDepthStencilState(oldDSS,oldSRef);
    ctx->VSSetShader(oldVS,nullptr,0);
    ctx->PSSetShader(oldPS,nullptr,0);
    ctx->IASetInputLayout(oldIL);
    ctx->IASetPrimitiveTopology(oldTopo);
    ctx->PSSetShaderResources(0,1,&oldSRV);
    ctx->PSSetSamplers(0,1,&oldSamp);
    for(auto *r:oldRTV) if(r) r->Release();
    if(oldDSV)  oldDSV->Release();
    if(oldBS)   oldBS->Release();
    if(oldRS)   oldRS->Release();
    if(oldDSS)  oldDSS->Release();
    if(oldVS)   oldVS->Release();
    if(oldPS)   oldPS->Release();
    if(oldIL)   oldIL->Release();
    if(oldSRV)  oldSRV->Release();
    if(oldSamp) oldSamp->Release();
    rtv->Release();
}

// ---------------------------------------------------------------------------
// Hooked IDXGISwapChain::Present
// ---------------------------------------------------------------------------
static HRESULT WINAPI HookedPresent(IDXGISwapChain *sc, UINT syncInterval, UINT flags) {
    // Phase 1 -> Phase 2 switch: on the very first call we:
    //   a) restore the inline hook bytes (so g_presentFnAddr is the clean original again),
    //   b) patch FIFA's real swapchain vtable[8] -> HookedPresent (vtable hook),
    //   c) record g_OrigPresent = original function pointer (no trampoline needed).
    if (!g_hookSwitched) {
        g_hookSwitched = true;

        // Restore inline hook (original bytes back in place)
        DWORD old = 0;
        if (VirtualProtect(g_presentFnAddr, 14, PAGE_EXECUTE_READWRITE, &old)) {
            memcpy(g_presentFnAddr, g_origPresentBytes, 14);
            VirtualProtect(g_presentFnAddr, 14, old, &old);
            FlushInstructionCache(GetCurrentProcess(), g_presentFnAddr, 14);
        }
        if (g_presentTrampoline) {
            VirtualFree(g_presentTrampoline, 0, MEM_RELEASE);
            g_presentTrampoline = nullptr;
        }
        // Original function pointer = the (now restored) proxy Present body
        g_OrigPresent = reinterpret_cast<PFN_Present>(g_presentFnAddr);

        // Patch FIFA's actual swapchain vtable
        g_fifaVtbl = *reinterpret_cast<void***>(sc);
        if (VirtualProtect(&g_fifaVtbl[8], sizeof(void*), PAGE_EXECUTE_READWRITE, &old)) {
            g_fifaVtbl[8] = reinterpret_cast<void*>(HookedPresent);
            VirtualProtect(&g_fifaVtbl[8], sizeof(void*), old, &old);
        }
        Log("[Present] switched to vtable hook sc=%p vtbl=%p origFn=%p",
            sc, g_fifaVtbl, g_OrigPresent);
    }

    LONG n = InterlockedIncrement(&g_frameCount);
    if (n==1 || (n%600)==0)
        Log("[Present] frame=%ld visible=%d", n, g_data?(int)g_data->visible:-1);

    if (g_data && InterlockedCompareExchange(&g_data->visible,0,0) != 0) {
        ID3D11Device *dev=nullptr;
        if (SUCCEEDED(sc->GetDevice(__uuidof(ID3D11Device),(void**)&dev))) {
            ID3D11DeviceContext *ctx=nullptr;
            dev->GetImmediateContext(&ctx);
            EnterCriticalSection(&g_drawCs);
            __try { DrawOverlay11(sc,dev,ctx); }
            __except(EXCEPTION_EXECUTE_HANDLER){ Log("[Present] EXCEPTION DrawOverlay11"); }
            LeaveCriticalSection(&g_drawCs);
            ctx->Release(); dev->Release();
        }
    }
    // Call the RESTORED original proxy Present (no trampoline, no RIP-relative issues)
    return g_OrigPresent(sc, syncInterval, flags);
}

// ---------------------------------------------------------------------------
// Inline hook helpers (x64: FF 25 00000000 [8-byte addr] = 14 bytes)
// ---------------------------------------------------------------------------
static uint8_t *InstallInlineHook(uint8_t *fn, void *hook, uint8_t *saved) {
    DWORD old=0;
    if (!VirtualProtect(fn,14,PAGE_EXECUTE_READWRITE,&old)) {
        Log("[Hook] VirtualProtect failed %lu fn=%p", GetLastError(),fn); return nullptr;
    }
    memcpy(saved,fn,14);
    fn[0]=0xFF; fn[1]=0x25;
    *reinterpret_cast<DWORD*>(fn+2)=0;
    *reinterpret_cast<void**>(fn+6)=hook;
    VirtualProtect(fn,14,old,&old);
    FlushInstructionCache(GetCurrentProcess(),fn,14);

    uint8_t *t=(uint8_t*)VirtualAlloc(nullptr,64,MEM_COMMIT|MEM_RESERVE,PAGE_EXECUTE_READWRITE);
    if (!t){ Log("[Hook] VirtualAlloc failed %lu",GetLastError()); return nullptr; }
    memcpy(t,saved,14);
    t[14]=0xFF; t[15]=0x25;
    *reinterpret_cast<DWORD*>(t+16)=0;
    *reinterpret_cast<void**>(t+20)=fn+14;
    return t;
}

static void RemoveInlineHook(uint8_t *fn, uint8_t *tramp, const uint8_t *saved) {
    if (!fn||!tramp) return;
    DWORD old=0;
    VirtualProtect(fn,14,PAGE_EXECUTE_READWRITE,&old);
    memcpy(fn,saved,14);
    VirtualProtect(fn,14,old,&old);
    FlushInstructionCache(GetCurrentProcess(),fn,14);
    VirtualFree(tramp,0,MEM_RELEASE);
}

// ---------------------------------------------------------------------------
// Hook setup: temp D3D11 device+swapchain -> get Present addr -> inline hook
// ---------------------------------------------------------------------------
static DWORD WINAPI HookThread(LPVOID) {
    Log("[HookThread] started pid=%lu", GetCurrentProcessId());
    Sleep(500);

    WNDCLASSEXW wc={}; wc.cbSize=sizeof(wc);
    wc.lpfnWndProc=DefWindowProcW;
    wc.hInstance=GetModuleHandleW(nullptr);
    wc.lpszClassName=L"_CGFS16DXGI";
    RegisterClassExW(&wc);
    HWND hw=CreateWindowExW(0,L"_CGFS16DXGI",L"",WS_POPUP,0,0,1,1,
        nullptr,nullptr,wc.hInstance,nullptr);

    ID3D11Device *tmpDev=nullptr; IDXGISwapChain *tmpSC=nullptr;
    D3D_FEATURE_LEVEL fl=D3D_FEATURE_LEVEL_11_0;
    DXGI_SWAP_CHAIN_DESC scd={};
    scd.BufferCount=1; scd.BufferDesc.Format=DXGI_FORMAT_R8G8B8A8_UNORM;
    scd.BufferUsage=DXGI_USAGE_RENDER_TARGET_OUTPUT;
    scd.OutputWindow=hw; scd.SampleDesc.Count=1; scd.Windowed=TRUE;

    HRESULT hr=D3D11CreateDeviceAndSwapChain(nullptr,D3D_DRIVER_TYPE_HARDWARE,
        nullptr,0,nullptr,0,D3D11_SDK_VERSION,&scd,&tmpSC,&tmpDev,&fl,nullptr);
    Log("[HookThread] D3D11CreateDeviceAndSwapChain(HW) hr=0x%08X sc=%p",(unsigned)hr,tmpSC);

    if (FAILED(hr)||!tmpSC) {
        hr=D3D11CreateDeviceAndSwapChain(nullptr,D3D_DRIVER_TYPE_WARP,
            nullptr,0,nullptr,0,D3D11_SDK_VERSION,&scd,&tmpSC,&tmpDev,&fl,nullptr);
        Log("[HookThread] WARP fallback hr=0x%08X sc=%p",(unsigned)hr,tmpSC);
    }

    if (FAILED(hr)||!tmpSC) {
        Log("[HookThread] cannot create D3D11 SwapChain, aborting");
        DestroyWindow(hw); UnregisterClassW(wc.lpszClassName,wc.hInstance);
        return 0;
    }

    void **vt=*reinterpret_cast<void***>(tmpSC);
    g_presentFnAddr=reinterpret_cast<uint8_t*>(vt[8]); // IDXGISwapChain::Present = slot 8

    MEMORY_BASIC_INFORMATION mbi={};
    VirtualQuery(g_presentFnAddr,&mbi,sizeof(mbi));
    char modPath[MAX_PATH]="(unknown)";
    GetModuleFileNameA((HMODULE)mbi.AllocationBase,modPath,MAX_PATH);
    Log("[HookThread] SwapChain::Present at %p in %s", g_presentFnAddr, modPath);

    tmpSC->Release(); if (tmpDev) tmpDev->Release();
    DestroyWindow(hw); UnregisterClassW(wc.lpszClassName,wc.hInstance);

    g_presentTrampoline=InstallInlineHook(g_presentFnAddr,(void*)HookedPresent,g_origPresentBytes);
    if (g_presentTrampoline) {
        g_OrigPresent=reinterpret_cast<PFN_Present>(g_presentTrampoline);
        Log("[HookThread] Present inline hook installed ok (tramp=%p)",g_presentTrampoline);
    } else {
        Log("[HookThread] Present inline hook FAILED");
    }

    Log("[HookThread] done");
    return 0;
}

// ---------------------------------------------------------------------------
// DllMain
// ---------------------------------------------------------------------------
BOOL WINAPI DllMain(HINSTANCE hInst, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hInst);
        InitializeCriticalSection(&g_drawCs);
        InitLog();
        Log("[DllMain] ATTACH pid=%lu", GetCurrentProcessId());

        g_hMap=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,
            PAGE_READWRITE,0,sizeof(OverlayShared),SHMEM_NAME);
        if (g_hMap)
            g_data=reinterpret_cast<OverlayShared*>(
                MapViewOfFile(g_hMap,FILE_MAP_ALL_ACCESS,0,0,sizeof(OverlayShared)));
        Log("[DllMain] shmem hMap=%p data=%p visible=%d",
            g_hMap,g_data,g_data?(int)g_data->visible:-1);

        HANDLE ht=CreateThread(nullptr,0,HookThread,nullptr,0,nullptr);
        if (ht) CloseHandle(ht);

    } else if (reason==DLL_PROCESS_DETACH) {
        Log("[DllMain] DETACH");
        if (g_hookSwitched) {
            // Restore vtable hook
            if (g_fifaVtbl) {
                DWORD old = 0;
                if (VirtualProtect(&g_fifaVtbl[8], sizeof(void*), PAGE_EXECUTE_READWRITE, &old)) {
                    g_fifaVtbl[8] = reinterpret_cast<void*>(g_OrigPresent);
                    VirtualProtect(&g_fifaVtbl[8], sizeof(void*), old, &old);
                }
            }
        } else {
            // Still in phase 1 — restore inline hook
            RemoveInlineHook(g_presentFnAddr, g_presentTrampoline, g_origPresentBytes);
        }
        // Do NOT release D3D11 resources — FIFA is shutting down, releasing COM
        // objects owned by its device here can cause secondary crashes.
        EnterCriticalSection(&g_drawCs);
        if (g_data){ UnmapViewOfFile(g_data); g_data=nullptr; }
        if (g_hMap){ CloseHandle(g_hMap);     g_hMap=nullptr; }
        LeaveCriticalSection(&g_drawCs);
        DeleteCriticalSection(&g_drawCs);
        DeleteCriticalSection(&g_logCs);
    }
    return TRUE;
}
