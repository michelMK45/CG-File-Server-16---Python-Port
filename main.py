def _start_splash():
    # Before anything heavy is imported: the imports below are most of the
    # startup time, so the splash has to be up first to cover them.
    try:
        from server16_py.splash import SplashScreen, enable_dpi_awareness

        enable_dpi_awareness()
        return SplashScreen()
    except Exception:
        return None


def _close_bootloader_splash():
    # In the onefile exe, PyInstaller's bootloader shows a static image while
    # it unpacks (see Server16Python.spec). Closed only now, once the live
    # splash is already on screen over it, so the two overlap with no gap.
    # The module doesn't exist outside such a build.
    try:
        import pyi_splash

        pyi_splash.close()
    except Exception:
        pass


if __name__ == "__main__":
    splash = _start_splash()
    _close_bootloader_splash()
    try:
        from server16_py.app import main

        main(splash=splash)
    except BaseException:
        if splash is not None:
            splash.close()
        raise
