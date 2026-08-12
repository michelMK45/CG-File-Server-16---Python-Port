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
long RmlOverlay_DashboardItemCount();
const wchar_t *RmlOverlay_DashboardItemText(int index);
const wchar_t *RmlOverlay_HomeCrestPath();
const wchar_t *RmlOverlay_AwayCrestPath();
const wchar_t *RmlOverlay_ListHeader();
const wchar_t *RmlOverlay_ImagePath();
const wchar_t *RmlOverlay_GamepadIconDir();
const wchar_t *RmlOverlay_KeyboardIconDir();
long RmlOverlay_MenuMouseX();
long RmlOverlay_MenuMouseY();
bool RmlOverlay_MenuMouseLeftDown();
void RmlOverlay_PushMenuEvent(int kind, int index);

#define MAX_MENU_ITEMS    256
#define MAX_DASH_ITEMS    10
#define NUM_MENU_TABS     5
#define MAX_IMG           512
#define ROW_POOL          64
#define NUM_HINT_ITEMS    5

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
static const HintDef kGpHints[NUM_HINT_ITEMS] = {
    { { GP_DPAD, -1    }, L"Navigate" },
    { { GP_RS,   -1    }, L"Scroll"   },
    { { GP_LB,   GP_RB }, L"Tab"      },
    { { GP_A,    -1    }, L"Select"   },
    { { GP_B,    -1    }, L"Close"    },
};
enum KeyIcon { KEY_UP = 0, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_ENTER, KEY_ESC, KEY_MOUSE, KEY_ICON_COUNT };
static const wchar_t * const kKeyIconFiles[KEY_ICON_COUNT] = {
    L"up.png", L"down.png", L"left.png", L"right.png", L"enter.png", L"esc.png", L"mouse.png",
};
static const HintDef kKeyHints[NUM_HINT_ITEMS] = {
    { { KEY_UP,    KEY_DOWN  }, L"Navigate" },
    { { KEY_MOUSE, -1        }, L"Scroll"   },
    { { KEY_LEFT,  KEY_RIGHT }, L"Tab"      },
    { { KEY_ENTER, -1        }, L"Select"   },
    { { KEY_ESC,   -1        }, L"Close"    },
};

// ---------------------------------------------------------------------------
// Module state
// ---------------------------------------------------------------------------
static Rml::ElementDocument *g_menuDoc = nullptr;
static bool g_menuDocShown = false;

static Rml::Element *g_panel = nullptr;
static Rml::Element *g_tabStrip = nullptr;
static Rml::Element *g_tab[NUM_MENU_TABS] = {};
static Rml::Element *g_contentBg = nullptr;
static Rml::Element *g_wizardHeader = nullptr;
static Rml::Element *g_wizardHeaderText = nullptr;
static Rml::Element *g_listArea = nullptr;
static Rml::Element *g_row[ROW_POOL] = {};
static std::wstring  g_rowTextCache[ROW_POOL];
static bool           g_rowShown[ROW_POOL] = {};
static bool           g_rowSelected[ROW_POOL] = {};
static Rml::Element *g_emptyState = nullptr;
static Rml::Element *g_scrollTrack = nullptr;
static Rml::Element *g_scrollThumb = nullptr;
static Rml::Element *g_splitPreview = nullptr;
static Rml::Element *g_previewImg = nullptr;
static wchar_t        g_previewPathLoaded[MAX_IMG] = {};
static Rml::Element *g_dashboard = nullptr;
static Rml::Element *g_homeCrest = nullptr;
static Rml::Element *g_awayCrest = nullptr;
static wchar_t        g_homeCrestPathLoaded[MAX_IMG] = {};
static wchar_t        g_awayCrestPathLoaded[MAX_IMG] = {};
static Rml::Element *g_dashLine[MAX_DASH_ITEMS] = {};

static Rml::Element *g_hintKeyRow = nullptr;
static Rml::Element *g_hintGpRow = nullptr;
static Rml::Element *g_hintKeyIcon1[NUM_HINT_ITEMS] = {};
static Rml::Element *g_hintKeyIcon2[NUM_HINT_ITEMS] = {};
static Rml::Element *g_hintGpIcon1[NUM_HINT_ITEMS] = {};
static Rml::Element *g_hintGpIcon2[NUM_HINT_ITEMS] = {};
static wchar_t        g_gpIconDirLoaded[MAX_IMG] = {};
static wchar_t        g_keyIconDirLoaded[MAX_IMG] = {};

static bool g_tabActiveCache[NUM_MENU_TABS] = {};
static long g_lastActiveTabForClear = -1;

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
    g_tabStrip = g_menuDoc->GetElementById("tabstrip");
    for (int i = 0; i < NUM_MENU_TABS; i++) {
        char idBuf[8];
        snprintf(idBuf, sizeof(idBuf), "tab%d", i);
        g_tab[i] = g_menuDoc->GetElementById(idBuf);
    }
    g_contentBg = g_menuDoc->GetElementById("content-bg");
    g_wizardHeader = g_menuDoc->GetElementById("wizard-header");
    g_wizardHeaderText = g_menuDoc->GetElementById("wizard-header-text");
    g_listArea = g_menuDoc->GetElementById("list-area");
    for (int i = 0; i < ROW_POOL; i++) {
        char idBuf[8];
        snprintf(idBuf, sizeof(idBuf), "row%d", i);
        g_row[i] = g_menuDoc->GetElementById(idBuf);
    }
    g_emptyState = g_menuDoc->GetElementById("empty-state");
    g_scrollTrack = g_menuDoc->GetElementById("scrollbar-track");
    g_scrollThumb = g_menuDoc->GetElementById("scrollbar-thumb");
    g_splitPreview = g_menuDoc->GetElementById("split-preview");
    g_previewImg = g_menuDoc->GetElementById("preview-img");
    g_dashboard = g_menuDoc->GetElementById("dashboard");
    g_homeCrest = g_menuDoc->GetElementById("home-crest");
    g_awayCrest = g_menuDoc->GetElementById("away-crest");
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
        }
        snprintf(idBuf, sizeof(idBuf), "hintgp%d", i);
        item = g_menuDoc->GetElementById(idBuf);
        if (item) {
            g_hintGpIcon1[i] = item->QuerySelector(".icon1");
            g_hintGpIcon2[i] = item->QuerySelector(".icon2");
            Rml::Element *label = item->QuerySelector(".label");
            if (label) label->SetInnerRML(WideToUtf8(kGpHints[i].description));
        }
    }

    bool ok = g_panel && g_tabStrip && g_contentBg && g_listArea && g_dashboard &&
              g_scrollTrack && g_scrollThumb && g_splitPreview && g_previewImg &&
              g_hintKeyRow && g_hintGpRow;
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

    Log("[RmlMenu] Load ok ('%s')", path.c_str());
    return true;
}

// menu_event_kind values — must match d3d_injector.py's get_menu_event() /
// app_overlay.py's _handle_rmlui_menu_event() docstrings exactly.
enum MenuEventKind { EVK_TAB_CLICK = 1, EVK_ITEM_CLICK = 2, EVK_SCROLL_TO = 3 };

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
        }
    }
}

void RmlMenu_Sync(int vpW, int vpH, void *outputWindow) {
    if (!g_menuDoc) return;

    bool visible = RmlOverlay_MenuVisible();
    if (!visible) {
        if (g_menuDocShown) {
            g_menuDoc->Hide();
            g_menuDocShown = false;
            // Avoid a stuck-drag if the button was still held when the menu
            // closed (e.g. Esc/B while dragging the scrollbar thumb).
            g_mouseLeftWasDown = false;
        }
        return;
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
    const float MW = (std::min)(availW, (std::max)(MENU_MIN_W, floorf(vw * MENU_RATIO_W)));
    const float MH = (std::min)(availH, (std::max)(MENU_MIN_H, floorf(vh * MENU_RATIO_H)));
    const float mx = floorf((vw - MW) / 2.f);
    const float my = floorf((vh - MH) / 2.f);
    const float TAB_H = 56.f;
    const float HINT_H = 38.f;
    const float HINT_ZONE = HINT_H * 2.f + 6.f;
    const float DASH_H = (std::max)(220.f, (std::min)(320.f, floorf(MH * 0.28f)));
    const float ITEM_H = 28.f;
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
    const float lKeyHintY = MH - 2.f - HINT_H * 2.f - 1.f;

    const float baseContentW = MW - 8.f;
    const float listSideW = showSplit ? floorf(baseContentW * SPLIT_FRAC) : baseContentW;
    const float prevSideW = showSplit ? (baseContentW - listSideW - 4.f) : 0.f;
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
    }

    SetRectPx(g_panel, mx, my, MW, MH);
    SetRectPx(g_tabStrip, 2.f, 2.f, MW - 4.f, TAB_H - 2.f);
    SetRectPx(g_contentBg, 2.f, TAB_H + 2.f, MW - 4.f, MH - TAB_H - 4.f);

    for (int i = 0; i < NUM_MENU_TABS; i++) {
        bool active = (i == (int)activeTab);
        if (g_tab[i] && active != g_tabActiveCache[i]) {
            g_tab[i]->SetClass("active", active);
            g_tabActiveCache[i] = active;
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
    for (int k = 0; k < ROW_POOL; k++) {
        long realIndex = scrollOffset + k;
        // Step 4: absolute index (into the full list, not just this window)
        // for MenuEventListener to report on a Click — cached even for
        // out-of-window slots for simplicity; the listener only trusts it
        // when g_rowShown[k] is also true.
        g_rowAbsIndex[k] = windowBase + realIndex;
        bool inWindow = (k < visibleRows) && (realIndex < itemCount);
        if (inWindow != g_rowShown[k]) {
            SetVisible(g_row[k], inWindow, "block");
            g_rowShown[k] = inWindow;
        }
        if (!inWindow) continue;
        bool selected = (realIndex == selIdx);
        if (selected != g_rowSelected[k]) {
            if (g_row[k]) g_row[k]->SetClass("selected", selected);
            g_rowSelected[k] = selected;
        }
        const wchar_t *text = RmlOverlay_MenuItemText((int)realIndex);
        if (g_rowTextCache[k] != text) {
            g_rowTextCache[k] = text;
            if (g_row[k]) g_row[k]->SetInnerRML(WideToUtf8(text));
        }
    }

    // ── Empty state (overlays the same rect as the list area)
    bool empty = (itemCount == 0);
    SetVisible(g_emptyState, empty, "flex");
    if (empty) SetRectPx(g_emptyState, lListX, lAdjListY, adjListW, adjScrollH);

    // ── Scrollbar
    SetRectPx(g_scrollTrack, lScrollX, lAdjListY, SCROLL_W, adjScrollH);
    long maxScrollTotal = (std::max)(0L, totalCount - (long)visibleRows);
    if (maxScrollTotal > 0) {
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

    // ── Split preview (stadiums/kits tabs)
    SetVisible(g_splitPreview, showSplit, "block");
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
    long dashCount = (std::max)(0L, (std::min)((long)MAX_DASH_ITEMS, RmlOverlay_DashboardItemCount()));
    for (int i = 0; i < MAX_DASH_ITEMS; i++) {
        bool show = (i < dashCount);
        SetVisible(g_dashLine[i], show, "block");
        if (show && g_dashLine[i]) g_dashLine[i]->SetInnerRML(WideToUtf8(RmlOverlay_DashboardItemText(i)));
    }

    // ── Hint bars — positions every frame (viewport-dependent); icons/labels
    // only (re)loaded when the icon directory changes (set once by Python
    // shortly after injection, so this is a rare, not per-frame, operation).
    SetRectPx(g_hintKeyRow, lHintX, lKeyHintY, lHintW, HINT_H);
    SetRectPx(g_hintGpRow, lHintX, lHintY, lHintW, HINT_H);
    const wchar_t *gpDir = RmlOverlay_GamepadIconDir();
    if (wcscmp(gpDir, g_gpIconDirLoaded) != 0 &&
        RmlMenu_LoadIconRow(g_hintGpIcon1, g_hintGpIcon2, kGpHints, kGpIconFiles, gpDir)) {
        wcscpy_s(g_gpIconDirLoaded, gpDir);
    }
    const wchar_t *keyDir = RmlOverlay_KeyboardIconDir();
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
