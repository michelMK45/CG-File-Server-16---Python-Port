# CGFS 16 Server 16 Python Port v1.2.0

## Highlights

- New **in-game interactive overlay** to assign stadiums, scoreboards, TV logos, movies, and other CGFS assets without leaving FIFA 16, fully controllable with a gamepad.
- Overlay supports **fullscreen mode** so it works properly over the game.
- Open the overlay at any time with **F12** or by **holding the Start button for 0.6 seconds**.
- **Stadium selection with visual previews** directly inside the overlay.
- **Team logos** displayed in the overlay for quick identification.
- **Controller navigation hints** shown in the overlay UI.
- **Chants dialog** now has translation support and volume sliders.
- Option to **enable or disable the overlay** via a checkbox in the settings.

## New Features

### In-Game Interactive Overlay
A new overlay replaces the previous prototype, adding full-screen support and full gamepad compatibility. You can assign stadiums, scoreboards, TV packages, movies, and other assets while the game is running, directly from within the game.

- Open with **F12** (single press) or hold the **Start/Menu button** for 0.6 seconds.
- Close the overlay with the controller without leaving the game.
- Navigate all sections using controller buttons, with on-screen hints displayed at all times.
- Team logos are shown for easy team identification when assigning assets.
- Stadium selection includes visual previews inside the overlay.

### Chants Dialog Improvements
- Volume **sliders** added to the chants dialog for fine-grained control.
- UI strings in the chants dialog are now **translated** according to the active language.

### Overlay Toggle Setting
- A checkbox in the settings allows you to **enable or disable the in-game overlay** independently.

## Fixes

- Fixed game **crashes when loading stadiums** for certain teams.
- Restored **goal songs fade-out and pause** behavior in the pause menu that was lost in a previous merge.
- Fixed **away team chants** not playing correctly.
- Fixed overlay **not opening on first F12 press** (previously required two presses).
- Fixed overlay **not closing correctly** when dismissing with the controller.
- Fixed **stadium info** not displaying correctly inside the overlay.
- Fixed styles for list dialogs (TV/Scoreboard, Movies).

## Release Asset

- `Server16Python.exe`
