"""
Executable entry point for `python3 -m linux_rufus`.
"""

import sys
from linux_rufus.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
