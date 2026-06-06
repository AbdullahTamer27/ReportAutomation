"""Tab 2 — Automation Report.

Inputs: Word template (.docx) + Excel data workbook (.xlsx/.xlsm) + working
directory. Produces one .docx report with images and tables. All heavy lifting
lives in report.report_builder; this file is only the UI.
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .dnd import DND_FILES, parse_drop_data
from ..report.report_builder import build_automation_report, ReportInputError


class ReportTab:
    def __init__(self, parent, dnd_enabled):
        self.parent = parent
        self.dnd_enabled = dnd_enabled

        self.word_template_path = None
        self.excel_data_path = None
        self.working_dir = None

        self.container = ttk.Frame(parent)
        self.container.pack(fill="both", expand=True, padx=10, pady=10)

        self.setup_ui()

    def setup_ui(self):
        info_frame = ttk.LabelFrame(self.container, text="Instructions")
        info_frame.pack(fill="x", padx=10, pady=5)
        instructions = ("1. Load the Word template (.docx) — layout / letterhead for the report.\n"
                        "2. Load the Excel data workbook (.xlsx/.xlsm) — tables to pull in.\n"
                        "3. Choose the working directory — images to embed live here, and the\n"
                        "   finished report is saved here.\n"
                        "4. Click 'Generate Report' — one .docx with images and tables is produced.")
        ttk.Label(info_frame, text=instructions, justify="left").pack(padx=10, pady=10)

        # Step 1 — Word template
        word_frame = ttk.LabelFrame(self.container, text="Step 1 — Word Template (.docx)")
        word_frame.pack(fill="x", padx=10, pady=5)
        self.word_label = ttk.Label(word_frame, text="No Word template loaded",
                                    foreground="gray", font=("Arial", 10))
        self.word_label.pack(pady=5)
        ttk.Button(word_frame, text="Load Word Template",
                   command=self.load_word_template).pack(pady=5)

        # Step 2 — Excel data
        excel_frame = ttk.LabelFrame(self.container, text="Step 2 — Excel Data (.xlsx/.xlsm)")
        excel_frame.pack(fill="x", padx=10, pady=5)
        self.excel_label = ttk.Label(excel_frame, text="No Excel data loaded",
                                     foreground="gray", font=("Arial", 10))
        self.excel_label.pack(pady=5)
        ttk.Button(excel_frame, text="Load Excel Data",
                   command=self.load_excel_data).pack(pady=5)

        # Step 3 — Working directory
        dir_frame = ttk.LabelFrame(self.container, text="Step 3 — Working Directory")
        dir_frame.pack(fill="x", padx=10, pady=5)
        self.dir_label = ttk.Label(dir_frame, text="No working directory selected",
                                   foreground="gray", font=("Arial", 10))
        self.dir_label.pack(pady=5)
        ttk.Button(dir_frame, text="Choose Working Directory",
                   command=self.choose_working_dir).pack(pady=5)

        # Review panel — only important items show here (problems & data flags)
        preview_frame = ttk.LabelFrame(self.container, text="Review")
        preview_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.preview = tk.Text(preview_frame, height=12, wrap="word", font=("Courier", 9))
        self.preview.pack(fill="both", expand=True)
        preview_scroll = ttk.Scrollbar(preview_frame, command=self.preview.yview)
        preview_scroll.pack(side="right", fill="y")
        self.preview.config(yscrollcommand=preview_scroll.set)

        self.generate_btn = ttk.Button(self.container, text="Step 4 — Generate Report",
                                       command=self.generate_report)
        self.generate_btn.pack(pady=10)

        if self.dnd_enabled:
            self._setup_drag_and_drop(word_frame, excel_frame, dir_frame)
            self.word_label.config(text="No Word template loaded  (or drag & drop here)")
            self.excel_label.config(text="No Excel data loaded  (or drag & drop here)")
            self.dir_label.config(text="No working directory selected  (or drag a folder here)")

    # ---- Drag & drop ----

    def _setup_drag_and_drop(self, word_frame, excel_frame, dir_frame):
        for widget in (word_frame, excel_frame, dir_frame, self.container):
            widget.drop_target_register(DND_FILES)
        word_frame.dnd_bind('<<Drop>>', self._on_drop_word)
        excel_frame.dnd_bind('<<Drop>>', self._on_drop_excel)
        dir_frame.dnd_bind('<<Drop>>', self._on_drop_dir)
        self.container.dnd_bind('<<Drop>>', self._on_drop_smart)

    def _on_drop_word(self, event):
        paths = parse_drop_data(event.data)
        if not paths:
            return
        path = paths[0]
        if not path.lower().endswith('.docx'):
            messagebox.showwarning("Wrong File Type",
                f"Expected a Word .docx file, got:\n{os.path.basename(path)}")
            return
        self.load_word_template(path)

    def _on_drop_excel(self, event):
        paths = parse_drop_data(event.data)
        if not paths:
            return
        path = paths[0]
        if not path.lower().endswith(('.xlsx', '.xlsm')):
            messagebox.showwarning("Wrong File Type",
                f"Expected an Excel file (.xlsx or .xlsm), got:\n{os.path.basename(path)}")
            return
        self.load_excel_data(path)

    def _on_drop_dir(self, event):
        paths = parse_drop_data(event.data)
        if not paths:
            return
        path = paths[0]
        if not os.path.isdir(path):
            messagebox.showwarning("Wrong Type",
                f"Expected a folder, got:\n{os.path.basename(path)}")
            return
        self.choose_working_dir(path)

    def _on_drop_smart(self, event):
        for path in parse_drop_data(event.data):
            low = path.lower()
            if low.endswith('.docx'):
                self.load_word_template(path)
            elif low.endswith(('.xlsx', '.xlsm')):
                self.load_excel_data(path)
            elif os.path.isdir(path):
                self.choose_working_dir(path)

    # ---- Loading ----

    def load_word_template(self, file_path=None):
        if file_path is None:
            file_path = filedialog.askopenfilename(
                title="Select Word Template",
                filetypes=[("Word Document", "*.docx"), ("All Files", "*.*")]
            )
        if not file_path:
            return
        self.word_template_path = file_path
        self.word_label.config(text=f"✓ {os.path.basename(file_path)}", foreground="green")

    def load_excel_data(self, file_path=None):
        if file_path is None:
            file_path = filedialog.askopenfilename(
                title="Select Excel Data Workbook",
                filetypes=[("Excel Files", "*.xlsx *.xlsm"), ("All Files", "*.*")]
            )
        if not file_path:
            return
        self.excel_data_path = file_path
        self.excel_label.config(text=f"✓ {os.path.basename(file_path)}", foreground="green")

    def choose_working_dir(self, dir_path=None):
        if dir_path is None:
            dir_path = filedialog.askdirectory(title="Select Working Directory")
        if not dir_path:
            return
        self.working_dir = dir_path
        self.dir_label.config(text=f"✓ {dir_path}", foreground="green")

    # ---- Generate ----

    def _log(self, msg):
        self.preview.insert(tk.END, msg + "\n")
        self.preview.see(tk.END)
        self.preview.update_idletasks()

    def _review(self, msg):
        """A curated review item from the engine — these are what the panel shows."""
        self._review_count += 1
        self._log(msg)

    def generate_report(self):
        try:
            from ..report.report_builder import validate_inputs
            validate_inputs(self.word_template_path, self.excel_data_path, self.working_dir)
        except ReportInputError as e:
            messagebox.showwarning("Missing Input", str(e))
            return

        self.preview.delete("1.0", tk.END)
        self.generate_btn.config(state="disabled")
        self._review_count = 0
        self._log("===== REVIEW =====")

        # Run off the UI thread so the window stays responsive on large data.
        def worker():
            try:
                out = build_automation_report(
                    self.word_template_path,
                    self.excel_data_path,
                    self.working_dir,
                    review=lambda m: self.container.after(0, self._review, m),
                )
                self.container.after(0, self._on_success, out)
            except ReportInputError as e:
                self.container.after(0, self._on_error, str(e), "Missing Input")
            except PermissionError:
                self.container.after(0, self._on_error,
                    "Can't write the report — a file may be open. Close it and retry.",
                    "File Locked")
            except Exception as e:  # noqa: BLE001
                self.container.after(0, self._on_error, str(e), "Error")

        threading.Thread(target=worker, daemon=True).start()

    def _on_success(self, out_path):
        self.generate_btn.config(state="normal")
        if self._review_count == 0:
            self._log("No issues found ✓")
        self._log(f"\n✅ Report saved:\n{out_path}")
        messagebox.showinfo("Success", f"Report created:\n{os.path.basename(out_path)}")

    def _on_error(self, msg, title):
        self.generate_btn.config(state="normal")
        self._log(f"\n✗ {title}: {msg}")
        messagebox.showerror(title, msg)
