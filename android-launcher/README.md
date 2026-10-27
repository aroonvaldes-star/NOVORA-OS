# Novora Launcher (Android, estilo iOS)

Launcher para Android 8+ con aspecto de iPhone:

- Cuadrícula de 4×6 iconos con esquinas redondeadas y páginas deslizables con puntos.
- Dock translúcido de 4 apps (mantén pulsado un icono → «Añadir/Quitar del Dock»).
- Desliza hacia abajo para buscar apps (tipo Spotlight).
- Mantener pulsado: información de la app o eliminarla.
- Usa el fondo de pantalla del sistema.

## Obtener el APK

GitHub Actions lo compila en cada push (workflow «Novora Launcher (APK)»);
descarga el artefacto `novora-launcher-debug`. En local, con Android SDK:

    cd android-launcher && gradle assembleDebug

Instálalo, pulsa el botón Inicio y elige «Novora Launcher» como predeterminado.
