#!/usr/bin/env python3
"""
Richard — Voice-Activated AI Assistant
Double-clap = instant workspace. No lag. No mercy.
"""

import os, sys, time, threading, subprocess
import numpy as np

# ─────────────────────────────────────────────────────────────
#  CONFIG  — tweak these if needed
# ─────────────────────────────────────────────────────────────
CLAP_THRESHOLD  = 2500      # mic amplitude to count as a clap
CLAP_WINDOW_SEC = 1.8       # max gap between two claps
COOLDOWN_SEC    = 5         # ignore claps after launch for this long

# Smallest chunk = lowest detection latency (~2.9 ms per chunk at 44100 Hz)
SAMPLE_RATE = 44100
CHUNK       = 128           # was 1024 → 8× faster detection loop

WORKSPACE_SITES = [
    "https://www.github.com",
    "https://www.linkedin.com",
    "https://chat.openai.com",
    "https://claude.ai",
]

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
STARTUP_SONG = os.path.join(
    SCRIPT_DIR,
    "The Clash - Should I Stay or Should I Go (Official Audio) - The Clash (128k).mp3"
)
# ─────────────────────────────────────────────────────────────

CYAN  = "\033[96m"; GREEN = "\033[92m"
YELL  = "\033[93m"; RED   = "\033[91m"
BOLD  = "\033[1m";  RST   = "\033[0m"
def say(m, c=CYAN): print(f"{c}{BOLD}[Richard]{RST} {m}", flush=True)


# ═════════════════════════════════════════════
#  DEPS
# ═════════════════════════════════════════════
def _check_deps():
    missing = []
    for pkg, pip in [("sounddevice","sounddevice"), ("numpy","numpy"), ("pygame","pygame")]:
        try: __import__(pkg)
        except ImportError: missing.append(pip)
    if missing:
        say(f"Missing: {' '.join(missing)}", RED)
        say(f"Fix:  pip install {' '.join(missing)}", YELL)
        sys.exit(1)

_check_deps()
import sounddevice as sd   # replaces pyaudio — lower latency, no PortAudio stutter
import pygame


# ═════════════════════════════════════════════
#  AUDIO  — pre-loaded at startup, instant play
# ═════════════════════════════════════════════
_audio_ok = False

def prewarm_audio():
    global _audio_ok
    try:
        pygame.mixer.pre_init(44100, -16, 2, 128)  # 128-frame buffer ≈ 3 ms
        pygame.mixer.init()
        if os.path.exists(STARTUP_SONG):
            pygame.mixer.music.load(STARTUP_SONG)
            _audio_ok = True
            say("🎵 Audio ready.", GREEN)
        else:
            say(f"⚠  No song at: {STARTUP_SONG}", YELL)
    except Exception as e:
        say(f"⚠  Audio init: {e}", RED)

def play_audio():
    if _audio_ok:
        try: pygame.mixer.music.play()
        except Exception: pass


# ═════════════════════════════════════════════
#  LAUNCHERS  — paths resolved ONCE at import
# ═════════════════════════════════════════════
_IS_WIN = os.name == "nt"
_IS_MAC = sys.platform == "darwin"

# ── Chrome ──────────────────────────────────
_CHROME_CANDIDATES = (
    [
        rf"C:\Program Files\Google\Chrome\Application\chrome.exe",
        rf"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ] if _IS_WIN else
    ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"] if _IS_MAC else
    ["/usr/bin/google-chrome", "/usr/bin/chromium-browser", "/usr/bin/chromium"]
)
_CHROME = next((p for p in _CHROME_CANDIDATES if os.path.exists(p)), None)

def open_browser():
    if _CHROME:
        subprocess.Popen(
            [_CHROME, "--new-window"] + WORKSPACE_SITES,
            close_fds=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    elif _IS_MAC:
        subprocess.Popen(["open"] + WORKSPACE_SITES,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif _IS_WIN:
        for url in WORKSPACE_SITES:
            subprocess.Popen(f'start "" "{url}"', shell=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        import webbrowser
        for url in WORKSPACE_SITES:
            webbrowser.open_new_tab(url)

# ── VS Code ─────────────────────────────────
_CODE_CANDIDATES = (
    [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        r"C:\Program Files\Microsoft VS Code\Code.exe",
    ] if _IS_WIN else
    ["/Applications/Visual Studio Code.app/Contents/MacOS/Electron"] if _IS_MAC else
    ["/usr/bin/code", "/snap/bin/code", "/usr/local/bin/code"]
)
_VSCODE = next((p for p in _CODE_CANDIDATES if os.path.exists(p)), None)

def open_vscode():
    cmd = [_VSCODE] if _VSCODE else (["code"] if not _IS_WIN else None)
    if cmd:
        try:
            subprocess.Popen(cmd, close_fds=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            say("⚠  VS Code not found.", YELL)
    elif _IS_WIN:
        subprocess.Popen("code", shell=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ═════════════════════════════════════════════
#  WORKSPACE  — fire all 3 in true parallel, zero blocking
# ═════════════════════════════════════════════
_cooling = False

def launch_workspace():
    global _cooling
    say("💥 GO!", GREEN)
    threading.Thread(target=open_vscode,  daemon=True).start()
    threading.Thread(target=open_browser, daemon=True).start()
    threading.Thread(target=play_audio,   daemon=True).start()

    def _cool():
        global _cooling
        _cooling = True
        time.sleep(COOLDOWN_SEC)
        _cooling = False
        say("👂 Ready.", CYAN)

    threading.Thread(target=_cool, daemon=True).start()


# ═════════════════════════════════════════════
#  CLAP DETECTOR  — sounddevice callback runs in C-level audio thread
#  No GIL, no sleep(), CHUNK=128 = ~2.9 ms response time
# ═════════════════════════════════════════════
class ClapDetector:
    def __init__(self, cb):
        self._cb      = cb
        self._times   = []
        self._in_clap = False
        self._stream  = None

    def start(self):
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=CHUNK,       # 128 frames ≈ 2.9 ms per callback
            latency="low",         # tell PortAudio to minimise buffering
            callback=self._on_audio,
        )
        self._stream.start()

    def stop(self):
        if self._stream:
            self._stream.stop()
            self._stream.close()

    def _on_audio(self, indata, frames, time_info, status):
        peak = np.max(np.abs(indata))

        if peak > CLAP_THRESHOLD and not self._in_clap:
            self._in_clap = True
            now = time.monotonic()
            self._times = [t for t in self._times if now - t < CLAP_WINDOW_SEC]
            self._times.append(now)

            if len(self._times) >= 2:
                self._times.clear()
                if not _cooling:
                    # Dispatch to thread so audio callback returns instantly
                    threading.Thread(target=self._cb, daemon=True).start()

        elif peak < CLAP_THRESHOLD // 2:
            self._in_clap = False


# ═════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════
def main():
    say("Richard online. 🤖", GREEN)
    prewarm_audio()
    say(f"Chrome : {_CHROME or 'system default'}", CYAN)
    say(f"VSCode : {_VSCODE or 'PATH fallback'}", CYAN)
    say("Double-clap to launch. Ctrl+C to quit.", CYAN)

    det = ClapDetector(launch_workspace)
    det.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        say("Later. 👋", GREEN)
        det.stop()


if __name__ == "__main__":
    main()