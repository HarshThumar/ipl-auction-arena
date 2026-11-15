"""Root entry point for build_decision_dataset."""
import sys
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).resolve().parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from scripts.build_decision_dataset import main

if __name__ == "__main__":
    main()
