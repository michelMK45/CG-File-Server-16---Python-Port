<h1 align="center">CGFS 16 Server 16 Python Port</h1>

<p align="center">
  <a href="https://github.com/michelMK45/CG-File-Server-16---Python-Port/releases">
  <img alt="Github Downloads" src="https://img.shields.io/github/downloads/michelMK45/CG-File-Server-16---Python-Port/total?style=for-the-badge&logo=github">
  </a>
  <br>
</p>

<img alt="main" src="https://i.ibb.co/xN3vf95/main.png" />

⚠ This is a fork of the original project, continued by the community after the original author stopped developing the tool.

**CGFS 16 Server 16** is a Windows desktop control panel and in-game overlay for **FIFA 16** modding. It watches the game's live memory state while you play and automatically swaps in the right stadium, scoreboard, TV logo, movie, chants, camera package, and kit assets for the match you're about to play — no manual file-copying or alt-tabbing required. This is a full Python rewrite of the classic Server 16 tool by shawminator, aimed at being easier for the community to maintain, fix, and extend.

>  **Full documentation lives in the [Wiki](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki).** This README is only a quick overview — every setup guide, folder layout and `settings.ini` reference is there.

## Screenshots

Dashboard:

<img alt="dashboard" src="https://i.ibb.co/7xHy5y1C/image.jpg" />

Kit server:

<img alt="kits" src="https://i.ibb.co/WbtRwVZ/image.jpg" />

Camera library:

<img alt="Screenshot_1" src="https://i.ibb.co/845Kjjtz/image.png" />

In-game overlay:

<img alt="overlay" src="https://i.ibb.co/Xr6NDqqs/image.jpg" />

## Quick Start

**Requirements:** Windows and FIFA 16 installed locally.

1. Download the latest `Server16Python.exe` from [Releases](https://github.com/michelMK45/CG-File-Server-16---Python-Port/releases) and run it. Point it at your `FIFA 16.exe` if it isn't auto-detected.
2. **Add an antivirus exclusion first.** CGFS injects a DLL into FIFA 16 for the overlay and reads/writes the game's memory, which Windows Defender can flag as a false positive — see [Antivirus / Windows Defender Warnings](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Antivirus).
3. In the **Set Up** tab, run **Run Setup** and then **Regen BH** (uncheck the `FSW/settings.ini` box in the checklist if you've already customized your assignments).
4. Drop your stadium, scoreboard, chants… packs into their folders, assign them from the desktop window, **launch FIFA 16 and play** — the app applies them automatically.
5. Press **F12** in-game (or hold Start/Menu on a gamepad) to open the interactive overlay.

The ordered step-by-step version, including the Assets Extractor and troubleshooting, is in the [Quick Guide](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Quick-Guide) and [Getting Started](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Getting-Started).

## Features

- **Live match-aware asset switching** — reads the home team, competition and round from FIFA's memory and applies whatever you assigned by home team, round, tournament, derby (one specific fixture) or default.
- **In-game interactive overlay** — an RmlUi menu rendered on top of FIFA 16 (even in exclusive fullscreen), navigable with keyboard, controller or mouse, with live previews and a manual in-game stadium picker.
- **Stadium management** — folders or `.zip`/`.rar` archives, multi-stadium rotations, previews, goalpost model/texture packs, shared entrance cameras, net values, custom pre-match stadium names and per-stadium gameplay cameras.
- **Scoreboards, TV logos & movies** — per round, tournament, derby or home team, with embedded video preview for movies.
- **Chants & audio** — per-team chants, held goal songs, random goal-song/entrance-anthem variants and a Team Entrance walkout anthem (overridable per tournament or round).
- **Kits** — Kit Sets with F7–F11 in-game hotkeys (Simple) and a full Kit Mixer for jersey/shorts/numbers/thumbnail/name color (Advanced).
- **Camera packages** — Anth's FIFA 16 AIO Camera Mod presets applied with one click.
- **Ball, Referee, Wipe & Adboard** modules assignable per round.
- **Gamepads bridge** — translate up to 4 non-Xbox controllers into virtual Xbox 360 pads.
- **Custom substitutions** — raise the 3-substitution limit up to 9.
- **Tools** — Assets Extractor, grouped Dashboard Modules switches, Autorun, settings export/import, Discord Rich Presence.

Details for each of these: [Features Overview](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Features-Overview).

## Documentation

Everything is in the **[Wiki](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki)**; the [Feature Index](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Feature-Index) maps every feature to its setup guide.

| Topic | Pages |
|---|---|
| **Start here** | [Quick Guide](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Quick-Guide) · [Getting Started](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Getting-Started) · [Antivirus](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Antivirus) · [FIFA folder layout](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/FIFA-Folder-Layout) |
| **Stadiums** | [Folders & archives](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Stadium-Loading) · [Previews](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Stadium-Previews) · [Goalposts](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Goalposts) · [Manual picker & multi-stadium](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Manual-Stadium-Picker) · [Net values](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Stadium-Net-Values) · [Custom name](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Stadium-Display-Name) |
| **Cameras** | [Camera packages](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Camera-Packages) · [Gameplay cameras](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Gameplay-Cameras) · [Entrance camera packs](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Entrance-Camera-Packs) |
| **Scoreboards, logos & movies** | [Scoreboards](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Scoreboards) · [TV logos](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/TV-Logos) · [Movies](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Movies) · [Derby assignments](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Derby-Assignments) |
| **Chants & entrance** | [Chants audio](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Chants-Audio) · [MP3 compatibility](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/MP3-Compatibility) · [Random goal songs](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Random-Goal-Songs) · [Team Entrance](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Team-Entrance) · [Tournament / round entrance](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Tournament-Round-Entrance) |
| **Kits** | [Overview](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Kits) · [Kit Sets](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Kit-Sets) · [Kit Mixer](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Kit-Mixer) |
| **Ball, referee, wipe & adboard** | [Ball](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Ball) · [Referee](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Referee) · [Wipe](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Wipe) · [Adboard](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Adboard) · [Shared rules](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Match-Asset-Packs) |
| **Tools & gameplay** | [Dashboard modules](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Dashboard-Modules) · [Assets Extractor](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Assets-Extractor) · [Settings export & import](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Settings-Export-Import) · [Gamepads](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Gamepads) · [Substitutions](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Substitutions) · [Discord](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Discord) (also [DISCORD_SETUP.md](DISCORD_SETUP.md)) |
| **Project** | [Contributing](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Contributing) · [For developers](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Developers) |

## For Developers

Run from source with Python 3.10+:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install psutil pillow pygame rarfile pypresence ffpyplayer pyinstaller
python main.py
```

Build the standalone executable with `.\build_exe.bat` (output: `dist/Server16Python.exe`).

Running from source also needs the native binaries in `bin/` (overlay DLL/injector, 32-bit Python bridge via `scripts\setup_python32.bat`, etc.). The repository structure, full requirements, the 32-bit database bridge and build details are in the wiki's [For Developers](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Developers) page; internals are documented under [`docs/`](docs/).

## Contributing

Contributions are welcome — bug fixes, overlay UX, documentation, or testing on different FIFA 16 setups. Fork the repository, create a feature branch, make focused changes, test locally and open a pull request with a clear description. See [Contributing](https://github.com/michelMK45/CG-File-Server-16---Python-Port/wiki/Contributing) for the details.

## Project Status

This repository is public and open for community contributions.

The goal is to preserve and evolve the FIFA 16 Server 16 experience in a modern Python codebase that is easier to maintain, improve, and extend.

## Release Notes

Each release has its notes in this repository: [v1.2.0](RELEASE_NOTES_v1.2.0.md) · [v1.3.0](RELEASE_NOTES_v1.3.0.md) · [v1.3.1](RELEASE_NOTES_v1.3.1.md) · [v1.4.0](RELEASE_NOTES_v1.4.0.md) · [v1.5.0](RELEASE_NOTES_v1.5.0.md) · [v1.6.0](RELEASE_NOTES_v1.6.0.md)

## Credits

- Original concept and workflow: CGFS 16 Server 16 for FIFA 16
- Python port and ongoing maintenance: this community project and its contributors
- Support development: [Donate via PayPal](https://paypal.me/michellmk)

## Disclaimer

This project is an unofficial community tool for FIFA 16 modding workflows. Use it at your own risk and always keep backups of important game and mod files.
