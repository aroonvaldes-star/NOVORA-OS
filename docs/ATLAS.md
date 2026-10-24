# ATLAS — asistente local de NOVORA OS

Se llama **ATLAS** en todo lo que ve el usuario (menú, panel, atajos). La orden corta es `atlas`; `novora-atlas` sigue funcionando y es el nombre técnico interno.

**Estado:** integrado en la rama 0.1.1 y probado con un motor simulado (58 pruebas). **Sin probar todavía con un modelo real ni dentro de la ISO** (pruebas A01–A06 pendientes).

## Qué hace

| Función | Cómo se usa |
|---|---|
| Conversación y ayuda general | Panel (`Meta+Shift+A`, menú → ATLAS) o `atlas chat` |
| Ver la pantalla | `Meta+Shift+X` captura **antes** de abrir el panel y la explica. En el panel, «Ver pantalla (3 s)» te da 3 segundos para cambiar de ventana. «Ver zona» permite elegir un recuadro |
| Programar | «Explicar archivo» / `atlas explicar main.py "¿por qué falla?"`. Propone órdenes como `ORDEN:` |
| Organizar | Escribe `tarea: …` o `nota: …` en el panel; «Organizar mi día» prioriza las tareas pendientes |
| Ejecutar una orden | Escribe `$ git status` en el panel o `atlas orden "git status"` |
| **Agente** (tareas en varios pasos) | Botón «Agente» o `atlas agente "revisa los TODO de ~/NOVORA-LINK y crea tareas"` |
| **Investigar** en tus documentos, con citas | Botón «Investigar» o `atlas investigar "¿qué decidimos sobre VECore?"` |
| **Memoria** (índice de documentos) | Botón «Memoria» o `atlas memoria indexar ~/Documentos ~/NOVORA-LINK` · `buscar` · `estado` · `actualizar` · `olvidar` |
| **Resumen del día** | Botón o `atlas resumen [--voz] [--notificar]`: tareas atrasadas y de hoy, notas, actualizaciones y espacio libre |
| **Rutinas** programadas | `atlas rutina agregar mi-dia --hora 08:00 --resumen --voz` · `atlas rutina agregar revisar-repo --hora 18:30 --dias laborables --agente "git status de ~/NOVORA-LINK y dime qué cambió"` · `lista` · `ultimo` · `quitar` |

## Agente, investigación, memoria y rutinas

Son las funciones de OpenJarvis (Stanford), **hechas dentro de ATLAS**: un solo asistente, el mismo motor local y **la misma política de seguridad**. No hace falta instalar OpenJarvis.

| OpenJarvis | En ATLAS |
|---|---|
| `jarvis memory index / search / stats` (SQLite FTS5) | `atlas memoria` — SQLite FTS5 incluido en Python; texto, código, Markdown, CSV/JSON, **Office** (Office Oxide) y **PDF** (`pdftotext`). Base en `~/.local/share/novora-atlas/memoria.db` (0600). Omite carpetas ocultas, `node_modules`, `bin`/`obj`, enlaces y rutas de sistema; solo reindexa lo que cambió |
| agente `deep_research` (varios saltos, citas) | `atlas investigar`: busca, el modelo pide nuevas búsquedas (`BUSCAR:`) hasta 4 saltos y responde con citas `[n]` → archivo y trozo. Las citas que no existen se descartan |
| `orchestrator` / `native_react` / preset `code-assistant` | `atlas agente`: bucle de razonamiento con herramientas `buscar_memoria`, `leer_archivo`, `listar`, `orden`, `calcular`, `nota`, `tarea`, `escribir_archivo`. Hasta 8 pasos y un detector de bucles |
| `morning_digest` (con voz) | `atlas resumen --voz` (espeak-ng, local). Sin el modelo hace un resumen en texto sin IA |
| `scheduled-monitor` / `monitor_operative` | `atlas rutina`: temporizador de systemd **del usuario** (sin root). Cada ejecución recibe el resultado anterior para decir qué cambió. Guarda los resultados en `~/.local/share/novora-atlas/rutinas/` (últimos 30) y avisa con una notificación |
| Skills (agentskills.io) | Ya incluidas (ver abajo) |

**Qué NO se copió, a propósito:**
- Los conectores de Gmail, Calendar y Slack (OAuth y nube).
- Su navegador automatizado y la ejecución libre de código Python (CodeAct).
- El bucle de aprendizaje que reentrena modelos.

Todo eso choca con «sin internet» o con la lista prohibida.

**Reglas del agente:**
- Cada `orden` pasa por la política de ATLAS: lo **PROHIBIDO** nunca se ejecuta.
- Solo se ejecutan solas las órdenes de **solo lectura** que no tocan archivos ocultos ni recorren carpetas enteras (`grep -r`, `rg`, `tree`, `ls -R` piden confirmación). Lo demás (`git commit`, `make`, scripts…) queda como **propuesta** que confirmas al final.
- `escribir_archivo` es siempre una propuesta, con vista previa. Solo escribe dentro de tu carpeta personal y nunca en archivos ocultos (así no puede tocar `~/.bashrc` ni el autoarranque). Si sobrescribe, guarda una copia `.atlas-bak`.
- `leer_archivo` y `listar` no entran en `.ssh`, `.gnupg`, `.config`… ni en `/etc`, `/root`, `/var/lib` o `/var/log`.
- Lo que devuelven las herramientas es **dato**, nunca instrucción.
- Para que pregunte también antes de leer: `"agente_auto_lectura": false` en `~/.config/novora-atlas/config.json`.
- Las **rutinas** siempre son locales (nunca nube). Lo que habría requerido confirmación queda anotado como pendiente en el resultado.

El contexto del modelo sube a **8192** tokens para que quepan los pasos del agente.

## Arquitectura

```
Panel web local (127.0.0.1, token)  ─┐
CLI novora-atlas                     ├─> novora_atlas (Python, sin dependencias)
Atajos KDE (.desktop)               ─┘        │
                                              ├─ policy.py   lista prohibida + confirmación
                                              ├─ screen.py   Spectacle + Tesseract (OCR)
                                              ├─ store.py    notas/tareas en JSON (0600)
                                              ├─ memoria.py  índice SQLite FTS5 de documentos
                                              ├─ agente.py   bucle ACCION/FINAL con herramientas
                                              ├─ investigar.py  varios saltos con citas
                                              ├─ rutinas.py  resumen diario + temporizadores
                                              └─ engine.py ──> llama-server (llama.cpp, Debian)
                                                               se arranca al usarse y se detiene
                                                               tras 10 min sin uso (libera RAM/VRAM)
```

- **Sin internet:** solo acepta motores en `127.0.0.1`/`localhost`; se niega a arrancar con cualquier otra dirección.
- **No se carga al iniciar sesión:** no consume recursos hasta que lo abres.
- **Interfaz:** panel flotante translúcido con modo claro/oscuro, inspirado en el lenguaje visual de macOS pero original (sin recursos de Apple).

## Seguridad

1. **Nunca ejecuta sin confirmación**, salvo las órdenes de solo lectura del modo agente (ver arriba). Cada orden recibe un código de un solo uso que caduca a los 10 minutos, y se vuelve a validar justo antes de ejecutarse.
2. **Lista prohibida fija**, aunque el usuario la pida:
   - discos, particiones y sistemas de archivos (`mkfs*`, `dd`, `parted`, `wipefs`, `mount`…);
   - arranque y EFI (`efibootmgr`, `grub-*`);
   - cifrado y LVM;
   - `sudo`/`pkexec`, `systemctl`, `apt`, `rm`, `chmod`;
   - herramientas NOVORA (`novora-disk-guard`, `novora-install`);
   - rutas `/dev`, `/sys`, `/boot`, `/etc`.
3. **Contra los atajos que esquivarían la lista:** prohíbe intérpretes con código en línea (`sh -c`, `python3 -c`), envoltorios (`env`, `xargs`, `timeout`…), `find -exec` y cualquier operador o comodín de shell (`| ; & > $ * ~`). Ejecuta una sola orden sin shell.
4. **El texto de la pantalla y de los archivos es dato, nunca instrucción.** Va entre `<datos>` y se neutraliza el intento de cerrar esa etiqueta (prueba con una inyección en el OCR).
5. **Panel web:** solo escucha en 127.0.0.1, exige un token por sesión, rechaza `Host`/`Origin` ajenos (DNS rebinding, otras webs) y aplica CSP sin recursos externos.
6. **Capturas:** se guardan en `~/.local/state/novora-atlas` (0700) y se borran tras analizarlas.

Riesgo residual: una orden permitida como `cp` podría escribir en un enlace simbólico que apunte a un dispositivo. Mitigación: en la Live los discos están en solo lectura del kernel, y en el sistema instalado el usuario no pertenece al grupo `disk`.

## Agent Skills (estándar abierto agentskills.io)

ATLAS implementa el estándar **Agent Skills** (carpetas con `SKILL.md`), con divulgación progresiva:
1. Al iniciar, solo carga el nombre y la descripción de cada skill.
2. Al activarla, añade el `SKILL.md`, recortado al contexto del modelo local (`skill_max_chars`, 6000 caracteres; en modo nube, 40000).
3. Los archivos de apoyo se leen bajo demanda.

| Colección incluida | Licencia | Skills |
|---|---|---|
| [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) (commit `aeac41d`) | MIT | 25 de ingeniería: revisión de código, depuración, rendimiento, seguridad, TDD, CI/CD, Git, documentación/ADR, planificación… (con su carpeta `references/`) |
| [anthropics/skills](https://github.com/anthropics/skills) (commit `dbd4588`) | Apache-2.0 | 14: mcp-builder, webapp-testing, frontend-design, skill-creator, theme-factory, claude-api… **Excluidas** `docx`, `pdf`, `pptx`, `xlsx` (licencia propietaria) y `doc-coauthoring` (sin licencia) |
| [agentskills/agentskills](https://github.com/agentskills/agentskills) | Apache-2.0 | Especificación del estándar en `/usr/share/doc/novora/agent-skills/` |

- **Activación:**
  - **Explícita:** `/code-review-and-quality revisa VECoreRuntime.cs`, o el botón «Skills» del panel.
  - **Automática:** por coincidencia con tu pregunta, con un diccionario español→inglés (las descripciones están en inglés). La elige ATLAS, no el modelo, porque los modelos de 3–4B no usan herramientas de forma fiable.
- **Scripts de las skills:** **nunca se ejecutan solos**. El modelo puede proponerlos con `ORDEN:` y pasan por la política y tu confirmación.
- **Órdenes:**

  ```
  atlas skills lista | info NOMBRE | validar RUTA
  atlas skills instalar RUTA|https://…git   # colecciones completas (conserva ../../references)
  atlas skills quitar NOMBRE
  atlas skills exportar NOMBRE [--claude]   # a ~/.agents/skills o ~/.claude/skills (Claude Code)
  ```
- **Ubicaciones:** `/usr/share/novora-atlas/skills` (sistema) < `~/.agents/skills` < `~/.local/share/novora-atlas/skills`. Si dos skills se llaman igual, gana la del usuario. **No** se cargan skills de repositorios clonados (`.agents/` de proyectos), porque pueden ser una fuente no confiable.
- **Limitación honesta:** con un modelo local pequeño y 4K de contexto, las skills largas (10–20 KB) se recortan. En modo nube o con un modelo mayor se aprovechan completas.

## Documentos de Office

`atlas explicar informe.docx` (y `.xlsx`, `.pptx`, `.doc`, `.xls`, `.ppt`) convierte el documento a Markdown con **Office Oxide** (MIT/Apache-2.0, instalado por el hook 9100) y lo analiza **sin internet**.

## Motor compartido

`atlas motor iniciar | estado | detener` deja la IA local disponible en `http://127.0.0.1:8181/v1`, con el nombre de modelo fijo `novora-atlas`, para otras apps como GenOffice. `novora-con-ia-local PROGRAMA` la arranca mientras el programa está abierto y la detiene al cerrarlo. `detener` solo termina el proceso que lanzó ATLAS: comprueba el host y el puerto antes de enviar la señal.

## Modo nube opcional (OmniRoute)

ATLAS es **100 % local por defecto**. Si instalas OmniRoute (`novora-apps instalar omniroute`) y ejecutas `atlas nube activar`, puedes enviar a la nube **solo las consultas que tú marques**: `--nube` en la terminal o el interruptor **☁ Nube** del panel, que se apaga en cada sesión. Así llegas a Claude, GPT, Gemini, Kimi, etc., con tus cuentas configuradas en OmniRoute.

- La pasarela tiene que ser **local** (`127.0.0.1`). ATLAS se niega a hablar directamente con internet.
- La clave se guarda en `~/.config/novora-atlas/nube.key` (0600). `atlas nube desactivar` la borra.
- Con el modo nube activo, el pie del panel avisa de que tus datos salen del equipo, y cada respuesta lleva la etiqueta «☁ nube».
- En modo nube no se envían imágenes de la pantalla, solo el texto reconocido.
- La política de órdenes es la misma: la nube tampoco puede ejecutar nada sin tu confirmación.

## Modelos

ATLAS no incluye modelo por defecto (ocuparía 2–3 GB en la ISO). Dos opciones:

- **En la ISO:** `bash scripts/add-atlas-model.sh modelo.gguf <SHA256 publicado>` antes de `build-iso.sh`. Sin el hash correcto no se copia nada.
- **Después, sin internet:** `atlas modelo instalar /media/usb/modelo.gguf [--sha256 …]`. Comprueba el formato GGUF.
- **Para ver con visión** (además del OCR): añade el proyector multimodal del modelo (un archivo con `mmproj` en el nombre).

Orientación para la RTX 3050 Laptop de 4 GB (medirlo en tu equipo): modelos de 3–4B en Q4_K_M para chat y código; modelos multimodales de ~2B para visión. Revisa la licencia de cada modelo antes de redistribuirlo.

## Construcción

- El hook `9100-novora-atlas` instala `llama.cpp-tools` desde trixie y, si no hay versión ahí, desde trixie-backports.
- También instala el backend Vulkan de ggml si existe. Así la GPU puede usarse sin el controlador propietario (vía Mesa/NVK), lo que **está pendiente de verificar**.
- Con `--atlas-required`, la construcción falla si no se pudo instalar el motor.

## Pruebas

**Ejecutadas** (`tests/atlas/test_atlas.py`, 58 pruebas; incluyen skills, Office, motor, modo nube, memoria, agente, investigación y rutinas):
- agente: lectura permitida, `~/.ssh` y `~/.bashrc` bloqueados, `git commit` queda pendiente, `mkfs` prohibido, escribir solo con confirmación de un solo uso, detector de bucles, calculadora sin `eval`;
- memoria: omite ocultos, binarios y `node_modules`; reindexa solo lo cambiado; consultas FTS saneadas; PDF; base 0600;
- investigación de 2 saltos con citas válidas; rutinas con temporizador, memoria del resultado anterior, notificación y voz;
- política: 37 órdenes prohibidas, 6 de solo lectura y 6 que requieren confirmación;
- motor gestionado (arranque bajo demanda y parada);
- rechazo de endpoints remotos y de variables XDG vacías;
- pantalla con inyección en el OCR, retardo y capturas que no salen de su carpeta;
- seguridad web: token, Host, Origin, JSON y CSP;
- códigos de un solo uso;
- CLI e instalación de modelos con hash.

Una prueba de mutación (quitar el filtro de shell y el token) produjo 6 fallos, como se esperaba. El panel se renderizó en Chromium en modo claro, oscuro y móvil, sin errores de JavaScript ni desbordamiento.

**Pendientes:**

| ID | Prueba |
|---|---|
| A01 | `llama-server` real de Debian con un modelo de 3–4B: medir tokens/s y VRAM en la RTX 3050 |
| A02 | Spectacle en Plasma 6 Wayland: captura completa y por zona desde el atajo |
| A03 | Atajos `X-KDE-Shortcuts` registrados por defecto en Plasma 6 |
| A04 | Falkon/Firefox abre el panel con el token en el fragmento de la URL |
| A05 | Backend Vulkan de ggml con nouveau/NVK frente al controlador propietario |
| A06 | Consumo en reposo: con ATLAS cerrado, 0 procesos y 0 MB |
| A07 | Modo agente con un modelo real de 3–4B: ¿sigue el formato `ACCION:`/`FINAL:`? (los modelos pequeños pueden fallar; anotar el modelo que funcione mejor) |
| A08 | `atlas memoria indexar` sobre el repositorio real de NOVORA-LINK (tiempo y tamaño de la base) |
| A09 | Rutina con temporizador de systemd del usuario en el sistema instalado; voz `espeak-ng -v es-419` |
