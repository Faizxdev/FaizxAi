import os, sys

# Works regardless of working directory or Python path
bot = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "bot.py")
os.chdir(os.path.dirname(os.path.abspath(__file__)))  # ensure cwd = project root
os.execv(sys.executable, [sys.executable, bot])
