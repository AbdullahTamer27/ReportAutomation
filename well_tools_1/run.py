"""Entry point for PyInstaller / double-click launching.

Lives next to the `well_tools` package so its relative imports resolve.
Run the app with:  python run.py
"""

from well_tools.main import main

if __name__ == "__main__":
    main()
