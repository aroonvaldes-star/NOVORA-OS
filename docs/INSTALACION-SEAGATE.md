# Instalación en una partición del Seagate sin reemplazar Windows

**Estado:** plan de instalación, pendiente de validar en hardware real. **NO es un instalador con bloqueo de discos garantizado.**

1. Haz respaldo verificado del Seagate y guarda la clave de recuperación BitLocker de Windows, si está activado.
2. Arranca la ISO en modo Live, sin instalar, y ejecuta «NOVORA OS - Auditoría de discos».
3. Verifica modelo, tamaño y número de serie del Seagate. No confíes en la letra `sdb`, porque puede cambiar.
4. Verifica la tabla de particiones (MBR/dos o GPT) y las particiones existentes. En tu caso, el Seagate de 4 TB había sido reportado con MBR: **no convertir automáticamente**; MBR limita el direccionamiento práctico tradicional a ~2 TiB con sectores de 512 bytes.
5. Comprueba el modo de arranque. Para UEFI, lo deseado es una ESP FAT32 **en el propio Seagate**, más una partición Linux ext4 para `/` (mínimo 40 GiB; ideal 80+ GiB para herramientas de desarrollo). La ESP suele ocupar 300–512 MiB. Si aún no existe, hay que rediseñar el espacio cuidadosamente con respaldo; la auditoría no la crea.
6. Dentro de Calamares, selecciona **Particionado manual**. Asigna `/` a la partición elegida del Seagate. Solo marca Formatear sobre esa partición **si estás seguro de que puedes borrar su contenido**.
7. Selecciona para `/boot/efi` la ESP del Seagate y **NO la del disco interno de Windows**. Si el instalador no deja verificar con seguridad a dónde escribirá GRUB, CANCELA.
8. Comprueba el resumen final antes de aplicar cambios. NINGUNA operación debe escribir/formatear particiones internas de Windows.
9. Verifica el arranque desde el menú UEFI seleccionando el Seagate; sin Seagate, Windows debe seguir iniciando independientemente. Para un sistema USB portátil, puede requerirse instalar GRUB con ruta EFI extraíble; esto debe probarse antes, no se automatiza en v0.1.

## Reglas de bloqueo para una versión futura del instalador

- Mostrar identidades estables de disco y número de serie.
- Lista blanca explícita de partición Linux y ESP externa.
- Impedir operaciones sobre disco interno y ESP de Windows desde el instalador **personalizado**, con validación de planes de Calamares antes de ejecutar.
- Cancelar ante desconexiones USB, cambios de número de serie, puntos de montaje inesperados, salud SMART anómala o rendimiento de E/S inestable.
- Prueba destructiva únicamente en discos VIRTUALES descartables hasta haber auditado el instalador personalizado.

## Advertencia sobre el Seagate

Se reportaron latencias próximas a un segundo y pausas sin transferencia. Antes de instalar, revisa cable/conector, SMART y estabilidad; un disco externo con fallos de E/S comprometería la fluidez aunque el escritorio esté optimizado.
