#!/usr/bin/env bash
# shellcheck disable=SC2015,SC2016  # ok()/bad() nunca fallan; los falsos expanden al ejecutarse
# Pruebas de novora-dev, novora-win y novora-gpu con programas simulados.
# No instala nada real: apt-get, dotnet, wine, lspci, mokutil… son falsos.
set -Euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="${HERE}/../config/includes.chroot/usr/local/bin"
TMP="$(mktemp -d)"; trap 'rm -rf "${TMP}"' EXIT
F="${TMP}/fake"; mkdir -p "${F}"
export HOME="${TMP}/home"; mkdir -p "${HOME}"; unset XDG_DATA_HOME
pass=0 fail=0
ok()  { echo "  PASÓ  $*"; pass=$((pass + 1)); }
bad() { echo "  FALLÓ $*"; fail=$((fail + 1)); }
fake() { printf '#!/bin/sh\n%s\n' "$2" > "${F}/$1"; chmod +x "${F}/$1"; }
export PATH="${F}:${PATH}"
LOG="${TMP}/calls.log"; : > "${LOG}"; export LOG

echo "1) novora-gpu"
fake lspci "cat <<'X'
00:02.0 VGA compatible controller [0300]: Intel Corporation Alder Lake-P GT1 [UHD Graphics] [8086:46a3] (rev 0c)
	Kernel driver in use: i915
01:00.0 3D controller [0302]: NVIDIA Corporation GA107M [GeForce RTX 3050 Mobile] [10de:25a2] (rev a1)
	Kernel driver in use: nouveau
X"
fake mokutil 'case "$1" in --sb-state) echo "SecureBoot enabled";; *) echo "mokutil $*" >> "$LOG";; esac'
fake apt-get 'echo "apt-get $*" >> "$LOG"'
fake update-initramfs 'echo "update-initramfs $*" >> "$LOG"'
out="$(bash "${BIN}/novora-gpu" estado 2>&1)"
grep -q "Intel: .*UHD.*(driver: i915)" <<<"${out}" && grep -q "NVIDIA: .*RTX 3050.*(driver: nouveau)" <<<"${out}" \
  && ok "detecta Intel + NVIDIA con su driver" || bad "detección: ${out}"
grep -q "Equipo híbrido" <<<"${out}" && ok "detecta equipo híbrido" || bad "híbrido"
envdump='env | grep -E "^(DRI_PRIME|__NV_PRIME_RENDER_OFFLOAD|__GLX_VENDOR_LIBRARY_NAME)=" | sort'
o1="$(bash "${BIN}/novora-gpu" usar-nvidia sh -c "${envdump}")"
[[ "${o1}" == "DRI_PRIME=1" ]] && ok "usar-nvidia con drivers abiertos → DRI_PRIME=1" || bad "usar-nvidia abierto: ${o1}"
o2="$(NOVORA_FORCE_PROPRIETARY=1 bash "${BIN}/novora-gpu" usar-nvidia sh -c "${envdump}")"
grep -q "__NV_PRIME_RENDER_OFFLOAD=1" <<<"${o2}" && grep -q "__GLX_VENDOR_LIBRARY_NAME=nvidia" <<<"${o2}" \
  && ok "usar-nvidia con propietario → PRIME render offload" || bad "usar-nvidia propietario: ${o2}"

S="${TMP}/apt"; mkdir -p "${S}/sources.list.d" "${TMP}/modprobe"
cat > "${S}/sources.list.d/debian.sources" <<'X'
Types: deb
URIs: http://deb.debian.org/debian
Suites: trixie trixie-updates
Components: main non-free-firmware
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
X
echo "fake-mok" > "${TMP}/mok.pub"
export NOVORA_APT_SOURCES_DIR="${S}" NOVORA_MODPROBE_DIR="${TMP}/modprobe" NOVORA_MOK_PUB="${TMP}/mok.pub"
echo "boot=live components" > "${TMP}/cmd-live"; echo "root=UUID=x ro quiet" > "${TMP}/cmd-inst"
if [[ "${EUID}" -ne 0 ]]; then echo "  OMITIDAS: instalación NVIDIA (requiere root)"; else
  NOVORA_CMDLINE="${TMP}/cmd-live" bash "${BIN}/novora-gpu" nvidia instalar <<<"NVIDIA" >/dev/null 2>&1 \
    && bad "permitió instalar en sesión Live" || ok "rechaza instalar el driver en la sesión Live"
  NOVORA_CMDLINE="${TMP}/cmd-inst" bash "${BIN}/novora-gpu" nvidia instalar <<<"no" >/dev/null 2>&1 \
    && bad "instaló sin confirmación" || ok "cancelar sin escribir NVIDIA"
  [[ ! -s "${LOG}" ]] && grep -q "^Components: main non-free-firmware$" "${S}/sources.list.d/debian.sources" \
    && ok "al cancelar no cambia nada" || bad "cambios tras cancelar"
  NOVORA_CMDLINE="${TMP}/cmd-inst" bash "${BIN}/novora-gpu" nvidia instalar --cuda <<<"NVIDIA" >/dev/null 2>&1 \
    && ok "instalación confirmada termina" || bad "instalación"
  grep -q "^Components: main non-free-firmware non-free contrib$" "${S}/sources.list.d/debian.sources" \
    && ok "habilita contrib y non-free (deb822)" || bad "fuentes: $(grep Components "${S}/sources.list.d/debian.sources")"
  grep -q "apt-get install -y linux-headers-amd64 dkms nvidia-driver nvidia-smi nvidia-settings libnvcuvid1 libnvidia-encode1 firmware-misc-nonfree nvidia-cuda-toolkit" "${LOG}" \
    && ok "instala driver + NVDEC/NVENC + CUDA" || bad "paquetes: $(cat "${LOG}")"
  grep -q "mokutil --import ${TMP}/mok.pub" "${LOG}" && ok "Secure Boot: registra la clave MOK" || bad "MOK"
  grep -q "modeset=1" "${TMP}/modprobe/novora-nvidia.conf" && ok "nvidia-drm modeset=1 (Wayland)" || bad "modprobe"
  NOVORA_CMDLINE="${TMP}/cmd-inst" bash "${BIN}/novora-gpu" nvidia instalar <<<"NVIDIA" >/dev/null 2>&1
  [[ "$(grep -c "non-free contrib" "${S}/sources.list.d/debian.sources")" -eq 1 ]] && ! grep -q "non-free non-free" "${S}/sources.list.d/debian.sources" \
    && ok "repetir la instalación no duplica componentes" || bad "idempotencia"
  fake lspci 'echo "00:02.0 VGA compatible controller [0300]: Intel UHD [8086:46a3]"'
  NOVORA_CMDLINE="${TMP}/cmd-inst" bash "${BIN}/novora-gpu" nvidia instalar <<<"NVIDIA" >/dev/null 2>&1 \
    && bad "instaló sin GPU NVIDIA" || ok "sin GPU NVIDIA no instala nada"
fi

echo "2) novora-win"
: > "${LOG}"
fake wine 'echo "wine WINEPREFIX=$WINEPREFIX $*" >> "$LOG"; [ "$1" = wineboot ] && mkdir -p "$WINEPREFIX/dosdevices"; exit 0'
printf 'hola' > "${TMP}/texto.exe"
bash "${BIN}/novora-win" ejecutar "${TMP}/texto.exe" >/dev/null 2>&1 && bad "aceptó un .exe falso" || ok "rechaza archivos que no son de Windows"
printf 'MZ\x90\x00resto' > "${TMP}/NOVORA-LINK.exe"
bash "${BIN}/novora-win" ejecutar "${TMP}/NOVORA-LINK.exe" --modo prueba >/dev/null 2>&1
grep -q "wine WINEPREFIX=${HOME}/.local/share/novora-win/NOVORA-LINK wineboot --init" "${LOG}" \
  && grep -q "wine WINEPREFIX=${HOME}/.local/share/novora-win/NOVORA-LINK ${TMP}/NOVORA-LINK.exe --modo prueba" "${LOG}" \
  && ok "crea prefijo propio y ejecuta el .exe con sus argumentos" || bad "ejecutar: $(cat "${LOG}")"
printf '\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1resto' > "${TMP}/setup.msi"
bash "${BIN}/novora-win" ejecutar "${TMP}/setup.msi" >/dev/null 2>&1
grep -q "msiexec /i ${TMP}/setup.msi" "${LOG}" && ok "los .msi se instalan con msiexec" || bad "msi"
bash "${BIN}/novora-win" borrar .. <<<"si" >/dev/null 2>&1 && bad "aceptó prefijo '..'" || ok "rechaza nombres de prefijo peligrosos"
apps_out="$(bash "${BIN}/novora-win" apps 2>&1)"; grep -q "^NOVORA-LINK" <<<"${apps_out}" && ok "lista los prefijos" || bad "apps: ${apps_out} / $(ls -la "${HOME}/.local/share/novora-win" 2>&1)"

echo "2b) novora-win: antivirus, optimizar y perfiles"
: > "${LOG}"
fake novora-antivirus 'echo "av $*" >> "$LOG"; case "$2" in *VIRUS*) exit 1;; *) exit 0;; esac'
printf 'MZvirus' > "${TMP}/VIRUS.exe"
bash "${BIN}/novora-win" ejecutar "${TMP}/VIRUS.exe" >/dev/null 2>&1 && bad "ejecutó un .exe con amenaza" || ok "bloquea un .exe con amenaza"
! grep -q "wine WINEPREFIX=.*VIRUS.exe" "${LOG}" && ok "Wine nunca recibió el .exe infectado" || bad "wine llamado con virus"
printf 'MZlimpio' > "${TMP}/Juego.exe"
bash "${BIN}/novora-win" ejecutar "${TMP}/Juego.exe" >/dev/null 2>&1
bash "${BIN}/novora-win" ejecutar "${TMP}/Juego.exe" >/dev/null 2>&1
[[ "$(grep -c "av analizar ${TMP}/Juego.exe" "${LOG}")" -eq 1 ]] && ok "analiza solo la primera vez (caché por SHA256)" || bad "caché av: $(cat "${LOG}")"
printf 'MZlimpio-v2' > "${TMP}/Juego.exe"
bash "${BIN}/novora-win" ejecutar "${TMP}/Juego.exe" >/dev/null 2>&1
[[ "$(grep -c "av analizar ${TMP}/Juego.exe" "${LOG}")" -eq 2 ]] && ok "si el .exe cambia, se vuelve a analizar" || bad "reanálisis"
SH="${TMP}/share"; mkdir -p "${SH}/dxvk/x64" "${SH}/dxvk/x32" "${SH}/vkd3d-proton/x64" "${SH}/vkd3d-proton/x86"
for d in d3d9 d3d11 dxgi; do touch "${SH}/dxvk/x64/${d}.dll" "${SH}/dxvk/x32/${d}.dll"; done
touch "${SH}/vkd3d-proton/x64/d3d12.dll" "${SH}/vkd3d-proton/x86/d3d12.dll"
fake gamemoderun 'echo "gamemoderun $*" >> "$LOG"; exec "$@"'
fake novora-gpu 'case "$1" in estado) echo "NVIDIA: RTX 3050";; usar-nvidia) shift; echo "usar-nvidia" >> "$LOG"; exec "$@";; esac'
: > "${LOG}"
out="$(NOVORA_WIN_SHARE="${SH}" bash "${BIN}/novora-win" optimizar Juego 2>&1)"
P="${HOME}/.local/share/novora-win/Juego/drive_c/windows"
[[ -f "${P}/system32/d3d11.dll" && -f "${P}/syswow64/d3d9.dll" && -f "${P}/system32/d3d12.dll" && -f "${P}/syswow64/d3d12.dll" ]] \
  && ok "optimizar instala DXVK y VKD3D-Proton (64 y 32 bits) sin internet" || bad "dlls: ${out}"
grep -q "reg add HKEY_CURRENT_USER.Software.Wine.DllOverrides /v d3d12 /d native /f" "${LOG}" && ok "registra las DLL como nativas" || bad "overrides: $(cat "${LOG}")"
grep -q "^GAMEMODE=1$" "${HOME}/.config/novora-win/perfiles/Juego.conf" && grep -q "^GPU=nvidia$" "${HOME}/.config/novora-win/perfiles/Juego.conf" \
  && ok "perfil: GameMode + NVIDIA automáticos" || bad "perfil optimizar"
: > "${LOG}"
DISPLAY=:0 bash "${BIN}/novora-win" perfil Juego WAYLAND=1 >/dev/null
fake wine 'echo "wine DISPLAY=${DISPLAY:-ninguno} $*" >> "$LOG"; exit 0'
DISPLAY=:0 bash "${BIN}/novora-win" ejecutar "${TMP}/Juego.exe" >/dev/null 2>&1
grep -q "^usar-nvidia$" "${LOG}" && grep -q "^gamemoderun " "${LOG}" && grep -q "wine DISPLAY=ninguno ${TMP}/Juego.exe" "${LOG}" \
  && ok "ejecuta con NVIDIA + GameMode + Wayland" || bad "envoltorios: $(cat "${LOG}")"
bash "${BIN}/novora-win" perfil Juego 'DLL_OVERRIDES=x;rm -rf ~' >/dev/null 2>&1 && bad "aceptó valor con ;" || ok "perfil rechaza valores peligrosos"
printf 'GPU=nvidia\nWINEDEBUG=+all\nDXVK_HUD=$(id)\n' > "${HOME}/.config/novora-win/perfiles/Juego.conf"
o="$(bash "${BIN}/novora-win" perfil Juego)"
! grep -q "WINEDEBUG" <<<"${o}" && grep -q "^DXVK_HUD=$" <<<"${o}" && ok "perfil editado a mano: ignora claves y valores no permitidos" || bad "parser perfil: ${o}"
rm -f "${F}/novora-antivirus" "${F}/novora-gpu" "${F}/gamemoderun"

echo "2c) novora-antivirus"
fake clamscan-falso 'for a; do last="$a"; done; case "$last" in *eicar*) echo "$last: Eicar-Test-Signature FOUND"; exit 1;; *) exit 0;; esac'
export NOVORA_CLAMSCAN=clamscan-falso
printf 'limpio' > "${TMP}/doc.txt"; printf 'x' > "${TMP}/eicar.com"
if bash "${BIN}/novora-antivirus" analizar "${TMP}/doc.txt" >/dev/null; then ok "archivo limpio → código 0"; else bad "limpio"; fi
o="$(bash "${BIN}/novora-antivirus" analizar "${TMP}/eicar.com")"; rc=$?
[[ ${rc} -eq 1 ]] && grep -q "Eicar-Test-Signature FOUND" <<<"${o}" && ok "amenaza → código 1 y nombre de la firma" || bad "amenaza: ${rc} ${o}"
NOVORA_CLAMSCAN=no-existe bash "${BIN}/novora-antivirus" analizar "${TMP}/doc.txt" >/dev/null 2>&1; [[ $? -eq 2 ]] && ok "sin ClamAV → código 2 (no finge estar limpio)" || bad "sin clamav"
mkdir -p "${TMP}/db"; touch -d '10 days ago' "${TMP}/db/main.cvd"; touch -d '9 days ago' "${TMP}/db/daily.cld"
o="$(NOVORA_CLAM_DB="${TMP}/db" bash "${BIN}/novora-antivirus" estado)"
grep -q "2 bases; la más reciente tiene 9 día" <<<"${o}" && grep -q "AVISO: firmas con más de 7 días" <<<"${o}" && ok "estado avisa de firmas viejas" || bad "estado: ${o}"
unset NOVORA_CLAMSCAN

echo "3) novora-dev"
: > "${LOG}"
fake dotnet 'echo "dotnet $*" >> "$LOG"
if [ "$1" = publish ]; then while [ $# -gt 0 ]; do [ "$1" = -o ] && out="$2"; shift; done; printf "MZfake" > "$out/LinkApp.exe"; fi'
fake novora-win 'echo "novora-win PREFIX=$NOVORA_WIN_PREFIX $*" >> "$LOG"'
mkdir -p "${TMP}/repo/LinkApp" && touch "${TMP}/repo/NOVORA-LINK.sln" "${TMP}/repo/LinkApp/LinkApp.csproj"
bash "${BIN}/novora-dev" compilar "${TMP}/repo/NOVORA-LINK.sln" >/dev/null
grep -q "dotnet build ${TMP}/repo/NOVORA-LINK.sln -p:EnableWindowsTargeting=true" "${LOG}" \
  && ok "compila la solución WPF en Linux (EnableWindowsTargeting)" || bad "compilar: $(cat "${LOG}")"
bash "${BIN}/novora-dev" ejecutar-windows "${TMP}/repo/LinkApp/LinkApp.csproj" >/dev/null 2>&1
grep -q -- "dotnet publish ${TMP}/repo/LinkApp/LinkApp.csproj -c Release -r win-x64 --self-contained true -p:EnableWindowsTargeting=true" "${LOG}" \
  && ok "publica .exe autocontenido win-x64" || bad "publish: $(cat "${LOG}")"
grep -q "novora-win PREFIX=novora-link ejecutar ${HOME}/NOVORA-builds/LinkApp-win-x64/LinkApp.exe" "${LOG}" \
  && ok "lo abre con Wine en el prefijo novora-link" || bad "ejecutar-windows: $(cat "${LOG}")"
bash "${BIN}/novora-dev" publicar-windows "${TMP}/repo/NOVORA-LINK.sln" >/dev/null 2>&1 && bad "aceptó .sln para publicar" || ok "publicar exige el .csproj"
mkdir -p "${TMP}/as/android-studio/bin" && printf '#!/bin/sh\n' > "${TMP}/as/android-studio/bin/studio.sh" && chmod +x "${TMP}/as/android-studio/bin/studio.sh"
tar -czf "${TMP}/as.tar.gz" -C "${TMP}/as" android-studio
bash "${BIN}/novora-dev" instalar android-studio "${TMP}/as.tar.gz" --sha256 "$(printf '0%.0s' {1..64})" >/dev/null 2>&1 \
  && bad "instaló con SHA256 incorrecto" || ok "rechaza SHA256 incorrecto"
bash "${BIN}/novora-dev" instalar android-studio "${TMP}/as.tar.gz" --sha256 "$(sha256sum "${TMP}/as.tar.gz" | cut -d' ' -f1)" >/dev/null 2>&1
[[ -x "${HOME}/.local/opt/android-studio/bin/studio.sh" && -f "${HOME}/.local/share/applications/novora-android-studio.desktop" ]] \
  && ok "instala Android Studio y lo añade al menú" || bad "instalar android-studio"
mkdir -p "${TMP}/evil/x" && touch "${TMP}/evil/x/a" && tar -czf "${TMP}/evil.tar.gz" -C "${TMP}/evil" x --transform 's,^x/a,x/../../escapado,'
bash "${BIN}/novora-dev" instalar rider "${TMP}/evil.tar.gz" >/dev/null 2>&1 && bad "aceptó tar con '..'" || ok "rechaza archivos con rutas '..'"
[[ ! -e "${HOME}/.local/escapado" && ! -e "${TMP}/escapado" ]] && ok "no se escribió fuera del destino" || bad "escape de ruta"

echo "4) actualizaciones"
PRE="${HERE}/../config/includes.chroot/usr/lib/novora/novora-instantanea-pre-apt"
: > "${LOG}"
fake timeshift 'echo "timeshift $*" >> "$LOG"'
export NOVORA_SNAP_FLAG="${TMP}/snapflag" NOVORA_SNAP_STAMP="${TMP}/stamp" NOVORA_SNAP_LOG="${TMP}/snap.log" NOVORA_CMDLINE="${TMP}/cmd-inst"
sh "${PRE}"; [[ ! -s "${LOG}" ]] && ok "sin activar: no crea instantáneas" || bad "instantánea sin activar"
touch "${NOVORA_SNAP_FLAG}"
NOVORA_CMDLINE="${TMP}/cmd-live" sh "${PRE}"; [[ ! -s "${LOG}" ]] && ok "en la sesión Live: no crea instantáneas" || bad "instantánea en live"
sh "${PRE}" >/dev/null; sh "${PRE}" >/dev/null
[[ "$(grep -c 'timeshift --create --scripted --tags D' "${LOG}")" -eq 1 ]] && ok "crea 1 instantánea y respeta el límite de 1 por hora" || bad "instantáneas: $(cat "${LOG}")"
fake timeshift 'exit 3'; rm -f "${NOVORA_SNAP_STAMP}"
if sh "${PRE}" >/dev/null 2>&1; then ok "si Timeshift falla, apt continúa (código 0)"; else bad "pre-apt bloquea apt"; fi
unset NOVORA_SNAP_FLAG NOVORA_SNAP_STAMP NOVORA_SNAP_LOG NOVORA_CMDLINE
if [[ "${EUID}" -eq 0 ]]; then
  : > "${LOG}"
  NOVORA_APT=apt-get bash "${BIN}/novora-actualizar" ahora <<<"no" >/dev/null 2>&1 && bad "actualizó sin confirmar" || ok "ahora: cancelar sin escribir 'si'"
  ! grep -q "full-upgrade -y" "${LOG}" && ok "al cancelar no se instala nada" || bad "instaló tras cancelar"
  NOVORA_APT=apt-get bash "${BIN}/novora-actualizar" ahora <<<"si" >/dev/null 2>&1
  grep -q "apt-get full-upgrade -y" "${LOG}" && ok "ahora: actualiza tras confirmar" || bad "ahora: $(cat "${LOG}")"
fi
bash "${BIN}/novora-actualizar" estado >/dev/null 2>&1 && ok "estado funciona" || bad "estado"
CONF="${HERE}/../config/includes.chroot/etc/apt/apt.conf.d"
grep -q 'Automatic-Reboot "false"' "${CONF}/52novora-unattended-upgrades" && grep -q 'Remove-Unused-Kernel-Packages "false"' "${CONF}/52novora-unattended-upgrades" \
  && grep -q -- '-security,label=Debian-Security' "${CONF}/52novora-unattended-upgrades" && ok "solo seguridad, sin reinicios, conserva kernel anterior" || bad "unattended conf"

echo "5) novora-apariencia"
: > "${LOG}"
for t in kwriteconfig6 plasma-apply-colorscheme plasma-apply-lookandfeel qdbus6; do fake "${t}" "echo \"${t} \$*\" >> \"\$LOG\""; done
AP="${BIN}/novora-apariencia"
bash "${AP}" oscuro >/dev/null && grep -q "plasma-apply-colorscheme NovoraOscuro" "${LOG}" && ok "modo oscuro" || bad "oscuro"
bash "${AP}" acento violeta >/dev/null && grep -q "plasma-apply-colorscheme --accent-color #8b5cf6" "${LOG}" && ok "acento por nombre" || bad "acento"
bash "${AP}" acento '#12ab9F' >/dev/null && grep -q -- "--accent-color #12ab9F" "${LOG}" && ok "acento #rrggbb" || bad "acento hex"
bash "${AP}" acento 'rojo;rm' >/dev/null 2>&1 && bad "aceptó color inválido" || ok "rechaza colores no válidos"
bash "${AP}" ligero on >/dev/null && grep -q "kwriteconfig6 --file kwinrc --group Plugins --key blurEnabled false" "${LOG}" \
  && grep -q "AnimationDurationFactor 0$" "${LOG}" && grep -q "qdbus6 org.kde.KWin /KWin reconfigure" "${LOG}" && ok "modo ligero: sin desenfoque ni animaciones y recarga KWin" || bad "ligero"
bash "${AP}" botones derecha >/dev/null && grep -q "ButtonsOnRight IAX" "${LOG}" && ok "botones a la derecha" || bad "botones"
bash "${AP}" restablecer >/dev/null && grep -q "plasma-apply-lookandfeel --apply org.novora.desktop --resetLayout" "${LOG}" && ok "restablecer diseño NOVORA" || bad "restablecer"
node "${HERE}/visual/test_layout.js" "${HERE}/../config/includes.chroot/usr/share/plasma/look-and-feel/org.novora.desktop/contents/layouts/org.kde.plasma.desktop-layout.js" >/dev/null \
  && ok "layout.js correcto contra la API de Plasma simulada" || bad "layout.js"

echo "Resultado: ${pass} PASÓ, ${fail} FALLÓ"
[[ "${fail}" -eq 0 ]]
