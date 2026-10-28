# Laptop Guard 1.1.0

Download, unzip, and open the app. **No Python installation needed.**

| Computer | Download |
|---|---|
| Windows 10/11, Intel or AMD 64-bit | `LaptopGuard-1.1.0-windows-x64.zip` |
| Mac with Apple Silicon (M1 or newer), macOS 15+ | `LaptopGuard-1.1.0-macos-apple-silicon.zip` |
| Mac with Intel processor, macOS 15+ | `LaptopGuard-1.1.0-macos-intel.zip` |

On Mac, Apple menu → About This Mac tells you whether you have an Apple chip or an Intel processor. Older macOS versions and Windows ARM are not validated for these packages. The GitHub **Source code** downloads are for developers; choose one of the ZIPs named above to use the app.

## First launch

1. Extract the ZIP. On Windows keep the app in a writable folder; on Mac move `LaptopGuard.app` to Applications.
2. Open Laptop Guard and choose **Customize…** to set your own contact phone number and unlock combination. **Saving activates the guard.** The default combination is **Ctrl + Shift + Z** (Control, not Command, on Mac).
3. Before leaving the computer unattended, use **Probar sin bloquear** to test the screen, sound and camera individually. On later launches, click this button during the five-second countdown.
4. Once armed, a key press, click or mouse movement triggers the warning, alarm and optional webcam clip. Use your combination to deactivate it.

## What's new

- Persistent event logs and three rotating webcam clips; unsuccessful recordings keep existing clips.
- Safe screen, sound and camera checks without blocking input. Test videos are temporary.
- Windows: warning on all monitors, including display-layout changes; sound uses built-in Windows audio.
- Windows: optional automatic activation after 15 idle minutes with a cancellable 10-second warning. Open **Automático (15 minutos)** during the launch countdown to enable or pause it. This portable download does not install startup entries; reopen these controls after signing in to start the watcher again.
- Windows: shutdown/restart evidence recovered from the system journal when available.

## Before you use it

- These builds have **no verified publisher certificate**. Windows may show SmartScreen; macOS may require Privacy & Security → Open Anyway. macOS also requires Accessibility permission and, for recording, Camera permission. Read the included guide. A managed computer may prevent unsigned apps from running.
- macOS currently shows a warning on one screen. Automatic idle activation and Windows system-event recovery are Windows-only.
- This is a local alarm and screen overlay, **not the operating system's secure lock screen**. It does not encrypt or delete files; the on-screen deletion warning is a deterrent message.
- No cloud account is needed and the app does not upload recordings. Settings, logs and clips stay on the computer. The download contains no personal settings or recordings from the developer.
- VS Code tunnels, terminal commands and model-server requests are not blocked by the guard. Automation that simulates desktop keyboard/mouse input may trigger it. Network connections still require an awake, connected computer.

Each ZIP has a matching `.sha256` checksum. Automated tests and packaged-app startup checks run separately on Windows, Apple Silicon and Intel Mac. Physical camera, sound, input permissions and multi-monitor behavior still require a supervised test on your own computer.
