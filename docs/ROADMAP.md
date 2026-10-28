# Feature roadmap

## Remote activation

- Keep the computer awake and online; remote control cannot operate on a powered-off machine.
- Add explicit arm, disarm and status actions over an authenticated private connection. Reuse the existing guard lifecycle and audit trail.
- Define which phone/client will be used and how pairing and access revocation work before implementing a network endpoint. Do not expose an unauthenticated public port.
- Record remote requests and their result, distinguishing an authenticated account from proof of who physically touched the laptop.
- Test disconnects, duplicate commands and local emergency unlock before unattended use.

## Automatic activation — implemented for Windows

- `--watch` observes the current Windows session's keyboard/mouse idle time. After 15 idle minutes, a 10-second warning precedes activation. Input cancels the warning.
- `--auto-settings` provides persistent enable/pause controls in `auto_guard.json`. Closing the controls keeps the selected setting.
- Starting the monitor, unlocking the guard, returning from sleep or a locked desktop, or cancelling starts a fresh interval. The watcher does not prevent sleep or change the Windows power plan.
- Manual activation remains available through the normal launcher. Both paths share the instance lock, evidence storage and unlock combination.
- `logs/auto_guard.jsonl` records the monitor's activity; `guard_activated.reason` records `manual` or `idle`. `logs/auto_status.json` is a replaceable heartbeat, not historical evidence.
- This user's installation is enabled, starts now and uses a per-user Startup shortcut to start the watcher at Windows sign-in. It does not run before sign-in or while the computer is asleep/off.

## Voice prototype

The supplied draft is preserved in `prototypes/voice_lock_screen_draft.py` and is not imported by the current app. Before integrating, repair its key-sequence state/focus handling, UI-thread communication and image API compatibility. Its Google speech recognizer uses a network service; select offline or online recognition explicitly during that future work. A spoken phrase alone is not speaker authentication.

## Acceptance checks for future work

Retain the current alarm, warning screen and local unlock; keep logs append-only and the three-clip ring. Exercise new activation paths with fake inputs first, then supervised physical keyboard/mouse and camera tests. Remote activation remains planned and is not enabled.
