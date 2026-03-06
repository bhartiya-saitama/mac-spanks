# app.py
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
        self.minsize(520, 700)  # narrower minimum is ok now

        self.config_path = os.path.join(os.path.dirname(__file__), "config.json")
        self.cfg = ConfigManager(self.config_path)

        self.detector = None
        self.log_q = queue.Queue()

        self.sound_var = tk.StringVar()
        self.threshold_var = tk.DoubleVar()
        self.cooldown_var = tk.DoubleVar()
        self.sleep_var = tk.DoubleVar()

        self._advanced_widgets = []

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
        # Row 1: label + combobox (no buttons here, so it never disappears)
        row1 = ttk.Frame(self.general_tab)
        row1.pack(fill="x", pady=(0, 8))

        ttk.Label(row1, text="Sound:").pack(side="left")

        self.sound_combo = ttk.Combobox(row1, textvariable=self.sound_var, state="readonly")
        self.sound_combo.pack(side="left", padx=10, fill="x", expand=True)
        self.sound_combo.bind("<<ComboboxSelected>>", self.on_sound_selected)

        # Row 2: buttons (always visible even on narrow windows)
        row2 = ttk.Frame(self.general_tab)
        row2.pack(fill="x", pady=(0, 6))

        self.add_sound_btn = ttk.Button(row2, text="Add new sound", command=self.on_add_sound)
        self.add_sound_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.remove_sound_btn = ttk.Button(row2, text="Remove sound", command=self.on_remove_sound)
        self.remove_sound_btn.pack(side="left", fill="x", expand=True)

    def _build_advanced_tab(self):
        self._add_param_row("Threshold:", self.threshold_var, 0.0, 1.5)
        self._add_param_row("Cooldown (in sec):", self.cooldown_var, 0.0, 3.0)
        self._add_param_row("Sleep time (in sec):", self.sleep_var, 0.01, 3.0)

        btn_row = ttk.Frame(self.advanced_tab)
        btn_row.pack(fill="x", pady=(8, 0))
        default_btn = ttk.Button(btn_row, text="Default", command=self.on_reset_defaults)
        default_btn.pack()
        self._advanced_widgets.append(default_btn)

    def _add_param_row(self, label, var, from_, to):
        frame = ttk.Frame(self.advanced_tab)
        frame.pack(fill="x", pady=6)

        lbl = ttk.Label(frame, text=label, width=18)
        lbl.pack(side="left")
        self._advanced_widgets.append(lbl)

        entry = ttk.Entry(frame, textvariable=var, width=10)
        entry.pack(side="left", padx=(0, 10))
        entry.bind("<Return>", lambda e: self.on_advanced_change())
        entry.bind("<FocusOut>", lambda e: self._format_and_apply(var))
        self._advanced_widgets.append(entry)

        scale = ttk.Scale(
            frame,
            variable=var,
            from_=from_,
            to=to,
            orient="horizontal",
            command=lambda _v, v=var: self._on_scale_change(v),
        )
        scale.pack(side="left", fill="x", expand=True)
        self._advanced_widgets.append(scale)

        apply_btn = ttk.Button(frame, text="Apply", command=self.on_advanced_change)
        apply_btn.pack(side="left", padx=(10, 0))
        self._advanced_widgets.append(apply_btn)

    # ---------------- Config/UI sync ----------------
    def _load_vars_from_cfg(self):
        dv = self.cfg.get_default_values()
        av = self.cfg.get_active_values()

        self._sound_paths = list(dv.hit_sound_list)
        display_names = [os.path.basename(p) for p in self._sound_paths]
        self.sound_combo["values"] = display_names

        if self._sound_paths:
            if av.hit_sound in self._sound_paths:
                idx = self._sound_paths.index(av.hit_sound)
            else:
                idx = 0
                # keep config consistent if active points to missing file
                self.cfg.set_active_sound(self._sound_paths[0])

            self.sound_combo.current(idx)
            self.sound_var.set(display_names[idx])
            self.remove_sound_btn.configure(state="normal")
        else:
            self.sound_combo.set("")
            self.sound_var.set("")
            self.remove_sound_btn.configure(state="disabled")

        self.threshold_var.set(round(av.threshold, 2))
        self.cooldown_var.set(round(av.cooldown, 2))
        self.sleep_var.set(round(av.sleep_time, 2))

    def _current_params(self) -> RuntimeParams:
        idx = self.sound_combo.current()
        hit_sound = self._sound_paths[idx] if (0 <= idx < len(self._sound_paths)) else ""

        return RuntimeParams(
            threshold=round(float(self.threshold_var.get()), 2),
            cooldown=round(float(self.cooldown_var.get()), 2),
            sleep_time=round(float(self.sleep_var.get()), 2),
            hit_sound=hit_sound,
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
        idx = self.sound_combo.current()
        if 0 <= idx < len(self._sound_paths):
            self.cfg.set_active_sound(self._sound_paths[idx])
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
        self._load_vars_from_cfg()

        if self.detector:
            self.detector.update_params(self._current_params())

    def on_remove_sound(self):
        idx = self.sound_combo.current()
        if not (0 <= idx < len(self._sound_paths)):
            return

        full_path = self._sound_paths[idx]
        name = os.path.basename(full_path)

        if not messagebox.askyesno("Remove sound", f"Remove '{name}' from the list?"):
            return

        self.cfg.remove_sound(full_path)
        self._load_vars_from_cfg()

        if self.detector:
            # If currently running, update to whatever new active sound is
            self.detector.update_params(self._current_params())

    def _format_and_apply(self, var):
        try:
            val = round(float(var.get()), 2)
        except Exception:
            messagebox.showerror("Invalid value", "Please enter a valid number.")
            self._load_vars_from_cfg()
            return
        var.set(val)
        self.on_advanced_change()

    def _on_scale_change(self, var):
        try:
            var.set(round(float(var.get()), 2))
        except Exception:
            pass

    def on_advanced_change(self):
        try:
            self.cfg.set_active_advanced(
                threshold=round(float(self.threshold_var.get()), 2),
                cooldown=round(float(self.cooldown_var.get()), 2),
                sleep_time=round(float(self.sleep_var.get()), 2),
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

    # ---------------- Start/Stop + disable advanced while running ----------------
    def _set_advanced_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for w in self._advanced_widgets:
            try:
                w.configure(state=state)
            except Exception:
                pass

    def on_start(self):
        # Format values to 2 decimals and persist
        self._format_and_apply(self.threshold_var)
        self._format_and_apply(self.cooldown_var)
        self._format_and_apply(self.sleep_var)

        # Save active sound (full path)
        idx = self.sound_combo.current()
        if 0 <= idx < len(self._sound_paths):
            self.cfg.set_active_sound(self._sound_paths[idx])

        params = self._current_params()
        if not params.hit_sound:
            messagebox.showerror("No sound selected", "Please select or add a sound first.")
            return

        self.detector = Detector(params, log_callback=self.log)
        self.detector.start()

        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self._set_advanced_enabled(False)

        # Optional: also prevent add/remove while running
        self.add_sound_btn.configure(state="disabled")
        self.remove_sound_btn.configure(state="disabled")

    def on_stop(self):
        if self.detector:
            self.detector.stop()
            self.detector = None

        self.clear_console()

        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self._set_advanced_enabled(True)

        # Re-enable sound list editing
        self.add_sound_btn.configure(state="normal")
        # remove depends on whether list has items
        self.remove_sound_btn.configure(state="normal" if getattr(self, "_sound_paths", []) else "disabled")


if __name__ == "__main__":
    App().mainloop()