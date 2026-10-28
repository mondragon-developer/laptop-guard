# Laptop Guard 1.1.0 · Versión preliminar para pruebas

**Descarga, descomprime y abre. No necesitas instalar Python.**

| Tu computador | Descarga |
|---|---|
| 🟦 Windows 10/11 · Intel/AMD x64 | [LaptopGuard-1.1.0-windows-x64.zip](https://github.com/mondragon-developer/laptop-guard/releases/download/v1.1.0/LaptopGuard-1.1.0-windows-x64.zip) |
| 🍎 Mac Apple Silicon · M1 o posterior · macOS 15+ | [LaptopGuard-1.1.0-macos-apple-silicon.zip](https://github.com/mondragon-developer/laptop-guard/releases/download/v1.1.0/LaptopGuard-1.1.0-macos-apple-silicon.zip) |
| 🍎 Mac Intel · macOS 15+ | [LaptopGuard-1.1.0-macos-intel.zip](https://github.com/mondragon-developer/laptop-guard/releases/download/v1.1.0/LaptopGuard-1.1.0-macos-intel.zip) |

En Mac, consulta ** → Acerca de este Mac** para elegir el procesador. Elige uno de estos ZIP, no la descarga **Source code**. Windows ARM y versiones anteriores de macOS no están validados para estos paquetes.

### 🎬 Mira cómo funciona

[Ver la demostración de 15 segundos](https://github.com/mondragon-developer/laptop-guard/releases/download/v1.1.0/LaptopGuard-1.1.0-demo.mp4). Es un recorrido ilustrado, sin audio y con datos ficticios; no contiene capturas del escritorio ni grabaciones de personas. [README con la demo animada](https://github.com/mondragon-developer/laptop-guard#readme).

### Empieza en cuatro pasos

1. **Descomprime.** En Windows usa una carpeta donde puedas guardar archivos; en Mac mueve `LaptopGuard.app` a **Aplicaciones**.
2. **Abre y prueba.** Pulsa **Probar sin bloquear** para comprobar pantallas, sonido y cámara. Los clips de prueba son temporales.
3. **Personaliza.** En **Customize…** configura tu propio contacto y combinación. **Guardar activa la protección.** El valor predeterminado es **Ctrl + Shift + Z**; en Mac, Control, no Command.
4. **Desactiva con tu combinación.** Al volver a abrir la app, tienes cinco segundos para entrar a Settings, probar o cancelar el inicio.

Las aplicaciones todavía no tienen certificado de editor verificado. Windows puede mostrar **SmartScreen**; macOS puede requerir **Privacidad y seguridad → Abrir de todos modos**, además de permisos de **Accesibilidad** y **Cámara**. La guía incluida en cada ZIP explica los pasos. Los equipos administrados pueden bloquear aplicaciones sin firma.

### Qué incluye

- Alarma, aviso local y combinación para desactivar.
- Registro persistente de eventos y tres clips de cámara con rotación. Los caracteres escritos y la combinación no se guardan en el historial de actividad.
- Pruebas de pantalla, sonido y cámara sin bloquear entradas.
- **Windows:** aviso en todos los monitores y activación opcional tras 15 minutos sin teclado o mouse, con aviso cancelable de diez segundos. El ZIP portátil no instala un inicio automático con Windows; abre los controles **Automático (15 minutos)** después de iniciar sesión para iniciar la vigilancia.
- **Mac:** aviso en una pantalla. El automático de 15 minutos y la recuperación de eventos de apagado/reinicio de Windows no están disponibles en Mac.

### Privacidad y alcance de esta prueba

Las configuraciones, registros y videos se guardan localmente. **Los paquetes no contienen el teléfono, configuración, logs ni videos personales del autor.** El código incluye únicamente un contacto de ejemplo y la demo usa texto ficticio.

Laptop Guard es una alarma con una pantalla disuasoria; **no sustituye el bloqueo seguro del sistema operativo**. El mensaje que anuncia borrado es ficticio: la aplicación no borra ni cifra archivos. Un corte de energía puede impedir el último registro.

Se validaron **49 pruebas automáticas por plataforma**, el arranque de las tres apps empaquetadas y la integridad de sus ZIP. Todavía se requieren pruebas supervisadas de permisos, cámara, sonido y monitores en equipos reales. Cada ZIP incluye una comprobación `.sha256` separada.

**¿Algo falla?** [Reporta el problema](https://github.com/mondragon-developer/laptop-guard/issues/new) indicando sistema, procesador, versión y pasos. No adjuntes tu número, combinación, videos privados ni logs sin revisarlos.
