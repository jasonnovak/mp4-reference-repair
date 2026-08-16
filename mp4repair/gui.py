from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import RepairError, default_output, describe, find_untrunc, inspect_media, repair


class RepairApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("MP4 Reference Repair")
        root.geometry("820x610")
        root.minsize(700, 500)
        self.reference = tk.StringVar()
        self.damaged = tk.StringVar()
        self.output = tk.StringVar()
        self.strategy = tk.StringVar(value="auto")
        self.status = tk.StringVar(value="Ready")
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._build()
        root.after(100, self._poll)

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Repair a cut-off MP4", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="Choose a short, healthy clip made by the same camera/app with the same recording settings. Your source files are never modified.",
            wraplength=760,
        ).pack(anchor="w", pady=(4, 16))

        form = ttk.Frame(outer)
        form.pack(fill="x")
        self._file_row(form, 0, "Healthy reference", self.reference, self._choose_reference)
        self._file_row(form, 1, "Damaged video", self.damaged, self._choose_damaged)
        self._file_row(form, 2, "Repaired output", self.output, self._choose_output)
        ttk.Label(form, text="Method").grid(row=3, column=0, sticky="w", pady=7)
        ttk.Combobox(
            form,
            textvariable=self.strategy,
            values=("auto", "reference", "deep-scan", "sony-xavc", "remux"),
            state="readonly",
            width=18,
        ).grid(row=3, column=1, sticky="w", padx=8, pady=7)
        form.columnconfigure(1, weight=1)

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(12, 8))
        self.repair_button = ttk.Button(buttons, text="Repair video", command=self._start_repair)
        self.repair_button.pack(side="left")
        ttk.Button(buttons, text="Inspect damaged file", command=self._inspect).pack(side="left", padx=8)
        engine = find_untrunc()
        engine_text = f"Reference engine: {engine}" if engine else "Reference engine not installed (run install-engine.ps1)"
        ttk.Label(buttons, text=engine_text).pack(side="right")

        self.log = tk.Text(outer, height=20, wrap="word", state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, pady=(4, 8))
        ttk.Label(outer, textvariable=self.status).pack(anchor="w")

    def _file_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=7)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=7)
        ttk.Button(parent, text="Browse...", command=command).grid(row=row, column=2, pady=7)

    @staticmethod
    def _types():
        return [("MP4/MOV media", "*.mp4 *.mov *.m4v *.3gp *.m4a"), ("All files", "*.*")]

    def _choose_reference(self) -> None:
        value = filedialog.askopenfilename(title="Choose healthy reference", filetypes=self._types())
        if value:
            self.reference.set(value)

    def _choose_damaged(self) -> None:
        value = filedialog.askopenfilename(title="Choose damaged video", filetypes=self._types())
        if value:
            self.damaged.set(value)
            self.output.set(str(default_output(value)))

    def _choose_output(self) -> None:
        value = filedialog.asksaveasfilename(
            title="Save repaired video", defaultextension=".mp4", filetypes=self._types(), initialfile="repaired.mp4"
        )
        if value:
            self.output.set(value)

    def _append(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _inspect(self) -> None:
        path = self.damaged.get().strip()
        if not path:
            messagebox.showwarning("Choose a file", "Choose the damaged video first.")
            return
        try:
            self._append(describe(inspect_media(path)))
        except (RepairError, OSError) as exc:
            messagebox.showerror("Inspection failed", str(exc))

    def _start_repair(self) -> None:
        reference, damaged, output = self.reference.get().strip(), self.damaged.get().strip(), self.output.get().strip()
        if not all((reference, damaged, output)):
            messagebox.showwarning("Missing file", "Choose the reference, damaged, and output files.")
            return
        if Path(output).exists() and not messagebox.askyesno("Replace output?", f"This output already exists:\n{output}\n\nReplace it?"):
            return
        strategy = self.strategy.get()
        self.repair_button.configure(state="disabled")
        self.status.set("Repairing... large recordings may take a while")
        self._append("\nStarting repair...")

        def worker() -> None:
            try:
                result = repair(
                    reference,
                    damaged,
                    output,
                    strategy=strategy,
                    overwrite=True,
                    log=lambda line: self.events.put(("log", line)),
                )
                self.events.put(("done", result))
            except Exception as exc:  # delivered to the UI thread
                self.events.put(("error", exc))

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self._append(str(value))
                elif kind == "done":
                    self.repair_button.configure(state="normal")
                    self.status.set("Repair complete")
                    self._append(f"Repair complete: {value.output}")
                    messagebox.showinfo("Repair complete", f"Recovered video saved to:\n{value.output}")
                elif kind == "error":
                    self.repair_button.configure(state="normal")
                    self.status.set("Repair failed")
                    self._append(f"ERROR: {value}")
                    messagebox.showerror("Repair failed", str(value))
        except queue.Empty:
            pass
        self.root.after(100, self._poll)


def launch() -> None:
    root = tk.Tk()
    RepairApp(root)
    root.mainloop()
