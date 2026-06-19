from __future__ import annotations

import traceback
from datetime import datetime


class LogMixin:
    """File and widget logging system — part of Server16App via multiple inheritance."""

    def _install_exception_hook(self) -> None:
        def report(exc_type, exc_value, exc_tb):
            self.log("Unhandled exception", exc_value, exc_info=(exc_type, exc_value, exc_tb))

        self.report_callback_exception = report

    def _build_runtime_log_header(self) -> str:
        mapped_executable = self.settings.fifa_exe or "default"
        settings_path = self.settings.path
        return "\n".join(
            (
                f"Mapped executable: {mapped_executable}",
                f"Settings file: {settings_path}",
            )
        ) + "\n"

    def _prepare_runtime_log(self) -> None:
        header = self._build_runtime_log_header()
        try:
            if self.log_path.exists():
                previous_content = self.log_path.read_text(encoding="utf-8", errors="replace")
                if previous_content and previous_content != header:
                    self.log_backup_path.write_text(previous_content, encoding="utf-8")
            self.log_path.write_text(header, encoding="utf-8")
        except Exception:
            pass

    def log(self, message: str, error: Exception | None = None, exc_info=None) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}"
        if error is not None:
            line = f"{line}: {error}"
        if exc_info is not None:
            line = f"{line}\n{''.join(traceback.format_exception(*exc_info)).strip()}"
        elif error is not None:
            line = f"{line}\n{traceback.format_exc().strip()}" if traceback.format_exc().strip() != "NoneType: None" else line
        try:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except Exception:
            pass
        if self.log_widget is not None:
            if self._log_filter_pointer_trace and message.startswith("Pointer trace"):
                return
            if self._log_filter_discord_rpc and (message.startswith("DiscordRPC") or message.startswith("Discord ")):
                return
            self.log_widget.configure(state="normal")
            self.log_widget.insert("end", line + "\n")
            if self._log_autofollow:
                self.log_widget.see("end")
            self.log_widget.configure(state="disabled")

    def _log_widget_is_near_bottom(self) -> bool:
        if self.log_widget is None:
            return True
        _first, last = self.log_widget.yview()
        return last >= 0.995

    def _refresh_log_autofollow_state(self, _event=None) -> None:
        pass

    def _on_filter_pointer_trace_toggled(self) -> None:
        if self._log_filter_pointer_trace_var is None:
            return
        self._log_filter_pointer_trace = self._log_filter_pointer_trace_var.get()

    def _on_filter_discord_rpc_toggled(self) -> None:
        if self._log_filter_discord_rpc_var is None:
            return
        self._log_filter_discord_rpc = self._log_filter_discord_rpc_var.get()

    def _on_autofollow_toggled(self) -> None:
        if self._log_autofollow_var is None:
            return
        self._log_autofollow = self._log_autofollow_var.get()
        if self._log_autofollow and self.log_widget is not None:
            self.log_widget.see("end")
        self._update_log_follow_ui()

    def _jump_logs_to_latest(self) -> None:
        if self.log_widget is None:
            return
        self._log_autofollow = True
        self.log_widget.see("end")
        self._update_log_follow_ui()

    def _update_log_follow_ui(self) -> None:
        if self._log_autofollow_var is not None:
            self._log_autofollow_var.set(self._log_autofollow)
        if self.log_follow_button is not None:
            self.log_follow_button.configure(state="disabled" if self._log_autofollow else "normal")
