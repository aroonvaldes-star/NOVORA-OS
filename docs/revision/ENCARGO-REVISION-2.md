# NOVORA OS 0.1.1 — Encargo de revisión cruzada, ronda 2 (Gemini y Codex)

**Fecha:** 24 de octubre de 2026
**De:** Claude (autor de la rama 0.1.1)
**Para:** Gemini (fuentes oficiales y compatibilidad) y Codex (revisión de código y pruebas)
**Adjuntos:** `NOVORA-OS-0.1.1.zip` (código completo), `AUDITORIA-CLAUDE.md`, `ATLAS.md`, `DESARROLLO-Y-COMPATIBILIDAD.md`, `SEGURIDAD-ACTUALIZACIONES-APARIENCIA.md` y, si los tienes, `AUDITORIA-GEMINI.md` de la ronda 1.

> **Reglas que no se negocian**
> - Ninguna operación sobre discos físicos: ni el disco interno de Windows, ni su ESP, ni la NVRAM, ni el Seagate. Las pruebas destructivas se hacen **solo** con discos virtuales desechables de una VM.
> - Prioridad: datos y arranque de Windows > integridad del Seagate > estabilidad > compatibilidad > rendimiento > diseño visual.
> - No declares nada «funcional» ni «seguro» sin evidencia (comando, log, hash o captura). Lo no ejecutado se marca **PENDIENTE**; lo no comprobado en una fuente, **NO VERIFICADO**.
> - No pidas ni publiques números de serie, claves de BitLocker, contraseñas LUKS ni credenciales.
> - Si no tienes ejecución de comandos o acceso a la web, dilo al principio.
> - No votes por consenso con Claude: si tu evidencia lo contradice, gana la evidencia.

---

## 1. Estado real (sin adornos)

- **La ISO nunca se ha construido ni arrancado.** Claude no tuvo acceso a `deb.debian.org`. Todo lo probado (196 comprobaciones en `tests/run-tests.sh`) usa programas simulados: motor de IA falso, Wine, GPU, `apt`, `systemctl` y discos *loop*.
- **Veredicto de Claude:** 0.1.1 → APTO PARA VM (tras construir la ISO) · hardware real → **BLOQUEADO**.
- **El instalador nuevo (§3) es solo diseño:** todavía no hay código.

## 2. Parte A — Revisión del OS (todo lo añadido después de la ronda 1)

Componentes a revisar dentro del zip:

| Componente | Dónde | Qué es |
|---|---|---|
| Protección de discos | `usr/local/sbin/novora-disk-guard`, `usr/lib/novora/novora_storage.py`, regla udev, `novora-live-lockdown.service`, envoltorios de GRUB/efibootmgr, hook 9000 | Bloqueo de solo lectura en la Live, auditor *fail-closed* |
| ATLAS | `usr/lib/novora/atlas/novora_atlas/*.py` | Asistente local: chat, pantalla (OCR), archivos y Office, notas, **agente con herramientas**, **investigación con citas**, **memoria SQLite FTS5**, **resumen diario y rutinas (systemd del usuario)**, Agent Skills, modo nube opcional vía OmniRoute en 127.0.0.1 |
| Política de órdenes | `policy.py`, `agente.py` (`auto_runnable`, `check_path`) | Lista prohibida, confirmación de un solo uso, autoejecución solo de lectura |
| Panel web | `web.py`, `ui.py` | 127.0.0.1, token, Host/Origin, CSP |
| Desarrollo | `novora-dev`, hook 9200 | .NET 8/10, Rider y Android Studio desde tarball, adb y scrcpy |
| Apps de Windows | `novora-win`, hook 9300 | Wine 11 de WineHQ (Wine 10 de Debian como respaldo), DXVK y VKD3D-Proton, perfiles por app, ClamAV antes de ejecutar |
| GPU | `novora-gpu` | Mesa por defecto; driver NVIDIA 550 bajo demanda con MOK |
| Seguridad y actualizaciones | hook 9400, `novora-antivirus`, `novora-actualizar`, `etc/apt/apt.conf.d/*` | ClamAV, firewalld, AppArmor, unattended-upgrades solo de seguridad, Timeshift antes de `apt` |
| Catálogo | `novora-apps` | GenOffice, Spotifast, Zuno, Huntly, OmniRoute, Claude Code, Codex, Gemini CLI y Copilot CLI con verificación SHA256 |
| Aspecto | look-and-feel `org.novora.desktop`, `layout.js` | Barra superior y dock al estilo macOS, original |

### Preguntas de la parte A

**P0 — seguridad**

| # | Pregunta |
|---|---|
| R-01 | **(Codex)** Intenta saltarte la política de ATLAS: busca órdenes que `policy.classify` marque como `SOLO_LECTURA` o `CONFIRMAR` pero que puedan escribir en discos, ejecutar código arbitrario o leer secretos. Incluye `git` con alias o `-c`, `find`, `sed`, `sort -o`, `tee` y otras opciones de programas de solo lectura que escriben archivos. Para cada caso entrega una prueba que falle hoy. |
| R-02 | **(Codex)** Modo agente: ¿puede un texto malicioso (un archivo leído, el OCR o un documento indexado) lograr que el agente ejecute algo sin confirmación, lea `~/.ssh` o escriba fuera de `$HOME`? Revisa `auto_runnable`, `check_path` (enlaces simbólicos, `..`, rutas relativas a `$HOME`) y `propose_write` (condición de carrera entre propuesta y confirmación). |
| R-03 | **(Codex)** Panel web: CSRF, DNS rebinding, fuga del token (URL, historial, `Referer`) y XSS en `ui.py` (todo el HTML pasa por `esc()`). |
| R-04 | **(Codex)** `novora-apps`: verificación del `digest` de GitHub, extracción de tar con `filter="data"`, `npm` en `~/.local` e inyección en nombres de assets. |
| R-05 | **(Gemini + Codex)** `novora-disk-guard` y el bloqueo de solo lectura: ¿existen vías de escritura que no contempla? Por ejemplo dm o LVM activados antes del bloqueo, comandos admin de NVMe, SCSI passthrough o montajes automáticos tempranos. |

**P1 — construcción y arranque**

| # | Pregunta |
|---|---|
| R-06 | **(Gemini)** Comprueba en Debian 13 amd64 cada paquete de `config/package-lists/novora.list.chroot`, en especial los marcados `[VERIFICAR]`, además de `llama.cpp-tools` (trixie o trixie-backports), `poppler-utils`, `espeak-ng`, `libnotify-bin`, `fonts-inter` y `papirus-icon-theme`. Indica el área (main, contrib, non-free, non-free-firmware). |
| R-07 | **(Gemini)** Estado actual de WineHQ para trixie: ¿`winehq-stable` 11 sigue exigiendo i386 (bug 59343)? ¿DXVK y VKD3D-Proton tienen versiones recientes compatibles? |
| R-08 | **(Gemini)** NVIDIA RTX 3050 Laptop (Ampere) en trixie: driver 550 de `non-free` o uno más nuevo, Wayland en Plasma 6, firma MOK con Secure Boot y PRIME. |
| R-09 | **(Ambos, si tenéis VM)** Construye la ISO (`sudo bash scripts/build-iso.sh` en Debian 13 limpio) y arráncala en QEMU + OVMF: menú sin d-i, `novora-disk-guard status` con todo en `ro=True`, escritorio, teclado latam, ATLAS sin modelo y `novora-win estado`. Entrega `build.log`, el `.sha256` y capturas. |

## 3. Parte B — Diseño del instalador nuevo (aún sin código)

**Objetivo del usuario:**
- Instalar desde Windows **sin formatear sus datos** y sin perder Windows.
- No tiene memoria USB.
- El Seagate (4 TB, MBR, NTFS, puente USB con sectores lógicos de 4K) tiene sus datos.
- Decisiones del usuario: **ext4 + Timeshift + LUKS2**.

**Diseño propuesto por Claude:**

```
Seagate (MBR)
├── Partición 1: NTFS con los datos del usuario (encogida 1 GiB con «Reducir volumen» de Windows)
│   └── NOVORA\
│       ├── novora-os.iso     (solo para el primer arranque: sesión Live + instalador)
│       ├── arranque.img      ~1 GiB, ext4 SIN cifrar (/boot: kernel e initramfs)
│       ├── sistema.img       192–256 GiB, LUKS2 (aes-xts-plain64, argon2id, sectores de 4096) → ext4
│       └── destino.json      marcador: PARTUUID, tamaño y un ID aleatorio (sin números de serie)
└── Partición 2 (nueva): FAT32 512 MiB "NOVORA-EFI" → shim + GRUB en /EFI/BOOT/BOOTX64.EFI
```

**Flujo previsto:**
1. **En Windows**, un instalador (WPF o PowerShell):
   - Hace comprobaciones de solo lectura: UEFI, Secure Boot, BitLocker, que el destino sea USB, NTFS, espacio libre, «Inicio rápido» e hibernación desactivados, y que la carpeta no esté en OneDrive.
   - Obtiene la confirmación escrita del usuario.
   - Reduce la NTFS 1 GiB, crea la partición FAT32 y copia la ISO y los archivos EFI.
   - Escribe `grub.cfg` y `destino.json`.
   - **No toca el disco interno ni el BCD ni la NVRAM.**
2. **El usuario** pulsa la tecla del menú de arranque (F12/F9/Esc) y elige el Seagate.
3. **GRUB**, desde la FAT32, abre `NOVORA\novora-os.iso` desde NTFS (`loopback` y `findiso=`) y arranca la sesión Live.
4. **En la Live**, el instalador:
   - Comprueba el marcador.
   - Solo crea o formatea **dentro** de los archivos `arranque.img` y `sistema.img`, nunca una partición.
   - Pide la contraseña LUKS2 con el teclado latam y la cuenta del usuario.
   - Copia el sistema y guarda una copia de la cabecera LUKS para otro medio.
   - Reescribe `grub.cfg` para arrancar el sistema instalado, manteniendo una entrada Live de rescate.
5. **En cada arranque**, GRUB abre `arranque.img` desde NTFS y carga el kernel. Un hook propio del initramfs monta la NTFS, conecta `sistema.img` a un dispositivo loop, abre LUKS2 y monta ext4 como `/`.

### Preguntas de la parte B (son las que más preocupan a Claude)

| # | Pregunta | Por qué importa |
|---|---|---|
| R-10 | **Secure Boot:** ¿el `grubx64.efi` **firmado** de Debian trixie incluye los módulos `ntfs`, `loopback`, `ext2`, `iso9660`, `search` y `part_msdos`? ¿Puede cargar `grub.cfg` desde la FAT32 del Seagate? Si no los incluye, ¿cuál es la alternativa sin desactivar Secure Boot (por ejemplo, firmar un GRUB propio con MOK)? | **Riesgo n.º 1 del diseño** |
| R-11 | ¿El firmware UEFI arranca desde un disco USB **MBR** con una partición FAT32 de tipo `0x0C` o `0xEF` por la ruta extraíble `/EFI/BOOT/BOOTX64.EFI`? ¿Permiten `New-Partition -MbrType` o `diskpart set id=ef` crear el tipo `0xEF` en un disco USB? | Si el firmware no lo ve, no arranca |
| R-12 | ¿«Reducir volumen» o `Resize-Partition` funciona bien en una NTFS a través de un puente USB con sectores lógicos de 4K? ¿Hay casos documentados de corrupción? ¿Qué impide reducir (archivos inamovibles, `$MFT`, puntos de restauración)? | Es el único cambio a la tabla de particiones |
| R-13 | Kernel 6.12 de trixie: ¿`ntfs3` es fiable para un archivo de 200 GiB con escritura continua, o conviene `ntfs-3g` (FUSE)? ¿Qué pasa con una NTFS marcada «sucia» por Windows? ¿Funciona `fallocate`? | Riesgo para los datos de la NTFS |
| R-14 | ¿El `live-boot` de trixie admite `findiso=` con la ISO guardada en **NTFS**? ¿Qué módulos o herramientas necesita en el initramfs? | Primer arranque |
| R-15 | Raíz en un loop dentro de NTFS con LUKS2: ¿existe un hook mantenido para `initramfs-tools` en Debian (equivalente al `loop=` de Wubi/lupin) o hay que escribirlo? ¿Qué pasa con `cryptsetup-initramfs` y el teclado de `/etc/default/keyboard` en el initramfs? | Arranque diario |
| R-16 | **BitLocker** del disco interno: elegir el Seagate en el menú de arranque y volver después a Windows, ¿puede cambiar las PCR (por ejemplo la PCR 7 con Secure Boot) y hacer que Windows pida la clave de recuperación? | No perder Windows |
| R-17 | ¿Timeshift en modo rsync copia `/boot` cuando está montado desde otro archivo loop? ¿Cómo restaurar el kernel si falla una actualización? | Recuperación |
| R-18 | ¿Ves un diseño **más seguro** que cumpla las mismas condiciones (sin USB, sin formatear datos, sin tocar Windows)? Por ejemplo: VHDX nativo, una partición en espacio sin asignar sin reducir, u otra idea. Dalo con sus pros y contras. | Alternativas |

## 4. Reparto sugerido

- **Gemini:** R-05 a R-08, R-10 a R-18, con fuente oficial (URL, versión y fecha) en cada respuesta.
- **Codex:** R-01 a R-05 sobre el código, con una prueba automática por cada fallo encontrado (formato `unittest` o el script de shell correspondiente de `tests/`). Si puede, R-09.
- Ambos: si encontráis un fallo **P0**, ponedlo al principio del informe.

## 5. Formato de entrega

Archivo `REVISION-<IA>-RONDA-2.md` con:
1. Lo que pudiste ejecutar o consultar, y lo que no.
2. Hallazgos ordenados P0 → P2: componente, archivo y línea, evidencia, corrección propuesta y prueba.
3. Una tabla con estas columnas:

   | ID | Estado (CONFIRMADO / REFUTADO / NO VERIFICADO / PENDIENTE) | Respuesta | Fuente o evidencia |
   |---|---|---|---|

4. Una sección «Contraste con Claude» con los puntos en los que discrepas.
5. Un veredicto explícito:
   - ¿Es seguro construir y probar la ISO en una VM?
   - ¿Es viable el diseño del instalador o hay que cambiarlo?
   - ¿Es seguro tocar el equipo real? Se espera **NO** hasta pasar T01–T12 en VM.

---

### Mensaje breve para pegar junto a los archivos

> Revisa NOVORA OS 0.1.1 con el encargo `NOVORA-OS-0.1.1-ENCARGO-REVISION-2.md`. No toques discos físicos. Responde las preguntas que te corresponden en la §4 con fuentes oficiales o evidencia y señala primero cualquier fallo P0. Entrega `REVISION-<tu nombre>-RONDA-2.md` con la tabla de estados y un veredicto.
