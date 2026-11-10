#!/bin/bash
# Install the kernel and device packages into the Fedora root prepared by
# install-rootfs.sh and let kernel-install deploy them to the ESP. Runs on the
# tablet as root, from the system that is currently booted.
#
# Writes to the ESP: /fedora/<kver>/{linux,initrd,<dtb>} and
# /loader/entries/fedora-<kver>.conf. loader.conf, systemd-boot, KSHIM.CHO and
# every existing entry must come out unchanged; the script checks that.
#
# Usage: install-kernel.sh RPM_DIR
#   RPM_DIR holds the four packages and SHA256SUMS from tools/collect-rpms.sh.
# Environment: OPD_MIRROR as in install-rootfs.sh (dependencies come from the
# Fedora repositories).
set -euo pipefail

rpms=$(realpath -e "${1:?rpm dir}")
release=${OPD_RELEASE:-45}
mirror=${OPD_MIRROR:-}
work=/run/opd2413-install
target=${work}/target
esp=/boot/efi
image=registry.fedoraproject.org/fedora:${release}
# Kernel 64 MB + initramfs about 93 MB, plus slack for FAT cluster rounding.
need_bytes=$((200 * 1024 * 1024))

step() { printf '\n==> %s\n' "$*"; }
die() { echo "install-kernel: $*" >&2; exit 1; }
# Files on the ESP that this step must not change.
fingerprint() {
    (cd "${esp}" && find . -type f ! -path './fedora/*' ! -name 'fedora-*.conf' -print0 \
        | sort -z | xargs -0 sha256sum)
}

[ "$(id -u)" = 0 ] || die "must run as root"
mountpoint -q "${target}" || die "${target} is not mounted; run install-rootfs.sh first"
mountpoint -q "${esp}" || die "the ESP is not mounted at ${esp}"
[ "$(findmnt -no SOURCE "${esp}")" = "$(readlink -f /dev/disk/by-partlabel/ARMADA)" ] \
    || die "${esp} is not the ARMADA partition"
(cd "${rpms}" && sha256sum --quiet --check SHA256SUMS) || die "package checksums do not match"
free=$(df -B1 --output=avail "${esp}" | tail -1)
[ "${free}" -ge "${need_bytes}" ] || die "ESP has ${free} bytes free, need ${need_bytes}"
[ -s "${target}/etc/kernel/cmdline" ] || die "missing /etc/kernel/cmdline in the target"
[ -e "${esp}/fedora" ] && die "${esp}/fedora already exists; remove it before a retry"

step "ESP before"
fingerprint > "${work}/esp-before.sha256"
df -h "${esp}" | tail -1

step "Install the packages (kernel-install writes to the ESP)"
mount --bind "${esp}" "${target}${esp}"
trap 'umount "${target}${esp}"' EXIT
podman run --rm --privileged --network host -e MIRROR="${mirror}" -v "${target}:/target" -v "${rpms}:/rpms:ro" "${image}" bash -euc '
    if [ -n "${MIRROR}" ]; then
        sed -i -e "s|^metalink=|#metalink=|" \
            -e "s|^#baseurl=http://download.example/pub/fedora/linux|baseurl=${MIRROR}|" \
            /usr/share/dnf5/repos.d/fedora.repo /usr/share/dnf5/repos.d/fedora-updates.repo
    fi
    mount -t proc proc /target/proc
    mount --rbind /sys /target/sys
    mount --rbind /dev /target/dev
    mountpoint -q /target/boot/efi
    dnf -y --installroot=/target --use-host-config --releasever='"${release}"' install /rpms/*.rpm
    dnf -y --installroot=/target clean all
    # On a retry the kernel package is already installed and its scriptlet
    # does not run again, so deploy it here.
    kver=$(ls /target/usr/lib/modules)
    if [ ! -e "/target/boot/efi/loader/entries/fedora-${kver}.conf" ]; then
        chroot /target kernel-install add "${kver}" "/usr/lib/modules/${kver}/vmlinuz"
    fi
'

step "Check the result"
kver=$(ls "${target}/usr/lib/modules")
entry=${esp}/loader/entries/fedora-${kver}.conf
for file in "${esp}/fedora/${kver}/linux" "${esp}/fedora/${kver}/initrd" \
    "${esp}/fedora/${kver}/sm8750-oneplus-pad2pro.dtb" "${entry}"; do
    [ -s "${file}" ] || die "missing on the ESP: ${file}"
done
cmp "${target}/usr/lib/modules/${kver}/vmlinuz" "${esp}/fedora/${kver}/linux"
grep -qx "linux      /fedora/${kver}/linux" "${entry}" || die "unexpected linux line in ${entry}"
grep -qx "initrd     /fedora/${kver}/initrd" "${entry}" || die "unexpected initrd line in ${entry}"
grep -q "^options .*rootflags=subvol=fedora" "${entry}" || die "entry does not select the fedora subvolume"
fingerprint > "${work}/esp-after.sha256"
cmp "${work}/esp-before.sha256" "${work}/esp-after.sha256" \
    || die "files outside the Fedora entry changed on the ESP (compare ${work}/esp-*.sha256)"
sync
cat "${entry}"
df -h "${esp}" | tail -1
echo "Kernel ${kver} deployed. The default boot entry is unchanged."
