import os, sys, subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

# ── Auto-updater ──────────────────────────────────────────────────────────────
def run(cmd, **kw):
    print(f"[updater] $ {' '.join(cmd)}")
    return subprocess.run(cmd, **kw)

print("[updater] Checking for updates from GitHub...")

# Only pull if this is a git repo
if os.path.isdir(os.path.join(ROOT, ".git")):
    result = run(["git", "pull", "--rebase", "origin", "main"],
                 capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[updater] {result.stdout.strip() or 'Already up to date.'}")
    else:
        print(f"[updater] git pull failed (offline?): {result.stderr.strip()}")
else:
    print("[updater] No .git folder — skipping pull (zip deploy mode)")

# Always re-install requirements in case new deps were added
req = os.path.join(ROOT, "requirements.txt")
if os.path.exists(req):
    print("[updater] Installing/updating requirements...")
    run([sys.executable, "-m", "pip", "install", "-r", req, "-q", "--upgrade"])

# ── Launch bot ────────────────────────────────────────────────────────────────
bot = os.path.join(ROOT, "src", "bot.py")
print(f"[updater] Starting bot: {bot}\n{'─'*50}")
os.execv(sys.executable, [sys.executable, bot])
