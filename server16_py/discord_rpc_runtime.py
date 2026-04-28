"""
Discord Rich Presence Runtime for Server16

Manages Discord RPC connection and presence updates for FIFA 16 match monitoring.
Provides graceful error handling and thread-safe operations.
"""

import threading
import time
import logging
from typing import Optional, Dict, Any

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
        large_text: str = "FIFA 16 Server16",
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
                    self.client.update(**presence_data)
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
        
        normalized_state = (game_state or "").strip().lower()
        is_running = normalized_state == "running"
        is_paused = normalized_state == "paused"
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
        
        # Determine large image
        large_text = f"Stadium: {stadium}" if stadium else "FIFA 16 Server16"
        
        # Use small image if available
        small_image = home_team_image or away_team_image
        small_text = home_team or away_team or None
        
        return {
            "state": state_text,
            "details": details_text,
            "large_image": "fifa16",
            "large_text": large_text,
            "small_image": small_image,
            "small_text": small_text,
        }
