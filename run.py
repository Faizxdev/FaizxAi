"""Root entry point — works regardless of working directory."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from src.bot import main
main()
