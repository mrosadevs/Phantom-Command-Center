"""
launcher.py — Phantom Command Center Desktop Launcher

Start, reboot, or shutdown all Phantom services from one window.

Run with: python launcher.py
Requires: pip install customtkinter
"""

import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import customtkinter as ctk

ROOT = Path(__file__).parent

# Common LM Studio install paths on Windows
LM_STUDIO_PATHS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "LM-Studio" / "LM Studio.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "LM-Studio" / "LM Studio.exe",
    Path(os.environ.get("APPDATA", "")) / "LM-Studio" / "LM Studio.exe",
    Path("C:/Program Files/LM Studio/LM Studio.exe"),
    Path("C:/Program Files (x86)/LM Studio/LM Studio.exe"),
]

# ── Colors matching the dashboard ─────────────────────────────────────────────
BG        = "#0d0d15"
BG2       = "#13131e"
BG_HEADER = "#080810"
PURPLE    = "#7b2fbe"
PURPLE_DIM = "#2d1057"
PURPLE_HOV = "#4a1a8a"
BLUE_DIM  = "#171730"
BLUE_BRD  = "#3a3aaa"
RED_DIM   = "#2a0d0d"
RED_BRD   = "#993333"
GREEN     = "#00e55a"
GREEN_DIM = "#004422"
MUTED     = "#55556a"
TEXT      = "#d8d8f0"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


class PhantomLauncher(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Phantom Launcher")
        self.geometry("460x640")
        self.resizable(False, False)
        self.configure(fg_color=BG)

        # Spawned subprocess handles
        self._procs: dict[str, subprocess.Popen | None] = {
            "Discord Bot": None,
            "Dashboard": None,
        }

        self._build_ui()
        self._start_status_thread()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=BG_HEADER, corner_radius=0, height=110)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr,
            text="⚡ PHANTOM",
            font=ctk.CTkFont("Helvetica", 32, "bold"),
            text_color=PURPLE,
        ).place(relx=0.5, rely=0.38, anchor="center")

        ctk.CTkLabel(
            hdr,
            text="COMMAND  CENTER",
            font=ctk.CTkFont("Courier", 10, "bold"),
            text_color=MUTED,
        ).place(relx=0.5, rely=0.72, anchor="center")

        # Status card
        card = ctk.CTkFrame(self, fg_color=BG2, corner_radius=14)
        card.pack(fill="x", padx=22, pady=(18, 6))

        ctk.CTkLabel(
            card,
            text="SERVICES",
            font=ctk.CTkFont("Courier", 10, "bold"),
            text_color=MUTED,
        ).pack(anchor="w", padx=18, pady=(14, 6))

        self._dots: dict[str, ctk.CTkLabel] = {}
        self._status_lbl: dict[str, ctk.CTkLabel] = {}

        rows = [
            ("Discord Bot",  "Bot process"),
            ("Dashboard",    "localhost:3000"),
            ("LM Studio",    "localhost:1234"),
        ]
        for name, detail in rows:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=5)

            dot = ctk.CTkLabel(
                row, text="●",
                font=ctk.CTkFont("Helvetica", 17),
                text_color="#2a2a44",
                width=22,
            )
            dot.pack(side="left")

            ctk.CTkLabel(
                row, text=f"  {name}",
                font=ctk.CTkFont("Helvetica", 13),
                text_color=TEXT,
            ).pack(side="left")

            lbl = ctk.CTkLabel(
                row, text="offline",
                font=ctk.CTkFont("Helvetica", 11),
                text_color=MUTED,
            )
            lbl.pack(side="right")

            self._dots[name] = dot
            self._status_lbl[name] = lbl

        ctk.CTkFrame(card, height=1, fg_color="#1e1e30").pack(fill="x", padx=18, pady=(10, 14))

        # Buttons
        btn_wrap = ctk.CTkFrame(self, fg_color="transparent")
        btn_wrap.pack(fill="x", padx=22, pady=8)

        # START
        self.btn_start = ctk.CTkButton(
            btn_wrap,
            text="▶   START ALL",
            height=68,
            font=ctk.CTkFont("Helvetica", 18, "bold"),
            fg_color=PURPLE_DIM,
            hover_color=PURPLE_HOV,
            border_color=PURPLE,
            border_width=2,
            corner_radius=12,
            command=lambda: threading.Thread(target=self._start_all, daemon=True).start(),
        )
        self.btn_start.pack(fill="x", pady=(0, 10))

        # REBOOT + SHUTDOWN side by side
        bottom_row = ctk.CTkFrame(btn_wrap, fg_color="transparent")
        bottom_row.pack(fill="x")

        self.btn_reboot = ctk.CTkButton(
            bottom_row,
            text="↺   REBOOT",
            height=56,
            font=ctk.CTkFont("Helvetica", 14, "bold"),
            fg_color=BLUE_DIM,
            hover_color="#20204a",
            border_color=BLUE_BRD,
            border_width=2,
            corner_radius=12,
            command=lambda: threading.Thread(target=self._reboot_all, daemon=True).start(),
        )
        self.btn_reboot.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_stop = ctk.CTkButton(
            bottom_row,
            text="■   SHUTDOWN",
            height=56,
            font=ctk.CTkFont("Helvetica", 14, "bold"),
            fg_color=RED_DIM,
            hover_color="#3a1010",
            border_color=RED_BRD,
            border_width=2,
            corner_radius=12,
            command=lambda: threading.Thread(target=self._shutdown_all, daemon=True).start(),
        )
        self.btn_stop.pack(side="right", fill="x", expand=True, padx=(6, 0))

        # Log
        ctk.CTkLabel(
            self,
            text="LOG",
            font=ctk.CTkFont("Courier", 10, "bold"),
            text_color=MUTED,
        ).pack(anchor="w", padx=24, pady=(16, 3))

        self.log_box = ctk.CTkTextbox(
            self,
            height=158,
            font=ctk.CTkFont("Courier", 10),
            fg_color="#07070f",
            text_color="#8080ee",
            corner_radius=12,
            border_color="#18183a",
            border_width=1,
            wrap="word",
        )
        self.log_box.pack(fill="x", padx=22, pady=(0, 22))
        self.log_box.configure(state="disabled")

        self._log("Launcher ready. Press START ALL to begin.")

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, msg: str):
        def _do():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"› {msg}\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, _do)

    # ── Status polling ────────────────────────────────────────────────────────

    def _start_status_thread(self):
        threading.Thread(target=self._status_loop, daemon=True).start()

    def _status_loop(self):
        while True:
            self._refresh_status()
            time.sleep(3)

    def _refresh_status(self):
        # Discord Bot — is our subprocess alive?
        proc = self._procs.get("Discord Bot")
        bot_alive = proc is not None and proc.poll() is None
        self._set_dot("Discord Bot", bot_alive, "running" if bot_alive else "offline")

        # Dashboard — HTTP check
        self._set_dot("Dashboard", *self._http_check("http://localhost:3000"))

        # LM Studio — HTTP check against OpenAI-compatible endpoint
        self._set_dot("LM Studio", *self._http_check("http://localhost:1234/v1/models"))

    def _http_check(self, url: str):
        try:
            urllib.request.urlopen(url, timeout=2)
            return True, "online"
        except Exception:
            return False, "offline"

    def _set_dot(self, name: str, online: bool, label: str):
        color = GREEN if online else "#2a2a44"
        text_color = "#00cc44" if online else MUTED

        def _do():
            self._dots[name].configure(text_color=color)
            self._status_lbl[name].configure(text=label, text_color=text_color)
        self.after(0, _do)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _start_all(self):
        python = sys.executable
        self._log("Starting services...")

        # Discord Bot
        proc = self._procs.get("Discord Bot")
        if proc is None or proc.poll() is not None:
            try:
                p = subprocess.Popen(
                    [python, "src/interfaces/discord_bot.py"],
                    cwd=str(ROOT),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._procs["Discord Bot"] = p
                self._log(f"Discord Bot started (PID {p.pid})")
            except Exception as e:
                self._log(f"Discord Bot error: {e}")
        else:
            self._log("Discord Bot already running.")

        # Dashboard
        proc = self._procs.get("Dashboard")
        if proc is None or proc.poll() is not None:
            try:
                p = subprocess.Popen(
                    [python, "src/dashboard/server.py"],
                    cwd=str(ROOT),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._procs["Dashboard"] = p
                self._log(f"Dashboard started (PID {p.pid})")
            except Exception as e:
                self._log(f"Dashboard error: {e}")
        else:
            self._log("Dashboard already running.")

        # LM Studio
        self._launch_lm_studio()

        self._log("Done.")

    def _launch_lm_studio(self):
        for path in LM_STUDIO_PATHS:
            if path.exists():
                try:
                    subprocess.Popen(
                        [str(path)],
                        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                    )
                    self._log("LM Studio launched.")
                    return
                except Exception as e:
                    self._log(f"LM Studio error: {e}")
                    return
        self._log("LM Studio not found in common paths — open it manually.")

    def _stop_all(self):
        self._log("Stopping services...")

        # 1. Kill any processes the launcher spawned this session
        for name, proc in list(self._procs.items()):
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=6)
                    self._log(f"{name} stopped (PID {proc.pid}).")
                except Exception:
                    try:
                        proc.kill()
                        self._log(f"{name} force-killed.")
                    except Exception as e:
                        self._log(f"{name} kill error: {e}")
        self._procs = {k: None for k in self._procs}

        # 2. Sweep for orphaned processes (started outside this launcher session)
        targets = {
            "discord_bot.py": "Discord Bot",
            "server.py":      "Dashboard",
        }
        for script, label in targets.items():
            try:
                result = subprocess.run(
                    ["wmic", "process", "where", f'CommandLine like "%{script}%"',
                     "get", "ProcessId", "/format:value"],
                    capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line.startswith("ProcessId="):
                        pid_str = line.split("=", 1)[1].strip()
                        if pid_str.isdigit() and int(pid_str) != os.getpid():
                            subprocess.run(["taskkill", "/F", "/PID", pid_str],
                                           capture_output=True)
                            self._log(f"{label} orphan killed (PID {pid_str}).")
            except Exception as e:
                self._log(f"Sweep error for {label}: {e}")

    def _shutdown_all(self):
        self._stop_all()
        self._log("All services offline.")

    def _reboot_all(self):
        self._log("Rebooting...")
        self._stop_all()
        self._log("Waiting for ports to clear...")
        time.sleep(4)
        self._start_all()
        self._log("Reboot complete.")


if __name__ == "__main__":
    app = PhantomLauncher()
    app.mainloop()
