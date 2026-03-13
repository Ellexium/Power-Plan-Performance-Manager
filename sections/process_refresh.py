from datetime import datetime
import threading
import time
try:
    import psutil  # type: ignore
except Exception:
    psutil = None


class ProcessRefreshMixin:

    def _refresh_now(self):
        self.log("Manual refresh requested.")
        self._schedule_refresh(0)

    def _get_filtered_process_rows(self):
        q = self.search_var.get().strip().lower()

        filtered = []
        for r in self.all_proc_rows:
            if not q or (q in r["exe"].lower() or q in r["path"].lower()):
                filtered.append(r)

        return filtered
    


    def _sort_process_rows(self, rows):
        def sort_value(r):
            exe_name = r.get("exe", "")
            cpu_val = float(r.get("cpu", 0) or 0.0)
            threads = int(r.get("threads", 0) or 0)
            mem_bytes = int(r.get("memory", 0) or 0)
            path = r.get("path", "")

            cores_used = cpu_val / 100.0
            cpu_total_pct = cpu_val / float(self.logical_cpu_count)

            if self.sort_col == "exe":
                return exe_name.lower()
            elif self.sort_col == "cores":
                return cores_used
            elif self.sort_col == "cpu_total":
                return cpu_total_pct
            elif self.sort_col == "threads":
                return threads
            elif self.sort_col == "memory":
                return mem_bytes
            elif self.sort_col == "threading":
                return 0 if threads == 1 else 1
            elif self.sort_col == "path":
                return path.lower()
            else:
                return cpu_total_pct

        return sorted(rows, key=sort_value, reverse=self.sort_reverse)





    def _watched_running(self) -> bool:
        if not self.watch_names:
            return False
        # running = set(self.all_proc_names)
        running_names = set(r["exe"].lower() for r in self.all_proc_rows)
        for exe in self.watch_names:
            if exe in running_names:
                return True
        return False


    def _start_process_worker(self):
        if self._process_worker_running:
            return

        self._process_worker_running = True

        def worker():
            while self._process_worker_running:
                try:
                    self.thread_refresh_counter += 1
                    refresh_threads_now = (self.thread_refresh_counter % 64 == 0)

                    new_rows, disk_rows, any_heavy_hitter_now = self._scan_process_rows(refresh_threads_now)

                    with self._state_lock:
                        self._proc_snapshot = {
                            "rows": new_rows,
                            "disk_rows": disk_rows,
                            "any_heavy": any_heavy_hitter_now,
                            "ready": True,
                        }

                except Exception as e:
                    self.log(f"PROCESS WORKER ERROR: {e}")

                time.sleep(max(self.POLL_MS / 1000.0, 0.25))

        self._process_worker_thread = threading.Thread(target=worker, daemon=True)
        self._process_worker_thread.start()
        



    def _refresh_tick(self, initial=False):
        try:
            if getattr(self, "_ui_interacting", False):
                return

            with self._state_lock:
                snap = dict(self._proc_snapshot)

            if snap.get("ready"):
                new_rows = list(snap.get("rows", []))
                disk_rows = list(snap.get("disk_rows", []))
                any_heavy_hitter_now = bool(snap.get("any_heavy", False))

                self.all_proc_rows = new_rows
                self.disk_rows = disk_rows

                self._apply_process_filter()
                self._apply_disk_filter()

                self._update_auto_power_logic(any_heavy_hitter_now)

                live_pids = {r["pid"] for r in new_rows if "pid" in r}
                self._cleanup_dead_pid_caches(live_pids)

        except Exception as e:
            self.log(f"REFRESH ERROR: {e}")

        finally:
            self._schedule_refresh(self.POLL_MS)

                

    def _scan_process_rows(self, refresh_threads_now):
        new_rows = []
        disk_rows = []
        any_heavy_hitter_now = False

        if psutil is None:
            return new_rows, disk_rows, any_heavy_hitter_now

        poll_seconds = max(self.POLL_MS / 1000.0, 0.001)

        for p in psutil.process_iter(attrs=["pid", "name", "cpu_percent"]):
            try:
                pid = p.pid
                name = (p.info.get("name") or "").strip()
                path = p.exe()
                cpu = p.info.get("cpu_percent", 0.0)

                # Thread caching logic
                if (pid not in self.thread_count_cache) or refresh_threads_now:
                    try:
                        self.thread_count_cache[pid] = p.num_threads()
                    except Exception:
                        self.thread_count_cache[pid] = 0

                threads = self.thread_count_cache.get(pid, 0)

                # Memory usage
                try:
                    mem_bytes = p.memory_info().rss
                except Exception:
                    mem_bytes = 0

                new_rows.append({
                    "pid": pid,
                    "exe": name,
                    "path": path or "",
                    "cpu": cpu,
                    "threads": threads,
                    "memory": mem_bytes,
                })

                if (
                    name.lower() not in self.exclude_list
                    and not self._is_dynamic_blacklisted(name, path or "")
                    and cpu > self.AUTO_DETECT_THRESHOLD
                ):
                    any_heavy_hitter_now = True

                # Disk I/O
                read_speed, write_speed, accum_read, accum_write = self._get_process_disk_io(pid, p, poll_seconds)

                disk_rows.append({
                    "pid": pid,
                    "exe": name,
                    "path": path or "",
                    "read_speed": read_speed,
                    "write_speed": write_speed,
                    "accum_read": accum_read,
                    "accum_write": accum_write,
                    "file_path": "N/A",
                })

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            except Exception:
                continue

        return new_rows, disk_rows, any_heavy_hitter_now

    def _is_dynamic_blacklisted(self, exe_name: str, path: str) -> bool:
        exe_lower = (exe_name or "").strip().lower()
        path_lower = (path or "").strip().lower()

        if exe_lower in self.blacklist_names:
            return True

        for p in self.blacklist_paths:
            if path_lower == p.strip().lower():
                return True

        return False
    

    def _get_process_disk_io(self, pid, proc, poll_seconds):
        try:
            io = proc.io_counters()
            read_now = int(io.read_bytes)
            write_now = int(io.write_bytes)
        except Exception:
            read_now = 0
            write_now = 0

        prev = self.proc_io_prev.get(pid, {"read": read_now, "write": write_now})

        read_delta = max(0, read_now - prev["read"])
        write_delta = max(0, write_now - prev["write"])

        self.proc_io_prev[pid] = {
            "read": read_now,
            "write": write_now,
        }

        accum = self.proc_io_accum.get(pid, {"read": 0, "write": 0})
        accum["read"] += read_delta
        accum["write"] += write_delta
        self.proc_io_accum[pid] = accum

        read_speed = read_delta / poll_seconds
        write_speed = write_delta / poll_seconds
        return read_speed, write_speed, accum["read"], accum["write"]


    def _update_auto_power_logic(self, any_heavy_hitter_now):
        # Manual plan lock from top dropdown
        manual_selected_guid = self.manual_plan_guid.get().strip()
        if manual_selected_guid:
            if manual_selected_guid != self.last_auto_target:
                try:
                    self.log(f"MANUAL PLAN LOCK ACTIVE: {manual_selected_guid}")
                    self.set_active_scheme(manual_selected_guid)

                    if manual_selected_guid == self.default_low_guid.get().strip():
                        # self._set_status_color(self._get_default_status_color())
                        self._update_bottom_bar_border(False)
                    else:
                        # self._set_status_color("red")
                        self._update_bottom_bar_border(True)


                    self.last_auto_target = manual_selected_guid
                    self._load_power_plans()
                except Exception as e:
                    self.log(f"MANUAL PLAN LOCK ERROR: {e}")

            self._set_status(
                f"Manual plan locked: {self.name_by_guid.get(manual_selected_guid, manual_selected_guid)}"
            )
            return

        # 1. Dynamic Load Logic
        dynamic_triggered = False

        if any_heavy_hitter_now:
            self.high_load_consecutive_polls += 1
            if self.high_load_consecutive_polls >= self.AUTO_DETECT_CONFIRM_WAIT:
                dynamic_triggered = True
                self.temp_cooldown_counter = self.AUTO_DETECT_COOLDOWN
        else:
            self.high_load_consecutive_polls = 0

        if not dynamic_triggered and self.temp_cooldown_counter > 0:
            self.temp_cooldown_counter -= 1
            if self.temp_cooldown_counter > 0:
                dynamic_triggered = True

        # 2. Final Decision Logic
        manual_watched_running = self._watched_running()
        dynamic_is_allowed = self.auto_mode.get()

        should_be_high_perf = manual_watched_running or (dynamic_is_allowed and dynamic_triggered)

        high_guid = self.default_high_guid.get().strip()
        low_guid = self.default_low_guid.get().strip()

        if not low_guid:
            low_guid = self.balanced_guid or ""
        if not high_guid:
            high_guid = low_guid

        target = high_guid if should_be_high_perf else low_guid

        # 3. Apply Plan Switch
        if target and target != self.last_auto_target:
            try:
                self.log(f"SWITCHING PLAN: {target}")
                self.set_active_scheme(target)

                if target == low_guid:
                    # self._set_status_color(self._get_default_status_color())
                    self._update_bottom_bar_border(False)
                else:
                    # self._set_status_color("red")
                    self._update_bottom_bar_border(True)


                if manual_watched_running:
                    self._toast_plan("Watched EXE detected", target)

                self.last_auto_target = target
                self._load_power_plans()

            except Exception as e:
                self.log(f"AUTO SWITCH ERROR: {e}")

        # 4. Update Status Text
        if manual_watched_running:
            self._set_status("Status: High Perf (Watched EXE)")
        elif dynamic_triggered:
            if dynamic_is_allowed:
                self._set_status("Status: High Perf (Dynamic)")
            else:
                self._set_status("Status: Low Perf (Ignoring Dynamic Load)")
        elif any_heavy_hitter_now and dynamic_is_allowed:
            self._set_status(
                f"Monitoring Load: {self.high_load_consecutive_polls}/{self.AUTO_DETECT_CONFIRM_WAIT}..."
            )
        else:
            self._set_status("Status: Low Perf")



    def _cleanup_dead_pid_caches(self, live_pids):
        self.thread_count_cache = {
            pid: count for pid, count in self.thread_count_cache.items()
            if pid in live_pids
        }

        self.proc_io_prev = {
            pid: counters for pid, counters in self.proc_io_prev.items()
            if pid in live_pids
        }

        self.proc_io_accum = {
            pid: counters for pid, counters in self.proc_io_accum.items()
            if pid in live_pids
        }


    def _update_usage_histories(self):
        try:
            cpu = psutil.cpu_percent(interval=None) if psutil is not None else 0.0
        except Exception:
            cpu = 0.0

        try:
            ram = psutil.virtual_memory().percent if psutil is not None else 0.0
        except Exception:
            ram = 0.0

        self.cpu_history.append(cpu)
        self.cpu_history.pop(0)

        self.ram_history.append(ram)
        self.ram_history.pop(0)





    def _apply_disk_filter(self):
        rows = list(self.disk_rows)

        def sort_value(r):
            if self.disk_sort_col == "exe":
                return r.get("exe", "").lower()
            elif self.disk_sort_col == "path":
                return r.get("path", "").lower()
            elif self.disk_sort_col == "read_speed":
                return float(r.get("read_speed", 0.0) or 0.0)
            elif self.disk_sort_col == "write_speed":
                return float(r.get("write_speed", 0.0) or 0.0)
            elif self.disk_sort_col == "accum_read":
                return float(r.get("accum_read", 0.0) or 0.0)

            elif self.disk_sort_col == "accum_write":
                return float(r.get("accum_write", 0.0) or 0.0)
            else:
                return float(r.get("write_speed", 0.0) or 0.0)

        rows.sort(key=sort_value, reverse=self.disk_sort_reverse)

        for iid in self.disk_tree.get_children():
            self.disk_tree.delete(iid)

        for r in rows:
            self.disk_tree.insert(
                "",
                "end",
                values=(
                    r.get("exe", ""),
                    r.get("path", ""),
                    self._format_bytes_per_sec(r.get("read_speed", 0.0)),
                    self._format_bytes_per_sec(r.get("write_speed", 0.0)),
                    self._format_bytes_total(r.get("accum_read", 0.0)),
                    self._format_bytes_total(r.get("accum_write", 0.0)),
                    r.get("file_path", "N/A"),
                )
            )


    def _format_bytes_per_sec(self, value):
        value = float(value or 0.0)

        if value >= 1024 ** 3:
            return f"{value / (1024 ** 3):.2f} GB/s"
        elif value >= 1024 ** 2:
            return f"{value / (1024 ** 2):.1f} MB/s"
        elif value >= 1024:
            return f"{value / 1024:.0f} KB/s"
        else:
            return f"{value:.0f} B/s"


    def _format_bytes_total(self, value):
        value = float(value or 0.0)

        if value >= 1024 ** 3:
            return f"{value / (1024 ** 3):.2f} GB"
        elif value >= 1024 ** 2:
            return f"{value / (1024 ** 2):.1f} MB"
        elif value >= 1024:
            return f"{value / 1024:.0f} KB"
        else:
            return f"{value:.0f} B"


    def _reset_disk_accum_timestamp(self):
        self.disk_reset_timestamp = datetime.now()
        self.disk_reset_var.set(
            f"Since: {self.disk_reset_timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        self.proc_io_accum.clear()

        # Re-baseline to current counters so accumulation starts from "now"
        fresh_prev = {}

        if psutil is not None:
            for p in psutil.process_iter(attrs=["pid"]):
                try:
                    io = p.io_counters()
                    fresh_prev[p.pid] = {
                        "read": int(io.read_bytes),
                        "write": int(io.write_bytes),
                    }
                except Exception:
                    continue

        self.proc_io_prev = fresh_prev
        self.disk_rows = []
        self._apply_disk_filter()
        
    def _schedule_refresh(self, delay_ms=None):
        if delay_ms is None:
            delay_ms = self.POLL_MS

        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None

        self._refresh_job = self.after(delay_ms, self._refresh_tick)
        