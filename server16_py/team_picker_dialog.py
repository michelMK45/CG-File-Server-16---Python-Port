from __future__ import annotations

import tkinter as tk
import unicodedata
from tkinter import ttk

from PIL import Image, ImageTk

from .dialogs import BaseDialog


class TeamPickerDialog(BaseDialog):
    """League-filtered team browser.

    Shows every team from the loaded FIFA team database, narrowable by a
    league selection (left list) and/or a name search (both lists), with the
    league logo and team crest shown as a live preview on the right. Returns
    the chosen team_id (str) via `self.result` -- same `close_ok(...)` modal
    convention already used by StadiumDialog/SectionPickerDialog:

        dlg = TeamPickerDialog(app)
        app.wait_window(dlg)
        if dlg.result:
            ...  # dlg.result is the team_id string
    """

    # Each preview box's image area -- see _build_preview_box for why the box
    # itself is a fixed pixel height rather than one that stretches with the
    # window (a stretchy box only reserves its *natural* size, based on the
    # placeholder text, until an image is actually loaded -- same clipping
    # bug already fixed once in dialogs.py's _build_preview_sb).
    PREVIEW_IMAGE_SIZE = (180, 180)

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, "dialog.team_picker.title")
        self._set_geometry(980, 780, 820, 680)

        self._preview_images: dict[str, ImageTk.PhotoImage] = {}
        self._preview_labels: dict[str, tk.Label] = {}

        team_db = getattr(self.app, "team_db", None)
        self._team_db = team_db
        self._all_teams: list[tuple[str, str]] = []
        self._leagues: list[tuple[str, str]] = []
        if team_db is not None:
            self._all_teams = sorted(team_db.team_cache.items(), key=lambda pair: pair[1].lower())
            self._leagues = team_db.leagues_sorted()

        self._league_list_ids: list[str | None] = []
        self._team_list_ids: list[str] = []
        self._selected_league_id: str | None = None
        self._selected_team_id: str | None = None

        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=3)
        self.grid_columnconfigure(2, weight=3)
        self.grid_rowconfigure(1, weight=1)

        topbar = tk.Frame(self, bg=self.bg)
        topbar.grid(row=0, column=0, columnspan=3, sticky="ew", padx=14, pady=(14, 10))
        topbar.grid_columnconfigure(0, weight=1)
        self._dark_label(topbar, self.tr("dialog.team_picker.title"), bg=self.bg, font=("Bahnschrift", 18, "bold")).grid(row=0, column=0, sticky="w")
        self.status_label = self._dark_label(topbar, "", bg=self.bg, muted=True, font=("Bahnschrift", 10))
        self.status_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        league_card = self._card(self, self.tr("dialog.team_picker.leagues"))
        league_card.grid(row=1, column=0, sticky="nsew", padx=(14, 6), pady=(0, 14))

        team_card = self._card(self, self.tr("dialog.team_picker.teams"))
        team_card.grid(row=1, column=1, sticky="nsew", padx=(6, 6), pady=(0, 14))

        preview_card = self._card(self, self.tr("dialog.team_picker.preview"))
        preview_card.grid(row=1, column=2, sticky="nsew", padx=(6, 14), pady=(0, 14))

        # --- Leagues (left) ---
        league_body = tk.Frame(league_card, bg=self.card)
        league_body.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        league_body.grid_columnconfigure(0, weight=1)
        league_body.grid_rowconfigure(2, weight=1)

        self._dark_label(league_body, self.tr("dialog.team_picker.search_league"), muted=True, font=("Bahnschrift", 10), anchor="w").grid(row=0, column=0, sticky="w")
        self.league_search_var = tk.StringVar()
        league_search = ttk.Entry(league_body, textvariable=self.league_search_var, style="Server16.TEntry")
        league_search.grid(row=1, column=0, sticky="ew", pady=(4, 8))
        league_search.bind("<KeyRelease>", lambda _e: self._refresh_league_list())

        league_wrap = tk.Frame(league_body, bg=self.card)
        league_wrap.grid(row=2, column=0, sticky="nsew")
        league_wrap.grid_columnconfigure(0, weight=1)
        league_wrap.grid_rowconfigure(0, weight=1)
        self.league_list = self._dark_listbox(league_wrap, exportselection=False, font=("Consolas", 10))
        league_scroll = ttk.Scrollbar(league_wrap, orient="vertical", command=self.league_list.yview, style="Server16.Vertical.TScrollbar")
        self.league_list.configure(yscrollcommand=league_scroll.set)
        self.league_list.grid(row=0, column=0, sticky="nsew")
        league_scroll.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self.league_list.bind("<<ListboxSelect>>", lambda _e: self._on_league_select())

        # --- Teams (middle) ---
        team_body = tk.Frame(team_card, bg=self.card)
        team_body.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        team_body.grid_columnconfigure(0, weight=1)
        team_body.grid_rowconfigure(2, weight=1)

        self._dark_label(team_body, self.tr("dialog.team_picker.search_team"), muted=True, font=("Bahnschrift", 10), anchor="w").grid(row=0, column=0, sticky="w")
        self.team_search_var = tk.StringVar()
        team_search = ttk.Entry(team_body, textvariable=self.team_search_var, style="Server16.TEntry")
        team_search.grid(row=1, column=0, sticky="ew", pady=(4, 8))
        team_search.bind("<KeyRelease>", lambda _e: self._refresh_team_list())

        team_wrap = tk.Frame(team_body, bg=self.card)
        team_wrap.grid(row=2, column=0, sticky="nsew")
        team_wrap.grid_columnconfigure(0, weight=1)
        team_wrap.grid_rowconfigure(0, weight=1)
        self.team_list = self._dark_listbox(team_wrap, exportselection=False, font=("Consolas", 10))
        team_scroll = ttk.Scrollbar(team_wrap, orient="vertical", command=self.team_list.yview, style="Server16.Vertical.TScrollbar")
        self.team_list.configure(yscrollcommand=team_scroll.set)
        self.team_list.grid(row=0, column=0, sticky="nsew")
        team_scroll.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self.team_list.bind("<<ListboxSelect>>", lambda _e: self._on_team_select())
        self.team_list.bind("<Double-Button-1>", lambda _e: self._confirm())

        # --- Preview (right) ---
        preview_body = tk.Frame(preview_card, bg=self.card)
        preview_body.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        preview_body.grid_columnconfigure(0, weight=1)
        preview_body.grid_rowconfigure(0, weight=1)
        preview_body.grid_rowconfigure(1, weight=1)

        self._build_preview_box(preview_body, row=0, key="league", title=self.tr("dialog.team_picker.leagues"))
        self._build_preview_box(preview_body, row=1, key="team", title=self.tr("dialog.team_picker.teams"))

        self.selected_label = self._dark_label(preview_body, self.tr("dialog.team_picker.no_selection"), muted=True, wraplength=260, justify="left", anchor="w")
        self.selected_label.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        # --- Actions ---
        action_bar = tk.Frame(self, bg=self.bg)
        action_bar.grid(row=2, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 14))
        action_bar.grid_columnconfigure(0, weight=1)
        action_bar.grid_columnconfigure(1, weight=1)
        self.select_button = ttk.Button(action_bar, text=self.tr("button.select_team"), command=self._confirm, state="disabled")
        self.select_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(action_bar, text=self.tr("button.cancel"), command=self.destroy).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        if team_db is None:
            self.status_label.configure(text=self.tr("dialog.team_picker.no_database"))
        else:
            self.status_label.configure(text=self.tr("dialog.team_picker.team_count", count=len(self._all_teams)))

        self._refresh_league_list()
        self._refresh_team_list()

    # -- preview boxes --------------------------------------------------

    def _build_preview_box(self, parent: tk.Misc, row: int, key: str, title: str) -> None:
        # tk.Label's -width/-height are character/line counts while showing
        # text (the "No preview" placeholder) but stop reserving enough room
        # once an image is configured on the same label, clipping it -- same
        # bug already fixed for other preview panels (dialogs.py's
        # _build_preview_sb, settings_editor.py's _build_stadium_preview_box).
        # An earlier version of this fix put the title label and the image
        # in the same fixed-height frame, splitting one budget between them
        # (image_size + a guessed allowance for the title's own rendered
        # height) -- that guess left near-zero slack and still clipped the
        # top of the image by a few pixels. Fix: keep the title on its own
        # naturally-sized row, and give ONLY the image its own fixed-height,
        # grid_propagate(False) frame sized purely from image_size -- so the
        # image box no longer has to share its budget with text at all.
        image_size = self.PREVIEW_IMAGE_SIZE
        outer = tk.Frame(parent, bg=self.card_soft, highlightthickness=1, highlightbackground="#243654")
        outer.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        outer.grid_columnconfigure(0, weight=1)
        self._dark_label(outer, title, bg=self.card_soft, muted=True, font=("Bahnschrift", 10)).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 4))

        image_wrap = tk.Frame(outer, bg=self.panel, height=image_size[1] + 20)
        image_wrap.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        image_wrap.grid_propagate(False)
        image_wrap.grid_columnconfigure(0, weight=1)
        image_wrap.grid_rowconfigure(0, weight=1)

        preview = tk.Label(image_wrap, text=self.tr("dialog.team_picker.no_preview"), bg=self.panel, fg=self.muted, anchor="center", justify="center", relief="flat")
        preview.grid(row=0, column=0, sticky="nsew")
        preview.image_size = image_size
        self._preview_labels[key] = preview

    def _update_preview(self, key: str, image_path, fallback_text: str) -> None:
        label = self._preview_labels.get(key)
        if label is None:
            return
        self._preview_images.pop(key, None)
        if image_path is None or not image_path.exists():
            label.configure(image="", text=fallback_text, compound="center")
            return
        try:
            image = Image.open(image_path).convert("RGBA")
            image.thumbnail(getattr(label, "image_size", (220, 220)))
            photo = ImageTk.PhotoImage(image)
        except Exception:
            label.configure(image="", text=fallback_text, compound="center")
            return
        self._preview_images[key] = photo
        label.configure(image=photo, text="", compound="center")

    # -- filtering --------------------------------------------------------

    @staticmethod
    def _normalize_text(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value or "")
        return "".join(char for char in normalized if not unicodedata.combining(char)).lower()

    def _refresh_league_list(self) -> None:
        query = self._normalize_text(self.league_search_var.get().strip())
        self.league_list.delete(0, "end")
        self._league_list_ids = [None]
        self.league_list.insert("end", self.tr("dialog.team_picker.all_leagues"))
        for league_id, league_name in self._leagues:
            if query and query not in self._normalize_text(league_name):
                continue
            self._league_list_ids.append(league_id)
            self.league_list.insert("end", f"{league_name}  [{league_id}]")

    def _refresh_team_list(self) -> None:
        query = self._normalize_text(self.team_search_var.get().strip())
        allowed_ids = None
        if self._selected_league_id is not None and self._team_db is not None:
            allowed_ids = self._team_db.teams_in_league(self._selected_league_id)

        self.team_list.delete(0, "end")
        self._team_list_ids = []
        for team_id, team_name in self._all_teams:
            if allowed_ids is not None and team_id not in allowed_ids:
                continue
            if query and query not in self._normalize_text(team_name):
                continue
            self._team_list_ids.append(team_id)
            self.team_list.insert("end", f"{team_name}  [{team_id}]")

    # -- selection handlers -------------------------------------------------

    def _on_league_select(self) -> None:
        selection = self.league_list.curselection()
        if not selection:
            return
        index = selection[0]
        league_id = self._league_list_ids[index] if index < len(self._league_list_ids) else None
        self._selected_league_id = league_id
        if league_id is None:
            self._update_preview("league", None, self.tr("dialog.team_picker.no_preview"))
        else:
            app = self.app
            logo_path = app._resolve_league_logo_path(league_id) if hasattr(app, "_resolve_league_logo_path") else None
            self._update_preview("league", logo_path, self.tr("dialog.team_picker.no_preview"))
        self._refresh_team_list()

    def _on_team_select(self) -> None:
        selection = self.team_list.curselection()
        if not selection:
            return
        index = selection[0]
        if index >= len(self._team_list_ids):
            return
        team_id = self._team_list_ids[index]
        self._selected_team_id = team_id
        team_name = dict(self._all_teams).get(team_id, team_id)
        self.selected_label.configure(text=self.tr("dialog.team_picker.selected_team", name=team_name, id=team_id))
        self.select_button.configure(state="normal")
        app = self.app
        crest_path = app._resolve_team_crest_path(team_id) if hasattr(app, "_resolve_team_crest_path") else None
        self._update_preview("team", crest_path, self.tr("dialog.team_picker.no_preview"))

    def _confirm(self) -> None:
        if self._selected_team_id is None:
            return
        self.close_ok(self._selected_team_id)
