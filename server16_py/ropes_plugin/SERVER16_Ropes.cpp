// SERVER16_Ropes.cpp - FIFA Plugin Loader plugin (plugins\SERVER16_Ropes.asi) that hides parts of the
// goal-net ropes (the ropes that hold the net up), per stadium.
//
// Why a plugin and not cgfs16_overlay.dll: the rope draw is recognised by hashes of the objects
// FIFA creates (index buffer, shaders). Those are only visible at creation time, and the overlay is
// injected after FIFA has created them. The Plugin Loader (winmm.dll, a static import of
// fifa16.exe) loads this file before FIFA creates its D3D11 device.
//
// How it works
//   1. DllMain patches fifa16.exe's import slot for d3d11!D3D11CreateDevice (FIFA's only d3d11 import).
//   2. When FIFA creates its device, the ID3D11Device / ID3D11DeviceContext vtables are patched:
//      CreateBuffer / CreateVertexShader / CreatePixelShader / CreateDeferredContext and
//      DrawIndexed / DrawIndexedInstanced. Each hook calls the previous slot value, so other
//      plugins that hook the same slots (SelfShadow, GrassDistance...) keep working.
//   3. Index buffers whose 3Dmigoto hash matches the rope buffer, and every shader (FNV-1 64 of its
//      bytecode, 3Dmigoto's shader hash), are tagged with SetPrivateData at creation.
//   4. A 120-index draw whose bound index buffer is tagged (or whose vertex shader matches the rope
//      shader hash) is a rope draw. It is re-issued as the sub-ranges the level keeps:
//        indices  0..47 outer ropes,  48..95 centre ropes,  96..119 top rope
//      (ranges and hashes from the rope sections of a forum 3Dmigoto d3dx.ini).
//
// Level: 0 all ropes, 1 hide centre, 2 hide centre + top, 3 hide all.
//   Source: shared memory Local\CGFS16_Ropes_v1 (written by CG File Server 16 per stadium) when its
//   level is 0..3, otherwise Level= in plugins\SERVER16_Ropes.ini (re-read every second).
//
// The shared-memory struct below MUST match its Python mirror by hand (no other versioning than
// kVersion). Build: see build.bat in this folder, or build_exe.bat at the repo root.

#define WIN32_LEAN_AND_MEAN
#define _CRT_SECURE_NO_WARNINGS
#define NOMINMAX
#include <windows.h>
#include <d3d11.h>

#include <atomic>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cwchar>
#include <mutex>
#include <string>

#include "thirdparty/minhook/include/MinHook.h"

namespace {

// ---------------------------------------------------------------------------------------------
// Shared memory (Server <-> plugin). Keep in sync with the Python mirror.
// ---------------------------------------------------------------------------------------------
constexpr wchar_t kSharedName[] = L"Local\\CGFS16_Ropes_v1";
constexpr uint32_t kMagic = 0x50524743;  // 'CGRP'
constexpr uint32_t kVersion = 1;

enum PluginFlags : LONG {
    kFlagIatHooked = 1 << 0,     // D3D11CreateDevice import slot patched
    kFlagDeviceHooked = 1 << 1,  // device + context vtables patched
    kFlagRopeBuffer = 1 << 2,    // a rope index buffer was tagged at creation
    kFlagRopeDraw = 1 << 3,      // a rope draw was seen
};

#pragma pack(push, 4)
struct RopesShared {
    uint32_t magic;                // kMagic once initialised
    uint32_t version;              // kVersion
    volatile LONG level;           // -1: not set by the Server (the ini Level applies); 0..3
    volatile LONG plugin_flags;    // PluginFlags, written by the plugin
    volatile LONG rope_draws;      // rope draws seen (wraps)
    volatile LONG rope_draws_cut;  // rope draws re-issued partially or skipped (wraps)
    volatile LONG effective_level; // level the plugin is applying right now
    uint32_t reserved[9];
};
#pragma pack(pop)
static_assert(sizeof(RopesShared) == 64, "RopesShared layout is part of the Server contract");

// ---------------------------------------------------------------------------------------------
// Rope draw geometry (from the d3dx.ini of the forum author's filter)
// ---------------------------------------------------------------------------------------------
constexpr UINT kRopeIndexCount = 120;
constexpr UINT kOuterStart = 0, kOuterCount = 48;
constexpr UINT kInnerStart = 48, kInnerCount = 48;
constexpr UINT kTopStart = 96, kTopCount = 24;

constexpr uint32_t kDefaultIndexBufferHash = 0xcd59201f;          // d3dx.ini rope [TextureOverride...] (index buffer)
constexpr uint64_t kDefaultVertexShaderHash = 0x323fadce500155adULL;  // d3dx.ini rope [ShaderOverride...] (vertex shader)
constexpr uint64_t kDefaultPixelShaderHash = 0x31dd874b1278e9c6ULL;   // d3dx.ini rope [ShaderOverride...] (pixel shader, log only)

// Private-data tags. {6A1C9F52-3B7E-4C1D-9E2A-5F0B7C3D8E41/42}
constexpr GUID kRopeTagGuid = {0x6a1c9f52, 0x3b7e, 0x4c1d, {0x9e, 0x2a, 0x5f, 0x0b, 0x7c, 0x3d, 0x8e, 0x41}};
constexpr GUID kShaderHashGuid = {0x6a1c9f52, 0x3b7e, 0x4c1d, {0x9e, 0x2a, 0x5f, 0x0b, 0x7c, 0x3d, 0x8e, 0x42}};

enum RopeTag : uint32_t {
    kTagNone = 0,
    kTagHashData = 1,  // crc32c(initial data) == IndexBufferHash
    kTagHashFull = 2,  // crc32c(desc, seed = crc32c(initial data)) == IndexBufferHash
    kTagSize = 3,      // SizeFallback=1: 240-byte index buffer
};

// vtable slots (COM ABI order of d3d11.h)
constexpr int kDevCreateBuffer = 3;
constexpr int kDevCreateVertexShader = 12;
constexpr int kDevCreatePixelShader = 15;
constexpr int kDevCreateDeferredContext = 27;
constexpr int kCtxDrawIndexed = 12;
constexpr int kCtxDrawIndexedInstanced = 20;
constexpr int kMaxSlot = 32;

// ---------------------------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------------------------
HMODULE g_module = nullptr;
std::wstring g_ini_path;
std::wstring g_log_path;

std::atomic<int> g_ini_level{0};
bool g_log_enabled = true;
bool g_size_fallback = false;
uint32_t g_ib_hash = kDefaultIndexBufferHash;
uint64_t g_vs_hash = kDefaultVertexShaderHash;
uint64_t g_ps_hash = kDefaultPixelShaderHash;

RopesShared* g_shared = nullptr;
LONG g_local_flags = 0;  // mirror when the shared memory is unavailable
std::atomic<long> g_rope_draws{0};
std::atomic<long> g_rope_draws_cut{0};
std::atomic<long> g_shaders_hashed{0};
std::atomic<long> g_rope_buffers{0};
std::atomic<long> g_indexed_draws{0};  // every DrawIndexed/DrawIndexedInstanced through the hooks (Log=1 only)
std::atomic<long> g_draws_120{0};      // of those, the 120-index ones
ID3D11DeviceContext* g_immediate = nullptr;  // not AddRef'd, only compared in the log

using PFN_CreateDevice = HRESULT(WINAPI*)(IDXGIAdapter*, D3D_DRIVER_TYPE, HMODULE, UINT, const D3D_FEATURE_LEVEL*,
                                          UINT, UINT, ID3D11Device**, D3D_FEATURE_LEVEL*, ID3D11DeviceContext**);
PFN_CreateDevice g_orig_create_device = nullptr;

// ---------------------------------------------------------------------------------------------
// Log (plugins\SERVER16_Ropes.log, truncated at every FIFA start, capped)
// ---------------------------------------------------------------------------------------------
constexpr int kMaxLogLines = 4000;
std::mutex g_log_mutex;
FILE* g_log = nullptr;
int g_log_lines = 0;
ULONGLONG g_start_tick = 0;

void Log(const char* fmt, ...) {
    if (!g_log_enabled) return;
    std::lock_guard<std::mutex> lock(g_log_mutex);
    if (!g_log || g_log_lines >= kMaxLogLines) return;
    ++g_log_lines;
    const ULONGLONG ms = GetTickCount64() - g_start_tick;
    std::fprintf(g_log, "[%7llu.%03llu] ", ms / 1000, ms % 1000);
    va_list args;
    va_start(args, fmt);
    std::vfprintf(g_log, fmt, args);
    va_end(args);
    if (g_log_lines == kMaxLogLines) std::fputs(" (log line limit reached)", g_log);
    std::fputc('\n', g_log);
    std::fflush(g_log);
}

// ---------------------------------------------------------------------------------------------
// Hashes (3Dmigoto compatible)
// ---------------------------------------------------------------------------------------------
uint32_t g_crc_table[256];

void InitCrc32c() {
    for (uint32_t i = 0; i < 256; ++i) {
        uint32_t c = i;
        for (int k = 0; k < 8; ++k) c = (c & 1) ? (c >> 1) ^ 0x82F63B78u : (c >> 1);
        g_crc_table[i] = c;
    }
}

// Same contract as Mark Adler's crc32c_append (used by 3Dmigoto's crc32c_hw): pre/post inverted.
uint32_t Crc32cAppend(uint32_t crc, const void* buffer, size_t length) {
    const auto* p = static_cast<const uint8_t*>(buffer);
    crc = ~crc;
    while (length--) crc = g_crc_table[(crc ^ *p++) & 0xff] ^ (crc >> 8);
    return ~crc;
}

// 3Dmigoto's fnv_64_buf: FNV-1 (multiply, then xor), initial value 0.
uint64_t Fnv64(const void* buffer, size_t length) {
    const auto* p = static_cast<const uint8_t*>(buffer);
    uint64_t h = 0;
    for (size_t i = 0; i < length; ++i) {
        h *= 0x100000001b3ULL;
        h ^= p[i];
    }
    return h;
}

// ---------------------------------------------------------------------------------------------
// vtable patching. Originals are kept per vtable. On the FIP install (live log 2026-11-23) the
// device vtable lives in d3d11.dll and is shared, but EVERY context (immediate and deferred, 20+
// per session) has its own heap vtable, so this is an open-addressing table keyed by the vtable
// pointer: one hash + ~1 probe per draw call. Keys are only added (a freed vtable address that is
// reused is re-patched and its originals overwritten); readers never lock.
// ---------------------------------------------------------------------------------------------
struct VtEntry {
    std::atomic<void**> vtable;
    void* original[kMaxSlot];
};
constexpr size_t kVtCapacity = 1024;  // power of two
VtEntry g_vtables[kVtCapacity];
size_t g_vtables_used = 0;        // under g_patch_mutex
void* g_last_original[kMaxSlot];  // fallback when an object's vtable is not one we patched
std::mutex g_patch_mutex;

size_t VtHash(void** vt) {
    const uint64_t v = (static_cast<uint64_t>(reinterpret_cast<uintptr_t>(vt)) >> 3) * 0x9E3779B97F4A7C15ull;
    return static_cast<size_t>(v >> 40) & (kVtCapacity - 1);
}

VtEntry* FindVtEntry(void** vt) {
    size_t i = VtHash(vt);
    for (size_t probe = 0; probe < kVtCapacity; ++probe, i = (i + 1) & (kVtCapacity - 1)) {
        void** key = g_vtables[i].vtable.load(std::memory_order_acquire);
        if (key == vt) return &g_vtables[i];
        if (!key) return nullptr;
    }
    return nullptr;
}

void* OriginalFor(void* object, int slot) {
    if (VtEntry* entry = FindVtEntry(*static_cast<void***>(object))) {
        if (void* original = entry->original[slot]) return original;
    }
    return g_last_original[slot];
}

bool WriteSlot(void** where, void* value) {
    DWORD old = 0;
    if (!VirtualProtect(where, sizeof(void*), PAGE_EXECUTE_READWRITE, &old)) return false;
    *where = value;
    DWORD ignored = 0;
    VirtualProtect(where, sizeof(void*), old, &ignored);
    return true;
}

// Patches `count` slots of the object's vtable. Returns the number of slots newly patched.
int PatchVtable(void* object, const int* slots, void* const* hooks, int count, const char* what) {
    std::lock_guard<std::mutex> lock(g_patch_mutex);
    void** vt = *static_cast<void***>(object);
    VtEntry* entry = FindVtEntry(vt);
    bool fresh = false;
    if (!entry) {
        if (g_vtables_used >= kVtCapacity * 3 / 4) {
            Log("%s: vtable %p not patched (table full)", what, static_cast<void*>(vt));
            return 0;
        }
        size_t i = VtHash(vt);
        while (g_vtables[i].vtable.load(std::memory_order_relaxed)) i = (i + 1) & (kVtCapacity - 1);
        entry = &g_vtables[i];
        fresh = true;
    }
    int patched = 0;
    for (int k = 0; k < count; ++k) {
        const int slot = slots[k];
        if (vt[slot] == hooks[k]) continue;  // ours already
        entry->original[slot] = vt[slot];
        g_last_original[slot] = vt[slot];
        if (WriteSlot(&vt[slot], hooks[k])) {
            ++patched;
        } else {
            Log("%s: VirtualProtect failed on slot %d (error %lu)", what, slot, GetLastError());
            entry->original[slot] = nullptr;
        }
    }
    if (fresh) {
        entry->vtable.store(vt, std::memory_order_release);  // publish after the originals
        ++g_vtables_used;
    }
    if (patched || std::strcmp(what, "Deferred context") != 0) {
        Log("%s: vtable %p, %d slot(s) patched%s", what, static_cast<void*>(vt), patched,
            patched ? "" : " (already hooked: same vtable)");
    }
    return patched;
}

// ---------------------------------------------------------------------------------------------
// Level and shared state
// ---------------------------------------------------------------------------------------------
void SetFlag(LONG flag) {
    if (g_shared) {
        InterlockedOr(&g_shared->plugin_flags, flag);
    } else {
        InterlockedOr(&g_local_flags, flag);
    }
}

int EffectiveLevel() {
    if (g_shared) {
        const LONG level = g_shared->level;
        if (level >= 0 && level <= 3) return static_cast<int>(level);
    }
    return g_ini_level.load(std::memory_order_relaxed);
}

void OpenShared() {
    HANDLE mapping = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, sizeof(RopesShared), kSharedName);
    if (!mapping) {
        Log("Shared memory %ls not created (error %lu): only the ini Level applies", kSharedName, GetLastError());
        return;
    }
    const bool existed = GetLastError() == ERROR_ALREADY_EXISTS;
    auto* view = static_cast<RopesShared*>(MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(RopesShared)));
    if (!view) {
        Log("Shared memory %ls not mapped (error %lu)", kSharedName, GetLastError());
        CloseHandle(mapping);
        return;
    }
    // The handle stays open for the life of the process (the view keeps the mapping alive anyway).
    if (!existed || view->magic != kMagic || view->version != kVersion) {
        view->level = -1;
        view->plugin_flags = 0;
        view->rope_draws = 0;
        view->rope_draws_cut = 0;
        view->version = kVersion;
        MemoryBarrier();
        view->magic = kMagic;
    }
    view->plugin_flags = 0;
    g_shared = view;
    Log("Shared memory %ls %s (Server level %ld)", kSharedName, existed ? "opened" : "created", view->level);
}

// ---------------------------------------------------------------------------------------------
// ini (plugins\SERVER16_Ropes.ini)
// ---------------------------------------------------------------------------------------------
const char kDefaultIni[] =
    "[ROPES]\r\n"
    "; Goal-net ropes: 0 = all ropes, 1 = hide the centre ropes, 2 = hide centre + top rope, 3 = hide all ropes.\r\n"
    "; Used while CG File Server 16 does not set a level for the current stadium. Re-read every second.\r\n"
    "Level=0\r\n"
    "; 1 = write plugins\\SERVER16_Ropes.log (diagnostics), 0 = no log. Read when FIFA starts.\r\n"
    "Log=1\r\n"
    "; 3Dmigoto hashes of the rope draw (from the original rope d3dx.ini). Leave them as they are.\r\n"
    "IndexBufferHash=cd59201f\r\n"
    "VertexShaderHash=323fadce500155ad\r\n"
    "PixelShaderHash=31dd874b1278e9c6\r\n"
    "; 1 = also treat any 240-byte index buffer drawn with 120 indices as ropes (only if the log shows the hashes never match).\r\n"
    "SizeFallback=0\r\n";

std::wstring ModuleDir() {
    wchar_t path[MAX_PATH] = {};
    const DWORD len = GetModuleFileNameW(g_module, path, MAX_PATH);
    std::wstring dir(path, len);
    const size_t slash = dir.find_last_of(L"\\/");
    return slash == std::wstring::npos ? std::wstring() : dir.substr(0, slash + 1);
}

uint64_t IniHex(const wchar_t* key, uint64_t fallback) {
    wchar_t buf[64] = {};
    GetPrivateProfileStringW(L"ROPES", key, L"", buf, 64, g_ini_path.c_str());
    if (!buf[0]) return fallback;
    wchar_t* end = nullptr;
    const uint64_t value = _wcstoui64(buf, &end, 16);
    return (end && end != buf) ? value : fallback;
}

int IniLevel() {
    const int level = static_cast<int>(GetPrivateProfileIntW(L"ROPES", L"Level", 0, g_ini_path.c_str()));
    return (level >= 0 && level <= 3) ? level : 0;
}

void LoadIni() {
    if (GetFileAttributesW(g_ini_path.c_str()) == INVALID_FILE_ATTRIBUTES) {
        if (FILE* f = _wfopen(g_ini_path.c_str(), L"wb")) {
            std::fwrite(kDefaultIni, 1, sizeof(kDefaultIni) - 1, f);
            std::fclose(f);
        }
    }
    g_ini_level.store(IniLevel());
    g_log_enabled = GetPrivateProfileIntW(L"ROPES", L"Log", 1, g_ini_path.c_str()) != 0;
    g_size_fallback = GetPrivateProfileIntW(L"ROPES", L"SizeFallback", 0, g_ini_path.c_str()) != 0;
    g_ib_hash = static_cast<uint32_t>(IniHex(L"IndexBufferHash", kDefaultIndexBufferHash));
    g_vs_hash = IniHex(L"VertexShaderHash", kDefaultVertexShaderHash);
    g_ps_hash = IniHex(L"PixelShaderHash", kDefaultPixelShaderHash);
}

// ---------------------------------------------------------------------------------------------
// Rope identification
// ---------------------------------------------------------------------------------------------
template <class T>
uint64_t ShaderHash(T* shader) {
    if (!shader) return 0;
    uint64_t hash = 0;
    UINT size = sizeof(hash);
    if (FAILED(shader->GetPrivateData(kShaderHashGuid, &size, &hash)) || size != sizeof(hash)) return 0;
    return hash;
}

uint64_t BoundVsHash(ID3D11DeviceContext* ctx) {
    ID3D11VertexShader* vs = nullptr;
    ctx->VSGetShader(&vs, nullptr, nullptr);
    const uint64_t hash = ShaderHash(vs);
    if (vs) vs->Release();
    return hash;
}

uint64_t BoundPsHash(ID3D11DeviceContext* ctx) {
    ID3D11PixelShader* ps = nullptr;
    ctx->PSGetShader(&ps, nullptr, nullptr);
    const uint64_t hash = ShaderHash(ps);
    if (ps) ps->Release();
    return hash;
}

struct BoundIndexBuffer {
    ID3D11Buffer* buffer = nullptr;  // not AddRef'd after Inspect returns (compared only)
    uint32_t tag = kTagNone;
    UINT byte_width = 0;
    DXGI_FORMAT format = DXGI_FORMAT_UNKNOWN;
    UINT offset = 0;
};

BoundIndexBuffer InspectIndexBuffer(ID3D11DeviceContext* ctx) {
    BoundIndexBuffer out;
    ID3D11Buffer* ib = nullptr;
    ctx->IAGetIndexBuffer(&ib, &out.format, &out.offset);
    if (!ib) return out;
    uint32_t tag = kTagNone;
    UINT size = sizeof(tag);
    if (FAILED(ib->GetPrivateData(kRopeTagGuid, &size, &tag)) || size != sizeof(tag)) tag = kTagNone;
    D3D11_BUFFER_DESC desc = {};
    ib->GetDesc(&desc);
    out.buffer = ib;
    out.tag = tag;
    out.byte_width = desc.ByteWidth;
    ib->Release();
    return out;
}

// Diagnostics: the first rope draws, and the first untagged 120-index draws (distinct buffers),
// so a single match tells whether the hashes match on this install.
constexpr int kMaxLoggedRopeDraws = 24;
constexpr int kMaxLoggedOtherBuffers = 40;
std::atomic<int> g_logged_rope_draws{0};
ID3D11Buffer* g_logged_other_buffers[kMaxLoggedOtherBuffers];
std::atomic<int> g_logged_other_count{0};
std::mutex g_diag_mutex;

void LogOther120(ID3D11DeviceContext* ctx, const BoundIndexBuffer& ib, bool instanced) {
    if (!g_log_enabled || g_logged_other_count.load(std::memory_order_relaxed) >= kMaxLoggedOtherBuffers) return;
    {
        std::lock_guard<std::mutex> lock(g_diag_mutex);
        const int n = g_logged_other_count.load(std::memory_order_relaxed);
        if (n >= kMaxLoggedOtherBuffers) return;
        for (int i = 0; i < n; ++i) {
            if (g_logged_other_buffers[i] == ib.buffer) return;
        }
        g_logged_other_buffers[n] = ib.buffer;
        g_logged_other_count.store(n + 1, std::memory_order_relaxed);
    }
    Log("120-index draw, not ropes: ib %p (%u bytes, fmt %d) vs %016llx ps %016llx%s%s", ib.buffer, ib.byte_width,
        static_cast<int>(ib.format), BoundVsHash(ctx), BoundPsHash(ctx), instanced ? " instanced" : "",
        ctx == g_immediate ? "" : " deferred");
}

void LogRopeDraw(ID3D11DeviceContext* ctx, const BoundIndexBuffer& ib, bool by_vs, int level, UINT start, INT base,
                 bool instanced) {
    if (!g_log_enabled) return;
    if (g_logged_rope_draws.fetch_add(1) >= kMaxLoggedRopeDraws) return;
    const uint64_t vs = BoundVsHash(ctx);
    const uint64_t ps = BoundPsHash(ctx);
    Log("Rope draw (%s): ib %p (%u bytes, fmt %d, tag %u) start %u base %d vs %016llx%s ps %016llx%s level %d%s%s",
        by_vs ? "vertex shader" : "index buffer", ib.buffer, ib.byte_width, static_cast<int>(ib.format), ib.tag, start,
        base, vs, vs == g_vs_hash ? " (d3dx.ini)" : "", ps, ps == g_ps_hash ? " (d3dx.ini)" : "", level,
        instanced ? " instanced" : "", ctx == g_immediate ? "" : " deferred");
}

// Decides whether this 120-index draw is a rope draw. Cheap test (index count) first: this runs
// for every indexed draw FIFA makes.
bool IsRopeDraw(ID3D11DeviceContext* ctx, BoundIndexBuffer& ib, bool& by_vs, bool instanced) {
    ib = InspectIndexBuffer(ctx);
    by_vs = false;
    if (ib.tag != kTagNone) return true;
    if (g_vs_hash && BoundVsHash(ctx) == g_vs_hash) {
        by_vs = true;
        return true;
    }
    LogOther120(ctx, ib, instanced);
    return false;
}

// ---------------------------------------------------------------------------------------------
// Device hooks
// ---------------------------------------------------------------------------------------------
using PFN_CreateBuffer = HRESULT(STDMETHODCALLTYPE*)(ID3D11Device*, const D3D11_BUFFER_DESC*,
                                                     const D3D11_SUBRESOURCE_DATA*, ID3D11Buffer**);
using PFN_CreateVS = HRESULT(STDMETHODCALLTYPE*)(ID3D11Device*, const void*, SIZE_T, ID3D11ClassLinkage*,
                                                 ID3D11VertexShader**);
using PFN_CreatePS = HRESULT(STDMETHODCALLTYPE*)(ID3D11Device*, const void*, SIZE_T, ID3D11ClassLinkage*,
                                                 ID3D11PixelShader**);
using PFN_CreateDeferred = HRESULT(STDMETHODCALLTYPE*)(ID3D11Device*, UINT, ID3D11DeviceContext**);
using PFN_DrawIndexed = void(STDMETHODCALLTYPE*)(ID3D11DeviceContext*, UINT, UINT, INT);
using PFN_DrawIndexedInstanced = void(STDMETHODCALLTYPE*)(ID3D11DeviceContext*, UINT, UINT, UINT, INT, UINT);

void TagIndexBuffer(ID3D11Buffer* buffer, const D3D11_BUFFER_DESC* desc, const D3D11_SUBRESOURCE_DATA* init) {
    const bool has_data = init && init->pSysMem && desc->ByteWidth;
    const uint32_t data_hash = has_data ? Crc32cAppend(0, init->pSysMem, desc->ByteWidth) : 0;
    const uint32_t full_hash = Crc32cAppend(data_hash, desc, sizeof(*desc));
    uint32_t tag = kTagNone;
    if (has_data && data_hash == g_ib_hash) {
        tag = kTagHashData;
    } else if (full_hash == g_ib_hash) {
        tag = kTagHashFull;
    } else if (g_size_fallback && desc->ByteWidth == kRopeIndexCount * 2) {
        tag = kTagSize;
    }
    if (tag == kTagNone) return;
    buffer->SetPrivateData(kRopeTagGuid, sizeof(tag), &tag);
    SetFlag(kFlagRopeBuffer);
    const long n = ++g_rope_buffers;
    if (n <= 16) {
        Log("Rope index buffer tagged: %p (%u bytes, usage %d, initial data %s) crc(data) %08x crc(data+desc) %08x -> %s",
            buffer, desc->ByteWidth, static_cast<int>(desc->Usage), has_data ? "yes" : "no", data_hash, full_hash,
            tag == kTagHashData ? "data hash" : tag == kTagHashFull ? "data+desc hash" : "size fallback");
    }
}

HRESULT STDMETHODCALLTYPE Hook_CreateBuffer(ID3D11Device* self, const D3D11_BUFFER_DESC* desc,
                                            const D3D11_SUBRESOURCE_DATA* init, ID3D11Buffer** out) {
    auto original = reinterpret_cast<PFN_CreateBuffer>(OriginalFor(self, kDevCreateBuffer));
    const HRESULT hr = original(self, desc, init, out);
    if (SUCCEEDED(hr) && desc && out && *out && (desc->BindFlags & D3D11_BIND_INDEX_BUFFER)) {
        TagIndexBuffer(*out, desc, init);
    }
    return hr;
}

template <class T>
void TagShader(T* shader, const void* bytecode, SIZE_T length) {
    if (!shader || !bytecode || !length) return;
    const uint64_t hash = Fnv64(bytecode, length);
    shader->SetPrivateData(kShaderHashGuid, sizeof(hash), &hash);
    ++g_shaders_hashed;
}

HRESULT STDMETHODCALLTYPE Hook_CreateVertexShader(ID3D11Device* self, const void* bytecode, SIZE_T length,
                                                  ID3D11ClassLinkage* linkage, ID3D11VertexShader** out) {
    auto original = reinterpret_cast<PFN_CreateVS>(OriginalFor(self, kDevCreateVertexShader));
    const HRESULT hr = original(self, bytecode, length, linkage, out);
    if (SUCCEEDED(hr) && out) TagShader(*out, bytecode, length);
    return hr;
}

HRESULT STDMETHODCALLTYPE Hook_CreatePixelShader(ID3D11Device* self, const void* bytecode, SIZE_T length,
                                                 ID3D11ClassLinkage* linkage, ID3D11PixelShader** out) {
    auto original = reinterpret_cast<PFN_CreatePS>(OriginalFor(self, kDevCreatePixelShader));
    const HRESULT hr = original(self, bytecode, length, linkage, out);
    if (SUCCEEDED(hr) && out) TagShader(*out, bytecode, length);
    return hr;
}

void HookContext(ID3D11DeviceContext* ctx, const char* what);

HRESULT STDMETHODCALLTYPE Hook_CreateDeferredContext(ID3D11Device* self, UINT flags, ID3D11DeviceContext** out) {
    auto original = reinterpret_cast<PFN_CreateDeferred>(OriginalFor(self, kDevCreateDeferredContext));
    const HRESULT hr = original(self, flags, out);
    if (SUCCEEDED(hr) && out && *out) HookContext(*out, "Deferred context");
    return hr;
}

// ---------------------------------------------------------------------------------------------
// Context hooks
// ---------------------------------------------------------------------------------------------
// Re-issues a rope draw as the parts the level keeps. `draw(count, offset)` draws `count` indices
// starting `offset` indices after the original start.
template <class Draw>
void DrawRopeParts(int level, Draw draw) {
    switch (level) {
        case 1:  // hide centre
            draw(kOuterCount, kOuterStart);
            draw(kTopCount, kTopStart);
            break;
        case 2:  // hide centre + top
            draw(kOuterCount, kOuterStart);
            break;
        case 3:  // hide all
            break;
        default:
            draw(kRopeIndexCount, 0);
            break;
    }
}

void CountRopeDraw(int level) {
    ++g_rope_draws;
    SetFlag(kFlagRopeDraw);
    if (g_shared) InterlockedIncrement(&g_shared->rope_draws);
    if (level != 0) {
        ++g_rope_draws_cut;
        if (g_shared) InterlockedIncrement(&g_shared->rope_draws_cut);
    }
}

// Shared draw logic. `original` is the next function down: the vtable slot's previous value, or the
// MinHook trampoline of an inline-hooked DrawIndexed implementation.
void DoDrawIndexed(PFN_DrawIndexed original, ID3D11DeviceContext* ctx, UINT count, UINT start, INT base) {
    if (g_log_enabled) {
        g_indexed_draws.fetch_add(1, std::memory_order_relaxed);
        if (count == kRopeIndexCount) g_draws_120.fetch_add(1, std::memory_order_relaxed);
    }
    if (count != kRopeIndexCount || (!g_log_enabled && EffectiveLevel() == 0)) {
        original(ctx, count, start, base);
        return;
    }
    BoundIndexBuffer ib;
    bool by_vs = false;
    if (!IsRopeDraw(ctx, ib, by_vs, false)) {
        original(ctx, count, start, base);
        return;
    }
    const int level = EffectiveLevel();
    CountRopeDraw(level);
    LogRopeDraw(ctx, ib, by_vs, level, start, base, false);
    DrawRopeParts(level, [&](UINT part_count, UINT part_offset) { original(ctx, part_count, start + part_offset, base); });
}

void DoDrawIndexedInstanced(PFN_DrawIndexedInstanced original, ID3D11DeviceContext* ctx, UINT count, UINT instances,
                            UINT start, INT base, UINT start_instance) {
    if (g_log_enabled) {
        g_indexed_draws.fetch_add(1, std::memory_order_relaxed);
        if (count == kRopeIndexCount) g_draws_120.fetch_add(1, std::memory_order_relaxed);
    }
    if (count != kRopeIndexCount || (!g_log_enabled && EffectiveLevel() == 0)) {
        original(ctx, count, instances, start, base, start_instance);
        return;
    }
    BoundIndexBuffer ib;
    bool by_vs = false;
    if (!IsRopeDraw(ctx, ib, by_vs, true)) {
        original(ctx, count, instances, start, base, start_instance);
        return;
    }
    const int level = EffectiveLevel();
    CountRopeDraw(level);
    LogRopeDraw(ctx, ib, by_vs, level, start, base, true);
    DrawRopeParts(level, [&](UINT part_count, UINT part_offset) {
        original(ctx, part_count, instances, start + part_offset, base, start_instance);
    });
}

// vtable hooks (fallback when the function behind a slot cannot be inline-hooked)
void STDMETHODCALLTYPE Hook_DrawIndexed(ID3D11DeviceContext* ctx, UINT count, UINT start, INT base) {
    DoDrawIndexed(reinterpret_cast<PFN_DrawIndexed>(OriginalFor(ctx, kCtxDrawIndexed)), ctx, count, start, base);
}

void STDMETHODCALLTYPE Hook_DrawIndexedInstanced(ID3D11DeviceContext* ctx, UINT count, UINT instances, UINT start,
                                                 INT base, UINT start_instance) {
    DoDrawIndexedInstanced(reinterpret_cast<PFN_DrawIndexedInstanced>(OriginalFor(ctx, kCtxDrawIndexedInstanced)),
                           ctx, count, instances, start, base, start_instance);
}

// ---------------------------------------------------------------------------------------------
// Inline hooks (MinHook) on the functions the context vtables point to. Live log 2026-11-23 (test 3):
// with every context's vtable slot patched, not one DrawIndexed came through ("indexed draws 0"):
// the per-context heap vtables are replaced or bypassed after creation. Hooking the function itself
// catches every caller, whatever vtable it goes through. Confirmed live (test 4): both methods
// inline-hooked in d3d11.dll, ropes gone at Level=3. Immediate and deferred contexts may use
// different implementations, so up to kMaxInlineTargets distinct functions per method.
// ---------------------------------------------------------------------------------------------
constexpr int kMaxInlineTargets = 8;
struct InlineHook {
    void* target;
    void* trampoline;
};
InlineHook g_inline[2][kMaxInlineTargets];  // [0] DrawIndexed, [1] DrawIndexedInstanced
int g_inline_count[2] = {0, 0};             // under g_patch_mutex
bool g_minhook_ready = false;

template <int N>
void STDMETHODCALLTYPE InlineDrawIndexed(ID3D11DeviceContext* ctx, UINT count, UINT start, INT base) {
    DoDrawIndexed(reinterpret_cast<PFN_DrawIndexed>(g_inline[0][N].trampoline), ctx, count, start, base);
}

template <int N>
void STDMETHODCALLTYPE InlineDrawIndexedInstanced(ID3D11DeviceContext* ctx, UINT count, UINT instances, UINT start,
                                                  INT base, UINT start_instance) {
    DoDrawIndexedInstanced(reinterpret_cast<PFN_DrawIndexedInstanced>(g_inline[1][N].trampoline), ctx, count,
                           instances, start, base, start_instance);
}

#define CGFS16_DETOURS(F)                                                                                  \
    {                                                                                                      \
        reinterpret_cast<void*>(&F<0>), reinterpret_cast<void*>(&F<1>), reinterpret_cast<void*>(&F<2>),    \
            reinterpret_cast<void*>(&F<3>), reinterpret_cast<void*>(&F<4>), reinterpret_cast<void*>(&F<5>), \
            reinterpret_cast<void*>(&F<6>), reinterpret_cast<void*>(&F<7>)                                 \
    }
void* const kInlineDetours[2][kMaxInlineTargets] = {CGFS16_DETOURS(InlineDrawIndexed),
                                                    CGFS16_DETOURS(InlineDrawIndexedInstanced)};
#undef CGFS16_DETOURS
const char* const kInlineNames[2] = {"DrawIndexed", "DrawIndexedInstanced"};

std::string ModuleOf(void* address, uintptr_t* offset) {
    HMODULE module = nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                            static_cast<LPCWSTR>(address), &module)) {
        return std::string();
    }
    char path[MAX_PATH] = {};
    const DWORD len = GetModuleFileNameA(module, path, MAX_PATH);
    std::string name(path, len);
    const size_t slash = name.find_last_of("\\/");
    if (slash != std::string::npos) name = name.substr(slash + 1);
    if (offset) *offset = reinterpret_cast<uintptr_t>(address) - reinterpret_cast<uintptr_t>(module);
    return name.empty() ? std::string("?") : name;
}

// Caller holds g_patch_mutex. True when calls to `target` now reach our draw logic.
bool InlineHookTarget(void* target, int kind, const char* what) {
    if (target == reinterpret_cast<void*>(&Hook_DrawIndexed) ||
        target == reinterpret_cast<void*>(&Hook_DrawIndexedInstanced)) {
        return true;  // the slot already holds our vtable hook
    }
    for (int i = 0; i < g_inline_count[kind]; ++i) {
        if (g_inline[kind][i].target == target) return true;
    }
    uintptr_t offset = 0;
    const std::string module = ModuleOf(target, &offset);
    if (module.empty()) {
        Log("%s: %s target %p is not inside a module: vtable hook instead", what, kInlineNames[kind], target);
        return false;
    }
    if (!g_minhook_ready || g_inline_count[kind] >= kMaxInlineTargets) {
        Log("%s: %s target %p (%s+0x%llx) not inline-hooked (%s): vtable hook instead", what, kInlineNames[kind],
            target, module.c_str(), static_cast<unsigned long long>(offset),
            g_minhook_ready ? "too many targets" : "MinHook unavailable");
        return false;
    }
    const int n = g_inline_count[kind];
    void* trampoline = nullptr;
    MH_STATUS status = MH_CreateHook(target, kInlineDetours[kind][n], &trampoline);
    if (status != MH_OK) {
        Log("%s: %s target %p (%s+0x%llx): MH_CreateHook %s, vtable hook instead", what, kInlineNames[kind], target,
            module.c_str(), static_cast<unsigned long long>(offset), MH_StatusToString(status));
        return false;
    }
    g_inline[kind][n].target = target;
    g_inline[kind][n].trampoline = trampoline;  // set before the hook goes live
    status = MH_EnableHook(target);
    if (status != MH_OK) {
        Log("%s: %s target %p: MH_EnableHook %s, vtable hook instead", what, kInlineNames[kind], target,
            MH_StatusToString(status));
        MH_RemoveHook(target);
        g_inline[kind][n] = InlineHook{};
        return false;
    }
    g_inline_count[kind] = n + 1;
    Log("%s: %s inline-hooked at %p (%s+0x%llx)", what, kInlineNames[kind], target, module.c_str(),
        static_cast<unsigned long long>(offset));
    return true;
}

void HookContext(ID3D11DeviceContext* ctx, const char* what) {
    void** vt = *reinterpret_cast<void***>(ctx);
    bool inline_ok[2] = {false, false};
    {
        std::lock_guard<std::mutex> lock(g_patch_mutex);
        inline_ok[0] = InlineHookTarget(vt[kCtxDrawIndexed], 0, what);
        inline_ok[1] = InlineHookTarget(vt[kCtxDrawIndexedInstanced], 1, what);
    }
    int slots[2];
    void* hooks[2];
    int count = 0;
    if (!inline_ok[0]) {
        slots[count] = kCtxDrawIndexed;
        hooks[count++] = reinterpret_cast<void*>(&Hook_DrawIndexed);
    }
    if (!inline_ok[1]) {
        slots[count] = kCtxDrawIndexedInstanced;
        hooks[count++] = reinterpret_cast<void*>(&Hook_DrawIndexedInstanced);
    }
    if (count) PatchVtable(ctx, slots, hooks, count, what);
}

void HookDevice(ID3D11Device* device, const char* what) {
    static const int slots[] = {kDevCreateBuffer, kDevCreateVertexShader, kDevCreatePixelShader,
                                kDevCreateDeferredContext};
    static void* const hooks[] = {
        reinterpret_cast<void*>(&Hook_CreateBuffer), reinterpret_cast<void*>(&Hook_CreateVertexShader),
        reinterpret_cast<void*>(&Hook_CreatePixelShader), reinterpret_cast<void*>(&Hook_CreateDeferredContext)};
    PatchVtable(device, slots, hooks, 4, what);
}

HRESULT WINAPI Hook_D3D11CreateDevice(IDXGIAdapter* adapter, D3D_DRIVER_TYPE driver, HMODULE software, UINT flags,
                                      const D3D_FEATURE_LEVEL* levels, UINT level_count, UINT sdk,
                                      ID3D11Device** device, D3D_FEATURE_LEVEL* out_level,
                                      ID3D11DeviceContext** context) {
    const HRESULT hr =
        g_orig_create_device(adapter, driver, software, flags, levels, level_count, sdk, device, out_level, context);
    Log("D3D11CreateDevice(driver %d, flags 0x%X) -> 0x%08lX, device %p", static_cast<int>(driver), flags,
        static_cast<unsigned long>(hr), (device && SUCCEEDED(hr)) ? static_cast<void*>(*device) : nullptr);
    if (SUCCEEDED(hr) && device && *device) {
        HookDevice(*device, "Device");
        ID3D11DeviceContext* immediate = nullptr;
        (*device)->GetImmediateContext(&immediate);
        if (immediate) {
            g_immediate = immediate;
            HookContext(immediate, "Immediate context");
            immediate->Release();
        }
        SetFlag(kFlagDeviceHooked);
    }
    return hr;
}

// ---------------------------------------------------------------------------------------------
// Getting FIFA's D3D11CreateDevice call. FIP's fifa16.exe ("DEL" build, entry point 0x1439FA151 on
// disk) imports it, but by the time plugins load, the in-memory PE header is the original protected
// one (entry point 0x149523000, seen live 2026-11-23) and its import directory no longer lists
// d3d11.dll. So, in order:
//   A. the in-memory import directory (an exe whose header is left alone),
//   B. the import table read from the exe file on disk, applied to the in-memory IAT slot,
//   C. d3d11.dll's export table (every later GetProcAddress gets the hook),
//   D. fallback: a throwaway device of our own, created right away from a thread, whose vtables
//      FIFA's device shares; patched before FIFA creates its resources.
// A slot is only patched while it still holds d3d11's own export (never another plugin's hook).
// ---------------------------------------------------------------------------------------------
void* g_real_create_device = nullptr;  // d3d11's export, read before any patch
bool g_export_patched = false;

bool IsReadable(const void* address, size_t size) {
    MEMORY_BASIC_INFORMATION mbi = {};
    if (!VirtualQuery(address, &mbi, sizeof(mbi)) || mbi.State != MEM_COMMIT) return false;
    if (mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)) return false;
    const auto* end = static_cast<const uint8_t*>(address) + size;
    return end <= static_cast<const uint8_t*>(mbi.BaseAddress) + mbi.RegionSize;
}

bool PatchImportSlot(void** slot, const char* how) {
    if (!IsReadable(slot, sizeof(void*))) {
        Log("%s: slot %p not readable", how, static_cast<void*>(slot));
        return false;
    }
    void* current = *slot;
    if (current == reinterpret_cast<void*>(&Hook_D3D11CreateDevice)) return true;
    if (current != g_real_create_device) {
        Log("%s: slot %p holds %p, not d3d11's export %p: left alone", how, static_cast<void*>(slot), current,
            g_real_create_device);
        return false;
    }
    if (!WriteSlot(slot, reinterpret_cast<void*>(&Hook_D3D11CreateDevice))) {
        Log("%s: slot %p not writable (error %lu)", how, static_cast<void*>(slot), GetLastError());
        return false;
    }
    Log("%s: import slot %p patched", how, static_cast<void*>(slot));
    return true;
}

// A. Import directory of the running image.
int HookImportInMemory() {
    auto* base = reinterpret_cast<uint8_t*>(GetModuleHandleW(nullptr));
    auto* nt = reinterpret_cast<IMAGE_NT_HEADERS64*>(base + reinterpret_cast<IMAGE_DOS_HEADER*>(base)->e_lfanew);
    const IMAGE_DATA_DIRECTORY& dir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (!dir.VirtualAddress || !IsReadable(base + dir.VirtualAddress, sizeof(IMAGE_IMPORT_DESCRIPTOR))) return 0;
    int patched = 0;
    for (auto* imp = reinterpret_cast<IMAGE_IMPORT_DESCRIPTOR*>(base + dir.VirtualAddress); imp->Name; ++imp) {
        if (_stricmp(reinterpret_cast<const char*>(base + imp->Name), "d3d11.dll") != 0) continue;
        auto* thunk = reinterpret_cast<IMAGE_THUNK_DATA64*>(base + imp->FirstThunk);
        auto* names = imp->OriginalFirstThunk
                          ? reinterpret_cast<IMAGE_THUNK_DATA64*>(base + imp->OriginalFirstThunk)
                          : nullptr;
        for (; thunk->u1.Function; ++thunk) {
            bool match = false;
            if (names && !IMAGE_SNAP_BY_ORDINAL64(names->u1.Ordinal)) {
                auto* by_name = reinterpret_cast<IMAGE_IMPORT_BY_NAME*>(base + names->u1.AddressOfData);
                match = std::strcmp(reinterpret_cast<const char*>(by_name->Name), "D3D11CreateDevice") == 0;
            } else {
                match = reinterpret_cast<void*>(thunk->u1.Function) == g_real_create_device;
            }
            if (names) ++names;
            if (match && PatchImportSlot(reinterpret_cast<void**>(&thunk->u1.Function), "A (in-memory imports)")) {
                ++patched;
            }
        }
    }
    return patched;
}

// B. Import table of the exe file on disk; the slot RVAs it names are where the Windows loader
// resolved the imports in memory, before the header was swapped.
int HookImportFromFile() {
    wchar_t path[MAX_PATH] = {};
    if (!GetModuleFileNameW(nullptr, path, MAX_PATH)) return 0;
    HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr,
                              OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        Log("B (file imports): exe not opened (error %lu)", GetLastError());
        return 0;
    }
    LARGE_INTEGER file_size = {};
    GetFileSizeEx(file, &file_size);
    HANDLE mapping = CreateFileMappingW(file, nullptr, PAGE_READONLY, 0, 0, nullptr);
    const auto* data = mapping ? static_cast<const uint8_t*>(MapViewOfFile(mapping, FILE_MAP_READ, 0, 0, 0)) : nullptr;
    int patched = 0;
    if (data) {
        const uint64_t size = static_cast<uint64_t>(file_size.QuadPart);
        auto in_file = [&](uint64_t offset, uint64_t length) { return offset <= size && length <= size - offset; };
        const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(data);
        const IMAGE_NT_HEADERS64* nt = nullptr;
        if (in_file(0, sizeof(*dos)) && dos->e_magic == IMAGE_DOS_SIGNATURE &&
            in_file(static_cast<uint64_t>(dos->e_lfanew), sizeof(IMAGE_NT_HEADERS64))) {
            nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(data + dos->e_lfanew);
            if (nt->Signature != IMAGE_NT_SIGNATURE) nt = nullptr;
        }
        if (nt) {
            const auto* sections = IMAGE_FIRST_SECTION(nt);
            const WORD section_count = nt->FileHeader.NumberOfSections;
            auto rva_to_offset = [&](DWORD rva) -> int64_t {
                for (WORD i = 0; i < section_count; ++i) {
                    const DWORD span = std::max(sections[i].Misc.VirtualSize, sections[i].SizeOfRawData);
                    if (rva >= sections[i].VirtualAddress && rva < sections[i].VirtualAddress + span) {
                        return static_cast<int64_t>(rva - sections[i].VirtualAddress) + sections[i].PointerToRawData;
                    }
                }
                return -1;
            };
            Log("B (file imports): exe on disk has entry point %p",
                reinterpret_cast<void*>(nt->OptionalHeader.ImageBase + nt->OptionalHeader.AddressOfEntryPoint));
            const IMAGE_DATA_DIRECTORY& dir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
            int64_t desc_off = dir.VirtualAddress ? rva_to_offset(dir.VirtualAddress) : -1;
            auto* image = reinterpret_cast<uint8_t*>(GetModuleHandleW(nullptr));
            for (; desc_off >= 0 && in_file(static_cast<uint64_t>(desc_off), sizeof(IMAGE_IMPORT_DESCRIPTOR));
                 desc_off += sizeof(IMAGE_IMPORT_DESCRIPTOR)) {
                const auto* imp = reinterpret_cast<const IMAGE_IMPORT_DESCRIPTOR*>(data + desc_off);
                if (!imp->Name) break;
                const int64_t name_off = rva_to_offset(imp->Name);
                if (name_off < 0 || !in_file(static_cast<uint64_t>(name_off), 10)) continue;
                if (_strnicmp(reinterpret_cast<const char*>(data + name_off), "d3d11.dll", 10) != 0) continue;
                const DWORD names_rva = imp->OriginalFirstThunk ? imp->OriginalFirstThunk : imp->FirstThunk;
                int64_t thunk_off = rva_to_offset(names_rva);
                for (DWORD index = 0; thunk_off >= 0 && in_file(static_cast<uint64_t>(thunk_off), 8);
                     ++index, thunk_off += 8) {
                    const uint64_t entry = *reinterpret_cast<const uint64_t*>(data + thunk_off);
                    if (!entry) break;
                    if (IMAGE_SNAP_BY_ORDINAL64(entry)) continue;
                    const int64_t by_name_off = rva_to_offset(static_cast<DWORD>(entry));
                    if (by_name_off < 0 || !in_file(static_cast<uint64_t>(by_name_off), 2 + 18)) continue;
                    const char* name = reinterpret_cast<const char*>(data + by_name_off + 2);
                    if (std::strncmp(name, "D3D11CreateDevice", 18) != 0) continue;
                    void** slot = reinterpret_cast<void**>(image + imp->FirstThunk + index * 8ull);
                    if (PatchImportSlot(slot, "B (file imports)")) ++patched;
                }
            }
        }
        UnmapViewOfFile(data);
    }
    if (mapping) CloseHandle(mapping);
    CloseHandle(file);
    return patched;
}

// C. Export table of d3d11.dll. The new RVA must be a 32-bit offset above the module, so the hook
// is reached through a small jump stub allocated just after the image.
bool HookExportTable(HMODULE d3d11) {
    auto* base = reinterpret_cast<uint8_t*>(d3d11);
    auto* nt = reinterpret_cast<IMAGE_NT_HEADERS64*>(base + reinterpret_cast<IMAGE_DOS_HEADER*>(base)->e_lfanew);
    const IMAGE_DATA_DIRECTORY& dir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT];
    if (!dir.VirtualAddress) return false;
    auto* exports = reinterpret_cast<IMAGE_EXPORT_DIRECTORY*>(base + dir.VirtualAddress);
    auto* names = reinterpret_cast<DWORD*>(base + exports->AddressOfNames);
    auto* ordinals = reinterpret_cast<WORD*>(base + exports->AddressOfNameOrdinals);
    auto* functions = reinterpret_cast<DWORD*>(base + exports->AddressOfFunctions);
    DWORD* rva_slot = nullptr;
    for (DWORD i = 0; i < exports->NumberOfNames; ++i) {
        if (std::strcmp(reinterpret_cast<const char*>(base + names[i]), "D3D11CreateDevice") == 0) {
            rva_slot = &functions[ordinals[i]];
            break;
        }
    }
    if (!rva_slot) return false;
    if (base + *rva_slot != g_real_create_device) {
        Log("C (d3d11 exports): export already redirected to %p: left alone", static_cast<void*>(base + *rva_slot));
        return false;
    }
    uint8_t* stub = nullptr;
    const uintptr_t image_end = reinterpret_cast<uintptr_t>(base) + nt->OptionalHeader.SizeOfImage;
    const uintptr_t first = (image_end + 0xFFFF) & ~static_cast<uintptr_t>(0xFFFF);
    for (uintptr_t at = first; at < reinterpret_cast<uintptr_t>(base) + 0x7FFF0000ull && !stub; at += 0x10000) {
        stub = static_cast<uint8_t*>(
            VirtualAlloc(reinterpret_cast<void*>(at), 4096, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
    }
    if (!stub) {
        Log("C (d3d11 exports): no memory for the jump stub near d3d11.dll");
        return false;
    }
    // jmp qword ptr [rip+0] ; dq Hook_D3D11CreateDevice
    const uint8_t jump[6] = {0xFF, 0x25, 0x00, 0x00, 0x00, 0x00};
    std::memcpy(stub, jump, sizeof(jump));
    void* target = reinterpret_cast<void*>(&Hook_D3D11CreateDevice);
    std::memcpy(stub + sizeof(jump), &target, sizeof(target));
    DWORD old = 0;
    VirtualProtect(stub, 4096, PAGE_EXECUTE_READ, &old);
    FlushInstructionCache(GetCurrentProcess(), stub, 16);
    const DWORD new_rva = static_cast<DWORD>(stub - base);
    if (!VirtualProtect(rva_slot, sizeof(DWORD), PAGE_READWRITE, &old)) {
        Log("C (d3d11 exports): export table not writable (error %lu)", GetLastError());
        return false;
    }
    *rva_slot = new_rva;
    DWORD ignored = 0;
    VirtualProtect(rva_slot, sizeof(DWORD), old, &ignored);
    Log("C (d3d11 exports): D3D11CreateDevice export redirected through stub %p", static_cast<void*>(stub));
    return true;
}

// D. Throwaway device, created right away from a thread (never inside DllMain).
DWORD WINAPI EarlyDeviceThread(LPVOID) {
    HMODULE d3d11 = GetModuleHandleW(L"d3d11.dll");
    if (!d3d11) {
        d3d11 = LoadLibraryW(L"d3d11.dll");
        Log("d3d11.dll was not loaded yet; loaded now: %p", static_cast<void*>(d3d11));
        if (!d3d11) return 0;
    }
    if (!g_real_create_device) {
        g_real_create_device = reinterpret_cast<void*>(GetProcAddress(d3d11, "D3D11CreateDevice"));
        g_orig_create_device = reinterpret_cast<PFN_CreateDevice>(g_real_create_device);
        if (!g_real_create_device) return 0;
        g_export_patched = HookExportTable(d3d11);
    }
    ID3D11Device* device = nullptr;
    ID3D11DeviceContext* context = nullptr;
    const HRESULT hr = g_orig_create_device(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr, 0, nullptr, 0,
                                            D3D11_SDK_VERSION, &device, nullptr, &context);
    Log("D (probe device): D3D11CreateDevice -> 0x%08lX", static_cast<unsigned long>(hr));
    if (SUCCEEDED(hr) && device && context) {
        HookDevice(device, "Device (probe)");
        HookContext(context, "Immediate context (probe)");
        SetFlag(kFlagDeviceHooked);
    }
    if (context) context->Release();
    if (device) device->Release();
    return 0;
}

void InstallCreateDeviceHooks() {
    HMODULE d3d11 = GetModuleHandleW(L"d3d11.dll");
    g_real_create_device = d3d11 ? reinterpret_cast<void*>(GetProcAddress(d3d11, "D3D11CreateDevice")) : nullptr;
    g_orig_create_device = reinterpret_cast<PFN_CreateDevice>(g_real_create_device);
    Log("d3d11.dll %p, D3D11CreateDevice %p", static_cast<void*>(d3d11), g_real_create_device);
    if (g_real_create_device) {
        const int a = HookImportInMemory();
        const int b = a ? 0 : HookImportFromFile();
        if (a + b) SetFlag(kFlagIatHooked);
        g_export_patched = HookExportTable(d3d11);
        Log("Hooks: import slots %d (in-memory %d, from file %d), export %s", a + b, a, b,
            g_export_patched ? "redirected" : "not redirected");
    }
    if (HANDLE thread = CreateThread(nullptr, 0, EarlyDeviceThread, nullptr, 0, nullptr)) CloseHandle(thread);
}

// ---------------------------------------------------------------------------------------------
// Watcher thread: ini Level changes and periodic counters
// ---------------------------------------------------------------------------------------------
DWORD WINAPI WatcherThread(LPVOID) {
    FILETIME last_write = {};
    int last_effective = -1;
    long last_draws = -1;
    ULONGLONG last_stats = GetTickCount64();
    for (;;) {
        Sleep(1000);
        WIN32_FILE_ATTRIBUTE_DATA attrs;
        if (GetFileAttributesExW(g_ini_path.c_str(), GetFileExInfoStandard, &attrs) &&
            CompareFileTime(&attrs.ftLastWriteTime, &last_write) != 0) {
            const bool first = last_write.dwLowDateTime == 0 && last_write.dwHighDateTime == 0;
            last_write = attrs.ftLastWriteTime;
            const int level = IniLevel();
            if (!first && level != g_ini_level.load()) Log("ini Level changed to %d", level);
            g_ini_level.store(level);
        }
        const int effective = EffectiveLevel();
        if (g_shared) g_shared->effective_level = effective;
        if (effective != last_effective) {
            const bool from_server = g_shared && g_shared->level >= 0 && g_shared->level <= 3;
            Log("Level %d (%s)", effective, from_server ? "set by the Server" : "from the ini");
            last_effective = effective;
        }
        const ULONGLONG now = GetTickCount64();
        if (now - last_stats >= (last_draws < 0 ? 20000u : 60000u)) {
            last_stats = now;
            const long draws = g_rope_draws.load();
            if (draws != last_draws) {
                Log("Counters: rope draws %ld (cut %ld), rope index buffers %ld, shaders hashed %ld, "
                    "indexed draws %ld (120-index %ld)", draws, g_rope_draws_cut.load(), g_rope_buffers.load(),
                    g_shaders_hashed.load(), g_indexed_draws.load(), g_draws_120.load());
                last_draws = draws;
            }
        }
    }
}

bool IsFifa16Process() {
    wchar_t path[MAX_PATH] = {};
    const DWORD len = GetModuleFileNameW(nullptr, path, MAX_PATH);
    std::wstring exe(path, len);
    const size_t slash = exe.find_last_of(L"\\/");
    if (slash != std::wstring::npos) exe = exe.substr(slash + 1);
    return _wcsicmp(exe.c_str(), L"fifa16.exe") == 0;
}

void Start() {
    if (!IsFifa16Process()) return;  // the Plugin Loader may run in other processes (ANY_PROCESS=1)
    g_start_tick = GetTickCount64();
    InitCrc32c();
    const std::wstring dir = ModuleDir();
    g_ini_path = dir + L"SERVER16_Ropes.ini";
    g_log_path = dir + L"SERVER16_Ropes.log";
    LoadIni();
    if (g_log_enabled) g_log = _wfopen(g_log_path.c_str(), L"w");

    auto* base = reinterpret_cast<uint8_t*>(GetModuleHandleW(nullptr));
    auto* nt = reinterpret_cast<IMAGE_NT_HEADERS64*>(base + reinterpret_cast<IMAGE_DOS_HEADER*>(base)->e_lfanew);
    Log("SERVER16_Ropes.asi (built " __DATE__ " " __TIME__ "), fifa16.exe in-memory entry point %p",
        static_cast<void*>(base + nt->OptionalHeader.AddressOfEntryPoint));
    Log("ini: Level %d, IndexBufferHash %08x, VertexShaderHash %016llx, PixelShaderHash %016llx, SizeFallback %d",
        g_ini_level.load(), g_ib_hash, g_vs_hash, g_ps_hash, g_size_fallback ? 1 : 0);

    OpenShared();
    const MH_STATUS mh = MH_Initialize();
    g_minhook_ready = mh == MH_OK || mh == MH_ERROR_ALREADY_INITIALIZED;
    Log("MinHook: %s", MH_StatusToString(mh));
    InstallCreateDeviceHooks();
    if (HANDLE thread = CreateThread(nullptr, 0, WatcherThread, nullptr, 0, nullptr)) CloseHandle(thread);
}

}  // namespace

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        g_module = module;
        DisableThreadLibraryCalls(module);
        Start();
    }
    return TRUE;
}
