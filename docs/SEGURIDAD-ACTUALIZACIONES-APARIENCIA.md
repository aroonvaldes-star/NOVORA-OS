# NOVORA OS — Seguridad, actualizaciones y apariencia

**Estado:** integrado en la rama 0.1.1 y probado con programas simulados (`tests/test_dev_win_gpu.sh`, secciones 2b–5). **Pendiente:** verificarlo en la ISO real (pruebas S01–S08).

## 1. Seguridad

| Capa | Qué hace | Cómo se usa |
|---|---|---|
| **Antivirus (ClamAV)** | Análisis **bajo demanda**, sin servicio residente (el demonio consume ~1 GB de RAM). Las firmas vienen incluidas en la ISO y se actualizan solas cuando hay internet (`freshclam`) | `novora-antivirus analizar RUTA` o clic derecho en Dolphin → «Analizar con antivirus» |
| **Análisis automático de apps de Windows** | `novora-win` analiza cada `.exe`/`.msi` **antes de su primera ejecución**. Si hay amenaza, **no lo ejecuta**. Recuerda la huella SHA256: si el archivo cambia, lo vuelve a analizar | Automático, también con doble clic |
| **Cortafuegos (firewalld)** | Bloquea todas las conexiones **entrantes** no solicitadas; las salientes funcionan | Configuración del sistema → Cortafuegos. Para recibir NOVORA-LINK por Wi-Fi, abre su puerto ahí |
| **AppArmor** | Limita lo que pueden hacer ciertos programas aunque estén comprometidos (activo por defecto en Debian) | Automático |
| **ATLAS** | Tiene prohibidos `novora-gpu`, `prime-run` y `gamemoderun` (sirven para ejecutar cualquier programa) | — |

`novora-antivirus estado` avisa si las firmas tienen más de 7 días. Si ClamAV no está disponible, el análisis devuelve error (código 2) en lugar de fingir que el archivo está limpio.

**Límite honesto:** ClamAV detecta bien el malware conocido de Windows, pero peor que los antivirus comerciales ante amenazas nuevas. La mejor defensa sigue siendo ejecutar en Wine solo programas de fuentes confiables.

## 2. Actualizaciones

| Tipo | Comportamiento |
|---|---|
| **Parches de seguridad de Debian** | Automáticos y diarios (unattended-upgrades). **Nunca reinicia** por su cuenta. No se ejecuta con batería ni en conexiones medidas |
| **Resto** (programas, Plasma, drivers, .NET) | Discover avisa **una vez por semana**; tú decides. También con `sudo novora-actualizar ahora` (muestra la lista y pide `si`) |
| **Kernel de respaldo** | Se conserva el kernel anterior en el menú de arranque (`Remove-Unused-Kernel-Packages "false"`) |
| **Instantáneas (opcional)** | `sudo novora-actualizar instantaneas activar`: Timeshift crea una instantánea antes de cada cambio de `apt` (máximo una por hora). Si falla, la actualización continúa |
| **Sesión Live** | No se actualiza (todo está en RAM) |
| **Estado** | `novora-actualizar estado`: pendientes, seguridad automática, reinicio pendiente, kernels instalados |

**Pendiente de tu decisión:**
- Repositorio propio de NOVORA para actualizar ATLAS y las herramientas `novora-*` como paquetes firmados (¿dónde alojarlo?).
- Btrfs + snapper en lugar de ext4 + Timeshift, para volver atrás desde el menú de arranque.

## 3. Apariencia NOVORA

Diseño **original**, inspirado en el lenguaje visual de macOS, sin iconos, fuentes ni recursos de Apple.

| Elemento | NOVORA |
|---|---|
| Disposición | **Barra superior**: logotipo N (lanzador), **menú global** de la app activa, bandeja y reloj. **Dock inferior flotante** centrado: Dolphin, Konsole, Kate, **ATLAS**, Discover, Configuración y Papelera; se aparta cuando una ventana lo tapa |
| Colores | Esquemas **NOVORA Claro** y **NOVORA Oscuro**, con acento azul `#3b6cf6` (el mismo de ATLAS) |
| Fondo | «NOVORA»: degradado azul/violeta con ondas suaves, con versión clara y oscura que cambia sola con el esquema (PNG 4K y 1080p) |
| Ventanas | Breeze con esquinas redondeadas y **botones a la izquierda** (cerrar, minimizar, maximizar) |
| Efectos | Desenfoque y translucidez; efecto «lámpara mágica» al minimizar; animaciones algo más rápidas (0.85×) |
| Tipografía | **Inter** para la interfaz y **JetBrains Mono** para código y terminal |
| Iconos | **Papirus** |
| Inicio de sesión | SDDM Breeze con el fondo NOVORA |

**`novora-apariencia`:**

```
novora-apariencia claro | oscuro
novora-apariencia acento azul|violeta|verde|naranja|rosa|rojo|grafito|#rrggbb
novora-apariencia ligero on|off        # sin desenfoques ni animaciones: equipos modestos o batería
novora-apariencia botones izquierda|derecha
novora-apariencia restablecer          # vuelve a la barra superior + dock
```

También hay accesos en el menú: «NOVORA: modo claro» y «NOVORA: modo oscuro». Todo es reversible desde Configuración del sistema.

**Rendimiento:** el desenfoque y la translucidez cuestan GPU. En la RTX 3050 o en una iGPU moderna no se notan, pero con batería o en equipos modestos conviene `novora-apariencia ligero on`.

La maqueta (`novora-escritorio-claro.png` / `-oscuro.png`) es una **recreación aproximada en HTML**, no una captura de Plasma real.

## Pruebas pendientes en la ISO real

| ID | Prueba |
|---|---|
| S01 | `freshclam` dentro de `lb build` (firmas incluidas) y `novora-antivirus` con EICAR |
| S02 | firewalld activo; puertos visibles en el módulo de Plasma |
| S03 | unattended-upgrades aplica solo seguridad; los temporizadores no corren en la Live |
| S04 | Discover avisa semanalmente (`RequiredNotificationInterval=604800`) |
| S05 | Timeshift antes de `apt` (rsync en ext4) y restauración |
| S06 | Plasma 6 aplica el tema global `org.novora.desktop` a usuarios nuevos: barra superior y dock flotante (`floating`, `lengthMode`, `alignment` en el API de scripting) |
| S07 | Menú global con apps Qt/KDE, GTK y Wine |
| S08 | `novora-apariencia` en una sesión real (`plasma-apply-colorscheme --accent-color`, recarga de KWin) |
