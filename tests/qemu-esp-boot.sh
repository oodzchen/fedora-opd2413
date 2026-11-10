#!/bin/bash
# Offline check of the boot chain's last hop: the QEMU build of the tablet's
# U-Boot reads a copy of the real ESP that also holds the Fedora entry written
# by kernel-install, starts systemd-boot, and systemd-boot starts the kernel's
# EFI stub. No device is involved.
#
# Usage: qemu-esp-boot.sh ESP_IMAGE ESP_TREE OUT_DIR
#   ESP_IMAGE  raw copy of the tablet's ESP partition (private)
#   ESP_TREE   esp/ produced by package-install-test.sh
# Environment (private inputs from the Armada port's work tree):
#   ARMADA_REPO   armada checkout with porting/oneplus-pad-2-pro/uboot
#   UBOOT_QEMU    u-boot-nodtb.bin built with --ufs-blk-ramdisk --esp-ufs ARMADA
#   GPT_DIR       primary.bin and backup.bin of LUN0
#   ABL_FDT       the FDT ABL hands to the kernel
#   SD_BOOT       optional systemd-bootaa64.efi to install as /EFI/BOOT/BOOTAA64.EFI
#                 (default: keep the loader that is on the ESP image)
#
# The harness waits for U-Boot to regain control. A kernel that starts never
# returns, so the expected outcome is the harness timing out after U-Boot's
# ExitBootServices hook has run, which only a started kernel triggers.
set -euo pipefail

esp_image=$(realpath -e "${1:?ESP image}")
esp_tree=$(realpath -e "${2:?ESP tree}")
out=$(realpath -m "${3:?output dir}")
armada=${ARMADA_REPO:?}
uboot=${UBOOT_QEMU:?}
gpt=${GPT_DIR:?}
fdt=${ABL_FDT:?}
tools=${armada}/porting/oneplus-pad-2-pro/uboot

# LUN0 geometry of the tablet (4 KiB blocks).
lun_blocks=124196864
backup_gpt_lba=124196859
esp_lba=57087744

rm -rf "${out}"
mkdir -p "${out}"
img=${out}/esp.img
cp --reflink=auto "${esp_image}" "${img}"
export MTOOLS_SKIP_CHECK=1

# Same edit the install performs on the tablet: drop the rollback deployments
# to make room, then add the Fedora kernel, initrd, DTB and entry.
for entry in $(mdir -b -i "${img}" ::/loader/entries/ | tr -d '\r'); do
    text=$(mtype -i "${img}" "${entry}")
    if grep -q '^title .*(Rollback)' <<< "${text}"; then
        dir=$(sed -n 's|^linux \(/ostree/[^/]*\)/.*|\1|p' <<< "${text}")
        [ -n "${dir}" ] || { echo "cannot find the kernel directory of ${entry}" >&2; exit 1; }
        mdeltree -i "${img}" "::${dir}"
    fi
    # Only for this run: with no other entry left, a started kernel can only be
    # Fedora's. The remaining deployment's files stay, so free space is real.
    mdel -i "${img}" "${entry}"
done
mcopy -s -i "${img}" "${esp_tree}/fedora" ::/
mcopy -i "${img}" "${esp_tree}"/loader/entries/fedora-*.conf ::/loader/entries/
mcopy -o -i "${img}" "${esp_tree}/dtbs/qcom/sm8750-oneplus-pad2pro.dtb" ::/dtbs/qcom/
# Only for this unattended run: on the tablet the default stays as it was and
# the Fedora entry is picked by hand the first time.
printf 'timeout 3\neditor no\ndefault fedora-*\n' > "${out}/loader.conf"
mcopy -o -i "${img}" "${out}/loader.conf" ::/loader/loader.conf
if [ -n "${SD_BOOT:-}" ]; then
    mcopy -o -i "${img}" "$(realpath -e "${SD_BOOT}")" ::/EFI/BOOT/BOOTAA64.EFI
fi
minfo -i "${img}" :: > /dev/null
mdir -i "${img}" ::/loader/entries/ > "${out}/entries.txt"
free=$(mdir -i "${img}" :: | awk '/bytes free/ {gsub(/ /, "", $0); sub(/bytesfree/, "", $0); print}')
echo "ESP free after the edit: ${free} bytes"

python3 "${tools}/make_ramdisk.py" --lun 0 --blocks "${lun_blocks}" \
    --extent "0:${gpt}/primary.bin" \
    --extent "${backup_gpt_lba}:${gpt}/backup.bin" \
    --extent "${esp_lba}:${img}" \
    --out "${out}/lun0.rdsk"

# The harness allows 60 s, sized for U-Boot alone. Emulated, systemd-boot needs
# longer to read a kernel and an initrd of 150 MB, so run a copy with a longer
# deadline.
harness=${out}/qemu_observer.py
sed 's/deadline=time.monotonic()+(60 if blk_ramdisk else 30)/deadline=time.monotonic()+'"${QEMU_DEADLINE:-300}"'/' \
    "${tools}/qemu_observer.py" > "${harness}"
grep -q "deadline=time.monotonic()+${QEMU_DEADLINE:-300}\$" "${harness}" || { echo "harness deadline line not found" >&2; exit 1; }

log=${out}/harness.log
if PYTHONPATH=${tools} python3 "${harness}" --binary "${uboot}" --fdt "${fdt}" --out "${out}/qemu" \
    --blk-ramdisk --esp-ufs --loader "${out}/lun0.rdsk@0x900000000" > "${log}" 2>&1; then
    echo "FAIL: U-Boot regained control, the kernel was not started (see ${out}/qemu/el1/console.log)" >&2
    exit 1
fi
console=${out}/qemu/el1/console-timeout.log
ram=${out}/qemu/el1/ramconsole.bin
[ -s "${ram}" ] || { echo "FAIL: no console captured" >&2; tail -5 "${log}" >&2; exit 1; }

# The decoded log stops at the menu; later output is only in the raw buffer.
fail=0
want() { grep -aq "$1" "$2" || { echo "FAIL: console lacks: $1" >&2; fail=1; }; }
want 'OPD2413_STEP esp_boot' "${console}"
want 'Fedora Linux' "${console}"
if [ -n "${SD_BOOT:-}" ]; then
    version=$(strings "${SD_BOOT}" | grep -oE 'systemd-boot [0-9][^ ]*' | head -1 || true)
    echo "loader under test: ${version}"
fi
want 'OPD2413_EXIT_BOOT_SERVICES restoring UFS: restored' "${ram}"
[ "${fail}" = 0 ] && echo "PASS: systemd-boot started the Fedora entry's kernel (ExitBootServices reached)"
exit "${fail}"
