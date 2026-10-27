#!/usr/bin/env bash
# Ejecuta todas las pruebas automáticas de NOVORA OS que NO requieren una VM.
# Las que requieren root (discos loop) se omiten sin root.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
rc=0
echo "== Sintaxis =="
for f in "${HERE}/../scripts/build-iso.sh" "${HERE}"/*.sh; do bash -n "$f" || rc=1; done
if command -v shellcheck >/dev/null; then
  shellcheck -s bash "${HERE}/../scripts/build-iso.sh" "${HERE}"/*.sh \
    "${HERE}/../config/includes.chroot/usr/local/sbin/novora-install" \
    "${HERE}/../config/includes.chroot/usr/lib/novora/novora-copiar-sistema" || rc=1
  shellcheck -s sh "${HERE}"/../config/includes.chroot/usr/lib/novora/{novora-udev-ro,grub-install-guarded,efibootmgr-readonly} \
    "${HERE}"/../config/hooks/normal/*.hook.chroot || rc=1
  shellcheck "${HERE}/../scripts/add-atlas-model.sh" \
    "${HERE}"/../config/includes.chroot/usr/local/bin/{novora-dev,novora-win,novora-gpu,novora-antivirus,novora-actualizar,novora-apariencia,novora-con-ia-local} || rc=1
  shellcheck -s sh "${HERE}"/../config/includes.chroot/usr/lib/novora/novora-instantanea-pre-apt || rc=1
else echo "(shellcheck no instalado: omitido)"; fi
echo "== Auditor e identidad (Python) =="
python3 -I "${HERE}/test_storage.py" || rc=1
echo "== ATLAS (motor simulado, sin modelo real) =="
python3 -I "${HERE}/atlas/test_atlas.py" || rc=1
echo "== Catálogo novora-apps (GitHub simulado) =="
python3 -I "${HERE}/test_apps.py" || rc=1
echo "== Desarrollo, apps de Windows y GPU (programas simulados) =="
bash "${HERE}/test_dev_win_gpu.sh" || rc=1
echo "== Envoltorios de Calamares y build-iso.sh simulado =="
bash "${HERE}/test_wrappers_and_build.sh" || rc=1
echo "== Guardián sobre discos virtuales loop (kernel real) =="
bash "${HERE}/test_guard_loop.sh"; r=$?; [[ $r -eq 0 || $r -eq 77 ]] || rc=1
echo "== Instalador sobre un Seagate virtual (LUKS2 real, chroot simulado) =="
bash "${HERE}/test_instalador_loop.sh"; r=$?; [[ $r -eq 0 || $r -eq 77 ]] || rc=1
find "${HERE}/.." -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
echo; [[ $rc -eq 0 ]] && echo "TODAS LAS PRUEBAS PASARON" || echo "HAY PRUEBAS FALLIDAS"
exit $rc
