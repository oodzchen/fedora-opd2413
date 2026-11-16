#!/bin/bash
# Offline check: install the package set into a clean Fedora aarch64 root and
# verify what kernel-install and dracut put on the ESP is what the boot chain
# (U-Boot -> systemd-boot) expects.
# Usage: package-install-test.sh RPM_DIR OUT_DIR
# OUT_DIR receives esp/ (the resulting ESP tree), report.txt and run.log.
set -euo pipefail

rpms=$(realpath -e "${1:?rpm dir}")
out=$(realpath -m "${2:?output dir}")
image=${FEDORA_IMAGE:-registry.fedoraproject.org/fedora:45}
cache=${DNF_CACHE:-$(dirname "${out}")/dnf-cache}
rm -rf "${out}/esp"
mkdir -p "${out}/esp" "${cache}"

# Host networking: the host proxy variables podman forwards point at 127.0.0.1.
# /boot/efi must be a mount point: kernel-install writes entry paths relative
# to the file system that holds BOOT_ROOT, as it does for the real ESP.
podman run --rm --arch arm64 --network host --tmpfs /boot/efi:rw,exec \
    -v "${rpms}:/in:ro,Z" -v "${out}:/out:Z" -v "${cache}:/var/cache/libdnf5:Z" \
    "${image}" bash -euxc '
mkdir -p /boot/efi/loader/entries /boot/efi/EFI/BOOT /etc/kernel
echo fedora > /etc/kernel/entry-token
echo "root=UUID=00000000-0000-0000-0000-000000000000 rootflags=subvol=fedora ro" > /etc/kernel/cmdline
# A container is not the tablet; host-only detection here would describe the
# build host, so the test builds a generic image.
mkdir -p /etc/dracut.conf.d
echo hostonly=no > /etc/dracut.conf.d/zz-test-generic.conf

# dracut-config-rescue comes with every Fedora desktop environment and adds a
# kernel-install plugin of its own; the device package must keep it off the ESP.
dnf -y --setopt=install_weak_deps=False --setopt=keepcache=True install dracut-config-rescue /in/*.rpm

kver=$(ls /usr/lib/modules)
{
    rpm -q systemd dracut alsa-ucm qcom-firmware kernel-opd2413 opd2413-firmware opd2413-device opd2413-audio
    echo "--- esp"; (cd /boot/efi && find . -type f -printf "%s %p\n" | sort -k2)
    echo "--- entry"; cat /boot/efi/loader/entries/*.conf
    echo "--- fedora kernels visible to dnf"; dnf -q repoquery kernel-core kernel 2>&1 | head -5
    echo "--- end"
} > /out/report.txt 2>&1
lsinitrd "/boot/efi/fedora/${kver}/initrd" > /out/initrd-list.txt
/usr/libexec/opd2413/early-firmware > /out/early-firmware.txt
cp -r /boot/efi/. /out/esp/

# Negative case: an initramfs built without the device firmware must make the
# kernel installation fail instead of producing a bootable but crippled entry.
echo "omit_dracutmodules+=\" opd2413 \"" > /etc/dracut.conf.d/zz-test-omit.conf
if kernel-install add "${kver}" "/usr/lib/modules/${kver}/vmlinuz" > /out/negative.log 2>&1; then
    echo accepted > /out/negative.txt
else
    echo refused > /out/negative.txt
fi
' > "${out}/run.log" 2>&1 || { tail -30 "${out}/run.log" >&2; exit 1; }

cat "${out}/report.txt"
esp=${out}/esp
kver=$(ls "${esp}/fedora")
[ "$(echo "${kver}" | wc -w)" = 1 ] || { echo "FAIL: expected one kernel on the ESP: ${kver}" >&2; exit 1; }
kre=${kver//./\\.}
entry=${esp}/loader/entries/fedora-${kver}.conf
fail=0
bad() { echo "FAIL: $*" >&2; fail=1; }
has() { grep -qxE "$1" "${entry}" || bad "entry lacks: $1"; }
has "linux +/fedora/${kre}/linux"
has "initrd +/fedora/${kre}/initrd"
has "devicetree +/fedora/${kre}/sm8750-oneplus-pad2pro\\.dtb"
has 'options +root=UUID=.* rootflags=subvol=fedora ro'
for f in fedora/${kver}/linux fedora/${kver}/initrd dtbs/qcom/sm8750-oneplus-pad2pro.dtb; do
    [ -s "${esp}/${f}" ] || bad "missing on ESP: ${f}"
done
cmp -s "${esp}/dtbs/qcom/sm8750-oneplus-pad2pro.dtb" "${esp}/fedora/${kver}/sm8750-oneplus-pad2pro.dtb" \
    || bad "fixed-path DTB differs from the entry DTB"

# Every device firmware file must be inside the initramfs: 63 stock files (incl.
# vpu35_4v.mbn), the audio topology and three Adreno microcode files.
need=${out}/early-firmware.txt
[ "$(wc -l < "${need}")" = 67 ] || bad "expected 67 early firmware files, the helper lists $(wc -l < "${need}")"
missing=0
while read -r path; do
    grep -qE "[[:space:]]${path#/}\$" "${out}/initrd-list.txt" || { bad "initramfs lacks ${path}"; missing=$((missing + 1)); }
done < "${need}"
echo "initramfs: $(stat -c %s "${esp}/fedora/${kver}/initrd") bytes, $(wc -l < "${need}") device firmware files required, ${missing} missing"
grep -A3 -e '--- fedora kernels' "${out}/report.txt" | grep -q '^kernel' && bad "Fedora kernel packages are not excluded"

[ "$(cat "${out}/negative.txt")" = refused ] || bad "kernel-install accepted an initramfs without device firmware"
grep -q 'opd2413-initrd-check: the initramfs lacks device firmware' "${out}/negative.log" \
    || bad "the refusal did not come from the initramfs check"

[ -e "${esp}/fedora/0-rescue" ] && bad "a rescue image was written to the ESP"

[ "${fail}" = 0 ] && echo "PASS: package install"
exit "${fail}"
