import subprocess
try:
    import psutil  # type: ignore
except Exception:
    psutil = None
import time
import csv
import io
import re
import threading


class TelemetryMixin:

    def _get_windows_temp(self):
        """Queries Open Hardware Monitor for the real CPU temperature."""
        try:
            # This PowerShell command looks into the OpenHardwareMonitor 'folder' in WMI.
            # We look for a Sensor where the Type is 'Temperature' and Name contains 'CPU Package'.
            # 'CPU Package' is usually the most accurate single number for the whole chip.
            ps_cmd = (
                "Get-WmiObject -Namespace 'root\\OpenHardwareMonitor' "
                "-Query \"SELECT * FROM Sensor WHERE SensorType='Temperature' AND Name LIKE '%CPU Package%'\" "
                "| Select-Object -ExpandProperty Value"
            )
            
            cmd = ["powershell", "-NoProfile", "-Command", ps_cmd]
            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if res.returncode == 0 and res.stdout.strip():
                temp_val = float(res.stdout.strip().splitlines()[0])
                return f"{temp_val:.0f}°C"
                
            # Fallback: If 'CPU Package' isn't found, try 'CPU Core #1'
            ps_cmd_fallback = (
                "Get-WmiObject -Namespace 'root\\OpenHardwareMonitor' "
                "-Query \"SELECT * FROM Sensor WHERE SensorType='Temperature' AND Name LIKE '%CPU Core #1%'\" "
                "| Select-Object -ExpandProperty Value"
            )
            cmd = ["powershell", "-NoProfile", "-Command", ps_cmd_fallback]
            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            if res.returncode == 0 and res.stdout.strip():
                temp_val = float(res.stdout.strip().splitlines()[0])
                return f"{temp_val:.0f}°C"

        except Exception as e:
            self.log(f"TEMP QUERY ERROR: {e}")
            
        return "N/A"



    def _update_freq_tick(self):
        try:
            if not getattr(self, "_ui_interacting", False):
                snap = None
                with self._state_lock:
                    snap = dict(self._telemetry_snapshot)

                if snap.get("ready"):
                    freq_ghz = snap.get("freq_ghz")
                    temp_text = snap.get("temp_text", "N/A")
                    cpu = float(snap.get("cpu", 0.0) or 0.0)
                    ram_percent = float(snap.get("ram_percent", 0.0) or 0.0)
                    ram_used_gb = float(snap.get("ram_used_gb", 0.0) or 0.0)
                    ram_total_gb = float(snap.get("ram_total_gb", 0.0) or 0.0)

                    if freq_ghz is None:
                        self.freq_var.set("CPU: N/A")
                    else:
                        self.freq_var.set(f"CPU: {freq_ghz:.2f} GHz")

                    self.temp_var.set(f"Temp: {temp_text}")

                    self.current_cpu_util = cpu
                    cores_used = (cpu / 100.0) * self.logical_cpu_count
                    self.cpu_usage_var.set(
                        f"Core Usage: {cores_used:.1f}/{self.logical_cpu_count}   Utilization: {cpu:.1f}%"
                    )

                    self.current_ram_util = ram_percent
                    self.mem_var.set(f"RAM: {ram_used_gb:.1f}/{ram_total_gb:.1f} GB")

                    self._update_graphs()

        except Exception as e:
            self.log(f"FREQ UI ERROR: {e}")

        finally:
            self.after(self.FREQ_POLL_MS, self._update_freq_tick)

    def _sample_all_graph_histories(self, target_len, cpu, ram_percent):
        self.cpu_history = self._resize_history(self.cpu_history, target_len)
        self.ram_history = self._resize_history(self.ram_history, target_len)

        self.cpu_history.append(float(cpu or 0.0))
        self.cpu_history = self.cpu_history[-target_len:]

        self.ram_history.append(float(ram_percent or 0.0))
        self.ram_history = self.ram_history[-target_len:]

        self._sample_disk_histories(target_len)
        self._sample_network_histories(target_len)
        self._sample_gpu_histories(target_len)


    def _draw_graph(self, canvas, data, color, label_text=""):
        w = canvas.winfo_width()
        h = canvas.winfo_height()

        if w < 20 or h < 20 or len(data) < 2:
            return

        canvas.delete("all")

        # Optional border so you can see the canvas is alive
        canvas.create_rectangle(0, 0, w - 1, h - 1, outline="#404040")

        # Optional label
        if label_text:
            canvas.create_text(6, 6, anchor="nw", text=label_text, fill="white", font=("Segoe UI", 9, "bold"))

        # Leave a little padding so the line is never drawn exactly on the edge
        top_pad = 14
        bottom_pad = 4
        usable_h = max(1, h - top_pad - bottom_pad)

        step = (w - 1) / max(1, len(data) - 1)

        points = []
        for i, val in enumerate(data):
            v = max(0.0, min(100.0, float(val)))
            x = i * step
            y = top_pad + (1.0 - (v / 100.0)) * usable_h

            # Clamp to visible area
            if y < top_pad:
                y = top_pad
            if y > h - bottom_pad - 1:
                y = h - bottom_pad - 1

            points.extend([x, y])

        # Draw a faint baseline
        baseline_y = h - bottom_pad - 1
        canvas.create_line(0, baseline_y, w, baseline_y, fill="#303030")

        # Draw the graph line
        canvas.create_line(*points, fill=color, width=2, smooth=False)
            

    def _get_windows_disk_sources(self):
        sources = []
        seen = set()

        if psutil is None:
            return sources

        try:
            parts = psutil.disk_partitions(all=False)
        except Exception:
            return sources

        for part in parts:
            try:
                mount = (part.mountpoint or "").strip()
                if not mount:
                    continue

                # Windows style label, e.g. C:
                label = mount.rstrip("\\/")
                if not label:
                    continue

                label_upper = label.upper()

                # Skip duplicates / strange mounts
                if label_upper in seen:
                    continue
                seen.add(label_upper)

                # Make sure usage can actually be queried
                psutil.disk_usage(mount)

                sources.append((mount, label_upper))
            except Exception:
                continue

        sources.sort(key=lambda x: x[1])
        return sources



    def _ensure_disk_histories(self, target_len):
        for option_label in self.disk_mount_map.keys():
            existing = self.disk_history_by_label.get(option_label, [])
            self.disk_history_by_label[option_label] = self._resize_history(existing, target_len)

        # remove stale histories if disks disappeared
        stale = [k for k in self.disk_history_by_label.keys() if k not in self.disk_mount_map]
        for k in stale:
            del self.disk_history_by_label[k]


    def _sample_disk_histories(self, target_len):
        self._ensure_disk_histories(target_len)

        active_map = dict(getattr(self, "_disk_active_map", {}) or {})

        for option_label, mount in self.disk_mount_map.items():
            label = (mount or "").rstrip("\\/").upper()
            active_percent = float(active_map.get(label, 0.0))

            hist = self.disk_history_by_label.get(option_label, [])
            hist = self._resize_history(hist, target_len)
            hist.append(active_percent)
            hist = hist[-target_len:]
            self.disk_history_by_label[option_label] = hist


    def _get_logical_disk_active_time_map(self):
        result = {}

        mounts = []
        for mount in getattr(self, "disk_mount_map", {}).values():
            label = (mount or "").rstrip("\\/").upper()
            if label and label not in mounts:
                mounts.append(label)

        if not mounts:
            return result

        counters = [f"\\LogicalDisk({label})\\% Idle Time" for label in mounts if label != "G:"]
        if not counters:
            return result

        cmd = ["typeperf", *counters, "-sc", "1"]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception as e:
            self.log(f"TYPEPERF ERROR: {e}")
            return result

        stdout_text = (proc.stdout or "").strip()
        if not stdout_text:
            return result

        raw_lines = stdout_text.splitlines()
        csv_lines = []

        for line in raw_lines:
            s = line.strip()
            if s.startswith('"'):
                csv_lines.append(s)

        if len(csv_lines) < 2:
            return result

        clean_csv_text = "\n".join(csv_lines)

        try:
            rows = list(csv.reader(io.StringIO(clean_csv_text)))
        except Exception as e:
            self.log(f"TYPEPERF CSV PARSE ERROR: {e}")
            return result

        if len(rows) < 2:
            return result

        header = rows[0]

        data_row = None
        for row in reversed(rows[1:]):
            if len(row) >= 2:
                first_col = str(row[0]).strip()
                if "/" in first_col or "-" in first_col or ":" in first_col:
                    data_row = row
                    break

        if data_row is None:
            return result

        usable_count = min(len(header), len(data_row))

        for i in range(1, usable_count):
            counter_name = str(header[i]).strip()
            raw_val = str(data_row[i]).strip()

            m = re.search(r"LogicalDisk\(([^)]+)\)", counter_name, re.IGNORECASE)
            if not m:
                continue

            label = m.group(1).upper()

            try:
                idle = float(raw_val)
            except Exception:
                continue

            idle = max(0.0, min(100.0, idle))
            active = max(0.0, min(100.0, 100.0 - idle))
            result[label] = active

        return result

    def _start_disk_sampler(self):
        if self._disk_sampler_running:
            return

        self._disk_sampler_running = True

        def worker():
            while self._disk_sampler_running:
                try:
                    active_map = self._get_logical_disk_active_time_map()
                    self._disk_active_map = active_map
                except Exception as e:
                    self.log(f"DISK SAMPLER ERROR: {e}")

                time.sleep(self._disk_sampler_interval_sec)

        self._disk_sampler_thread = threading.Thread(target=worker, daemon=True)
        self._disk_sampler_thread.start()


    


    def _resize_history(self, history, target_len):
        history = list(history or [])
        if len(history) > target_len:
            return history[-target_len:]
        if len(history) < target_len:
            return ([0.0] * (target_len - len(history))) + history
        return history

    def _graph_x_ticks_for_window(self, seconds):
        if seconds <= 30:
            divisions = 6
        elif seconds <= 60:
            divisions = 6
        else:
            divisions = 8

        if seconds <= 1:
            return [0]

        step = (seconds - 1) / divisions
        return [round(i * step) for i in range(divisions + 1)]
    

    def _get_network_sources(self):
        sources = []

        if psutil is None:
            return sources

        try:
            counters = psutil.net_io_counters(pernic=True)
        except Exception:
            return sources

        try:
            stats = psutil.net_if_stats()
        except Exception:
            stats = {}

        skip_names = {
            "loopback pseudo-interface 1",
            "loopback",
            "isatap",
            "teredo",
        }

        for nic_name in counters.keys():
            nic_lower = nic_name.strip().lower()

            if not nic_lower:
                continue

            if any(skip in nic_lower for skip in skip_names):
                continue

            st = stats.get(nic_name)
            if st is not None and not st.isup:
                continue

            sources.append(nic_name)

        sources.sort(key=lambda x: x.lower())
        return sources
    
    def _ensure_network_histories(self, target_len):
        for option_label in self.network_nic_map.keys():
            existing = self.network_history_by_label.get(option_label, [])
            self.network_history_by_label[option_label] = self._resize_history(existing, target_len)

        stale = [k for k in self.network_history_by_label.keys() if k not in self.network_nic_map]
        for k in stale:
            del self.network_history_by_label[k]

    def _sample_network_histories(self, target_len):
        self._ensure_network_histories(target_len)

        if psutil is None:
            return

        try:
            counters = psutil.net_io_counters(pernic=True)
        except Exception as e:
            self.log(f"NETWORK ERROR: {e}")
            return

        now = time.time()

        for option_label, nic_name in self.network_nic_map.items():
            c = counters.get(nic_name)

            send_mbps = 0.0
            recv_mbps = 0.0
            total_mbps = 0.0

            if c is not None:
                sent_now = float(c.bytes_sent or 0)
                recv_now = float(c.bytes_recv or 0)

                prev = self._net_prev_split.get(nic_name)
                if prev:
                    prev_sent, prev_recv, prev_time = prev
                    delta_sec = max(0.001, now - prev_time)

                    send_bps = max(0.0, sent_now - prev_sent) / delta_sec
                    recv_bps = max(0.0, recv_now - prev_recv) / delta_sec

                    send_mbps = (send_bps * 8.0) / (1024.0 * 1024.0)
                    recv_mbps = (recv_bps * 8.0) / (1024.0 * 1024.0)
                    total_mbps = send_mbps + recv_mbps

                self._net_prev_split[nic_name] = (sent_now, recv_now, now)

            hist = self.network_history_by_label.get(option_label, [])
            hist = self._resize_history(hist, target_len)
            hist.append(total_mbps)
            hist = hist[-target_len:]
            self.network_history_by_label[option_label] = hist

            self.network_live_stats[option_label] = {
                "send_mbps": send_mbps,
                "recv_mbps": recv_mbps,
                "total_mbps": total_mbps,
            }

    def _is_network_selection(self, selection):
        selected = (selection or "").strip()
        return selected in getattr(self, "network_history_by_label", {})


    def _nice_network_axis_max(self, values):
        vals = [float(v or 0.0) for v in (values or [])]
        peak = max(vals) if vals else 0.0

        if peak <= 0.1:
            return 1.0
        elif peak <= 0.5:
            return 1.0
        elif peak <= 1.0:
            return 2.0
        elif peak <= 2.0:
            return 5.0
        elif peak <= 5.0:
            return 10.0
        elif peak <= 10.0:
            return 20.0
        elif peak <= 20.0:
            return 50.0
        elif peak <= 50.0:
            return 100.0
        elif peak <= 100.0:
            return 200.0
        elif peak <= 200.0:
            return 500.0
        else:
            return max(1000.0, ((int(peak / 100.0) + 1) * 100.0))


    def _network_y_ticks(self, axis_max):
        return [0.0, axis_max * 0.25, axis_max * 0.5, axis_max * 0.75, axis_max]


    def _format_network_axis_label(self, value):
        value = float(value or 0.0)
        if value >= 1.0:
            return f"{value:.1f} Mbps"
        return f"{value * 1000.0:.0f} Kbps"


    def _get_graph_title_for_selection(self, graph_index):
        selected = "CPU"
        if hasattr(self, "graph_option_vars") and graph_index < len(self.graph_option_vars):
            selected = self.graph_option_vars[graph_index].get().strip()

        if selected in getattr(self, "network_live_stats", {}):
            stats = self.network_live_stats.get(selected, {})
            send_mbps = float(stats.get("send_mbps", 0.0) or 0.0)
            recv_mbps = float(stats.get("recv_mbps", 0.0) or 0.0)
            return f"Graph {graph_index + 1} - {selected}  ↑ {send_mbps:.2f} Mbps  ↓ {recv_mbps:.2f} Mbps"

        return f"Graph {graph_index + 1} - {selected}"



    def _get_graph_data_for_selection(self, selection, target_len):
        selected = (selection or "").strip()

        if selected == "Memory":
            return self._resize_history(self.ram_history, target_len)

        if selected in self.disk_history_by_label:
            return self._resize_history(self.disk_history_by_label[selected], target_len)

        if selected in self.network_history_by_label:
            return self._resize_history(self.network_history_by_label[selected], target_len)

        if selected in self.gpu_history_by_label:
            return self._resize_history(self.gpu_history_by_label[selected], target_len)

        return self._resize_history(self.cpu_history, target_len)

    def _read_ohm_gpu_load_sensors(self):
        """
        Returns GPU load sensors with proper hardware names from OHM.
        """

        sensors = []

        ps_cmd = (
            "Get-WmiObject -Namespace 'root\\OpenHardwareMonitor' "
            "-Query \"SELECT * FROM Sensor WHERE SensorType='Load'\" "
            "| Select Parent,Name,Value | ConvertTo-Csv -NoTypeInformation"
        )

        hw_cmd = (
            "Get-WmiObject -Namespace 'root\\OpenHardwareMonitor' "
            "-Query \"SELECT * FROM Hardware\" "
            "| Select Identifier,Name | ConvertTo-Csv -NoTypeInformation"
        )

        try:
            s = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            h = subprocess.run(
                ["powershell", "-NoProfile", "-Command", hw_cmd],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

        except Exception as e:
            self.log(f"GPU SENSOR QUERY ERROR: {e}")
            return sensors

        # Parse hardware names
        hw_map = {}
        try:
            rows = list(csv.DictReader(io.StringIO(h.stdout)))
            for r in rows:
                ident = str(r.get("Identifier", "")).strip()
                name = str(r.get("Name", "")).strip()
                hw_map[ident] = name
        except Exception:
            pass

        # Parse sensors
        try:
            rows = list(csv.DictReader(io.StringIO(s.stdout)))
        except Exception:
            return sensors

        for row in rows:
            parent = str(row.get("Parent", "") or "").strip()
            sensor_name = str(row.get("Name", "") or "").strip()

            if not parent or not sensor_name:
                continue

            try:
                value = float(row.get("Value", 0) or 0)
            except Exception:
                continue

            # Resolve friendly hardware name from OHM hardware table
            hw_name = str(hw_map.get(parent, parent) or "").strip()
            if not hw_name:
                continue

            # Normalize GPU name for cleaner UI labels
            clean_name = hw_name
            clean_name = clean_name.replace("NVIDIA ", "")
            clean_name = clean_name.replace("GeForce ", "")
            clean_name = clean_name.replace("AMD ", "")
            clean_name = clean_name.replace("Radeon ", "")
            clean_name = clean_name.replace("(TM)", "")
            clean_name = clean_name.replace("(R)", "")
            clean_name = " ".join(clean_name.split()).strip()

            # Keep only GPU hardware
            hw_lower = clean_name.lower()
            if (
                "gpu" not in hw_lower
                and "graphics" not in hw_lower
                and "rtx" not in hw_lower
                and "gtx" not in hw_lower
                and "intel" not in hw_lower
                and "arc" not in hw_lower
                and "vega" not in hw_lower
                and "uhd" not in hw_lower
                and "iris" not in hw_lower
            ):
                continue

            sensors.append({
                "hardware": clean_name,
                "sensor_name": sensor_name,
                "value": max(0.0, min(100.0, value)),
            })

        return sensors
    
    
    def _normalize_gpu_engine_name(self, sensor_name):
        """
        Maps OHM sensor names to nicer graph labels.
        """
        s = (sensor_name or "").strip()

        lower = s.lower()

        if "core" in lower or lower == "gpu core":
            return "Overall"
        if "3d" in lower:
            return "3D"
        if "copy" in lower:
            return "Copy"
        if "video decode" in lower:
            return "Video Decode"
        if "video encode" in lower:
            return "Video Encode"
        if "memory" in lower and "controller" in lower:
            return "Memory Controller"
        if "memory" in lower:
            return "Memory"
        if "bus" in lower:
            return "Bus"
        if "compute" in lower:
            return "Compute"

        return s

    def _get_gpu_sources(self):
        """
        Returns a list of tuples:
        [
            ("GPU 0 (Overall)", {"hardware": "...", "sensor_name": "GPU Core", "kind": "overall"}),
            ("GPU 0 (3D)", {"hardware": "...", "sensor_name": "GPU 3D", "kind": "engine"}),
            ...
        ]
        """
        sensors = self._read_ohm_gpu_load_sensors()
        if not sensors:
            return []

        # Group by GPU hardware name in stable order
        hardware_names = []
        by_hw = {}

        for s in sensors:
            hw = s["hardware"]
            if hw not in by_hw:
                by_hw[hw] = []
                hardware_names.append(hw)
            by_hw[hw].append(s)

        results = []

        for gpu_index, hw in enumerate(hardware_names):
            hw_sensors = by_hw[hw]

            # Deduplicate normalized labels
            seen_labels = set()

            # Prefer a "core"/overall sensor first if present
            overall_sensor = None
            for s in hw_sensors:
                pretty = self._normalize_gpu_engine_name(s["sensor_name"])
                if pretty == "Overall":
                    overall_sensor = s
                    break

            if overall_sensor is not None:
                gpu_name = hw.strip()

                # Remove common OHM prefixes if present
                gpu_name = gpu_name.replace("GPU ", "").strip()

                label = f"{gpu_name} (Overall)"
                results.append((
                    label,
                    {
                        "hardware": hw,
                        "sensor_name": overall_sensor["sensor_name"],
                        "pretty_name": "Overall",
                    }
                ))
                seen_labels.add("Overall")

            # Add the remaining sensors
            for s in hw_sensors:
                pretty = self._normalize_gpu_engine_name(s["sensor_name"])

                if pretty in seen_labels:
                    continue

                # If there was no explicit overall sensor, do not duplicate it here
                if pretty == "Overall" and overall_sensor is None:
                    label = f"GPU {gpu_index} (Overall)"
                else:
                    gpu_name = hw.strip()
                    gpu_name = gpu_name.replace("GPU ", "").strip()

                    label = f"{gpu_name} ({pretty})"

                results.append((
                    label,
                    {
                        "hardware": hw,
                        "sensor_name": s["sensor_name"],
                        "pretty_name": pretty,
                    }
                ))
                seen_labels.add(pretty)

        return results

    def _ensure_gpu_histories(self, target_len):
        for option_label in self.gpu_sensor_map.keys():
            existing = self.gpu_history_by_label.get(option_label, [])
            self.gpu_history_by_label[option_label] = self._resize_history(existing, target_len)

        stale = [k for k in self.gpu_history_by_label.keys() if k not in self.gpu_sensor_map]
        for k in stale:
            del self.gpu_history_by_label[k]

        stale_live = [k for k in self.gpu_live_values.keys() if k not in self.gpu_sensor_map]
        for k in stale_live:
            del self.gpu_live_values[k]

    def _sample_gpu_histories(self, target_len):
        self._ensure_gpu_histories(target_len)

        sensors = self._read_ohm_gpu_load_sensors()
        latest_map = {}

        for s in sensors:
            key = (s["hardware"], s["sensor_name"])
            latest_map[key] = max(0.0, min(100.0, float(s["value"])))

        for option_label, desc in self.gpu_sensor_map.items():
            key = (desc["hardware"], desc["sensor_name"])
            gpu_percent = float(latest_map.get(key, 0.0))

            hist = self.gpu_history_by_label.get(option_label, [])
            hist = self._resize_history(hist, target_len)
            hist.append(gpu_percent)
            hist = hist[-target_len:]
            self.gpu_history_by_label[option_label] = hist

            self.gpu_live_values[option_label] = gpu_percent
            

    def _refresh_graph_source_options(self):
        disk_sources = self._get_windows_disk_sources()
        net_sources = self._get_network_sources()
        gpu_sources = self._get_gpu_sources()

        self.disk_mount_map = {}
        self.network_nic_map = {}
        self.gpu_sensor_map = {}

        options = ["CPU", "Memory"]

        for mount, label in disk_sources:
            option_label = f"Disk with {label} Usage"
            options.append(option_label)
            self.disk_mount_map[option_label] = mount

        for nic_name in net_sources:
            option_label = nic_name
            options.append(option_label)
            self.network_nic_map[option_label] = nic_name

        for option_label, sensor_desc in gpu_sources:
            options.append(option_label)
            self.gpu_sensor_map[option_label] = sensor_desc

        self.graph_source_options = options

        if hasattr(self, "graph_option_vars"):
            for var in self.graph_option_vars:
                current = var.get().strip()
                if current not in options:
                    var.set("CPU")


    def _normalize_windows_gpu_engine_name(self, engine_name):
        s = (engine_name or "").strip()

        # remove trailing instance suffixes like Compute_0
        s = re.sub(r"_\d+$", "", s)

        lower = s.lower().replace("_", " ").strip()

        if lower == "3d":
            return "3D"
        if lower == "copy":
            return "Copy"
        if lower == "compute":
            return "Compute"
        if lower == "video decode":
            return "Video Decode"
        if lower == "video encode":
            return "Video Encode"
        if lower == "video processing":
            return "Video Processing"
        if lower == "overlay":
            return "Overlay"

        # keep unknown names readable
        parts = lower.split()
        return " ".join(p.capitalize() for p in parts) if parts else s


    def _start_telemetry_worker(self):
        if self._telemetry_worker_running:
            return

        self._telemetry_worker_running = True

        def worker():
            while self._telemetry_worker_running:
                try:
                    # CPU frequency
                    try:
                        if psutil is not None and psutil.cpu_freq():
                            freq_ghz = psutil.cpu_freq().current / 1000.0
                        else:
                            freq_ghz = None
                    except Exception:
                        freq_ghz = None

                    # Temperature
                    try:
                        temp_text = self._get_windows_temp()
                    except Exception:
                        temp_text = "N/A"

                    # CPU utilization
                    try:
                        cpu = psutil.cpu_percent(interval=None) if psutil is not None else 0.0
                    except Exception:
                        cpu = 0.0

                    # RAM
                    try:
                        vm = psutil.virtual_memory()
                        ram_percent = float(vm.percent)
                        ram_used_gb = vm.used / (1024 ** 3)
                        ram_total_gb = vm.total / (1024 ** 3)
                    except Exception:
                        ram_percent = 0.0
                        ram_used_gb = 0.0
                        ram_total_gb = 0.0

                    try:
                        target_len = 60
                        if hasattr(self, "graph_seconds_var"):
                            raw = str(self.graph_seconds_var.get()).strip()
                            if raw in {"30", "60", "120"}:
                                target_len = int(raw)
                    except Exception:
                        target_len = 60

                    with self._state_lock:
                        self._sample_all_graph_histories(target_len, cpu, ram_percent)

                        self._telemetry_snapshot = {
                            "cpu": cpu,
                            "ram_percent": ram_percent,
                            "ram_used_gb": ram_used_gb,
                            "ram_total_gb": ram_total_gb,
                            "freq_ghz": freq_ghz,
                            "temp_text": temp_text,
                            "ready": True,
                        }


                except Exception as e:
                    self.log(f"TELEMETRY WORKER ERROR: {e}")

                time.sleep(max(self.FREQ_POLL_MS / 1000.0, 0.25))

        self._telemetry_worker_thread = threading.Thread(target=worker, daemon=True)
        self._telemetry_worker_thread.start()