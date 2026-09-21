"""What the asset grid picker offers, and how a settings field gets its button.

Kept apart from asset_grid_picker_dialog.py on purpose: that module subclasses
`BaseDialog` from dialogs.py, and dialogs.py itself needs the item builders and
the picker button (for the Assign Stadium dialog), so everything the two
dialogs share lives here, free of any dependency on `BaseDialog`, to avoid an
import cycle.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk
from typing import Callable, Iterable

import tkinter as tk

from .file_tools import resolve_goalpost_model_preview_path, resolve_goalpost_texture_rx3_path

# Glyph on the small button beside a combo that opens the grid picker.
PICKER_ICON = "▦"


@dataclass(frozen=True)
class AssetGridItem:
    """One selectable cell of AssetGridPickerDialog.

    value      -- what gets written back into the settings field on selection.
    label      -- caption under the thumbnail (usually the same as value).
    image_path -- static preview image, when the asset has one on disk.
    render     -- for assets whose preview only exists once generated (a
                  GoalpostColor pack is rendered from its .rx3 through the
                  32-bit FifaLibrary bridge). Called from a background thread,
                  one item at a time; returns the rendered image's path.
                  Ignored when image_path is set.

    An item with neither just shows the "No preview" placeholder -- e.g. the
    "None" entry of an optional override.
    """

    value: str
    label: str
    image_path: Path | None = None
    render: Callable[[], Path | None] | None = None


def png_items(values: Iterable[str], preview_dir: Path) -> list[AssetGridItem]:
    """One item per value, previewed by `<preview_dir>/<value>.png` -- the
    convention the Police / PitchMowPattern / Nets preview folders share."""
    return [AssetGridItem(value, value, Path(preview_dir) / f"{value}.png") for value in values]


def goalpost_model_items(model_dir: Path, names: Iterable[str]) -> list[AssetGridItem]:
    """Goalpost model packs: a static `preview.<ext>` inside each pack folder
    (see resolve_goalpost_model_preview_path). "None" and packs without one
    resolve to no image and show the placeholder."""
    return [AssetGridItem(name, name, resolve_goalpost_model_preview_path(model_dir, name)) for name in names]


def goalpost_texture_items(color_dir: Path, names: Iterable[str], stadium_runtime) -> list[AssetGridItem]:
    """Goalpost texture (GoalpostColor) packs have no preview image on disk:
    each is rendered from the pack's own .rx3 by
    `stadium_runtime.render_goalpost_texture_preview`. `reuse_cached=True`
    because the grid renders EVERY pack at once, so any pack whose PNG is still
    current skips the (seconds-long) 32-bit subprocess. "None" and packs with no
    .rx3 have nothing to render and show the placeholder."""
    return [_goalpost_texture_item(color_dir, name, stadium_runtime) for name in names]


def _goalpost_texture_item(color_dir: Path, name: str, stadium_runtime) -> AssetGridItem:
    # A function (not a lambda inside the comprehension above) so each item's
    # closure captures its own source_rx3/name rather than the loop's last one.
    source_rx3 = resolve_goalpost_texture_rx3_path(color_dir, name)  # None for "None" / no .rx3
    if source_rx3 is None:
        return AssetGridItem(name, name)
    return AssetGridItem(
        name, name, render=lambda: stadium_runtime.render_goalpost_texture_preview(source_rx3, cache_key=name, reuse_cached=True),
    )


def make_picker_button(parent: tk.Misc, app, command: Callable[[], None]) -> ttk.Button:
    """The small `▦` button placed right of a combo to open the grid picker
    (compact `Server16.Picker.TButton` style from app_ui.py, with a hover
    tooltip when `app` provides `_add_tooltip`)."""
    button = ttk.Button(parent, text=PICKER_ICON, width=2, style="Server16.Picker.TButton", command=command)
    add_tooltip = getattr(app, "_add_tooltip", None)
    if add_tooltip is not None:
        add_tooltip(button, "tooltip.asset_grid_picker")
    return button
