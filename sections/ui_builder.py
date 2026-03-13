import os
import tkinter as tk
import customtkinter as ctk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

try:
    import psutil  # type: ignore
except Exception:
    psutil = None


class UIBuildMixin:
    def _setup_dark_ttk_style(self):
        style = ttk.Style(self)

        try:
            style.theme_use("default")
        except Exception:
            pass

        bg_main = "#1a1a1a"
        bg_panel = "#242424"
        bg_header = "#2b2b2b"
        fg_text = "#e6e6e6"
        fg_muted = "#a0a0a0"
        accent = "#3a7ebf"
        heavy = "#ff5c5c"
        separator_bg = "#303030"

        style.configure(
            "Treeview",
            background=bg_panel,
            foreground=fg_text,
            fieldbackground=bg_panel,
            borderwidth=0,
            rowheight=26,
        )
        style.map(
            "Treeview",
            background=[("selected", accent)],
            foreground=[("selected", "#ffffff")],
        )

        style.configure(
            "Treeview.Heading",
            background=bg_header,
            foreground=fg_text,
            relief="flat",
            borderwidth=0,
            padding=(8, 6),
        )
        style.map(
            "Treeview.Heading",
            background=[("active", "#383838")],
            foreground=[("active", "#ffffff")],
        )

        style.configure(
            "Vertical.TScrollbar",
            background=bg_panel,
            troughcolor=bg_main,
            borderwidth=0,
            arrowcolor=fg_text,
        )

        style.configure(
            "Dark.Vertical.TScrollbar",
            background="#242424",
            troughcolor="#1a1a1a",
            borderwidth=0,
            arrowcolor="#e6e6e6",
            gripcount=0,
            relief="flat",
        )

        style.map(
            "Dark.Vertical.TScrollbar",
            background=[
                ("active", "#383838"),
                ("pressed", "#4a4a4a"),
            ]
        )

        self._tree_colors = {
            "bg_main": bg_main,
            "bg_panel": bg_panel,
            "bg_header": bg_header,
            "fg_text": fg_text,
            "fg_muted": fg_muted,
            "accent": accent,
            "heavy": heavy,
            "separator_bg": separator_bg,
        }

    def _style_matplotlib_dark(self, fig, ax):
        colors = getattr(self, "_tree_colors", {})
        bg_main = colors.get("bg_main", "#1a1a1a")
        bg_panel = colors.get("bg_panel", "#242424")
        fg_text = colors.get("fg_text", "#e6e6e6")
        grid = "#404040"

        fig.patch.set_facecolor(bg_panel)
        ax.set_facecolor(bg_panel)

        for spine in ax.spines.values():
            spine.set_color("#555555")

        ax.tick_params(axis="x", colors=fg_text, labelsize=8)
        ax.tick_params(axis="y", colors=fg_text, labelsize=8)
        ax.yaxis.label.set_color(fg_text)
        ax.xaxis.label.set_color(fg_text)
        ax.title.set_color(fg_text)
        ax.grid(True, which="major", axis="both", linestyle="-", linewidth=0.6, color=grid)

    def _build_top_bar(self, root):
        top = ctk.CTkFrame(root, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        controls_left = ctk.CTkFrame(top, fg_color="transparent")
        controls_left.pack(side="left", fill="x", expand=True)

        controls_right = ctk.CTkFrame(top, fg_color="transparent")
        controls_right.pack(side="right")

        ctk.CTkSwitch(
            controls_left,
            text="Detect Load Dynamically",
            variable=self.auto_mode,
            command=self._on_auto_toggle,
        ).pack(side="left")

        ctk.CTkSwitch(
            controls_left,
            text="Run at Startup (No UAC)",
            variable=self.startup_var,
            command=self._toggle_startup,
        ).pack(side="left", padx=8)

        ctk.CTkSwitch(
            controls_left,
            text="Dark Mode",
            variable=self.dark_mode_var,
            command=self._on_theme_toggle
        ).pack(side="left", padx=8)

        ctk.CTkLabel(
            controls_right,
            text="Select plan",
        ).pack(side="left", padx=(0, 8))

        self.plan_select_menu = ctk.CTkOptionMenu(
            controls_right,
            variable=self.manual_plan_label_var,
            values=["Auto"],
            command=self._on_plan_dropdown_changed,
            width=220,
        )
        self.plan_select_menu.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            controls_right,
            text="Configure plans",
            command=self._open_plan_config_window,
            width=130,
        ).pack(side="left")



    def _build_bottom_status_bar(self, root):
        self.bottom_status_bar = ctk.CTkFrame(
            root,
            corner_radius=12,
            border_width=2,
        )
        self.bottom_status_bar.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        left = ctk.CTkFrame(self.bottom_status_bar, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True, padx=(10, 6), pady=6)

        right = ctk.CTkFrame(self.bottom_status_bar, fg_color="transparent")
        right.pack(side="right", padx=(6, 10), pady=6)

        self.pause_status_label = ctk.CTkLabel(
            left,
            textvariable=self.pause_status_var,
            anchor="w",
            font=self.top_status_font,
        )
        self.pause_status_label.pack(side="left")

        self._build_status_labels(right)

    def _update_bottom_bar_border(self, high_perf_active=False):
        if not hasattr(self, "bottom_status_bar"):
            return

        t = getattr(self, "_theme", None)
        if not t:
            return

        panel_color = t["bg_panel"]
        border_color = "#2563eb" if high_perf_active else panel_color

        try:
            self.bottom_status_bar.configure(
                fg_color=panel_color,
                border_color=border_color,
            )
        except Exception:
            pass


    def _build_status_labels(self, parent):
        self.status_label = ctk.CTkLabel(
            parent,
            textvariable=self.status_var,
            text_color=self.status_col,
            font=self.top_status_font,
        )
        self.status_label.pack(side="right", padx=(0, 15))

        self.mem_label = ctk.CTkLabel(
            parent,
            textvariable=self.mem_var,
            text_color=self.status_col,
            font=self.top_status_font,
        )
        self.mem_label.pack(side="right", padx=(0, 15))

        self.temp_label = ctk.CTkLabel(
            parent,
            textvariable=self.temp_var,
            text_color=self.status_col,
            font=self.top_status_font,
        )
        self.temp_label.pack(side="right", padx=(0, 15))

        self.freq_label = ctk.CTkLabel(
            parent,
            textvariable=self.freq_var,
            text_color=self.status_col,
            font=self.top_status_font,
        )
        self.freq_label.pack(side="right", padx=(0, 15))

        self.cpu_usage_label = ctk.CTkLabel(
            parent,
            textvariable=self.cpu_usage_var,
            text_color=self.status_col,
            font=self.top_status_font,
        )
        self.cpu_usage_label.pack(side="right", padx=(0, 20))



    def _build_ui(self):
        root = ctk.CTkFrame(self, corner_radius=0)
        root.pack(fill="both", expand=True, padx=10, pady=10)

        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        self._build_top_bar(root)
        self._build_main_area(root)
        self._build_bottom_status_bar(root)

        if hasattr(self, "dark_mode_var"):
            mode = "dark" if self.dark_mode_var.get() else "light"
            self._apply_theme(mode, initial=False)


    def _bind_ui_interaction_pause(self):
        targets = [self]

        for widget in targets:
            widget.bind_all("<Motion>", self._on_ui_interaction, add="+")
            widget.bind_all("<Button>", self._on_ui_interaction, add="+")
            widget.bind_all("<MouseWheel>", self._on_ui_interaction, add="+")
            widget.bind_all("<KeyPress>", self._on_ui_interaction, add="+")
            widget.bind_all("<Enter>", self._on_ui_interaction, add="+")


    def _on_ui_interaction(self, _event=None):
        self._ui_interacting = True

        if hasattr(self, "pause_status_var"):
            self.pause_status_var.set("Visual Updates Paused - Mouse activity detected")

        if self._ui_resume_job is not None:
            try:
                self.after_cancel(self._ui_resume_job)
            except Exception:
                pass
            self._ui_resume_job = None

        self._ui_resume_job = self.after(self._ui_pause_ms, self._end_ui_interaction)


    def _end_ui_interaction(self):
        self._ui_interacting = False
        self._ui_resume_job = None

        if hasattr(self, "pause_status_var"):
            self.pause_status_var.set("Visual Updates Active")



    def _build_main_area(self, root):
        main = ctk.CTkFrame(root, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew") # Placed on row 1

        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        # LEFT SIDE
        left = ctk.CTkFrame(main, corner_radius=12)
        
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=3)
        left.rowconfigure(1, weight=2)

        self._build_processes_panel(left)

        bottom_controls = ctk.CTkFrame(left, fg_color="transparent")
        bottom_controls.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        bottom_controls.columnconfigure(0, weight=1)
        bottom_controls.rowconfigure(0, weight=1)

        self._build_exe_rules_panel(bottom_controls, 0, 0)






        # RIGHT SIDE
        right = ctk.CTkFrame(main, corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        self._build_graphs_panel(right)
        self._build_disk_panel(right)
        
    def _build_processes_panel(self, main):
        left = ctk.CTkFrame(main, corner_radius=12)
        
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)

        left_title = ctk.CTkLabel(
            left,
            text="Running Processes (Double Click to watch them)",
            anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        left_title.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))

        sr = ctk.CTkFrame(left, fg_color="transparent")
        sr.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))
        sr.columnconfigure(1, weight=1)

        ctk.CTkLabel(sr, text="Search:").grid(row=0, column=0, sticky="w")
        ent = ctk.CTkEntry(sr, textvariable=self.search_var)
        ent.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ent.bind("<KeyRelease>", lambda e: self._apply_process_filter())

        proc_table_wrap = ctk.CTkFrame(left, fg_color="transparent")
        proc_table_wrap.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        proc_table_wrap.columnconfigure(0, weight=1)
        proc_table_wrap.rowconfigure(0, weight=1)

        self.proc_tree = ttk.Treeview(
            proc_table_wrap,
            columns=("exe", "cores", "cpu_total", "threads", "memory", "threading", "path"),
            show="headings",
            selectmode="browse",
        )

        # Hide "threading" from view, but keep it in the row values if you still want it available internally
        self.proc_tree["displaycolumns"] = ("exe", "cores", "cpu_total", "threads", "memory", "path")

        self.proc_tree.heading(
            "exe",
            text="EXE",
            command=lambda: self._sort_treeview(
                "exe",
                not (self.sort_col == "exe" and self.sort_reverse),
            ),
        )
        self.proc_tree.heading(
            "cores",
            text="Cores Used",
            command=lambda: self._sort_treeview(
                "cores",
                not (self.sort_col == "cores" and self.sort_reverse),
            ),
        )
        self.proc_tree.heading(
            "cpu_total",
            text="CPU %",
            command=lambda: self._sort_treeview(
                "cpu_total",
                not (self.sort_col == "cpu_total" and self.sort_reverse),
            ),
        )
        self.proc_tree.heading(
            "threads",
            text="Threads",
            command=lambda: self._sort_treeview(
                "threads",
                not (self.sort_col == "threads" and self.sort_reverse),
            ),
        )
        self.proc_tree.heading(
            "memory",
            text="Memory",
            command=lambda: self._sort_treeview(
                "memory",
                not (self.sort_col == "memory" and self.sort_reverse),
            ),
        )
        self.proc_tree.heading(
            "threading",
            text="Threading",
            command=lambda: self._sort_treeview(
                "threading",
                not (self.sort_col == "threading" and self.sort_reverse),
            ),
        )
        self.proc_tree.heading(
            "path",
            text="Full Path",
            command=lambda: self._sort_treeview(
                "path",
                not (self.sort_col == "path" and self.sort_reverse),
            ),
        )

        self.proc_tree.column("exe", width=180, anchor="w", stretch=False)
        self.proc_tree.column("cores", width=85, anchor="center", stretch=False)
        self.proc_tree.column("cpu_total", width=80, anchor="center", stretch=False)
        self.proc_tree.column("threads", width=70, anchor="center", stretch=False)
        self.proc_tree.column("memory", width=95, anchor="center", stretch=False)
        self.proc_tree.column("threading", width=90, anchor="center", stretch=False)
        self.proc_tree.column("path", width=620, anchor="w", stretch=True)

        proc_scroll = ttk.Scrollbar(proc_table_wrap, orient="vertical", command=self.proc_tree.yview)
        proc_scroll.grid(row=0, column=1, sticky="ns")

        proc_hscroll = ttk.Scrollbar(
            proc_table_wrap,
            orient="horizontal",
            command=self.proc_tree.xview,
            style="Horizontal.TScrollbar",
        )
        proc_hscroll.grid(row=1, column=0, sticky="ew")

        self.proc_tree.configure(
            yscrollcommand=proc_scroll.set,
            xscrollcommand=proc_hscroll.set
        )

        self.proc_tree.grid(row=0, column=0, sticky="nsew")
        proc_scroll.grid(row=0, column=1, sticky="ns")

        self.proc_tree.bind("<Double-1>", self._on_process_double_click)
        self.proc_tree.bind("<Button-3>", self._on_process_right_click)
        self.proc_tree.bind("<Shift-MouseWheel>", lambda e: self.proc_tree.xview_scroll(-int(e.delta/120), "units"))


        # Optional Linux/X11 middle/right-click compatibility
        self.proc_tree.bind("<Button-2>", self._on_process_right_click)
    
    def _build_graphs_panel(self, right):
        self._refresh_graph_source_options()

        graphs_panel = ctk.CTkFrame(right, corner_radius=12)
        graphs_panel.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        graphs_panel.columnconfigure(0, weight=1)
        graphs_panel.rowconfigure(2, weight=1)

        ctk.CTkLabel(
            graphs_panel,
            text="Performance Graphs",
            anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))

        top_controls = ctk.CTkFrame(graphs_panel, fg_color="transparent")
        top_controls.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        top_controls.columnconfigure(3, weight=1)

        ctk.CTkLabel(
            top_controls,
            text="Showing past",
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=(2, 6))

        if not hasattr(self, "graph_seconds_var"):
            saved_seconds = str(getattr(self, "saved_graph_seconds", "60")).strip()

            if saved_seconds not in {"30", "60", "120"}:
                saved_seconds = "60"

            self.graph_seconds_var = tk.StringVar(value=saved_seconds)

        def on_window_change(choice):
            try:
                seconds = int(str(choice).strip())
            except Exception:
                seconds = 60

            self.graph_seconds_var.set(str(seconds))

            self.cpu_history = self._resize_history(self.cpu_history, seconds)
            self.ram_history = self._resize_history(self.ram_history, seconds)
            self._ensure_disk_histories(seconds)
            self._ensure_network_histories(seconds)
            self._ensure_gpu_histories(seconds)

            for i, ax in enumerate(getattr(self, "graph_axes", [])):
                ax.set_xlim(0, max(0, seconds - 1))
                ax.set_xticks(self._graph_x_ticks_for_window(seconds))
                ax.set_yticks([0, 25, 50, 75, 100])
                ax.set_yticklabels(["0", "25", "50", "75", "100"])

                ax.set_xticklabels([])


                if i < len(getattr(self, "graph_lines", [])):
                    selected = "CPU"
                    if hasattr(self, "graph_option_vars") and i < len(self.graph_option_vars):
                        selected = self.graph_option_vars[i].get().strip()

                    data = self._get_graph_data_for_selection(selected, seconds)

                    self.graph_lines[i].set_xdata(list(range(seconds)))
                    self.graph_lines[i].set_ydata(data)

            for canvas in getattr(self, "graph_canvas_widgets", []):
                canvas.draw_idle()
            
            self._save_now()

        seconds_dropdown = ctk.CTkOptionMenu(
            top_controls,
            variable=self.graph_seconds_var,
            values=["30", "60", "120"],
            command=on_window_change,
            width=90,
        )
        seconds_dropdown.grid(row=0, column=1, sticky="w")

        ctk.CTkLabel(
            top_controls,
            text="seconds",
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=2, sticky="w", padx=(8, 0))

        graphs = ctk.CTkFrame(graphs_panel, fg_color="transparent")
        graphs.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 6))
        for c in range(3):
            graphs.columnconfigure(c, weight=1)
        for r in range(2):
            graphs.rowconfigure(r, weight=1)

        if not hasattr(self, "graph_option_vars"):
            saved_sources = list(getattr(self, "saved_graph_sources", ["CPU"] * 6))

            while len(saved_sources) < 6:
                saved_sources.append("CPU")

            self.graph_option_vars = [
                tk.StringVar(value=str(saved_sources[i] or "CPU"))
                for i in range(6)
]

        self.graph_figs = []
        self.graph_axes = []
        self.graph_lines = []
        self.graph_canvas_widgets = []

        window_seconds = int(self.graph_seconds_var.get())
        self._ensure_disk_histories(window_seconds)

        self.graph_title_labels = []

        # helper used by dropdowns
        def on_graph_source_change(idx):
            self.graph_title_labels[idx].configure(
                text=self._get_graph_title_for_selection(idx)
            )
            self._save_now()
            
        for i in range(6):
            row = i // 3
            col = i % 3

            card = ctk.CTkFrame(graphs, corner_radius=12)
            card.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
            card.columnconfigure(0, weight=1)
            card.rowconfigure(1, weight=1)

            title = ctk.CTkLabel(
                card,
                text=self._get_graph_title_for_selection(i),
                anchor="w",
                font=ctk.CTkFont(size=14, weight="bold"),
            )
            title.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
            
            self.graph_title_labels.append(title)

            fig = Figure(figsize=(4.0, 1.8), dpi=100)
            ax = fig.add_subplot(111)
            fig.subplots_adjust(left=0.18, right=0.98, top=0.92, bottom=0.12)

            ax.set_xlim(0, max(0, window_seconds - 1))
            ax.set_ylim(0, 100)
            ax.set_xticks(self._graph_x_ticks_for_window(window_seconds))
            ax.set_yticks([0, 25, 50, 75, 100])
            ax.set_xticklabels([])
            ax.set_yticklabels([])
            ax.tick_params(axis="both", which="both", length=0)

            initial_data = self._get_graph_data_for_selection(self.graph_option_vars[i].get(), window_seconds)
            line, = ax.plot(range(window_seconds), initial_data)

            canvas = FigureCanvasTkAgg(fig, master=card)
            canvas.draw()
            canvas.get_tk_widget().grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

            controls = ctk.CTkFrame(card, fg_color="transparent")
            controls.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
            controls.columnconfigure(0, weight=1)

            dropdown = ctk.CTkOptionMenu(
                controls,
                variable=self.graph_option_vars[i],
                values=self.graph_source_options,
                command=lambda _value, idx=i: on_graph_source_change(idx),
            )
            dropdown.grid(row=0, column=0, sticky="ew")

            self.graph_figs.append(fig)
            self.graph_axes.append(ax)
            self.graph_lines.append(line)
            self.graph_canvas_widgets.append(canvas)


    def _build_disk_panel(self, right):
        disk = ctk.CTkFrame(right, corner_radius=12)
        disk.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        disk.columnconfigure(0, weight=1)
        disk.rowconfigure(2, weight=1)

        ctk.CTkLabel(
            disk,
            text="Accumulated Disk Activity",
            anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))

        disk_top = ctk.CTkFrame(disk, fg_color="transparent")
        disk_top.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))
        disk_top.columnconfigure(1, weight=1)

        ctk.CTkButton(
            disk_top,
            text="Reset Accumulated Read/Write Timestamp",
            command=self._reset_disk_accum_timestamp,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            disk_top,
            textvariable=self.disk_reset_var,
        ).grid(row=0, column=1, sticky="w", padx=(12, 0))

        disk_table_wrap = ctk.CTkFrame(disk, fg_color="transparent")
        disk_table_wrap.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        disk_table_wrap.columnconfigure(0, weight=1)
        disk_table_wrap.rowconfigure(0, weight=1)

        self.disk_tree = ttk.Treeview(
            disk_table_wrap,
            columns=("exe", "path", "read_speed", "write_speed", "accum_read", "accum_write", "file_path"),
            show="headings",
            selectmode="browse",
        )

        self.disk_tree.heading("exe", text="EXE")
        self.disk_tree.heading("path", text="Path")
        self.disk_tree.heading(
            "read_speed",
            text="Read Speed",
            command=lambda: self._sort_disk_treeview(
                "read_speed",
                not (self.disk_sort_col == "read_speed" and self.disk_sort_reverse),
            ),
        )
        self.disk_tree.heading(
            "write_speed",
            text="Write Speed",
            command=lambda: self._sort_disk_treeview(
                "write_speed",
                not (self.disk_sort_col == "write_speed" and self.disk_sort_reverse),
            ),
        )
        self.disk_tree.heading(
            "accum_read",
            text="Accum Read",
            command=lambda: self._sort_disk_treeview(
                "accum_read",
                not (self.disk_sort_col == "accum_read" and self.disk_sort_reverse),
            ),
        )
        self.disk_tree.heading(
            "accum_write",
            text="Accum Write",
            command=lambda: self._sort_disk_treeview(
                "accum_write",
                not (self.disk_sort_col == "accum_write" and self.disk_sort_reverse),
            ),
        )
        self.disk_tree.heading("file_path", text="Path of file being written to")

        self.disk_tree.column("exe", width=130, anchor="w", stretch=False)
        self.disk_tree.column("path", width=260, anchor="w", stretch=True)
        self.disk_tree.column("read_speed", width=95, anchor="center", stretch=False)
        self.disk_tree.column("write_speed", width=95, anchor="center", stretch=False)
        self.disk_tree.column("accum_read", width=120, anchor="center", stretch=False)
        self.disk_tree.column("accum_write", width=120, anchor="center", stretch=False)
        self.disk_tree.column("file_path", width=0, anchor="w", stretch=True)

        self.disk_tree.grid(row=0, column=0, sticky="nsew")

        disk_scroll = ttk.Scrollbar(disk_table_wrap, orient="vertical", command=self.disk_tree.yview)
        disk_scroll.grid(row=0, column=1, sticky="ns")

        disk_hscroll = ttk.Scrollbar(
            disk_table_wrap,
            orient="horizontal",
            command=self.disk_tree.xview,
            style="Horizontal.TScrollbar",
        )
        disk_hscroll.grid(row=1, column=0, sticky="ew")

        self.disk_tree.configure(
            yscrollcommand=disk_scroll.set,
            xscrollcommand=disk_hscroll.set
        )
        self.disk_tree.bind("<Shift-MouseWheel>", lambda e: self.disk_tree.xview_scroll(-int(e.delta/120), "units"))

    def _build_exe_rules_panel(self, main, row, col, colspan=1):
        panel = ctk.CTkFrame(
            main,
            corner_radius=12,
            fg_color=("gray90", "gray20")
        )


        panel.grid(row=row, column=col, columnspan=colspan, sticky="nsew", padx=(0, 8))
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=1)

        panel_title = ctk.CTkLabel(
            panel,
            text="EXE Rules",
            anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        panel_title.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))

        info_row = ctk.CTkFrame(panel, fg_color="transparent")
        info_row.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))
        info_row.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            info_row,
            text="Watched → Forces high performance  |  Blacklisted → Never triggers high performance",
            anchor="w",
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=0, sticky="w")

        tree_wrap = ctk.CTkFrame(panel, fg_color="transparent")
        tree_wrap.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
        tree_wrap.columnconfigure(0, weight=1)
        tree_wrap.rowconfigure(0, weight=1)

        self.exe_rules_tree = ttk.Treeview(
            tree_wrap,
            columns=("status", "exe", "path"),
            show="headings",
            selectmode="browse",
        )

        self.exe_rules_tree.heading("status", text="Status")
        self.exe_rules_tree.heading("exe", text="EXE")
        self.exe_rules_tree.heading("path", text="Path")

        self.exe_rules_tree.column("status", width=120, anchor="center", stretch=False)
        self.exe_rules_tree.column("exe", width=180, anchor="w", stretch=False)
        self.exe_rules_tree.column("path", width=620, anchor="w", stretch=True)

        exe_scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.exe_rules_tree.yview)
        exe_scroll.grid(row=0, column=1, sticky="ns")

        exe_hscroll = ttk.Scrollbar(
            tree_wrap,
            orient="horizontal",
            command=self.exe_rules_tree.xview,
            style="Horizontal.TScrollbar",
        )
        exe_hscroll.grid(row=1, column=0, sticky="ew")

        self.exe_rules_tree.configure(
            yscrollcommand=exe_scroll.set,
            xscrollcommand=exe_hscroll.set,
        )

        self.exe_rules_tree.grid(row=0, column=0, sticky="nsew")

        self.exe_rules_tree.bind("<Double-1>", self._on_exe_rules_double_click)
        self.exe_rules_tree.bind("<Button-1>", self._on_exe_rules_click, add="+")
        self.exe_rules_tree.bind(
            "<Shift-MouseWheel>",
            lambda e: self.exe_rules_tree.xview_scroll(-int(e.delta / 120), "units")
        )

        buttons = ctk.CTkFrame(panel, fg_color="transparent")
        buttons.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))

        ctk.CTkButton(
            buttons,
            text="Add EXE...",
            command=self._add_exe_rule,
        ).pack(side="left")

        ctk.CTkButton(
            buttons,
            text="Remove Selected",
            command=self._remove_selected_exe_rule,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            buttons,
            text="Set Watched",
            command=lambda: self._set_selected_exe_rule_mode("watched"),
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            buttons,
            text="Set Blacklisted",
            command=lambda: self._set_selected_exe_rule_mode("blacklisted"),
        ).pack(side="left")

        self._render_exe_rules()







    def _on_exe_rules_click(self, event):
        tree = self.exe_rules_tree

        region = tree.identify("region", event.x, event.y)

        if region not in ("cell", "tree"):
            tree.selection_remove(tree.selection())
            return

        item = tree.identify_row(event.y)

        if not item:
            tree.selection_remove(tree.selection())



    def _on_theme_toggle(self):
        mode = "dark" if self.dark_mode_var.get() else "light"
        self._apply_theme(mode)
                
    def _apply_theme(self, mode: str, initial: bool = False):
        ctk.set_appearance_mode(mode)

        if mode == "dark":
            self._theme = {
                "bg_main": "#1a1a1a",
                "bg_panel": "#242424",
                "bg_header": "#2b2b2b",
                "fg_text": "#e6e6e6",
                "fg_muted": "#a0a0a0",
                "accent": "#3a7ebf",
                "accent_hover": "#2f6aa3",
                "heavy": "#ff5c5c",
                "separator_bg": "#303030",
                "list_select_bg": "#3a7ebf",
                "list_select_fg": "#ffffff",
                "plot_grid": "#404040",
                "plot_spine": "#555555",
                "heartbeat": "#66b3ff",
                "default_status": "#e6e6e6",
            }
        else:
            self._theme = {
                "bg_main": "#efefef",
                "bg_panel": "#ffffff",
                "bg_header": "#e8e8e8",
                "fg_text": "#111111",
                "fg_muted": "#666666",
                "accent": "#2563eb",
                "accent_hover": "#1d4ed8",
                "heavy": "#cc0000",
                "separator_bg": "#f2f2f2",
                "list_select_bg": "#2563eb",
                "list_select_fg": "#ffffff",
                "plot_grid": "#d0d0d0",
                "plot_spine": "#b0b0b0",
                "heartbeat": "#0066cc",
                "default_status": "#000000",
            }

        # During initial setup, widgets do not exist yet
        if initial:
            self.status_col = self._theme["default_status"]
            return

        self._setup_ttk_theme_from_current_mode()
        self._apply_listbox_theme()
        self._apply_plot_theme()
        self._reapply_treeview_tags()
        self._set_status_color(self.status_col)

        self._refresh_status_color_for_theme()
        
        color = "#e6e6e6" if self.dark_mode_var.get() else "#000000"
        self._set_status_color(color)

        is_high = str(getattr(self, "status_var", tk.StringVar(value="")).get()).lower()
        self._update_bottom_bar_border("high perf" in is_high)


        
    def _apply_listbox_theme(self):
        t = self._theme

        listboxes = [
            getattr(self, "override_list", None),
            getattr(self, "watch_list", None),
            getattr(self, "blacklist_list", None),
            getattr(self, "plan_config_low_list", None),
            getattr(self, "plan_config_high_list", None),
        ]

        alive_listboxes = []

        for lb in listboxes:
            if lb is None:
                continue

            try:
                if not bool(lb.winfo_exists()):
                    continue

                lb.configure(
                    bg=t["bg_panel"],
                    fg=t["fg_text"],
                    selectbackground=t["list_select_bg"],
                    selectforeground=t["list_select_fg"],
                    highlightbackground=t["bg_panel"],
                    highlightcolor=t["accent"],
                    highlightthickness=0,
                    relief="flat",
                    borderwidth=0,
                    activestyle="none",
                )
                alive_listboxes.append(lb)

            except Exception:
                continue

        # clear stale popup refs if their widgets are gone
        try:
            if getattr(self, "plan_config_low_list", None) not in alive_listboxes:
                self.plan_config_low_list = None
        except Exception:
            self.plan_config_low_list = None

        try:
            if getattr(self, "plan_config_high_list", None) not in alive_listboxes:
                self.plan_config_high_list = None
        except Exception:
            self.plan_config_high_list = None
            

    def _apply_plot_theme(self):
        t = self._theme

        plots = list(
            zip(
                getattr(self, "graph_figs", []),
                getattr(self, "graph_axes", []),
                getattr(self, "graph_canvas_widgets", []),
            )
        )

        for fig, ax, canvas in plots:
            if fig is None or ax is None or canvas is None:
                continue

            fig.patch.set_facecolor(t["bg_panel"])
            ax.set_facecolor(t["bg_panel"])

            for spine in ax.spines.values():
                spine.set_color(t["plot_spine"])

            ax.tick_params(axis="x", colors=t["fg_text"], labelsize=0, length=0)
            ax.tick_params(axis="y", colors=t["fg_text"], length=0)

            ax.xaxis.label.set_color(t["fg_text"])
            ax.yaxis.label.set_color(t["fg_text"])
            ax.title.set_color(t["fg_text"])

            ax.grid(True, which="major", axis="both", color=t["plot_grid"], linewidth=0.6)

            canvas.draw_idle()
                

    def _reapply_treeview_tags(self):
        t = self._theme

        if hasattr(self, "proc_tree"):
            self.proc_tree.tag_configure("notexe", foreground=t["fg_muted"])
            self.proc_tree.tag_configure("heavy", foreground=t["heavy"], font=("Segoe UI", 9, "bold"))
            self.proc_tree.tag_configure("heartbeat", foreground=t["heartbeat"])
            self.proc_tree.tag_configure("separator", background=t["separator_bg"])

        if hasattr(self, "exe_rules_tree"):
            self.exe_rules_tree.tag_configure("rule_blacklisted", foreground="#4da3ff")
            self.exe_rules_tree.tag_configure("rule_watched", foreground="#ff5c5c")




    def _get_default_status_color(self):
        return self._theme["fg_text"]

    def _refresh_status_color_for_theme(self):
        current = str(getattr(self, "status_col", "")).lower().strip()

        neutral_colors = {
            "black",
            "#000",
            "#000000",
            "white",
            "#fff",
            "#ffffff",
            "#e6e6e6",
            "#111111",
        }

        if current in neutral_colors or current == "":
            self._set_status_color(self._get_default_status_color())
        else:
            self._set_status_color(self.status_col)
                
    def _setup_ttk_theme_from_current_mode(self):
        t = self._theme
        style = ttk.Style(self)

        try:
            style.theme_use("default")
        except Exception:
            pass

        style.configure(
            "Treeview",
            background=t["bg_panel"],
            foreground=t["fg_text"],
            fieldbackground=t["bg_panel"],
            borderwidth=0,
            rowheight=26,
        )
        style.map(
            "Treeview",
            background=[("selected", t["accent"])],
            foreground=[("selected", t["list_select_fg"])],
        )

        style.configure(
            "Treeview.Heading",
            background=t["bg_header"],
            foreground=t["fg_text"],
            relief="flat",
            borderwidth=0,
            padding=(8, 6),
        )
        style.map(
            "Treeview.Heading",
            background=[("active", t["accent_hover"])],
            foreground=[("active", "#ffffff")],
        )

        # Scrollbar colors:
        # gutter/trough = grey
        # thumb normal  = grey
        # thumb hover   = blue
        if self.dark_mode_var.get():
            scrollbar_trough = "#3a3a3a"
            scrollbar_thumb = "#5a5a5a"
        else:
            scrollbar_trough = "#d4d4d4"
            scrollbar_thumb = "#a8a8a8"

        scrollbar_hover = t["accent"]

        style.configure(
            "Vertical.TScrollbar",
            background=scrollbar_thumb,
            troughcolor=scrollbar_trough,
            borderwidth=0,
            arrowcolor=t["fg_text"],
            relief="flat",
            gripcount=0,
        )
        style.map(
            "Vertical.TScrollbar",
            background=[
                ("active", scrollbar_hover),
                ("pressed", scrollbar_hover),
            ],
            arrowcolor=[
                ("active", "#ffffff"),
                ("pressed", "#ffffff"),
            ],
        )

        style.configure(
            "Horizontal.TScrollbar",
            background=scrollbar_thumb,
            troughcolor=scrollbar_trough,
            borderwidth=0,
            arrowcolor=t["fg_text"],
            relief="flat",
            gripcount=0,
        )
        style.map(
            "Horizontal.TScrollbar",
            background=[
                ("active", scrollbar_hover),
                ("pressed", scrollbar_hover),
            ],
            arrowcolor=[
                ("active", "#ffffff"),
                ("pressed", "#ffffff"),
            ],
        )

        # Keep alias for any existing references
        style.configure(
            "Dark.Vertical.TScrollbar",
            background=scrollbar_thumb,
            troughcolor=scrollbar_trough,
            borderwidth=0,
            arrowcolor=t["fg_text"],
            relief="flat",
            gripcount=0,
        )
        style.map(
            "Dark.Vertical.TScrollbar",
            background=[
                ("active", scrollbar_hover),
                ("pressed", scrollbar_hover),
            ],
            arrowcolor=[
                ("active", "#ffffff"),
                ("pressed", "#ffffff"),
            ],
        )

        self._tree_colors = dict(t)

    def _update_graphs(self):


        target_len = 60
        if hasattr(self, "graph_seconds_var"):
            try:
                target_len = int(self.graph_seconds_var.get())
            except Exception:
                target_len = 60

        with self._state_lock:
            self.cpu_history = self._resize_history(self.cpu_history, target_len)
            self.ram_history = self._resize_history(self.ram_history, target_len)
            self._ensure_disk_histories(target_len)
            self._ensure_network_histories(target_len)
            self._ensure_gpu_histories(target_len)


        if not hasattr(self, "graph_lines"):
            return

        x_data = list(range(target_len))
        xticks = self._graph_x_ticks_for_window(target_len)

        for i, line in enumerate(self.graph_lines):
            selected = "CPU"
            if hasattr(self, "graph_option_vars") and i < len(self.graph_option_vars):
                selected = self.graph_option_vars[i].get().strip()

            data = self._get_graph_data_for_selection(selected, target_len)

            # Choose graph color based on data source
            color = "#4da3ff"  # CPU default (blue)

            if selected == "Memory":
                color = "#1b3f8b"  # dark blue

            elif selected in getattr(self, "disk_history_by_label", {}):
                color = "#2ecc71"  # green

            elif selected in getattr(self, "network_history_by_label", {}):
                color = "#ff69b4"  # pink

            elif selected in getattr(self, "gpu_history_by_label", {}):
                color = "#9b59b6"  # purple

            line.set_color(color)
            line.set_xdata(x_data)
            line.set_ydata(data)

            if i < len(self.graph_axes):
                ax = self.graph_axes[i]
                ax.set_xlim(0, max(0, target_len - 1))
                ax.set_xticks(xticks)

                y_color = self._theme["fg_text"] if hasattr(self, "_theme") else "#e6e6e6"

                if self._is_network_selection(selected):
                    axis_max = self._nice_network_axis_max(data)
                    yticks = self._network_y_ticks(axis_max)

                    ax.set_ylim(0, axis_max)
                    ax.set_yticks(yticks)
                    ax.set_yticklabels(
                        [self._format_network_axis_label(v) for v in yticks],
                        color=y_color
                    )
                    ax.tick_params(axis="y", colors=y_color, labelsize=8, length=0)
                else:
                    ax.set_ylim(0, 100)
                    ax.set_yticks([0, 25, 50, 75, 100])
                    ax.set_yticklabels(["0", "25", "50", "75", "100"], color=y_color)
                    ax.tick_params(axis="y", colors=y_color, labelsize=8, length=0)

                ax.set_xticklabels([])
                ax.tick_params(axis="x", labelsize=0, length=0)

            if hasattr(self, "graph_title_labels") and i < len(self.graph_title_labels):
                self.graph_title_labels[i].configure(
                    text=self._get_graph_title_for_selection(i)
                )

        for canvas in getattr(self, "graph_canvas_widgets", []):
            canvas.draw_idle()
                
    def _set_status_color(self, color):
        requested = str(color or "").lower().strip()

        neutral_colors = {
            "",
            "black",
            "#000",
            "#000000",
            "white",
            "#fff",
            "#ffffff",
            "#e6e6e6",
            "#111111",
        }

        if requested in neutral_colors:
            final_color = self._get_default_status_color()
        else:
            final_color = color

        self.status_col = final_color

        self.cpu_usage_label.configure(text_color=final_color)
        self.freq_label.configure(text_color=final_color)
        self.temp_label.configure(text_color=final_color)
        self.mem_label.configure(text_color=final_color)
        self.status_label.configure(text_color=final_color)

        if hasattr(self, "pause_status_label"):
            self.pause_status_label.configure(text_color=final_color)


    def _sort_disk_treeview(self, col, reverse):
        self.disk_sort_col = col
        self.disk_sort_reverse = reverse
        self._apply_disk_filter()

    def _on_process_double_click(self, _evt=None):
        sel = self.proc_tree.selection()
        if not sel:
            return

        values = self.proc_tree.item(sel[0], "values")
        row = dict(zip(self.proc_tree["columns"], values))

        exe = str(row.get("exe", "")).strip()
        path = str(row.get("path", "")).strip()

        exe = (exe or "").strip()
        path = (path or "").strip()

        if not exe or not path or exe == "---":
            return

        norm = os.path.normpath(path)
        name = os.path.basename(norm).lower()

        if not norm.lower().endswith(".exe"):
            self.log(f"DBLCLICK: not an exe path -> {norm}")
            return

        already = any(p.lower() == norm.lower() for p in self.watch_paths)
        if already:
            self.log(f"DBLCLICK: already watched -> {norm}")
            try:
                messagebox.showinfo("Already watched", f"Already watching:\n{norm}")
            except Exception:
                pass
            return

        self.watch_paths.append(norm)
        self.watch_names.add(name)
        self._render_watchlist()
        self._save_now()

        self.log(f"DBLCLICK: added to watched list -> {norm} (match name: {name})")

        if self.auto_mode.get():
            self._schedule_refresh(0)

    def _on_process_right_click(self, event):
        row_id = self.proc_tree.identify_row(event.y)
        region = self.proc_tree.identify("region", event.x, event.y)

        if not row_id or region != "cell":
            return

        self.proc_tree.selection_set(row_id)
        self.proc_tree.focus(row_id)

        values = self.proc_tree.item(row_id, "values")
        if not values:
            return

        col_names = self.proc_tree["columns"]
        row = dict(zip(col_names, values))

        exe = str(row.get("exe", "")).strip()
        cores = str(row.get("cores", "")).strip()
        cpu_total = str(row.get("cpu_total", "")).strip()
        threads = str(row.get("threads", "")).strip()
        memory = str(row.get("memory", "")).strip()
        path = str(row.get("path", "")).strip()

        if not exe or exe == "---":
            return

        self._show_process_action_window(
            exe_name=exe,
            row_id=row_id,
            cores=cores,
            cpu_total=cpu_total,
            threads=threads,
            memory=memory,
            path=path,
        )



    def _show_process_action_window(self, exe_name, row_id, cores, cpu_total, threads, memory, path):
        win = ctk.CTkToplevel(self)
        win.title(exe_name if exe_name else "Process")
        win.transient(self)
        win.resizable(False, False)

        outer = ctk.CTkFrame(win)
        outer.pack(fill="both", expand=True, padx=12, pady=12)

        title = ctk.CTkLabel(
            outer,
            text="Details",
            anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        title.pack(fill="x", pady=(6, 10), padx=10)

        details = ctk.CTkFrame(outer)
        details.pack(fill="x", expand=True, padx=10, pady=(0, 10))

        def add_detail(label_text, value_text):
            row = ctk.CTkFrame(details, fg_color="transparent")
            row.pack(fill="x", pady=2, padx=8)

            ctk.CTkLabel(row, text=label_text, width=90, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=value_text, anchor="w").pack(side="left", fill="x", expand=True)

        add_detail("EXE", exe_name)
        add_detail("Cores", cores)
        add_detail("CPU %", cpu_total)
        add_detail("Threads", threads)
        add_detail("Memory", memory)
        add_detail("Path", path if path else "(No path)")

        def on_add_watch():
            try:
                self._add_watch_exe_from_path(path)
                if self.auto_mode.get():
                    self._schedule_refresh(0)
            except Exception as e:
                messagebox.showerror("Add to watched failed", str(e), parent=win)

        def on_add_blacklist():
            try:
                self._add_blacklist_exe_from_path(path)
                if self.auto_mode.get():
                    self._schedule_refresh(0)
            except Exception as e:
                messagebox.showerror("Add to blacklist failed", str(e), parent=win)

        btns = ctk.CTkFrame(outer, fg_color="transparent")
        btns.pack(fill="x", padx=10, pady=(2, 6))

        ctk.CTkButton(
            btns,
            text="End task",
            command=lambda: self._end_task_from_dialog(win, exe_name, path),
        ).pack(side="left")

        ctk.CTkButton(
            btns,
            text="Go to path",
            command=lambda: self._go_to_path(path),
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btns,
            text="End task then Go to path",
            command=lambda: self._end_task_then_go_to_path(win, exe_name, path),
        ).pack(side="left")

        second_row = ctk.CTkFrame(outer, fg_color="transparent")
        second_row.pack(fill="x", padx=10, pady=(0, 6))

        ctk.CTkButton(
            second_row,
            text="Add EXE to Watched",
            command=on_add_watch,
        ).pack(side="left")

        ctk.CTkButton(
            second_row,
            text="Add EXE to Blacklist",
            command=on_add_blacklist,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            second_row,
            text="Close",
            command=win.destroy,
            fg_color="#444444",
            hover_color="#555555",
        ).pack(side="right")

        try:
            win.update_idletasks()
            x = self.winfo_rootx() + 120
            y = self.winfo_rooty() + 120
            win.geometry(f"+{x}+{y}")
        except Exception:
            pass


    def _sort_treeview(self, col, reverse):
        self.sort_col = col
        self.sort_reverse = reverse
        self._apply_process_filter()

    def _set_status(self, msg: str):
        self.status_var.set(msg)
        self.update_idletasks()

    def _render_watchlist(self):
        self.watch_list.delete(0, tk.END)
        for p in self.watch_paths:
            self.watch_list.insert(tk.END, p)

    def _render_blacklist(self):
        if not hasattr(self, "blacklist_list"):
            return

        self.blacklist_list.delete(0, tk.END)

        for p in self.blacklist_paths:
            self.blacklist_list.insert(tk.END, p)

    def _apply_process_filter(self):
        filtered = self._get_filtered_process_rows()
        sorted_rows = self._sort_process_rows(filtered)
        self._render_process_rows(sorted_rows)

    def _render_process_rows(self, rows):
        for iid in self.proc_tree.get_children():
            self.proc_tree.delete(iid)

        for r in rows:
            self.proc_tree.insert(
                "",
                "end",
                values=self._build_process_row_values(r),
                tags=self._get_process_row_tags(r),
            )

    def _build_process_row_values(self, r):
        exe_name = r["exe"]
        cpu_val = float(r.get("cpu", 0) or 0.0)
        threads = int(r.get("threads", 0) or 0)
        mem_bytes = int(r.get("memory", 0) or 0)

        cores_used = cpu_val / 100.0
        cpu_total_pct = cpu_val / float(self.logical_cpu_count)

        cores_display = f"{cores_used:.2f}"
        cpu_total_display = f"{cpu_total_pct:.1f}%"
        threading_display = "Single" if threads == 1 else "Multi"

        if mem_bytes >= 1024**3:
            memory_display = f"{mem_bytes / (1024**3):.2f} GB"
        else:
            memory_display = f"{mem_bytes / (1024**2):.0f} MB"

        return (
            exe_name,
            cores_display,
            cpu_total_display,
            threads,
            memory_display,
            threading_display,
            r["path"],
        )

    def _get_process_row_tags(self, r):
        exe_lower = r["exe"].lower()
        cpu_val = float(r.get("cpu", 0) or 0.0)
        threshold = self.AUTO_DETECT_THRESHOLD

        tags = ()

        if exe_lower in self.heartbeat:
            tags = ("heartbeat",)
        elif exe_lower not in self.exclude_list and cpu_val >= threshold:
            tags = ("heavy",)

        if not exe_lower.endswith(".exe"):
            tags = tags + ("notexe",)

        return tags
    


    def _open_plan_config_window(self):
        win = ctk.CTkToplevel(self)
        win.title("Configure plans")
        win.transient(self)
        win.resizable(False, False)

        outer = ctk.CTkFrame(win)
        outer.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(
            outer,
            text="Configure plans",
            anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(fill="x", padx=10, pady=(8, 10))

        body = ctk.CTkFrame(outer, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(body, text="Default low performance plan", anchor="w").grid(
            row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 6)
        )
        ctk.CTkLabel(body, text="Default high performance plan", anchor="w").grid(
            row=0, column=1, sticky="ew", padx=(8, 0), pady=(0, 6)
        )

        low_list = tk.Listbox(body, exportselection=False, height=8)
        low_list.grid(row=1, column=0, sticky="nsew", padx=(0, 8))

        high_list = tk.Listbox(body, exportselection=False, height=8)
        high_list.grid(row=1, column=1, sticky="nsew", padx=(8, 0))

        self.plan_config_low_list = low_list
        self.plan_config_high_list = high_list

        for s in self.power_schemes:
            label = s["name"]
            if s["guid"] == self.balanced_guid:
                label += "  (Balanced)"
            if s["active"]:
                label += "  [ACTIVE]"
            low_list.insert(tk.END, label)
            high_list.insert(tk.END, label)

        def select_guid(lb, guid):
            for idx, s in enumerate(self.power_schemes):
                if s["guid"] == guid:
                    lb.selection_clear(0, tk.END)
                    lb.selection_set(idx)
                    lb.see(idx)
                    return

        select_guid(low_list, self.default_low_guid.get())
        select_guid(high_list, self.default_high_guid.get())

        if hasattr(self, "_apply_listbox_theme"):
            self._apply_listbox_theme()
        
        def guid_from(lb):
            sel = lb.curselection()
            if not sel:
                return None
            idx = sel[0]
            if 0 <= idx < len(self.power_schemes):
                return self.power_schemes[idx]["guid"]
            return None

        def on_save():
            low_guid = guid_from(low_list)
            high_guid = guid_from(high_list)

            try:
                self._save_configured_plans(low_guid, high_guid)
                on_close()
            except Exception as e:
                messagebox.showerror("Configure plans", str(e), parent=win)

        def on_close():
            self.plan_config_low_list = None
            self.plan_config_high_list = None
            try:
                win.destroy()
            except Exception:
                pass
            
        btns = ctk.CTkFrame(outer, fg_color="transparent")
        btns.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkButton(btns, text="Save", command=on_save).pack(side="left")
        ctk.CTkButton(btns, text="Close", command=on_close).pack(side="right")
        
######################## move 
# 
