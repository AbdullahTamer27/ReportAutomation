"""Talos — entry point.

Two tabs:
  1. Interval Generator  (existing tool, unchanged behavior)
  2. Automation Report   (Word template + Excel data + working dir → one report)

Run from the project root:  python -m well_tools.main
"""

from tkinter import ttk

from .ui.dnd import make_root
from .ui.interval_tab import IntervalTab
from .ui.report_tab import ReportTab


def main():
    root, dnd_enabled = make_root()
    root.title("Talos")
    root.geometry("820x780")

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True)

    interval_frame = ttk.Frame(notebook)
    report_frame = ttk.Frame(notebook)
    notebook.add(interval_frame, text="Interval Generator")
    notebook.add(report_frame, text="Automation Report")

    IntervalTab(interval_frame, dnd_enabled)
    ReportTab(report_frame, dnd_enabled)

    root.mainloop()


if __name__ == "__main__":
    main()
