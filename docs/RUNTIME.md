# Datos locales y diagnóstico

## Ubicación

| Ejecución | Carpeta de datos |
|---|---|
| Windows portátil | Junto a `LaptopGuard.exe`; usa una carpeta con permiso de escritura |
| macOS | `~/Library/Application Support/LaptopGuard` |
| Código fuente | Carpeta del proyecto |
| Ejecutable local en `dist/` dentro del proyecto | Logs y videos en el proyecto; configuración junto al ejecutable |

## Archivos

- `guard_config.json`: contacto, combinación y duraciones. No se incluye en Git ni en los ZIP públicos. El contacto predeterminado del código es un ejemplo.
- `logs/guard.jsonl`: eventos con fecha, zona horaria, sesión y tipo. Los intentos de teclado se cuentan sin almacenar los caracteres ni la combinación. Los movimientos del mouse se agrupan aproximadamente por segundo; clics y desplazamientos se registran individualmente.
- `logs/guard_debug.log`: diagnóstico de inicio, fallos y salida de la aplicación empaquetada. Se añade contenido sin borrar el historial.
- `logs/session.json`, `logs/windows_cursor.json`, `logs/guard.lock`: estado reemplazable y bloqueo de instancia; no son el historial de eventos.
- `videos/intruder_1.mp4` a `intruder_3.mp4`: hasta tres clips completos; AVI es la alternativa si no hay codificador MP4. Se sustituye el más antiguo solo después de validar que el nuevo clip puede decodificarse. Una grabación fallida o cancelada conserva los clips anteriores.
- `auto_guard.json`: opción de vigilancia automática en Windows. `logs/auto_guard.jsonl` conserva su historial y `logs/auto_status.json` su estado más reciente.

Puede existir un archivo `*.pending.*` durante la grabación. Un corte de energía puede dejarlo incompleto; no cuenta como un clip terminado. Los logs históricos no tienen rotación automática: archívalos según necesites.

## Apagados y reinicios

En Windows, la aplicación consulta el registro de eventos del sistema mientras está activa y recupera lo disponible al volver a ejecutarse. Distingue solicitudes de apagado/reinicio, inicio y cierre del sistema, interrupciones, suspensión y reanudación. Conserva la hora del evento original y la hora en que lo importó.

La recuperación depende de que Windows conserve sus eventos. Un corte de energía o cierre forzado puede impedir la última escritura. Una sesión inconclusa se informa como interrupción de causa desconocida; no demuestra quién tocó el equipo. Los eventos entre sesiones tampoco se atribuyen automáticamente a otra persona.

macOS no utiliza esta recuperación del registro de Windows. Sí detecta una sesión anterior que quedó abierta en sus propios archivos de estado.

## Pruebas y soporte

**Probar sin bloquear** reserva la instancia mientras el panel está abierto. Al cerrarlo, el vigilante automático de Windows empieza un intervalo nuevo de 15 minutos. Las pruebas de cámara usan una carpeta temporal que no reemplaza los clips reales.

`--check` comprueba importaciones, versión y rutas sin activar protección. `--check-output RUTA` escribe el resultado como JSON, incluso desde el ejecutable sin consola.

Revisa los logs antes de compartirlos: los detalles de eventos del sistema pueden contener nombres de cuenta, procesos o rutas. Nunca adjuntes tu configuración personal ni videos privados a un issue público.
