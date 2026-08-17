"""
Root entry point forwarding execution to /backtester/main.py.
Allows running 'python main.py' from root or 'python backtester/main.py'.
"""

import os
import sys

# Add backtester directory to Python path
base_dir = os.path.dirname(os.path.abspath(__file__))
backtester_dir = os.path.join(base_dir, "backtester")
if backtester_dir not in sys.path:
    sys.path.insert(0, backtester_dir)

from backtester.main import main

if __name__ == "__main__":
    main()
