# laptop-guard

A simple laptop "protection" prank for Windows and macOS. You activate it and walk away. If anyone touches the keyboard or mouse while you are gone:

- a full-screen black warning appears (a fake ransom message with YOUR phone number),
- a loud alarm sounds,
- a short webcam clip of the "intruder" is recorded,
- every attempt is written to a log file,
- and their keystrokes/clicks never reach the computer.

Nothing is harmed. Pressing your secret combo (default `Ctrl+Shift+Z`) stops everything and returns the laptop to normal.

![The warning screen an intruder sees](demo.gif)

> Intended use: deter or prank anyone who touches your unattended laptop. On Windows, `Ctrl+Alt+Del` always remains available as an OS-level way out (Sign out kills the guard). On macOS, `Cmd+Opt+Esc` does the same.


## Download (no Python needed)

Grab the latest zip for your OS from the [Releases page](https://github.com/mondragon-developer/laptop-guard/releases), unzip it, and follow the `READ-ME-FIRST.txt` inside. Everything below this section is for running from source instead.

- **Windows:** double-click `LaptopGuard.exe`. On the blue SmartScreen warning click **More info** -> **Run anyway** (the app is not code-signed; this appears once).
- **macOS:** double-click `LaptopGuard.app`, click **Done** on the "developer cannot be verified" warning, then go to **System Settings -> Privacy & Security**, scroll down, and click **Open Anyway** (first launch only). The app then asks macOS for **Accessibility** and waits until you turn it on (Privacy & Security -> Accessibility); **Camera** is requested on the first trigger. After updating to a new version, remove LaptopGuard from the Accessibility list and add it again: macOS ties the grant to the exact app file, so a stale entry looks enabled but does nothing.
- Some antivirus tools flag any program that blocks the keyboard as suspicious; the guard suppresses input by design and sends nothing anywhere. Every release zip is built from this repo by GitHub Actions, and a new release is just a pushed version tag - the workflow builds and attaches both zips automatically.


## Tech stack

- **Python 3.10+** - single codebase for Windows and macOS, no build step.
- **`tkinter`** (stdlib) - the full-screen warning window, the settings window, and the countdown splash; no external GUI framework.
- **`pynput`** - global keyboard/mouse listeners with `suppress=True`, so intruder input never reaches the OS; also drives the secret-combo detection.
- **`pygame` + `numpy`** - the alarm: a harsh 800 Hz square wave synthesized as a NumPy buffer and looped through the pygame mixer; on Windows a stdlib `winsound` beeper takes over if pygame is missing.
- **`opencv-python`** - records the short webcam clip of the intruder (`mp4v`, with an XVID/AVI fallback when the codec is unavailable).
- **`powercfg`** (Windows) - sleep/hibernate timeouts are set to "never" while the guard is active and restored exactly afterwards; on macOS a no-op manager keeps the same interface.
- **Threading model** - pynput hook callbacks never block (they only start daemon threads for the alarm and recorder); the tkinter warning screen always runs on the main thread, which both Tk/Cocoa on macOS and Windows hooks require. On macOS the pynput listeners additionally run in a helper subprocess (`input_helper_main`, respawned from the same binary), because macOS 26 kills any process whose keyboard listener calls the Text Services Manager off the main dispatch queue (SIGTRAP in `TSMGetInputSourceProperty`, unfixed in pynput as of 1.7.7). The helper reports events to the parent over a pipe and self-terminates if the parent dies, so input is never left suppressed. If macOS refuses the event tap (pynput signals that only by returning early), the helper says why and the guard switches itself off with an explanation instead of exiting silently. The launcher's Tk root is the only one the process ever creates: it is hidden while the guard waits and reused for the warning screen, because Tk on macOS crashes when a destroyed root is followed by a second one (Tk ticket c18c36f8).
- **Launchers** - `guard.bat` / `setup.bat` (Windows) and `LaptopGuard.command` / `Setup.command` (macOS) wrap the app in a double-click experience, and `guard_app.py` auto-installs missing packages on launch.
- **Diagnostics** - frozen builds have no console, so prints, tracebacks and the input helper's own output land in `guard_debug.log` in the data folder.

The code follows SOLID principles: each component (config, alarm, screen, power, webcam, input) is a small class behind a tiny interface, wired together by the `LaptopGuard` orchestrator, so any piece (for example the alarm backend) can be swapped without touching the rest.


## The one-icon app (Windows and Mac)

`guard_app.py` wraps everything into a single double-click experience. On Windows the desktop shortcut points to it; on Mac it runs either as the frozen `LaptopGuard.app` (release zip) or inside Terminal via `LaptopGuard.command` (source checkout) - double-click either one, or an alias of it:

- **First run ever:** a small window asks whether to keep the default settings (combo `Ctrl+Shift+Z`, default phone number, alarm/clip times) or **Customize...** them. Either choice saves `guard_config.json`, so this screen never appears again.
- **Every later run:** a 5-second countdown splash ("Activating in 5 s...") and the guard activates by itself. The **Settings** button on the splash is the only way back into the settings - exactly the "request it" path. Closing the window does NOT activate the guard.
- Missing packages are installed automatically on launch.
- On Windows no console window appears (it runs through `pythonw.exe`). On Mac the Accessibility/Camera permissions belong to whichever host runs the app: with the `.app` flow that is LaptopGuard itself; with the `.command` flow it is Terminal, whose window stays open in the background.
- On Mac, the app asks macOS for the Accessibility grant up front and waits on a "Permission needed" window until it is turned on. If macOS still refuses the input tap later (typically a stale grant after an update), the guard switches itself off and says so instead of vanishing.
- To brand it, drop an `icon.ico` (Windows) or `icon.png` (Mac) into the `laptop-guard` folder: the window and the desktop shortcut pick it up.

The classic launchers below remain available and work exactly as before.


## The two things you will double-click

| File              | What it does                                            |
|-------------------|---------------------------------------------------------|
| `setup.bat` (Windows) / `Setup.command` (Mac) | Opens the **Settings window**: phone number, secret combo, alarm length. Run this FIRST, and again any time you want to change something. |
| `guard.bat` (Windows) / `LaptopGuard.command` (Mac) | **Starts the app** (countdown, then the guard activates). Double-click it, then walk away. |

Keep all the files together in the `laptop-guard` folder. To use it from the desktop, make a shortcut/alias (see below) - do NOT move the files out of the folder.


## Windows - first time (about 5 minutes)

1. **Install Python** from https://www.python.org/downloads/ if you do not have it. During installation, tick the box **"Add python.exe to PATH"**.
2. **Double-click `setup.bat`.** It installs the required packages (only needed once) and then opens the Settings window.
3. **In the Settings window:**
   - type the phone number that should appear on the fake warning,
   - type your secret combo, for example `ctrl+shift+z` (one or more of `ctrl`, `shift`, `alt`, `win` plus one key),
   - click **Save**.
4. **Optional but recommended - desktop shortcut:** right-click `guard.bat` → **Send to** → **Desktop (create shortcut)**. Now you can activate the guard from the desktop.
5. **Test it once:** double-click `guard.bat` (or your new shortcut), touch a key to see the warning and hear the alarm, then press your combo to stop it.

That is all. From now on, step 5 is the only step.


## macOS - first time (about 5 minutes)

1. **Install Python 3** from https://www.python.org/downloads/ if you do not have it.
2. **Right-click `Setup.command` → Open** (a right-click is needed the first time so macOS lets it run). It installs the required packages and opens the Settings window. If macOS says the file is not executable, open Terminal in this folder once and run: `chmod +x Setup.command LaptopGuard.command`
3. **Grant the one-time permissions** when macOS asks:
   - **Accessibility / Input Monitoring** for Terminal (System Settings → Privacy & Security) - without it the guard cannot see or block keyboard and mouse. Quit and reopen Terminal after granting.
   - **Camera** - needed for the intruder clip.
   These grants are permanent for the Terminal app.
4. **In the Settings window:** type your phone number and secret combo (for example `ctrl+shift+z`, or use `cmd` instead of `ctrl`), then click **Save**.
5. **Optional - desktop alias:** right-click `LaptopGuard.command` → **Make Alias**, and drag the alias to the Desktop.
6. **Test it once:** double-click `LaptopGuard.command` (or the alias), touch a key, then press your combo to stop it.


## Every time you want to use it

1. Double-click `guard.bat` (Windows) or `LaptopGuard.command` (Mac), or the desktop shortcut/alias you made.
2. The console shows one line - `[Guard] ACTIVE - keyboard and mouse are blocked.` - and nothing else. Your combo is deliberately NOT shown, so nobody reading the screen learns the way out.
3. Walk away. Any key press, click, or mouse movement triggers the alarm, the warning screen, the webcam clip, and a log entry.
4. Come back and **press your secret combo** to stop everything.

If anything ever goes wrong: on Windows press `Ctrl+Alt+Del` → **Sign out**; on macOS press `Cmd+Opt+Esc` and force-quit Terminal. That always kills the guard and restores your input.


## Forgot your combo? Want to change the phone number?

Two ways in:

- Double-click the app icon and press **Settings** on the countdown splash before it activates.
- Or open the standalone Settings window (`setup.bat` / `Setup.command`).

Both show your current settings - including the combo - because only the owner opens them. Change whatever you like and click **Save**. The new settings apply the next time the guard starts.


## What gets saved where

Running from source, everything lands inside the `laptop-guard` folder. The Windows release exe stores the same files next to itself, and the macOS release app stores them in `~/Library/Application Support/LaptopGuard` (an unsigned macOS app runs from a read-only location, so they cannot live next to the app).

- `guard_config.json` - your settings from the Settings window. Plain text, so keep the folder private if the combo should stay secret. (The included `.gitignore` excludes it from version control, along with `guard.log` and the webcam clips; `guard_config.example.json` shows the file format and is safe to share.)
- `guard.log` - one timestamped line per intrusion attempt.
- `intruder.mp4` (or `.avi`) - the webcam clip, recorded once per activation.
- `guard_debug.log` - what the app did (helper start/stop, errors, tracebacks). Attach it when reporting a problem.

Advanced users can also edit `guard_config.json` directly:

| Key                  | Example            | Meaning                            |
|----------------------|--------------------|------------------------------------|
| `phone`              | `"555-1234567"`    | Phone number on the warning screen |
| `key_combo`          | `["ctrl","shift","z"]` | Deactivation combo             |
| `alarm_duration_sec` | `90`               | Alarm length in seconds            |
| `record_seconds`     | `5`                | Webcam clip length (`0` = off)     |

If the file is missing or invalid, built-in defaults are used.


## Requirements (installed automatically by the setup launchers)

- Python 3.10+ with `tkinter` (included in the python.org installers; Homebrew Python on macOS also needs `brew install python-tk`).
- Packages from `requirements.txt`: `pynput` (input listening/blocking), `pygame` + `numpy` (alarm), `opencv-python` (webcam clip). If `pygame` is missing on Windows, a `winsound` beeper is used instead; on macOS the alarm is then disabled but the rest still works.


## How it works (short version)

- `laptop_guard.py` is the guard itself. It loads `guard_config.json`, blocks keyboard and mouse with `pynput`, and on the first unauthorized input starts the alarm (pygame), the webcam recorder (opencv), and a full-screen `tkinter` warning. The combo listener runs the whole time; the correct combo closes everything cleanly.
- `guard_setup.py` is the settings window. It only reads and writes `guard_config.json`.
- The `.bat` / `.command` files are double-click launchers that first `cd` into their own folder, so they work from anywhere (desktop shortcuts, aliases, Dock).
