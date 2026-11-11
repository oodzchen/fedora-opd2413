#!/bin/bash
# Install a Fedora root file system next to the system that is running on the
# tablet. Runs on the tablet as root. It only adds two btrfs subvolumes to the
# Linux partition; existing subvolumes, the ESP and every other partition are
# left alone. The kernel is installed afterwards by install-kernel.sh.
#
# Usage: install-rootfs.sh LOGIN FULL_NAME
# Environment:
#   OPD_USER_PASSWORD  initial password of LOGIN (required)
#   OPD_RELEASE        Fedora release (default 45)
#   OPD_TIMEZONE       default Asia/Singapore
#   OPD_LANG           default en_US.UTF-8
#   OPD_HOSTNAME       default opd2413
#   OPD_MIRROR         Fedora mirror base URL (the directory holding releases/
#                      and updates/); default: metalink. The metalink can hand
#                      out mirrors that serve at a few KB/s.
set -euo pipefail

login=${1:?login name}
fullname=${2:?full name}
password=${OPD_USER_PASSWORD:?initial password}
release=${OPD_RELEASE:-45}
timezone=${OPD_TIMEZONE:-Asia/Singapore}
lang=${OPD_LANG:-en_US.UTF-8}
hostname=${OPD_HOSTNAME:-opd2413}
mirror=${OPD_MIRROR:-}

root_dev=/dev/disk/by-partlabel/ARMADA_ROOT
esp_dev=/dev/disk/by-partlabel/ARMADA
root_subvol=fedora
home_subvol=fedora-home
mount_opts=noatime,compress=zstd:1,discard=async
work=/run/opd2413-install
top=${work}/top
target=${work}/target
image=registry.fedoraproject.org/fedora:${release}
kernel_excludes=(-x kernel -x kernel-core -x kernel-modules -x kernel-modules-core
    -x kernel-modules-extra -x kernel-uki-virt)

step() { printf '\n==> %s\n' "$*"; }
die() { echo "install-rootfs: $*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "must run as root"
model=$(tr -d '\0' < /sys/firmware/devicetree/base/model)
[ "${model}" = "OnePlus Pad 2 Pro" ] || die "unexpected device: ${model}"
[ "$(blkid -s TYPE -o value "${root_dev}")" = btrfs ] || die "${root_dev} is not btrfs"
[ "$(blkid -s TYPE -o value "${esp_dev}")" = vfat ] || die "${esp_dev} is not FAT"
mountpoint -q "${target}" && die "${target} is already mounted"

step "Mount the top of the btrfs file system"
mkdir -p "${top}" "${target}"
mountpoint -q "${top}" || mount -o subvolid=5,noatime "${root_dev}" "${top}"
for subvol in "${root_subvol}" "${home_subvol}"; do
    [ -e "${top}/${subvol}" ] && die "subvolume ${subvol} already exists"
done

step "Create subvolumes ${root_subvol} and ${home_subvol}"
btrfs subvolume create "${top}/${root_subvol}"
btrfs subvolume create "${top}/${home_subvol}"
mount -o "subvol=${root_subvol},${mount_opts}" "${root_dev}" "${target}"
mkdir -p "${target}/home"
mount -o "subvol=${home_subvol},${mount_opts}" "${root_dev}" "${target}/home"

step "Install Fedora ${release} KDE Plasma"
# The container supplies Fedora ${release}'s dnf and repositories. /proc, /sys
# and /dev are mounted inside its own mount namespace for package scriptlets
# and vanish with it.
podman run --rm --privileged --network host -e MIRROR="${mirror}" -v "${target}:/target" "${image}" bash -euc '
    if [ -n "${MIRROR}" ]; then
        sed -i -e "s|^metalink=|#metalink=|" \
            -e "s|^#baseurl=http://download.example/pub/fedora/linux|baseurl=${MIRROR}|" \
            /usr/share/dnf5/repos.d/fedora.repo /usr/share/dnf5/repos.d/fedora-updates.repo
        grep -h "^baseurl=" /usr/share/dnf5/repos.d/fedora.repo /usr/share/dnf5/repos.d/fedora-updates.repo
    fi
    mkdir -p /target/proc /target/sys /target/dev
    mount -t proc proc /target/proc
    mount --rbind /sys /target/sys
    mount --rbind /dev /target/dev
    dnf -y --installroot=/target --use-host-config --releasever='"${release}"' \
        '"${kernel_excludes[*]}"' \
        install @^kde-desktop-environment \
        glibc-langpack-en google-noto-sans-cjk-vf-fonts openssh-server btrfs-progs dosfstools
    dnf -y --installroot=/target clean all
'
[ -x "${target}/usr/bin/plasmashell" ] || die "Plasma was not installed"
if chroot "${target}" rpm -q kernel-core >/dev/null 2>&1; then die "a Fedora kernel got installed"; fi

step "Configure the system"
root_uuid=$(blkid -s UUID -o value "${root_dev}")
esp_uuid=$(blkid -s UUID -o value "${esp_dev}")
cat > "${target}/etc/fstab" <<EOF
UUID=${root_uuid} /         btrfs subvol=${root_subvol},${mount_opts} 0 0
UUID=${root_uuid} /home     btrfs subvol=${home_subvol},${mount_opts} 0 0
UUID=${esp_uuid}  /boot/efi vfat  umask=0077,shortname=winnt 0 2
EOF
mkdir -p "${target}/boot/efi" "${target}/etc/kernel"
echo "${hostname}" > "${target}/etc/hostname"
ln -sf "../usr/share/zoneinfo/${timezone}" "${target}/etc/localtime"
echo "LANG=${lang}" > "${target}/etc/locale.conf"
echo "KEYMAP=us" > "${target}/etc/vconsole.conf"
# A machine ID now keeps systemd from treating the first boot as unprovisioned
# and asking questions on the console.
systemd-machine-id-setup --root="${target}"

# Hardware-related arguments are the ones the 7.2.6 kernel was validated with.
# SELinux starts permissive: files are labelled on the first boot. Once that
# boot shows no AVC denials, drop enforcing=0 here and run kernel-install add
# for each installed kernel (needs a kernel with selinux in CONFIG_LSM,
# 7.2.6-3.opd2413 or later).
echo fedora > "${target}/etc/kernel/entry-token"
cat > "${target}/etc/kernel/cmdline" <<EOF
root=UUID=${root_uuid} rootflags=subvol=${root_subvol},${mount_opts} ro console=tty0 quiet loglevel=3 allow_mismatched_32bit_el0 fw_devlink.strict=1 pcie_ports=compat psi=1 cpufreq.default_governor=schedutil swiotlb=8192 clk_ignore_unused pd_ignore_unused regulator_ignore_unused enforcing=0
EOF
touch "${target}/.autorelabel"

step "Create user ${login}"
chroot "${target}" useradd -m -c "${fullname}" -G wheel "${login}"
printf '%s:%s\n' "${login}" "${password}" | chroot "${target}" chpasswd
# The account exists, so Plasma's first-run wizard must not start.
touch "${target}/etc/plasma-setup-done"

step "Debug access and network"
# Key-only SSH: the tablet joins the home network.
install -d -m 0700 "${target}/root/.ssh"
install -m 0600 /root/.ssh/authorized_keys "${target}/root/.ssh/authorized_keys"
cat > "${target}/etc/ssh/sshd_config.d/40-opd2413.conf" <<EOF
PasswordAuthentication no
KbdInteractiveAuthentication no
EOF
chroot "${target}" systemctl enable sshd.service
chroot "${target}" systemctl set-default graphical.target
connections=0
for file in /etc/NetworkManager/system-connections/*.nmconnection; do
    [ -f "${file}" ] || continue
    install -m 0600 "${file}" "${target}/etc/NetworkManager/system-connections/"
    connections=$((connections + 1))
done
echo "copied ${connections} NetworkManager connection(s)"

step "Result"
chroot "${target}" rpm -q fedora-release-kde plasma-desktop systemd selinux-policy-targeted || true
echo "packages: $(chroot "${target}" rpm -qa | wc -l)"
ls -l "${target}/etc/systemd/system/display-manager.service" "${target}/etc/systemd/system/default.target" || true
btrfs subvolume list "${top}"
df -h "${target}" | tail -1
echo "Root file system installed and left mounted at ${target}."
