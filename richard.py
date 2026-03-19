#!/usr/bin/env python3
"""
Richard - Your Voice-Activated AI Assistant
Wake him up by clapping twice and saying "Wake up Richard"!
"""

import os
import sys
import time
import random
import datetime
import threading
import webbrowser
import subprocess
import numpy as np

# ─────────────────────────────────────────────
#  CONFIGURATION  ← edit these to your taste
# ─────────────────────────────────────────────
WAKE_PHRASE       = "wake up richard"   # what you say after clapping
# Any of these partial phrases also count as a valid wake
WAKE_ALTERNATIVES = ["wake up", "richard", "wake richard", "wakeup richard",
                     "wake", "richard wake", "up richard",
                     # ── bonus wake words ──
                     "daddy's home", "daddys home", "daddy home",
                     "hey man", "hey richard", "yo richard", "yo man"]
CLAP_THRESHOLD    = 2500               # mic loudness to count as a clap
CLAP_WINDOW_SEC   = 2.0                # seconds in which 2 claps must happen
SAMPLE_RATE       = 44100
CHUNK             = 1024

# ── Workspace command config ──────────────────
# Sites opened when you say "open workspace"
WORKSPACE_SITES = [
    "https://www.github.com",
    "https://www.linkedin.com",
    "https://chat.openai.com",
    "https://claude.ai",
]

# Path to Visual Studio Code executable
# Adjust this if VS Code is installed in a different location
VSCODE_PATHS = [
    # Windows
    r"C:\Users\{}\AppData\Local\Programs\Microsoft VS Code\Code.exe".format(os.environ.get("USERNAME", "")),
    r"C:\Program Files\Microsoft VS Code\Code.exe",
    # macOS
    "/Applications/Visual Studio Code.app/Contents/MacOS/Electron",
    # Linux
    "/usr/bin/code",
    "/snap/bin/code",
]
# ─────────────────────────────────────────────

# Websites Richard can open  (say "open youtube", "open gmail", etc.)
WEBSITES = {
    "youtube":   "https://www.youtube.com",
    "gmail":     "https://mail.google.com",
    "google":    "https://www.google.com",
    "github":    "https://www.github.com",
    "reddit":    "https://www.reddit.com",
    "twitter":   "https://www.twitter.com",
    "facebook":  "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "netflix":   "https://www.netflix.com",
    "amazon":    "https://www.amazon.in",
    "news":      "https://news.google.com",
    "maps":      "https://maps.google.com",
}
# ─────────────────────────────────────────────

# Lazy imports with friendly error messages
def _require(pkg, install_name=None):
    import importlib
    try:
        return importlib.import_module(pkg)
    except ImportError:
        name = install_name or pkg
        print(f"\n[Richard] Missing package '{name}'. Install it with:\n"
              f"  pip install {name}\n")
        sys.exit(1)


# ══════════════════════════════════════════════
#  COLOUR HELPERS
# ══════════════════════════════════════════════
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def say(msg, color=CYAN):
    print(f"{color}{BOLD}[Richard]{RESET} {msg}")

def user_says(msg):
    print(f"{YELLOW}[You    ]{RESET} {msg}")


# ══════════════════════════════════════════════
#  ELEVENLABS  JARVIS  VOICE ENGINE
# ══════════════════════════════════════════════
#
#  HOW TO GET YOUR FREE API KEY:
#  1. Go to https://elevenlabs.io  and sign up (free tier = 10,000 chars/month)
#  2. Click your profile icon → "Profile + API key"
#  3. Copy the key and paste it below  ↓
#
ELEVENLABS_API_KEY = "YOUR_ELEVENLABS_API_KEY_HERE"

#  VOICE ID — "Daniel" is the closest built-in British male to JARVIS.
#  After signing in you can browse voices at elevenlabs.io/voice-library
#  and paste any voice_id you like here.
ELEVENLABS_VOICE_ID = "onwK4e9ZLuTAKqWW03F9"   # Daniel — British, calm, authoritative

#  Audio model  (eleven_turbo_v2 = fastest, eleven_multilingual_v2 = best quality)
ELEVENLABS_MODEL = "eleven_turbo_v2_5"

# ── internal audio cache so identical phrases don't hit the API twice ──
_audio_cache: dict = {}

def _speak_elevenlabs(text: str) -> bool:
    """
    Stream audio from ElevenLabs and play it immediately.
    Returns True on success, False on any failure.
    """
    try:
        import requests
        import io

        # Check cache first
        if text in _audio_cache:
            audio_bytes = _audio_cache[text]
        else:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/stream"
            headers = {
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            }
            payload = {
                "text": text,
                "model_id": ELEVENLABS_MODEL,
                "voice_settings": {
                    "stability": 0.55,          # JARVIS-like consistency
                    "similarity_boost": 0.80,   # stay close to the voice
                    "style": 0.20,              # slight expressive flair
                    "use_speaker_boost": True,
                },
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            if resp.status_code != 200:
                say(f"ElevenLabs error {resp.status_code}: {resp.text[:120]}", RED)
                return False
            audio_bytes = resp.content
            _audio_cache[text] = audio_bytes  # cache it

        # Play with pygame (best cross-platform audio)
        try:
            import pygame
            pygame.mixer.init(frequency=44100)
            sound = pygame.mixer.Sound(io.BytesIO(audio_bytes))
            sound.play()
            # Wait for audio to finish
            while pygame.mixer.get_busy():
                time.sleep(0.05)
            return True
        except Exception:
            pass

        # Fallback: play via pydub + simpleaudio
        try:
            from pydub import AudioSegment
            from pydub.playback import play as pydub_play
            seg = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            pydub_play(seg)
            return True
        except Exception:
            pass

        # Last resort: write to tmp file and use system player
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name
        if os.name == "nt":
            os.startfile(tmp_path)
        elif sys.platform == "darwin":
            subprocess.call(["afplay", tmp_path])
        else:
            subprocess.call(["mpg123", "-q", tmp_path])
        time.sleep(0.5)
        return True

    except Exception as e:
        say(f"ElevenLabs speak error: {e}", RED)
        return False


# ── pyttsx3 fallback (silent install, used only if ElevenLabs fails) ──
_fallback_engine = None

def _speak_fallback(text: str):
    global _fallback_engine
    try:
        import pyttsx3
        if _fallback_engine is None:
            _fallback_engine = pyttsx3.init()
            _fallback_engine.setProperty("rate", 160)
            _fallback_engine.setProperty("volume", 1.0)
            for v in _fallback_engine.getProperty("voices"):
                if any(n in v.name.lower() for n in ["david", "mark", "male", "george"]):
                    _fallback_engine.setProperty("voice", v.id)
                    break
        _fallback_engine.say(text)
        _fallback_engine.runAndWait()
    except Exception as e:
        say(f"(fallback voice error: {e})", RED)


def speak(text: str):
    """Speak via ElevenLabs JARVIS voice; fall back to pyttsx3 if needed."""
    say(text)
    # If API key not configured, go straight to fallback
    if ELEVENLABS_API_KEY == "YOUR_ELEVENLABS_API_KEY_HERE":
        _speak_fallback(text)
        return
    success = _speak_elevenlabs(text)
    if not success:
        say("(ElevenLabs unavailable — using fallback voice)", YELLOW)
        _speak_fallback(text)


# ══════════════════════════════════════════════
#  RICHARD'S PERSONALITY  (smart replies)
# ══════════════════════════════════════════════
def _time_of_day():
    h = datetime.datetime.now().hour
    if 5  <= h < 12: return "morning"
    if 12 <= h < 17: return "afternoon"
    if 17 <= h < 21: return "evening"
    return "night"

WAKE_GREETINGS = [
    "Hello sir! Good {tod}. How can I help you today?",
    "Hey there sir! Good {tod}. What would you like me to do?",
    "Good {tod} sir! I'm all yours. What do you need?",
    "Rise and shine sir! Good {tod}. Ready when you are.",
    "Hello sir! Having a good {tod} so far? What can I do for you?",
    "Good {tod} sir! Richard here, fully awake. What's on your mind?",
    "Hey sir! Nice to hear from you. What do you need this {tod}?",
]

# ── Special greetings for "daddy's home" wake word ──
DADDYS_HOME_GREETINGS = [
    "Welcome home sir! The house is yours. What do you need?",
    "Ah, the boss is back! Good {tod} sir. What can I do for you?",
    "Welcome back sir! Good {tod}. Ready and waiting as always.",
    "The man of the house has arrived! Good {tod} sir. How can I help?",
    "Good {tod} sir! Glad you're back. What's on the agenda?",
]

# ── Special greetings for "hey man" wake word ──
HEY_MAN_GREETINGS = [
    "Hey! What's up sir? Good {tod}. What do you need?",
    "Yo! I'm here sir. Good {tod}. What are we doing?",
    "Hey hey! Good {tod} sir. What can I do for you?",
    "What's good sir! Ready when you are. What do you need?",
    "Sup sir! Good {tod}. I'm all ears. What's the move?",
]

IDLE_PROMPTS = [
    "What would you like me to do, sir?",
    "I'm listening, sir. What's next?",
    "How can I help you, sir?",
    "What's on your mind, sir?",
    "Go ahead sir, I'm all ears.",
    "What do you need, sir?",
]

CONFIRM_PHRASES = [
    "On it, sir!",
    "Right away, sir!",
    "Sure thing, sir!",
    "Consider it done, sir!",
    "Absolutely, sir!",
    "Got it, sir!",
]

SEARCH_CONFIRMS = [
    "Searching that up for you, sir.",
    "Let me look that up right away, sir.",
    "On it — searching now, sir.",
    "Sure sir, pulling that up!",
]

SLEEP_PHRASES = [
    "Going to sleep now sir. Double-clap whenever you need me!",
    "Alright sir, I'll be right here if you need me. Sweet dreams!",
    "Roger that sir. I'll be listening for your clap!",
    "Night night sir! Just double-clap to wake me.",
]

UNKNOWN_PHRASES = [
    "Hmm, I'm not sure how to do that yet sir. Say 'help' to see what I can do.",
    "I didn't quite get that sir. Try saying 'help' for a list of commands.",
    "Sorry sir, I don't know that one yet. Say 'help' for options.",
]

MISHEAR_PHRASES = [
    "Sorry sir, I didn't catch that. Could you say it again?",
    "Pardon sir? I missed that one.",
    "I couldn't hear you clearly sir. One more time?",
]

def richard_greet(phrase_used=""):
    tod = _time_of_day()
    # Pick greeting pool based on which wake word was used
    if any(w in phrase_used for w in ["daddy", "home"]):
        pool = DADDYS_HOME_GREETINGS
    elif any(w in phrase_used for w in ["hey man", "yo man", "hey richard", "yo richard"]):
        pool = HEY_MAN_GREETINGS
    else:
        pool = WAKE_GREETINGS
    speak(random.choice(pool).format(tod=tod))

def richard_confirm():
    speak(random.choice(CONFIRM_PHRASES))

def richard_idle():
    speak(random.choice(IDLE_PROMPTS))

def richard_search_confirm():
    speak(random.choice(SEARCH_CONFIRMS))

def richard_sleep():
    speak(random.choice(SLEEP_PHRASES))

def richard_mishear():
    speak(random.choice(MISHEAR_PHRASES))

def richard_unknown():
    speak(random.choice(UNKNOWN_PHRASES))


# ══════════════════════════════════════════════
#  CLAP DETECTOR  (runs in background thread)
# ══════════════════════════════════════════════
class ClapDetector:
    def __init__(self, on_double_clap):
        self.on_double_clap = on_double_clap
        self.clap_times     = []
        self._stop          = False
        self._thread        = threading.Thread(target=self._listen, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop = True

    def _listen(self):
        pyaudio = _require("pyaudio")
        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )
        in_clap = False  # debounce flag

        while not self._stop:
            try:
                data  = stream.read(CHUNK, exception_on_overflow=False)
                audio = np.frombuffer(data, dtype=np.int16)
                peak  = np.max(np.abs(audio))

                if peak > CLAP_THRESHOLD and not in_clap:
                    in_clap = True
                    now = time.time()
                    # prune old claps
                    self.clap_times = [t for t in self.clap_times
                                       if now - t < CLAP_WINDOW_SEC]
                    self.clap_times.append(now)

                    if len(self.clap_times) >= 2:
                        self.clap_times = []
                        self.on_double_clap()

                elif peak < CLAP_THRESHOLD // 2:
                    in_clap = False
            except Exception:
                pass

        stream.stop_stream()
        stream.close()
        pa.terminate()


# ══════════════════════════════════════════════
#  VOICE RECOGNISER
# ══════════════════════════════════════════════
def listen_for_speech(prompt="Listening…", timeout=8) -> str:
    sr = _require("speech_recognition", "SpeechRecognition")
    r  = sr.Recognizer()
    r.energy_threshold = 300          # more sensitive mic pickup
    r.dynamic_energy_threshold = True
    say(prompt, GREEN)
    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=0.2)
        say("🎤 Speak now!", GREEN)
        try:
            audio = r.listen(source, timeout=timeout, phrase_time_limit=10)
            text  = r.recognize_google(audio).lower()
            user_says(f'I heard: "{text}"')
            return text
        except sr.WaitTimeoutError:
            say("Timed out — didn't hear anything.", YELLOW)
            return ""
        except sr.UnknownValueError:
            say("Couldn't understand — try speaking louder/clearer.", YELLOW)
            return ""
        except sr.RequestError as e:
            say(f"Speech API error: {e}", RED)
            return ""


# ══════════════════════════════════════════════
#  CHROME LAUNCHER
# ══════════════════════════════════════════════
def open_chrome(url: str):
    chrome_paths = [
        # Windows
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        # macOS
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        # Linux
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ]
    for path in chrome_paths:
        if os.path.exists(path):
            subprocess.Popen([path, url])
            return
    # Fallback: let Python pick the default browser
    webbrowser.open(url)


# ══════════════════════════════════════════════
#  VS CODE LAUNCHER
# ══════════════════════════════════════════════
def open_vscode():
    for path in VSCODE_PATHS:
        if os.path.exists(path):
            subprocess.Popen([path])
            return True
    # Try launching via system command (works if 'code' is in PATH)
    try:
        subprocess.Popen(["code"], shell=(os.name == "nt"))
        return True
    except FileNotFoundError:
        return False


# ══════════════════════════════════════════════
#  COMMAND HANDLER
# ══════════════════════════════════════════════
def handle_command(text: str):
    if not text:
        say("I didn't catch that. Try again!", YELLOW)
        return

    # ── open workspace ────────────────────────
    if "workspace" in text:
        speak("Sure sir! Opening your workspace right away!")

        # Launch VS Code
        launched = open_vscode()
        if launched:
            speak("Visual Studio Code is launching sir.")
        else:
            speak("Hmm, I couldn't find Visual Studio Code sir. Make sure it's installed.")

        # Open all workspace sites with a small delay between each
        site_names = ["GitHub", "LinkedIn", "ChatGPT", "Claude"]
        for name, url in zip(site_names, WORKSPACE_SITES):
            say(f"   Opening {name}…")
            open_chrome(url)
            time.sleep(0.8)

        speak("Your workspace is all set sir. GitHub, LinkedIn, ChatGPT and Claude are open. Let's get to work!")
        return


    if "open" in text or "go to" in text or "launch" in text:
        for keyword, url in WEBSITES.items():
            if keyword in text:
                speak(f"{random.choice(CONFIRM_PHRASES)} Opening {keyword} for you.")
                open_chrome(url)
                return
        words = text.split()
        for word in words:
            if "." in word and " " not in word:
                url = word if word.startswith("http") else "https://" + word
                speak(f"Opening that for you sir.")
                open_chrome(url)
                return
        speak("Hmm, which site did you want sir? Try saying open youtube or open github.")
        return

    # ── search <site> for <query> ────────────
    if "search" in text:
        # Check if searching on a specific site
        for site_name, site_url in WEBSITES.items():
            if site_name in text:
                # Extract query: remove "search", site name, and "for"
                query = (text.replace("search", "")
                             .replace(site_name, "")
                             .replace("for", "")
                             .strip())
                if query:
                    # Build site-specific search URLs
                    if site_name == "youtube":
                        url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
                    elif site_name == "reddit":
                        url = f"https://www.reddit.com/search?q={query.replace(' ', '+')}"
                    elif site_name == "github":
                        url = f"https://github.com/search?q={query.replace(' ', '+')}"
                    elif site_name == "amazon":
                        url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
                    else:
                        # Generic site search (try to use the site's search)
                        url = f"{site_url}?q={query.replace(' ', '+')}"
                    
                    speak(f"Searching {site_name} for {query}.")
                    open_chrome(url)
                    return
                else:
                    speak(f"What would you like me to search for on {site_name} sir?")
                    return
        
        # Fallback: generic Google search
        query = (text.replace("search for", "")
                     .replace("search", "")
                     .replace("google", "")
                     .replace("look up", "")
                     .strip())
        if query:
            url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            richard_search_confirm()
            open_chrome(url)
        else:
            speak("What would you like me to search for sir?")
        return

    # ── help ─────────────────────────────────
    if "help" in text or "what can you do" in text:
        sites = ", ".join(WEBSITES.keys())
        speak("Sure sir! Here's what I can do. Say open workspace to launch VS Code with all your sites. Say open followed by a site name like youtube or gmail. Say search followed by anything to Google it. Or say go to sleep to put me back to sleep.")
        say("  • open workspace → VS Code + GitHub, LinkedIn, ChatGPT, Claude")
        say(f"  • open <site>    → {sites}")
        say("  • search <query> → Google search")
        say("  • go to sleep    → puts Richard to sleep")
        return

    if "sleep" in text or "goodbye" in text or "bye" in text:
        richard_sleep()
        return "__sleep__"

    richard_unknown()


# ══════════════════════════════════════════════
#  MAIN  LOOP
# ══════════════════════════════════════════════
double_clap_event = threading.Event()

def on_double_clap():
    double_clap_event.set()

def main():
    say("Hello sir! Richard here, ready to assist.")
    
    # Check hard dependencies
    _require("pyaudio")
    _require("speech_recognition", "SpeechRecognition")
    _require("numpy")
    _require("requests")

    detector = ClapDetector(on_double_clap)
    detector.start()
    speak("Going to sleep now. Double-clap and say wake up Richard whenever you need me.")

    awake = False

    try:
        while True:
            if not awake:
                # Wait for double-clap
                double_clap_event.wait()
                double_clap_event.clear()

                say("I heard two claps! Say the wake phrase…", GREEN)

                # Give up to 3 attempts to say the wake phrase
                woke = False
                detected_phrase = ""
                for attempt in range(3):
                    speak(f"I heard two claps sir. Say: wake up Richard, daddy's home, or hey man. Attempt {attempt+1} of 3.")
                    phrase = listen_for_speech(
                        f"Say wake phrase (attempt {attempt+1}/3)", timeout=8
                    )
                    # Fuzzy match — accept if any keyword found
                    if phrase and (
                        WAKE_PHRASE in phrase or
                        any(alt in phrase for alt in WAKE_ALTERNATIVES)
                    ):
                        woke = True
                        detected_phrase = phrase
                        break
                    elif phrase:
                        speak("I didn't quite catch that sir. Please try again.")

                if woke:
                    richard_greet(detected_phrase)
                    awake = True
                else:
                    speak("I couldn't hear the wake phrase sir. Going back to sleep. Just double-clap when you need me!")

            else:
                # Active session — ask what to do
                richard_idle()
                command = listen_for_speech("🎤 Listening for your command…")
                if not command:
                    richard_mishear()
                    continue
                result = handle_command(command)
                if result == "__sleep__":
                    awake = False

    except KeyboardInterrupt:
        speak("Goodbye sir! It was a pleasure. See you next time!")
        detector.stop()
        sys.exit(0)


if __name__ == "__main__":
    main()