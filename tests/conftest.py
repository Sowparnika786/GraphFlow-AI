import os
import sys

# Add api directory to PYTHONPATH
api_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "api"))
if api_path not in sys.path:
    sys.path.insert(0, api_path)
