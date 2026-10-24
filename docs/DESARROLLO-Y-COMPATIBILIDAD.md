# NOVORA OS — Desarrollo de NOVORA-LINK y LINK CONTROL, apps de Windows y GPU

**Estado:** integrado en la rama 0.1.1. Las herramientas están probadas con programas simulados (27 comprobaciones en `tests/test_dev_win_gpu.sh`). **Pendiente:** probarlas con el `.sln` real de NOVORA-LINK, con Wine real y con la RTX 3050 (pruebas D01–D08).

Todo funciona **dentro de NOVORA OS**, sin máquinas virtuales ni Windows aparte.

## 1. NOVORA-LINK (.NET / WPF)

| Qué | Cómo |
|---|---|
| SDK | .NET 8 y 10 del repositorio oficial de Microsoft para Debian 13 (hook 9200), con la telemetría desactivada |
| IDE | **JetBrains Rider**: abre el `.sln` como Visual Studio; gratis para uso no comercial; con soporte oficial para Debian 13 + KDE. Se instala con `novora-dev instalar rider ARCHIVO.tar.gz --sha256 HASH` (descárgalo de la web oficial) |
| Compilar todo, WPF incluido | `novora-dev compilar NOVORA-LINK.sln` (usa `EnableWindowsTargeting=true`) |
| Pruebas | `novora-dev probar` (los proyectos multiplataforma, por ejemplo la lógica de VE/EXIN/LE, se ejecutan; los de destino `-windows` solo compilan) |
| Ejecutar la app | `novora-dev ejecutar-windows LinkApp.csproj`: publica un `.exe` **autocontenido** win-x64 (con .NET incluido) y lo abre con Wine |
| Ayuda | ATLAS: `atlas explicar VECoreRuntime.cs "¿por qué se pierden frames?"` |

**Por qué no Visual Studio:** solo existe para Windows y no funciona en Wine. Rider lee los mismos `.sln`/`.csproj`, así que el proyecto sigue abriéndose en Visual Studio cuando arranques Windows.

## 2. LINK CONTROL (Android)

| Qué | Cómo |
|---|---|
| IDE | **Android Studio**: `novora-dev instalar android-studio ARCHIVO.tar.gz --sha256 HASH` |
| Teléfono | `adb`, `fastboot` y reglas USB de Android; `novora-dev telefono` lista los dispositivos |
| Ver y controlar el teléfono | `novora-dev espejo` (scrcpy) |
| Java | OpenJDK 21 (Android Studio trae el suyo propio) |

## 3. Aplicaciones de Windows (Wine)

**Compatibilidad real**, sin un número único:
- **Juegos:** cerca del 90 % de los títulos de Windows arrancan con Proton/Wine (ProtonDB, octubre 2025); el 42 % de los lanzamientos nuevos es «Platinum». Con antitrampas, solo funciona alrededor del 41 % (Are We Anti-Cheat Yet, 2026).
- **Aplicaciones:**
  - **Muy bien:** Win32 clásicas y utilidades; .NET Framework/WinForms en general.
  - **Parcial:** WPF y Office.
  - **Mal:** Adobe Creative Cloud.
  - **No funcionan:** apps que instalan **drivers de Windows** (antivirus, antitrampas, VPN, llaves USB).

**Cómo lo mejora NOVORA OS:**

| Mejora | Detalle |
|---|---|
| **Wine 11** (WineHQ oficial) | Nuevo WoW64, NTSync, mejor soporte de Wayland. Respaldo automático: Wine 10 de Debian. En trixie, `winehq-stable` 11.0 aún exige i386 (bug WineHQ 59343), por eso se habilita multiarch |
| **DXVK + VKD3D-Proton incluidos** | DirectX 9/10/11 y **12** → Vulkan, **sin internet**: `novora-win optimizar APP` |
| **GameMode** | Perfil de rendimiento de CPU/GPU mientras la app corre |
| **GPU dedicada automática** | En laptops híbridas, `optimizar` activa la NVIDIA en el perfil de la app |
| **Perfiles por app** | `novora-win perfil APP GPU=nvidia GAMEMODE=1 WAYLAND=1 DLL_OVERRIDES=... DXVK_HUD=fps` (claves y valores validados; un perfil editado a mano no puede inyectar órdenes) |
| **NTSync** | Sincronización rápida: lista para cargarse sola (`modules-load` + regla udev) cuando el kernel sea 6.14+. El kernel de trixie (6.12) no la trae y no se fuerza un kernel nuevo, porque puede romper el driver NVIDIA |
| **Antivirus previo** | Cada `.exe`/`.msi` se analiza antes de su primera ejecución |

- Doble clic en un `.exe`/`.msi` → `novora-win ejecutar`. Cada app tiene su propio prefijo (su propia `C:`) en `~/.local/share/novora-win/`.
- **Wine NO es un aislamiento de seguridad:** el programa puede leer tus archivos.

**Límites para NOVORA-LINK:**
- WPF en Wine puede tener fallos de dibujado.
- **CUDA, NVDEC y NVENC no pasan a través de Wine** (VE usa software).
- El `adb.exe` de Windows no ve el USB (usa el `adb` de Linux por `localhost:5037`).
- El **Reverse Tethering con VPN** depende de un driver de red de Windows y **no funcionará en Wine**.
- La solución de fondo es una versión nativa de Linux (por ejemplo, la UI en Avalonia).

## 4. Gráficos: Intel, AMD y NVIDIA

| Situación | Qué hace NOVORA OS |
|---|---|
| Cualquier equipo (Live y recién instalado) | Drivers abiertos de Mesa: Intel (iris), AMD (radeonsi), NVIDIA (nouveau/NVK). Vulkan, VA-API y firmware de las tres marcas |
| NVIDIA con máximo rendimiento | `sudo novora-gpu nvidia instalar [--cuda]`: driver oficial (rama 550 de Debian 13, `non-free`), NVDEC/NVENC (`libnvcuvid1`, `libnvidia-encode1`), CUDA opcional y `nvidia-drm modeset=1` para Wayland. Pide escribir `NVIDIA` para confirmar |
| Secure Boot activado | El instalador genera y registra una clave MOK. Al reiniciar: pantalla azul → *Enroll MOK* → contraseña |
| Laptop híbrida (Intel + RTX 3050) | `novora-gpu usar-nvidia PROGRAMA` lo ejecuta en la NVIDIA; el escritorio sigue en la integrada |
| Volver atrás | `sudo novora-gpu nvidia quitar` |

El driver propietario **no va activado en la ISO** a propósito: rompería el arranque en equipos sin NVIDIA y con Secure Boot exige registrar la clave. Solo se instala en el sistema ya instalado: en la sesión Live, `novora-gpu` se niega.

## 5. Ofimática y catálogo `novora-apps`

- **LibreOffice** (Writer, Calc, Impress) en español, preinstalado.
- **`novora-apps lista | instalar | quitar | info`**: apps opcionales, nada preinstalado.
  - Cada archivo de GitHub se **verifica contra la huella SHA256 que publica GitHub**. Sin huella no se instala, salvo con `--sin-verificar`.
  - Los `.tar` se extraen con el filtro de seguridad de Python (rechaza rutas `..` o absolutas).

| App | Licencia | Notas |
|---|---|---|
| GenOffice | Apache-2.0 (`ee/` aparte) | NOVORA **desactiva las analíticas** antes del primer arranque y la conecta a la **IA local de ATLAS** (`novora-con-ia-local`) |
| Spotifast | MIT | Cliente no oficial de Spotify; requiere Premium |
| Zuno | Apache-2.0 | Cliente no oficial de YouTube Music; pide escribir `ACEPTO` por los términos de YouTube |
| Huntly | Apache-2.0 | Archivo de artículos, RSS y tuits |
| OmniRoute | MIT | Pasarela de IA local; NOVORA la limita a `127.0.0.1`; nunca actives su MITM/TPROXY |
| Claude Code, Codex, Gemini CLI | según proveedor | npm en `~/.local`; comprueba la versión de Node; aviso de nube |
| Copilot CLI | GitHub | Binario oficial (evita el requisito de Node 22); aviso de nube. En Rider: plugin oficial «GitHub Copilot» |

**OpenJarvis:** no se instala aparte; sus funciones (agente, investigación con citas, memoria, resumen diario y rutinas) están **dentro de ATLAS**, ver [ATLAS.md](ATLAS.md).

**Descartados tras revisión:** Dolmades (abandonado desde 2020), WinApps (usa una máquina virtual de Windows) y Buzz (espacio de trabajo de equipo, no sustituye a X).

## Seguridad

- ATLAS tiene **prohibido** usar `novora-gpu` y `prime-run`, porque `usar-nvidia` ejecuta cualquier programa y serviría para saltarse su lista prohibida.
- `novora-dev instalar` exige `--sha256` para verificar el archivo (avisa si falta), rechaza archivos con rutas `..` o absolutas y no sobrescribe instalaciones existentes.
- `novora-gpu nvidia instalar` guarda copia de las fuentes de APT (`*.novora-bak`) antes de cambiarlas y no duplica componentes si se repite.

## Pruebas pendientes en hardware o VM real

| ID | Prueba |
|---|---|
| D01 | Hook 9200: .NET 8/10 desde packages.microsoft.com dentro de `lb build` |
| D02 | `novora-dev compilar` con el `.sln` real de NOVORA-LINK |
| D03 | `novora-dev ejecutar-windows`: la interfaz WPF de NOVORA-LINK bajo Wine (anotar los fallos de dibujado) |
| D04 | Rider y Android Studio en Plasma 6 Wayland |
| D05 | LINK CONTROL: compilar e instalar en el SM-A566E por `adb`; `scrcpy` |
| D06 | `novora-gpu nvidia instalar` en la RTX 3050 con Secure Boot (registro MOK) |
| D07 | FFmpeg nativo con `-hwaccel cuda` / `h264_cuvid` en Linux; compararlo con la validación de Windows |
| D08 | Wine 11 (WineHQ) o Wine 10 de respaldo; `novora-win optimizar` con DXVK/VKD3D-Proton; suite pequeña de apps y juegos de Windows (estado por app) |
