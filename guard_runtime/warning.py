"""Purely visual warning state. Never read, change or delete user files."""
from dataclasses import dataclass

SIMULATION_SECONDS = 120


@dataclass(frozen=True)
class WarningState:
    color: str
    countdown: str
    console: str


def warning_state(elapsed, *, flash=True, simulation=True):
    elapsed = max(0, elapsed)
    color = "#ff3030" if not flash or int(elapsed / 0.65) % 2 == 0 else "#a81818"
    if not simulation:
        return WarningState(color, "", "")
    remaining = max(0, SIMULATION_SECONDS - int(elapsed))
    if remaining == 0:
        return WarningState(color, "00:00 — CONTACT THE OWNER NOW",
                            "[SIMULATION] Countdown ended.\n"
                            "[SIMULATION] No files were changed.\n"
                            "[WAITING] Owner authorization required.")
    tick = int(elapsed)
    rows = [f"[SIMULATION] demo_file_{number:03d}.dat  →  DELETE QUEUED"
            for number in range(max(1, tick - 1), max(1, tick - 1) + 3)]
    return WarningState(color, f"CALL WITHIN {remaining // 60:02d}:{remaining % 60:02d}",
                        "\n".join(rows))
