import os
import subprocess
from tkinter import messagebox

try:
    import psutil  # type: ignore
except Exception:
    psutil = None


class ProcessActionsMixin:


    def _end_task(self, exe_name, path):
        if psutil is None:
            raise RuntimeError("psutil is not available.")

        exe_name = (exe_name or "").strip().lower()
        path = os.path.normpath(path).strip().lower() if path else ""

        matched = []

        for p in psutil.process_iter(attrs=["pid", "name"]):
            try:
                p_name = (p.info.get("name") or "").strip().lower()
                p_path = ""
                try:
                    p_path = os.path.normpath(p.exe()).strip().lower()
                except Exception:
                    p_path = ""

                if path:
                    if p_path == path:
                        matched.append(p)
                else:
                    if p_name == exe_name:
                        matched.append(p)
            except Exception:
                continue

        if not matched:
            raise RuntimeError("Could not find a matching running process to end.")

        errors = []

        for p in matched:
            try:
                p.terminate()
            except Exception as e:
                errors.append(f"PID {p.pid}: {e}")

        gone, alive = psutil.wait_procs(matched, timeout=3)

        for p in alive:
            try:
                p.kill()
            except Exception as e:
                errors.append(f"PID {p.pid}: {e}")

        gone2, alive2 = psutil.wait_procs(alive, timeout=2)

        if alive2:
            alive_pids = ", ".join(str(p.pid) for p in alive2)
            extra = ""
            if errors:
                extra = "\n\n" + "\n".join(errors)
            raise RuntimeError(f"Failed to end process(es): {alive_pids}{extra}")

    def _go_to_path(self, path):
        path = (path or "").strip()

        if not path:
            raise RuntimeError("This item does not have a file path.")

        norm = os.path.normpath(path)

        if not os.path.exists(norm):
            raise RuntimeError(f"Path does not exist:\n{norm}")

        subprocess.Popen(
            ["explorer", "/select,", norm],
            creationflags=subprocess.CREATE_NO_WINDOW
        )

    def _end_task_from_dialog(self, dialog, exe_name, path):
        try:
            self._end_task(exe_name, path)
            dialog.destroy()
            self._refresh_tick()
        except Exception as e:
            messagebox.showerror("End task failed", str(e), parent=dialog)


    def _end_task_then_go_to_path(self, dialog, exe_name, path):
        try:
            self._end_task(exe_name, path)
        except Exception as e:
            messagebox.showerror("End task failed", str(e), parent=dialog)
            return

        try:
            self._go_to_path(path)
            dialog.destroy()
            self._refresh_tick()
        except Exception as e:
            messagebox.showerror("Go to path failed", str(e), parent=dialog)

