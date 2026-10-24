# NOVORA OS 0.1 — Auditoría Claude (código y seguridad de instalación)

**Fecha:** 24 de octubre de 2026 · **Revisor:** Claude (configurado como `claude-opus-5-5`), primera ronda independiente; no se vio el informe de Gemini.
**Material auditado:** `NOVORA-OS-v0.1-FUENTES.zip` (6 archivos, sin errores de CRC). Es idéntico, archivo por archivo, al contenido de `NOVORA-OS-v0.1-CODIGO-COMPLETO.md`.
**Entorno de auditoría:** contenedor Linux aislado (Ubuntu 24.04, kernel 6.18.44, root), **sin acceso a `deb.debian.org` ni a `salsa.debian.org`** (el proxy los rechaza con 403). No hay VM, OVMF ni QEMU. **No se tocó ningún disco físico.** Todas las pruebas de disco se hicieron sobre archivos de imagen montados como dispositivos *loop* desechables.

---

## 1. Resumen ejecutivo

| Objeto | Veredicto |
|---|---|
| **NOVORA OS 0.1 (original)** | **APTO SOLO PARA REVISIÓN.** No hay ISO, y el instalador no impide escribir en el disco de Windows, en su ESP ni en la NVRAM del firmware. |
| **NOVORA OS 0.1.1 (parches de esta auditoría)** | **APTO PARA VM**, en cuanto T01 (compilación) pase. El guardián de discos está probado contra el kernel real con discos virtuales; nada se ha probado arrancando una ISO. |
| **Instalación física en el PC con Windows 11 / Seagate de 4 TB** | **BLOQUEADO.** 0.1.1 lo impone en código: `novora-install` se niega a ejecutarse fuera de una VM. |

Resultados principales:

1. **El 0.1 no tiene ninguna protección técnica.** `novora-storage-audit` es un programa aparte: solo avisa, y Calamares lista todos los discos. La configuración de Calamares no tiene ninguna opción para excluir discos ni para quitar «Borrar disco» (revisado en el código fuente de Calamares). Además, `--debian-installer live` añade **un segundo instalador** (d-i) al menú de arranque, que sortea cualquier protección.
2. **Calamares escribe en la NVRAM del firmware.** Ejecuta `grub-install --force` sin `--no-nvram` y, en modo shim, `efibootmgr -c -w` y `BootNext`. Eso cambia el orden de arranque de Windows y puede activar la recuperación de BitLocker.
3. **El auditor original aprueba casos peligrosos.** Probado: devuelve 0 con un destino montado vía LUKS, un disco sin número de serie, una partición fuera del límite MBR y dos discos idénticos conectados (§6, E-03).
4. **Hay un mecanismo de bloqueo que funciona**, demostrado en el kernel 6.18: el indicador de solo lectura del kernel sobre el **disco completo** bloquea todas sus particiones, también tras releer la tabla. Además, Calamares **no lista** los dispositivos en solo lectura (`DeviceList.cpp`, escaneo «not includeReadOnly»). Sobre esto se construyó 0.1.1.
5. **Limitación que no se puede eliminar en el Seagate.** Mientras el disco destino está desbloqueado, el kernel no puede impedir que un particionador borre **otras particiones del mismo disco** (prueba H). Con datos en el Seagate, la instalación con Calamares exige un respaldo verificado o un instalador propio que no particione (v0.2).

## 2. Inventario real del código (0.1)

| Archivo | Función | Estado | Evidencia |
|---|---|---|---|
| `scripts/build-iso.sh` (44 l.) | `lb config` + `lb build` + SHA256 | **Parcial.** Sintaxis correcta; nunca ejecutado de verdad | `bash -n` OK; ShellCheck 0.10.0 sin avisos (solo estilo con `-o all`); sin acceso a los espejos de Debian para T01 |
| `config/package-lists/novora.list.chroot` (36 paq.) | Lista de paquetes | **Parcial.** `wine64` existe en trixie (10.0~repack-6); el resto no se pudo verificar | tracker.debian.org; packages.debian.org bloqueado |
| `.../usr/local/bin/novora-storage-audit` (108 l.) | Listado y evaluación de discos en solo lectura | **Implementado, pero solo avisa** e incluye falsos «aprobados» | E-03 |
| `.../novora-storage-audit.desktop` | Lanzador | **Defectuoso**: `konsole -e` cierra la ventana al terminar y el resultado no llega a leerse | §3 C-13 |
| `docs/INSTALACION-SEAGATE.md` | Guía manual | **Solo propuesta** | — |
| `README.md` | Descripción | Correcto en sus advertencias | — |
| Protección de discos, Calamares personalizado, tema, pruebas, CI | — | **No implementado** | No hay archivos |

## 3. Hallazgos

Las líneas se refieren a los archivos **originales** de 0.1.

| ID | Sev. | Archivo:línea | Causa | Impacto | Reproducción / evidencia |
|---|---|---|---|---|---|
| C-01 | **P0** | `build-iso.sh:27` | `--debian-installer live` incluye el instalador clásico de Debian (d-i) en el menú de arranque | Un segundo instalador con particionado guiado («usar todo el disco») que se arranca **antes** que cualquier protección en la sesión Live | El build oficial de Debian Live 13.2 usa esta misma opción (log oficial, §10). Confirmar en T02 viendo el menú |
| C-02 | **P0** | (ausencia) | El auditor no está conectado a Calamares, y Calamares lista todos los discos | Un clic en «Borrar disco» o «Reemplazar» sobre el disco interno destruye Windows | `partition.conf` (Calamares 95aa33f): no hay clave para filtrar dispositivos ni desactivar el borrado |
| C-03 | **P0** | (Calamares) `bootloader/main.py:633-638, 790-798` | `grub-install --force` sin `--no-nvram`. Ruta shim: `efibootmgr -c -w -d <disco ESP>` + `efibootmgr -n` | Crea o reordena entradas NVRAM y cambia el arranque por defecto. Puede pedir la clave de BitLocker. `-w` puede escribir una firma en el MBR del disco de la ESP | Lectura del código fuente |
| C-04 | **P0** | `novora-storage-audit:90` | BIOS/Legacy solo genera un aviso | En BIOS, Calamares instala GRUB en el MBR del dispositivo elegido en «ubicación del cargador», que por defecto es el primer disco | Windows 11 exige UEFI: el modo BIOS debe bloquearse |
| C-05 | **P0** | `novora-storage-audit:8, 76, 84, 87, 92` | Usa `MOUNTPOINT` (uno solo, sin recorrer hijos). La serie ausente solo se imprime. Lista de *exclusión* de sistemas de archivos (ext4/xfs/btrfs/LUKS/LVM pasan). El límite MBR solo se avisa. No detecta discos gemelos | `return 0` («inspección terminada») en selecciones peligrosas | **E-03**: exit 0 en `luks_mounted`, `no_serial`, `mbr_beyond` y `twins` |
| C-06 | **P0** | `novora-storage-audit:95-96` | Considera ESP cualquier partición `vfat`, sin mirar el tipo de partición (GPT `c12a7328…` / MBR `0xef`). No pregunta qué ESP se usará | Una FAT32 de datos pasa como ESP. Nada impide montar en `/boot/efi` la ESP de Windows | Prueba `test_fat_data_partition_is_not_an_esp` |
| C-07 | **P0** | (ausencia) | La sesión Live monta y escribe discos libremente (udisks, gparted, mkfs) | Incumple T02 («sin escribir discos existentes»). Además, **un sistema de archivos montado en escritura antes del bloqueo sigue escribiendo** | **E-02**, pruebas J y M |
| C-08 | P1 | `build-iso.sh:29` | `--hostname`: no se pudo confirmar en el manual de trixie. Históricamente se ignoraba con syslinux | El nombre de host puede ignorarse o `lb config` puede fallar | Lista de correo debian-live (§10). Alternativa documentada: `hostname=` de live-config |
| C-09 | P1 | `build-iso.sh:37, 43` | `find … -quit` toma cualquier ISO. `sha256sum` guarda la ruta absoluta | Puede publicarse una ISO antigua, y `sha256sum -c` falla en otra carpeta | E-05 (0.1.1 verifica con ruta relativa) |
| C-10 | P1 | `build-iso.sh` (todo) | Sin log, sin manifiesto de paquetes, sin comprobar el anfitrión ni el espacio libre, sin `--clean` | La construcción no es auditable ni repetible | — |
| C-11 | P1 | (Calamares) `main.py:728-736` | `installEFIFallback` copia `grubx64.efi` como `BOOTX64.EFI` | Con Secure Boot, la ruta extraíble queda sin shim y el disco externo no arranca | Código fuente |
| C-12 | P1 | `novora.list.chroot` | Sin paquetes de firmware, sin herramientas SMART, sin listar `grub-efi-amd64-signed`/`shim-signed`; `wine32` ausente | Wi-Fi o audio sin firmware; P0.9 (salud del Seagate) imposible desde la Live; apps Windows de 32 bits fallan | — |
| C-13 | P1 | `.desktop:5` | `konsole -e` sin `--hold` | La ventana se cierra y el usuario no ve los avisos | Comportamiento documentado de Konsole; confirmar en T02 |
| C-14 | P2 | `novora-storage-audit:37, 76` | Muestra la serie completa | Filtra identificadores si se comparte una captura | Requisito §2 del encargo |
| C-15 | P2 | (ausencia) | El medio Live no se excluye explícitamente | Bajo riesgo hoy (iso9660 montado), pero sin política | — |
| C-16 | P3 | (ausencia) | Sin pruebas, sin CI, sin licencia, sin control de versiones | — | — |

## 4. Riesgos para Windows y el Seagate

| Ruta de fallo | 0.1 | 0.1.1 | Pendiente |
|---|---|---|---|
| «Borrar disco» o particionado manual sobre el disco **interno** | Sin protección | El disco está en solo lectura desde el arranque (udev + servicio), Calamares no lo lista y cualquier escritura devuelve EPERM (E-04) | T03 en VM |
| GRUB en la **ESP de Windows** | Solo una advertencia en la guía | La ESP interna es de solo lectura; el envoltorio rechaza una ESP en otro disco o no desbloqueada (E-05) | T04 |
| Cambio de **NVRAM** / orden de arranque / BitLocker | Siempre ocurre | `--no-nvram`, efibootmgr de solo lectura y `efivarfs` remontado en solo lectura | T04, T11 |
| Instalador d-i del menú de arranque | Presente | Eliminado (`--debian-installer none`) | T02 |
| Cambio de orden `sda`/`sdb`, discos gemelos, serie vacía, desconexión | Sin control | Identidad por serie/WWN + tamaño + PTUUID; ante ambigüedad, cancela (E-01, E-04 paso 6) | T05, T06 |
| **Otras particiones del Seagate** durante la instalación | Sin protección | **Parcial**: siguen en solo lectura y la regla udev las vuelve a bloquear tras releer la tabla, pero **no se puede impedir que se reescriba la tabla del Seagate** (prueba H) | Instalador sin particionado (v0.2) o respaldo completo verificado |
| FS montado en escritura antes del bloqueo | — | El bloqueo corre en `sysinit` antes de udisks y reporta «NO SEGURO» si encuentra montajes en escritura | Confirmar el orden en un arranque real (T02) |
| Usuario Live con `sudo` sin contraseña | — | El guardián protege contra **errores**, no contra un usuario que lo desactive a propósito | Documentado |

**MBR en un disco de 4 TB.** MBR guarda inicio y longitud de cada partición en campos de 32 bits contados en sectores lógicos. Con sectores de 512 B el máximo direccionable es 2³² × 512 B = 2 TiB (≈ 2,2 TB). En un disco de 4 TB (≈ 3,64 TiB) unos 1,6 TiB quedan inaccesibles. Si el puente USB del Seagate expone sectores lógicos de **4096 B**, el límite sube a 16 TiB, pero la tabla queda **ligada a ese puente**: con otra carcasa o por SATA directo (512e), los desplazamientos dejan de coincidir y las particiones se vuelven ilegibles. Se comprueba sin escribir con `lsblk -o NAME,SIZE,PTTYPE,LOG-SEC,PHY-SEC`. 0.1.1 bloquea las particiones que pasan del límite (B07) y avisa en ambos casos (W07, W08). **No se recomienda convertir a GPT in situ** sin un respaldo completo verificado y evaluación especializada.

**UEFI con MBR.** El firmware UEFI puede arrancar una ESP de tipo `0xEF` en MBR desde la ruta extraíble, pero depende de cada fabricante (T07).

**Arranque independiente.** Con GRUB en `EFI/BOOT/BOOTX64.EFI` del Seagate y sin entradas NVRAM, el Seagate se arranca desde el menú de arranque único del firmware. Windows conserva su orden y su ESP intactos. Tocar ajustes del firmware (Secure Boot, arranque USB) también puede pedir la clave de BitLocker: tenla a mano.

## 5. Correcciones propuestas (rama 0.1.1 — incluida completa en el ZIP)

| Archivo | Cambio | Compatibilidad / regresión posible |
|---|---|---|
| `scripts/build-iso.sh` | `--debian-installer none`; `--bootappend-live "… hostname=novora-os username=novora"`; `--bootloaders "grub-efi,syslinux"`; comprobación de anfitrión trixie, herramientas y ≥25 GiB; `--clean` y `--work` confinados al proyecto; `build.log` con versión de live-build y commit de git; ISO con nombre fijo; manifiesto `.packages`; SHA256 relativo; copia de hooks y docs | La sintaxis de `--bootloaders` y la existencia de `--iso-application` en trixie **no están verificadas** (T01) |
| `usr/lib/novora/novora_storage.py` (nuevo) | Biblioteca común: árbol completo de `lsblk`, montajes recursivos, ESP por tipo de partición, límites MBR, identidad estable y resolución por identidad | Requiere util-linux ≥ 2.37 (columnas START, MOUNTPOINTS); trixie trae una versión posterior |
| `novora-storage-audit` (v0.2) | Fail-closed con códigos B00–B13 / W05–W09; pide la ESP explícitamente; serie enmascarada; `--emit-allowlist` (0600, en `/run`); `--json` | Las salidas de código cambian (3 = bloqueado) |
| `usr/local/sbin/novora-disk-guard` (nuevo) | `lockdown` (lsblk + sysfs independiente + efivarfs en solo lectura; aborta ante montajes en escritura), `unlock --apply` (solo el disco autorizado, hermanas en solo lectura), `verify`, `status` | Si la identidad udev ≠ lsblk, el Seagate queda bloqueado (fallo seguro: la instalación no avanza) |
| `etc/udev/rules.d/90-novora-live-readonly.rules` + `usr/lib/novora/novora-udev-ro` (nuevos) | Todo disco o partición nuevo queda en solo lectura, salvo los PARTUUID autorizados. Solo con `boot=live` | Hay una ventana breve entre la relectura de la tabla y el evento udev |
| `etc/systemd/system/novora-live-lockdown.service` (nuevo) | Bloqueo en `sysinit`, antes de udisks y del gestor de pantalla | Posibles ciclos de orden de systemd: revisar `systemd-analyze verify` en T02 |
| `usr/lib/novora/grub-install-guarded` (nuevo) | Solo `x86_64-efi`; ESP y raíz en el mismo disco y desbloqueadas; añade `--no-nvram --force-extra-removable` | `--force-extra-removable` es un parche de Debian: **verificar en trixie**. Si no existe, GRUB falla (fallo seguro) |
| `usr/lib/novora/efibootmgr-readonly` (nuevo) | Solo deja pasar listados; bloquea y registra el resto | Calamares no recibe error (no lo comprueba en esas llamadas) |
| `config/hooks/normal/9000-novora-hardening.hook.chroot` (nuevo) | Activa el servicio; reescribe `bootloader.conf` (envoltorios, `installEFIFallback: false`); debconf `grub2/update_nvram=false` y `grub2/force_efi_extra_removable=true`; oculta «Install Debian»; avisa de llamadas directas a GRUB; **falla la construcción** si falta `bootloader.conf` | Si Debian invoca GRUB desde otro script, el aviso aparece en `build.log` |
| `usr/local/sbin/novora-install` + `.desktop` (nuevos) | Bloqueo → auditoría → confirmación escrita `INSTALAR <6 últimos del PARTUUID>` → desbloqueo → verificación → Calamares → bloqueo. **Se niega fuera de una VM** | Lanzar Calamares como root desde Konsole en Wayland está sin probar |
| `novora.list.chroot` | + firmware, `grub-efi-amd64(-signed)`, `shim-signed`, `efibootmgr`, `smartmontools`, `usbutils`, `pciutils`, `python3-venv` | Marcados `[VERIFICAR]`. Si falta uno, `lb build` falla (T01) |
| `.desktop` del auditor | `konsole --hold` | — |
| `tests/` (nuevo) | `run-tests.sh` y tres baterías (§6) | — |

El diff completo contra 0.1 se entrega como `novora-os-0.1-to-0.1.1.patch`.

## 6. Pruebas ejecutadas / no ejecutadas

**Entorno:** Ubuntu 24.04, kernel 6.18.44, Python 3.13, util-linux 2.39.3, ShellCheck 0.10.0, root, dispositivos loop. Comando: `sudo bash tests/run-tests.sh` → `TODAS LAS PRUEBAS PASARON` (23 + 20 + 25 comprobaciones).

| ID | Qué | Resultado |
|---|---|---|
| E-01 | Integridad: `unzip -t`; los 6 archivos del ZIP coinciden con el `.md`; SHA256 en el anexo | PASÓ |
| E-02 | Semántica de solo lectura del kernel con loop (A–M, abajo) | Evidencia, no pasa/falla |
| E-03 | Auditor **original** con `lsblk` simulado: `luks_mounted`, `no_serial`, `mbr_beyond`, `twins`, `base` | **Los 5 devolvieron exit 0** («Inspección terminada») |
| E-04 | `test_guard_loop.sh`: discos virtuales «Windows» y «Seagate»; lockdown, unlock, mkfs en Windows, relectura de tabla + regla udev, disco desconocido, desconexión, bloqueo final | 25/25 PASÓ (la primera ejecución dio 23/25 por un error de la propia prueba, corregido; ver nota) |
| E-05 | `test_wrappers_and_build.sh`: envoltorio de GRUB (4 casos), efibootmgr (5 casos), `build-iso.sh` con `lb` simulado (10 casos) | 20/20 PASÓ |
| E-06 | `test_storage.py`: 23 pruebas de evaluación, resolución por identidad (T05/T06 simulados), CLI y sysfs | 23/23 PASÓ |
| E-07 | Hook sobre el `bootloader.conf` **real** de Calamares: YAML válido, claves sustituidas, lanzador oculto, fallo si falta el archivo | PASÓ |
| E-08 | ShellCheck en todos los scripts; `py_compile` en todo el Python | 0 avisos |

**E-02, semántica de solo lectura (kernel 6.18.44).** Ejecutado con escrituras reales de 512 B y 4 KiB:

```
A) RO solo en disco completo        → disco y p1/p2/p3: EPERM
B) RO solo en p1,p3 (disco en RW)   → p1,p3 EPERM; p2 y DISCO COMPLETO escribibles (desvío)
C) RO en disco + p1 + p3, p2 en RW  → TODO EPERM (el RO del disco se propaga; no puede haber una partición RW)
D/E) mkfs.ext4 con disco en RO      → "Operation not permitted while setting up superblock"
F/G) partx -u / partx -d + -a con disco en RO → las particiones recreadas siguen en ro=1
H) RO en p1,p3, disco en RW, se recrea la tabla → p1,p3 vuelven a ro=0  ← límite clave
J/L) mount (incluso -o rw) de partición RO → "write-protected, mounted read-only"; touch: Read-only FS
K) usuario sin privilegios: blockdev --setrw → Permission denied
M) descriptor abierto ANTES del bloqueo → pwrite EPERM (bloqueado)
   FS montado en RW ANTES del bloqueo → la escritura LLEGA al disco (verificado al remontar)
```

*Nota sobre E-04:* la primera ejecución falló en el paso 7 porque la prueba reasignaba la variable exportada del árbol de discos. Ese fallo destapó una debilidad real: `lockdown` solo bloqueaba lo que veía `lsblk`. Se corrigió en el código: ahora también enumera `/sys/class/block` de forma independiente (`test_sysfs_enumeration`).

**No ejecutadas (todas PENDIENTES):**

| ID | Escenario | Estado | Motivo |
|---|---|---|---|
| T01 | Compilar en Debian 13 | **PENDIENTE** | `deb.debian.org` bloqueado (403). Solo se probó la lógica del script con `lb` simulado |
| T02 | Live en VM UEFI/OVMF | **PENDIENTE** | Sin VM |
| T03 | Disco Windows + Seagate simulados en VM | **PENDIENTE** | Mecanismo del kernel probado con loop (E-04); falta Calamares real |
| T04 | ESP interna + ESP externa | **PENDIENTE** | Envoltorio probado con herramientas simuladas (E-05) |
| T05 | Intercambio de `sdX` | **PENDIENTE** (VM) | Lógica PASÓ con árboles simulados (E-06) |
| T06 | Serie desconocida / desconexión | **PENDIENTE** (VM) | Lógica PASÓ (E-04 paso 6, E-06) |
| T07 | 4 TB MBR/GPT | **PENDIENTE** (VM) | Lógica PASÓ (B07, W07, W08) |
| T08 | Particiones preexistentes con datos | **PENDIENTE** | Riesgo residual documentado (prueba H) |
| T09 | KDE, red, audio, GPU | **PENDIENTE** | Sin ISO ni hardware |
| T10 | APT/Flatpak/Wine/toolchains | **PENDIENTE** | Sin ISO |
| T11 | Windows sin el disco Linux | **PENDIENTE** | Requiere una VM con Windows y OVMF |
| T12 | Errores de E/S y falta de espacio | **PENDIENTE** | Puede simularse con `dm-flakey`/`dm-error` en VM |

## 7. Rendimiento y compatibilidad

- **Medido:** nada de rendimiento. No hay ISO ni hardware.
- **Comprobado en repositorio:** `wine64` existe en Debian 13 (10.0~repack-6; tracker.debian.org). El resto de paquetes no pudo comprobarse (packages.debian.org y los espejos estaban bloqueados) y lo valida T01.
- **Hipótesis a medir, sin cifras inventadas:**
  - El Seagate USB 3.0 de 4 TB es casi seguro un disco mecánico. Como disco de sistema añadirá latencia de acceso aleatorio de varios milisegundos por operación, y las pausas de ~1000 ms reportadas apuntan a problemas de enlace o salud (resets de UAS, sectores reasignados).
  - **No atribuir a KDE** ninguna lentitud antes de medir: `smartctl -a` (con `-d sat` si el puente lo requiere), `dmesg | grep -iE "reset|uas|I/O error"`, `lsusb -t` (debe indicar 5000M) y una lectura sin escritura con `fio --readonly`.
  - Si aparecen errores de E/S o resets, el despliegue físico queda bloqueado.
- **RTX 3050 Laptop:** sin `non-free`, solo funciona nouveau. Su rendimiento en Ampere es limitado, y Wayland en híbrido Intel/NVIDIA depende de PRIME. El controlador propietario requiere el área `non-free`, DKMS y, con Secure Boot, firmar módulos y registrar una clave MOK (decisión 9.6).
- **Wine:** solo 64 bits. Las apps de 32 bits necesitan `dpkg --add-architecture i386` + `wine32` en un hook. Hay que medir el impacto en tamaño de la ISO.
- **Método de medición propuesto:** mismo equipo y mismas condiciones, 5 repeticiones, mediana e intervalo:
  - `systemd-analyze` (arranque);
  - `free -m` / `ps_mem` en reposo a los 5 minutos;
  - tiempo de apertura en frío de Konsole, Dolphin y Kate;
  - `fio --readonly` en el Seagate antes de instalar.

## 8. Roadmap priorizado

| # | Tarea | Resp. sugerido | Depende de | Aceptación |
|---|---|---|---|---|
| 1 | Ejecutar T01 con 0.1.1 en VM Debian 13 limpia | Usuario + Gemini | — | ISO + `.sha256` + `.packages` + `build.log`; sin errores de paquetes; avisos «NOVORA AVISO» revisados |
| 2 | T02: arranque Live en OVMF; `novora-disk-guard status` todo `ro=True`; `systemd-analyze verify` del servicio; menú sin d-i | Usuario | 1 | Captura del estado y del menú; escritorio, red y audio funcionando |
| 3 | T03–T06 en VM con 2 discos virtuales; intentos deliberados de «Borrar disco» y de ESP de Windows | Claude (guion) + usuario | 2 | `sha256sum` de las imágenes del disco «Windows» idéntico antes y después; NVRAM de OVMF (`OVMF_VARS.fd`) sin cambios |
| 4 | Confirmar en el ISO: `bootloader.conf` final, secuencia de `settings.conf`, `grub-install --help` con `--force-extra-removable` | Claude | 1 | Salidas anexadas al informe |
| 5 | T11: VM con Windows 11 + disco Linux; quitar el disco Linux | Usuario | 3 | Windows arranca igual; NVRAM y ESP de Windows sin cambios |
| 6 | Diseñar e implementar `novora-installer` **sin particionado**: destino y ESP preexistentes por PARTUUID; nunca abrir el disco completo para escribir; `unsquashfs`; fstab por UUID; GRUB extraíble sin NVRAM | Claude | 3 | T08 PASÓ con hash idéntico de las particiones hermanas |
| 7 | Salud del Seagate, solo lectura (SMART, dmesg, `fio --readonly`) | Usuario | — | Informe sin errores; si hay anomalías, bloqueo |
| 8 | Firmware/NVIDIA/Wine32 (P1–P2) | Gemini | 1 | T09/T10 con estado por componente |
| 9 | Tema NOVORA en Plasma 6 (P2), CI con `run-tests.sh` (P3) | Gemini / Claude | 2 | — |

Releases propuestas: `0.1.1-live` (tareas 1–2) → `0.2-installer-vm` (3–6) → `0.3-hardware-pilot` (5 y 7 aprobadas + autorización expresa).

## 9. Decisiones que requieren autorización del usuario

1. **Mantener Calamares** (con el riesgo residual sobre las particiones hermanas del Seagate) **o** pasar a un instalador propio sin particionado para el Seagate (recomendado).
2. Cómo se crearán la partición destino y la ESP en el Seagate: requiere **respaldo completo verificado** previo. La auditoría no lo hace.
3. Conversión MBR → GPT del Seagate: **no recomendada in situ**; solo con respaldo y como operación separada.
4. Cualquier formateo de una partición del Seagate.
5. Cambios en el firmware (Secure Boot, orden de arranque, arranque USB) y disponibilidad de la clave de BitLocker.
6. Controlador NVIDIA propietario (área `non-free`, DKMS, clave MOK).
7. Activar multiarch i386 para Wine de 32 bits.
8. Pasar a pruebas físicas controladas (`0.3-hardware-pilot`): requiere cambiar la comprobación de VM de `novora-install`, de forma explícita y versionada.

**Datos técnicos que aún hacen falta** (sin números de serie ni claves): salida de `lsblk -o NAME,SIZE,TRAN,PTTYPE,LOG-SEC,PHY-SEC,FSTYPE,PARTTYPE` del Seagate, con la serie omitida; modo de arranque y estado de Secure Boot de Windows (`msinfo32`); si BitLocker está activo; espacio libre real en el Seagate; salud SMART resumida (atributos 5, 187, 197, 198 y 199).

## 10. Veredicto final

**No es seguro proceder con la instalación física.** Motivos, con evidencia:

- El 0.1 no tiene protección: C-01 a C-07. Los falsos «aprobados» del auditor original están demostrados en E-03.
- 0.1.1 aporta un bloqueo que funciona contra el kernel real (E-02, E-04). Pero no se ha construido ni arrancado ninguna ISO (T01 y T02 PENDIENTES) y las pruebas de Calamares en VM no existen (T03–T08, T11, T12 PENDIENTES).
- Aun con 0.1.1, las particiones con datos del Seagate no pueden protegerse técnicamente mientras ese disco está desbloqueado para Calamares (prueba H).

**Estado: 0.1 → APTO SOLO PARA REVISIÓN · 0.1.1 → APTO PARA VM (tras T01) · Hardware real → BLOQUEADO.**

### Fuentes (consultadas el 24/10/2026)

- Calamares, código fuente, commit `95aa33fd2f0ea6f081fe604fb84eb829fc806d86` (6 de mayo de 2025): `src/modules/partition/core/DeviceList.cpp`, `src/modules/partition/partition.conf`, `src/modules/bootloader/main.py`, `src/modules/bootloader/bootloader.conf` — https://github.com/calamares/calamares
- Debian Package Tracker, `wine` — https://tracker.debian.org/pkg/src:wine
- Log oficial de Debian Live 13.2.0 (opciones `lb config`, `--debian-installer live`) — https://ftp.uni-bayreuth.de/debian-cd/13.2.0-live/amd64/iso-hybrid/debian-live-13.2.0-amd64-debian-junior.log
- Bug #661369 de live-build, `--hostname` con syslinux — https://www.mail-archive.com/debian-live@lists.debian.org/msg08883.html
- Calamares, documentación de particiones — https://calamares.io/docs/partitions/ (indicada en el README original; no se pudo abrir desde este entorno)
- Manual de `lb_config` en trixie — https://manpages.debian.org/trixie/live-build/lb_config.1.en.html (**bloqueado**; las opciones que dependen de él están marcadas para T01)

### Anexo — SHA256 del material original

```
409ab132ca80159d15f1a6be465f63368ed303d5dd3573d5a3f50f9fd6369b70  README.md
7805d5e0f149c9ce25ab33e89d66330aec8e46d7ab23cee5f7bd86fd8d6889c4  scripts/build-iso.sh
593003f205e06b045b2810cb251692a06b277c0798c7c8d3ee07de7461c7504c  config/package-lists/novora.list.chroot
312244597ecd607de1127ccf63f6ea7e6b36e766a9df2e70a8732255e00fc9df  config/includes.chroot/usr/local/bin/novora-storage-audit
1677a287fbe654e6374403d1d51273089b66d6ec433e22317225b829e77ed54f  config/includes.chroot/usr/share/applications/novora-storage-audit.desktop
e0af5f6c01edb37fa18ae2701effce4c85fab4995869205f3544ad53521669d7  docs/INSTALACION-SEAGATE.md
```
