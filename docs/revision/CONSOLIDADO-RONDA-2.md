# NOVORA OS 0.1.1 — Consolidado de la revisión cruzada, ronda 2

**Fecha:** 24 de octubre de 2026 · **Base:** commit `23c0ef3` · **Fuentes:** informe de Codex
(R-01 a R-05, R-09), informe de Gemini (R-05 a R-18) y la auditoría previa de Claude.

**Regla aplicada:** cada afirmación se contrastó con el código o con una prueba ejecutada
aquí. Lo que no se pudo ejecutar queda **PENDIENTE**; lo que solo se apoya en conocimiento
general, sin fuente ni prueba, queda **NO VERIFICADO**.

## 1. Qué se ejecutó

- Pruebas del repositorio (`tests/run-tests.sh`) como root, incluidas las de discos *loop*
  con el kernel real del contenedor: **todas pasan** tras las correcciones.
- Cada prueba nueva se ejecutó también contra el código original: **falla** allí
  (32 fallos y 2 errores en ATLAS, 4 en el guardián), es decir, reproduce el problema.
- **No** se pudo construir la ISO: la red de este entorno bloquea `deb.debian.org` (403).
  R-09 sigue **PENDIENTE**.
- **No** hay device-mapper ni md en este contenedor: las pruebas de dm/LVM/MD con kernel
  real siguen **PENDIENTES** para la VM. Las de este PR usan un sysfs simulado.
- Ningún disco físico se tocó.

## 2. Parte A (código): verificación y correcciones

| ID | Codex dijo | Verificación | Estado | Corrección en este PR |
|---|---|---|---|---|
| R-01 | `sort -o`, `tree -o` y `git -c core.fsmonitor=…` pasan como lectura | `sort -o` / `--output` se **autoejecutaban** (confirmado). `tree -o` quedaba como SOLO_LECTURA, pero `auto_runnable` ya lo frenaba. El caso exacto `git -c X status` **ya** pedía confirmación (Codex se equivoca en esa forma), pero `git -cX status`, `git --config-env=…`, `git diff --output=…`, `uniq A B` y `file -C` sí se autoejecutaban. `git branch NOMBRE`, `git tag NOMBRE` y `git remote add` figuraban como lectura. | **CONFIRMADO** (con matices) | Lista de opciones peligrosas por programa (`sort`, `tree`, `file`, `date`, `rg`, `uniq`); git: cualquier opción global, `--output`, `--ext-diff`, `--textconv`, `-O` → CONFIRMAR; `branch`/`tag`/`remote` solo listan. **git ya no se autoejecuta nunca**: `.git/config` y `.gitattributes` de un repositorio descargado pueden ejecutar programas hasta en `git status` (fsmonitor, filtros *clean*, *textconv*). |
| R-02a | `memoria.index()` acepta `~/.ssh` como raíz | Confirmado: solo se filtraba lo descubierto al recorrer. | **CONFIRMADO** | Rechazo de toda raíz con un componente oculto (también vía enlace simbólico); `search()` nunca devuelve trozos de rutas ocultas; `refresh()` purga entradas antiguas. |
| R-02b | TOCTOU entre propuesta y escritura | Confirmado: `open()` seguía enlaces; además la revalidación no comprobaba que siguiera dentro de `$HOME`. | **CONFIRMADO** | Recorrido desde `$HOME` con descriptores y `O_NOFOLLOW`; solo archivos normales, propios y sin enlaces duros; la copia `.atlas-bak` también sin seguir enlaces. |
| R-03 | Sin bypass; `Content-Length` negativo | Confirmado: `-1` dejaba el hilo leyendo hasta EOF (la prueba se colgaba con el código original). | **CONFIRMADO** (DoS local, sin fuga) | Solo dígitos ASCII; si no, 400. Pruebas de navegador (Referer, DNS rebinding real): **PENDIENTE**. |
| R-04 | npm sin versión fija; `--sin-verificar` | Coincide con el código. | **CONFIRMADO** (riesgo aceptado) | Sin cambio: es una decisión de producto; queda para otra ronda. |
| R-05 | dm/LVM/MD excluidos; montajes `/dev/mapper` no se comparan | Confirmado en el código. Además, según el código del kernel, el indicador RO solo se comprueba **al abrir** el dispositivo: una capa dm/md ya abierta antes del bloqueo sigue escribiendo (el envío de *bios* solo avisa). **NO VERIFICADO** en VM. | **CONFIRMADO** | `lockdown`, `unlock` y `verify` fallan cerrados si un disco protegido tiene *holders* en sysfs (recursivo), y marcan RO esas capas; los montajes se comparan también por número de dispositivo. Límite documentado: NVMe/SCSI *passthrough*, firmware y root deliberado quedan fuera. |
| R-09 | No ejecutado | Bloqueado por red. | **PENDIENTE** | — |

## 3. Parte B (instalador): qué sostiene la evidencia de Gemini

Gemini no tuvo ejecución ni dio URLs concretas; varias respuestas se presentan como
CONFIRMADO sin fuente. Esto es lo que se sostiene:

| ID | Postura de Gemini | Valoración | Estado |
|---|---|---|---|
| R-16 BitLocker | Arrancar el Seagate hará que Windows pida la clave «obligatoriamente» | **Exagerado.** Las PCR se reinician en cada arranque; elegir otro disco una vez en el menú de arranque no cambia lo que mide Windows en su siguiente arranque. Lo que sí la dispara: cambiar el orden de arranque o la configuración de Secure Boot en el firmware, o actualizaciones DBX/SBAT. Mitigación: guardar la clave de recuperación antes, no tocar NVRAM (el diseño ya lo prevé). | **NO VERIFICADO** (riesgo real pero no seguro) |
| R-10 GRUB firmado sin `ntfs` | «Altamente probable» que falte | **Especulación.** Es cierto que con Secure Boot GRUB no carga módulos sueltos, así que solo vale lo incluido en `grubx64.efi`. Hasta donde sé, Debian incluye `ntfs`, `loopback`, `iso9660`, `ext2` y `part_msdos` en esa imagen, pero hay que comprobarlo en el paquete real. | **NO VERIFICADO** |
| R-05 NVMe/SG_IO | La protección es falsa | El límite es real (lo mismo dice Codex), pero ATLAS ya prohíbe `nvme` y `sg_*` y hace falta root. Es un límite que hay que documentar, no un fallo del diseño. | **CONFIRMADO como límite** |
| R-13 ntfs3 con NTFS «sucia» | Puede corromper | `ntfs3` rechaza montar RW un volumen sucio o hibernado sin forzarlo; el diseño ya exige desactivar «Inicio rápido». Lo de corrupción bajo carga no tiene fuente. | **PARCIAL** |
| R-15 hook de initramfs | Hay que escribirlo | Correcto, y el diseño de Claude ya lo decía. Es trabajo pendiente, no un fallo. | **CONFIRMADO** |
| R-17 Timeshift | Ignora montajes anidados | Sin fuente. | **NO VERIFICADO** |
| R-18 Wubi/BCD/grub2win, o exigir USB | Alternativas | Tocar el BCD contradice «no tocar Windows»; grub2win no está firmado (habría que quitar Secure Boot); el usuario no tiene USB. **No se adoptan.** | **RECHAZADO** |

**Conclusión de la parte B:** el diseño «archivos loop dentro de NTFS» acumula riesgos reales
(R-10, R-13, R-14, R-15) aunque Gemini los exagere. Una alternativa más simple, que cumple
las mismas condiciones, es **particiones reales en el Seagate**: reducir la NTFS desde
Windows y crear en el espacio libre una ESP FAT32, un `/boot` ext4 y una partición LUKS2 →
ext4. Elimina el loop en NTFS, el `findiso=` sobre NTFS y el hook propio de initramfs, y
con sectores lógicos de 4K el MBR llega a 16 TiB, así que los 4 TB caben. Queda para
decisión del usuario.

## 4. Veredicto

- **¿Construir y probar la ISO en una VM?** Sí, en cuanto haya un entorno con acceso a
  `deb.debian.org`.
- **¿Diseño del instalador?** Cambiar a particiones reales en el Seagate (pendiente de la
  decisión del usuario).
- **¿Tocar el equipo real?** **NO**, hasta pasar T01–T12 en VM, incluidas las pruebas
  dm/LVM/MD con kernel real.
