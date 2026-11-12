#!/bin/bash
# This module is outside device/ and is not installed by any production package.
# The offline builder must explicitly --add opd2413-bootlog and supply private
# identity + a target-architecture static collector. Never infer UUIDs on build host.
check() { return 255; }
depends() { echo 'bash dracut-systemd'; }
installkernel() { instmods ext4; }

install() {
    local collector=${OPD2413_BOOTLOG_COLLECTOR-} identity=${OPD2413_BOOTLOG_IDENTITY-}
    [[ -n $collector && -x $collector && -n $identity && -f $identity && ! -L $identity ]] || {
        dfatal 'opd2413-bootlog: explicit collector/private identity required'
        return 1
    }
    # Validate contents as data, never source the private file as shell code.
    . "$moddir/bootlog-lib.sh"
    local props part fs
    props=$(<"$identity")
    part=$(bootlog_property "$props" PARTUUID) && bootlog_uuid "$part" || return 1
    fs=$(bootlog_property "$props" FSUUID) && bootlog_uuid "$fs" || return 1
    inst_simple "$collector" /usr/libexec/opd2413-bootlog/kmsg-to-file || return 1
    inst_simple "$identity" /etc/opd2413-bootlog.identity || return 1
    chmod 0600 "$initdir/etc/opd2413-bootlog.identity" || return 1
    inst_simple "$moddir/bootlog-lib.sh" /usr/libexec/opd2413-bootlog/lib.sh || return 1
    inst_script "$moddir/bootlog-control" /usr/libexec/opd2413-bootlog/control || return 1
    inst_script "$moddir/bootlog-generator" "$systemdutildir/system-generators/opd2413-bootlog-generator" || return 1
    inst_simple "$moddir/opd2413-bootlog.service" "$systemdsystemunitdir/opd2413-bootlog.service" || return 1
    inst_simple "$moddir/device-timeout.conf" \
        "$systemdsystemunitdir/dev-disk-by\\x2dpartlabel-ARMADA_BOOT.device.d/20-bootlog-timeout.conf" || return 1
    inst_multiple mount umount readlink stat du sync awk udevadm dumpe2fs mkdir chmod ln || return 1
    # No static wants symlink. The generator adds it only with exact opt-in.
}
