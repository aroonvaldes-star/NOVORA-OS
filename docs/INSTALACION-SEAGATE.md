# Instalación en el Seagate sin reemplazar Windows

**Estado:** `novora-install` instala sobre dos particiones que el usuario ya preparó en el
disco externo: una **ext4** (p. ej. 1 TB) para el sistema y una **FAT32** (p. ej. 100 GB) para
el arranque. Se probó de punta a punta con un Seagate virtual (`tests/test_instalador_loop.sh`:
LUKS2 real, chroot simulado). **Pendiente de VM:** arranque real con OVMF y Secure Boot,
desbloqueo LUKS en el initramfs y GRUB firmado desde la FAT32. Fuera de una VM el instalador
exige `--equipo-real` y escribir «ENTIENDO EL RIESGO».

## Qué hace con cada partición

| Partición | Qué pasa |
|---|---|
| ext4 elegida (sistema) | Se **cifra con LUKS2** (argon2id, sectores de 4096) y dentro se crea ext4 para `/`. **Se borra su contenido**: si tiene archivos, muestra algunos y exige escribir `BORRAR`. |
| FAT32 del mismo disco (arranque) | **No se formatea.** Se monta como `/boot` y se añaden los núcleos, `grub/`, `EFI/debian/` y `EFI/BOOT/BOOTX64.EFI` (shim firmado). Tus archivos se conservan. |
| NTFS y demás particiones del Seagate | Solo lectura del kernel durante todo el proceso. |
| Disco de Windows y su ESP | Solo lectura; GRUB no puede usarlos y la NVRAM no se toca (`--no-nvram`). |

Una FAT32 creada desde Windows en un disco MBR tiene tipo `0x0C`, no `0xEF`. El instalador la
acepta como arranque del disco externo (aviso W10). Casi todos los firmwares UEFI arrancan un
USB desde ella por la ruta `EFI/BOOT/BOOTX64.EFI`; si el tuyo no lo ve, hay que cambiar el tipo a
`0xEF` (solo cambia un byte de la tabla y no toca los datos).

## Pasos

1. En Windows: guarda la **clave de recuperación de BitLocker**, desactiva el «Inicio rápido» y
   haz copia de lo importante del Seagate.
2. Arranca la ISO en modo **UEFI** desde el menú de arranque del firmware (F12/F9/Esc).
3. En una terminal: `sudo novora-install --equipo-real` (en una VM basta con `sudo novora-install`).
4. Elige el número de la partición **ext4** (sistema) y después el de la **FAT32** del mismo disco.
   Revisa los AVISOS y escribe `INSTALAR xxxxxx` con el código que se muestre.
5. Elige la contraseña de cifrado (teclado latam), tu usuario y su contraseña.
6. Para arrancar NOVORA OS: menú de arranque del firmware → el disco externo. Sin elegirlo,
   Windows arranca igual que siempre.

`sudo novora-install --calamares` sigue disponible para usar Calamares con particionado manual.

## Reglas de bloqueo para una versión futura del instalador

- Mostrar identidades estables de disco y número de serie.
- Lista blanca explícita de partición Linux y ESP externa.
- Impedir operaciones sobre disco interno y ESP de Windows desde el instalador **personalizado**, con validación de planes de Calamares antes de ejecutar.
- Cancelar ante desconexiones USB, cambios de número de serie, puntos de montaje inesperados, salud SMART anómala o rendimiento de E/S inestable.
- Prueba destructiva únicamente en discos VIRTUALES descartables hasta haber auditado el instalador personalizado.

## Advertencia sobre el Seagate

Se reportaron latencias próximas a un segundo y pausas sin transferencia. Antes de instalar, revisa cable/conector, SMART y estabilidad; un disco externo con fallos de E/S comprometería la fluidez aunque el escritorio esté optimizado.
