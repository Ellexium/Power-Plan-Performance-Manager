import os
import sys
import re
import json
import ctypes
import subprocess
import threading
import tkinter as tk
import customtkinter as ctk
from datetime import datetime

import pystray
from PIL import Image, ImageDraw
from win10toast import ToastNotifier

try:
    import psutil  # type: ignore
except Exception:
    psutil = None

from sections import (
    UIBuildMixin,
    ProcessRefreshMixin,
    PowerStateMixin,
    ProcessActionsMixin,
    TrayRuntimeMixin,
    TelemetryMixin,
)


class PowerPlanWatcher(
    ctk.CTk,
    UIBuildMixin,
    ProcessRefreshMixin,
    PowerStateMixin,
    ProcessActionsMixin,
    TrayRuntimeMixin,
    TelemetryMixin,
):
    def __init__(self):
        super().__init__()
        self.title("Power Plan Manager (Custom Built)")
        self.geometry("1200x700")
        self.minsize(1020, 620)

        self.startup_var = tk.BooleanVar(value=self._is_task_created())

        # State
        self.power_schemes =[]
        self.name_by_guid = {}
        self.balanced_guid = None

        self.AUTO_DETECT_THRESHOLD = 90.0  # % CPU usage to trigger High Performance #
        self.AUTO_DETECT_CONFIRM_WAIT = 3   # Must be high for 2 polls (e.g., 10 seconds) before switching
        self.AUTO_DETECT_COOLDOWN = 4      # Number of poll cycles to stay High Perf after load drops #15 seconds since poll ms is 5000? 

        self.SETTINGS_FILENAME = "power_plan_watcher_settings.txt"
        self.SETTINGS_PATH = os.path.join(self.script_dir(), self.SETTINGS_FILENAME)

        self.TASK_NAME = "PowerPlanWatcherAutoStart"
        self.TASK_NAME_BAT = "PowerPlanWatcherKeepBusy"

        self.GUID_RE = re.compile(r"Power Scheme GUID:\s*([0-9a-fA-F-]{36})\s*\((.+?)\)\s*(\*)?")

        self.POLL_MS = 2000
        self.FREQ_POLL_MS = 1000  # 2 seconds for CPU frequency

        self.status_col = "black"
        self.freq_var = tk.StringVar(value="CPU: --- GHz")
        self.temp_var = tk.StringVar(value="Temp: --°C")

        self.logical_cpu_count = psutil.cpu_count(logical=True) if psutil else 1
        if not self.logical_cpu_count:
            self.logical_cpu_count = 1

        self.cpu_usage_var = tk.StringVar(value="Core Usage: --/--  Utilization: --%")
        self.mem_var = tk.StringVar(value="RAM: --/--")

        self.exclude_list = {"idle", "system", "powershell.exe"}
        self.heartbeat = {"powershell.exe"}

        self.disk_reset_timestamp = datetime.now()
        self.disk_reset_var = tk.StringVar(
            value=f"Since: {self.disk_reset_timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        self.proc_io_prev = {}          # pid -> {"read": int, "write": int}
        self.proc_io_accum = {}         # pid -> {"read": int, "write": int}
        self.disk_rows =[]             # rows for the disk tree
        self.disk_sort_col = "write_speed"
        self.disk_sort_reverse = True

        self.all_proc_names =[]
        self.all_proc_rows =[]
        self.thread_count_cache = {}   # pid -> int
        self.proc_io_cache = {}         # pid -> last write_bytes
        self.proc_write_rate_cache = {} # pid -> smoothed bytes/sec

        self.temp_watch_names = set()
        self.temp_cooldown_counter = 0

        self.search_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Ready.")
        
        # --- MISSING VARIABLE ADDED HERE ---
        self.dark_mode_var = tk.BooleanVar(value=True) 
        self.auto_mode = tk.BooleanVar(value=True)

        self.top_status_font = ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
        
        self.sort_col = "cpu_total"
        self.sort_reverse = True


        self._ui_interacting = False
        self._ui_pause_ms = 600
        self._ui_resume_job = None



        # Auto logic state
        self.last_exe_state = None  # watched running? True/False
        self.last_auto_target = None
        self._last_toast_key = None  # This fixes the specific error you got

        # Threading
        self._state_lock = threading.Lock()

        self._proc_snapshot = {
            "rows": [],
            "disk_rows": [],
            "any_heavy": False,
            "ready": False,
        }

        self._telemetry_snapshot = {
            "cpu": 0.0,
            "ram_percent": 0.0,
            "ram_used_gb": 0.0,
            "ram_total_gb": 0.0,
            "freq_ghz": None,
            "temp_text": "N/A",
            "ready": False,
        }

        self._process_worker_running = False
        self._process_worker_thread = None

        self._telemetry_worker_running = False
        self._telemetry_worker_thread = None

        # Watchlist
        self.watch_paths: list[str] =[]
        self.watch_names: set[str] = set()

        # Dynamic blacklist
        self.blacklist_paths: list[str] = []
        self.blacklist_names: set[str] = set()

        # Load saved settings
        s = self.load_settings()
        self.auto_mode.set(s.get("auto", "1") == "1")



        self.default_low_guid = tk.StringVar(value="")
        self.default_high_guid = tk.StringVar(value="")

        self.saved_default_low_guid = s.get("default_low_guid", "")
        self.saved_default_low_name = s.get("default_low_name", "")
        self.saved_default_high_guid = s.get("default_high_guid", "")
        self.saved_default_high_name = s.get("default_high_name", "")

        self.plan_config_low_list = None
        self.plan_config_high_list = None

        self.pause_status_var = tk.StringVar(value="Visual Updates Active")

        self.manual_plan_guid = tk.StringVar(value="")
        self.manual_plan_label_var = tk.StringVar(value="Auto")

        self.saved_manual_plan_guid = s.get("manual_plan_guid", "")
        self.manual_plan_guid.set(self.saved_manual_plan_guid)



        self.saved_exes = s.get("exes",[])
        self.saved_blacklist_exes = s.get("blacklist_exes", [])

        self.saved_graph_seconds = s.get("graph_seconds", "60")
        self.saved_graph_sources = list(s.get("graph_sources", ["CPU"] * 6))

        self.cpu_history = [0] * 60
        self.ram_history = [0] * 60

        self.disk_history_by_label = {}
        self.disk_mount_map = {}
        self.graph_source_options = ["CPU", "Memory"]

        self._disk_active_map = {}
        self._disk_sampler_running = False
        self._disk_sampler_thread = None
        self._disk_sampler_interval_sec = 2.0

        self.network_history_by_label = {}
        self.network_nic_map = {}
        self.network_live_stats = {}   # option label -> {"send_mbps": ..., "recv_mbps": ..., "total_mbps": ...}

        self._net_prev_totals = {}
        self._net_prev_split = {}

        self.gpu_history_by_label = {}
        self.gpu_sensor_map = {}          # dropdown label -> sensor descriptor
        self.gpu_live_values = {}         # dropdown label -> latest %


        self.current_cpu_util = 0.0
        self.current_ram_util = 0.0

        self._build_ui()
        self._bind_ui_interaction_pause()

        self._load_power_plans()
        self._start_disk_sampler()

        self._start_process_worker()
        self._start_telemetry_worker()

        self._load_watchlist_from_saved()
        self._load_blacklist_from_saved()

        self.thread_refresh_counter = 0

        self._refresh_job = None
        self._refresh_running = False
                
        self._toaster = ToastNotifier()
        self._schedule_refresh(0)

        self._last_toast_key = None
        self._update_freq_tick()
        self.high_load_consecutive_polls = 0


    def ts(self):
        return datetime.now().strftime("%H:%M:%S")

    def log(self, msg: str):
        print(f"[{self.ts()}] {msg}", flush=True)


    def run_powercfg(self, args):
        cmd = ["powercfg"] + args
        self.log(f"RUN: {' '.join(cmd)}")
        # Added creationflags here
        p = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            shell=False, 
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        if p.returncode != 0:
            stderr = (p.stderr or "").strip()
            stdout = (p.stdout or "").strip()
            msg = stderr if stderr else stdout if stdout else f"powercfg failed: {' '.join(cmd)}"
            self.log(f"ERROR: powercfg returned {p.returncode}: {msg}")
            raise RuntimeError(msg)
        out = (p.stdout or "").strip()
        return out

    def get_power_schemes(self):
        out = self.run_powercfg(["/list"])
        schemes = []
        for line in out.splitlines():
            m = self.GUID_RE.search(line)
            if m:
                schemes.append({
                    "guid": m.group(1),
                    "name": m.group(2),
                    "active": bool(m.group(3)),
                })
        self.log(f"Found {len(schemes)} power scheme(s).")
        return schemes

    def set_active_scheme(self, guid: str):
        self.run_powercfg(["/setactive", guid])


    def script_dir(self):
        try:
            return os.path.dirname(os.path.abspath(__file__))
        except Exception:
            return os.getcwd()






    def list_process_rows(self):
        """
        Returns list of rows: [{"exe": "chrome.exe", "path": "C:\\...\\chrome.exe"}]
        Only uses psutil because full paths are required.
        """
        rows = []
        if psutil is None:
            return rows

        seen = set()
        for p in psutil.process_iter(attrs=["name"]):
            try:
                name = (p.info.get("name") or "").strip()
                if not name:
                    continue

                # This can throw AccessDenied, NoSuchProcess, etc.
                path = p.exe()

                key = (name.lower(), (path or "").lower())
                if key in seen:
                    continue
                seen.add(key)

                rows.append({"exe": name, "path": path or ""})
            except Exception:
                continue

        rows.sort(key=lambda r: (r["exe"].lower(), r["path"].lower()))
        return rows

    def basename_exe(self, path: str) -> str:
        return os.path.basename(path).strip().lower()

    def find_balanced_guid(self, schemes):
        for s in schemes:
            if s["name"].strip().lower() == "balanced":
                return s["guid"]
        for s in schemes:
            if s["active"]:
                return s["guid"]
        return schemes[0]["guid"] if schemes else None

    def safe_write_text(self, path: str, text: str):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)

        data = {
            "auto": "1",
            "highest_guid": "",
            "highest_name": "",
            "exes": [],
            "blacklist_exes": [],
            "graph_seconds": "60",
            "graph_sources": ["CPU", "CPU", "CPU", "CPU", "CPU", "CPU"],
        }

        if not os.path.exists(self.SETTINGS_PATH):
            self.log(f"No settings file found at {self.SETTINGS_PATH}")
            return data

        self.log(f"Loading settings from {self.SETTINGS_PATH}")
        try:
            with open(self.SETTINGS_PATH, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("exe="):
                        data["exes"].append(line[4:].strip())
                    elif line.startswith("blacklist_exe="):
                        data["blacklist_exes"].append(line[len("blacklist_exe="):].strip())    
                    elif line.startswith("auto="):
                        data["auto"] = line.split("=", 1)[1].strip()
                    elif line.startswith("startup="): # Add this
                        data["startup"] = line.split("=", 1)[1].strip()
                    elif line.startswith("highest="):
                        rhs = line.split("=", 1)[1].strip()
                        if "|" in rhs:
                            g, n = rhs.split("|", 1)
                            data["highest_guid"] = g.strip()
                            data["highest_name"] = n.strip()
                        else:
                            data["highest_guid"] = rhs.strip()
                    elif line.startswith("graph_seconds="):
                        data["graph_seconds"] = line.split("=", 1)[1].strip()

                    elif line.startswith("graph_source_"):
                        left, rhs = line.split("=", 1)

                        try:
                            idx = int(left.replace("graph_source_", "").strip())
                        except Exception:
                            continue

                        if 0 <= idx < 6:
                            data["graph_sources"][idx] = rhs.strip() or "CPU"

        except Exception as e:
            self.log(f"Settings load error: {e}")
            return data

        self.log(f"Settings loaded: auto={data['auto']} highest_guid={data['highest_guid']} exes={len(data['exes'])}")
        return data

    def save_settings(
        self,
        auto_enabled: bool,
        startup_enabled: bool,
        exe_paths: list[str],
        blacklist_paths: list[str],
        graph_seconds: str,
        graph_sources: list[str],
        default_low_guid: str,
        default_low_name: str,
        default_high_guid: str,
        default_high_name: str,
        manual_plan_guid: str,

    ):
        lines = []
        lines.append("# power plan watcher settings")
        lines.append(f"auto={'1' if auto_enabled else '0'}")
        lines.append(f"startup={'1' if startup_enabled else '0'}")
        # lines.append(f"highest={highest_guid}|{highest_name}")
        lines.append(f"default_low={default_low_guid}|{default_low_name}")
        lines.append(f"default_high={default_high_guid}|{default_high_name}")

        lines.append(f"graph_seconds={graph_seconds}")
        lines.append(f"manual_plan_guid={manual_plan_guid}")


        for i in range(6):
            src = "CPU"
            if i < len(graph_sources):
                src = str(graph_sources[i] or "CPU").strip() or "CPU"

            lines.append(f"graph_source_{i}={src}")

        for p in exe_paths:
            lines.append(f"exe={p}")

        for p in blacklist_paths:
            lines.append(f"blacklist_exe={p}")

        self.safe_write_text(self.SETTINGS_PATH, "\n".join(lines) + "\n")
        self.log(f"Settings saved to {self.SETTINGS_PATH}")

    def load_settings(self):
        data = {
            "auto": "1",
            # "highest_guid": "",
            # "highest_name": "",
            "default_low_guid": "",
            "default_low_name": "",
            "default_high_guid": "",
            "default_high_name": "",
            "manual_plan_guid": "",

            "exes": [],
            "blacklist_exes": [],
            "graph_seconds": "60",
            "graph_sources": ["CPU", "CPU", "CPU", "CPU", "CPU", "CPU"],
        }

        if not os.path.exists(self.SETTINGS_PATH):
            self.log(f"No settings file found at {self.SETTINGS_PATH}")
            return data

        self.log(f"Loading settings from {self.SETTINGS_PATH}")
        try:
            with open(self.SETTINGS_PATH, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue

                    if line.startswith("exe="):
                        data["exes"].append(line[4:].strip())

                    elif line.startswith("blacklist_exe="):
                        data["blacklist_exes"].append(line[len("blacklist_exe="):].strip())

                    elif line.startswith("auto="):
                        data["auto"] = line.split("=", 1)[1].strip()

                    elif line.startswith("startup="):
                        data["startup"] = line.split("=", 1)[1].strip()

                    # elif line.startswith("highest="):
                    #     rhs = line.split("=", 1)[1].strip()
                    #     if "|" in rhs:
                    #         g, n = rhs.split("|", 1)
                    #         data["highest_guid"] = g.strip()
                    #         data["highest_name"] = n.strip()
                    #     else:
                    #         data["highest_guid"] = rhs.strip()

                    elif line.startswith("default_low="):
                        rhs = line.split("=", 1)[1].strip()
                        if "|" in rhs:
                            g, n = rhs.split("|", 1)
                            data["default_low_guid"] = g.strip()
                            data["default_low_name"] = n.strip()
                        else:
                            data["default_low_guid"] = rhs.strip()

                    elif line.startswith("default_high="):
                        rhs = line.split("=", 1)[1].strip()
                        if "|" in rhs:
                            g, n = rhs.split("|", 1)
                            data["default_high_guid"] = g.strip()
                            data["default_high_name"] = n.strip()
                        else:
                            data["default_high_guid"] = rhs.strip()

                    elif line.startswith("graph_seconds="):
                        data["graph_seconds"] = line.split("=", 1)[1].strip()

                    elif line.startswith("graph_source_"):
                        left, rhs = line.split("=", 1)
                        try:
                            idx = int(left.replace("graph_source_", "").strip())
                        except Exception:
                            continue

                        if 0 <= idx < 6:
                            data["graph_sources"][idx] = rhs.strip() or "CPU"

                    elif line.startswith("manual_plan_guid="):
                        data["manual_plan_guid"] = line.split("=", 1)[1].strip()
        

        except Exception as e:
            self.log(f"Settings load error: {e}")
            return data

        self.log(
            f"Settings loaded: auto={data['auto']} "
            f"low={data['default_low_guid']} "
            f"high={data['default_high_guid']} "
            f"exes={len(data['exes'])} "
            f"blacklist={len(data['blacklist_exes'])}"
        )
        return data

def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin():
    params = " ".join([f'"{arg}"' for arg in sys.argv])
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    sys.exit(0)


def main():
    if os.name != "nt":
        print("Windows only.")
        sys.exit(1)

    if not is_admin():
        relaunch_as_admin()

    app = PowerPlanWatcher()
    app.log("Starting GUI...")
    app.mainloop()


if __name__ == "__main__":
    main()