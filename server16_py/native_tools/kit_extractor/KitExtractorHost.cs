// Native (compiled) .NET Framework x86 host for FifaLibrary16.dll kit extraction.
//
// This exists because FifaFile.Decompress() (used by Kit.ExportKitTextures for any
// kit not already a loose file override) shells out to external decompressor
// tools (fifa16_decryptor.exe / un_chunlzma.exe), using a working directory
// computed by FifaEnvironment.InitializeLaunchFolder(). That method does
// `Environment.CommandLine.Substring(1, ...)`, silently assuming the command
// line always starts with the opening quote Windows adds around a quoted exe
// path (`"C:\...\app.exe" ...`). Launched normally (double-click, or a launcher
// that quotes the path) that holds and the maths works out. Launched via
// Python's subprocess with a plain argv list, the exe path reaching
// CreateProcess has no surrounding quotes (no spaces to quote), so
// Substring(1, ...) chops the leading drive letter instead of a quote that was
// never there, corrupting the working directory and making the decompressor
// launch fail. Two things are required to avoid this:
//   1. Run as a real compiled .exe, not FifaLibrary16.dll hosted inside Python
//      via pythonnet (this .exe).
//   2. Launch it with a command line string that IS wrapped in quotes, e.g.
//      subprocess.Popen('"' + exe_path + '"', ...) rather than
//      subprocess.Popen([exe_path, ...]) — see _run_extract_kits in app_ui.py.
//
// The game directory is passed via the KITEXTRACTOR_GAMEDIR env var instead of
// argv, keeping the command line exactly `"<path to this exe>"` so the above
// Substring(1, ...) lands on the quote as intended.
//
// Kit.ExportKitTextures() spawns un_chunlzma.exe per kit. Something in that
// path (likely the external Process handles, since GC.Collect() +
// WaitForPendingFinalizers() every iteration made no difference) leaks a
// native OS resource, and the process reliably throws OutOfMemoryException
// around the ~195th team (~780 kit exports) regardless of which teams those
// are — a hard resource ceiling (e.g. the default 10,000 GDI/USER handle
// limit), not memory pressure the GC can reclaim. There's no fix available
// from outside this closed-source DLL, so the caller (kit_extractor_host.py)
// processes the roster in small batches, launching a fresh process per batch
// via KITEXTRACTOR_TEAM_START/KITEXTRACTOR_TEAM_COUNT so the OS reclaims
// whatever's leaking when each batch's process exits.
//
// A fresh game install has no data\db\fifa_ng_db.db loose file at all (vanilla
// FIFA 16 ships it packed), and FifaEnvironment.OpenFifaDb() needs one to
// enumerate the team/kit roster. FifaEnvironment.ExtractMainDatabase() doesn't
// decompress it from the archive — it just File.Copy()s a bundled template db
// from <this exe's folder>\Templates\data\db\fifa_ng_db.db (+ meta.xml), so
// that Templates folder (sourced from Creation Master 16's own install,
// bin/Templates/ in this repo) must sit next to KitExtractorHost.exe.
// ExtractMainDatabase() also returns false even when the copy succeeded (it
// does extra archive bookkeeping afterward that can fail independently), so
// success is checked by re-testing File.Exists(dbPath) rather than trusting
// the return value.
//
// The bootstrap only runs when KITEXTRACTOR_ALLOW_DB_BOOTSTRAP=1 (set by the
// Extract Database button only, via KITEXTRACTOR_TEAM_COUNT=0). Extract Kits
// leaves it unset, so a missing database fails fast with a message pointing
// at Extract Database instead of silently copying the template — keeps the
// two operations independent and never overwrites a database the app didn't
// just decide to (re)create.
//
// Stdout protocol (JSON lines), mirrors bh_worker.py / kit_worker.py:
//   {"t":"ready"}
//   {"t":"progress","i":1,"total":40,"team":1,"kittype":0,"ok":true}
//   {"t":"progress","i":2,"total":40,"team":1,"kittype":1,"ok":false,"error":"msg"}
//   {"t":"done","ok":38,"failed":2}
//   {"t":"error","msg":"fatal message"}

using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using FifaLibrary;

internal static class Program
{
    private static readonly object s_emitLock = new object();

    private static void Emit(string json)
    {
        lock (s_emitLock)
        {
            Console.WriteLine(json);
            Console.Out.Flush();
        }
    }

    private static string JsonEscape(string s)
    {
        if (s == null) return "";
        return s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", " ").Replace("\n", " ");
    }

    // Some archive entries trip an internal FifaLibrary16 validation check that
    // it reports via a blocking WinForms "Message" dialog (UserMessage) rather
    // than an exception. FifaLibrary's own EnableMessages/EnableWarnings/
    // EnableErrors suppression flags (set in Main below) only cover message IDs
    // that already have a row in its internal table at the time they're called
    // — in practice several IDs still slip through and show a dialog anyway.
    // This is a headless process with nobody there to click OK, so instead of
    // trusting that suppression, a background thread watches for any "Message"
    // window this process owns and clicks its OK button the instant one
    // appears, whatever triggered it.
    [DllImport("user32.dll")] private static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll")] private static extern bool EnumChildWindows(IntPtr hWndParent, EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Auto)] private static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
    [DllImport("user32.dll")] private static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hWnd);
    private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    private const uint BM_CLICK = 0x00F5;

    // Exceptions thrown inside a delegate that's been handed to unmanaged code
    // (EnumWindows/EnumChildWindows call back into managed code through a
    // reverse P/Invoke thunk) do NOT reliably unwind into a try/catch wrapped
    // around the *outer* EnumWindows call — they can instead be treated as an
    // unhandled exception crossing a native frame and take the whole process
    // down before the outer catch ever runs. Every callback body below must
    // therefore guard itself.
    private static long s_watchdogScans = 0;

    private static void DialogWatchdogLoop()
    {
        uint myPid = (uint)Process.GetCurrentProcess().Id;
        while (true)
        {
            try
            {
                EnumWindows(delegate(IntPtr hWnd, IntPtr lParam)
                {
                    try
                    {
                        uint pid;
                        GetWindowThreadProcessId(hWnd, out pid);
                        if (pid != myPid || !IsWindowVisible(hWnd))
                        {
                            return true;
                        }
                        var titleSb = new StringBuilder(256);
                        GetWindowText(hWnd, titleSb, 256);
                        // The dialog's actual title is " Message" (leading space) —
                        // trim before comparing, that's what let every prior scan
                        // miss it silently.
                        string title = titleSb.ToString().Trim();
                        if (title != "Message")
                        {
                            return true;
                        }
                        Emit("{\"t\":\"dialog_seen\",\"hwnd\":\"" + hWnd.ToString() + "\"}");
                        IntPtr okBtn = IntPtr.Zero;
                        EnumChildWindows(hWnd, delegate(IntPtr child, IntPtr lp2)
                        {
                            try
                            {
                                var sb = new StringBuilder(64);
                                GetWindowText(child, sb, 64);
                                if (sb.ToString() == "OK")
                                {
                                    okBtn = child;
                                    return false;
                                }
                            }
                            catch (Exception exChild)
                            {
                                Emit("{\"t\":\"watchdog_error\",\"where\":\"child\",\"msg\":\"" + JsonEscape(exChild.Message) + "\"}");
                            }
                            return true;
                        }, IntPtr.Zero);
                        if (okBtn != IntPtr.Zero)
                        {
                            IntPtr result = SendMessage(okBtn, BM_CLICK, IntPtr.Zero, IntPtr.Zero);
                            Emit("{\"t\":\"dialog_dismissed\",\"result\":\"" + result.ToString() + "\"}");
                        }
                        else
                        {
                            Emit("{\"t\":\"watchdog_error\",\"where\":\"no_ok_button\"}");
                        }
                    }
                    catch (Exception exOuter)
                    {
                        Emit("{\"t\":\"watchdog_error\",\"where\":\"outer\",\"msg\":\"" + JsonEscape(exOuter.Message) + "\"}");
                    }
                    return true;
                }, IntPtr.Zero);
            }
            catch (Exception exScan)
            {
                Emit("{\"t\":\"watchdog_error\",\"where\":\"scan\",\"msg\":\"" + JsonEscape(exScan.Message) + "\"}");
            }
            s_watchdogScans++;
            if (s_watchdogScans % 40 == 0)
            {
                Emit("{\"t\":\"watchdog_heartbeat\",\"scans\":" + s_watchdogScans + "}");
            }
            Thread.Sleep(150);
        }
    }

    private static int Main(string[] args)
    {
        Thread watchdog = new Thread(DialogWatchdogLoop);
        watchdog.IsBackground = true;
        watchdog.Start();

        // The game directory is passed via an environment variable rather than a
        // command-line argument. FifaEnvironment.InitializeLaunchFolder() derives its
        // internal working-directory (used to invoke the external un_chunlzma.exe /
        // fifa16_decryptor.exe decompressors) from Environment.CommandLine, assuming
        // it is just the quoted exe path with nothing else appended. Any extra argv
        // breaks that parsing and corrupts the computed directory, so this process
        // must be launched with zero arguments.
        string gameDir = Environment.GetEnvironmentVariable("KITEXTRACTOR_GAMEDIR");
        if (string.IsNullOrEmpty(gameDir))
        {
            Emit("{\"t\":\"error\",\"msg\":\"KITEXTRACTOR_GAMEDIR environment variable not set\"}");
            return 1;
        }

        try
        {
            if (!Directory.Exists(gameDir))
            {
                Emit("{\"t\":\"error\",\"msg\":\"Game directory not found: " + JsonEscape(gameDir) + "\"}");
                return 1;
            }

            if (!FifaEnvironment.Initialize(16, gameDir))
            {
                Emit("{\"t\":\"error\",\"msg\":\"FifaEnvironment.Initialize failed\"}");
                return 1;
            }

            // Some archive entries (a handful of specifickitnumbers_*.rx3 in
            // practice) trip an internal validation warning that FifaLibrary16
            // surfaces as a blocking WinForms message box (UserMessage) rather
            // than an exception. This process is headless — nobody is there to
            // click OK — so it would just hang forever. Suppressing it here
            // makes ShowMessage() a no-op instead of ever displaying anything;
            // the export call still returns false for that file, which we
            // already handle as a normal per-item failure.
            try
            {
                UserMessage um = FifaEnvironment.UserMessages;
                if (um != null)
                {
                    um.EnableMessages(false);
                    um.EnableWarnings(false);
                    um.EnableErrors(false);
                }
            }
            catch
            {
                // Best-effort — never let suppression setup itself block extraction.
            }

            if (!FifaEnvironment.OpenFat())
            {
                Emit("{\"t\":\"error\",\"msg\":\"FifaEnvironment.OpenFat failed\"}");
                return 1;
            }
            FifaFat fat = FifaEnvironment.FifaFat;

            string dbPath = Path.Combine(gameDir, Path.Combine("data", Path.Combine("db", "fifa_ng_db.db")));
            if (!File.Exists(dbPath))
            {
                // Only the "Extract Database" caller (KITEXTRACTOR_TEAM_COUNT=0)
                // sets this — kit extraction never bootstraps the database on
                // its own, so the two operations stay fully independent and a
                // missing database fails loudly instead of silently doing extra
                // work the caller didn't ask for.
                string allowBootstrap = Environment.GetEnvironmentVariable("KITEXTRACTOR_ALLOW_DB_BOOTSTRAP");
                if (allowBootstrap != "1")
                {
                    Emit("{\"t\":\"error\",\"msg\":\"Database not found. Click Extract Database first.\"}");
                    return 1;
                }
                Emit("{\"t\":\"extracting_db\"}");
                // ExtractMainDatabase() copies a bundled template db (see
                // bin/Templates/data/db/) into place and then does some
                // additional archive bookkeeping (hiding the packed entry so
                // the loose copy wins) that can return false even though the
                // copy itself succeeded — so re-check the actual file instead
                // of trusting the return value.
                FifaEnvironment.ExtractMainDatabase();
                if (!File.Exists(dbPath))
                {
                    Emit("{\"t\":\"error\",\"msg\":\"ExtractMainDatabase failed — database still missing after the call\"}");
                    return 1;
                }
            }

            if (!FifaEnvironment.OpenFifaDb())
            {
                Emit("{\"t\":\"error\",\"msg\":\"FifaEnvironment.OpenFifaDb failed\"}");
                return 1;
            }

            FifaEnvironment.LoadLists(EFifaObjects.FifaTeam | EFifaObjects.FifaKit);

            TeamList teams = FifaEnvironment.Teams;
            KitList kits = FifaEnvironment.Kits;

            if (teams == null || kits == null)
            {
                Emit("{\"t\":\"error\",\"msg\":\"Teams/Kits lists did not load\"}");
                return 1;
            }

            // "kit" (default) exports the jersey/shorts texture via
            // Kit.ExportKitTextures(); "kitui" exports the kit-selection-screen
            // thumbnail (j<kittype>_<team>_0.dds). All go through
            // FifaFile.Decompress() under the hood via the same FifaFat-backed
            // export pipeline, so the batching workaround above applies equally
            // to any of them.
            //
            // "kitnumbers" actually covers TWO distinct, differently-named
            // families of file living in data/sceneassets/kitnumbers/, and a
            // prior version of this code only ever attempted the second one:
            //   - kitnumbers_<style>_<color>.rx3 (FifaLibrary.NumberFont) — the
            //     shared glyph sheets every team's kit.jerseyNumberFont /
            //     .shortsNumberFont FK points at. This is what actually renders
            //     the number on every player in a vanilla install; the DLL's own
            //     NumberFontList.Load() already walks style x color and keeps
            //     only combos FifaFat confirms exist, so exporting that same
            //     validated list has a near-100% hit rate, mirroring how
            //     Teams/Kits are enumerated for "kit"/"kitui" above. Global, not
            //     per-team, so it only needs to run once (batch_start == 0).
            //   - specifickitnumbers_<team>_<jerseyShorts>_0_<kitType>.rx3
            //     (FifaLibrary.SpecificNumberFont) — a rare per-team override a
            //     handful of licensed clubs use for a bespoke number font. Most
            //     teams genuinely have none, so a high failure count here is
            //     expected and not a sign anything is broken — kept as a
            //     best-effort per-team pass since some teams do have one.
            string assetMode = Environment.GetEnvironmentVariable("KITEXTRACTOR_ASSET") ?? "kit";
            int itemsPerTeam = (assetMode == "kitnumbers") ? 8 : 4;

            int teamStart = 0;
            int teamCount = teams.Count;
            string startEnv = Environment.GetEnvironmentVariable("KITEXTRACTOR_TEAM_START");
            string countEnv = Environment.GetEnvironmentVariable("KITEXTRACTOR_TEAM_COUNT");
            if (!string.IsNullOrEmpty(startEnv)) int.TryParse(startEnv, out teamStart);
            if (!string.IsNullOrEmpty(countEnv)) int.TryParse(countEnv, out teamCount);
            teamStart = Math.Max(0, Math.Min(teamStart, teams.Count));
            int teamEnd = Math.Max(teamStart, Math.Min(teamStart + teamCount, teams.Count));

            Emit("{\"t\":\"ready\",\"teams\":" + teams.Count + ",\"batch_start\":" + teamStart + ",\"batch_end\":" + teamEnd + "}");

            NumberFontList numberFonts = null;
            int numberFontCount = 0;
            if (assetMode == "kitnumbers")
            {
                numberFonts = FifaEnvironment.NumberFonts;
                numberFontCount = numberFonts != null ? numberFonts.Count : 0;
            }

            int total = teams.Count * itemsPerTeam + numberFontCount;
            int i = numberFontCount + teamStart * itemsPerTeam;
            int ok = 0;
            int failed = 0;

            if (assetMode == "kitnumbers" && teamStart == 0 && numberFonts != null)
            {
                const int S_MAX_COLORS = 20;
                for (int nfi = 0; nfi < numberFonts.Count; nfi++)
                {
                    int fontId = ((NumberFont)numberFonts[nfi]).Id;
                    int style = fontId / S_MAX_COLORS;
                    int color = fontId - style * S_MAX_COLORS;
                    bool exported = false;
                    string error = null;
                    try
                    {
                        exported = NumberFont.Export(style, color, gameDir);
                    }
                    catch (Exception exc)
                    {
                        error = exc.Message;
                    }
                    if (exported) ok++; else failed++;

                    var sbf = new StringBuilder();
                    sbf.Append("{\"t\":\"progress\",\"i\":").Append(nfi + 1)
                       .Append(",\"total\":").Append(total)
                       .Append(",\"phase\":\"numberfont\",\"style\":").Append(style)
                       .Append(",\"color\":").Append(color)
                       .Append(",\"ok\":").Append(exported ? "true" : "false");
                    if (error != null)
                    {
                        sbf.Append(",\"error\":\"").Append(JsonEscape(error)).Append("\"");
                    }
                    sbf.Append("}");
                    Emit(sbf.ToString());
                }
            }

            for (int idx = teamStart; idx < teamEnd; idx++)
            {
                Team team = (Team)teams[idx];
                for (int kittype = 0; kittype <= 3; kittype++)
                {
                    if (assetMode == "kitnumbers")
                    {
                        foreach (EJerseyShorts slot in new[] { EJerseyShorts.Jersey, EJerseyShorts.Shorts })
                        {
                            i++;
                            bool exported = false;
                            string error = null;
                            try
                            {
                                string fname = SpecificNumberFont.SpecificNumberFontFileName(team.Id, slot, (EKitType)kittype);
                                // ExportFileFromZdata() itself triggers FifaLibrary's
                                // internal "file not found" Message dialog for any
                                // entry that isn't actually archived — fine for the
                                // rare hit, but nearly every team has none of these,
                                // so calling it unconditionally meant a dialog (and a
                                // wasted decompressor spin-up) for almost every one of
                                // the 673*8 combinations. NumberFontList.Load() (see
                                // the NumberFont pass above) sidesteps this the same
                                // way: check existence first via FifaFat, and only
                                // call Export for combinations that are actually
                                // there.
                                bool present = fat != null && (fat.IsArchivedFilePresent(fname) || fat.IsPhisycalFilePresent(fname));
                                if (present)
                                {
                                    exported = FifaEnvironment.ExportFileFromZdata(fname, gameDir);
                                }
                            }
                            catch (Exception exc)
                            {
                                error = exc.Message;
                            }

                            if (exported) ok++; else failed++;

                            var sbn = new StringBuilder();
                            sbn.Append("{\"t\":\"progress\",\"i\":").Append(i)
                              .Append(",\"total\":").Append(total)
                              .Append(",\"team\":").Append(team.Id)
                              .Append(",\"kittype\":").Append(kittype)
                              .Append(",\"slot\":\"").Append(slot == EJerseyShorts.Jersey ? "jersey" : "shorts").Append("\"")
                              .Append(",\"ok\":").Append(exported ? "true" : "false");
                            if (error != null)
                            {
                                sbn.Append(",\"error\":\"").Append(JsonEscape(error)).Append("\"");
                            }
                            sbn.Append("}");
                            Emit(sbn.ToString());
                        }
                        continue;
                    }

                    i++;
                    bool exported2 = false;
                    string error2 = null;
                    try
                    {
                        Kit kit = kits.GetKit(team.Id, kittype);
                        if (kit != null)
                        {
                            if (assetMode == "kitui")
                            {
                                exported2 = FifaEnvironment.ExportFileFromZdata(kit.MiniKitDdsFileName(), gameDir);
                            }
                            else
                            {
                                exported2 = kit.ExportKitTextures(gameDir);
                            }
                        }
                    }
                    catch (Exception exc)
                    {
                        error2 = exc.Message;
                    }

                    if (exported2)
                    {
                        ok++;
                    }
                    else
                    {
                        failed++;
                    }

                    var sb = new StringBuilder();
                    sb.Append("{\"t\":\"progress\",\"i\":").Append(i)
                      .Append(",\"total\":").Append(total)
                      .Append(",\"team\":").Append(team.Id)
                      .Append(",\"kittype\":").Append(kittype)
                      .Append(",\"ok\":").Append(exported2 ? "true" : "false");
                    if (error2 != null)
                    {
                        sb.Append(",\"error\":\"").Append(JsonEscape(error2)).Append("\"");
                    }
                    sb.Append("}");
                    Emit(sb.ToString());
                }
            }

            Emit("{\"t\":\"done\",\"ok\":" + ok + ",\"failed\":" + failed + "}");
            return 0;
        }
        catch (Exception exc)
        {
            Emit("{\"t\":\"error\",\"msg\":\"" + JsonEscape(exc.ToString()) + "\"}");
            return 1;
        }
    }
}
