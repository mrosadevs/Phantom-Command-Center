"""
create_shortcut.py — One-time setup: creates a Desktop shortcut for the launcher.

Run with: python create_shortcut.py

After it runs:
  1. Find "Phantom Command Center" on your Desktop
  2. Right-click it → Pin to taskbar
"""

import subprocess
import sys
from pathlib import Path

ROOT     = Path(__file__).resolve().parent
LAUNCHER = ROOT / "launcher.py"
DESKTOP  = Path.home() / "Desktop"
LNK      = DESKTOP / "Phantom Command Center.lnk"

# pythonw.exe runs Python without a console window (same dir as python.exe)
pythonw = Path(sys.executable).with_name("pythonw.exe")
if not pythonw.exists():
    pythonw = Path(sys.executable)   # fallback — will show a console

# Use PowerShell's WScript.Shell COM object to create the shortcut
ps = f"""
$ws  = New-Object -ComObject WScript.Shell
$sc  = $ws.CreateShortcut('{LNK}')
$sc.TargetPath       = '{pythonw}'
$sc.Arguments        = '"{LAUNCHER}"'
$sc.WorkingDirectory = '{ROOT}'
$sc.Description      = 'Phantom Command Center'
$sc.Save()
"""

result = subprocess.run(
    ["powershell", "-NoProfile", "-Command", ps],
    capture_output=True,
    text=True,
)

if result.returncode == 0 and LNK.exists():
    print(f"✓ Shortcut created: {LNK}")
    print()
    print("  Next steps:")
    print("  1. Go to your Desktop")
    print("  2. Right-click 'Phantom Command Center'")
    print("  3. Select 'Pin to taskbar'")
    print()
    print("  Double-clicking it will open the launcher with no console window.")
else:
    print("✗ Shortcut creation failed.")
    if result.stderr:
        print(result.stderr)
