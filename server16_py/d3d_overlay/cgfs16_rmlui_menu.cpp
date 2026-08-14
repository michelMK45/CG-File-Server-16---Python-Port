// cgfs16_rmlui_menu.cpp
// -----------------------
// The real, interactive F12 menu (tabs, dashboard, item list, wizard header,
// scrollbar, split-preview, hint bars) — Phase 2 of the RmlUi migration,
// replacing the former hand-rolled DrawMenuOverlay11 in cgfs16_overlay.cpp
// (deleted at cutover). See CLAUDE.md's migration notes / the "Phase 2"
// section of C:\Users\Miguel\.claude\plans\lazy-tumbling-balloon.md for the
// full history (the migration went through a static-shell-only pass behind
// a temporary F6 dev-preview toggle, then live mouse feed, then click/drag
// event reporting, before this file became the sole menu renderer).
//
// This file's layout math is the authoritative source for menu_visible_rows
// and the viewport telemetry (reserved0/1/2, see
// RmlOverlay_SetMenuViewportTelemetry) — both formerly derived independently
// by DrawMenuOverlay11 in C++ and _compute_d3d_menu_layout in Python; the
// Python copy is gone, this is now the only place that geometry is computed.
#include "cgfs16_rmlui_menu.h"

#include <windows.h>
#include <cstdio>
#include <cstring>
#include <string>
#include <algorithm>
#include <cmath>

// Shared with cgfs16_overlay.cpp / cgfs16_rmlui.cpp (same %TEMP%\cgfs16_overlay.log).
void Log(const char *fmt, ...);

// Narrow accessors into OverlayShared, defined in cgfs16_overlay.cpp — see
// the comment above their definitions there for why this file doesn't share
// OverlayShared's struct layout directly. Must match the real field sizes in
// cgfs16_overlay.cpp / d3d_injector.py exactly.
bool RmlOverlay_MenuVisible();
void RmlOverlay_SetMenuVisibleRows(int rows);
void RmlOverlay_SetMenuViewportTelemetry(int vpW, int vpH, void *outputWindow);
long RmlOverlay_ActiveTab();
long RmlOverlay_MenuItemCount();
long RmlOverlay_MenuSelectedIndex();
long RmlOverlay_MenuScrollOffset();
long RmlOverlay_MenuTotalCount();
long RmlOverlay_MenuWindowBase();
const wchar_t *RmlOverlay_MenuItemText(int index);
const wchar_t *RmlOverlay_MenuItemThumbPath(int index);
long RmlOverlay_DashboardItemCount();
const wchar_t *RmlOverlay_DashboardItemText(int index);
const wchar_t *RmlOverlay_HomeCrestPath();
const wchar_t *RmlOverlay_AwayCrestPath();
const wchar_t *RmlOverlay_ScoreText();
const wchar_t *RmlOverlay_MatchTimeText();
const wchar_t *RmlOverlay_ListHeader();
const wchar_t *RmlOverlay_ImagePath();
const wchar_t *RmlOverlay_GamepadIconDir();
const wchar_t *RmlOverlay_KeyboardIconDir();
long RmlOverlay_MenuMouseX();
long RmlOverlay_MenuMouseY();
bool RmlOverlay_MenuMouseLeftDown();
void RmlOverlay_PushMenuEvent(int kind, int index);
long RmlOverlay_InputMode();
bool RmlOverlay_MenuLoading();
bool RmlOverlay_MenuActivateDown();

#define MAX_MENU_ITEMS    256
#define MAX_DASH_ITEMS    10
#define NUM_MENU_TABS     5
#define MAX_IMG           512
#define ROW_POOL          64
// Navigate/Scroll/Close only — Select (A/Enter) and Tab (LB+RB / Left+Right)
// moved out of the bottom hint bar into contextual spots (hero button /
// selected-or-hovered row, and beside the tab strip respectively). See
// RmlMenu_Sync's hero-btn-icon / row-action-hint / tab-hint-l/r handling.
#define NUM_HINT_ITEMS    3
// Tab index of the Stadiums tab (see menu.rml's #tab1) — the only tab whose
// rows get a thumbnail image + taller row height (Phase 3 visual redesign).
#define TAB_STADIUMS      1

// Zoom+fade in/out played each time the menu opens/closes (#panel only —
// see the RmlMenu_Sync call site and ApplyPanelOpenAnim/ApplyPanelCloseAnim
// below). Deliberately NOT an RCSS `transition`: #panel's transform/opacity
// computed style survives Hide()/Show() as whatever the PREVIOUS session
// settled on — a `transition` declared here would tween FROM that stale
// settled value (e.g. an instant full-size flash on open, then a shrink-away
// in the wrong direction) rather than from a fresh pose, because RmlUi only
// ever diffs against the last value Context::Update() actually committed,
// hidden document or not — same category of hazard as g_gliderTabCache
// further down, just solved by manually driving every frame from a real
// elapsed-time clock instead of a write-once guard.
static bool g_panelOpenAnimActive = false;
static ULONGLONG g_panelOpenAnimStartTick = 0;
static const float PANEL_OPEN_ANIM_MS = 220.f;
static const float PANEL_OPEN_START_SCALE = 0.85f;
// Close animation: #panel shrinks/fades back out to the same pose the open
// animation starts from, slightly quicker than the open (snappier exit is
// the usual UI convention). Runs AFTER menu_visible has already flipped to
// 0 in shared memory — RmlMenu_Sync keeps the document Shown() and RmlUi
// content untouched (nothing has actually changed except #panel's own
// transform/opacity) until the animation finishes, only THEN calling
// Hide(). See RmlMenu_DocShown()/its call site in cgfs16_rmlui.cpp for why
// RmlOverlay_RenderFrame must keep invoking RmlMenu_Sync every frame while
// this is active, even though menu_visible itself already reads false.
static bool g_panelCloseAnimActive = false;
static ULONGLONG g_panelCloseAnimStartTick = 0;
static const float PANEL_CLOSE_ANIM_MS = 160.f;

static Rml::String WideToUtf8(const wchar_t *s) {
    if (!s || !s[0]) return Rml::String();
    int len = WideCharToMultiByte(CP_UTF8, 0, s, -1, nullptr, 0, nullptr, nullptr);
    if (len <= 0) return Rml::String();
    std::string out(len - 1, '\0');
    WideCharToMultiByte(CP_UTF8, 0, s, -1, out.data(), len, nullptr, nullptr);
    return Rml::String(out);
}

static void SetPx(Rml::Element *el, const char *prop, float px) {
    if (!el) return;
    char buf[24];
    snprintf(buf, sizeof(buf), "%.1fpx", px);
    el->SetProperty(prop, buf);
}
static void SetRectPx(Rml::Element *el, float left, float top, float w, float h) {
    SetPx(el, "left", left);
    SetPx(el, "top", top);
    SetPx(el, "width", w);
    SetPx(el, "height", h);
}
static void SetVisible(Rml::Element *el, bool visible, const char *shownDisplay = "block") {
    if (!el) return;
    el->SetProperty("display", visible ? shownDisplay : "none");
}

// Drives #panel's open-in zoom (see g_panelOpenAnimActive's comment for why
// this is a manual per-frame tween rather than an RCSS `transition`). Ease-
// out cubic: fast start, gentle settle into the final scale(1)/opacity(1)
// pose, which is set explicitly (rather than left at the last interpolated
// value) once t reaches 1 so floating-point drift never leaves the panel a
// hair short of fully opaque/full-size.
static void ApplyPanelOpenAnim(Rml::Element *el) {
    if (!el || !g_panelOpenAnimActive) return;
    float elapsedMs = (float)(GetTickCount64() - g_panelOpenAnimStartTick);
    float t = (std::min)(1.f, elapsedMs / PANEL_OPEN_ANIM_MS);
    float eased = 1.f - powf(1.f - t, 3.f);
    float scale = PANEL_OPEN_START_SCALE + (1.f - PANEL_OPEN_START_SCALE) * eased;
    char buf[32];
    if (t >= 1.f) {
        g_panelOpenAnimActive = false;
        el->SetProperty("transform", "none");
        el->SetProperty("opacity", "1");
        return;
    }
    snprintf(buf, sizeof(buf), "scale(%.4f)", scale);
    el->SetProperty("transform", buf);
    snprintf(buf, sizeof(buf), "%.4f", eased);
    el->SetProperty("opacity", buf);
}

// Drives #panel's close-out zoom — mirror of ApplyPanelOpenAnim, ease-in
// cubic (slow start, fast finish) shrinking/fading from the settled
// scale(1)/opacity(1) pose back down to PANEL_OPEN_START_SCALE/0. Returns
// true once the animation has finished (caller is then responsible for
// actually Hide()-ing the document — this function only ever touches
// #panel's own properties, never document visibility).
static bool ApplyPanelCloseAnim(Rml::Element *el) {
    if (!el) return true;
    float elapsedMs = (float)(GetTickCount64() - g_panelCloseAnimStartTick);
    float t = (std::min)(1.f, elapsedMs / PANEL_CLOSE_ANIM_MS);
    if (t >= 1.f) return true;
    float eased = t * t * t;
    float scale = 1.f - (1.f - PANEL_OPEN_START_SCALE) * eased;
    float opacity = 1.f - eased;
    char buf[32];
    snprintf(buf, sizeof(buf), "scale(%.4f)", scale);
    el->SetProperty("transform", buf);
    snprintf(buf, sizeof(buf), "%.4f", opacity);
    el->SetProperty("opacity", buf);
    return false;
}

// ---------------------------------------------------------------------------
// Hint definitions — duplicated from cgfs16_overlay.cpp's GpIcon/KeyIcon/
// kHints/kKeyHints (cgfs16_overlay.cpp:279-331) so this file can build icon
// <img> src paths and set each hint's label text once at load time. Small,
// static, transition-only duplication: DrawMenuOverlay11 (the source of
// truth for these tables today) gets deleted at cutover, at which point only
// this copy remains.
// ---------------------------------------------------------------------------
enum GpIcon { GP_DPAD = 0, GP_RS, GP_LB, GP_RB, GP_A, GP_B, GP_ICON_COUNT };
static const wchar_t * const kGpIconFiles[GP_ICON_COUNT] = {
    L"dpad.png", L"rs.png", L"lb.png", L"rb.png", L"a.png", L"b.png",
};
struct HintDef { int icons[2]; const wchar_t *description; };
// Tab (LB+RB) and Select (A) live beside the tab strip / hero button / row
// now — see RmlMenu_Sync — not in this bottom bar.
static const HintDef kGpHints[NUM_HINT_ITEMS] = {
    { { GP_DPAD, -1    }, L"Navigate" },
    { { GP_RS,   -1    }, L"Scroll"   },
    { { GP_B,    -1    }, L"Close"    },
};
enum KeyIcon { KEY_UP = 0, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_ENTER, KEY_ESC, KEY_MOUSE, KEY_ICON_COUNT };
static const wchar_t * const kKeyIconFiles[KEY_ICON_COUNT] = {
    L"up.png", L"down.png", L"left.png", L"right.png", L"enter.png", L"esc.png", L"mouse.png",
};
// Tab (Left+Right) and Select (Enter) live beside the tab strip / hero
// button / row now — see RmlMenu_Sync — not in this bottom bar.
static const HintDef kKeyHints[NUM_HINT_ITEMS] = {
    { { KEY_UP,    KEY_DOWN  }, L"Navigate" },
    { { KEY_MOUSE, -1        }, L"Scroll"   },
    { { KEY_ESC,   -1        }, L"Close"    },
};

// ---------------------------------------------------------------------------
// Module state
// ---------------------------------------------------------------------------
static Rml::ElementDocument *g_menuDoc = nullptr;
static bool g_menuDocShown = false;

static Rml::Element *g_panel = nullptr;
static Rml::Element *g_panelAccent = nullptr;
static Rml::Element *g_brandTitle = nullptr;
// Bottom-right corner resize handle — see g_panelUserPositioned above.
static Rml::Element *g_resizeGrip = nullptr;
static Rml::Element *g_tabStrip = nullptr;
static Rml::Element *g_tabGlider = nullptr;
static Rml::Element *g_tab[NUM_MENU_TABS] = {};
static Rml::Element *g_contentBg = nullptr;
static Rml::Element *g_wizardHeader = nullptr;
static Rml::Element *g_wizardHeaderText = nullptr;
static Rml::Element *g_listArea = nullptr;
static Rml::Element *g_row[ROW_POOL] = {};
// .row-text/.row-thumb children (Phase 3) — text is set on g_rowText, not
// g_row itself, because SetInnerRML replaces ALL children of its target,
// which would wipe out the sibling <img class="row-thumb"> every frame.
static Rml::Element *g_rowText[ROW_POOL] = {};
static Rml::Element *g_rowThumb[ROW_POOL] = {};
static std::wstring  g_rowTextCache[ROW_POOL];
static std::wstring  g_rowThumbPathLoaded[ROW_POOL];
static bool           g_rowShown[ROW_POOL] = {};
static bool           g_rowSelected[ROW_POOL] = {};
static bool           g_rowStadiumStyled[ROW_POOL] = {};
static Rml::Element *g_emptyState = nullptr;
static Rml::Element *g_loadingSpinner = nullptr;
static Rml::Element *g_scrollTrack = nullptr;
static Rml::Element *g_scrollThumb = nullptr;
static Rml::Element *g_splitPreview = nullptr;
static Rml::Element *g_previewImg = nullptr;
static wchar_t        g_previewPathLoaded[MAX_IMG] = {};
// Hero panel enrichment (Phase 3): title mirrors the selected item's own row
// text (no separate data source exists for a "tag"/description beyond the
// item name — see the Phase 3 plan notes on this gap, deliberately not
// faked here). g_heroBtn fires EVK_HERO_ACTIVATE on click — activates the
// already-selected item immediately, unlike a row Click (which only selects;
// activation there needs a second click/dblclick).
static Rml::Element *g_heroTitle = nullptr;
static Rml::Element *g_heroBtn = nullptr;
static Rml::Element *g_heroBtnIcon = nullptr;
static wchar_t        g_heroBtnIconLoaded[MAX_IMG] = {};
static std::wstring  g_heroTitleTextLoaded;
// .hero-highlight mirrors real mouse :hover while in gamepad mode (there's
// no meaningful mouse position to actually hover it with a controller —
// the real cursor is just wherever it was last left resting on screen), so
// the button still visibly reads as "this is what A activates". .hero-
// pressed mirrors real mouse :active for the keyboard/gamepad "activate"
// inputs (Enter/A), which never touch RmlUi's own :active pseudo-class
// since they're not a mouse button. Both cached to avoid redundant
// SetClass calls, same pattern as g_tabActiveCache/g_tabOnGliderCache.
static bool g_heroHighlightCache = false;
static bool g_heroPressedCache = false;
// Floating "press A/Enter" icon for tabs with no hero button (Scoreboards/
// Movies/TV Logos) — attached to whichever row is hovered (mouse) or,
// failing that, the keyboard/gamepad-selected row. See its handling in
// RmlMenu_Sync's row loop.
static Rml::Element *g_rowActionHint = nullptr;
static wchar_t        g_rowActionHintIconLoaded[MAX_IMG] = {};
// L/R (gamepad) or Left/Right (keyboard) tab-switch hints, flanking the tab
// strip rather than living in the bottom hint bar.
static Rml::Element *g_tabHintL = nullptr;
static Rml::Element *g_tabHintR = nullptr;
static wchar_t        g_tabHintLIconLoaded[MAX_IMG] = {};
static wchar_t        g_tabHintRIconLoaded[MAX_IMG] = {};
static Rml::Element *g_dashboard = nullptr;
static Rml::Element *g_dashScore = nullptr;
static Rml::Element *g_homeCrest = nullptr;
static Rml::Element *g_awayCrest = nullptr;
static wchar_t        g_homeCrestPathLoaded[MAX_IMG] = {};
static wchar_t        g_awayCrestPathLoaded[MAX_IMG] = {};
static Rml::Element *g_dashScoreText = nullptr;
static Rml::Element *g_dashTimeText = nullptr;
static Rml::Element *g_dashLine[MAX_DASH_ITEMS] = {};

static Rml::Element *g_hintKeyRow = nullptr;
static Rml::Element *g_hintGpRow = nullptr;
static Rml::Element *g_hintKeyIcon1[NUM_HINT_ITEMS] = {};
static Rml::Element *g_hintKeyIcon2[NUM_HINT_ITEMS] = {};
static Rml::Element *g_hintGpIcon1[NUM_HINT_ITEMS] = {};
static Rml::Element *g_hintGpIcon2[NUM_HINT_ITEMS] = {};
static wchar_t        g_gpIconDirLoaded[MAX_IMG] = {};
static wchar_t        g_keyIconDirLoaded[MAX_IMG] = {};
// The "Close" hint item (index 2 in both kKeyHints/kGpHints below) doubles as
// a clickable button — same close/back action as the Esc key / gamepad B
// button, reported via EVK_CLOSE_CLICK. Captured from the same hintkey2/
// hintgp2 lookup the icon/label loop already does below, just kept around
// instead of discarded, so MenuEventListener can compare against them.
static Rml::Element *g_hintCloseKey = nullptr;
static Rml::Element *g_hintCloseGp = nullptr;

static bool g_tabActiveCache[NUM_MENU_TABS] = {};
// Distinct from g_tabActiveCache: .active marks the real selected tab
// (unaffected by hover), .on-glider marks whichever tab the glider is
// CURRENTLY sitting under (hovered tab if any, else the active tab) — the
// one that gets the dark on-glider text color. Mirrors overlay.html's own
// split between `.tab-btn.active` and the hover-driven text-color rules
// (see the glider-position block below for the hover-detection logic that
// feeds this).
static bool g_tabOnGliderCache[NUM_MENU_TABS] = {};
static long g_lastActiveTabForClear = -1;
// Last gliderTab (hovered-or-active tab index)/tabStripW the glider's
// C++-driven tween (see RetargetTabGliderAnim/ApplyTabGliderAnim further
// down) was last retargeted for — just a plain "did the desired slot
// change" check so RetargetTabGliderAnim is only called on an actual
// change, not every frame; g_gliderTabCache < 0 also doubles as the
// "never positioned yet" sentinel RetargetTabGliderAnim checks to skip
// animating in from (0,0) on the menu's very first open.
static long g_gliderTabCache = -1;
static float g_gliderTabStripWCache = -1.f;

// Tab-glider slide — manual per-frame tween, same reasoning as
// ApplyPanelOpenAnim/g_panelOpenAnimActive's comment further up: RCSS
// `transition` only fires from ElementStyle::TransitionPropertyChanges,
// which runs on a stylesheet-DEFINITION change (a class/pseudo-class toggle
// causing different RCSS rules to match) — never for a plain inline
// SetProperty() call, which is exactly what SetRectPx does every time this
// element needs to move. A `transition` declared on #tab-glider in menu.rml
// would (and did, before this) have zero actual effect. 300ms ease-out-cubic
// approximates overlay.html's own `transition: all 0.3s cubic-bezier(0.25,
// 1, 0.5, 1)` — RCSS has no arbitrary-bezier support to match it exactly
// (see the file's other cubic-bezier comments), and this is plain C++ now
// anyway, not RCSS, so there's no keyword-table restriction left to work
// around; ease-out-cubic is simply the same curve already used above.
static bool      g_gliderAnimActive = false;
static ULONGLONG g_gliderAnimStartTick = 0;
static float     g_gliderAnimStartLeft = 0.f, g_gliderAnimStartWidth = 0.f;
static float     g_gliderAnimTargetLeft = 0.f, g_gliderAnimTargetWidth = 0.f;
static const float GLIDER_ANIM_MS = 300.f;

// Starts (or redirects) the glider's slide toward (targetLeft, targetWidth).
// Called only when the target actually changed (see RmlMenu_Sync's
// gliderTab/tabStripW guard) — redirecting mid-flight (e.g. the mouse
// sweeps from tab 1 straight to tab 3 before the first slide finishes)
// captures wherever THIS leg had actually eased to as the new leg's start,
// rather than snapping back to the old target first — same "redirect
// smoothly, don't snap" principle as g_panelCloseAnimActive's reopen-cancel
// handling further up.
static void RetargetTabGliderAnim(float targetLeft, float targetWidth) {
    float curLeft = g_gliderAnimTargetLeft;
    float curWidth = g_gliderAnimTargetWidth;
    bool firstEver = (g_gliderTabCache < 0);
    if (g_gliderAnimActive) {
        float elapsedMs = (float)(GetTickCount64() - g_gliderAnimStartTick);
        float t = (std::min)(1.f, elapsedMs / GLIDER_ANIM_MS);
        float eased = 1.f - powf(1.f - t, 3.f);
        curLeft  = g_gliderAnimStartLeft  + (g_gliderAnimTargetLeft  - g_gliderAnimStartLeft)  * eased;
        curWidth = g_gliderAnimStartWidth + (g_gliderAnimTargetWidth - g_gliderAnimStartWidth) * eased;
    }
    g_gliderAnimStartLeft   = curLeft;
    g_gliderAnimStartWidth  = curWidth;
    g_gliderAnimTargetLeft  = targetLeft;
    g_gliderAnimTargetWidth = targetWidth;
    if (firstEver) {
        // No previous position to slide from — snap straight to the
        // initial slot instead of visibly sliding in from (0,0) the first
        // time the menu ever opens.
        g_gliderAnimActive = false;
    } else {
        g_gliderAnimStartTick = GetTickCount64();
        g_gliderAnimActive = true;
    }
}

// Renders this frame's eased in-flight rect, or the settled target once the
// slide has finished (or never started) — called unconditionally every
// frame RmlMenu_Sync runs, same pattern as ApplyPanelOpenAnim; harmless to
// keep re-applying the same settled value every frame once t reaches 1,
// same as every other per-frame geometry call in this file.
static void ApplyTabGliderAnim(Rml::Element *el, float height) {
    if (!el) return;
    if (g_gliderAnimActive) {
        float elapsedMs = (float)(GetTickCount64() - g_gliderAnimStartTick);
        float t = (std::min)(1.f, elapsedMs / GLIDER_ANIM_MS);
        if (t >= 1.f) {
            g_gliderAnimActive = false;
        } else {
            float eased = 1.f - powf(1.f - t, 3.f);
            float left  = g_gliderAnimStartLeft  + (g_gliderAnimTargetLeft  - g_gliderAnimStartLeft)  * eased;
            float width = g_gliderAnimStartWidth + (g_gliderAnimTargetWidth - g_gliderAnimStartWidth) * eased;
            SetRectPx(el, left, 0.f, width, height);
            return;
        }
    }
    SetRectPx(el, g_gliderAnimTargetLeft, 0.f, g_gliderAnimTargetWidth, height);
}

// Phase 2 Step 3: last-seen raw button state, for down/up edge detection —
// Present fires far more often than Python's ~80ms mouse-field write, so
// this must be compared every frame rather than trusting a single sample.
static bool g_mouseLeftWasDown = false;

// Phase 2 Step 4: click/scroll event reporting state.
// g_rowAbsIndex[k] = the ABSOLUTE index (into the current tab's full item
// list, not just the visible window) that row pool slot k currently shows —
// refreshed every frame in RmlMenu_Sync's row loop, read back when a Click
// fires on that row. windowBase/scrollOffset/totalCount/visibleRows are
// cached the same way so the scrollbar handlers below (which run from an
// event callback, not from RmlMenu_Sync's own call stack) can convert a
// drag/click position into an absolute scroll target without re-deriving
// the whole layout.
static long g_rowAbsIndex[ROW_POOL] = {};
static long g_cachedTotalCount = 0;
static long g_cachedVisibleRows = 1;
static long g_cachedWindowBase = 0;
static long g_cachedScrollOffset = 0;
// Where within the thumb the drag grabbed it (Dragstart), so Drag doesn't
// snap the thumb's top edge to the cursor — same anchor technique as
// RmlUi's own built-in scrollbar (Source/Core/WidgetScroll.cpp).
static float g_thumbDragAnchorY = 0.f;

// User-driven panel move/resize (drag #brand-title to move, #resize-grip's
// bottom-right corner to resize) — "window" behavior layered on top of the
// panel geometry block's normal auto-centered/ratio-sized default. Until
// the user actually drags something, g_panelUserPositioned stays false and
// RmlMenu_Sync keeps computing mx/my/MW/MH the original way; the first
// Dragstart on either handle seeds these from the panel's own current
// (auto) box via GetAbsoluteOffset()/GetBox() so nothing jumps, then every
// later frame uses (and re-clamps, in case the game's output resolution
// changed) these instead. Persists for the rest of the DLL's lifetime,
// including across menu close/reopen — same "remember where I left it"
// expectation as a real desktop window, not reset per-open.
static bool  g_panelUserPositioned = false;
static float g_panelUserX = 0.f, g_panelUserY = 0.f;
static float g_panelUserW = 0.f, g_panelUserH = 0.f;
// Offset from the mouse to the panel's top-left at move-Dragstart, so Drag
// doesn't snap the panel's corner to the cursor — same anchor technique as
// g_thumbDragAnchorY above.
static float g_panelDragAnchorX = 0.f, g_panelDragAnchorY = 0.f;
// Panel size + mouse position at resize-Dragstart; Drag then applies the
// mouse's delta from these on top of the starting size, so growth tracks
// the corner precisely instead of jumping to (mouse - grip's own origin).
static float g_panelResizeStartMouseX = 0.f, g_panelResizeStartMouseY = 0.f;
static float g_panelResizeStartW = 0.f, g_panelResizeStartH = 0.f;

// Reports every raw click as item_click/tab_click/scroll_to over the
// menu_event_* "last event wins" slot — never distinguishes click vs.
// double-click itself (see the migration plan's "C++ listens only to
// RmlUi's Click event, never Dblclick" note): Python's own, unchanged
// double-click detection in _handle_rmlui_menu_event keeps deciding
// select-vs-activate, exactly as it already does for the old renderer's
// mouse hit-testing.
class MenuEventListener : public Rml::EventListener {
public:
    void ProcessEvent(Rml::Event &event) override;
};
static MenuEventListener g_menuEventListener;

// Sets a single standalone icon <img>'s src to "<iconDir>\<iconFile>",
// skipping the SetAttribute call (which triggers a real texture load) when
// the resolved path already matches *cache — used for the hero-btn/row-
// action/tab-hint icons, which (unlike RmlMenu_LoadIconRow's fixed hint-bar
// icons) switch file every time input_mode flips between keyboard and
// gamepad, so this runs every frame rather than only when iconDir changes.
static void SetIconSrcCached(Rml::Element *el, wchar_t *cache, size_t cacheLen,
                              const wchar_t *iconDir, const wchar_t *iconFile) {
    if (!el || !iconDir || !iconDir[0] || !iconFile) return;
    size_t dirLen = wcslen(iconDir);
    bool hasSlash = dirLen > 0 && (iconDir[dirLen - 1] == L'\\' || iconDir[dirLen - 1] == L'/');
    wchar_t path[MAX_IMG] = {};
    _snwprintf_s(path, MAX_IMG, _TRUNCATE, hasSlash ? L"%s%s" : L"%s\\%s", iconDir, iconFile);
    if (wcscmp(path, cache) != 0) {
        wcsncpy_s(cache, cacheLen, path, _TRUNCATE);
        el->SetAttribute("src", WideToUtf8(path));
    }
}

static bool RmlMenu_LoadIconRow(Rml::Element *(&icon1)[NUM_HINT_ITEMS],
                                 Rml::Element *(&icon2)[NUM_HINT_ITEMS],
                                 const HintDef *hints,
                                 const wchar_t * const *iconFiles,
                                 const wchar_t *iconDir) {
    if (!iconDir || !iconDir[0]) return false;
    size_t dirLen = wcslen(iconDir);
    bool hasSlash = dirLen > 0 && (iconDir[dirLen - 1] == L'\\' || iconDir[dirLen - 1] == L'/');
    for (int i = 0; i < NUM_HINT_ITEMS; i++) {
        for (int k = 0; k < 2; k++) {
            Rml::Element *img = (k == 0) ? icon1[i] : icon2[i];
            if (!img) continue;
            int iconIdx = hints[i].icons[k];
            if (iconIdx < 0) {
                img->SetProperty("display", "none");
                continue;
            }
            wchar_t path[MAX_IMG] = {};
            _snwprintf_s(path, MAX_IMG, _TRUNCATE, hasSlash ? L"%s%s" : L"%s\\%s",
                         iconDir, iconFiles[iconIdx]);
            img->SetAttribute("src", WideToUtf8(path));
            img->SetProperty("display", "block");
        }
    }
    return true;
}

bool RmlMenu_Load(Rml::Context *context, const Rml::String &content_dir) {
    if (!context || content_dir.empty()) {
        Log("[RmlMenu] Load: empty context or content_dir");
        return false;
    }
    Rml::String path = content_dir + "\\menu.rml";
    g_menuDoc = context->LoadDocument(path);
    if (!g_menuDoc) {
        Log("[RmlMenu] LoadDocument failed for '%s'", path.c_str());
        return false;
    }

    g_panel = g_menuDoc->GetElementById("panel");
    g_panelAccent = g_menuDoc->GetElementById("panel-accent");
    g_brandTitle = g_menuDoc->GetElementById("brand-title");
    g_resizeGrip = g_menuDoc->GetElementById("resize-grip");
    g_tabStrip = g_menuDoc->GetElementById("tabstrip");
    g_tabGlider = g_menuDoc->GetElementById("tab-glider");
    for (int i = 0; i < NUM_MENU_TABS; i++) {
        char idBuf[8];
        snprintf(idBuf, sizeof(idBuf), "tab%d", i);
        g_tab[i] = g_menuDoc->GetElementById(idBuf);
    }
    g_tabHintL = g_menuDoc->GetElementById("tab-hint-l");
    g_tabHintR = g_menuDoc->GetElementById("tab-hint-r");
    g_contentBg = g_menuDoc->GetElementById("content-bg");
    g_wizardHeader = g_menuDoc->GetElementById("wizard-header");
    g_wizardHeaderText = g_menuDoc->GetElementById("wizard-header-text");
    g_listArea = g_menuDoc->GetElementById("list-area");
    for (int i = 0; i < ROW_POOL; i++) {
        char idBuf[8];
        snprintf(idBuf, sizeof(idBuf), "row%d", i);
        g_row[i] = g_menuDoc->GetElementById(idBuf);
        if (g_row[i]) {
            g_rowText[i]  = g_row[i]->QuerySelector(".row-text");
            g_rowThumb[i] = g_row[i]->QuerySelector(".row-thumb");
        }
    }
    g_emptyState = g_menuDoc->GetElementById("empty-state");
    g_rowActionHint = g_menuDoc->GetElementById("row-action-hint");
    g_loadingSpinner = g_menuDoc->GetElementById("loading-spinner");
    g_scrollTrack = g_menuDoc->GetElementById("scrollbar-track");
    g_scrollThumb = g_menuDoc->GetElementById("scrollbar-thumb");
    g_splitPreview = g_menuDoc->GetElementById("split-preview");
    g_previewImg = g_menuDoc->GetElementById("preview-img");
    g_heroTitle = g_menuDoc->GetElementById("hero-title");
    g_heroBtn = g_menuDoc->GetElementById("hero-btn");
    if (g_heroBtn) g_heroBtnIcon = g_heroBtn->QuerySelector(".hero-btn-icon");
    g_dashboard = g_menuDoc->GetElementById("dashboard");
    g_dashScore = g_menuDoc->GetElementById("dash-score");
    g_homeCrest = g_menuDoc->GetElementById("home-crest");
    g_awayCrest = g_menuDoc->GetElementById("away-crest");
    g_dashScoreText = g_menuDoc->GetElementById("dash-score-text");
    g_dashTimeText = g_menuDoc->GetElementById("dash-time-text");
    for (int i = 0; i < MAX_DASH_ITEMS; i++) {
        char idBuf[8];
        snprintf(idBuf, sizeof(idBuf), "dash%d", i);
        g_dashLine[i] = g_menuDoc->GetElementById(idBuf);
    }
    g_hintKeyRow = g_menuDoc->GetElementById("hint-key-row");
    g_hintGpRow = g_menuDoc->GetElementById("hint-gp-row");
    for (int i = 0; i < NUM_HINT_ITEMS; i++) {
        char idBuf[16];
        snprintf(idBuf, sizeof(idBuf), "hintkey%d", i);
        Rml::Element *item = g_menuDoc->GetElementById(idBuf);
        if (item) {
            g_hintKeyIcon1[i] = item->QuerySelector(".icon1");
            g_hintKeyIcon2[i] = item->QuerySelector(".icon2");
            Rml::Element *label = item->QuerySelector(".label");
            if (label) label->SetInnerRML(WideToUtf8(kKeyHints[i].description));
            if (i == 2) g_hintCloseKey = item;
        }
        snprintf(idBuf, sizeof(idBuf), "hintgp%d", i);
        item = g_menuDoc->GetElementById(idBuf);
        if (item) {
            g_hintGpIcon1[i] = item->QuerySelector(".icon1");
            g_hintGpIcon2[i] = item->QuerySelector(".icon2");
            Rml::Element *label = item->QuerySelector(".label");
            if (label) label->SetInnerRML(WideToUtf8(kGpHints[i].description));
            if (i == 2) g_hintCloseGp = item;
        }
    }

    bool ok = g_panel && g_panelAccent && g_brandTitle && g_resizeGrip && g_tabStrip && g_tabGlider && g_contentBg &&
              g_listArea && g_dashboard && g_dashScore && g_dashScoreText && g_dashTimeText &&
              g_scrollTrack && g_scrollThumb &&
              g_splitPreview && g_previewImg && g_heroTitle && g_heroBtn && g_heroBtnIcon &&
              g_hintKeyRow && g_hintGpRow && g_hintCloseKey && g_hintCloseGp &&
              g_rowActionHint && g_tabHintL && g_tabHintR && g_loadingSpinner;
    if (!ok) {
        Log("[RmlMenu] Load: one or more required elements missing after GetElementById");
        return false;
    }

    // Step 4: click/scroll listeners. Registered once here, not per-frame —
    // RmlUi keeps the listener alive on the element for its lifetime, and
    // these elements are never destroyed/recreated (fixed pool, see the
    // file's top comment).
    for (int i = 0; i < NUM_MENU_TABS; i++)
        if (g_tab[i]) g_tab[i]->AddEventListener(Rml::EventId::Click, &g_menuEventListener);
    for (int k = 0; k < ROW_POOL; k++)
        if (g_row[k]) g_row[k]->AddEventListener(Rml::EventId::Click, &g_menuEventListener);
    g_scrollTrack->AddEventListener(Rml::EventId::Click, &g_menuEventListener);
    // "drag" (not "drag-drop"/"clone") — plain reposition-on-drag, same as
    // RmlUi's own built-in scrollbar thumb (Source/Core/WidgetScroll.cpp).
    g_scrollThumb->SetProperty("drag", "drag");
    g_scrollThumb->AddEventListener(Rml::EventId::Dragstart, &g_menuEventListener);
    g_scrollThumb->AddEventListener(Rml::EventId::Drag, &g_menuEventListener);
    // Window-style move (drag the brand/title area) and resize (drag the
    // bottom-right corner grip) — see g_panelUserPositioned's comment.
    g_brandTitle->SetProperty("drag", "drag");
    g_brandTitle->AddEventListener(Rml::EventId::Dragstart, &g_menuEventListener);
    g_brandTitle->AddEventListener(Rml::EventId::Drag, &g_menuEventListener);
    g_resizeGrip->SetProperty("drag", "drag");
    g_resizeGrip->AddEventListener(Rml::EventId::Dragstart, &g_menuEventListener);
    g_resizeGrip->AddEventListener(Rml::EventId::Drag, &g_menuEventListener);
    // Phase 3: hero panel's "Select" button — activates the already-selected
    // item on a single click (see EVK_HERO_ACTIVATE).
    g_heroBtn->AddEventListener(Rml::EventId::Click, &g_menuEventListener);
    // "Close" hint item — same close/back action as Esc/B, now also
    // clickable (see EVK_CLOSE_CLICK). Only one of the two rows is ever
    // visible at once (see the input_mode guard in ProcessEvent below), but
    // both get a listener since either could be the visible one.
    g_hintCloseKey->AddEventListener(Rml::EventId::Click, &g_menuEventListener);
    g_hintCloseGp->AddEventListener(Rml::EventId::Click, &g_menuEventListener);

    Log("[RmlMenu] Load ok ('%s')", path.c_str());
    return true;
}

// menu_event_kind values — must match d3d_injector.py's get_menu_event() /
// app_overlay.py's _handle_rmlui_menu_event() docstrings exactly.
enum MenuEventKind { EVK_TAB_CLICK = 1, EVK_ITEM_CLICK = 2, EVK_SCROLL_TO = 3, EVK_HERO_ACTIVATE = 4, EVK_CLOSE_CLICK = 5 };

// Converts a relative position along the scrollbar track [0, 1] into an
// absolute scroll target, using the same maxScrollTotal = totalCount -
// visibleRows relationship RmlMenu_Sync's own thumb-positioning math uses
// (just inverted) — see the "── Scrollbar" block above.
static long RmlMenu_RelPosToAbsScroll(float relPos) {
    long maxScrollTotal = (std::max)(0L, g_cachedTotalCount - g_cachedVisibleRows);
    if (maxScrollTotal <= 0) return 0;
    relPos = (std::max)(0.f, (std::min)(1.f, relPos));
    return (std::max)(0L, (std::min)(maxScrollTotal, (long)lroundf(relPos * (float)maxScrollTotal)));
}

void MenuEventListener::ProcessEvent(Rml::Event &event) {
    Rml::Element *cur = event.GetCurrentElement();
    if (!cur) return;

    if (event == Rml::EventId::Click) {
        if (cur == g_heroBtn) {
            RmlOverlay_PushMenuEvent(EVK_HERO_ACTIVATE, 0);
            return;
        }
        if (cur == g_hintCloseKey || cur == g_hintCloseGp) {
            // Guard against a click landing on the currently-hidden hint row
            // (mirrors the g_rowShown[k] check the row-click branch below
            // uses for the same reason) — only the row matching the live
            // input mode should ever actually close/back out of the menu.
            bool gamepadMode = RmlOverlay_InputMode() != 0;
            if (cur == (gamepadMode ? g_hintCloseGp : g_hintCloseKey)) {
                RmlOverlay_PushMenuEvent(EVK_CLOSE_CLICK, 0);
            }
            return;
        }
        for (int i = 0; i < NUM_MENU_TABS; i++) {
            if (cur == g_tab[i]) {
                RmlOverlay_PushMenuEvent(EVK_TAB_CLICK, i);
                return;
            }
        }
        for (int k = 0; k < ROW_POOL; k++) {
            if (cur == g_row[k] && g_rowShown[k]) {
                RmlOverlay_PushMenuEvent(EVK_ITEM_CLICK, (int)g_rowAbsIndex[k]);
                return;
            }
        }
        if (cur == g_scrollTrack && g_scrollThumb) {
            // Page up/down toward the click, same behavior as RmlUi's own
            // built-in scrollbar track (WidgetScroll::ProcessEvent's Click
            // handling) — simpler than the old renderer's click-in-thumb=
            // jump/click-outside=page split, and this is a separate,
            // independently-testable click path (old renderer untouched).
            float clickY = event.GetParameter<float>("mouse_y", 0.f);
            float trackTop = g_scrollTrack->GetAbsoluteOffset().y;
            float trackH = g_scrollTrack->GetBox().GetSize().y;
            float thumbH = g_scrollThumb->GetBox().GetSize().y;
            float traversable = (std::max)(1.f, trackH - thumbH);
            long curAbsScroll = g_cachedScrollOffset + g_cachedWindowBase;
            long maxScrollTotal = (std::max)(0L, g_cachedTotalCount - g_cachedVisibleRows);
            float curThumbY = maxScrollTotal > 0 ? ((float)curAbsScroll / (float)maxScrollTotal) * traversable : 0.f;
            long pageSize = (std::max)(1L, g_cachedVisibleRows);
            long target = curAbsScroll + ((clickY - trackTop) < curThumbY ? -pageSize : pageSize);
            target = (std::max)(0L, (std::min)(maxScrollTotal, target));
            RmlOverlay_PushMenuEvent(EVK_SCROLL_TO, (int)target);
        }
    } else if (event == Rml::EventId::Dragstart) {
        if (cur == g_scrollThumb) {
            g_thumbDragAnchorY = event.GetParameter<float>("mouse_y", 0.f) - g_scrollThumb->GetAbsoluteOffset().y;
        } else if (cur == g_brandTitle && g_panel) {
            float mouseX = event.GetParameter<float>("mouse_x", 0.f);
            float mouseY = event.GetParameter<float>("mouse_y", 0.f);
            Rml::Vector2f panelPos = g_panel->GetAbsoluteOffset();
            g_panelDragAnchorX = mouseX - panelPos.x;
            g_panelDragAnchorY = mouseY - panelPos.y;
            if (!g_panelUserPositioned) {
                // First-ever drag: seed size from the panel's current
                // (auto-computed) box so switching into "user positioned"
                // mode this frame doesn't also jump the size.
                Rml::Vector2f sz = g_panel->GetBox().GetSize();
                g_panelUserW = sz.x;
                g_panelUserH = sz.y;
            }
        } else if (cur == g_resizeGrip && g_panel) {
            g_panelResizeStartMouseX = event.GetParameter<float>("mouse_x", 0.f);
            g_panelResizeStartMouseY = event.GetParameter<float>("mouse_y", 0.f);
            Rml::Vector2f sz = g_panel->GetBox().GetSize();
            g_panelResizeStartW = sz.x;
            g_panelResizeStartH = sz.y;
            if (!g_panelUserPositioned) {
                // Same seeding as above, but for position instead of size —
                // resizing from the corner keeps the top-left anchored, so
                // it's the position that must not jump on the first drag.
                Rml::Vector2f pos = g_panel->GetAbsoluteOffset();
                g_panelUserX = pos.x;
                g_panelUserY = pos.y;
            }
        }
    } else if (event == Rml::EventId::Drag) {
        if (cur == g_scrollThumb && g_scrollTrack) {
            float mouseY = event.GetParameter<float>("mouse_y", 0.f);
            float trackTop = g_scrollTrack->GetAbsoluteOffset().y;
            float trackH = g_scrollTrack->GetBox().GetSize().y;
            float thumbH = g_scrollThumb->GetBox().GetSize().y;
            float traversable = trackH - thumbH;
            float relPos = traversable > 0.f ? (mouseY - g_thumbDragAnchorY - trackTop) / traversable : 0.f;
            RmlOverlay_PushMenuEvent(EVK_SCROLL_TO, (int)RmlMenu_RelPosToAbsScroll(relPos));
        } else if (cur == g_brandTitle) {
            // Raw, unclamped intent — RmlMenu_Sync re-clamps to the current
            // viewport every frame (also covers a mid-drag resolution
            // change), so there's no need to duplicate those bounds here.
            g_panelUserX = event.GetParameter<float>("mouse_x", 0.f) - g_panelDragAnchorX;
            g_panelUserY = event.GetParameter<float>("mouse_y", 0.f) - g_panelDragAnchorY;
            g_panelUserPositioned = true;
        } else if (cur == g_resizeGrip) {
            float mouseX = event.GetParameter<float>("mouse_x", 0.f);
            float mouseY = event.GetParameter<float>("mouse_y", 0.f);
            g_panelUserW = g_panelResizeStartW + (mouseX - g_panelResizeStartMouseX);
            g_panelUserH = g_panelResizeStartH + (mouseY - g_panelResizeStartMouseY);
            g_panelUserPositioned = true;
        }
    }
}

void RmlMenu_Sync(int vpW, int vpH, void *outputWindow) {
    if (!g_menuDoc) return;

    bool visible = RmlOverlay_MenuVisible();
    if (!visible) {
        if (g_panelCloseAnimActive) {
            // Still finishing the close-out from the frame the menu closed
            // on (see ApplyPanelCloseAnim) — keep driving it until it
            // finishes, then actually Hide(). Nothing else needs
            // recomputing: content/layout are unchanged since the last open
            // frame, only #panel's own transform/opacity move.
            if (ApplyPanelCloseAnim(g_panel)) {
                g_menuDoc->Hide();
                g_menuDocShown = false;
                g_panelCloseAnimActive = false;
                // Avoid a stuck-drag if the button was still held when the
                // menu closed (e.g. Esc/B while dragging the scrollbar thumb).
                g_mouseLeftWasDown = false;
            }
        } else if (g_menuDocShown) {
            // Just transitioned open -> closed this frame: kick off the
            // close-out instead of hiding immediately.
            g_panelOpenAnimActive = false; // don't fight an interrupted open
            g_panelCloseAnimActive = true;
            g_panelCloseAnimStartTick = GetTickCount64();
            ApplyPanelCloseAnim(g_panel);
        }
        return;
    }
    if (g_panelCloseAnimActive) {
        // Reopened before a pending close-out finished — cancel it and
        // re-arm the open animation so #panel reverses smoothly from
        // wherever the close-out had gotten to, rather than being left
        // stuck at that partial scale/opacity forever (ApplyPanelOpenAnim
        // below is a no-op whenever g_panelOpenAnimActive is false, so
        // without this it would never touch #panel again after a
        // cancelled close-out).
        g_panelCloseAnimActive = false;
        g_panelOpenAnimActive = true;
        g_panelOpenAnimStartTick = GetTickCount64();
    }
    RmlOverlay_SetMenuViewportTelemetry(vpW, vpH, outputWindow);

    long activeTab = RmlOverlay_ActiveTab();
    if (activeTab < 0 || activeTab >= NUM_MENU_TABS) activeTab = 0;
    long itemCount = (std::max)(0L, (std::min)((long)MAX_MENU_ITEMS, RmlOverlay_MenuItemCount()));
    long selIdx = (std::max)(0L, RmlOverlay_MenuSelectedIndex());
    long scrollOffset = (std::max)(0L, RmlOverlay_MenuScrollOffset());
    long totalCount = (std::max)((long)itemCount, RmlOverlay_MenuTotalCount());
    long windowBase = (std::max)(0L, RmlOverlay_MenuWindowBase());
    const wchar_t *listHeaderW = RmlOverlay_ListHeader();
    bool showHeader = listHeaderW && listHeaderW[0] != L'\0';
    bool showSplit = (activeTab == 1 || activeTab == 4);
    // Computed once here (not down at the bottom hint bar anymore) since the
    // tab-strip hints, hero-btn icon, and row-action hint all need it too.
    bool gamepadMode = RmlOverlay_InputMode() != 0;
    const wchar_t *gpDir = RmlOverlay_GamepadIconDir();
    const wchar_t *keyDir = RmlOverlay_KeyboardIconDir();
    // True while Python's _update_menu_content() is still computing the item
    // list this frame's activeTab/wizard step actually wants (menu_items[]
    // etc. are stale, about-to-be-replaced data until it clears this) — see
    // the loading-spinner block below, which is the only thing that reacts
    // to it directly; row/empty-state/split-preview visibility below are
    // gated on it too so nothing stale flashes underneath the spinner.
    bool loading = RmlOverlay_MenuLoading();

    float vw = (float)(vpW > 0 ? vpW : 1280);
    float vh = (float)(vpH > 0 ? vpH : 720);

    // ── Panel geometry — mirrors DrawMenuOverlay11's math exactly
    //    (cgfs16_overlay.cpp:882-929); "l*" vars are panel-local (mx/my
    //    subtracted out), since every element below is nested inside #panel.
    const float MENU_RATIO_W = 0.88f, MENU_RATIO_H = 0.90f;
    const float MENU_MIN_W = 1240.f, MENU_MIN_H = 760.f;
    const float VIEW_MARGIN = 20.f;
    const float availW = (std::max)(320.f, vw - 2.f * VIEW_MARGIN);
    const float availH = (std::max)(240.f, vh - 2.f * VIEW_MARGIN);
    float MW, MH, mx, my;
    if (g_panelUserPositioned) {
        // User has dragged/resized at least once this session (see
        // g_panelUserPositioned's comment) — use that instead of the
        // auto-centered/ratio-sized default, but still re-clamp to the
        // current viewport every frame: keeps the panel fully on-screen and
        // no smaller than MENU_MIN_W/H even if the game's output resolution
        // changes mid-session, without needing a separate "reset" action.
        MW = (std::max)(MENU_MIN_W, (std::min)(availW, g_panelUserW));
        MH = (std::max)(MENU_MIN_H, (std::min)(availH, g_panelUserH));
        float maxX = (std::max)(VIEW_MARGIN, vw - VIEW_MARGIN - MW);
        float maxY = (std::max)(VIEW_MARGIN, vh - VIEW_MARGIN - MH);
        mx = floorf((std::max)(VIEW_MARGIN, (std::min)(maxX, g_panelUserX)));
        my = floorf((std::max)(VIEW_MARGIN, (std::min)(maxY, g_panelUserY)));
        MW = floorf(MW);
        MH = floorf(MH);
        // Write the clamped values back so next frame's clamp starts from
        // an already-valid state (and so a drag that's mid-flight when the
        // viewport changes doesn't fight this frame's correction).
        g_panelUserX = mx; g_panelUserY = my; g_panelUserW = MW; g_panelUserH = MH;
    } else {
        MW = (std::min)(availW, (std::max)(MENU_MIN_W, floorf(vw * MENU_RATIO_W)));
        MH = (std::min)(availH, (std::max)(MENU_MIN_H, floorf(vh * MENU_RATIO_H)));
        mx = floorf((vw - MW) / 2.f);
        my = floorf((vh - MH) / 2.f);
    }
    const float TAB_H = 56.f;
    const float HINT_H = 38.f;
    // Only one hint row is ever shown at once (keyboard/mouse XOR gamepad,
    // picked below from RmlOverlay_InputMode) — single-row zone, not double.
    const float HINT_ZONE = HINT_H + 6.f;
    const float DASH_H = (std::max)(220.f, (std::min)(320.f, floorf(MH * 0.28f)));
    // Stadiums rows are taller than every other tab's (Phase 3 visual
    // redesign) so their .row-thumb is an actually-recognizable photo, not
    // a color chip — must stay in sync with menu.rml's `.row`/`.row.stadium-
    // row` height RCSS (28px/56px), since the real per-row height comes from
    // flex layout there, not from this file's pixel math; ITEM_H here only
    // drives visibleRows/scrollbar sizing to match what flex actually renders.
    const float ITEM_H_DEFAULT = 28.f;
    const float ITEM_H_STADIUMS = 56.f;
    const float ITEM_H = (activeTab == TAB_STADIUMS) ? ITEM_H_STADIUMS : ITEM_H_DEFAULT;
    const float SCROLL_W = 12.f;
    const float SCROLL_GAP = 6.f;
    const float HEADER_H = 30.f;
    const float SPLIT_FRAC = 0.60f;

    const float lListX = 4.f;
    const float lListY = TAB_H + 4.f;
    const float lListYMax = MH - DASH_H - HINT_ZONE - 14.f;
    const float lDashX = 10.f;
    const float lDashY = MH - DASH_H - HINT_ZONE - 6.f;
    const float lDashW = MW - 20.f;
    const float lHintY = MH - 2.f - HINT_H;
    const float lHintX = 2.f;
    const float lHintW = MW - 4.f;

    const float baseContentW = MW - 8.f;
    const float listSideW = showSplit ? floorf(baseContentW * SPLIT_FRAC) : baseContentW;
    // #split-preview carries its own box-shadow glow (0 0 20px, see menu.rml)
    // which #panel doesn't clip (no overflow:hidden there) — a plain 4px
    // right margin, same as every other edge in this file, left only 4px of
    // clearance for a 20px blur, so the glow (and at high output resolutions
    // even the border itself) visibly bled past #panel's own right edge into
    // the game behind it. 24px = 20px blur radius + the usual 4px margin.
    const float PREVIEW_RIGHT_MARGIN = 24.f;
    const float prevSideW = showSplit ? (baseContentW - listSideW - PREVIEW_RIGHT_MARGIN) : 0.f;
    const float lPrevX = 4.f + listSideW + 4.f;
    const float lPrevY = TAB_H + 4.f;
    const float prevSideH = lListYMax - lPrevY;
    const float adjListW = listSideW - SCROLL_W - SCROLL_GAP;
    const float lScrollX = lListX + adjListW + SCROLL_GAP;
    const float lAdjListY = lListY + (showHeader ? (HEADER_H + 4.f) : 0.f);
    const float adjScrollH = (std::max)(1.f, lListYMax - lAdjListY);
    const int visibleRows = (std::max)(1, (int)floorf((lListYMax - lAdjListY) / ITEM_H));
    RmlOverlay_SetMenuVisibleRows(visibleRows);
    // Step 4: cache for the scrollbar event handlers (MenuEventListener),
    // which run from an event callback outside this function's call stack.
    g_cachedTotalCount = totalCount;
    g_cachedVisibleRows = visibleRows;
    g_cachedWindowBase = windowBase;
    g_cachedScrollOffset = scrollOffset;

    if (!g_menuDocShown) {
        g_menuDoc->Show(Rml::ModalFlag::None, Rml::FocusFlag::None);
        g_menuDocShown = true;
        g_panelOpenAnimActive = true;
        g_panelOpenAnimStartTick = GetTickCount64();
    }

    SetRectPx(g_panel, mx, my, MW, MH);
    ApplyPanelOpenAnim(g_panel);
    // Resize grip, tucked into #panel's own bottom-right rounded corner.
    const float GRIP_SIZE = 20.f;
    const float GRIP_MARGIN = 3.f;
    SetRectPx(g_resizeGrip, MW - GRIP_SIZE - GRIP_MARGIN, MH - GRIP_SIZE - GRIP_MARGIN, GRIP_SIZE, GRIP_SIZE);
    // Top accent bar (mirrors the sketch's #game-hud::before — RCSS has no
    // ::before/::after, so this is a real element instead, positioned with
    // explicit left/width rather than RCSS `right:`, per this file's
    // established caution around untested right+width interaction).
    SetRectPx(g_panelAccent, 40.f, -1.f, (std::max)(0.f, MW - 80.f), 3.f);
    // Brand title (mirrors the sketch's .top-bar: a fixed-width branding
    // block on the left, tabs occupying the rest of the row) — reserved
    // BEFORE the tab strip's own rect is computed, so the strip fills
    // exactly what's left rather than running under/over the brand block.
    // Wide enough for "CGFS" at 38px Teko + the "PORT v2.0" badge at 18px
    // (overlay.html's exact brand-title/brand-badge text and sizes) — may
    // need a visual tuning pass once seen live, no font-metrics API used
    // here to measure it precisely.
    const float BRAND_W = 270.f;
    const float BRAND_GAP = 10.f;
    SetRectPx(g_brandTitle, 12.f, 2.f, BRAND_W, TAB_H - 2.f);
    // Tab-switch (LB+RB / Left+Right) hint icons, flanking the tab strip
    // itself instead of living in the bottom hint bar — carve out fixed
    // space for them on each side the same way BRAND_W already does for the
    // brand block, rather than overlapping the strip's own flex-laid-out
    // tabs.
    const float TAB_HINT_SIZE = 26.f;
    const float TAB_HINT_GAP = 8.f;
    const float tabStripX = 4.f + BRAND_W + BRAND_GAP + TAB_HINT_SIZE + TAB_HINT_GAP;
    const float tabStripW = (std::max)(0.f, MW - tabStripX - TAB_HINT_GAP - TAB_HINT_SIZE - 2.f);
    SetRectPx(g_tabStrip, tabStripX, 2.f, tabStripW, TAB_H - 2.f);
    SetRectPx(g_contentBg, 2.f, TAB_H + 2.f, MW - 4.f, MH - TAB_H - 4.f);
    {
        float tabHintY = 2.f + (TAB_H - 2.f - TAB_HINT_SIZE) / 2.f;
        SetVisible(g_tabHintL, true, "block");
        SetVisible(g_tabHintR, true, "block");
        SetRectPx(g_tabHintL, tabStripX - TAB_HINT_GAP - TAB_HINT_SIZE, tabHintY, TAB_HINT_SIZE, TAB_HINT_SIZE);
        SetRectPx(g_tabHintR, tabStripX + tabStripW + TAB_HINT_GAP, tabHintY, TAB_HINT_SIZE, TAB_HINT_SIZE);
        if (gamepadMode) {
            SetIconSrcCached(g_tabHintL, g_tabHintLIconLoaded, MAX_IMG, gpDir, kGpIconFiles[GP_LB]);
            SetIconSrcCached(g_tabHintR, g_tabHintRIconLoaded, MAX_IMG, gpDir, kGpIconFiles[GP_RB]);
        } else {
            SetIconSrcCached(g_tabHintL, g_tabHintLIconLoaded, MAX_IMG, keyDir, kKeyIconFiles[KEY_LEFT]);
            SetIconSrcCached(g_tabHintR, g_tabHintRIconLoaded, MAX_IMG, keyDir, kKeyIconFiles[KEY_RIGHT]);
        }
    }

    // Which tab the mouse is actually over right now, if any — RmlUi already
    // tracks :hover internally from the mouse feed _sync_rmlui_menu_mouse_feed
    // writes every ~80ms (see cgfs16_rmlui.cpp's ProcessMouseMove call), so
    // this is just reading that state back, not detecting it ourselves.
    // First match wins on the (practically never happening) chance two
    // skewed tabs' boxes both report hover at a shared boundary pixel.
    int hoveredTab = -1;
    for (int i = 0; i < NUM_MENU_TABS; i++) {
        if (g_tab[i] && g_tab[i]->IsPseudoClassSet("hover")) {
            hoveredTab = i;
            break;
        }
    }
    // Animated tab-glider — slides to the hovered tab's slot if the mouse is
    // over one, else back to the active tab's (mirrors overlay.html's own
    // mouseenter/mouseleave moveGliderTo calls, which likewise re-target the
    // glider to whichever is relevant rather than always following the
    // clicked/active tab). Also re-slides on tabStripW changes (viewport
    // resize). Only calls RetargetTabGliderAnim when the target actually
    // changed — see ApplyTabGliderAnim's own comment for why the render
    // call below is unconditional every frame regardless.
    const long gliderTab = (hoveredTab >= 0) ? (long)hoveredTab : activeTab;
    {
        const float tabW = tabStripW / (float)NUM_MENU_TABS;
        if (gliderTab != g_gliderTabCache || fabsf(tabStripW - g_gliderTabStripWCache) > 0.5f) {
            RetargetTabGliderAnim((float)gliderTab * tabW, tabW);
            g_gliderTabCache = gliderTab;
            g_gliderTabStripWCache = tabStripW;
        }
        ApplyTabGliderAnim(g_tabGlider, TAB_H - 2.f);
    }

    for (int i = 0; i < NUM_MENU_TABS; i++) {
        bool active = (i == (int)activeTab);
        if (g_tab[i] && active != g_tabActiveCache[i]) {
            g_tab[i]->SetClass("active", active);
            g_tabActiveCache[i] = active;
        }
        // Dark text follows the glider itself, not the real active state —
        // see g_tabOnGliderCache's comment.
        bool onGlider = (i == (int)gliderTab);
        if (g_tab[i] && onGlider != g_tabOnGliderCache[i]) {
            g_tab[i]->SetClass("on-glider", onGlider);
            g_tabOnGliderCache[i] = onGlider;
        }
    }

    // ── Wizard header band
    SetVisible(g_wizardHeader, showHeader);
    if (showHeader) {
        SetRectPx(g_wizardHeader, lListX, lListY, adjListW + SCROLL_W + SCROLL_GAP, HEADER_H);
        if (g_wizardHeaderText) g_wizardHeaderText->SetInnerRML(WideToUtf8(listHeaderW));
    }

    // ── Item list (fixed 64-row pool; pool slot k = real item scrollOffset+k)
    SetRectPx(g_listArea, lListX, lAdjListY, adjListW, adjScrollH);
    // Row action hint (A/Enter) tracking — see its positioning block right
    // after this loop. Rows are plain flex-column in-flow (no per-row
    // SetRectPx), so pool slot k's panel-local rect is derivable directly:
    // top = lAdjListY + k*ITEM_H, same left/width as #list-area itself.
    long rowHintHoverAbsIndex = -1;
    float rowHintHoverLocalY = 0.f;
    long rowHintSelAbsIndex = -1;
    float rowHintSelLocalY = 0.f;
    float mouseXAbs = (float)RmlOverlay_MenuMouseX();
    float mouseYAbs = (float)RmlOverlay_MenuMouseY();
    for (int k = 0; k < ROW_POOL; k++) {
        long realIndex = scrollOffset + k;
        // Step 4: absolute index (into the full list, not just this window)
        // for MenuEventListener to report on a Click — cached even for
        // out-of-window slots for simplicity; the listener only trusts it
        // when g_rowShown[k] is also true.
        g_rowAbsIndex[k] = windowBase + realIndex;
        // !loading: hide every row while a new list is still being computed
        // rather than showing the previous (stale) one under the spinner.
        bool inWindow = !loading && (k < visibleRows) && (realIndex < itemCount);
        if (inWindow != g_rowShown[k]) {
            // "flex", not "block": .row lays its optional .row-thumb and
            // .row-text side by side (see menu.rml) — needed for every tab,
            // not just Stadiums, since row-text must still get flex:1 1 auto
            // to fill the row when the thumb is hidden.
            SetVisible(g_row[k], inWindow, "flex");
            g_rowShown[k] = inWindow;
        }
        if (!inWindow) continue;
        bool selected = (realIndex == selIdx);
        if (selected != g_rowSelected[k]) {
            if (g_row[k]) g_row[k]->SetClass("selected", selected);
            g_rowSelected[k] = selected;
        }
        if (!showSplit) {
            float rowTopLocal = lAdjListY + (float)k * ITEM_H;
            // Hover only tested in keyboard/mouse mode — a gamepad user's
            // mouse cursor may be resting anywhere (stale position, not a
            // deliberate hover), and pressing A always activates the
            // selected row regardless, so trusting hover there would show
            // the hint on a row A won't actually activate.
            if (!gamepadMode) {
                float rowLeftAbs = mx + lListX;
                float rowTopAbs = my + rowTopLocal;
                if (mouseXAbs >= rowLeftAbs && mouseXAbs < rowLeftAbs + adjListW &&
                    mouseYAbs >= rowTopAbs && mouseYAbs < rowTopAbs + ITEM_H) {
                    rowHintHoverAbsIndex = realIndex;
                    rowHintHoverLocalY = rowTopLocal;
                }
            }
            if (selected) {
                rowHintSelAbsIndex = realIndex;
                rowHintSelLocalY = rowTopLocal;
            }
        }
        const wchar_t *text = RmlOverlay_MenuItemText((int)realIndex);
        if (g_rowTextCache[k] != text) {
            g_rowTextCache[k] = text;
            if (g_rowText[k]) g_rowText[k]->SetInnerRML(WideToUtf8(text));
        }

        // ── Row thumbnail (Phase 3, Stadiums tab only). RmlUi's own
        // RenderManager/FileTextureDatabase already caches loaded textures
        // by source path (Source/Core/TextureDatabase.h) — repeatedly
        // setting the same src across frames/elements is cheap and shared,
        // so no separate texture cache is needed here, just a per-row
        // reload guard to avoid redundant SetAttribute calls every frame.
        bool stadiumRow = (activeTab == TAB_STADIUMS);
        if (stadiumRow != g_rowStadiumStyled[k]) {
            if (g_row[k]) g_row[k]->SetClass("stadium-row", stadiumRow);
            g_rowStadiumStyled[k] = stadiumRow;
        }
        const wchar_t *thumbPath = stadiumRow ? RmlOverlay_MenuItemThumbPath((int)realIndex) : L"";
        if (g_rowThumbPathLoaded[k] != thumbPath) {
            g_rowThumbPathLoaded[k] = thumbPath;
            if (g_rowThumb[k]) {
                if (thumbPath[0]) {
                    g_rowThumb[k]->SetAttribute("src", WideToUtf8(thumbPath));
                    g_rowThumb[k]->SetProperty("display", "block");
                } else {
                    g_rowThumb[k]->SetProperty("display", "none");
                }
            }
        }
    }

    // ── Row action hint (A/Enter) — the split-preview tabs (Stadiums/Kits)
    // get this inside their hero button instead (see showSplit below);
    // every other tab attaches it to whichever row is hovered, falling back
    // to the selected row when nothing is (see the tracking above the loop).
    {
        long targetAbsIndex = (rowHintHoverAbsIndex >= 0) ? rowHintHoverAbsIndex : rowHintSelAbsIndex;
        float targetLocalY = (rowHintHoverAbsIndex >= 0) ? rowHintHoverLocalY : rowHintSelLocalY;
        bool showRowHint = !showSplit && targetAbsIndex >= 0;
        SetVisible(g_rowActionHint, showRowHint, "block");
        if (showRowHint) {
            const float ROW_HINT_SIZE = 20.f;
            SetRectPx(g_rowActionHint, lListX + adjListW - ROW_HINT_SIZE - 6.f,
                      targetLocalY + (ITEM_H - ROW_HINT_SIZE) / 2.f, ROW_HINT_SIZE, ROW_HINT_SIZE);
            if (gamepadMode) {
                SetIconSrcCached(g_rowActionHint, g_rowActionHintIconLoaded, MAX_IMG, gpDir, kGpIconFiles[GP_A]);
            } else {
                SetIconSrcCached(g_rowActionHint, g_rowActionHintIconLoaded, MAX_IMG, keyDir, kKeyIconFiles[KEY_ENTER]);
            }
        }
    }

    // ── Empty state (overlays the same rect as the list area)
    bool empty = !loading && (itemCount == 0);
    SetVisible(g_emptyState, empty, "flex");
    if (empty) SetRectPx(g_emptyState, lListX, lAdjListY, adjListW, adjScrollH);

    // ── Loading spinner — replaces the (stale) row list/empty-state while
    // Python computes a new one (see the `loading` comment above). Centered
    // over the same rect empty-state uses.
    SetVisible(g_loadingSpinner, loading, "block");
    if (loading) {
        const float SPIN_SIZE = 44.f;
        SetRectPx(g_loadingSpinner,
                  lListX + (adjListW - SPIN_SIZE) / 2.f,
                  lAdjListY + (adjScrollH - SPIN_SIZE) / 2.f,
                  SPIN_SIZE, SPIN_SIZE);
    }

    // ── Scrollbar
    SetRectPx(g_scrollTrack, lScrollX, lAdjListY, SCROLL_W, adjScrollH);
    long maxScrollTotal = (std::max)(0L, totalCount - (long)visibleRows);
    if (!loading && maxScrollTotal > 0) {
        long realScroll = scrollOffset + windowBase;
        float thumbH = (std::max)(22.f, adjScrollH * ((float)visibleRows / (float)totalCount));
        if (thumbH > adjScrollH) thumbH = adjScrollH;
        float thumbRange = (std::max)(1.f, adjScrollH - thumbH);
        float thumbY = ((float)realScroll / (float)maxScrollTotal) * thumbRange;
        SetVisible(g_scrollThumb, true);
        SetRectPx(g_scrollThumb, 1.f, thumbY, SCROLL_W - 2.f, thumbH);
    } else {
        SetVisible(g_scrollThumb, false);
    }

    // ── Split preview / hero panel (stadiums/kits tabs)
    SetVisible(g_splitPreview, showSplit && !loading, "flex");
    if (showSplit) {
        SetRectPx(g_splitPreview, lPrevX, lPrevY, prevSideW, prevSideH);
        const wchar_t *imgPath = RmlOverlay_ImagePath();
        if (wcscmp(imgPath, g_previewPathLoaded) != 0) {
            wcscpy_s(g_previewPathLoaded, imgPath);
            if (g_previewImg) {
                if (imgPath[0]) {
                    g_previewImg->SetAttribute("src", WideToUtf8(imgPath));
                    g_previewImg->SetProperty("display", "block");
                } else {
                    g_previewImg->SetProperty("display", "none");
                }
            }
        }
        // Hero title mirrors the selected item's own row text — no separate
        // "tag"/description data source exists (see the g_heroTitle comment
        // above), so this is deliberately just the item name, not the
        // sketch's fuller flavor copy.
        const wchar_t *heroText = RmlOverlay_MenuItemText((int)selIdx);
        if (g_heroTitleTextLoaded != heroText) {
            g_heroTitleTextLoaded = heroText;
            if (g_heroTitle) g_heroTitle->SetInnerRML(WideToUtf8(heroText));
        }
        // Select (A/Enter) hint, inline next to the "Select" label — the row
        // action hint (above) is deliberately skipped for these tabs instead.
        if (gamepadMode) {
            SetIconSrcCached(g_heroBtnIcon, g_heroBtnIconLoaded, MAX_IMG, gpDir, kGpIconFiles[GP_A]);
        } else {
            SetIconSrcCached(g_heroBtnIcon, g_heroBtnIconLoaded, MAX_IMG, keyDir, kKeyIconFiles[KEY_ENTER]);
        }
        // Grow/press feedback for input methods that don't drive RmlUi's own
        // :hover/:active pseudo-classes — see g_heroHighlightCache's comment.
        if (g_heroBtn) {
            if (gamepadMode != g_heroHighlightCache) {
                g_heroBtn->SetClass("hero-highlight", gamepadMode);
                g_heroHighlightCache = gamepadMode;
            }
            bool activateDown = RmlOverlay_MenuActivateDown();
            if (activateDown != g_heroPressedCache) {
                g_heroBtn->SetClass("hero-pressed", activateDown);
                g_heroPressedCache = activateDown;
            }
        }
    }

    // ── Dashboard (always visible, independent of tab)
    SetRectPx(g_dashboard, lDashX, lDashY, lDashW, DASH_H);
    const wchar_t *homePath = RmlOverlay_HomeCrestPath();
    if (wcscmp(homePath, g_homeCrestPathLoaded) != 0) {
        wcscpy_s(g_homeCrestPathLoaded, homePath);
        if (g_homeCrest) {
            if (homePath[0]) {
                g_homeCrest->SetAttribute("src", WideToUtf8(homePath));
                g_homeCrest->SetProperty("display", "block");
            } else {
                g_homeCrest->SetProperty("display", "none");
            }
        }
    }
    const wchar_t *awayPath = RmlOverlay_AwayCrestPath();
    if (wcscmp(awayPath, g_awayCrestPathLoaded) != 0) {
        wcscpy_s(g_awayCrestPathLoaded, awayPath);
        if (g_awayCrest) {
            if (awayPath[0]) {
                g_awayCrest->SetAttribute("src", WideToUtf8(awayPath));
                g_awayCrest->SetProperty("display", "block");
            } else {
                g_awayCrest->SetProperty("display", "none");
            }
        }
    }
    // #dash-score (crest/score/crest + match clock) only makes sense once a
    // team context exists — same signal ("do we have a crest to show")
    // individual crests already gated on pre-redesign — rather than showing
    // a bare "0 x 0 / 00:00" with no crests on menu screens with no match
    // context (Setup tab, main menu, etc.).
    SetVisible(g_dashScore, homePath[0] != L'\0' || awayPath[0] != L'\0', "flex");
    if (g_dashScoreText) g_dashScoreText->SetInnerRML(WideToUtf8(RmlOverlay_ScoreText()));
    if (g_dashTimeText) g_dashTimeText->SetInnerRML(WideToUtf8(RmlOverlay_MatchTimeText()));
    long dashCount = (std::max)(0L, (std::min)((long)MAX_DASH_ITEMS, RmlOverlay_DashboardItemCount()));
    for (int i = 0; i < MAX_DASH_ITEMS; i++) {
        bool show = (i < dashCount);
        SetVisible(g_dashLine[i], show, "block");
        if (show && g_dashLine[i]) g_dashLine[i]->SetInnerRML(WideToUtf8(RmlOverlay_DashboardItemText(i)));
    }

    // ── Hint bar — only one row shown at a time (keyboard/mouse XOR gamepad,
    // see gamepadMode above). Both rows are still positioned identically
    // every frame (viewport-dependent); icons/labels are only (re)loaded
    // when the icon directory changes (set once by Python shortly after
    // injection, so that's a rare, not per-frame, operation).
    SetVisible(g_hintKeyRow, !gamepadMode, "flex");
    SetVisible(g_hintGpRow, gamepadMode, "flex");
    SetRectPx(g_hintKeyRow, lHintX, lHintY, lHintW, HINT_H);
    SetRectPx(g_hintGpRow, lHintX, lHintY, lHintW, HINT_H);
    if (wcscmp(gpDir, g_gpIconDirLoaded) != 0 &&
        RmlMenu_LoadIconRow(g_hintGpIcon1, g_hintGpIcon2, kGpHints, kGpIconFiles, gpDir)) {
        wcscpy_s(g_gpIconDirLoaded, gpDir);
    }
    if (wcscmp(keyDir, g_keyIconDirLoaded) != 0 &&
        RmlMenu_LoadIconRow(g_hintKeyIcon1, g_hintKeyIcon2, kKeyHints, kKeyIconFiles, keyDir)) {
        wcscpy_s(g_keyIconDirLoaded, keyDir);
    }

    // ── Live mouse feed — deliberately last, after every element above has
    // its final position for this frame, so RmlUi's hit-testing (driven by
    // Context::Update(), called right after RmlMenu_Sync returns) sees
    // up-to-date geometry. Modifier keys (shift/ctrl/etc.) aren't tracked by
    // this simplified feed, so 0 is passed for key_modifier_state.
    Rml::Context *ctx = g_menuDoc->GetContext();
    if (ctx) {
        int mx = (int)RmlOverlay_MenuMouseX();
        int my = (int)RmlOverlay_MenuMouseY();
        ctx->ProcessMouseMove(mx, my, 0);
        bool leftDown = RmlOverlay_MenuMouseLeftDown();
        if (leftDown && !g_mouseLeftWasDown) {
            ctx->ProcessMouseButtonDown(0, 0);
        } else if (!leftDown && g_mouseLeftWasDown) {
            ctx->ProcessMouseButtonUp(0, 0);
        }
        g_mouseLeftWasDown = leftDown;
    }
}

// See the declaration in cgfs16_rmlui_menu.h — lets RmlOverlay_RenderFrame
// know it still has to call RmlMenu_Sync (and thus keep rendering) even
// though menu_visible itself has already flipped to 0, so the close-out
// animation above actually gets frames to run in and its Hide()/state-reset
// eventually happens instead of being starved forever.
bool RmlMenu_DocShown() {
    return g_menuDocShown;
}
