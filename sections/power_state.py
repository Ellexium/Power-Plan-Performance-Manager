import os
import ctypes
import subprocess
import sys
import re
from tkinter import ttk, messagebox, filedialog
import tkinter as tk

class PowerStateMixin:

    def _is_task_created(self) -> bool:
        """Check if the scheduled task already exists."""
        try:
            cmd = ["schtasks", "/query", "/tn", self.TASK_NAME]
            # stderr=subprocess.DEVNULL hides the "ERROR: The system cannot find the file specified"
            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return res.returncode == 0
        except Exception:
            return False


        
    def _toggle_startup(self):
        """Create or remove the Windows startup task for the app.

        Supports both:
        - running as a normal Python script
        - running as a compiled EXE

        Also creates an optional developer-only batch task if keepbusy.bat
        exists beside the script/EXE. Failure to create the optional batch
        task will not prevent the main app task from being enabled.
        """
        if getattr(sys, "frozen", False):
            # Running as a compiled EXE
            app_exe = sys.executable
            task_command = f'"{app_exe}"'
            base_dir = os.path.dirname(app_exe)
        else:
            # Running as a script
            python_dir = os.path.dirname(sys.executable)
            pythonw_exe = os.path.join(python_dir, "pythonw.exe")
            python_exe = pythonw_exe if os.path.exists(pythonw_exe) else sys.executable

            script_path = os.path.abspath(sys.argv[0])
            task_command = f'"{python_exe}" "{script_path}"'
            base_dir = os.path.dirname(script_path)

        bat_path = os.path.join(base_dir, "keepbusy.bat")

        if self.startup_var.get():
            create_app_cmd = [
                "schtasks", "/create", "/f", "/tn", self.TASK_NAME,
                "/tr", task_command,
                "/sc", "onlogon", "/rl", "highest"
            ]

            try:
                subprocess.run(
                    create_app_cmd,
                    check=True,
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                self.log("Main startup task created successfully.")

                if os.path.exists(bat_path):
                    create_bat_cmd = [
                        "schtasks", "/create", "/f", "/tn", self.TASK_NAME_BAT,
                        "/tr", f'"{bat_path}"',
                        "/sc", "onlogon", "/rl", "highest"
                    ]

                    try:
                        subprocess.run(
                            create_bat_cmd,
                            check=True,
                            capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW
                        )
                        self.log("Optional keepbusy.bat startup task created.")
                    except subprocess.CalledProcessError as e:
                        err = (e.stderr or b"").decode(errors="replace").strip()
                        self.log(f"Optional keepbusy.bat task failed to create: {err}")
                else:
                    self.log("Optional keepbusy.bat not found. Skipping batch startup task.")

                messagebox.showinfo(
                    "Success",
                    "Power Plan Manager will now start automatically at login with the highest available privileges."
                )

            except subprocess.CalledProcessError as e:
                err = (e.stderr or b"").decode(errors="replace").strip()
                self.log(f"Failed to create main startup task: {err}")
                self.startup_var.set(False)
                messagebox.showerror(
                    "Error",
                    f"Failed to create startup task:\n{err}"
                )

        else:
            delete_targets = [self.TASK_NAME, self.TASK_NAME_BAT]
            delete_errors = []

            for task_name in delete_targets:
                try:
                    result = subprocess.run(
                        ["schtasks", "/delete", "/tn", task_name, "/f"],
                        capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        text=True
                    )

                    if result.returncode == 0:
                        self.log(f"Startup task removed: {task_name}")
                    else:
                        details = (result.stderr or result.stdout or "").strip()
                        if details and "cannot find the file specified" not in details.lower():
                            self.log(f"Startup task not removed ({task_name}): {details}")

                except Exception as e:
                    delete_errors.append(f"{task_name}: {e}")
                    self.log(f"Error deleting task {task_name}: {e}")

            if delete_errors:
                messagebox.showwarning(
                    "Warning",
                    "Startup was turned off, but one or more cleanup steps had issues.\n\n"
                    + "\n".join(delete_errors)
                )
            else:
                messagebox.showinfo("Success", "Startup tasks removed.")

        self._save_now()


    def _toast_plan(self, reason: str, guid: str):
        name = self.name_by_guid.get(guid, guid)
        title = "Power plan changed"
        msg = f"{reason}: {name}"
        key = f"{reason}|{guid}"

        # prevent spam if it picks the same target repeatedly
        if key == self._last_toast_key:
            return
        self._last_toast_key = key

        try:
            # threaded=True keeps GUI responsive
            self._toaster.show_toast(title, msg, duration=4, threaded=True)
        except Exception as e:
            self.log(f"TOAST FAILED: {e}")

    def _load_power_plans(self):
        self.power_schemes = self.get_power_schemes()
        self.name_by_guid = {s["guid"]: s["name"] for s in self.power_schemes}
        self.balanced_guid = self.find_balanced_guid(self.power_schemes)
        self.log(f"Balanced GUID: {self.balanced_guid}")

        # Populate dropdown
        self._refresh_plan_dropdown()

        # -------------------------
        # Resolve default low plan
        # -------------------------
        low_guid = ""

        if self.saved_default_low_guid and self.saved_default_low_guid in self.name_by_guid:
            low_guid = self.saved_default_low_guid
            self.log(f"Default low from settings: {low_guid} ({self.name_by_guid.get(low_guid)})")
        else:
            if self.balanced_guid:
                low_guid = self.balanced_guid
                self.log(f"Default low defaulted to Balanced: {low_guid}")
            elif self.power_schemes:
                low_guid = self.power_schemes[0]["guid"]
                self.log(f"Default low defaulted to first plan: {low_guid}")

        # -------------------------
        # Resolve default high plan
        # -------------------------
        high_guid = ""

        if self.saved_default_high_guid and self.saved_default_high_guid in self.name_by_guid:
            high_guid = self.saved_default_high_guid
            self.log(f"Default high from settings: {high_guid} ({self.name_by_guid.get(high_guid)})")
        else:
            for s in self.power_schemes:
                if s["name"].strip().lower() == "high performance":
                    high_guid = s["guid"]
                    self.log(f"Default high defaulted to High performance: {high_guid}")
                    break

            if not high_guid:
                for s in self.power_schemes:
                    if s["guid"] != low_guid:
                        high_guid = s["guid"]
                        self.log(f"Default high defaulted to first non-low plan: {high_guid}")
                        break

            if not high_guid and self.power_schemes:
                high_guid = self.power_schemes[0]["guid"]
                self.log(f"Default high defaulted to first plan: {high_guid}")

        self.default_low_guid.set(low_guid)
        self.default_high_guid.set(high_guid)

        # keep saved copies aligned once resolved
        self.saved_default_low_guid = low_guid
        self.saved_default_low_name = self.name_by_guid.get(low_guid, "")
        self.saved_default_high_guid = high_guid
        self.saved_default_high_name = self.name_by_guid.get(high_guid, "")

        # restore dropdown label based on saved / current manual plan
        self._refresh_plan_dropdown()


    def _refresh_plan_dropdown(self):
        if not hasattr(self, "plan_select_menu"):
            return

        labels = ["Auto"]
        self.plan_dropdown_guid_by_label = {"Auto": ""}

        for s in self.power_schemes:
            label = s["name"]
            if s["guid"] == self.balanced_guid:
                label += "  (Balanced)"
            labels.append(label)
            self.plan_dropdown_guid_by_label[label] = s["guid"]

        self.plan_select_menu.configure(values=labels)

        manual_guid = ""
        if hasattr(self, "manual_plan_guid"):
            manual_guid = self.manual_plan_guid.get().strip()

        if not manual_guid:
            self.manual_plan_label_var.set("Auto")
            return

        chosen_label = "Auto"
        for label, guid in self.plan_dropdown_guid_by_label.items():
            if guid == manual_guid:
                chosen_label = label
                break

        self.manual_plan_label_var.set(chosen_label)

    def _get_exe_rules_rows(self):
        rows = []

        for path in self.watch_paths:
            norm = os.path.normpath(path)
            rows.append({
                "status": "Watched",
                "mode": "watched",
                "exe": self.basename_exe(norm),
                "path": norm,
            })

        for path in self.blacklist_paths:
            norm = os.path.normpath(path)
            rows.append({
                "status": "Blacklisted",
                "mode": "blacklisted",
                "exe": self.basename_exe(norm),
                "path": norm,
            })

        rows.sort(key=lambda r: (r["exe"].lower(), r["path"].lower()))
        return rows

    def _render_exe_rules(self, selected_path=None):
        if not hasattr(self, "exe_rules_tree"):
            return

        tree = self.exe_rules_tree

        for iid in tree.get_children():
            tree.delete(iid)

        selected_iid = None

        for row in self._get_exe_rules_rows():
            mode = row["mode"]

            tags = ()
            if mode == "watched":
                tags = ("rule_watched",)
            elif mode == "blacklisted":
                tags = ("rule_blacklisted",)

            iid = tree.insert(
                "",
                "end",
                values=(row["status"], row["exe"], row["path"]),
                tags=tags,
            )

            if selected_path and row["path"].lower() == selected_path.lower():
                selected_iid = iid

        if selected_iid:
            tree.selection_set(selected_iid)
            tree.focus(selected_iid)
            tree.see(selected_iid)

    def _get_selected_exe_rule_path(self):
        if not hasattr(self, "exe_rules_tree"):
            return None

        sel = self.exe_rules_tree.selection()
        if not sel:
            return None

        values = self.exe_rules_tree.item(sel[0], "values")
        if not values or len(values) < 3:
            return None

        return str(values[2]).strip()

    def _add_exe_rule(self):
        path = filedialog.askopenfilename(
            title="Select EXE",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")]
        )
        if not path:
            return

        if not path.lower().endswith(".exe"):
            messagebox.showinfo("Not an EXE", "Please select a .exe file.")
            return

        norm = os.path.normpath(path)
        name = self.basename_exe(norm)

        if any(p.lower() == norm.lower() for p in self.watch_paths):
            messagebox.showinfo("Already added", f"{name} is already in the watched list.")
            return

        if any(p.lower() == norm.lower() for p in self.blacklist_paths):
            messagebox.showinfo("Already added", f"{name} is already in the blacklist.")
            return

        self.watch_paths.append(norm)
        self.watch_names.add(name)

        self.log(f"EXE RULE ADDED: {norm} -> watched")

        self._render_exe_rules(selected_path=norm)
        self._save_now()

    def _remove_selected_exe_rule(self):
        path = self._get_selected_exe_rule_path()
        if not path:
            return

        norm = os.path.normpath(path)
        name = self.basename_exe(norm)

        removed = False

        self.watch_paths = [p for p in self.watch_paths if p.lower() != norm.lower()]
        self.blacklist_paths = [p for p in self.blacklist_paths if p.lower() != norm.lower()]

        self.watch_names = {self.basename_exe(p) for p in self.watch_paths}
        self.blacklist_names = {self.basename_exe(p) for p in self.blacklist_paths}

        removed = True

        if removed:
            self.log(f"EXE RULE REMOVED: {norm}")
            self._render_exe_rules()
            self._save_now()

    def _set_selected_exe_rule_mode(self, mode):
        path = self._get_selected_exe_rule_path()
        if not path:
            return

        norm = os.path.normpath(path)
        name = self.basename_exe(norm)

        self.watch_paths = [p for p in self.watch_paths if p.lower() != norm.lower()]
        self.blacklist_paths = [p for p in self.blacklist_paths if p.lower() != norm.lower()]

        if mode == "watched":
            self.watch_paths.append(norm)
            self.log(f"EXE RULE SET: {norm} -> watched")
        elif mode == "blacklisted":
            self.blacklist_paths.append(norm)
            self.log(f"EXE RULE SET: {norm} -> blacklisted")
        else:
            return

        self.watch_names = {self.basename_exe(p) for p in self.watch_paths}
        self.blacklist_names = {self.basename_exe(p) for p in self.blacklist_paths}

        self._render_exe_rules(selected_path=norm)
        self._save_now()

    def _toggle_selected_exe_rule_mode(self):
        path = self._get_selected_exe_rule_path()
        if not path:
            return

        norm = os.path.normpath(path)

        in_watch = any(p.lower() == norm.lower() for p in self.watch_paths)
        in_blacklist = any(p.lower() == norm.lower() for p in self.blacklist_paths)

        if in_watch:
            self._set_selected_exe_rule_mode("blacklisted")
        elif in_blacklist:
            self._set_selected_exe_rule_mode("watched")

    def _on_exe_rules_double_click(self, _evt=None):
        self._toggle_selected_exe_rule_mode()



    def _on_plan_dropdown_changed(self, selected_label):
        selected_label = str(selected_label or "").strip()

        if selected_label == "Auto":
            self.manual_plan_guid.set("")
            self.log("PLAN DROPDOWN: Auto selected")
            self._set_status("Plan selection: Auto")
            self._save_now()
            return

        guid = self.plan_dropdown_guid_by_label.get(selected_label, "")
        if not guid:
            self.manual_plan_guid.set("")
            self.manual_plan_label_var.set("Auto")
            self._save_now()
            return

        self.manual_plan_guid.set(guid)
        self.log(f"PLAN DROPDOWN: Manual selected -> {guid} ({self.name_by_guid.get(guid, guid)})")

        try:
            self.set_active_scheme(guid)
            self._toast_plan("Manual selection", guid)
            self._load_power_plans()
            self._set_status(f"Manual plan: {self.name_by_guid.get(guid, guid)}")
        except Exception as e:
            self.log(f"MANUAL PLAN DROPDOWN FAILED: {e}")
            messagebox.showerror("Error", f"Failed to apply plan.\n\n{e}")
            self.manual_plan_guid.set("")
            self.manual_plan_label_var.set("Auto")

        self._save_now()




    def _select_guid_in_listbox(self, lb: tk.Listbox, guid: str):
        for idx, s in enumerate(self.power_schemes):
            if s["guid"] == guid:
                lb.selection_clear(0, tk.END)
                lb.selection_set(idx)
                lb.see(idx)
                return

    def _guid_from_listbox_selection(self, lb: tk.Listbox):
        sel = lb.curselection()
        if not sel:
            return None
        idx = sel[0]
        if idx < 0 or idx >= len(self.power_schemes):
            return None
        return self.power_schemes[idx]["guid"]

    # -------------------------
    # UI handlers
    # -------------------------


    def _on_override_selected(self, _evt=None):
        guid = self._guid_from_listbox_selection(self.override_list)
        if not guid:
            return
        self.log(f"MANUAL OVERRIDE CLICK: {guid} ({self.name_by_guid.get(guid)})")
        try:
            self._set_status("Applying manual override plan...")
            self.set_active_scheme(guid)
            self.log("MANUAL OVERRIDE APPLIED OK")
            self._toast_plan("Manual override", guid)
            self._load_power_plans()
            self._set_status(f"Manual override: {self.name_by_guid.get(guid, guid)}")
        except Exception as e:
            self.log(f"MANUAL OVERRIDE FAILED: {e}")
            messagebox.showerror("Error", f"Failed to apply plan.\n\n{e}")
            self._set_status("Error applying manual override.")

    def _on_auto_toggle(self):
        self.log(f"AUTO MODE TOGGLED -> {self.auto_mode.get()}")

        if self.auto_mode.get():
            self._set_status("Auto mode enabled.")
        else:
            self._set_status("Auto mode disabled. Manual override only.")
        self._save_now()

    def _load_watchlist_from_saved(self):
        for p in self.saved_exes:
            if p and p.lower().endswith(".exe"):
                norm = os.path.normpath(p)
                name = self.basename_exe(norm)
                if name not in self.watch_names:
                    self.watch_paths.append(norm)
                    self.watch_names.add(name)
        self.log(f"Watchlist loaded: {len(self.watch_paths)} exe(s)")




    def _add_watch_exe(self):
        path = filedialog.askopenfilename(
            title="Select EXE",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")]
        )
        if not path:
            return
        if not path.lower().endswith(".exe"):
            messagebox.showinfo("Not an EXE", "Please select a .exe file.")
            return
        norm = os.path.normpath(path)
        name = self.basename_exe(norm)
        if name in self.watch_names:
            messagebox.showinfo("Already added", f"{name} is already in the watch list.")
            return
        self.watch_paths.append(norm)
        self.watch_names.add(name)
        self.log(f"EXE ADDED: {norm} (match name: {name})")
        self._render_watchlist()
        self._save_now()

    def _add_watch_exe_from_path(self, path):
        path = (path or "").strip()
        if not path:
            raise RuntimeError("This item does not have a file path.")

        if not path.lower().endswith(".exe"):
            raise RuntimeError("Selected item is not an EXE path.")

        norm = os.path.normpath(path)
        name = self.basename_exe(norm)

        if any(p.lower() == norm.lower() for p in self.watch_paths):
            raise RuntimeError(f"Already watching:\n{norm}")

        self.watch_paths.append(norm)
        self.watch_names.add(name)
        self.log(f"EXE ADDED FROM PROCESS WINDOW: {norm} (match name: {name})")
        self._render_watchlist()
        self._save_now()


    def _add_blacklist_exe_from_path(self, path):
        path = (path or "").strip()
        if not path:
            raise RuntimeError("This item does not have a file path.")

        if not path.lower().endswith(".exe"):
            raise RuntimeError("Selected item is not an EXE path.")

        norm = os.path.normpath(path)
        name = self.basename_exe(norm)

        if any(p.lower() == norm.lower() for p in self.blacklist_paths):
            raise RuntimeError(f"Already blacklisted:\n{norm}")

        self.blacklist_paths.append(norm)
        self.blacklist_names.add(name)
        self.log(f"BLACKLIST EXE ADDED FROM PROCESS WINDOW: {norm} (match name: {name})")
        self._render_blacklist()
        self._save_now()

        
    def _remove_selected_watch_exe(self):
        sel = self.watch_list.curselection()
        if not sel:
            return
        idx = sel[0]
        path = self.watch_list.get(idx)
        name = self.basename_exe(path)

        self.log(f"EXE REMOVED: {path} (match name: {name})")

        self.watch_list.delete(idx)
        try:
            self.watch_paths.remove(path)
        except ValueError:
            pass
        self.watch_names.discard(name)
        self._save_now()


    def _clear_watch_exes(self):
        self.log("EXE LIST CLEARED")
        self.watch_paths.clear()
        self.watch_names.clear()
        self._render_watchlist()
        self._save_now()

    def _load_blacklist_from_saved(self):
        for p in self.saved_blacklist_exes:
            if p and p.lower().endswith(".exe"):
                norm = os.path.normpath(p)
                name = self.basename_exe(norm)
                if norm not in self.blacklist_paths:
                    self.blacklist_paths.append(norm)
                self.blacklist_names.add(name)

        self.log(f"Blacklist loaded: {len(self.blacklist_paths)} exe(s)")
        self._render_exe_rules()


    def _remove_selected_blacklist_exe(self):
        sel = self.blacklist_list.curselection()
        if not sel:
            return

        idx = sel[0]
        path = self.blacklist_list.get(idx)
        name = self.basename_exe(path)

        self.log(f"BLACKLIST EXE REMOVED: {path} (match name: {name})")

        self.blacklist_list.delete(idx)
        try:
            self.blacklist_paths.remove(path)
        except ValueError:
            pass

        # rebuild names from remaining paths so duplicates by basename stay correct
        self.blacklist_names = {self.basename_exe(p) for p in self.blacklist_paths}
        self._save_now()

    def _clear_blacklist_exes(self):
        self.log("BLACKLIST EXE LIST CLEARED")
        self.blacklist_paths.clear()
        self.blacklist_names.clear()
        self._render_blacklist()
        self._save_now()

    def _add_blacklist_exe(self):
        path = filedialog.askopenfilename(
            title="Select EXE to blacklist from dynamic detection",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")]
        )
        if not path:
            return
        if not path.lower().endswith(".exe"):
            messagebox.showinfo("Not an EXE", "Please select a .exe file.")
            return

        norm = os.path.normpath(path)
        name = self.basename_exe(norm)

        if any(p.lower() == norm.lower() for p in self.blacklist_paths):
            messagebox.showinfo("Already added", f"This EXE is already blacklisted:\n{norm}")
            return

        self.blacklist_paths.append(norm)
        self.blacklist_names.add(name)
        self.log(f"BLACKLIST EXE ADDED: {norm} (match name: {name})")
        self._render_blacklist()
        self._save_now()


    def _save_now(self):
        try:
            graph_seconds = "60"
            if hasattr(self, "graph_seconds_var"):
                graph_seconds = str(self.graph_seconds_var.get()).strip() or "60"

            graph_sources = []
            if hasattr(self, "graph_option_vars"):
                for var in self.graph_option_vars[:6]:
                    graph_sources.append(str(var.get()).strip() or "CPU")

            while len(graph_sources) < 6:
                graph_sources.append("CPU")

            low_guid = ""
            high_guid = ""
            low_name = ""
            high_name = ""

            manual_plan_guid = ""
            if hasattr(self, "manual_plan_guid"):
                manual_plan_guid = str(self.manual_plan_guid.get()).strip()
            if hasattr(self, "default_low_guid"):
                low_guid = str(self.default_low_guid.get()).strip()
            if hasattr(self, "default_high_guid"):
                high_guid = str(self.default_high_guid.get()).strip()

            low_name = self.name_by_guid.get(low_guid, "") if low_guid else ""
            high_name = self.name_by_guid.get(high_guid, "") if high_guid else ""

            self.save_settings(
                self.auto_mode.get(),
                self.startup_var.get(),
                self.watch_paths[:],
                self.blacklist_paths[:],
                graph_seconds,
                graph_sources,
                low_guid,
                low_name,
                high_guid,
                high_name,
                manual_plan_guid,
            )

        except Exception as e:
            self.log(f"SAVE FAILED: {e}")
            messagebox.showerror("Error", f"Failed to save settings.\n\n{e}")


    def _save_configured_plans(self, low_guid, high_guid):
        if not low_guid or not high_guid:
            raise RuntimeError("Choose both plans.")

        low_name = self.name_by_guid.get(low_guid, "")
        high_name = self.name_by_guid.get(high_guid, "")

        self.default_low_guid.set(low_guid)
        self.default_high_guid.set(high_guid)

        self.saved_default_low_guid = low_guid
        self.saved_default_low_name = low_name
        self.saved_default_high_guid = high_guid
        self.saved_default_high_name = high_name

        self.log(f"DEFAULT LOW PLAN SET: {low_guid} ({low_name})")
        self.log(f"DEFAULT HIGH PLAN SET: {high_guid} ({high_name})")

        self._save_now()
            