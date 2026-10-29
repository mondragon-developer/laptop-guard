"""Opt-in hardware checks. Never install input hooks or rotate evidence clips."""
from dataclasses import replace
import queue
import tempfile
import threading
import tkinter as tk
from tkinter import messagebox

from .storage import InstanceLock, RuntimePaths
from .video import WebcamRecorder


def camera_check(config, register):
    """Exercise recording/decoding in a temporary folder, away from evidence."""
    with tempfile.TemporaryDirectory(prefix="laptop-guard-test-") as folder:
        paths = RuntimePaths(folder)
        recorder = WebcamRecorder(replace(config, record_seconds=2), paths=paths)
        register(recorder)
        recorder.record()
        if not any(paths.videos.glob("intruder_*.*")):
            raise RuntimeError("No se pudo grabar un video. Revisa la cámara y sus permisos.")
    return "Cámara y grabación correctas. El video de prueba se eliminó."


def show(root, config, paths=None):
    from laptop_guard import FakeScreen, _make_alarm
    paths = paths or RuntimePaths()
    paths.ensure()
    lock = InstanceLock(paths.logs / "guard.lock")
    try:
        lock.acquire()
    except RuntimeError:
        messagebox.showinfo("Laptop Guard", "Desactiva primero la protección o cierra la otra prueba.", parent=root)
        root.destroy()
        return

    for widget in root.winfo_children():
        widget.destroy()
    root.title("Laptop Guard — pruebas sin bloqueo")
    root.resizable(False, False)
    tk.Label(root, text="Elige qué quieres probar", font=("Arial", 13, "bold")).pack(padx=25, pady=(20, 8))
    tk.Label(root, text="El teclado y el mouse seguirán funcionando.\n"
                        "La vigilancia automática espera mientras esta ventana esté abierta.\n"
                        "Al cerrarla, vuelve a contar los 15 minutos.").pack(padx=25, pady=8)
    status = tk.Label(root, text="La cámara y el sonido se activan solo al pulsar su botón.", wraplength=480)
    status.pack(padx=25, pady=10)
    results = queue.Queue()
    stopped = threading.Event()
    resource_lock = threading.Lock()
    resource = [None]
    buttons = []
    poll_id = None

    def register(value):
        with resource_lock:
            resource[0] = value
            if stopped.is_set():
                value.stop()

    def stop_resource():
        with resource_lock:
            if resource[0] is not None:
                resource[0].stop()
                resource[0] = None

    def close():
        stopped.set()
        stop_resource()
        root.quit()

    def set_busy(value):
        for button in buttons:
            button.configure(state="disabled" if value else "normal")

    def screens():
        set_busy(True)
        try:
            FakeScreen(config, root).show(preview_seconds=5)
            status.config(text="Prueba de pantallas terminada. Comprueba que viste el aviso en cada una.")
        except Exception as exc:
            status.config(text=f"No se pudieron mostrar las pantallas: {exc}")
        finally:
            root.deiconify()
            set_busy(False)

    def sound():
        alarm = _make_alarm(config.alarm_style)
        register(alarm)
        try:
            alarm.play(2)
            # pygame returns immediately, whereas winsound blocks until done.
            if not stopped.is_set():
                stopped.wait(2)
        finally:
            alarm.stop()
        return "Prueba de sonido terminada. Confirma que escuchaste la alarma."

    def start(work, text):
        set_busy(True)
        status.config(text=text)
        def run():
            try:
                result = work()
            except Exception as exc:
                result = str(exc)
            finally:
                stop_resource()
            # Only enable another test after this worker releases its resource.
            results.put(result)
        threading.Thread(target=run, daemon=True).start()

    for text, action in (
        ("Probar pantallas (5 segundos)", screens),
        ("Probar sonido (2 segundos)", lambda: start(sound, "Sonando…")),
        ("Probar cámara (video temporal de 2 segundos)",
         lambda: start(lambda: camera_check(config, register), "Probando cámara y grabación…")),
    ):
        button = tk.Button(root, text=text, command=action)
        button.pack(padx=25, pady=5, fill="x")
        buttons.append(button)
    tk.Button(root, text="Cerrar pruebas", command=close).pack(pady=(10, 20))
    root.protocol("WM_DELETE_WINDOW", close)
    root.bind("<Escape>", lambda event: close())

    def poll():
        nonlocal poll_id
        try:
            text = results.get_nowait()
        except queue.Empty:
            pass
        else:
            status.config(text=text)
            set_busy(False)
        poll_id = root.after(100, poll)

    try:
        root.deiconify()
        poll()
        root.mainloop()
    finally:
        stopped.set()
        stop_resource()
        if poll_id is not None:
            root.after_cancel(poll_id)
        lock.release()
        root.destroy()
