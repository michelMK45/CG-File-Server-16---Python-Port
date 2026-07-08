"""
Discord Rich Presence Runtime for Server16

Manages Discord RPC connection and presence updates for FIFA 16 match monitoring.
Provides graceful error handling and thread-safe operations.
"""

import io
import base64
import threading
import time
import logging
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from typing import Optional, Dict, Any

try:
    from PIL import Image as _PILImage
    PIL_AVAILABLE = True
except ImportError:
    _PILImage = None
    PIL_AVAILABLE = False

_RPC_IMAGE_MAX_PX = 1024  # Discord RPC recommended max image dimension

try:
    import requests as _requests
    REQUESTS_AVAILABLE = True
except ImportError:
    _requests = None
    REQUESTS_AVAILABLE = False

_PREVIEW_CACHE_TTL = 23 * 3600  # 23 hours (Discord webhook URLs expire ~24h)
_PENDING_SENTINEL = "__pending__"
_FAILED_SENTINEL = "__failed__"
_FAILURE_COOLDOWN = 5 * 60  # don't retry a failed upload for 5 minutes


class StadiumPreviewUploader:
    """
    Uploads stadium preview images and caches resulting URLs for reuse
    within the same session.

    All uploads are performed in daemon threads so they never block the
    main game-stats loop.
    """

    def __init__(
        self,
        webhook_url: str,
        logger: Optional[logging.Logger] = None,
        provider: str = "discord_webhook",
        imgur_client_id: str = "",
        imgbb_api_key: str = "",
    ) -> None:
        self._webhook_url = webhook_url
        self._logger = logger or logging.getLogger(__name__)
        self._provider = (provider or "discord_webhook").strip().lower()
        self._imgur_client_id = (imgur_client_id or "").strip()
        self._imgbb_api_key = (imgbb_api_key or "").strip()
        # { stadium_name: (attachment_url, upload_timestamp) }
        self._cache: Dict[str, tuple] = {}
        self._lock = threading.Lock()
        # Callbacks called with (stadium_name, url) after a successful upload
        self._on_upload_callbacks: list = []

    def add_upload_callback(self, cb) -> None:
        """Register a callback invoked on the main thread after a successful upload."""
        with self._lock:
            self._on_upload_callbacks.append(cb)

    def get_cached_url(self, stadium_name: str) -> Optional[str]:
        """Return a valid cached URL or None if missing / expired."""
        with self._lock:
            entry = self._cache.get(stadium_name)
            if entry is None:
                return None
            url, ts = entry
            if url in (_PENDING_SENTINEL, _FAILED_SENTINEL):
                return None
            if time.time() - ts > _PREVIEW_CACHE_TTL:
                del self._cache[stadium_name]
                return None
            return url

    def get_or_upload(self, stadium_name: str, local_path: Path, webhook_url: Optional[str] = None) -> Optional[str]:
        """
        Return cached URL if still valid, otherwise schedule an async upload.

        Returns the cached URL immediately if available, or None while the
        upload thread is running.  Once the thread completes the registered
        callbacks are fired so the caller can refresh the presence.
        """
        if not REQUESTS_AVAILABLE:
            return None

        cached = self.get_cached_url(stadium_name)
        if cached:
            return cached

        provider = self._provider
        effective_webhook = webhook_url or self._webhook_url
        if provider == "imgur":
            if not self._imgur_client_id:
                self._logger.warning("Imgur provider selected but stadium_preview_imgur_client_id is empty")
                return None
        elif provider == "imgbb":
            if not self._imgbb_api_key:
                self._logger.warning("ImgBB provider selected but stadium_preview_imgbb_api_key is empty")
                return None
        elif not effective_webhook:
            return None

        # Avoid launching duplicate threads for the same stadium
        with self._lock:
            entry = self._cache.get(stadium_name)
            if entry is not None:
                sentinel, ts = entry
                still_cooling_down = (
                    sentinel == _FAILED_SENTINEL and time.time() - ts < _FAILURE_COOLDOWN
                )
                if sentinel == _PENDING_SENTINEL or still_cooling_down:
                    return None  # Upload already in-flight, or recently failed
            # Reserve the slot so a second call won't start another thread
            self._cache[stadium_name] = (_PENDING_SENTINEL, time.time())

        t = threading.Thread(
            target=self._upload_thread,
            args=(stadium_name, local_path, effective_webhook, provider, self._imgur_client_id, self._imgbb_api_key),
            daemon=True,
        )
        t.start()
        return None

    def _prepare_image_bytes(self, local_path: Path) -> tuple:
        """Return (filename, bytes_io, content_type), resizing to <=1024px if needed."""
        suffix = local_path.suffix.lower()
        content_type = "image/png" if suffix == ".png" else "image/jpeg"
        filename = local_path.name
        if PIL_AVAILABLE:
            try:
                img = _PILImage.open(local_path)
                w, h = img.size
                if w > _RPC_IMAGE_MAX_PX or h > _RPC_IMAGE_MAX_PX:
                    img.thumbnail((_RPC_IMAGE_MAX_PX, _RPC_IMAGE_MAX_PX), _PILImage.LANCZOS)
                    self._logger.debug(f"Stadium preview resized {w}x{h} -> {img.size} for Discord RPC")
                buf = io.BytesIO()
                fmt = "PNG" if suffix == ".png" else "JPEG"
                save_kwargs = {} if fmt == "PNG" else {"quality": 90}
                img.save(buf, format=fmt, **save_kwargs)
                buf.seek(0)
                return filename, buf, content_type
            except Exception as e:
                self._logger.debug(f"PIL resize skipped ({e}), uploading original")
        with open(local_path, "rb") as fh:
            return filename, io.BytesIO(fh.read()), content_type

    def _upload_to_discord_webhook(self, image_bytes: io.BytesIO, filename: str, content_type: str, webhook_url: str) -> Optional[str]:
        """Upload preview image to Discord webhook and return attachment URL."""
        webhook_url = self._with_wait_true(webhook_url)
        response = _requests.post(
            webhook_url,
            files={"file": (filename, image_bytes, content_type)},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        attachments = data.get("attachments", [])
        if not attachments:
            return None
        first_attachment = attachments[0]
        return first_attachment.get("url") or first_attachment.get("proxy_url")

    def _upload_to_imgur(self, image_bytes: io.BytesIO, filename: str, content_type: str, imgur_client_id: str) -> Optional[str]:
        """Upload preview image to Imgur and return public link."""
        headers = {"Authorization": f"Client-ID {imgur_client_id}"}
        response = _requests.post(
            "https://api.imgur.com/3/image",
            headers=headers,
            files={"image": (filename, image_bytes, content_type)},
            data={"type": "file"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            return None
        data = payload.get("data", {})
        return data.get("link")

    def _upload_to_imgbb(self, image_bytes: io.BytesIO, imgbb_api_key: str) -> Optional[str]:
        """Upload preview image to ImgBB and return public link."""
        encoded = base64.b64encode(image_bytes.getvalue()).decode("ascii")
        response = _requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": imgbb_api_key, "image": encoded},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            return None
        data = payload.get("data", {})
        return data.get("url") or data.get("display_url")

    def _upload_thread(
        self,
        stadium_name: str,
        local_path: Path,
        webhook_url: str,
        provider: str,
        imgur_client_id: str,
        imgbb_api_key: str,
    ) -> None:
        """Worker that performs the multipart upload and updates the cache."""
        try:
            filename, image_bytes, content_type = self._prepare_image_bytes(local_path)
            if provider == "imgur":
                url = self._upload_to_imgur(image_bytes, filename, content_type, imgur_client_id)
            elif provider == "imgbb":
                url = self._upload_to_imgbb(image_bytes, imgbb_api_key)
            else:
                url = self._upload_to_discord_webhook(image_bytes, filename, content_type, webhook_url)
            if not url:
                self._logger.warning(f"Preview upload returned no URL for '{stadium_name}' (provider={provider})")
                self._mark_failed(stadium_name)
                return
            # Strip trailing '&' that Discord CDN sometimes appends to signed URLs.
            url = url.rstrip("&")
            with self._lock:
                self._cache[stadium_name] = (url, time.time())
                callbacks = list(self._on_upload_callbacks)
            self._logger.info(f"Stadium preview uploaded for '{stadium_name}' (provider={provider}): {url}")
            for cb in callbacks:
                try:
                    cb(stadium_name, url)
                except Exception as e:
                    self._logger.debug(f"Upload callback error: {e}")
        except Exception as e:
            self._logger.warning(f"Failed to upload stadium preview for '{stadium_name}': {e}")
            self._mark_failed(stadium_name)

    def _with_wait_true(self, webhook_url: str) -> str:
        """Ensure webhook URL includes wait=true so Discord returns attachment metadata."""
        parts = urlsplit(webhook_url)
        query_items = dict(parse_qsl(parts.query, keep_blank_values=True))
        query_items["wait"] = "true"
        new_query = urlencode(query_items)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))

    def _mark_failed(self, stadium_name: str) -> None:
        """Record a failed upload so retries wait out _FAILURE_COOLDOWN instead of spamming."""
        with self._lock:
            self._cache[stadium_name] = (_FAILED_SENTINEL, time.time())

try:
    from pypresence import Presence
    PYPRESENCE_AVAILABLE = True
except ImportError:
    PYPRESENCE_AVAILABLE = False
    Presence = None


class DiscordRPCRuntime:
    """
    Manages Discord Rich Presence (IPC) for FIFA 16 match state.
    
    - Thread-safe, non-blocking operations
    - Automatic reconnection with exponential backoff
    - Graceful degradation if Discord is not available
    - No data sent to external servers (local IPC only)
    """
    
    def __init__(self, client_id: str, logger: Optional[logging.Logger] = None):
        """
        Initialize Discord RPC runtime.
        
        Args:
            client_id: Discord Application Client ID
            logger: Optional logger instance
        """
        self.client_id = client_id
        self.logger = logger or logging.getLogger(__name__)
        self.client = None
        self.connected = False
        self._lock = threading.Lock()
        self._last_presence = None
        self._last_update_time = 0.0
        self._connection_failed = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5
        self._reconnect_backoff = 2  # seconds, exponential
        self._error_already_logged = False  # Prevent log spam
        self.team_name_resolver: Optional[callable] = None  # Callback to resolve team IDs to names
        
    def connect(self) -> bool:
        """
        Establish connection to Discord IPC.
        
        Returns:
            True if connection successful, False otherwise
        """
        with self._lock:
            if self.connected:
                return True
            
            if not PYPRESENCE_AVAILABLE:
                if not self._error_already_logged:
                    self.logger.error(
                        "pypresence not installed. Install with: pip install pypresence"
                    )
                    self._error_already_logged = True
                self._connection_failed = True
                return False
            
            try:
                self.client = Presence(self.client_id)
                self.client.connect()
                self.connected = True
                self._connection_failed = False
                self._reconnect_attempts = 0
                self._error_already_logged = False
                self.logger.info(f"Discord RPC connected (Client ID: {self.client_id})")
                return True
                
            except Exception as e:
                if not self._error_already_logged:
                    self.logger.warning(f"Failed to connect to Discord RPC: {e}")
                    self._error_already_logged = True
                self._connection_failed = True
                self._reconnect_attempts += 1
                return False
    
    def disconnect(self) -> None:
        """Gracefully disconnect from Discord RPC and clear presence."""
        with self._lock:
            # Try to clear presence even if not explicitly connected
            if self.client or PYPRESENCE_AVAILABLE:
                try:
                    # If not connected, try to connect briefly just to clear
                    if not self.connected and self.client is None and PYPRESENCE_AVAILABLE:
                        try:
                            self.client = Presence(self.client_id)
                            self.client.connect(timeout=2)
                        except Exception:
                            pass
                    
                    # Clear presence
                    if self.client:
                        try:
                            self.client.clear()
                            self.logger.debug("Discord presence cleared")
                        except Exception as e:
                            self.logger.debug(f"Error clearing Discord presence: {e}")
                    
                    # Close connection
                    if self.client:
                        try:
                            self.client.close()
                        except Exception as e:
                            self.logger.debug(f"Error closing Discord RPC connection: {e}")
                            
                except Exception as e:
                    self.logger.debug(f"Error during disconnect: {e}")
                finally:
                    self.client = None
                    self.connected = False
                    self._last_presence = None
                    self._error_already_logged = False
    
    def is_connected(self) -> bool:
        """Check if currently connected to Discord."""
        with self._lock:
            return self.connected
    
    def set_team_name_resolver(self, resolver: Optional[callable]) -> None:
        """
        Set a callback function to resolve team IDs to team names.
        
        Args:
            resolver: Callable(team_id: str | int) -> Optional[str]
                     Returns team name for the given ID, or None if not found
        """
        with self._lock:
            self.team_name_resolver = resolver
    
    def update_presence(
        self,
        state: Optional[str] = None,
        details: Optional[str] = None,
        large_image: str = "fifa16",
        large_text: str = "FIFA 16",
        small_image: Optional[str] = None,
        small_text: Optional[str] = None,
        buttons: Optional[list] = None,
    ) -> bool:
        """
        Update Discord Rich Presence display.
        
        Args:
            state: Primary state text (e.g., "Playing vs Arsenal | 0-1 | 45:30")
            details: Secondary details text (e.g., "Premier League - Round 30")
            large_image: Large image asset key
            large_text: Hover text for large image
            small_image: Small image asset key
            small_text: Hover text for small image
            buttons: List of {"label": str, "url": str} dicts (max 2)
        
        Returns:
            True if update sent successfully, False otherwise
        """
        # If pypresence not available, don't even try
        if not PYPRESENCE_AVAILABLE:
            return False
        
        if not state and not details:
            # Clear presence if both empty
            self._clear_presence_internal()
            return True
        
        # Build presence dictionary
        presence_data = {
            "state": state,
            "details": details,
            "large_image": large_image,
            "large_text": large_text,
        }
        
        if small_image:
            presence_data["small_image"] = small_image
        if small_text:
            presence_data["small_text"] = small_text
        if buttons:
            presence_data["buttons"] = buttons[:2]  # Discord max 2 buttons
        
        # Add timestamp
        presence_data["start"] = int(time.time())
        
        # Check if presence changed
        if presence_data == self._last_presence:
            return True
        
        # Attempt to send or reconnect
        with self._lock:
            if not self.connected:
                # Try to reconnect if we haven't hit max attempts and not permanently failed
                if self._reconnect_attempts < self._max_reconnect_attempts and not self._connection_failed:
                    self._try_reconnect()
                elif self._connection_failed:
                    return False
            
            if self.connected and self.client:
                try:
                    rpc_response = self.client.update(**presence_data)
                    self.logger.info(f"Discord RPC update response: {rpc_response}")
                    self._last_presence = presence_data.copy()
                    return True
                except Exception as e:
                    self.logger.warning(f"Failed to update Discord presence: {e}")
                    self.connected = False
                    return False
        
        return False
    
    def _try_reconnect(self) -> None:
        """Attempt to reconnect to Discord with backoff."""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            return
        
        if not PYPRESENCE_AVAILABLE:
            return
        
        # Exponential backoff: don't attempt every frame
        backoff_time = min(self._reconnect_backoff ** self._reconnect_attempts, 30)
        current_time = time.time()
        
        if current_time - self._last_update_time < backoff_time:
            return
        
        self._last_update_time = current_time
        try:
            self.client = Presence(self.client_id)
            self.client.connect()
            self.connected = True
            self._reconnect_attempts = 0
            self.logger.info("Discord RPC reconnected")
        except Exception as e:
            self._reconnect_attempts += 1
            self.logger.debug(f"Reconnection attempt {self._reconnect_attempts} failed: {e}")
    
    def _clear_presence_internal(self) -> None:
        """Clear presence display (internal, no lock)."""
        if self.connected and self.client:
            try:
                self.client.clear()
                self._last_presence = None
            except Exception as e:
                self.logger.debug(f"Failed to clear presence: {e}")
    
    def build_match_presence(
        self,
        home_team: str = "",
        away_team: str = "",
        home_score: int = 0,
        away_score: int = 0,
        match_time: str = "00:00",
        tournament: str = "",
        round_name: str = "",
        stadium: str = "",
        game_state: str = "Idle",
        home_team_image: Optional[str] = None,
        away_team_image: Optional[str] = None,
        stadium_image_url: Optional[str] = None,
        external_image_mode: str = "button_fallback",
    ) -> Dict[str, Any]:
        """
        Build a complete match presence from game state data.
        
        Args:
            home_team: Home team name or ID
            away_team: Away team name or ID
            home_score: Home team goals
            away_score: Away team goals
            match_time: Match time (e.g., "45:30")
            tournament: Tournament name
            round_name: Round/league name
            stadium: Stadium name
            game_state: Game state (Idle, Paused, Running)
            home_team_image: Image asset key for home team
            away_team_image: Image asset key for away team
        
        Returns:
            Dictionary ready for update_presence()
        """
        # Resolve team names from IDs if resolver available
        if self.team_name_resolver:
            # Check if home_team looks like a numeric ID
            if home_team and home_team.isdigit():
                resolved_name = self.team_name_resolver(home_team)
                if resolved_name:
                    home_team = resolved_name
            # Check if away_team looks like a numeric ID
            if away_team and away_team.isdigit():
                resolved_name = self.team_name_resolver(away_team)
                if resolved_name:
                    away_team = resolved_name
        
        normalized_state = str(game_state or "").strip().lower()
        compact_state = normalized_state.replace("_", " ").replace("-", " ")

        # Accept common runtime/UI variants so localized labels do not break RPC state.
        is_running = (
            compact_state in {"running", "run", "en ejecución", "en ejecucion", "rodando"}
            or compact_state.startswith("run")
        )
        is_paused = (
            compact_state in {"paused", "pause", "pausado"}
            or compact_state.startswith("paus")
        )
        is_live = is_running or is_paused

        # Determine state line
        if home_team and away_team:
            if is_running:
                state_text = f"{home_team} {home_score}-{away_score} {away_team} | {match_time}"
            elif is_paused:
                state_text = f"Paused | {home_team} {home_score}-{away_score} {away_team} | {match_time}"
            else:
                state_text = f"{home_team} vs {away_team} | waiting to start"
        else:
            if is_paused:
                state_text = f"Paused | {match_time}"
            elif is_running:
                state_text = f"Match in progress | {match_time}"
            else:
                state_text = "Browsing FIFA 16"
        
        # Determine details line
        # If in a live match with stadium, prioritize stadium name (ignore numeric IDs)
        if is_live and stadium:
            details_text = stadium
        elif tournament and round_name:
            # Only show tournament/round if they're not numeric IDs
            if not (tournament.isdigit() or round_name.isdigit()):
                details_text = f"{tournament} - {round_name}"
            else:
                details_text = "Match in progress"
        elif tournament and not tournament.isdigit():
            details_text = tournament
        elif round_name and not round_name.isdigit():
            details_text = round_name
        elif is_live:
            details_text = "Match in progress"
        else:
            details_text = "Not in a match"
        
        # Determine large image: stadium preview URL if available, else default asset
        large_text = f"{stadium}" if stadium else "FIFA 16"
        preview_button = None
        if stadium_image_url:
            # Support multiple external-image formats for RPC compatibility testing.
            _url = stadium_image_url.strip().rstrip("&")
            if not (_url.startswith("https://") or _url.startswith("http://")):
                _url = f"https://{_url}"
            mode = (external_image_mode or "").strip().lower()
            if mode == "url":
                large_image = _url
            elif mode == "mp_external_raw":
                large_image = f"mp:external/{_url}"
            elif mode == "mp_external_no_scheme":
                _no_scheme = _url
                for _scheme in ("https://", "http://"):
                    if _no_scheme.startswith(_scheme):
                        _no_scheme = _no_scheme[len(_scheme):]
                        break
                large_image = f"mp:external/{_no_scheme}"
            elif mode == "mp_external_encoded":
                large_image = f"mp:external/{quote(_url, safe='')}"
            else:
                # Stable fallback: no broken image, provide preview via button.
                large_image = "fifa16"
                preview_button = {"label": "Stadium Preview", "url": _url}
        else:
            large_image = "fifa16"

        # Only include a small image when a stadium preview exists.
        has_stadium_preview = bool((stadium_image_url or "").strip())

        presence = {
            "state": state_text,
            "details": details_text,
            "large_image": large_image,
            "large_text": large_text,
        }
        if has_stadium_preview:
            presence["small_image"] = "fifa16"
            presence["small_text"] = "FIFA 16"
        if preview_button is not None:
            presence["buttons"] = [preview_button]
        return presence
