"""System tray integration for 巡查者 agent.

Provides a Windows system tray icon with a right-click menu and
balloon notifications for critical alerts. Falls back gracefully
if the tray cannot be created (e.g. headless environment).
"""

from __future__ import annotations

import logging
import os
import webbrowser
from typing import Any, Callable, Dict, Optional

from agent.alert import Alert, AlertSeverity, AlertStore

logger = logging.getLogger(__name__)

# Pystray is an optional dependency — degrade gracefully.
_TRAY_AVAILABLE = False
try:
    import pystray
    from PIL import Image, ImageDraw

    _TRAY_AVAILABLE = True
except ImportError:
    logger.warning("pystray not available — system tray disabled")


def _generate_icon(size: int = 64) -> "Image.Image":
    """Generate a simple shield icon for the system tray.

    Creates a blue shield shape with a white border.
    """
    from PIL import Image, ImageDraw  # re-import for type-checking

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    margin = size // 10
    top = margin
    bottom = size - margin
    left = margin
    right = size - margin

    # Shield shape: pointed bottom.
    shield_points = [
        (size // 2, top),           # top point
        (right, top + size // 4),   # right shoulder
        (right, size // 2),          # right mid
        (size // 2, bottom),         # bottom point
        (left, size // 2),           # left mid
        (left, top + size // 4),    # left shoulder
    ]

    draw.polygon(shield_points, fill=(30, 100, 220, 255), outline="white", width=2)

    cx, cy = size // 2, size // 2 - size // 10
    cross_size = size // 6
    draw.line([(cx - cross_size, cy), (cx + cross_size, cy)], fill="white", width=2)
    draw.line([(cx, cy - cross_size), (cx, cy + cross_size)], fill="white", width=2)

    return image




class SystemTray:
    """Windows system tray icon with menu and alert notifications.

    Parameters
    ----------
    alert_store : AlertStore
        Alert system — subscribes to critical alerts for balloon
        notifications.
    api_host : str
    api_port : int
    """

    _ALERT_PREFIX = "[巡查者] "

    def __init__(
        self,
        alert_store: AlertStore,
        api_host: str = "127.0.0.1",
        api_port: int = 8099,
    ) -> None:
        self._alert_store = alert_store
        self._api_url = f"http://{api_host}:{api_port}"
        self._icon: Optional["pystray.Icon"] = None
        self._paused = False
        self._request_shutdown: Optional[Callable[[], None]] = None


    def start(self) -> None:
        """Create and show the tray icon.  Non-blocking — runs in its own thread."""
        if not _TRAY_AVAILABLE:
            logger.info("System tray not available (pystray missing)")
            return

        try:
            icon_image = _generate_icon()
            menu = self._build_menu()
            self._icon = pystray.Icon(
                "patroller",
                icon_image,
                "巡查者 — Security Monitor",
                menu,
            )

            # Subscribe to critical alerts for balloon notifications.
            self._alert_store.subscribe(self._on_alert)

            # Run the tray icon in a daemon thread (pystray runs its own event loop).
            import threading

            t = threading.Thread(target=self._icon.run, daemon=True)
            t.start()
            logger.info("System tray started")
        except Exception:
            logger.exception("Failed to start system tray")

    def stop(self) -> None:
        """Remove the tray icon."""
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
            logger.info("System tray stopped")

    def _on_alert(self, alert: Alert) -> None:
        """Show a balloon notification for critical alerts."""
        if alert.severity != AlertSeverity.CRITICAL:
            return
        if self._paused:
            return
        if self._icon and hasattr(self._icon, "notify"):
            try:
                message = alert.message
                if len(message) > 120:
                    message = message[:117] + "..."
                self._icon.notify(
                    message,
                    self._ALERT_PREFIX + "Critical Alert",
                )
                logger.debug("Tray notification: %s", alert.message)
            except Exception:
                logger.exception("Failed to show tray notification")

    def _build_menu(self) -> Any:
        """Build the right-click context menu.

        Returns
        -------
        pystray.Menu
            The menu structure.
        """
        import pystray

        return pystray.Menu(
            pystray.MenuItem(
                "Show Dashboard",
                self._on_dashboard,
                default=True,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Pause / Resume",
                self._on_pause_resume,
                checked=lambda item: self._paused,
            ),
            pystray.MenuItem(
                "Settings",
                self._on_settings,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Exit",
                self._on_exit,
            ),
        )

    def _on_dashboard(self, icon: Any, item: Any) -> None:
        """Open the API docs / dashboard in the default browser."""
        try:
            webbrowser.open(self._api_url + "/docs")
        except Exception:
            logger.exception("Failed to open browser")

    def _on_pause_resume(self, icon: Any, item: Any) -> None:
        """Toggle pause/resume state."""
        self._paused = not self._paused
        state = "paused" if self._paused else "resumed"
        logger.info("Monitoring %s", state)

    def _on_settings(self, icon: Any, item: Any) -> None:
        """Open settings dialog (placeholder for future)."""
        # Phase 1: open the config file in notepad.
        config_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "config.yaml"
        )
        try:
            os.startfile(config_path)
        except Exception:
            logger.warning("Could not open config file: %s", config_path)

    def _on_exit(self, icon: Any, item: Any) -> None:
        """Request agent shutdown."""
        logger.info("Exit requested from tray")
        if self._request_shutdown:
            self._request_shutdown()
        self.stop()

    @property
    def paused(self) -> bool:
        """Return whether monitoring is currently paused."""
        return self._paused
