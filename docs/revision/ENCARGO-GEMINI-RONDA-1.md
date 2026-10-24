# NOVORA OS 0.1.1 — Encargo de auditoría para Gemini

**Fecha:** 24 de octubre de 2026
**De:** Claude (auditoría de código y seguridad de instalación, ronda 1 terminada)
**Para:** Gemini (validación tecnológica, compatibilidad y alternativas)
**Adjuntos obligatorios:** `NOVORA-OS-0.1-AUDITORIA-CLAUDE-GEMINI-1.md` (encargo original), `NOVORA-OS-v0.1-FUENTES.zip` (código 0.1), `NOVORA-OS-0.1.1.zip` (rama corregida por Claude) y `AUDITORIA-CLAUDE.md`.

> **Reglas que no se negocian (las mismas del encargo original):**
> - No se ejecuta ninguna operación sobre discos físicos, el Seagate, el disco de Windows, su ESP ni la NVRAM real.
> - Las pruebas destructivas se hacen **solo** con discos virtuales desechables de una VM.
> - No declares nada «funcional» ni «seguro» sin evidencia (comando, log, hash o captura). Lo que no se ejecutó se marca **PENDIENTE**.
> - No pidas ni publiques números de serie, claves de BitLocker ni credenciales.

---

## 1. Cómo trabajar

1. **Ronda 1, independiente.** Audita primero el 0.1 original (`NOVORA-OS-v0.1-FUENTES.zip`) siguiendo tu parte del encargo original (§6, «Gemini»), **sin leer `AUDITORIA-CLAUDE.md`**. Así tus conclusiones no se contaminan con las mías.
2. **Ronda 2, contraste.** Después lee `AUDITORIA-CLAUDE.md` y la rama 0.1.1. Confirma, refuta o completa cada punto de la §3 de este documento con fuentes oficiales o con pruebas en VM.
3. Si no tienes ejecución de comandos ni acceso a la web, dilo de forma explícita y marca todo lo afectado como **NO VERIFICADO**.

## 2. Resumen de lo que hizo Claude (para la ronda 2)

**Veredicto de Claude:** 0.1 → APTO SOLO PARA REVISIÓN · 0.1.1 → APTO PARA VM (tras T01) · hardware real → **BLOQUEADO**.

**Hallazgos P0 del 0.1:**
- **Instalador duplicado.** `--debian-installer live` añade el instalador clásico de Debian (d-i) al menú de arranque, sin ninguna protección.
- **Sin protección de discos.** El auditor solo avisa. En el código fuente de Calamares, `partition.conf` no tiene ninguna opción para filtrar discos ni para desactivar «Borrar disco».
- **Escritura en el firmware.** Calamares ejecuta `grub-install --force` sin `--no-nvram`; en la ruta shim usa `efibootmgr -c -w` y `BootNext`.
- **Falsos aprobados.** El auditor original devuelve 0 con un destino montado vía LUKS, un disco sin serie, una partición fuera del límite MBR y dos discos gemelos.
- **ESP mal detectada.** Considera ESP cualquier partición `vfat`, sin mirar el tipo de partición.
- **BIOS solo avisa.** En modo BIOS, GRUB escribiría en el MBR del disco elegido.

**Evidencia en el kernel 6.18 con discos loop:**
- El modo solo lectura del **disco completo** bloquea todas sus particiones, también tras releer la tabla.
- El modo solo lectura **por partición** se pierde al releer la tabla.
- Un sistema de archivos montado en escritura **antes** del bloqueo sigue escribiendo.
- Calamares (`DeviceList.cpp`) no lista los dispositivos en solo lectura.

**Lo que aporta 0.1.1:**
- Todos los discos en solo lectura al arrancar la Live, con regla udev y servicio systemd.
- Auditor *fail-closed*.
- `novora-disk-guard`: desbloquea solo el disco autorizado, identificado por serie/WWN, tamaño y PTUUID.
- Envoltorios de GRUB (`--no-nvram --force-extra-removable`) y un `efibootmgr` de solo lectura.
- Hook de construcción que endurece Calamares.
- Se quita d-i.
- Instalador bloqueado fuera de una VM.
- 68 pruebas automáticas que pasan.

**Riesgo residual reconocido:** con el Seagate desbloqueado, Calamares puede borrar sus otras particiones. Se propone un instalador propio sin particionado para la v0.2.

**Lo que Claude NO pudo hacer:** compilar la ISO (`deb.debian.org`, `salsa.debian.org` y `packages.debian.org` estaban bloqueados), arrancar una VM o leer el manual de `lb_config` de trixie. **Ahí es donde más se te necesita.**

## 3. Puntos que Gemini debe verificar (prioridad P0 → P2)

Para cada punto entrega: **estado** (CONFIRMADO / REFUTADO / NO VERIFICADO), **fuente oficial** con URL, versión y fecha de consulta, o **evidencia de VM**.

### P0 — Seguridad

| # | Pregunta concreta | Dónde mirar |
|---|---|---|
| G-01 | ¿Qué incluye exactamente `calamares-settings-debian` en trixie? Lista `settings.conf` (secuencia `exec`), `modules/bootloader.conf`, `modules/partition.conf` y cualquier script (`bootloader-config`, `install-debian`, módulos `shellprocess`). **¿Algún paso llama a `grub-install` o `efibootmgr` sin pasar por el módulo `bootloader`?** Si lo hay, los envoltorios de 0.1.1 no lo cubren. | Fuente del paquete en Debian (salsa / sources.debian.org), versión de trixie |
| G-02 | ¿El `grub-install` de Debian trixie acepta `--force-extra-removable` y `--no-nvram`? ¿Con Secure Boot copia `shimx64.efi` a `EFI/BOOT/BOOTX64.EFI`? | Parches del paquete `grub2` en trixie, `grub-install --help` en una VM |
| G-03 | ¿Existen en trixie las claves debconf `grub2/update_nvram` y `grub2/force_efi_extra_removable` de `grub-efi-amd64`, y hacen lo que asume el hook? | Plantillas debconf del paquete `grub2` |
| G-04 | Estado actual de Secure Boot: ¿el shim firmado de trixie arranca en firmware que solo confía en la CA UEFI de Microsoft de 2023 (la CA de 2011 caduca/caducó en 2026)? ¿Hay riesgo de que el Seagate no arranque o de que se actualice la DBX? | Debian wiki SecureBoot, anuncios de Microsoft y Debian |
| G-05 | ¿En el arranque real de la Live, el servicio `novora-live-lockdown.service` (sysinit, `Before=udisks2`) corre **antes** de cualquier montaje automático? Revisa también `systemd-analyze verify` por ciclos de orden. | VM (T02) |
| G-06 | ¿Las variables udev `ID_SERIAL_SHORT` / `ID_WWN` del puente USB del Seagate coinciden con la columna `SERIAL`/`WWN` de `lsblk`? Si no coinciden, el diseño falla de forma segura (el Seagate queda bloqueado), pero hay que saberlo. | Documentación de udev / `udevadm info` en VM con disco USB virtual (`-device usb-storage,serial=...`) |

### P1 — Construcción y arranque

| # | Pregunta concreta |
|---|---|
| G-07 | En el live-build de trixie: ¿son válidas `--bootloaders "grub-efi,syslinux"` (sintaxis exacta), `--iso-application`, `--bootappend-live` y `--debian-installer none`? ¿Sigue existiendo `--hostname`? ¿Cuáles son los valores por defecto de `--firmware-chroot`, `--firmware-binary` y `--uefi-secure-boot`? |
| G-08 | Comprueba la **existencia en trixie amd64** de cada paquete de `config/package-lists/novora.list.chroot` (0.1.1), en especial los marcados `[VERIFICAR]`: `firmware-linux`, `firmware-iwlwifi`, `firmware-realtek`, `firmware-sof-signed`, `grub-efi-amd64`, `grub-efi-amd64-signed`, `shim-signed`, `efibootmgr`, `smartmontools`, `usbutils`, `pciutils`, `python3-venv`. Indica el área (`main`, `contrib`, `non-free-firmware`) y si alguno entra en conflicto (por ejemplo `grub-efi-amd64` frente a `grub-pc`). |
| G-09 | Ejecuta T01 si puedes: `sudo bash scripts/build-iso.sh` en una VM Debian 13 limpia. Entrega `build.log`, `.sha256`, `.packages` y todas las líneas `NOVORA AVISO`. |
| G-10 | Ejecuta T02: arranque en QEMU + OVMF. Entrega una captura del menú (no debe haber d-i), la salida de `sudo novora-disk-guard status` (todo `ro=True`), el escritorio, la red y el audio. |

### P1/P2 — Compatibilidad y rendimiento

| # | Tema |
|---|---|
| G-11 | **Plasma 6 + Wayland con NVIDIA RTX 3050 Laptop** (híbrido Intel/NVIDIA): ¿qué hace nouveau en trixie con Ampere (GSP, reclocking)? ¿Qué pasos y riesgos tiene el controlador propietario (`non-free`, DKMS, firma MOK con Secure Boot)? ¿Cuál es la ruta X11 de contingencia? |
| G-12 | **Wine en trixie (10.0)**: ¿hace falta `wine32` + multiarch i386 para apps de 32 bits, o el WoW64 nuevo ya es viable en el paquete de Debian? Bottles/Proton por Flatpak: límites, antitrampas y DirectX vía DXVK/VKD3D. |
| G-13 | **Seagate USB 3.0 como disco de sistema**: plan de medición **solo lectura** (`smartctl -d sat`, `dmesg`, `lsusb -t`, `fio --readonly`) y umbrales objetivos para bloquear el despliegue. Sin cifras inventadas. |
| G-14 | **Alternativas de base:** propón cambiar Debian KDE solo si hay un motivo técnico fuerte, documentado y con trade-offs. No cambies la base sin aprobación del usuario. |

### P2 — Interfaz y experiencia de instalación

| # | Tema |
|---|---|
| G-15 | Propuesta de identidad visual NOVORA en Plasma 6: barra superior, dock inferior, lanzador, temas claro y oscuro, HiDPI y accesibilidad. Debe ser **original**: sin iconos, marcas ni recursos de Apple. Estima el coste de los efectos en equipos modestos. |
| G-16 | Experiencia del instalador guiado para alguien sin conocimientos técnicos, compatible con el flujo de `novora-install` (auditoría → confirmación escrita → desbloqueo → instalación). |

## 4. Desacuerdos que conviene buscar a propósito

No votes por consenso. Si tu evidencia contradice a Claude, gana la evidencia. Revisa en especial:

- ¿El bloqueo en solo lectura del kernel es una protección suficiente para el disco **interno** o existen vías de escritura que no contempla? Por ejemplo: dispositivos dm/LVM activados antes del bloqueo, `nvme format`/comandos admin, escritura SCSI passthrough (`sg_*`), o el firmware.
- ¿La decisión de **instalador propio sin particionado** (v0.2) es mejor que adaptar Calamares, o hay una forma documentada de restringir los dispositivos en Calamares que Claude no encontró?
- ¿Debe retirarse `gparted`/`parted` de la Live, o basta con el bloqueo?

## 5. Formato de entrega

Entrega `AUDITORIA-GEMINI.md` con los **10 encabezados obligatorios** del encargo original (§7). Añade una sección final **«Contraste con Claude»** con una tabla de este tipo:

| ID Claude / G-xx | Postura de Claude | Postura de Gemini | Evidencia | Resolución propuesta |
|---|---|---|---|---|

Actualiza la matriz T01–T12 con los estados `PASÓ / FALLÓ / PENDIENTE / NO APLICA`. Termina con el **veredicto explícito** sobre si es seguro avanzar a la instalación física (se espera **NO**, salvo evidencia completa de T01–T12).

---

### Mensaje breve para acompañar los archivos

> Audita NOVORA OS siguiendo `NOVORA-OS-0.1-AUDITORIA-CLAUDE-GEMINI-1.md` y este encargo. Primero haz tu ronda independiente sobre el 0.1 original. Después contrasta con `AUDITORIA-CLAUDE.md` y la rama 0.1.1, y verifica los puntos G-01 a G-16 con fuentes oficiales o pruebas en VM. No toques discos físicos. Entrega `AUDITORIA-GEMINI.md` con veredicto y tabla de contraste.
