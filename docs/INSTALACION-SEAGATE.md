# Instalación en una partición del Seagate sin reemplazar Windows

**Estado (0.1.1):** plan de instalación. **La instalación física está BLOQUEADA**: `novora-install` se niega a ejecutarse fuera de una máquina virtual hasta superar las pruebas P0. Los pasos siguientes describen el procedimiento que se validará primero en VM.

1. Haz respaldo verificado del Seagate y guarda la clave de recuperación BitLocker de Windows, si está activado.
2. Arranca la ISO en modo Live **UEFI**. Todos los discos quedan en solo lectura del kernel. Ejecuta «NOVORA OS - Auditoría de discos» y comprueba que ningún resultado sea BLOQUEO.
3. Verifica modelo, tamaño y número de serie del Seagate. No confíes en la letra `sdb`, porque puede cambiar.
4. Verifica la tabla de particiones (MBR/dos o GPT) y las particiones existentes. En tu caso, el Seagate de 4 TB había sido reportado con MBR: **no convertir automáticamente**; MBR limita el direccionamiento práctico tradicional a ~2 TiB con sectores de 512 bytes.
5. Comprueba el modo de arranque. Para UEFI, lo deseado es una ESP FAT32 **en el propio Seagate**, más una partición Linux ext4 para `/` (mínimo 40 GiB; ideal 80+ GiB para herramientas de desarrollo). La ESP suele ocupar 300–512 MiB. Si aún no existe, hay que rediseñar el espacio cuidadosamente con respaldo; la auditoría no la crea.
6. Dentro de Calamares, selecciona **Particionado manual**. Asigna `/` a la partición elegida del Seagate. Solo marca Formatear sobre esa partición **si estás seguro de que puedes borrar su contenido**.
7. Selecciona para `/boot/efi` la ESP del Seagate y **NO la del disco interno de Windows** (en 0.1.1 el disco de Windows ni siquiera aparece: está en solo lectura). El envoltorio de GRUB rechaza una ESP de otro disco y no modifica la NVRAM.
8. Comprueba el resumen final antes de aplicar cambios. NINGUNA operación debe escribir/formatear particiones internas de Windows.
9. Arranca el Seagate con el **menú de arranque único** del firmware (p. ej. F12/F9/Esc según el fabricante). 0.1.1 instala GRUB en la ruta extraíble `EFI/BOOT/BOOTX64.EFI` y **no crea entradas NVRAM**, así que el orden de arranque de Windows no cambia. Sin Seagate, Windows debe iniciar exactamente igual (prueba T11).

## Reglas de bloqueo para una versión futura del instalador

- Mostrar identidades estables de disco y número de serie.
- Lista blanca explícita de partición Linux y ESP externa.
- Impedir operaciones sobre disco interno y ESP de Windows desde el instalador **personalizado**, con validación de planes de Calamares antes de ejecutar.
- Cancelar ante desconexiones USB, cambios de número de serie, puntos de montaje inesperados, salud SMART anómala o rendimiento de E/S inestable.
- Prueba destructiva únicamente en discos VIRTUALES descartables hasta haber auditado el instalador personalizado.

## Advertencia sobre el Seagate

Se reportaron latencias próximas a un segundo y pausas sin transferencia. Antes de instalar, revisa cable/conector, SMART y estabilidad; un disco externo con fallos de E/S comprometería la fluidez aunque el escritorio esté optimizado.
