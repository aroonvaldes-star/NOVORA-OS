# NOVORA OS — Encargo para Codex: instalador en el Seagate (v0.2)

**Fecha:** 24 de octubre de 2026
**Base:** rama `main` (0.1.1 + PR #1). Lee antes `docs/AUDITORIA-CLAUDE.md`, `docs/revision/CONSOLIDADO-RONDA-2.md` y `config/includes.chroot/usr/local/sbin/novora-disk-guard`.
**Entrega:** un PR con código, pruebas y documentación. **No se ejecuta nada sobre discos físicos.**

> **Reglas que no se negocian**
> - Prioridad: datos y arranque de Windows > integridad del Seagate > estabilidad > compatibilidad > rendimiento > diseño visual.
> - **Nunca** se toca el disco interno de Windows: ni sus particiones, ni su ESP, ni el BCD, ni la NVRAM. Nada de `bcdedit`, `bcdboot`, `efibootmgr -c` ni `grub-install` sin `--no-nvram`.
> - **Nunca** se formatea, mueve ni convierte (MBR → GPT) la partición NTFS de datos del Seagate. Solo se **reduce** con la herramienta oficial de Windows.
> - Fail-closed: ante cualquier duda (disco no identificado, tamaños que no cuadran, más particiones de las previstas, firma de sistema de archivos inesperada) el instalador **se detiene sin cambiar nada**.
> - Las pruebas destructivas se hacen **solo** con discos virtuales en una VM. No declares nada «funcional» sin evidencia; lo no ejecutado se marca **PENDIENTE**.
> - No pidas ni guardes números de serie, claves de BitLocker ni contraseñas LUKS en registros o informes.

## 1. Situación del usuario

- **Equipo:** laptop con Windows 11 en el disco interno, posiblemente con BitLocker, y una RTX 3050 Laptop híbrida.
- **Disco destino:** Seagate Expansion de 4 TB por USB:
  - tabla **MBR**, puente USB con **sectores lógicos de 4K**;
  - **una partición NTFS con datos que se conservan**.
- **No tiene memoria USB.** El arranque debe salir del propio Seagate.
- **Decisiones del usuario:** **ext4 + Timeshift + LUKS2**. NOVORA se elige con la tecla del menú de arranque (F12/F9/Esc); Windows sigue siendo el predeterminado.

## 2. Diseño elegido (opción A de la revisión)

```
Seagate (MBR, sectores de 4K)
├── p1  NTFS  datos del usuario      → solo se REDUCE desde Windows (Resize-Partition)
├── p2  FAT32 512 MiB  "NOVORA-EFI"  → shim + GRUB en /EFI/BOOT/BOOTX64.EFI (ruta extraíble, sin NVRAM)
├── p3  ext4  1 GiB    "NOVORA-BOOT" → /boot sin cifrar (kernel + initramfs)
└── p4  LUKS2 → ext4   "NOVORA-ROOT" → / (192–256 GiB; tamaño elegido por el usuario)
```

- **LUKS2:** `aes-xts-plain64`, clave de 512 bits, `--pbkdf argon2id`, `--sector-size 4096`.
- **ext4:** `noatime`, sin `discard`.
- **Intercambio:** archivo de 4–8 GiB más zram, sin hibernación.
- **Timeshift** en modo rsync, con las instantáneas en `/timeshift` dentro de p4.
- **Teclado latam** también en el initramfs, porque ahí se pide la contraseña LUKS.

Si el Seagate tiene **más de una** partición antes de empezar, MBR no admite las 3 nuevas: **se aborta** y se explica por qué. No se crean particiones extendidas.

## 3. Componentes que hay que construir

### 3.1 Parte Windows: `installer/windows/Instalar-NOVORA.ps1`

PowerShell 5.1 o superior, ejecutado como administrador, con modo `-Simular` por defecto. Es más fácil de auditar que una app WPF; la interfaz puede llegar después.

**1. Comprobaciones de solo lectura, que abortan si fallan:**

| Comprobación | Condición para seguir |
|---|---|
| Firmware | arranque en UEFI |
| Secure Boot | informar del estado |
| BitLocker | informar del estado del disco interno; si está activo, pedir confirmar que la clave de recuperación está guardada **sin pedir la clave** |
| Disco destino | `BusType -eq 'USB'`, **no** es el disco de arranque ni el de sistema, tabla MBR, exactamente 1 partición, NTFS sana, `LogicalSectorSize` (informar 512 o 4096) |
| Partición NTFS | sin BitLocker To Go |
| Hibernación | desactivada (`powercfg /a`) |
| «Inicio rápido» | desactivado (`HiberbootEnabled = 0`) |
| Espacio | `Get-PartitionSupportedSize` permite reducir lo necesario más un margen |

**2. Plan:**
- Mostrar el plan exacto: disco, tamaños, nuevas particiones.
- Pedir que el usuario escriba `NOVORA` para confirmar.
- Guardar un registro en `%PUBLIC%\NOVORA-instalacion.log` sin números de serie.

**3. Ejecución:**
- `Resize-Partition` de p1.
- `New-Partition` p2 + `Format-Volume FAT32 -NewFileSystemLabel NOVORA-EFI`. Investiga y documenta cómo dejar el tipo MBR `0xEF` o si basta `0x0C` para que el firmware la arranque (R-11).
- `New-Partition` p3 y p4 **sin formato** (tipo `0x83`).
- Copiar a p2 los archivos de arranque y el **marcador** `\NOVORA\destino.json`:
  - firma del disco MBR;
  - número, desplazamiento y tamaño de p3 y p4;
  - un ID de instalación aleatorio;
  - versión;
  - **sin** números de serie.

**4. Primer arranque, que el diseño debe resolver con evidencia en VM.** Hay que llegar a la sesión Live sin memoria USB. Opciones candidatas; elige una y justifícala:
- **(a)** Preparar p4 **temporalmente** como partición de preparación, con los archivos de la Live (`vmlinuz`, `initrd`, `filesystem.squashfs`), arrancar con `toram` y que el instalador la convierta después en LUKS2. Requisitos: que el squashfs quepa en el sistema de archivos elegido (FAT32 no admite archivos de más de 4 GiB) y suficiente RAM.
- **(b)** GRUB en p2 con `loopback` a `\NOVORA\novora-os.iso` en la NTFS y `findiso=`. Requisitos: los módulos `ntfs` y `loopback` en el **GRUB firmado** de Debian (R-10) y soporte de NTFS en el initramfs de live-boot (R-14).
- **(c)** Otra opción mejor que encuentres. Ninguna puede tocar Windows ni exigir una memoria USB.

### 3.2 Parte Linux: `config/includes.chroot/usr/local/sbin/novora-instalar-seagate`

Se ejecuta en la sesión Live. Debe reutilizar `novora_storage.py` y `novora-disk-guard`, **no** Calamares. Sustituye a `novora-install`, que sigue bloqueado fuera de una VM.

**1. Encontrar el destino:**
- Buscar p2 por etiqueta y leer `NOVORA/destino.json`.
- Comprobar que la firma del disco, los desplazamientos y los tamaños de p3 y p4 coinciden.
- Comprobar que **ninguna de las dos tiene firma** (`blkid -p` vacío o solo la marca de preparación de la opción a).
- Si algo no cuadra, se detiene.

**2. Desbloquear solo lo necesario:** `novora-disk-guard unlock --apply` **únicamente** para p2, p3 y p4 (por PARTUUID). p1 y el disco interno siguen en solo lectura del kernel. Después, `novora-disk-guard verify`.

**3. Crear el sistema:**
- `cryptsetup luksFormat` en p4 con los parámetros del §2. La contraseña la escribe el usuario dos veces en la terminal y nunca se registra.
- `mkfs.ext4` en p3 y en el volumen abierto de p4.

**4. Instalar el sistema:**
- Copiar el sistema de la Live (`unsquashfs` o `rsync -aHAX` desde el squashfs, sin la configuración propia de la Live).
- Crear el usuario, configurar `fstab` y `crypttab` (por UUID).
- `KEYMAP=y` y latam en el initramfs.
- `update-initramfs -u`.

**5. Arranque:**
- `grub-install --target=x86_64-efi --efi-directory=<p2> --boot-directory=<p3> --removable --no-nvram` (a través de `grub-install-guarded`).
- `shim` en `EFI/BOOT/BOOTX64.EFI` y `update-grub`.
- Comprobar después que `efibootmgr` no cambió nada, comparando la salida de antes y después.

**6. Recuperación:**
- `cryptsetup luksHeaderBackup` a un archivo que el usuario debe sacar a **otro** medio. Avisarle de forma explícita.
- Configurar Timeshift (rsync, dispositivo p4).

**7. Cerrar:**
- Desmontar todo y `cryptsetup close`.
- Volver a dejar p2, p3 y p4 en solo lectura.
- Mostrar un resumen.

### 3.3 Pruebas obligatorias (QEMU + OVMF)

Montaje de la VM:
- **Disco «interno» virtual:** GPT, ESP, una NTFS que simula Windows y archivos de muestra con su SHA256 anotado.
- **Disco «Seagate» virtual:** `usb-storage`/`scsi-hd` con `logical_block_size=4096`, MBR con una NTFS **llena de archivos** con su SHA256 anotado.
- **`OVMF_VARS`** con su SHA256 anotado.

| ID | Prueba | Criterio para pasar |
|---|---|---|
| I-01 | Script de Windows en modo `-Simular` contra un disco virtual (Windows en VM, o pruebas Pester con cmdlets simulados) | No cambia nada y el plan es correcto |
| I-02 | Ejecución real del script en una VM Windows con un disco USB virtual | NTFS reducida, p2–p4 creadas, **los SHA256 de los archivos de p1 no cambian** |
| I-03 | Arranque desde p2 en OVMF eligiendo el disco en el menú de arranque | Llega a la sesión Live |
| I-04 | `novora-instalar-seagate` completo | Arranca el sistema instalado, pide la contraseña LUKS con teclado latam y se llega al escritorio |
| I-05 | Integridad | Imagen del disco interno, SHA256 de p1 y `OVMF_VARS` **sin cambios** |
| I-06 | Fail-closed: marcador alterado, tamaños distintos, p4 con una firma ext4 existente, 2 particiones previas, destino que no es USB | Se aborta sin escribir nada (comparar con `sha256sum` del disco antes y después) |
| I-07 | Secure Boot activo en OVMF (con claves de Microsoft) | Arranca con shim; si no, documentar por qué |
| I-08 | Timeshift: crear una instantánea, romper un paquete y restaurar | El sistema vuelve a arrancar |
| I-09 | `luksHeaderBackup` y restauración en una copia de p4 | Se puede abrir con la copia |

## 4. Preguntas abiertas que debes responder con fuente o evidencia

- R-10: ¿qué módulos trae el `grubx64.efi` firmado de Debian trixie?
- R-11: ¿basta el tipo `0x0C` o hace falta `0xEF` en MBR para la ruta extraíble?
- R-12: ¿`Resize-Partition` funciona bien con un puente USB de 4K?
- R-14: ¿live-boot con `findiso` sobre NTFS?
- R-16: ¿elegir otro disco una vez en el menú de arranque altera las PCR de BitLocker?

Marca cada una como CONFIRMADO, REFUTADO o PENDIENTE.

## 5. Formato de entrega

- PR contra `main` con:
  - `installer/windows/`;
  - `novora-instalar-seagate`;
  - pruebas automáticas en `tests/` que se puedan ejecutar sin hardware: lógica del marcador, comprobaciones *fail-closed* y plan, con discos *loop* donde se pueda;
  - `docs/INSTALACION-SEAGATE-V0.2.md`.
- En la descripción del PR:
  - la tabla I-01–I-09 con su estado y evidencia;
  - las respuestas del §4;
  - la opción elegida para el primer arranque y por qué.
- Veredicto explícito sobre si es seguro probarlo en el equipo real. Se espera **NO** hasta que I-01–I-09 pasen en VM.
