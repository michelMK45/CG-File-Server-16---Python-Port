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
#include <tlhelp32.h>

#include "cgfs16_rmlui.h"

#pragma comment(lib, "d3d11.lib")
#pragma comment(lib, "dxgi.lib")
#pragma comment(lib, "d3dcompiler.lib")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "ole32.lib")

// ---------------------------------------------------------------------------
// Shared memory (same layout as Python _OverlayShared)
// ---------------------------------------------------------------------------
#define SHMEM_NAME  L"Local\\CGFS16_Overlay_v2"
#define MAX_STR          256
#define MAX_IMG          512
#define MAX_MENU_ITEM_LEN 80
#define MAX_MENU_ITEMS    256
#define MAX_DASH_ITEMS    10
#define MAX_TOASTS        6
#define MAX_ICON          32

struct ToastEntry {
    volatile LONG visible;       // 0 = hidden, 1 = shown
    wchar_t title[MAX_STR];
    wchar_t body[MAX_STR];
    volatile LONG style;         // 0 = info (blue), 1 = warning (amber)
    // Lowercase key naming a file under resources/rmlui/icons/<icon>.png
    // ("tv", "scoreboard", "movie", "goalpost", ...) — empty (the default)
    // or a name with no matching file falls back to the app icon, see
    // ResolveToastIconPath in cgfs16_rmlui.cpp.
    wchar_t icon[MAX_ICON];
};

struct OverlayShared {
    volatile LONG visible;
    volatile LONG progress_x100;
    wchar_t stadium_name[MAX_STR];
    wchar_t detail_text[MAX_STR];
    wchar_t image_path[MAX_IMG];  // path to stadium preview image (PNG/JPG/BMP)
    volatile LONG menu_visible;   // 0 = hidden, 1 = shown
    volatile LONG active_tab;     // controlled by Python app loop for now
    volatile LONG last_input_event;
    volatile LONG reserved0;      // menu viewport width  (runtime telemetry)
        volatile LONG menu_item_count;          // 0..MAX_MENU_ITEMS valid items
        volatile LONG menu_selected_index;      // highlighted row (0-based)
        volatile LONG menu_scroll_offset;       // first visible row
        volatile LONG reserved1;                // menu viewport height (runtime telemetry)
        volatile LONG dashboard_item_count;
        volatile LONG reserved2;                // swapchain output HWND (runtime telemetry)
        wchar_t dashboard_items[MAX_DASH_ITEMS][MAX_MENU_ITEM_LEN];
        wchar_t  menu_items[MAX_MENU_ITEMS][MAX_MENU_ITEM_LEN];
        // Virtual-scroll fields: written by Python, read by C++ for scrollbar.
        volatile LONG menu_total_count;   // real list size (may exceed MAX_MENU_ITEMS)
        volatile LONG menu_window_base;   // real index of menu_items[0]
    // Team crest image paths — written by Python, read by C++ for dashboard render
    wchar_t home_crest_path[MAX_IMG];  // PNG path for home team crest (empty = none)
    wchar_t away_crest_path[MAX_IMG];  // PNG path for away team crest (empty = none)
    wchar_t list_header[MAX_STR];      // wizard step header text shown above list (empty = hidden)
    // Toast notification stack — each slot is independently shown/hidden
    ToastEntry toasts[MAX_TOASTS];
    // Overrides the DrawOverlay11 panel's hardcoded "Loading Stadium" header
    // line — empty (the default) keeps that exact text, so every existing
    // stadium-loading caller needs no changes.
    wchar_t panel_title[MAX_STR];
    // Absolute directory containing the bundled gamepad button icon PNGs
    // (a.png/b.png/dpad.png/lb.png/rb.png/rs.png) — written once by Python
    // after injection, read by C++ to render the gamepad hint bar with real
    // button glyphs instead of text badges.
    wchar_t gamepad_icon_dir[MAX_IMG];
    // Absolute directory containing the bundled keyboard key icon PNGs
    // (up.png/down.png/left.png/right.png/enter.png/esc.png/mouse.png) —
    // written once by Python after injection, read by C++ to render the
    // keyboard hint bar with real key glyphs instead of text badges.
    wchar_t keyboard_icon_dir[MAX_IMG];
    // Absolute directory containing the loose .rml/.rcss documents for the
    // RmlUi-rendered screens (resources/rmlui/ — toast.rml, stadium_panel.rml)
    // — written once by Python after injection, read by cgfs16_rmlui.cpp so
    // those documents can be edited on disk without recompiling this DLL.
    wchar_t rmlui_content_dir[MAX_IMG];
    // DLL -> Python: how many item rows fit in the RmlUi menu's list area at
    // the current viewport size, computed once per frame by
    // cgfs16_rmlui_menu.cpp's RmlMenu_Sync from its own RCSS-derived layout
    // (replaces the old hand-rolled DrawMenuOverlay11/Python
    // _compute_d3d_menu_layout duplication — see CLAUDE.md's Phase 2
    // migration notes).
    volatile LONG menu_visible_rows;
    // Live mouse feed into the RmlUi Context. Written every ~80ms from
    // _sync_d3d_menu_input (same cadence as every other input source in this
    // codebase today), in the same window-coordinate space (0,0 = top-left
    // client area) as menu_visible_rows' viewport telemetry above. left_down
    // is the RAW continuous button state, not an edge/click event — the DLL
    // does its own down/up edge detection each Present call, since Present
    // fires far more often than this field is updated.
    volatile LONG rmlui_menu_mouse_x;
    volatile LONG rmlui_menu_mouse_y;
    volatile LONG rmlui_menu_mouse_left_down;
    // DLL -> Python "last event wins" click/scroll signal, written by
    // cgfs16_rmlui_menu.cpp's MenuEventListener (Click on tabs/rows/
    // scrollbar-track, Drag on the scrollbar thumb) and polled once per
    // ~80ms tick in Python (_handle_rmlui_menu_event). A single slot, not a
    // queue: safe because every payload (a tab index, absolute item index,
    // or absolute scroll target) is fully self-contained, so only the latest
    // matters. Written in kind/index-then-seq order (seq last, via
    // InterlockedIncrement) so a torn read either sees the old or the new
    // event, never a mix — same "write the flag last" principle as `visible`
    // for the stadium-loading panel (see CLAUDE.md), just DLL->Python here.
    volatile LONG menu_event_seq;    // increments on every event; 0 = none yet
    volatile LONG menu_event_kind;   // 0=none, 1=tab_click, 2=item_click, 3=scroll_to, 4=hero_activate, 5=close_click
    volatile LONG menu_event_index;  // tab index / absolute item index / absolute scroll target
    // Phase 3 (visual redesign): per-item row thumbnail image paths, parallel
    // to menu_items[] and windowed identically (same index i belongs to the
    // same logical item, same windowBase applies) — written by Python only
    // when the active tab is Stadiums, left blank (and ignored) otherwise.
    // Unlike image_path (one path, for the currently-selected item's big
    // hero preview), this can have many entries alive on screen at once as
    // the list scrolls, so cgfs16_rmlui_menu.cpp caches these behind a small
    // bounded LRU texture cache rather than the single-slot reload-on-change
    // pattern image_path/home_crest_path/away_crest_path use.
    wchar_t menu_item_thumb_paths[MAX_MENU_ITEMS][MAX_IMG];
    // Which hint bar cgfs16_rmlui_menu.cpp should show: 0 = keyboard/mouse,
    // 1 = gamepad. Written every ~80ms by Python's _sync_d3d_menu_input from
    // whichever device produced input most recently (button/key down or
    // meaningful analog stick movement, mouse move/click) — never both hint
    // rows are shown at once. Defaults to 0 (keyboard/mouse) until the first
    // input is observed.
    volatile LONG input_mode;
    // 1 while Python's _update_menu_content() is (synchronously) computing a
    // new item list for the wizard/tab it just navigated to — e.g. the
    // Stadiums tab's discover_stadium_names() filesystem scan, which can
    // take a moment. Set immediately before that work starts and cleared
    // right after, so cgfs16_rmlui_menu.cpp can show a loading spinner in
    // place of the (stale, about-to-be-replaced) row list for exactly that
    // window — rendering keeps running on FIFA's own Present thread the
    // whole time even though Python's main thread is blocked doing the scan,
    // which is what makes the spinner actually animate instead of freezing.
    volatile LONG menu_loading;
    // Compact scoreboard widget (dashboard, right side, next to the team
    // crests) — "2 x 1" / "23:45", independent of dashboard_items[] (the
    // generic stat-line list) since these render as their own large text
    // beside the crests rather than one more line in that list. Written by
    // Python's set_match_score_time(), read via RmlOverlay_ScoreText()/
    // RmlOverlay_MatchTimeText() below.
    wchar_t score_text[MAX_STR];
    wchar_t match_time_text[MAX_STR];
    // 1 while the keyboard/gamepad "activate" input (Enter / A) is
    // currently held — drives #hero-btn.hero-pressed's press-shrink in
    // menu.rml for those two input methods, which (unlike a real mouse
    // click) never touch RmlUi's own :active pseudo-class. Written by
    // Python's set_menu_activate_down(), read via
    // RmlOverlay_MenuActivateDown() below.
    volatile LONG menu_activate_down;
    // 1 while the F12 overlay should show the "Filter" button beside the
    // wizard-header band (Stadiums tab only) — clickable with the mouse AND
    // shows the Y glyph in gamepad mode. Python computes the gating
    // condition (Stadiums tab, past the scope step, not mid-wizard) and
    // just tells the DLL yes/no — see set_stadium_filter_hint_visible() /
    // RmlOverlay_StadiumFilterHintVisible().
    volatile LONG stadium_filter_hint_visible;
    // 1 while the Stadiums country-filter bubble (opened by the Filter
    // button / gamepad Y) is open — tells cgfs16_rmlui_menu.cpp to render
    // #list-area as a small bordered popover anchored under the wizard-
    // header instead of the normal full-height list. See
    // set_stadium_filter_panel_open() / RmlOverlay_StadiumFilterPanelOpen().
    volatile LONG stadium_filter_panel_open;
    // Parallel to menu_items[]/menu_item_thumb_paths[], windowed identically
    // — 1 marks a row as "checked" (lit up via .row-checked) rather than
    // encoding that into the row's own text. Only meaningful while the
    // Stadiums filter bubble is open; left all-zero otherwise. See
    // set_menu_content()'s checked parameter /
    // RmlOverlay_MenuItemChecked().
    volatile LONG menu_item_checked[MAX_MENU_ITEMS];
    // DLL -> Python: real number of columns the Stadiums country-filter grid
    // is actually rendering this frame, computed by RmlMenu_Sync from the
    // same box-model math (item width + column-gap) that #list-area.bubble's
    // RCSS uses. A previous version of this feature hardcoded the column
    // count (7) identically on both sides — worked only by coincidence at
    // whatever panel width it was tuned against; at any other width RmlUi's
    // flex-wrap actually fit a different number of columns per line, so a
    // full-row Up/Down step (a fixed multiple of the hardcoded count) landed
    // in the wrong column — the highlighted cell visibly walked diagonally.
    // Sending the real, current count back removes the need for either side
    // to guess. Only meaningful while stadium_filter_panel_open is set.
    volatile LONG menu_filter_grid_cols;
    // Kit-cycling carousel notification (F7-F10) — a fully independent
    // panel/doc from the stadium-loading one above (own visible flag), unlike
    // the old approach of reusing `visible`/`image_path`/etc. for it, which
    // meant a kit-cycle notification had to be skipped outright whenever a
    // stadium load happened to be in progress. See kit_carousel.rml /
    // SyncKitCarousel in cgfs16_rmlui.cpp.
    volatile LONG kit_carousel_visible;
    wchar_t kit_carousel_title[MAX_STR];   // e.g. "Home: Real Madrid"
    wchar_t kit_carousel_detail[MAX_STR];  // e.g. "Kit: 42" / "Default kit"
    wchar_t kit_carousel_hint[MAX_STR];    // localized control legend
    wchar_t kit_carousel_image_prev[MAX_IMG];
    wchar_t kit_carousel_image_current[MAX_IMG];
    wchar_t kit_carousel_image_next[MAX_IMG];
    // "Last event wins" signal for a genuine F7-F10 cycle step (same shape as
    // menu_event_seq above) — incremented by show_kit_carousel() every time,
    // never touched by update_kit_carousel_images()'s background-prefetch
    // pop-ins. SyncKitCarousel diffs this against the last seq it saw to
    // decide whether THIS frame's slot content changes should slide in
    // (a real cycle, direction -1/+1) or just crossfade in place (a
    // prefetched thumbnail arriving late).
    volatile LONG kit_carousel_cycle_seq;
    volatile LONG kit_carousel_direction;
};

static HANDLE        g_hMap  = NULL;
static OverlayShared *g_data = NULL;

// ---------------------------------------------------------------------------
// Narrow accessors into OverlayShared for cgfs16_rmlui.cpp (the toast +
// stadium-loading-panel RmlUi renderer, Phase 1 of the migration) — kept as
// plain scalar/pointer getters rather than sharing OverlayShared's full type
// across the translation-unit boundary, so that file never has to duplicate
// (and risk drifting out of sync with) this struct's layout.
// ---------------------------------------------------------------------------
bool RmlOverlay_ToastVisible(int slot) {
    return g_data && slot >= 0 && slot < MAX_TOASTS &&
           InterlockedCompareExchange(&g_data->toasts[slot].visible, 0, 0) != 0;
}
bool RmlOverlay_ToastWarning(int slot) {
    return g_data && slot >= 0 && slot < MAX_TOASTS &&
           InterlockedCompareExchange(&g_data->toasts[slot].style, 0, 0) != 0;
}
const wchar_t *RmlOverlay_ToastTitle(int slot) {
    return (g_data && slot >= 0 && slot < MAX_TOASTS) ? g_data->toasts[slot].title : L"";
}
const wchar_t *RmlOverlay_ToastBody(int slot) {
    return (g_data && slot >= 0 && slot < MAX_TOASTS) ? g_data->toasts[slot].body : L"";
}
const wchar_t *RmlOverlay_ToastIcon(int slot) {
    return (g_data && slot >= 0 && slot < MAX_TOASTS) ? g_data->toasts[slot].icon : L"";
}
bool RmlOverlay_StadiumPanelVisible() {
    return g_data && InterlockedCompareExchange(&g_data->visible, 0, 0) != 0;
}
int RmlOverlay_ProgressX100() {
    return g_data ? (int)InterlockedCompareExchange(&g_data->progress_x100, 0, 0) : 0;
}
const wchar_t *RmlOverlay_StadiumName() { return g_data ? g_data->stadium_name : L""; }
const wchar_t *RmlOverlay_DetailText()  { return g_data ? g_data->detail_text  : L""; }
const wchar_t *RmlOverlay_ImagePath()   { return g_data ? g_data->image_path   : L""; }
const wchar_t *RmlOverlay_PanelTitle()  { return g_data ? g_data->panel_title  : L""; }
const wchar_t *RmlOverlay_ContentDir()  { return g_data ? g_data->rmlui_content_dir : L""; }
bool RmlOverlay_KitCarouselVisible() {
    return g_data && InterlockedCompareExchange(&g_data->kit_carousel_visible, 0, 0) != 0;
}
const wchar_t *RmlOverlay_KitCarouselTitle()   { return g_data ? g_data->kit_carousel_title   : L""; }
const wchar_t *RmlOverlay_KitCarouselDetail()  { return g_data ? g_data->kit_carousel_detail  : L""; }
const wchar_t *RmlOverlay_KitCarouselHint()    { return g_data ? g_data->kit_carousel_hint    : L""; }
const wchar_t *RmlOverlay_KitCarouselImagePrev()    { return g_data ? g_data->kit_carousel_image_prev    : L""; }
const wchar_t *RmlOverlay_KitCarouselImageCurrent() { return g_data ? g_data->kit_carousel_image_current : L""; }
const wchar_t *RmlOverlay_KitCarouselImageNext()    { return g_data ? g_data->kit_carousel_image_next    : L""; }
int RmlOverlay_KitCarouselCycleSeq() {
    return g_data ? (int)InterlockedCompareExchange(&g_data->kit_carousel_cycle_seq, 0, 0) : 0;
}
int RmlOverlay_KitCarouselDirection() {
    return g_data ? (int)InterlockedCompareExchange(&g_data->kit_carousel_direction, 0, 0) : 0;
}

// ---------------------------------------------------------------------------
// Narrow accessors for cgfs16_rmlui_menu.cpp (Phase 2 of the migration — the
// real F12 menu). Same rationale as the accessors above: no shared struct
// type across the translation-unit boundary. MAX_MENU_ITEMS/MAX_MENU_ITEM_LEN/
// MAX_DASH_ITEMS/NUM_MENU_TABS must match the same constants here and in
// d3d_injector.py.
// ---------------------------------------------------------------------------
// The F12 menu's visibility — the single source of truth for whether the
// RmlUi menu document (cgfs16_rmlui_menu.cpp) should be showing and
// processing input, now that it's the only menu renderer (Phase 2 cutover).
bool RmlOverlay_MenuVisible() {
    return g_data && InterlockedCompareExchange(&g_data->menu_visible, 0, 0) != 0;
}
// DLL -> Python: written by RmlMenu_Sync once per frame from its own
// RCSS-derived layout math; read by d3d_injector.py's get_menu_metrics().
void RmlOverlay_SetMenuVisibleRows(int rows) {
    if (g_data) InterlockedExchange(&g_data->menu_visible_rows, (LONG)rows);
}
// DLL -> Python: real column count of the Stadiums filter grid this frame —
// see menu_filter_grid_cols' field comment. Read by
// d3d_injector.py's get_filter_grid_cols().
void RmlOverlay_SetMenuFilterGridCols(int cols) {
    if (g_data) InterlockedExchange(&g_data->menu_filter_grid_cols, (LONG)cols);
}
// DLL -> Python: swapchain output viewport width/height/HWND, written by
// RmlMenu_Sync whenever the menu is visible. Formerly written directly by
// DrawMenuOverlay11 (now removed); reads (get_menu_metrics()) are unchanged
// — mouse coordinate transforms and menu-window focus detection both depend
// on this. reserved0/1/2 are pre-existing field names (see OverlayShared);
// kept as-is rather than renamed, to avoid an unrelated wire-format churn.
void RmlOverlay_SetMenuViewportTelemetry(int vpW, int vpH, void *outputWindow) {
    if (!g_data) return;
    InterlockedExchange(&g_data->reserved0, (LONG)vpW);
    InterlockedExchange(&g_data->reserved1, (LONG)vpH);
    InterlockedExchange(&g_data->reserved2, (LONG)(LONG_PTR)outputWindow);
}
LONG RmlOverlay_ActiveTab() {
    return g_data ? InterlockedCompareExchange(&g_data->active_tab, 0, 0) : 0;
}
LONG RmlOverlay_MenuItemCount() {
    return g_data ? InterlockedCompareExchange(&g_data->menu_item_count, 0, 0) : 0;
}
LONG RmlOverlay_MenuSelectedIndex() {
    return g_data ? InterlockedCompareExchange(&g_data->menu_selected_index, 0, 0) : 0;
}
LONG RmlOverlay_MenuScrollOffset() {
    return g_data ? InterlockedCompareExchange(&g_data->menu_scroll_offset, 0, 0) : 0;
}
LONG RmlOverlay_MenuTotalCount() {
    return g_data ? InterlockedCompareExchange(&g_data->menu_total_count, 0, 0) : 0;
}
LONG RmlOverlay_MenuWindowBase() {
    return g_data ? InterlockedCompareExchange(&g_data->menu_window_base, 0, 0) : 0;
}
const wchar_t *RmlOverlay_MenuItemText(int index) {
    return (g_data && index >= 0 && index < MAX_MENU_ITEMS) ? g_data->menu_items[index] : L"";
}
// Phase 3: per-item row thumbnail path (see the OverlayShared field comment
// on menu_item_thumb_paths) — empty string means "no thumbnail for this row",
// which the renderer treats identically to "not loaded yet".
const wchar_t *RmlOverlay_MenuItemThumbPath(int index) {
    return (g_data && index >= 0 && index < MAX_MENU_ITEMS) ? g_data->menu_item_thumb_paths[index] : L"";
}
LONG RmlOverlay_DashboardItemCount() {
    return g_data ? InterlockedCompareExchange(&g_data->dashboard_item_count, 0, 0) : 0;
}
const wchar_t *RmlOverlay_DashboardItemText(int index) {
    return (g_data && index >= 0 && index < MAX_DASH_ITEMS) ? g_data->dashboard_items[index] : L"";
}
const wchar_t *RmlOverlay_HomeCrestPath()   { return g_data ? g_data->home_crest_path   : L""; }
const wchar_t *RmlOverlay_AwayCrestPath()   { return g_data ? g_data->away_crest_path   : L""; }
const wchar_t *RmlOverlay_ScoreText()       { return g_data ? g_data->score_text        : L""; }
const wchar_t *RmlOverlay_MatchTimeText()   { return g_data ? g_data->match_time_text   : L""; }
const wchar_t *RmlOverlay_ListHeader()      { return g_data ? g_data->list_header       : L""; }
const wchar_t *RmlOverlay_GamepadIconDir()  { return g_data ? g_data->gamepad_icon_dir  : L""; }
const wchar_t *RmlOverlay_KeyboardIconDir() { return g_data ? g_data->keyboard_icon_dir : L""; }
// Phase 2 Step 3: raw mouse feed (Python writes every ~80ms; the reader does
// its own down/up edge detection each Present call — see the field comments
// on OverlayShared above).
LONG RmlOverlay_MenuMouseX() { return g_data ? InterlockedCompareExchange(&g_data->rmlui_menu_mouse_x, 0, 0) : 0; }
LONG RmlOverlay_MenuMouseY() { return g_data ? InterlockedCompareExchange(&g_data->rmlui_menu_mouse_y, 0, 0) : 0; }
bool RmlOverlay_MenuMouseLeftDown() {
    return g_data && InterlockedCompareExchange(&g_data->rmlui_menu_mouse_left_down, 0, 0) != 0;
}
// Phase 2 Step 4: writer for the "last event wins" click/scroll signal (see
// the OverlayShared field comments for the kind/index-then-seq write order).
void RmlOverlay_PushMenuEvent(int kind, int index) {
    if (!g_data) return;
    InterlockedExchange(&g_data->menu_event_kind, (LONG)kind);
    InterlockedExchange(&g_data->menu_event_index, (LONG)index);
    InterlockedIncrement(&g_data->menu_event_seq);
}
// Which hint bar to show — see the OverlayShared::input_mode field comment.
LONG RmlOverlay_InputMode() {
    return g_data ? InterlockedCompareExchange(&g_data->input_mode, 0, 0) : 0;
}
// See the OverlayShared::menu_loading field comment.
bool RmlOverlay_MenuLoading() {
    return g_data && InterlockedCompareExchange(&g_data->menu_loading, 0, 0) != 0;
}
// See the OverlayShared::menu_activate_down field comment.
bool RmlOverlay_MenuActivateDown() {
    return g_data && InterlockedCompareExchange(&g_data->menu_activate_down, 0, 0) != 0;
}
// See the OverlayShared::stadium_filter_hint_visible field comment.
bool RmlOverlay_StadiumFilterHintVisible() {
    return g_data && InterlockedCompareExchange(&g_data->stadium_filter_hint_visible, 0, 0) != 0;
}
// See the OverlayShared::stadium_filter_panel_open field comment.
bool RmlOverlay_StadiumFilterPanelOpen() {
    return g_data && InterlockedCompareExchange(&g_data->stadium_filter_panel_open, 0, 0) != 0;
}
// See the OverlayShared::menu_item_checked field comment.
bool RmlOverlay_MenuItemChecked(int index) {
    if (!g_data || index < 0 || index >= MAX_MENU_ITEMS) return false;
    return InterlockedCompareExchange(&g_data->menu_item_checked[index], 0, 0) != 0;
}
static HMODULE       g_selfModule = NULL;
static volatile LONG g_unloading = 0;

// XInput hook removed — inline hooking XInputGetState is unsafe with DLL thunks.
// Gamepad suppression while the overlay menu is open is handled by the Python host
// which polls XInput directly and owns the input dispatch loop.

// Forward declaration. Not static: cgfs16_rmlui.cpp (RmlUi renderer, its own
// translation unit) calls this too, so both share the one log file.
void Log(const char *fmt, ...);

// TryInstallXInputHook removed — see comment above.


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
void Log(const char *fmt, ...) {
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
// Strategy (vtable-only, ReShade-safe):
//   HookThread creates a temporary D3D11 device+swapchain to read vtable[8]
//   (IDXGISwapChain::Present) and installs a vtable hook there.
//   On the first HookedPresent call we also patch FIFA's real swapchain vtable
//   if it differs from the temporary one.
//   We NEVER write inline bytes to the Present function body, so we cannot
//   conflict with ReShade (or any other injected DLL) that also hooks Present.
// ---------------------------------------------------------------------------
typedef HRESULT (WINAPI *PFN_Present)(IDXGISwapChain*, UINT, UINT);

static PFN_Present g_OrigPresent         = nullptr;  // original vtable[8] before our hook

static void      **g_tmpVtbl             = nullptr;  // vtable of the probe swapchain
static void      **g_fifaVtbl            = nullptr;  // FIFA's swapchain vtable (may differ)
static bool        g_hookSwitched        = false;    // set after first real-sc patch

static CRITICAL_SECTION g_drawCs;
static LONG g_frameCount = 0;

// ---------------------------------------------------------------------------
// WIC -> D3D11 texture (generic, reused for preview and team crests).
// Releases *outTex/*outSRV before loading. outW/outH are optional. Shared
// across translation units: called from cgfs16_rmlui.cpp's RenderInterface
// (Phase 1+ of the RmlUi migration) — that's the only remaining caller now
// that the hand-rolled DrawMenuOverlay11/DrawToast11/DrawOverlay11 renderers
// (former callers) have all been removed.
//
// premultiplyAlpha: RmlUi's RenderInterface (cgfs16_rmlui.cpp) uses
// premultiplied-alpha blending — RmlUi's own generated content (glyph
// atlases) already comes out premultiplied, but WIC-decoded PNGs do not, so
// any semi-transparent pixel (most icon-style PNGs have anti-aliased edges)
// would composite with a visible bright fringe if handed to that pipeline
// unmultiplied. Pass true only from that RenderInterface's LoadTexture.
// ---------------------------------------------------------------------------
bool LoadWICTexture(ID3D11Device *dev, const wchar_t *path,
    ID3D11Texture2D **outTex, ID3D11ShaderResourceView **outSRV,
    int *outW = nullptr, int *outH = nullptr, bool premultiplyAlpha = false)
{
    if (*outTex) { (*outTex)->Release(); *outTex = nullptr; }
    if (*outSRV) { (*outSRV)->Release(); *outSRV = nullptr; }
    if (outW) *outW = 0;
    if (outH) *outH = 0;

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

    if (premultiplyAlpha) {
        BYTE *px = pixels.data();
        for (size_t i = 0, n = (size_t)w * h; i < n; i++) {
            BYTE a = px[3];
            px[0] = (BYTE)((int)px[0] * a / 255);
            px[1] = (BYTE)((int)px[1] * a / 255);
            px[2] = (BYTE)((int)px[2] * a / 255);
            px += 4;
        }
    }

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

    hr = dev->CreateTexture2D(&td, &srd, outTex);
    if (FAILED(hr)) { Log("[WIC] CreateTexture2D hr=0x%08X", (unsigned)hr); return false; }
    dev->CreateShaderResourceView(*outTex, nullptr, outSRV);
    if (outW) *outW = (int)w;
    if (outH) *outH = (int)h;
    Log("[WIC] loaded '%ls' %dx%d", path, w, h);
    return true;
}

// ---------------------------------------------------------------------------
// DrawMenuOverlay11 (the last hand-rolled D3D11 screen — tab bar, dashboard,
// item list, scrollbar, split-preview, hint bars) removed at Phase 2 cutover
// — replaced entirely by RmlOverlay_RenderFrame / cgfs16_rmlui_menu.cpp's
// RmlMenu_Sync (see CLAUDE.md's migration notes). Its one non-drawing side
// effect (writing reserved0/1/2 viewport telemetry) moved to
// RmlOverlay_SetMenuViewportTelemetry, called from RmlMenu_Sync.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// DrawToast11 / DrawOverlay11 (toast notifications, stadium-loading panel)
// removed — replaced by RmlOverlay_RenderFrame in cgfs16_rmlui.cpp (Phase 1
// of the RmlUi migration). See the plan at
// C:\Users\Miguel\.claude\plans\lazy-tumbling-balloon.md.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// XInput suppression — forward declarations (defined after HookThread helpers)
// ---------------------------------------------------------------------------
typedef void (WINAPI *PFN_XInputEnable_t)(BOOL);
static PFN_XInputEnable_t g_XInputEnable      = nullptr;
static LONG               g_menuWasSuppressed = 0;
static void InitXInputEnable();

// ---------------------------------------------------------------------------
// Hooked IDXGISwapChain::Present
// ---------------------------------------------------------------------------
static HRESULT WINAPI HookedPresent(IDXGISwapChain *sc, UINT syncInterval, UINT flags) {
    if (InterlockedCompareExchange(&g_unloading, 0, 0) != 0)
        return g_OrigPresent ? g_OrigPresent(sc, syncInterval, flags) : S_OK;

    // If FIFA's real swapchain differs from our probe swapchain, patch its vtable too.
    if (!g_hookSwitched) {
        g_hookSwitched = true;
        void **scVtbl = *reinterpret_cast<void***>(sc);
        if (scVtbl != g_tmpVtbl) {
            g_fifaVtbl = scVtbl;
            DWORD old = 0;
            if (VirtualProtect(&g_fifaVtbl[8], sizeof(void*), PAGE_EXECUTE_READWRITE, &old)) {
                g_fifaVtbl[8] = reinterpret_cast<void*>(HookedPresent);
                VirtualProtect(&g_fifaVtbl[8], sizeof(void*), old, &old);
            }
            Log("[Present] patched FIFA vtable sc=%p vtbl=%p origFn=%p",
                sc, g_fifaVtbl, g_OrigPresent);
        } else {
            g_fifaVtbl = g_tmpVtbl;
            Log("[Present] FIFA uses same vtable as probe sc=%p", sc);
        }
    }

    LONG n = InterlockedIncrement(&g_frameCount);
    if (n==1 || (n%600)==0)
        Log("[Present] frame=%ld visible=%d menu=%d", n,
            g_data?(int)g_data->visible:-1,
            g_data?(int)g_data->menu_visible:-1);

    // Suppress / restore gamepad input for FIFA when the overlay menu opens or closes.
    // XInputEnable(FALSE) sets a flag inside xinput*.dll that makes all XInputGetState
    // calls in this process return zero — covers IAT, cached GetProcAddress, and any
    // other call path.  Python runs in a separate process and is unaffected.
    if (!g_XInputEnable) InitXInputEnable();
    if (g_XInputEnable && g_data) {
        LONG menuVis = InterlockedCompareExchange(&g_data->menu_visible, 0, 0) ? 1 : 0;
        if (InterlockedExchange(&g_menuWasSuppressed, menuVis) != menuVis) {
            g_XInputEnable(menuVis == 0 ? TRUE : FALSE);
            Log("[XInput] XInputEnable(%s) menu_visible=%d", menuVis ? "FALSE" : "TRUE", menuVis);
        }
    }

    EnterCriticalSection(&g_drawCs);
    HRESULT presentResult = S_OK;
    __try {
        // Menu, stadium-loading panel, and toasts are all RmlUi-rendered now
        // (DrawMenuOverlay11 — the last hand-rolled D3D11 screen — was
        // deleted at Phase 2 cutover; see CLAUDE.md's migration notes). One
        // call drives all three, since they share a single Rml::Context; it
        // no-ops immediately if none is currently visible.
        {
            ID3D11Device *dev = nullptr;
            if (SUCCEEDED(sc->GetDevice(__uuidof(ID3D11Device), (void**)&dev))) {
                ID3D11DeviceContext *ctx = nullptr;
                dev->GetImmediateContext(&ctx);
                RmlOverlay_RenderFrame(sc, dev, ctx);
                ctx->Release(); dev->Release();
            }
        }
        // Call original Present inside the SEH guard so any AV in the
        // chain below is caught and logged rather than crashing silently.
        presentResult = g_OrigPresent(sc, syncInterval, flags);
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        Log("[Present] EXCEPTION (code=0x%08lX)", GetExceptionCode());
        presentResult = DXGI_ERROR_DRIVER_INTERNAL_ERROR;
    }
    LeaveCriticalSection(&g_drawCs);
    return presentResult;
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
// XInput IAT hook — zeroes gamepad state for FIFA while the overlay menu is open.
//
// Strategy: scan the IAT of EVERY loaded module (main EXE + all DLLs) and
// replace every XInputGetState pointer with our hook.  This covers both
// static-link imports and DLLs that statically import XInput on FIFA's behalf.
// Each replacement is a single aligned pointer write — atomic on x64, no
// trampoline, no inline-byte patching, no crash risk.
// Struct defined inline so xinput.h / xinput.lib are not required.
// ---------------------------------------------------------------------------
struct CGFS_XINPUT_GAMEPAD {
    WORD  wButtons;
    BYTE  bLeftTrigger, bRightTrigger;
    SHORT sThumbLX, sThumbLY, sThumbRX, sThumbRY;
};
struct CGFS_XINPUT_STATE {
    DWORD dwPacketNumber;
    CGFS_XINPUT_GAMEPAD Gamepad;
};
typedef DWORD (WINAPI *PFN_XInputGetState_t)(DWORD, CGFS_XINPUT_STATE*);
static PFN_XInputGetState_t g_origXInputGetState = nullptr;

static DWORD WINAPI HookedXInputGetState(DWORD idx, CGFS_XINPUT_STATE *pState) {
    DWORD r = g_origXInputGetState(idx, pState);
    // While the overlay menu is open, zero all buttons/axes so FIFA doesn't
    // see the same inputs the user sends to the overlay.
    // dwPacketNumber is left intact so the game still sees a live controller.
    if (r == 0 && pState && g_data &&
        InterlockedCompareExchange(&g_data->menu_visible, 0, 0) != 0)
        pState->Gamepad = {};
    return r;
}

static void TryInstallXInputIATHook() {
    // Enumerate every module currently loaded in this process and patch any
    // IAT entry that imports XInputGetState from an xinput*.dll.
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, GetCurrentProcessId());
    if (snap == INVALID_HANDLE_VALUE) {
        Log("[XInput] CreateToolhelp32Snapshot failed err=%lu", GetLastError());
        return;
    }
    int patches = 0;
    MODULEENTRY32 me = { sizeof(me) };
    if (Module32First(snap, &me)) {
        do {
            HMODULE hMod = me.hModule;
            __try {
                auto *dos = reinterpret_cast<IMAGE_DOS_HEADER*>(hMod);
                if (dos->e_magic != IMAGE_DOS_SIGNATURE) continue;
                auto *nt = reinterpret_cast<IMAGE_NT_HEADERS*>((BYTE*)hMod + dos->e_lfanew);
                auto &imp = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
                if (!imp.VirtualAddress) continue;
                auto *desc = reinterpret_cast<IMAGE_IMPORT_DESCRIPTOR*>((BYTE*)hMod + imp.VirtualAddress);
                for (; desc->Name; ++desc) {
                    const char *dn = reinterpret_cast<const char*>((BYTE*)hMod + desc->Name);
                    if (_strnicmp(dn, "xinput", 6) != 0) continue;
                    if (!desc->OriginalFirstThunk) continue;
                    auto *orig = reinterpret_cast<IMAGE_THUNK_DATA*>((BYTE*)hMod + desc->OriginalFirstThunk);
                    auto *iat  = reinterpret_cast<IMAGE_THUNK_DATA*>((BYTE*)hMod + desc->FirstThunk);
                    for (; orig->u1.AddressOfData; ++orig, ++iat) {
                        if (IMAGE_SNAP_BY_ORDINAL(orig->u1.Ordinal)) continue;
                        auto *ibn = reinterpret_cast<IMAGE_IMPORT_BY_NAME*>((BYTE*)hMod + orig->u1.AddressOfData);
                        if (strcmp(ibn->Name, "XInputGetState") != 0) continue;
                        auto existing = reinterpret_cast<PFN_XInputGetState_t>(iat->u1.Function);
                        if (existing == HookedXInputGetState) continue; // already patched
                        if (!g_origXInputGetState) g_origXInputGetState = existing;
                        DWORD old = 0;
                        if (VirtualProtect(&iat->u1.Function, sizeof(void*), PAGE_EXECUTE_READWRITE, &old)) {
                            iat->u1.Function = reinterpret_cast<ULONG_PTR>(HookedXInputGetState);
                            VirtualProtect(&iat->u1.Function, sizeof(void*), old, &old);
                            ++patches;
                            Log("[XInput] patched %s in module %s", dn, me.szModule);
                        }
                    }
                }
            } __except (EXCEPTION_EXECUTE_HANDLER) {
                // Skip modules whose PE headers are not readable
            }
        } while (Module32Next(snap, &me));
    }
    CloseHandle(snap);
    if (patches > 0)
        Log("[XInput] %d XInputGetState IAT patch(es) installed", patches);
    else
        Log("[XInput] XInputGetState not found in any module IAT");
}

// XInputEnable(FALSE/TRUE) — process-wide XInput suppression.
// Works regardless of how FIFA loaded XInput (IAT, GetProcAddress cache, etc.)
// because the flag lives inside xinput*.dll and is checked by every XInputGetState call.
static void InitXInputEnable() {
    static const char * const kNames[] = {
        "xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll", nullptr
    };
    for (int i = 0; kNames[i]; ++i) {
        HMODULE h = GetModuleHandleA(kNames[i]);
        if (!h) continue;
        auto fn = reinterpret_cast<PFN_XInputEnable_t>(GetProcAddress(h, "XInputEnable"));
        if (!fn) continue;
        g_XInputEnable = fn;
        Log("[XInput] XInputEnable found in %s at %p", kNames[i], fn);
        return;
    }
}

// ---------------------------------------------------------------------------
// Hook setup: temp D3D11 device+swapchain -> vtable hook (NO inline bytes)
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

    // Install vtable hook on the probe swapchain — no inline byte patching.
    // This is safe with ReShade and any other injected hook because we never
    // overwrite function body bytes that another hook may have already patched.
    void **vt = *reinterpret_cast<void***>(tmpSC);
    g_tmpVtbl = vt;

    // Log where Present lives (for diagnostics)
    uint8_t *presentAddr = reinterpret_cast<uint8_t*>(vt[8]);
    MEMORY_BASIC_INFORMATION mbi={};
    VirtualQuery(presentAddr,&mbi,sizeof(mbi));
    char modPath[MAX_PATH]="(unknown)";
    GetModuleFileNameA((HMODULE)mbi.AllocationBase,modPath,MAX_PATH);
    Log("[HookThread] SwapChain::Present at %p in %s", presentAddr, modPath);

    // Save original vtable[8] then replace with our hook
    g_OrigPresent = reinterpret_cast<PFN_Present>(vt[8]);
    DWORD old = 0;
    if (VirtualProtect(&vt[8], sizeof(void*), PAGE_EXECUTE_READWRITE, &old)) {
        vt[8] = reinterpret_cast<void*>(HookedPresent);
        VirtualProtect(&vt[8], sizeof(void*), old, &old);
        Log("[HookThread] vtable hook installed on probe sc=%p vt=%p origFn=%p",
            tmpSC, vt, g_OrigPresent);
    } else {
        Log("[HookThread] VirtualProtect vtable failed err=%lu", GetLastError());
        g_OrigPresent = nullptr;
    }

    // Keep probe SC alive until FIFA's first Present (then g_hookSwitched handles the rest).
    // Release device; the SC holds its own ref on the device internally.
    tmpSC->Release(); if (tmpDev) tmpDev->Release();
    DestroyWindow(hw); UnregisterClassW(wc.lpszClassName,wc.hInstance);

    // Patch FIFA's XInputGetState IAT entry so gamepad input is suppressed
    // while the overlay menu is open.  Must run after FIFA has finished
    // loading its import table, hence inside HookThread (500 ms after attach).
    TryInstallXInputIATHook();

    Log("[HookThread] done");
    return 0;
}

// ---------------------------------------------------------------------------
// DllMain
// ---------------------------------------------------------------------------
BOOL WINAPI DllMain(HINSTANCE hInst, DWORD reason, LPVOID reserved) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hInst);
        InitializeCriticalSection(&g_drawCs);
        InterlockedExchange(&g_unloading, 0);
        InitLog();
        Log("[DllMain] ATTACH pid=%lu", GetCurrentProcessId());

        HMODULE selfModule = NULL;
        if (GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                               GET_MODULE_HANDLE_EX_FLAG_PIN,
                               reinterpret_cast<LPCWSTR>(&DllMain),
                               &selfModule)) {
            g_selfModule = selfModule;
            Log("[DllMain] module pinned hmod=%p", g_selfModule);
        } else {
            Log("[DllMain] module pin failed err=%lu", GetLastError());
        }

        g_hMap=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,
            PAGE_READWRITE,0,sizeof(OverlayShared),SHMEM_NAME);
        DWORD shmemErr=GetLastError();
        if (g_hMap) {
            g_data=reinterpret_cast<OverlayShared*>(
                MapViewOfFile(g_hMap,FILE_MAP_ALL_ACCESS,0,0,sizeof(OverlayShared)));
            if (!g_data)
                Log("[DllMain] MapViewOfFile failed err=%lu (shmem size mismatch? expected %zu bytes)",
                    GetLastError(), sizeof(OverlayShared));
        } else {
            Log("[DllMain] CreateFileMappingW failed err=%lu", shmemErr);
        }
        Log("[DllMain] shmem hMap=%p data=%p visible=%d (struct=%zu bytes)",
            g_hMap,g_data,g_data?(int)g_data->visible:-1, sizeof(OverlayShared));

        HANDLE ht=CreateThread(nullptr,0,HookThread,nullptr,0,nullptr);
        if (ht) CloseHandle(ht);

    } else if (reason==DLL_PROCESS_DETACH) {
        Log("[DllMain] DETACH reserved=%p", reserved);
        InterlockedExchange(&g_unloading, 1);
        // Do NOT restore hooks during DETACH — game threads may still be
        // executing through them, causing a race condition crash. The process
        // is dying; the OS will reclaim all memory and handles automatically.
        // Null g_data first so any concurrent HookedPresent/HookedXInput call
        // becomes a safe no-op.
        g_data = nullptr;
    }
    return TRUE;
}
