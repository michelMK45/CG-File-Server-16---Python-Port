# Discord Rich Presence Setup Guide

## Overview

Server16 includes **Discord Rich Presence (RPC)** integration that displays your FIFA 16 match information directly in your Discord status while playing. This is completely **local and private** — no data is sent to external servers, only to Discord via local IPC (Inter-Process Communication).

---

## Features

When enabled, Discord RPC displays:
-  Teams playing (Home vs Away)
-  Live match score
-  Match time (MM:SS)
-  Tournament and round information
-  Stadium name
-  Current game state (Playing, Paused, Browsing)

---

## How Names Are Read From Database

Server16 now resolves display names directly from FIFA's database files, instead of showing raw IDs.

### Data Source

The app reads from:
- `data/db/fifa_ng_db.db`
- `data/db/fifa_ng_db-meta.xml`

using `pythonnet` + `FifaLibrary14.dll`.

### Team Name Resolution

- Team IDs are read from game memory.
- Discord RPC resolves those IDs through the `teams` table in the FIFA database.
- Result: Discord shows human-readable team names instead of numeric IDs.

### Stadium Name Resolution (Current Priority)

For stadium text in Discord, Server16 applies this priority:

1. `scoreboardstdname` display name (if configured for the active custom stadium)
2. Active custom stadium folder/name
3. Stadium name resolved from the `stadiums` table using current `STADID`
4. If nothing is found, it falls back to generic match text (instead of reusing stale previous stadium names)

This prevents cases where Discord incorrectly keeps showing a previous custom stadium.

---

## Quick Start

### 1. Install the Required Library

Discord RPC requires the `pypresence` library. Install it with:

```bash
pip install pypresence
```

### 2. Enable Discord RPC

Discord RPC must be enabled in **both** configuration files.

In `FSW/settings.ini`, ensure this is set under `[Modules]`:

```ini
[Modules]
DiscordRPC=1
```

Then edit `runtime/settings.json` and set:

```json
{
  "FIFAEXE": "default",
  "discord_rpc": {
    "enabled": true,
    "client_id": "1495719449700077630"
  }
}
```

### 3. Start Server16

That's it! Once enabled, your Discord status will update automatically when FIFA 16 is running.

---

## Using Your Own Discord Application (Optional)

If you want to use your own Discord application instead of the community one, follow these steps:

### Step 1: Create a Discord Application

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** and give it a name (e.g., "My FIFA 16 Server16")
3. Go to **General Information** and copy your **Client ID**

### Step 2: Configure Assets (Optional)

For custom Rich Presence appearance:

1. In your application, go to **Rich Presence** → **Art Assets**
2. Upload a large image:
   - Name it: `fifa16`
   - This will be the main image shown in your status

### Step 3: Update settings.json

Replace the `client_id` in `runtime/settings.json`:

```json
{
  "discord_rpc": {
    "enabled": true,
    "client_id": "YOUR_CLIENT_ID_HERE"
  }
}
```

Restart Server16 and you're done!

---

## Troubleshooting

### IDs appear instead of names

If Discord shows numeric values (for teams/stadiums), verify:

1. FIFA database files exist:
  - `data/db/fifa_ng_db.db`
  - `data/db/fifa_ng_db-meta.xml`
2. `pythonnet` is installed
3. `bin/FifaLibrary14.dll` exists
4. Logs in `runtime/server16.log` do not show database load errors

### "pypresence not installed"

Make sure pypresence is installed:

```bash
pip install pypresence
```

### Discord RPC doesn't connect

1. **Ensure Discord is running** — The desktop application must be open for RPC to work
2. **Check that pypresence is installed** — Run the pip install command above
3. **Verify Client ID is valid** — Copy from Discord Developer Portal or use the default
4. **Check logs** — Look at `runtime/server16.log` for errors

Example error log:
```
Discord RPC connected (Client ID: 1495719449700077630)
```

### RPC disconnects while playing

This is normal if Discord is briefly closed or restarted. Server16 will automatically reconnect every 30 seconds with exponential backoff.

---

## Privacy & Security

### What Data is Sent?

- **Game State**: Team IDs, score, time, tournament name, stadium name
- **Discord**: Sends only to your local Discord application (IPC)
- **External Servers**: Nothing is sent to FIFA16Tools or any external server

### What's NOT Tracked?

❌ User information  
❌ IP addresses  
❌ Match outcomes  
❌ Personal data  
❌ Telemetry  

Discord RPC is **purely local** and **completely optional**.

---

## Disabling Discord RPC

To disable without uninstalling:

1. Edit `runtime/settings.json`
2. Set `"enabled": false`
3. Restart Server16

You can keep pypresence installed — it won't affect other features.

---

## Advanced Configuration

### Update Interval

Control how often RPC updates (in milliseconds):

```json
{
  "discord_rpc": {
    "enabled": true,
    "client_id": "1495719449700077630",
    "update_interval_ms": 1000
  }
}
```

- `500` = Very frequent updates (not recommended, may rate-limit Discord)
- `1000` = Default, recommended
- `5000` = Less frequent, lower CPU usage

---

## Community Notes

- This project is **community-driven** and **non-profit**
- Discord RPC is **entirely optional** — disable it anytime
- Your privacy is prioritized — all processing is local
- If you find a bug or have suggestions, report it in the project repository

---

## Support

For issues or questions:
1. Check the logs in `runtime/server16.log`
2. Verify pypresence is installed
3. Ensure Discord is running on your system
4. Report issues in the project repository

Enjoy your Discord presence! ⚽🎮

