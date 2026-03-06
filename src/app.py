import os
import json
import queue
import tkinter as tk
from tkinter import filedialog, messagebox

import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledText

from detector import Detector, RuntimeParams
from config_manager import ConfigManager


class App(tb.Window):
    def __init__(self):
        # read persistent theme (if present) from the raw config file, default to darkly
        self.config_path = os.path.join(os.path.dirname(__file__), "config.json")
        initial_theme = self._read_theme_from_file(default="darkly")

        super().__init__(title="Spank Detector", themename=initial_theme)

        self.geometry("760x820")
        self.minsize(560, 700)

        # try to match window background
        try:
            self.configure(bg=self.style.colors.bg)
        except Exception:
            pass

        # config manager and runtime
        self.cfg = ConfigManager(self.config_path)
        self.detector = None
        self.log_q = queue.Queue()

        # UI variables
        self.sound_var = tk.StringVar()
        self.theme_var = tk.StringVar(value=initial_theme)

        # advanced values as stringvars for precise formatting in entries
        self.threshold_var = tk.StringVar()
        self.cooldown_var = tk.StringVar()
        self.sleep_var = tk.StringVar()

        # scale doublevars to sync with entries
        self.threshold_scale = tk.DoubleVar()
        self.cooldown_scale = tk.DoubleVar()
        self.sleep_scale = tk.DoubleVar()

        # widgets collection for enabling/disabling
        self._advanced_widgets = []
        self._console_text = None

        # build UI
        self._build_ui()
        self._load_vars_from_cfg()

        # initial status
        self._set_running_ui(False)

        # start pumping logs
        self.after(50, self._pump_logs)

    # ----------------- Raw theme persistence helpers -----------------
    def _read_theme_from_file(self, default: str) -> str:
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r") as f:
                    data = json.load(f)
                return data.get("ui", {}).get("theme", default)
        except Exception:
            pass
        return default

    def _persist_theme_robust(self, theme: str) -> None:
        """
        Persist theme robustly:
        - merge/write 'ui.theme' into config.json on disk
        - update ConfigManager's in-memory dict and call save() so subsequent saves keep it
        """
        # merge into disk file
        data = {}
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r") as f:
                    data = json.load(f)
        except Exception:
            data = {}

        data.setdefault("ui", {})
        data["ui"]["theme"] = theme

        try:
            with open(self.config_path, "w") as f:
                json.dump(data, f, indent=4)
        except Exception:
            pass

        # also put it into ConfigManager internal dict and save via it
        try:
            self.cfg._config.setdefault("ui", {})
            self.cfg._config["ui"]["theme"] = theme
            self.cfg.save()
        except Exception:
            pass

    # ----------------- UI Building -----------------
    def _build_ui(self):
        outer = tb.Frame(self, padding=18, bootstyle="default")
        outer.pack(fill=BOTH, expand=YES)

        # Top card
        card = tb.Frame(outer, padding=16, bootstyle="secondary")
        card.pack(fill=X, pady=(0, 12))

        header = tb.Frame(card, bootstyle="secondary")
        header.pack(fill=X)

        tb.Label(
            header,
            text="SPANK DETECTOR",
            font=("Helvetica", 18, "bold"),
            bootstyle="inverse-secondary",
        ).pack(side=LEFT, anchor=W)

        # status area (right)
        status_wrap = tb.Frame(header, bootstyle="secondary")
        status_wrap.pack(side=RIGHT, anchor=E)

        self.status_dot = tk.Canvas(status_wrap, width=12, height=12, highlightthickness=0, bd=0)
        try:
            self.status_dot.configure(bg=self.style.colors.secondary)
        except Exception:
            pass
        self._dot_id = self.status_dot.create_oval(2, 2, 10, 10, fill="#dc3545", outline="")
        self.status_dot.pack(side=LEFT, padx=(0, 8))

        self.running_badge = tb.Label(status_wrap, text="Running…", bootstyle="success", padding=(10, 4))

        tb.Label(card, text="Detect chassis taps and play a sound", bootstyle="inverse-secondary").pack(
            anchor=W, pady=(8, 12)
        )

        # Notebook (left-aligned standard tabs)
        self.nb = tb.Notebook(card, bootstyle="secondary")
        self.nb.pack(fill=X, pady=(0, 10))

        self.general_tab = tb.Frame(self.nb, padding=12, bootstyle="secondary")
        self.advanced_tab = tb.Frame(self.nb, padding=12, bootstyle="secondary")
        self.nb.add(self.general_tab, text="General")
        self.nb.add(self.advanced_tab, text="Advanced")

        # build each tab's content
        self._build_general_tab()
        self._build_advanced_tab()

        # theme row (kept under tabs for space)
        theme_row = tb.Frame(card, bootstyle="secondary")
        theme_row.pack(fill=X, pady=(6, 6))

        theme_row.columnconfigure(0, weight=1)
        theme_row.columnconfigure(1, weight=0)

        theme_holder = tb.Frame(theme_row, bootstyle="secondary")
        theme_holder.grid(row=0, column=1)

        tb.Label(theme_holder, text="Theme:", bootstyle="inverse-secondary").pack(side=LEFT, padx=(0, 10))
        themes = sorted(self.style.theme_names())
        self.theme_combo = tb.Combobox(theme_holder, values=themes, textvariable=self.theme_var, state="readonly", width=18)
        self.theme_combo.pack(side=LEFT)
        self.theme_combo.bind("<<ComboboxSelected>>", self.on_theme_change)

        # Start / Stop buttons
        btn_row = tb.Frame(card, bootstyle="secondary")
        btn_row.pack(fill=X, pady=(10, 0))

        self.start_btn = tb.Button(btn_row, text="Start", bootstyle="success", command=self.on_start)
        self.start_btn.pack(side=LEFT, expand=YES, fill=X, padx=(0, 10))

        self.stop_btn = tb.Button(btn_row, text="Stop", bootstyle="danger", command=self.on_stop, state=DISABLED)
        self.stop_btn.pack(side=LEFT, expand=YES, fill=X)

        # Console area
        console_card = tb.Frame(outer, padding=12, bootstyle="secondary")
        console_card.pack(fill=BOTH, expand=YES)

        tb.Label(console_card, text="Console", bootstyle="inverse-secondary").pack(anchor=W)
        self.console = ScrolledText(console_card, height=18, autohide=True, padding=8, font=("Menlo", 11))
        self.console.pack(fill=BOTH, expand=YES, pady=(6, 0))

        # get inner text widget and set it disabled initially
        self._console_text = self._get_console_text_widget()
        if self._console_text is not None:
            self._console_text.configure(state=DISABLED)

    def _build_general_tab(self):
        # sound dropdown row
        row1 = tb.Frame(self.general_tab, bootstyle="secondary")
        row1.pack(fill=X, pady=(0, 8))

        tb.Label(row1, text="Sound:", width=10, bootstyle="inverse-secondary").pack(side=LEFT)

        self.sound_combo = tb.Combobox(row1, textvariable=self.sound_var, state="readonly")
        self.sound_combo.pack(side=LEFT, fill=X, expand=YES)
        self.sound_combo.bind("<<ComboboxSelected>>", self.on_sound_selected)

        # buttons row
        row2 = tb.Frame(self.general_tab, bootstyle="secondary")
        row2.pack(fill=X)

        # visible outline so border shows in dark themes
        self.add_sound_btn = tb.Button(row2, text="Add new sound", bootstyle="outline-primary", command=self.on_add_sound)
        self.add_sound_btn.pack(side=LEFT, fill=X, expand=YES, padx=(0, 10))

        self.remove_sound_btn = tb.Button(row2, text="Remove sound", bootstyle="outline-primary", command=self.on_remove_sound)
        self.remove_sound_btn.pack(side=LEFT, fill=X, expand=YES)

    def _build_advanced_tab(self):
        # param rows
        self._add_param_row("Threshold", "threshold", self.threshold_var, self.threshold_scale, 0.0, 1.5)
        self._add_param_row("Cooldown (s)", "cooldown", self.cooldown_var, self.cooldown_scale, 0.0, 3.0)
        self._add_param_row("Sleep time (s)", "sleep", self.sleep_var, self.sleep_scale, 0.01, 3.0)

        # restore defaults row - visible border
        row = tb.Frame(self.advanced_tab, bootstyle="secondary")
        row.pack(fill=X, pady=(10, 0))

        default_btn = tb.Button(row, text="Restore Defaults", bootstyle="outline-primary", command=self.on_reset_defaults)
        default_btn.pack(side=LEFT)
        self._advanced_widgets.append(default_btn)

    def _add_param_row(self, label, key, entry_var: tk.StringVar, scale_var: tk.DoubleVar, from_, to):
        frame = tb.Frame(self.advanced_tab, bootstyle="secondary")
        frame.pack(fill=X, pady=6)

        tb.Label(frame, text=label, width=14, bootstyle="inverse-secondary").pack(side=LEFT)

        entry = tb.Entry(frame, textvariable=entry_var, width=10)
        entry.pack(side=LEFT, padx=(0, 10))
        entry.bind("<Return>", lambda e, k=key: self._format_and_apply_key(k))
        entry.bind("<FocusOut>", lambda e, k=key: self._format_and_apply_key(k))
        self._advanced_widgets.append(entry)

        scale = tb.Scale(frame, variable=scale_var, from_=from_, to=to)
        scale.pack(side=LEFT, fill=X, expand=YES)
        self._advanced_widgets.append(scale)

        scale.configure(command=lambda _v, k=key: self._sync_entry_from_scale(k))

        apply_btn = tb.Button(frame, text="Apply", bootstyle="outline-primary", command=self.on_advanced_change)
        apply_btn.pack(side=LEFT, padx=(10, 0))
        self._advanced_widgets.append(apply_btn)

    # ----------------- Console helpers -----------------
    def _get_console_text_widget(self):
        # newer ScrolledText wrappers expose .text, otherwise find Text child
        if hasattr(self.console, "text"):
            return self.console.text
        for child in self.console.winfo_children():
            if child.winfo_class() == "Text":
                return child
        return None

    # ----------------- Advanced rounding + sync -----------------
    def _get_scale_var(self, key: str) -> tk.DoubleVar:
        return {"threshold": self.threshold_scale, "cooldown": self.cooldown_scale, "sleep": self.sleep_scale}[key]

    def _get_entry_var(self, key: str) -> tk.StringVar:
        return {"threshold": self.threshold_var, "cooldown": self.cooldown_var, "sleep": self.sleep_var}[key]

    def _sync_entry_from_scale(self, key: str):
        sv = self._get_scale_var(key)
        ev = self._get_entry_var(key)
        ev.set(f"{round(float(sv.get()), 2):.2f}")

    def _sync_scale_from_entry(self, key: str):
        sv = self._get_scale_var(key)
        ev = self._get_entry_var(key)
        try:
            sv.set(float(ev.get()))
        except Exception:
            pass

    def _format_and_apply_key(self, key: str):
        ev = self._get_entry_var(key)
        try:
            ev.set(f"{round(float(ev.get()), 2):.2f}")
        except Exception:
            messagebox.showerror("Invalid value", "Please enter a valid number.")
            self._load_vars_from_cfg()
            return
        self._sync_scale_from_entry(key)
        self.on_advanced_change()

    # ----------------- Config sync -----------------
    def _load_vars_from_cfg(self):
        dv = self.cfg.get_default_values()
        av = self.cfg.get_active_values()

        # sounds: store full paths internally, show basenames
        self._sound_paths = list(dv.hit_sound_list)
        display = [os.path.basename(p) for p in self._sound_paths]
        self.sound_combo["values"] = display

        if self._sound_paths:
            idx = self._sound_paths.index(av.hit_sound) if av.hit_sound in self._sound_paths else 0
            if av.hit_sound not in self._sound_paths:
                self.cfg.set_active_sound(self._sound_paths[0])
            self.sound_combo.current(idx)
            self.sound_var.set(display[idx])
            self.remove_sound_btn.configure(state=NORMAL)
        else:
            self.sound_combo.set("")
            self.sound_var.set("")
            self.remove_sound_btn.configure(state=DISABLED)

        # advanced values displayed with 2 decimals
        self.threshold_var.set(f"{round(av.threshold, 2):.2f}")
        self.cooldown_var.set(f"{round(av.cooldown, 2):.2f}")
        self.sleep_var.set(f"{round(av.sleep_time, 2):.2f}")

        # sync sliders
        self.threshold_scale.set(float(self.threshold_var.get()))
        self.cooldown_scale.set(float(self.cooldown_var.get()))
        self.sleep_scale.set(float(self.sleep_var.get()))

    def _current_params(self) -> RuntimeParams:
        idx = self.sound_combo.current()
        sound = self._sound_paths[idx] if (0 <= idx < len(self._sound_paths)) else ""

        def tof(s: str, default: float) -> float:
            try:
                return round(float(s), 2)
            except Exception:
                return default

        return RuntimeParams(
            threshold=tof(self.threshold_var.get(), 0.7),
            cooldown=tof(self.cooldown_var.get(), 0.4),
            sleep_time=tof(self.sleep_var.get(), 1.0),
            hit_sound=sound,
        )

    # ----------------- Logging -----------------
    def log(self, msg: str):
        self.log_q.put(msg)

    def _pump_logs(self):
        try:
            while True:
                msg = self.log_q.get_nowait()
                if self._console_text is None:
                    continue
                self._console_text.configure(state=NORMAL)
                self._console_text.insert("end", msg + "\n")
                self._console_text.see("end")
                self._console_text.configure(state=DISABLED)
        except queue.Empty:
            pass
        self.after(50, self._pump_logs)

    def _clear_console(self):
        if self._console_text is None:
            return
        self._console_text.configure(state=NORMAL)
        self._console_text.delete("1.0", "end")
        self._console_text.configure(state=DISABLED)

    # ----------------- Running UI (badge + dot) -----------------
    def _set_running_ui(self, running: bool):
        dot_color = "#28a745" if running else "#dc3545"
        try:
            self.status_dot.itemconfig(self._dot_id, fill=dot_color)
        except Exception:
            pass

        if running:
            if not self.running_badge.winfo_ismapped():
                self.running_badge.pack(side=LEFT)
        else:
            if self.running_badge.winfo_ismapped():
                self.running_badge.pack_forget()

    # ----------------- Theme change handler -----------------
    def on_theme_change(self, event=None):
        theme = self.theme_var.get()
        if not theme:
            return

        # Close dropdown/popdown and apply theme on next tick to avoid popdown Tcl errors
        try:
            self.theme_combo.event_generate("<Escape>")
            self.focus_set()
            self.update_idletasks()
        except Exception:
            pass

        def apply_theme():
            try:
                self.style.theme_use(theme)
                try:
                    self.configure(bg=self.style.colors.bg)
                except Exception:
                    pass
                try:
                    self.status_dot.configure(bg=self.style.colors.secondary)
                except Exception:
                    pass

                # persist robustly so ConfigManager doesn't wipe the key later
                self._persist_theme_robust(theme)

            except tk.TclError as e:
                msg = str(e)
                # ignore known combobox/popdown timing errors; try to set theme anyway
                if "combobox.popdown" in msg or "popdown" in msg:
                    try:
                        self.style.theme_use(theme)
                    except Exception:
                        pass
                    finally:
                        self._persist_theme_robust(theme)
                    return
                messagebox.showerror("Theme error", f"Could not apply theme:\n{e}")
            except Exception as e:
                messagebox.showerror("Theme error", f"Could not apply theme:\n{e}")

        self.after_idle(apply_theme)

    # ----------------- Handlers: sounds, advanced -----------------
    def on_sound_selected(self, event=None):
        idx = self.sound_combo.current()
        if 0 <= idx < len(self._sound_paths):
            self.cfg.set_active_sound(self._sound_paths[idx])
            if self.detector:
                self.detector.update_params(self._current_params())

    def on_add_sound(self):
        path = filedialog.askopenfilename(title="Select MP3 sound", filetypes=[("MP3 files", "*.mp3"), ("All files", "*.*")])
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
            self.detector.update_params(self._current_params())

    def on_advanced_change(self):
        # ensure formatting and sync with sliders
        for k in ("threshold", "cooldown", "sleep"):
            ev = self._get_entry_var(k)
            try:
                ev.set(f"{round(float(ev.get()), 2):.2f}")
            except Exception:
                self._load_vars_from_cfg()
                return
            self._sync_scale_from_entry(k)

        params = self._current_params()
        try:
            self.cfg.set_active_advanced(params.threshold, params.cooldown, params.sleep_time)
        except ValueError:
            messagebox.showerror("Invalid values", "Threshold >= 0, Cooldown >= 0, Sleep time > 0")
            self._load_vars_from_cfg()
            return

        if self.detector:
            self.detector.update_params(params)

    def on_reset_defaults(self):
        self.cfg.reset_active_advanced_to_defaults()
        self._load_vars_from_cfg()
        if self.detector:
            self.detector.update_params(self._current_params())

    # ----------------- Start / Stop -----------------
    def _set_advanced_enabled(self, enabled: bool):
        disabled_flag = ["disabled"] if not enabled else ["!disabled"]
        for w in self._advanced_widgets:
            try:
                if hasattr(w, "state"):
                    w.state(disabled_flag)
                else:
                    w.configure(state=("normal" if enabled else "disabled"))
            except Exception:
                pass

    def on_start(self):
        # ensure formatted values
        for k in ("threshold", "cooldown", "sleep"):
            self._format_and_apply_key(k)

        idx = self.sound_combo.current()
        if 0 <= idx < len(self._sound_paths):
            self.cfg.set_active_sound(self._sound_paths[idx])

        params = self._current_params()
        if not params.hit_sound:
            messagebox.showerror("No sound selected", "Please select or add a sound first.")
            return

        # start detector thread/process (from your detector.py)
        self.detector = Detector(params, log_callback=self.log)
        self.detector.start()

        # UI toggles
        self.start_btn.configure(state=DISABLED)
        self.stop_btn.configure(state=NORMAL)

        self._set_advanced_enabled(False)
        self.add_sound_btn.configure(state=DISABLED)
        self.remove_sound_btn.configure(state=DISABLED)
        self.theme_combo.configure(state=DISABLED)
        # disable notebook tabs (ttk.Notebook tabs can't be disabled simply; prevent switching by binding)
        self.nb.unbind("<<NotebookTabChanged>>", None)

        self._set_running_ui(True)

    def on_stop(self):
        if self.detector:
            self.detector.stop()
            self.detector = None

        self._clear_console()

        self.start_btn.configure(state=NORMAL)
        self.stop_btn.configure(state=DISABLED)

        self._set_advanced_enabled(True)
        self.add_sound_btn.configure(state=NORMAL)
        self.remove_sound_btn.configure(state=NORMAL if getattr(self, "_sound_paths", []) else DISABLED)
        self.theme_combo.configure(state="readonly")
        # re-enable tab switching - easiest is to leave Notebook default behavior intact

        self._set_running_ui(False)

    # ----------------- small helpers -----------------
    def _get_entry_var(self, key: str) -> tk.StringVar:
        return {"threshold": self.threshold_var, "cooldown": self.cooldown_var, "sleep": self.sleep_var}[key]

    def _get_scale_var(self, key: str) -> tk.DoubleVar:
        return {"threshold": self.threshold_scale, "cooldown": self.cooldown_scale, "sleep": self.sleep_scale}[key]

    def _sync_entry_from_scale(self, key: str):
        sv = self._get_scale_var(key)
        ev = self._get_entry_var(key)
        ev.set(f"{round(float(sv.get()), 2):.2f}")

    def _sync_scale_from_entry(self, key: str):
        sv = self._get_scale_var(key)
        ev = self._get_entry_var(key)
        try:
            sv.set(float(ev.get()))
        except Exception:
            pass

    def _format_and_apply_key(self, key: str):
        ev = self._get_entry_var(key)
        try:
            ev.set(f"{round(float(ev.get()), 2):.2f}")
        except Exception:
            messagebox.showerror("Invalid value", "Please enter a valid number.")
            self._load_vars_from_cfg()
            return
        self._sync_scale_from_entry(key)
        self.on_advanced_change()

    # ----------------- Text console helpers -----------------
    def _console_insert(self, text: str):
        if self._console_text is None:
            return
        self._console_text.configure(state=NORMAL)
        self._console_text.insert("end", text)
        self._console_text.see("end")
        self._console_text.configure(state=DISABLED)

    # ----------------- end -----------------
if __name__ == "__main__":
    App().mainloop()