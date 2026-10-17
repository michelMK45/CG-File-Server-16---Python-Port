"""Kits > Team subtab ("Classic" in the code): build per-team kit combinations from the team's own kits
(shirt, shorts and socks each from a different kit type) and choose which one the
team wears at home and away. See kit_classic.py for the team_<id>.lua side.

Every change is written straight to the team's lua (there is no separate Apply
step): the game only reads it when a match loads, and the write is atomic.

Self-contained widget, like rx3_texture_preview.Rx3TexturePreview: it only uses
`app` for colours, tr(), the shared team id (app.kitmix_team_id, also used by
the Simple/Advanced subtabs), team names and app.kit_classic.
"""

from __future__ import annotations

import io
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Hashable, Optional

from PIL import Image, ImageTk

from .kit_art_preview import IconLoader, KitArtPreview, Sources
from .kit_classic import PART_MAX, Combination, Mix, TeamCombinations, encode_parts
from .kit_classic_art import art_size
from .team_picker_dialog import TeamPickerDialog

CARD_ICON_SIZE = 46
PREVIEW_ICON_SIZE = 110
GK_ICON_SIZE = 30
FALLBACK_KIT_TYPES = (0, 1, 2, 3)
HOME_BADGE_BG = "#2e7d32"
AWAY_BADGE_BG = "#e65100"
WARNING_FG = "#FFAA00"
STRIP_DRAG_THRESHOLD = 5   # pixels a press must move before it scrolls instead of clicking

IconKey = tuple[int, int, int, int, int, int]   # team, tourn, shirt, shorts, socks, size


class KitClassicTab:
    def __init__(self, parent: tk.Misc, app) -> None:
        self.app = app
        self.runtime = app.kit_classic
        self.team: Optional[int] = None
        self._states: dict[int, TeamCombinations] = {}
        self._editing: dict[int, int] = {}
        self._card_photos: dict[IconKey, ImageTk.PhotoImage] = {}
        self._card_icon_labels: dict[IconKey, list[tk.Label]] = {}
        self._listed_mix_keys: list[tuple[int, int]] = []
        self._editable_widgets: list[tk.Widget] = []

        self._build(parent)
        self._card_loader = IconLoader(self.strip_canvas, self.runtime.art_lock, self._on_card_icon)

    # ------------------------------------------------------------------ build
    def _build(self, parent: tk.Misc) -> None:
        app = self.app
        outer = tk.Frame(parent, bg=app.bg)
        outer.pack(fill="both", expand=True, padx=10, pady=10)
        card = app._card(outer, "card.kitclassic.title", "card.kitclassic.subtitle")
        card.pack(fill="both", expand=True)
        # Packed right under the card header (subtitle), before anything else;
        # wraps to the card's width.
        note = tk.Label(card, text=app.tr("kitclassic.menu_note"), bg=app.card, fg=WARNING_FG, anchor="w",
                        justify="left", wraplength=1000, font=("Bahnschrift", 9, "bold"))
        note.pack(fill="x", padx=12, pady=(0, 8))
        card.bind("<Configure>", lambda e: note.configure(wraplength=max(200, e.width - 24)), add="+")

        footer = tk.Frame(card, bg=app.card)
        footer.pack(side="bottom", fill="x", padx=12, pady=(6, 12))
        self.status_label = tk.Label(
            footer, text=app.display_value("idle"), bg=app.card, fg=app.muted, font=("Bahnschrift", 9),
            anchor="w", justify="left", wraplength=1000,
        )
        self.status_label.pack(fill="x")

        scroll_host = tk.Frame(card, bg=app.card)
        scroll_host.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        canvas = tk.Canvas(scroll_host, bg=app.card, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(scroll_host, orient="vertical", command=canvas.yview, style="Server16.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(canvas, bg=app.card)
        body_win = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(body_win, width=e.width))
        self.body_canvas = canvas
        self.body = body
        # add="+" -- see the dashboard's bind_all for why this must not replace
        # other tabs' scoped mousewheel handlers.
        canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

        # team row
        top = tk.Frame(body, bg=app.card)
        top.pack(fill="x", pady=(0, 6))
        app._dark_label(top, app.tr("dialog.kitmix.team_id"), bg=app.card, muted=True).pack(side="left")
        team_entry = ttk.Entry(top, textvariable=app.kitmix_team_id, width=10)
        team_entry.pack(side="left", padx=(6, 12))
        team_entry.bind("<Return>", lambda _e: self.refresh())
        team_entry.bind("<FocusOut>", lambda _e: self._refresh_if_team_changed())
        ttk.Button(top, text=app.tr("button.use_home_team"), command=lambda: self._use_match_team(app.HID)).pack(side="left", padx=(0, 6))
        ttk.Button(top, text=app.tr("button.use_away_team"), command=lambda: self._use_match_team(app.AID)).pack(side="left", padx=(0, 6))
        ttk.Button(top, text=app.tr("button.pick_team"), command=self._pick_team).pack(side="left", padx=(0, 6))
        ttk.Button(top, text=app.tr("dialog.kitmix.refresh"), command=lambda: self.refresh(reload=True)).pack(side="left")
        self.team_name_label = app._dark_label(top, "", bg=app.card, muted=True)
        self.team_name_label.pack(side="left", padx=(12, 0))

        # Packed only while it has text (see _refresh_warning), right above combo_bar.
        self.warning_label = tk.Label(
            body, text="", bg=app.card, fg=WARNING_FG, anchor="w", justify="left", wraplength=900, font=("Bahnschrift", 9),
        )

        # combinations
        combo_bar = tk.Frame(body, bg=app.card)
        combo_bar.pack(fill="x", pady=(0, 4))
        self._combo_bar = combo_bar
        app._dark_label(combo_bar, app.tr("kitclassic.combinations"), bg=app.card, muted=True).pack(side="left", padx=(0, 10))
        for key, command in (("kitclassic.new", self._new_combination), ("kitclassic.duplicate", self._duplicate_combination),
                             ("kitclassic.delete", self._delete_combination)):
            button = ttk.Button(combo_bar, text=app.tr(key), command=command)
            button.pack(side="left", padx=(0, 6))
            self._editable_widgets.append(button)
        app._dark_label(combo_bar, app.tr("kitclassic.name"), bg=app.card, muted=True).pack(side="left", padx=(12, 4))
        self.name_var = tk.StringVar()
        name_entry = ttk.Entry(combo_bar, textvariable=self.name_var, width=24)
        name_entry.pack(side="left", padx=(0, 6))
        name_entry.bind("<Return>", lambda _e: self._rename_combination())
        rename = ttk.Button(combo_bar, text=app.tr("kitclassic.rename"), command=self._rename_combination)
        rename.pack(side="left")
        self._editable_widgets += [name_entry, rename]

        # No scrollbar: the strip scrolls by dragging it (see _on_strip_press), and
        # the mouse wheel stays with the page.
        strip = tk.Frame(body, bg=app.card_soft, highlightthickness=1, highlightbackground="#243654")
        strip.pack(fill="x", pady=(0, 6))
        self.strip_canvas = tk.Canvas(strip, height=art_size(CARD_ICON_SIZE)[1] + 60, bg=app.card_soft, highlightthickness=0, bd=0)
        self.strip_canvas.pack(fill="x")
        self.strip_inner = tk.Frame(self.strip_canvas, bg=app.card_soft)
        self.strip_canvas.create_window((0, 0), window=self.strip_inner, anchor="nw")
        self.strip_inner.bind("<Configure>", lambda _e: self.strip_canvas.configure(scrollregion=self.strip_canvas.bbox("all")))
        self._strip_drag_x: Optional[int] = None
        self._strip_dragged = False
        self._strip_team: Optional[int] = None
        for widget in (self.strip_canvas, self.strip_inner):
            self._bind_strip_drag(widget)

        sel_row = tk.Frame(body, bg=app.card)
        sel_row.pack(fill="x", pady=(0, 8))
        self.home_var = tk.StringVar()
        self.away_var = tk.StringVar()
        self.home_combo = self._labeled_combo(sel_row, "kitclassic.home_uses", self.home_var, 30)
        self.away_combo = self._labeled_combo(sel_row, "kitclassic.away_uses", self.away_var, 30)
        self.home_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_side_selected(0))
        self.away_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_side_selected(1))
        self._editable_widgets += [self.home_combo, self.away_combo]

        gk_row = tk.Frame(body, bg=app.card)
        gk_row.pack(fill="x", pady=(0, 8))
        self.gk_vars = (tk.StringVar(), tk.StringVar())
        self.gk_combos: list[ttk.Combobox] = []
        self.gk_thumbs: list[KitArtPreview] = []
        self._gk_options: list[list[Optional[int]]] = [[], []]
        for side, key in ((0, "kitclassic.home_gk"), (1, "kitclassic.away_gk")):
            combo = self._labeled_combo(gk_row, key, self.gk_vars[side], 14)
            combo.pack_configure(padx=(0, 6))
            combo.bind("<<ComboboxSelected>>", lambda _e, s=side: self._on_gk_selected(s))
            thumb = KitArtPreview(gk_row, app, GK_ICON_SIZE, framed=False, bg=app.card)
            thumb.pack(side="left", padx=(0, 18))
            self.gk_combos.append(combo)
            self.gk_thumbs.append(thumb)
        app._dark_label(gk_row, app.tr("kitclassic.gk_hint"), bg=app.card, muted=True, font=("Bahnschrift", 8),
                        wraplength=320, justify="left").pack(side="left")
        self._editable_widgets += self.gk_combos

        # mix editor + preview
        editor = tk.Frame(body, bg=app.card)
        editor.pack(fill="x", pady=(0, 6))
        preview_box = tk.Frame(editor, bg=app.card_soft, highlightthickness=1, highlightbackground="#243654")
        preview_box.pack(side="right", anchor="n")
        form = tk.Frame(editor, bg=app.card)
        form.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.tourn_var = tk.StringVar(value="0")
        self.slot_var = tk.StringVar()
        self.shirt_var = tk.StringVar()
        self.shorts_var = tk.StringVar()
        self.socks_var = tk.StringVar()
        self.tourn_combo = self._form_row(form, 0, "kitclassic.tournament", self.tourn_var, "kitclassic.tournament_hint", readonly=True)
        self.slot_combo = self._form_row(form, 1, "kitclassic.requested_kit", self.slot_var, "kitclassic.requested_hint")
        self.shirt_combo = self._form_row(form, 2, "kitclassic.shirt_from", self.shirt_var)
        self.shorts_combo = self._form_row(form, 3, "kitclassic.shorts_from", self.shorts_var)
        self.socks_combo = self._form_row(form, 4, "kitclassic.socks_from", self.socks_var)
        self.tourn_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_tourn_changed())
        for combo in (self.slot_combo, self.shirt_combo, self.shorts_combo, self.socks_combo):
            combo.bind("<<ComboboxSelected>>", self._on_part_changed)
            combo.bind("<Return>", self._on_part_changed)
            combo.bind("<FocusOut>", self._on_part_changed)

        self.code_label = tk.Label(form, text="", bg=app.card, fg=app.accent, anchor="w", font=("Consolas", 9))
        self.code_label.grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 4))
        buttons = tk.Frame(form, bg=app.card)
        buttons.grid(row=6, column=0, columnspan=3, sticky="w", pady=(0, 6))
        add = ttk.Button(buttons, text=app.tr("kitclassic.add_mix"), command=self._add_mix)
        add.pack(side="left", padx=(0, 6))
        remove = ttk.Button(buttons, text=app.tr("kitclassic.remove_mix"), command=self._remove_mix)
        remove.pack(side="left")
        self._editable_widgets += [add, remove]
        self.mix_list = app._dark_listbox(form, exportselection=False, height=6, font=("Consolas", 10))
        self.mix_list.grid(row=7, column=0, columnspan=3, sticky="ew")
        self.mix_list.bind("<<ListboxSelect>>", self._on_mix_selected)
        form.grid_columnconfigure(2, weight=1)

        tk.Label(preview_box, text=app.tr("kitclassic.preview"), bg=app.card_soft, fg=app.muted, font=("Bahnschrift", 9)).pack(
            anchor="w", padx=8, pady=(8, 2),
        )
        self.preview = KitArtPreview(preview_box, app, PREVIEW_ICON_SIZE, zoom_title=app.tr("kitclassic.preview"))
        self.preview.configure(highlightthickness=0)
        self.preview.pack(padx=0, pady=(0, 4))

    def _labeled_combo(self, parent: tk.Misc, key: str, var: tk.StringVar, width: int) -> ttk.Combobox:
        self.app._dark_label(parent, self.app.tr(key), bg=self.app.card, muted=True).pack(side="left", padx=(0, 6))
        combo = ttk.Combobox(parent, state="readonly", textvariable=var, width=width, style="Server16.TCombobox")
        combo.pack(side="left", padx=(0, 18))
        return combo

    def _form_row(self, parent: tk.Misc, row: int, key: str, var: tk.StringVar, hint_key: str = "",
                  readonly: bool = False) -> ttk.Combobox:
        app = self.app
        app._dark_label(parent, app.tr(key), bg=app.card, muted=True).grid(row=row, column=0, sticky="w", pady=2)
        combo = ttk.Combobox(parent, textvariable=var, width=8, state="readonly" if readonly else "normal",
                             style="Server16.TCombobox")
        combo.grid(row=row, column=1, sticky="w", padx=(8, 8), pady=2)
        if hint_key:
            app._dark_label(parent, app.tr(hint_key), bg=app.card, muted=True, font=("Bahnschrift", 8)).grid(
                row=row, column=2, sticky="w",
            )
        self._editable_widgets.append(combo)
        return combo

    def _on_mousewheel(self, event) -> None:
        app = self.app
        if app.tabview is None:
            return
        try:
            if app.tabview.nametowidget(app.tabview.select()) is not app.kits_tab:
                return
        except Exception:
            return
        if app._event_widget_belongs_to(event, self.body_canvas, self.body):
            self.body_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # Combination strip: press and drag scrolls it sideways; a press released
    # without moving more than STRIP_DRAG_THRESHOLD pixels is a click (selects
    # the card under it, if any). scan_mark/scan_dragto keep the view inside the
    # scroll region, so a strip that fits doesn't move.
    def _bind_strip_drag(self, widget: tk.Widget, index: Optional[int] = None) -> None:
        widget.bind("<ButtonPress-1>", self._on_strip_press)
        widget.bind("<B1-Motion>", self._on_strip_motion)
        widget.bind("<ButtonRelease-1>", lambda _e, i=index: self._on_strip_release(i))

    def _on_strip_press(self, event) -> None:
        self._strip_drag_x = event.x_root
        self._strip_dragged = False
        self.strip_canvas.scan_mark(event.x_root - self.strip_canvas.winfo_rootx(), 0)

    def _on_strip_motion(self, event) -> None:
        if self._strip_drag_x is None:
            return
        if not self._strip_dragged and abs(event.x_root - self._strip_drag_x) < STRIP_DRAG_THRESHOLD:
            return
        self._strip_dragged = True
        self.strip_canvas.scan_dragto(event.x_root - self.strip_canvas.winfo_rootx(), 0, gain=1)

    def _on_strip_release(self, index: Optional[int]) -> None:
        dragged = self._strip_dragged
        self._strip_drag_x, self._strip_dragged = None, False
        if index is not None and not dragged:
            self._select_combination(index)

    # ------------------------------------------------------------------ team
    def on_shown(self) -> None:
        app = self.app
        if not app.kitmix_team_id.get().strip():
            default_team = app.HID or app.AID or ""
            if default_team:
                app.kitmix_team_id.set(default_team)
        self.refresh()

    def _use_match_team(self, team_id: str) -> None:
        team_id = (team_id or "").strip()
        if not team_id:
            messagebox.showwarning(self.app.tr("message.kitmix"), self.app.tr("message.kitmix.no_match_team"))
            return
        self.app.kitmix_team_id.set(team_id)
        self.refresh()

    def _pick_team(self) -> None:
        dialog = TeamPickerDialog(self.app)
        self.app.wait_window(dialog)
        if dialog.result:
            self.app.kitmix_team_id.set(dialog.result)
            self.refresh()

    def _refresh_if_team_changed(self) -> None:
        raw = self.app.kitmix_team_id.get().strip()
        if (int(raw) if raw.isdigit() else None) != self.team:
            self.refresh()

    def refresh(self, reload: bool = False) -> None:
        """Re-read the team id and show its combinations. `reload` drops this
        session's copy of the team and rescans the kit folder, picking up changes
        made outside the app (by hand or with Dinei's standalone tool)."""
        app = self.app
        raw = app.kitmix_team_id.get().strip()
        previous = self.team
        self.team = int(raw) if raw.isdigit() else None
        if self.team != previous:
            self.tourn_var.set("0")
            self.slot_var.set("")
        if reload:
            self.runtime.kits(refresh=True)
            if self.team is not None:
                self._states.pop(self.team, None)
        name = app._resolve_team_name(raw) if self.team is not None else None
        self.team_name_label.configure(text=name or "")
        if self.team is not None:
            try:
                self._state()
            except Exception as exc:  # noqa: BLE001 - unreadable team lua
                app.log(f"Kits Classic: could not read team {self.team} lua", exc)
                self._set_status(app.tr("kitclassic.status.read_failed", error=exc), error=True)
                self.team = None
        self._refresh_warning()
        self._refresh_all()

    def _state(self) -> Optional[TeamCombinations]:
        if self.team is None:
            return None
        tc = self._states.get(self.team)
        if tc is None:
            tc = self.runtime.load(self.team) or TeamCombinations(self.team)
            if not tc.items:
                tc.items.append(Combination(self.app.tr("kitclassic.default_name", n=1)))
            self._states[self.team] = tc
        return tc

    def _editing_index(self) -> int:
        tc = self._state()
        if tc is None or not tc.items:
            return 0
        idx = self._editing.get(tc.team, 0)
        return idx if 0 <= idx < len(tc.items) else 0

    def _current(self) -> Optional[Combination]:
        tc = self._state()
        return tc.items[self._editing_index()] if tc is not None and tc.items else None

    def _can_edit(self) -> bool:
        return self.app.fifaEXE != "default" and self.team is not None and self.runtime.is_supported()

    def _refresh_warning(self) -> None:
        app = self.app
        lines = []
        if app.fifaEXE == "default":
            lines.append(app.tr("message.warning.select_fifa_first"))
        else:
            missing = self.runtime.missing_player_lua_functions()
            if missing is None:
                lines.append(app.tr("kitclassic.no_player_lua"))
            elif missing:
                lines.append(app.tr("kitclassic.unsupported", functions=", ".join(missing)))
            if self.team is None:
                lines.append(app.tr("kitclassic.enter_team"))
            elif not self.runtime.team_kits(self.team):
                lines.append(app.tr("kitclassic.no_loose_kits"))
            tc = self._states.get(self.team) if self.team is not None else None
            conflicts = tc.side_conflicts() if tc is not None else []
            if conflicts:
                slots = ", ".join(str(slot) for slot in sorted({slot for _tourn, slot in conflicts}))
                lines.append(app.tr("kitclassic.side_conflict", slots=slots))
        self.warning_label.configure(text="\n".join(lines))
        if lines:
            self.warning_label.pack(fill="x", pady=(0, 6), before=self._combo_bar)
        else:
            self.warning_label.pack_forget()
        state ="normal" if self._can_edit() else "disabled"
        for widget in self._editable_widgets:
            try:
                if isinstance(widget, ttk.Combobox):
                    readonly = widget in (self.tourn_combo, self.home_combo, self.away_combo, *self.gk_combos)
                    widget.configure(state=("readonly" if readonly else "normal") if state == "normal" else "disabled")
                else:
                    widget.configure(state=state)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------ views
    def _refresh_all(self) -> None:
        self._rebuild_cards()
        self._refresh_selection_combos()
        self._refresh_gk_combos()
        self._refresh_kit_choices()
        self._refresh_mix_list()
        current = self._current()
        self.name_var.set(current.name if current else "")
        self._fill_from_slot()
        self._update_preview()

    def _combo_labels(self, tc: TeamCombinations) -> list[str]:
        return [self.app.tr("kitclassic.original_kits")] + [f"{i + 1}. {c.name}" for i, c in enumerate(tc.items)]

    def _refresh_selection_combos(self) -> None:
        tc = self._state()
        if tc is None:
            for combo, var in ((self.home_combo, self.home_var), (self.away_combo, self.away_var)):
                combo.configure(values=())
                var.set("")
            return
        labels = self._combo_labels(tc)
        for combo, var, sel in ((self.home_combo, self.home_var, tc.home), (self.away_combo, self.away_var, tc.away)):
            combo.configure(values=tuple(labels))
            sel = tc.selection_valid(sel)
            var.set(labels[0 if sel is None else sel + 1])

    def _refresh_gk_combos(self) -> None:
        """Goalkeeper dropdowns: Automatic + the team's goalkeeper kits (plus the saved
        one if it isn't among them, e.g. set by Dinei's tool for a kit that isn't
        loose here), and a thumbnail of each side's forced kit."""
        app = self.app
        tc = self._state()
        for side in (0, 1):
            combo, var, thumb = self.gk_combos[side], self.gk_vars[side], self.gk_thumbs[side]
            if tc is None:
                self._gk_options[side] = []
                combo.configure(values=())
                var.set("")
                thumb.show(None)
                continue
            current = tc.gk_home if side == 0 else tc.gk_away
            kits = self.runtime.gk_kit_options(tc.team)
            if current is not None and current not in kits:
                kits = sorted(kits + [current])
            self._gk_options[side] = [None, *kits]
            labels = [app.tr("kitclassic.gk_auto")] + [app.tr("kitclassic.gk_kit", kit=k) for k in kits]
            combo.configure(values=tuple(labels))
            var.set(labels[self._gk_options[side].index(current)])
            if current is None:
                thumb.show(None)
            else:
                side_key = "kitclassic.home_gk" if side == 0 else "kitclassic.away_gk"
                thumb.zoom_title = f"{app.tr(side_key).rstrip(':')} · {app.tr('kitclassic.gk_kit', kit=current)}"
                thumb.show(self._team_sources(tc.team, 0, current, current, current))

    def _team_sources(self, team: int, tourn: int, shirt: int, shorts: int, socks: int) -> Sources:
        path = self.runtime.kit_path
        return path(team, tourn, shirt), path(team, tourn, shorts), path(team, tourn, socks)

    def _on_gk_selected(self, side: int) -> None:
        tc = self._state()
        if tc is None or not self._can_edit():
            return
        labels = list(self.gk_combos[side].cget("values"))
        label = self.gk_vars[side].get()
        if label not in labels:
            return
        kit = self._gk_options[side][labels.index(label)]
        if side == 0:
            tc.gk_home = kit
        else:
            tc.gk_away = kit
        self._refresh_gk_combos()
        self._save()

    def _rebuild_cards(self) -> None:
        app = self.app
        tc = self._state()
        # Same team: keep the strip where the user dragged it (clicking a card
        # rebuilds the strip); another team starts at the left.
        keep_x = self.strip_canvas.xview()[0] if tc is not None and tc.team == self._strip_team else 0.0
        self._strip_team = tc.team if tc is not None else None
        for child in self.strip_inner.winfo_children():
            child.destroy()
        self._card_photos.clear()
        self._card_icon_labels = {}
        if tc is None:
            self._card_loader.request([])
            return
        editing = self._editing_index()
        keys: list[IconKey] = []
        placeholder_w, placeholder_h = art_size(CARD_ICON_SIZE)
        for i, combo in enumerate(tc.items):
            active = i == editing
            bg = "#19324d" if active else app.card
            card = tk.Frame(self.strip_inner, bg=bg, highlightthickness=2 if active else 1,
                            highlightbackground=app.accent if active else "#243654", padx=6, pady=4)
            card.pack(side="left", padx=4, pady=4, anchor="n")
            head = tk.Frame(card, bg=bg)
            head.pack(anchor="w", fill="x")
            title = tk.Label(head, text=f"{i + 1}. {combo.name}", bg=bg, fg=app.fg, font=("Bahnschrift", 9, "bold"))
            title.pack(side="left")
            if tc.selection_valid(tc.home) == i:
                tk.Label(head, text=f" {app.tr('kitclassic.badge_home')} ", bg=HOME_BADGE_BG, fg="white",
                         font=("Bahnschrift", 7, "bold")).pack(side="left", padx=(6, 0))
            if tc.selection_valid(tc.away) == i:
                tk.Label(head, text=f" {app.tr('kitclassic.badge_away')} ", bg=AWAY_BADGE_BG, fg="white",
                         font=("Bahnschrift", 7, "bold")).pack(side="left", padx=(4, 0))
            icons = tk.Frame(card, bg=bg)
            icons.pack(anchor="w", pady=(4, 0))
            if not combo.mixes:
                tk.Label(icons, text=app.tr("kitclassic.no_mixes"), bg=bg, fg=app.muted,
                         font=("Bahnschrift", 8), height=4).pack(padx=8)
            for mix in sorted(combo.mixes, key=lambda m: m.key):
                key: IconKey = (tc.team, mix.tourn, mix.shirt, mix.shorts, mix.socks, CARD_ICON_SIZE)
                cell = tk.Frame(icons, bg=bg)
                cell.pack(side="left", padx=(0, 6))
                image_label = tk.Label(cell, bg=bg, width=placeholder_w, height=placeholder_h, bd=0,
                                       image=self._blank_image(placeholder_w, placeholder_h))
                image_label.pack()
                caption = app.tr("kitclassic.card_kit", slot=mix.slot)
                if mix.tourn:
                    caption += f" T{mix.tourn}"
                tk.Label(cell, text=caption, bg=bg, fg=app.muted, font=("Bahnschrift", 8)).pack()
                self._card_icon_labels.setdefault(key, []).append(image_label)
                keys.append(key)
            # Every widget of the card, badges included, so a drag can start anywhere.
            pending: list[tk.Widget] = [card]
            while pending:
                widget = pending.pop()
                pending += widget.winfo_children()
                self._bind_strip_drag(widget, i)
                widget.configure(cursor="hand2")
        self.strip_inner.update_idletasks()
        self.strip_canvas.configure(scrollregion=self.strip_canvas.bbox("all"))
        self.strip_canvas.xview_moveto(keep_x)
        art = self.runtime.art
        self._card_loader.request([(key, lambda k=key: art.icon_png(*k)) for key in keys])

    def _blank_image(self, w: int, h: int) -> tk.PhotoImage:
        cache = getattr(self, "_blank_images", None)
        if cache is None:
            cache = self._blank_images = {}
        if (w, h) not in cache:
            cache[(w, h)] = tk.PhotoImage(width=w, height=h)
        return cache[(w, h)]

    def _on_card_icon(self, key: Hashable, png: Optional[bytes]) -> None:
        labels = self._card_icon_labels.get(key)
        if not labels or png is None:
            return
        try:
            photo = ImageTk.PhotoImage(Image.open(io.BytesIO(png)))
        except Exception:  # noqa: BLE001
            return
        self._card_photos[key] = photo
        for label in labels:
            try:
                label.configure(image=photo, width=photo.width(), height=photo.height())
            except tk.TclError:
                pass

    def _refresh_kit_choices(self) -> None:
        if self.team is None:
            for combo in (self.tourn_combo, self.slot_combo, self.shirt_combo, self.shorts_combo, self.socks_combo):
                combo.configure(values=())
            return
        by_tourn = self.runtime.team_kits(self.team)
        tourns = sorted(by_tourn) or [0]
        self.tourn_combo.configure(values=tuple(str(t) for t in tourns))
        if self._read_int(self.tourn_var) not in tourns:
            self.tourn_var.set(str(0 if 0 in tourns else tourns[0]))
        self._refresh_type_choices()

    def _refresh_type_choices(self) -> None:
        if self.team is None:
            return
        by_tourn = self.runtime.team_kits(self.team)
        types = sorted(by_tourn.get(self._read_int(self.tourn_var) or 0) or by_tourn.get(0) or FALLBACK_KIT_TYPES)
        values = tuple(str(t) for t in types)
        for combo in (self.slot_combo, self.shirt_combo, self.shorts_combo, self.socks_combo):
            combo.configure(values=values)
        if self._read_int(self.slot_var) is None:
            self.slot_var.set(values[0])

    def _refresh_mix_list(self) -> None:
        app = self.app
        self.mix_list.delete(0, "end")
        self._listed_mix_keys = []
        current = self._current()
        if current is None:
            return
        for mix in sorted(current.mixes, key=lambda m: m.key):
            if mix.is_identity:
                text = app.tr("kitclassic.mix_row_original", slot=mix.slot)
            else:
                text = app.tr("kitclassic.mix_row", slot=mix.slot, shirt=mix.shirt, shorts=mix.shorts, socks=mix.socks)
            if mix.tourn:
                text += app.tr("kitclassic.mix_tourn_suffix", tourn=mix.tourn)
            self.mix_list.insert("end", text)
            self._listed_mix_keys.append(mix.key)

    @staticmethod
    def _read_int(var: tk.StringVar) -> Optional[int]:
        value = var.get().strip()
        return int(value) if value.isdigit() else None

    def _read_parts(self) -> Optional[tuple[int, int, int, int, int]]:
        values = [self._read_int(v) for v in (self.tourn_var, self.slot_var, self.shirt_var, self.shorts_var, self.socks_var)]
        if any(v is None for v in values) or any(v > PART_MAX for v in values[1:]):
            return None
        return tuple(values)  # type: ignore[return-value]

    def _fill_from_slot(self) -> None:
        """Shirt/shorts/socks of the mix the current combination already has for the
        requested slot, or the slot's own kit when it has none."""
        slot = self._read_int(self.slot_var)
        if slot is None:
            return
        tourn = self._read_int(self.tourn_var) or 0
        current = self._current()
        for mix in (current.mixes if current else []):
            if mix.key == (tourn, slot):
                self.shirt_var.set(str(mix.shirt))
                self.shorts_var.set(str(mix.shorts))
                self.socks_var.set(str(mix.socks))
                return
        for var in (self.shirt_var, self.shorts_var, self.socks_var):
            var.set(str(slot))

    def _update_preview(self) -> None:
        parts = self._read_parts()
        if self.team is None or parts is None:
            self.code_label.configure(text="")
            self.preview.show(None)
            return
        tourn, slot, shirt, shorts, socks = parts
        mix = Mix(tourn, slot, shirt, shorts, socks)
        self.code_label.configure(text=self.app.tr("kitclassic.code", code=mix.code if mix.is_identity else encode_parts(shirt, shorts, socks)))
        self.preview.show(self._team_sources(self.team, tourn, shirt, shorts, socks))

    # ------------------------------------------------------------------ events
    def _on_tourn_changed(self) -> None:
        self._refresh_type_choices()
        self._fill_from_slot()
        self._update_preview()

    def _on_part_changed(self, event=None) -> None:
        if event is not None and event.widget is self.slot_combo:
            self._fill_from_slot()
        self._update_preview()

    def _on_mix_selected(self, _event=None) -> None:
        selection = self.mix_list.curselection()
        current = self._current()
        if not selection or current is None or selection[0] >= len(self._listed_mix_keys):
            return
        key = self._listed_mix_keys[selection[0]]
        mix = next((m for m in current.mixes if m.key == key), None)
        if mix is None:
            return
        if str(mix.tourn) in self.tourn_combo.cget("values") and self._read_int(self.tourn_var) != mix.tourn:
            self.tourn_var.set(str(mix.tourn))
            self._refresh_type_choices()
        self.slot_var.set(str(mix.slot))
        self.shirt_var.set(str(mix.shirt))
        self.shorts_var.set(str(mix.shorts))
        self.socks_var.set(str(mix.socks))
        self._update_preview()

    def _select_combination(self, index: int) -> None:
        tc = self._state()
        if tc is None or not 0 <= index < len(tc.items):
            return
        self._editing[tc.team] = index
        self._rebuild_cards()
        self._refresh_mix_list()
        self.name_var.set(tc.items[index].name)
        self._fill_from_slot()
        self._update_preview()

    def _on_side_selected(self, side: int) -> None:
        tc = self._state()
        if tc is None or not self._can_edit():
            return
        combo = self.home_combo if side == 0 else self.away_combo
        values = list(combo.cget("values"))
        label = (self.home_var if side == 0 else self.away_var).get()
        if label not in values:
            return
        index = values.index(label)
        selection = None if index == 0 else index - 1
        if side == 0:
            tc.home = selection
        else:
            tc.away = selection
        self._rebuild_cards()
        self._refresh_warning()
        self._save()

    # ------------------------------------------------------------------ editing
    def _add_mix(self) -> None:
        current = self._current()
        if current is None or not self._can_edit():
            return
        parts = self._read_parts()
        if parts is None:
            self._set_status(self.app.tr("kitclassic.status.invalid_parts", max=PART_MAX), error=True)
            return
        current.set_mix(Mix(*parts))
        self._after_change()

    def _remove_mix(self) -> None:
        selection = self.mix_list.curselection()
        current = self._current()
        if not selection or current is None or not self._can_edit() or selection[0] >= len(self._listed_mix_keys):
            return
        current.remove_mix(self._listed_mix_keys[selection[0]])
        self._after_change()

    def _new_combination(self) -> None:
        tc = self._state()
        if tc is None or not self._can_edit():
            return
        tc.items.append(Combination(tc.unique_name(self.app.tr("kitclassic.default_name", n=len(tc.items) + 1))))
        self._editing[tc.team] = len(tc.items) - 1
        self._after_change()

    def _duplicate_combination(self) -> None:
        tc = self._state()
        current = self._current()
        if tc is None or current is None or not self._can_edit():
            return
        name = tc.unique_name(current.name + self.app.tr("kitclassic.copy_suffix"))
        tc.items.append(Combination(name, list(current.mixes)))
        self._editing[tc.team] = len(tc.items) - 1
        self._after_change()

    def _delete_combination(self) -> None:
        tc = self._state()
        current = self._current()
        if tc is None or current is None or not self._can_edit():
            return
        if not messagebox.askyesno(self.app.tr("message.kitmix"), self.app.tr("kitclassic.confirm_delete", name=current.name)):
            return
        index = self._editing_index()
        if len(tc.items) == 1:
            current.mixes = []
        else:
            tc.remove(index)
            self._editing[tc.team] = min(index, len(tc.items) - 1)
        self._after_change()

    def _rename_combination(self) -> None:
        current = self._current()
        name = self.name_var.get().strip()
        if current is None or not name or name == current.name or not self._can_edit():
            return
        current.name = name
        self._after_change()

    def _after_change(self) -> None:
        self._rebuild_cards()
        self._refresh_selection_combos()
        self._refresh_mix_list()
        current = self._current()
        self.name_var.set(current.name if current else "")
        self._update_preview()
        self._refresh_warning()
        self._save()

    def _save(self) -> None:
        tc = self._state()
        if tc is None:
            return
        app = self.app
        try:
            path, clashes = self.runtime.save(tc)
        except Exception as exc:  # noqa: BLE001 - surfaced in the status line
            app.log(f"Kits Classic: could not save team {tc.team}", exc)
            self._set_status(app.tr("kitclassic.status.save_failed", error=exc), error=True)
            return
        text = app.tr("kitclassic.status.saved", file=path.name)
        if clashes:
            slots = ", ".join(str(slot) for _tourn, slot in clashes)
            text += "  " + app.tr("kitclassic.status.clash", slots=slots)
        self._set_status(text)

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status_label.configure(text=text, fg=self.app.error if error else self.app.muted)
