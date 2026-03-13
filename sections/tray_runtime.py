import threading
import threading
import pystray
from PIL import Image, ImageDraw

class TrayRuntimeMixin:

    def _make_tray_icon_image(self, size=64):
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((6, 6, size - 6, size - 6), fill=(40, 120, 255, 255))
        d.rectangle((size * 0.42, size * 0.30, size * 0.58, size * 0.72), fill=(255, 255, 255, 255))
        return img

    def _run_tray(self, icon):
        icon.run()
        
    def _ensure_tray(self):
        if self._tray_icon is not None:
            return

        def on_restore(icon, item):
            self.after(0, self._restore_from_tray)

        def on_exit(icon, item):
            self.after(0, self._exit_app)

        menu = pystray.Menu(
            pystray.MenuItem("Restore", on_restore),
            pystray.MenuItem("Exit", on_exit),
        )

        self._tray_icon = pystray.Icon(
            "PowerPlanWatcher",
            self._make_tray_icon_image(),
            "Power Plan Watcher",
            menu,
        )

        self._tray_thread = threading.Thread(target=self._run_tray, args=(self._tray_icon,), daemon=True)
        self._tray_thread.start()

    def _hide_to_tray(self):
        self._ensure_tray()
        self.withdraw()  # hide window

    def _restore_from_tray(self):
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except Exception:
            pass


    def _ensure_tray(self):
        if self._tray_icon is not None:
            return

        def on_restore(icon, item):
            self.after(0, self._restore_from_tray)

        def on_exit(icon, item):
            self.after(0, self._exit_app)

        menu = pystray.Menu(
            pystray.MenuItem("Restore", on_restore),
            pystray.MenuItem("Exit", on_exit),
        )

        self._tray_icon = pystray.Icon(
            "PowerPlanWatcher",
            self._make_tray_icon_image(),
            "Power Plan Watcher",
            menu,
        )

        self._tray_thread = threading.Thread(target=self._run_tray, args=(self._tray_icon,), daemon=True)
        self._tray_thread.start()

    def _hide_to_tray(self):
        self._ensure_tray()
        self.withdraw()  # hide window

    def _restore_from_tray(self):
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except Exception:
            pass


    def _on_window_state_change(self, _evt=None):
        # Tk: minimize triggers Unmap; if state is iconic, we tray-hide
        try:
            if self.state() == "iconic":
                self._hide_to_tray()
        except Exception:
            pass

    def _on_close_clicked(self):
        # Clicking X should also minimize to tray (common behavior)
        self._hide_to_tray()

    def _exit_app(self):
        self._allow_close = True
        self._disk_sampler_running = False
        self._process_worker_running = False
        self._telemetry_worker_running = False

        try:
            if self._tray_icon:
                self._tray_icon.stop()
        except Exception:
            pass

        self.destroy()