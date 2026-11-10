#!/bin/bash
# Put the device firmware listed by /usr/libexec/opd2413/early-firmware into
# the initramfs. dracut carries on when a module fails, so the kernel-install
# plugin 60-opd2413-initrd-check.install verifies the result.

check() {
    return 0
}

depends() {
    return 0
}

install() {
    local _opd_root=${dracutsysrootdir-}
    local _opd_path _opd_list

    _opd_list=$("$_opd_root/usr/libexec/opd2413/early-firmware" "$_opd_root") || {
        dfatal "opd2413: device firmware is incomplete"
        return 1
    }
    while read -r _opd_path; do
        inst_simple "$_opd_root$_opd_path" "$_opd_path" || return 1
    done <<< "$_opd_list"
}
