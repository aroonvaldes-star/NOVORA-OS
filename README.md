# NOVORA OS 0.1 — fuente del primer prototipo

**Estado: configuración inicial de construcción, NO ISO validada ni instalador seguro certificado.**

Objetivo: primera ISO Live x86-64 basada en Debian 13 (Trixie), KDE Plasma, Wine, Flatpak, herramientas de desarrollo y Calamares. El requisito crítico es poder seleccionar particiones del disco Seagate externo sin tocar Windows. La versión 0.1 implementa una herramienta de **identificación SOLO LECTURA** y utiliza el particionado manual de Calamares; todavía **NO aplica una protección técnica infalible sobre los discos internos**.

## Arquitectura

- Base: Debian 13 + kernel proporcionado por Debian.
- Gráficos: Plasma 6 con Wayland cuando sea compatible, X11 como alternativa.
- Experiencia visual: inspiración macOS (barra superior, dock, animaciones discretas). **Tema propio aún pendiente**.
- Aplicaciones Linux: APT y Flatpak; soporte AppImage según binario específico.
- Windows: Wine/wine64 básico. 32 bits y Bottles/Proton requerirán configuración y pruebas adicionales; no se promete compatibilidad universal.
- Desarrollo: compiladores, Git, Python, Node.js. Editores y contenedores se incorporarán tras validación.
- Instalador: Calamares configurado por Debian, con particionado manual; auditoría preinstalación independiente.

## Construcción (en Debian 13 x86-64 o VM Debian 13; requiere Internet)

```bash
sudo apt update
sudo apt install -y live-build debootstrap xorriso squashfs-tools
cd NOVORA-OS-0.1
sudo bash scripts/build-iso.sh
```

Resultado esperado tras **construcción correcta**: `build/live-image-amd64.hybrid.iso` (el nombre exacto puede variar) y archivo SHA256. El script no escribe en un disco físico; genera un archivo ISO. Necesitarás espacio libre considerable y acceso a repositorios Debian.

## Pruebas antes de tocar un disco físico

1. Arrancar la ISO en una VM UEFI con un disco de prueba desechable.
2. Revisar KDE, red, audio, Wine y herramientas de desarrollo.
3. Revisar el instalador en dos discos **virtuales**: uno simula Windows y otro Seagate. Confirmar que se puede instalar en partición existente sin tocar el primero.
4. Comprobar que el disco de prueba externo incluye `/boot/efi` y que la VM puede arrancar sin depender de la ESP interna simulada.
5. Solo después estudiar instalación real. Ver [docs/INSTALACION-SEAGATE.md](docs/INSTALACION-SEAGATE.md).

## Límites conocidos de esta primera fuente

- ISO no compilada ni arrancada en este entorno; paquetes y configuración requieren integración/test.
- Se necesita conexión al construir; la ISO Live se ejecuta sin conexión una vez construida.
- No hay protección automatizada del cargador de arranque ni bloqueo contra seleccionar «Borrar disco» en Calamares; **no instalar aún en el Seagate real**.
- Este proyecto fuente no altera la partición de Windows ni el Seagate.

Fuentes: https://live-team.pages.debian.net/live-manual/html/live-manual.en.html ; https://manpages.debian.org/trixie/live-build/lb_config.1.en.html ; https://calamares.io/docs/partitions/ ; https://wiki.debian.org/UEFI
