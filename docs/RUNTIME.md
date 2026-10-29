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

La alarma necesita que el computador esté encendido y la aplicación en ejecución. Apagar, reiniciar o cerrar sesión termina ese proceso; no conserva una alarma sonando ni la cuenta regresiva entre arranques. Un acceso directo `LaptopGuard.exe --watch` en Inicio de Windows vuelve a abrir el vigilante **después de iniciar sesión**, si el acceso está habilitado. Con el modo automático activado, empieza un intervalo nuevo de 15 minutos; no se activa inmediatamente al encender. Los ZIP portátiles no instalan ese acceso por sí solos.

`Win + L` cambia al escritorio seguro de Windows. La aplicación no captura entradas ni muestra su aviso sobre esa pantalla. El vigilante automático espera mientras está bloqueada y reinicia su intervalo al desbloquear. Si una alarma ya estaba sonando, el proceso puede seguir reproduciéndola hasta su duración configurada mientras la sesión permanece activa; bloquear no garantiza silenciarla ni permite detectar toques sobre el escritorio seguro. La suspensión pausa la ejecución; no hay vigilancia mientras el equipo duerme. El bloqueo de Windows sigue siendo la protección del sistema.

Referencias: [inicio de aplicaciones al iniciar sesión](https://support.microsoft.com/en-us/windows/experience/startup-boot/configure-startup-applications-in-windows), [escritorios y escritorio seguro de Windows](https://learn.microsoft.com/en-us/windows/win32/winstation/desktops).

En Windows, la aplicación consulta el registro de eventos del sistema mientras está activa y recupera lo disponible al volver a ejecutarse. Distingue solicitudes de apagado/reinicio, inicio y cierre del sistema, interrupciones, suspensión y reanudación. Conserva la hora del evento original y la hora en que lo importó.

La recuperación depende de que Windows conserve sus eventos. Un corte de energía o cierre forzado puede impedir la última escritura. Una sesión inconclusa se informa como interrupción de causa desconocida; no demuestra quién tocó el equipo. Los eventos entre sesiones tampoco se atribuyen automáticamente a otra persona.

macOS no utiliza esta recuperación del registro de Windows. Sí detecta una sesión anterior que quedó abierta en sus propios archivos de estado.

## Pruebas y soporte

### Sonido y efectos visuales (código actual; posteriores a los ZIP v1.1.0)

Settings permite elegir **Classic alarm** (onda cuadrada de 800 Hz, como la alarma original) o **Beeps**. En Windows ambos usan audio del sistema, sin agregar bibliotecas. El volumen depende de los altavoces y el mezclador de Windows; la aplicación no cambia el volumen general ni desactiva el silencio. Usa **Probar sonido** para comparar con seguridad.

**Blink the red warning** alterna dos tonos de rojo cada 650 ms. **2-minute countdown + simulated file activity** muestra una cuenta de 02:00 a 00:00 y nombres ficticios; no enumera, modifica, cifra ni borra archivos. Al llegar a cero, el aviso permanece hasta desactivar la protección y confirma que los archivos no se cambiaron. Los dos efectos pueden deshabilitarse de forma independiente. La duración del sonido es una opción separada del contador visual.

Las configuraciones anteriores conservan contacto, combinación y duraciones; los campos nuevos usan alarma clásica y efectos activados de forma predeterminada. El botón de guardar sigue activando la protección en el lanzador.

**Probar sin bloquear** reserva la instancia mientras el panel está abierto. Al cerrarlo, el vigilante automático de Windows empieza un intervalo nuevo de 15 minutos. Las pruebas de cámara usan una carpeta temporal que no reemplaza los clips reales.

`--check` comprueba importaciones, versión y rutas sin activar protección. `--check-output RUTA` escribe el resultado como JSON, incluso desde el ejecutable sin consola.

Revisa los logs antes de compartirlos: los detalles de eventos del sistema pueden contener nombres de cuenta, procesos o rutas. Nunca adjuntes tu configuración personal ni videos privados a un issue público.
