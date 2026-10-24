# NOVORA OS — Plan de correcciones (P0 primero)

**Base:** `AUDITORIA-CLAUDE.md` del 24/10/2026, rama 0.1.1. Pendiente de cruzar con `AUDITORIA-GEMINI.md`.
**Regla:** una tarea solo pasa a «hecha» con evidencia: comando, log, hash o captura de la VM. Sin evidencia, sigue PENDIENTE.

## P0 — Seguridad de almacenamiento y arranque (bloqueante)

| ID | Corrección | Estado en 0.1.1 | Condición objetiva de aceptación |
|---|---|---|---|
| P0-1 | Quitar d-i del menú de arranque (`--debian-installer none`) | Hecho en el código | Menú de arranque de la ISO sin entradas «Install» / «Graphical install» (captura T02) |
| P0-2 | Todos los discos en solo lectura del kernel al arrancar la Live (udev + `novora-live-lockdown.service`) | Hecho; probado con loop | En T02: `novora-disk-guard status` muestra `ro=True` en cada disco y partición; `mkfs.ext4` sobre el disco «Windows» falla con EPERM |
| P0-3 | `lockdown` aborta («NO SEGURO») si hay montajes en escritura previos | Hecho | Prueba en VM: montar una partición en escritura antes del servicio → el servicio informa NO SEGURO |
| P0-4 | Auditor fail-closed (B00–B13) | Hecho; 23 pruebas | Los 13 escenarios de `test_storage.py` pasan en la ISO real (`python3 -I` desde la Live) |
| P0-5 | Identidad estable (serie/WWN + tamaño + PTUUID) y cancelación ante ambigüedad o desconexión | Hecho; probado con árboles simulados | T05 y T06 en VM con dos discos virtuales con serie (`-device ...,serial=`) |
| P0-6 | Desbloquear solo el disco autorizado; hermanas en solo lectura; regla udev que vuelve a bloquear tras releer la tabla | Hecho; 25/25 con loop | T03 y T08: hash SHA256 del disco «Windows» y de cada partición hermana idéntico antes y después de instalar |
| P0-7 | GRUB sin NVRAM (`--no-nvram --force-extra-removable`), efibootmgr de solo lectura, `efivarfs` en solo lectura, `installEFIFallback: false` | Hecho; probado con herramientas simuladas | T04: `OVMF_VARS.fd` con el mismo hash antes y después; la ESP del Seagate contiene `EFI/BOOT/BOOTX64.EFI` (shim) y arranca con Secure Boot activado |
| P0-8 | Rechazar BIOS/Legacy (B13 + envoltorio) | Hecho | En VM con SeaBIOS, el auditor devuelve 3 y el envoltorio no ejecuta GRUB |
| P0-9 | Bloquear el instalador en hardware físico | Hecho (`systemd-detect-virt`) | Fuera de una VM, `novora-install` sale con código 4 sin escribir nada |
| P0-10 | Confirmar que ningún otro módulo de Calamares/Debian llama a `grub-install`/`efibootmgr` sin envoltorio | **PENDIENTE** | `build.log` sin líneas «NOVORA AVISO», o cada una analizada y resuelta |
| P0-11 | Instalador sin particionado para el Seagate (`novora-installer`, v0.2) | **PENDIENTE (diseño)** | T08 PASÓ con «Borrar disco» imposible por diseño: la herramienta nunca abre el disco completo para escribir |
| P0-12 | Salud del Seagate (solo lectura) | **PENDIENTE** | `smartctl` sin sectores pendientes ni reasignados en aumento; `dmesg` sin resets durante 30 minutos de lectura con `fio --readonly` |
| P0-13 | T11: Windows arranca sin el disco Linux | **PENDIENTE** | VM con Windows 11 (OVMF + TPM virtual): arranque normal, sin pedir clave de BitLocker, con la ESP de Windows sin cambios (hash) |

## P1 — Construcción y arranque

| ID | Corrección | Estado | Aceptación |
|---|---|---|---|
| P1-1 | Log, manifiesto, SHA256 relativo, `--clean`, comprobación de anfitrión y espacio | Hecho; probado con `lb` simulado | T01 real: `sha256sum -c` correcto; `.packages` no vacío |
| P1-2 | `hostname`/`username` vía `--bootappend-live` | Hecho | En la Live, `hostname` devuelve `novora-os` |
| P1-3 | Verificar en trixie: `--bootloaders "grub-efi,syslinux"`, `--iso-application`, paquetes `[VERIFICAR]` | **PENDIENTE** | `lb config` y `lb build` sin errores |
| P1-4 | Konsole con `--hold` | Hecho | Captura del resultado del auditor visible |
| P1-5 | Ejecutar Calamares desde `novora-install` en Wayland/X11 | **PENDIENTE** | Calamares abre como root y solo lista el disco autorizado |
| P1-6 | Firmware Wi-Fi/audio; ruta gráfica (nouveau / NVIDIA) | Parcial (paquetes) | T09 con estado por componente |

## P2 / P3

- P2-1: `wine32` + multiarch i386 en un hook (requiere decisión 7). P2-2: Bottles por Flatpak. P2-3: tema NOVORA en Plasma 6 (barra superior, dock) sin recursos de Apple. P2-4: suite de aplicaciones de prueba.
- P3-1: repositorio git con licencia (sugerencia: GPL-3.0-or-later para scripts, coherente con Calamares). P3-2: CI que ejecute `tests/run-tests.sh` sin la parte de loop. P3-3: releases `0.1.1-live` → `0.2-installer-vm` → `0.3-hardware-pilot`.

## Matriz de pruebas (estado al 24/10/2026)

| ID | Escenario | Estado | Evidencia |
|---|---|---|---|
| T01 | Compilar en Debian 13 | PENDIENTE | Espejos de Debian bloqueados en el entorno de auditoría |
| T02 | Live en VM UEFI | PENDIENTE | — |
| T03 | Windows + Seagate simulados | PENDIENTE (kernel: PASÓ con loop, E-04) | `tests/test_guard_loop.sh` |
| T04 | ESP interna + externa | PENDIENTE (envoltorio: PASÓ simulado, E-05) | `tests/test_wrappers_and_build.sh` |
| T05 | Intercambio de `sdX` | PENDIENTE (lógica: PASÓ, E-06) | `test_T05_resolves_by_identity_after_sdX_swap` |
| T06 | Serie desconocida / desconexión | PENDIENTE (lógica: PASÓ) | `test_T06_unplugged_fails_closed`; E-04 paso 6 |
| T07 | 4 TB MBR/GPT | PENDIENTE (lógica: PASÓ) | `test_partition_beyond_mbr_limit_blocked`, `test_4k_logical_sector_warns` |
| T08 | Particiones con datos | PENDIENTE — riesgo residual con Calamares | Prueba H |
| T09 | KDE / red / audio / GPU | PENDIENTE | — |
| T10 | APT / Flatpak / Wine / toolchains | PENDIENTE | — |
| T11 | Windows sin el disco Linux | PENDIENTE | — |
| T12 | E/S defectuosa / sin espacio | PENDIENTE | Propuesta: `dm-error`/`dm-flakey` en VM |
