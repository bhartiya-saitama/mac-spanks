import os
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

from detector import Detector, RuntimeParams
from config_manager import ConfigManager


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SPANK DETECTOR")
        self.geometry("720x780")
        self.minsize(680, 740)

        self.config_path = os.path.join(os.path.dirname(__file__), "config.json")
        self.cfg = ConfigManager(self.config_path)

        self.detector = None
        self.log_q = queue.Queue()

        # UI vars
        self.sound_var = tk.StringVar()
        self.threshold_var = tk.DoubleVar()
        self.cooldown_var = tk.DoubleVar()
        self.sleep_var = tk.DoubleVar()

        self._build_ui()
        self._load_vars_from_cfg()
        self.after(50, self._pump_logs)

    # ---------------- UI ----------------
    def _build_ui(self):
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        card = ttk.Frame(outer, padding=14, relief="ridge")
        card.pack(fill="x", pady=(0, 12))

        ttk.Label(card, text="SPANK DETECTOR", font=("Helvetica", 16, "bold")).pack(pady=(0, 10))

        self.nb = ttk.Notebook(card)
        self.nb.pack(fill="x", expand=False)

        self.general_tab = ttk.Frame(self.nb, padding=12)
        self.advanced_tab = ttk.Frame(self.nb, padding=12)
        self.nb.add(self.general_tab, text="General")
        self.nb.add(self.advanced_tab, text="Advanced")

        self._build_general_tab()
        self._build_advanced_tab()

        btn_row = ttk.Frame(card)
        btn_row.pack(fill="x", pady=(12, 0))

        self.start_btn = ttk.Button(btn_row, text="START", command=self.on_start)
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 10))

        self.stop_btn = ttk.Button(btn_row, text="STOP", command=self.on_stop, state="disabled")
        self.stop_btn.pack(side="left", expand=True, fill="x")

        console_frame = ttk.Frame(outer, padding=10, relief="ridge")
        console_frame.pack(fill="both", expand=True)

        self.console = ScrolledText(console_frame, height=18, wrap="word", state="disabled")
        self.console.pack(fill="both", expand=True)

        style = ttk.Style()
        try:
            style.configure("Stop.TButton", foreground="white")
            style.map("Stop.TButton",
                      background=[("active", "#b00020"), ("!disabled", "#d32f2f")],
                      foreground=[("!disabled", "white")])
        except Exception:
            pass
        self.stop_btn.configure(style="Stop.TButton")

    def _build_general_tab(self):
        row = ttk.Frame(self.general_tab)
        row.pack(fill="x", pady=(0, 10))

        ttk.Label(row, text="Sound:").pack(side="left")

        self.sound_combo = ttk.Combobox(row, textvariable=self.sound_var, state="readonly", width=55)
        self.sound_combo.pack(side="left", padx=10, fill="x", expand=True)
        self.sound_combo.bind("<<ComboboxSelected>>", self.on_sound_selected)

        ttk.Button(row, text="Add new sound", command=self.on_add_sound).pack(side="left")

    def _build_advanced_tab(self):
        self._build_param_row("Threshold:", self.threshold_var, 0.0, 1.5)
        self._build_param_row("Cooldown (in sec):", self.cooldown_var, 0.0, 3.0)
        self._build_param_row("Sleep time (in sec):", self.sleep_var, 0.01, 3.0)

        btn_row = ttk.Frame(self.advanced_tab)
        btn_row.pack(fill="x", pady=(8, 0))
        ttk.Button(btn_row, text="Default", command=self.on_reset_defaults).pack()

    def _build_param_row(self, label, var, from_, to):
        frame = ttk.Frame(self.advanced_tab)
        frame.pack(fill="x", pady=6)

        ttk.Label(frame, text=label, width=18).pack(side="left")

        entry = ttk.Entry(frame, textvariable=var, width=10)
        entry.pack(side="left", padx=(0, 10))
        entry.bind("<Return>", lambda e: self.on_advanced_change())
        entry.bind("<FocusOut>", lambda e: self.on_advanced_change())

        ttk.Scale(frame, variable=var, from_=from_, to=to, orient="horizontal").pack(side="left", fill="x", expand=True)

        ttk.Button(frame, text="Apply", command=self.on_advanced_change).pack(side="left", padx=(10, 0))

    # ---------------- State sync ----------------
    def _load_vars_from_cfg(self):
        dv = self.cfg.get_default_values()
        av = self.cfg.get_active_values()

        self.sound_combo["values"] = dv.hit_sound_list
        self.sound_var.set(av.hit_sound)

        self.threshold_var.set(av.threshold)
        self.cooldown_var.set(av.cooldown)
        self.sleep_var.set(av.sleep_time)

    def _current_params(self) -> RuntimeParams:
        return RuntimeParams(
            threshold=float(self.threshold_var.get()),
            cooldown=float(self.cooldown_var.get()),
            sleep_time=float(self.sleep_var.get()),
            hit_sound=str(self.sound_var.get()),
        )

    # ---------------- Logging ----------------
    def log(self, msg: str):
        self.log_q.put(msg)

    def _pump_logs(self):
        try:
            while True:
                msg = self.log_q.get_nowait()
                self.console.configure(state="normal")
                self.console.insert("end", msg + "\n")
                self.console.see("end")
                self.console.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(50, self._pump_logs)

    def clear_console(self):
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

    # ---------------- Handlers ----------------
    def on_sound_selected(self, event=None):
        s = self.sound_var.get()
        if s:
            self.cfg.set_active_sound(s)
            if self.detector:
                self.detector.update_params(self._current_params())

    def on_add_sound(self):
        path = filedialog.askopenfilename(
            title="Select MP3 sound",
            filetypes=[("MP3 files", "*.mp3"), ("All files", "*.*")]
        )
        if not path:
            return

        self.cfg.add_sound(path)

        # refresh UI from config manager
        self._load_vars_from_cfg()

        if self.detector:
            self.detector.update_params(self._current_params())

    def on_advanced_change(self):
        try:
            self.cfg.set_active_advanced(
                threshold=float(self.threshold_var.get()),
                cooldown=float(self.cooldown_var.get()),
                sleep_time=float(self.sleep_var.get()),
            )
        except ValueError:
            messagebox.showerror("Invalid values", "Threshold >= 0, Cooldown >= 0, Sleep time > 0")
            self._load_vars_from_cfg()
            return

        if self.detector:
            self.detector.update_params(self._current_params())

    def on_reset_defaults(self):
        self.cfg.reset_active_advanced_to_defaults()
        self._load_vars_from_cfg()
        if self.detector:
            self.detector.update_params(self._current_params())

    def on_start(self):
        # Ensure active values are in sync
        self.on_advanced_change()
        self.on_sound_selected()

        params = self._current_params()
        if not params.hit_sound:
            messagebox.showerror("No sound selected", "Please select or add a sound first.")
            return

        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        self.detector = Detector(params, log_callback=self.log)
        self.detector.start()

    def on_stop(self):
        if self.detector:
            self.detector.stop()
            self.detector = None

        self.clear_console()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")


if __name__ == "__main__":
    App().mainloop()