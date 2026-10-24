# NOVORA OS 0.1.1 — fuente del prototipo (rama de auditoría Claude)

**Estado: configuración de construcción + guardián de discos probado en discos
virtuales. NO hay ISO construida ni probada. El instalador queda BLOQUEADO en
hardware físico (solo funciona dentro de una VM).**

Base: Debian 13 (trixie) amd64, KDE Plasma, Wine (64 bits), Flatpak,
herramientas de desarrollo y Calamares endurecido.

## Qué cambió respecto a 0.1 (ver docs/AUDITORIA-CLAUDE.md)

| Componente | 0.1 | 0.1.1 |
|---|---|---|
| Discos en la sesión Live | escribibles | **solo lectura del kernel** al arrancar (udev + servicio) |
| `novora-storage-audit` | solo avisa; aprueba casos peligrosos | fail-closed: bloquea serie ausente, LUKS montado, límite MBR, discos gemelos, ESP falsa o de otro disco |
| Instalador | Calamares + d-i sin protección | d-i eliminado; `novora-install` desbloquea **solo** el disco autorizado; Calamares oculta los discos RO |
| GRUB / NVRAM | `grub-install` sin `--no-nvram`, `efibootmgr -c -w`, `BootNext` | `--no-nvram --force-extra-removable`; efibootmgr de solo lectura |
| Construcción | sin log, sin manifiesto, hash con ruta absoluta | `build.log`, manifiesto de paquetes, SHA256 verificable, `--clean`, comprobación de anfitrión |

## Desarrollo, apps de Windows y GPU (nuevo)

- **NOVORA-LINK:** .NET 8/10, Rider, `novora-dev compilar` (WPF incluido) y
  `novora-dev ejecutar-windows` (.exe autocontenido abierto con Wine).
- **LINK CONTROL:** Android Studio, `adb`, `scrcpy` (`novora-dev espejo`).
- **Apps de Windows:** doble clic en `.exe`/`.msi` con Wine 11, DXVK/VKD3D-Proton,
  GameMode y perfiles por app (`novora-win optimizar`).
- **GPU:** Intel/AMD/NVIDIA con drivers abiertos desde el arranque;
  `sudo novora-gpu nvidia instalar` para el driver oficial con NVDEC/NVENC,
  Secure Boot (MOK) y modo híbrido (`novora-gpu usar-nvidia`).

Detalles y límites: [docs/DESARROLLO-Y-COMPATIBILIDAD.md](docs/DESARROLLO-Y-COMPATIBILIDAD.md).

## Seguridad, actualizaciones y apariencia (nuevo)

- **Antivirus ClamAV** bajo demanda (clic derecho en Dolphin) y **análisis
  automático de cada `.exe`/`.msi`** antes de su primera ejecución;
  **cortafuegos** (entrantes bloqueadas) y AppArmor.
- **Parches de seguridad automáticos**, resto con tu aprobación (Discover
  semanal o `novora-actualizar ahora`), kernel de respaldo e instantáneas
  Timeshift opcionales.
- **Tema NOVORA:** barra superior con menú global, dock flotante, colores
  claro/oscuro, fondo propio, Inter + JetBrains Mono, Papirus;
  `novora-apariencia` para modo claro/oscuro, acento y modo ligero.

Detalles: [docs/SEGURIDAD-ACTUALIZACIONES-APARIENCIA.md](docs/SEGURIDAD-ACTUALIZACIONES-APARIENCIA.md).

## Teclado

Distribución **Español (Latinoamericano), `latam`**, la de los teclados
mexicanos. Se aplica en el arranque Live (`keyboard-layouts=latam`), en
`/etc/default/keyboard`, en X11/SDDM y en Plasma (`kxkbrc` para usuarios
nuevos). En el instalador, confirma «Español (Latinoamericano)» en la página
de teclado (pendiente de verificar que venga preseleccionado).

## ATLAS — asistente local (nuevo)

Asistente integrado que funciona **sin internet**: conversación, ayuda para
programar, notas y tareas, y explicación de lo que hay en pantalla. Se abre
con `Meta+Shift+A` (panel flotante estilo macOS, claro/oscuro) y
`Meta+Shift+X` analiza la pantalla. Nunca ejecuta nada sin tu confirmación y
tiene prohibidas las órdenes de discos, arranque y privilegios.
Hace también lo de OpenJarvis, sin instalarlo: **agente** de varios pasos con
herramientas (bajo la misma lista prohibida), **investigación** en tus documentos
con citas, **memoria** indexada, **resumen del día** con voz y **rutinas** programadas.
Incluye **Agent Skills** (25 skills de ingeniería de Addy Osmani + 14 de Anthropic),
lee documentos de Office y, solo si lo activas, un **modo nube** por consulta
vía OmniRoute (Claude, GPT, Gemini…).
Detalles: [docs/ATLAS.md](docs/ATLAS.md).

## Apps opcionales

LibreOffice preinstalado. `novora-apps` instala, verificadas: GenOffice (sin
analíticas, con IA local), Spotifast, Zuno, Huntly, OmniRoute y las IAs de la
nube (Claude Code, Codex, Gemini CLI, Copilot CLI).

## Construcción (en Debian 13 x86-64 o VM Debian 13; requiere Internet)

```bash
sudo apt update
sudo apt install -y live-build debootstrap xorriso squashfs-tools
cd NOVORA-OS-0.1.1
sudo bash scripts/build-iso.sh            # primera vez
sudo bash scripts/build-iso.sh --clean    # reconstruir desde cero
# opcional, antes de construir: incluir un modelo para ATLAS (con su SHA256)
bash scripts/add-atlas-model.sh modelo.gguf <sha256>
```

Resultado esperado: `build/novora-os-0.1.1-amd64.iso`, `.sha256`, `.packages`
y `build/build.log`. El script no escribe en discos físicos.

## Pruebas automáticas (no necesitan VM)

```bash
sudo bash tests/run-tests.sh
```

Incluye pruebas del auditor con árboles de discos simulados, de los
envoltorios de GRUB/efibootmgr, de `build-iso.sh` con `lb` simulado y del
guardián sobre **discos virtuales loop** con el kernel real. Las pruebas de
VM (T02–T12) siguen PENDIENTES.

## Uso previsto en VM

1. Arrancar la ISO en una VM UEFI (OVMF) con un disco "Windows" y un disco
   "Seagate" virtuales desechables.
2. Comprobar `sudo novora-disk-guard status`: todo debe estar en `ro=True`.
3. Abrir «Instalar NOVORA OS (solo VM en 0.1.1)». El lanzador audita,
   pide confirmación escrita, desbloquea solo el disco autorizado y abre
   Calamares.

## Límites conocidos

- Mientras el disco destino está desbloqueado, el kernel **no** puede impedir
  que un particionador borre otras particiones de ese mismo disco
  (demostrado en la prueba H). Respaldo verificado obligatorio.
- `wine32` (aplicaciones de 32 bits) requiere multiarch i386: pendiente.
- NVIDIA propietario (área `non-free`) no incluido; se usa nouveau.
- Paquetes nuevos marcados `[VERIFICAR]` en la lista: confirmar en T01.

Fuentes: https://live-team.pages.debian.net/live-manual/ ;
https://calamares.io/docs/partitions/ ; https://wiki.debian.org/UEFI
