#!/bin/bash
# Functions take explicit inputs so offline fixtures never need a real disk.
# The installed control/generator pin all production paths; no test override.

bootlog_fail() { printf 'opd2413-bootlog: %s\n' "$*" >&2; return 1; }

bootlog_enabled() {
    local line token count=0 enabled=0
    local -a tokens
    IFS= read -r line < "$1" || return 1
    read -r -a tokens <<< "$line"
    for token in "${tokens[@]}"; do
        case "$token" in
            rd.opd2413.bootlog=*)
                count=$((count+1))
                [[ $token == rd.opd2413.bootlog=1 ]] && enabled=1
                ;;
        esac
    done
    [[ $count == 1 && $enabled == 1 ]]
}

bootlog_generate() {
    local output=$1 cmdline=$2 initrd_release=$3 unit=$4
    [[ -f $initrd_release ]] || return 0
    bootlog_enabled "$cmdline" || return 0
    mkdir -p -m 0755 -- "$output/initrd.target.wants" || return 1
    ln -s -- "$unit" "$output/initrd.target.wants/opd2413-bootlog.service"
}

bootlog_property() {
    awk -v key="$2" 'index($0,key"=")==1 {n++; value=substr($0,length(key)+2)}
        END {if(n!=1) exit 1; print value}' <<< "$1"
}

bootlog_uuid() {
    [[ $1 =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]
}

bootlog_identity() {
    local props=$1 syspath=$2 partition=$3 sectors=$4 readonly=$5 identity=$6
    local actual expected
    [[ $syspath == /sys/devices/platform/soc@0/1d84000.ufs/host*/target*:0:0/*:0:0:0/block/sda/sda17 ]] ||
        { bootlog_fail 'not the expected LUN0 UFS partition'; return 1; }
    [[ $partition == 17 && $sectors == 2097152 && $readonly == 0 ]] ||
        { bootlog_fail 'partition number/size/read-only guard failed'; return 1; }
    [[ $(bootlog_property "$props" ID_PART_ENTRY_NAME) == ARMADA_BOOT &&
       $(bootlog_property "$props" ID_PART_ENTRY_NUMBER) == 17 &&
       $(bootlog_property "$props" ID_FS_TYPE) == ext4 ]] ||
        { bootlog_fail 'partition label/type guard failed'; return 1; }
    for actual in PARTUUID FSUUID; do
        expected=$(bootlog_property "$identity" "$actual") || return 1
        bootlog_uuid "$expected" || { bootlog_fail 'invalid private identity'; return 1; }
        case "$actual" in
            PARTUUID) actual=$(bootlog_property "$props" ID_PART_ENTRY_UUID) || return 1 ;;
            FSUUID) actual=$(bootlog_property "$props" ID_FS_UUID) || return 1 ;;
        esac
        [[ $actual == "$expected" ]] || { bootlog_fail 'private UUID mismatch'; return 1; }
    done
}

# mount(8)/umount(8) create /run/mount (libmount's utab directory) with the
# caller's umask when it does not exist yet. /run survives switch-root, so a
# 0700 directory made here under our umask 077 breaks every unprivileged
# libmount monitor in the real system (seen on the tablet 2026-11-11: user
# systemd, kded, plasmashell "Failed to acquire watch file descriptor").
# Use the system umask in a subshell and skip utab (-n): nothing persists.
bootlog_mount() {
    local type=$1 device=$2 target=$3
    (umask 022; exec mount -n -t "$type" -o rw,nodev,nosuid,noexec,noatime -- "$device" "$target")
}

bootlog_umount() {
    (umask 022; exec umount -n -- "$1")
}

bootlog_unmounted() {
    awk -v dev="$1" '$3==dev {found=1} END {exit found}' "$2"
}

bootlog_has_mount() {
    awk -v target="$1" '$5==target {found=1} END {exit !found}' "$2"
}

bootlog_mount_matches() {
    local target=$1 device=$2 info=$3 count=0 index
    local -a fields
    while read -r -a fields; do
        [[ ${fields[4]-} == "$target" ]] || continue
        count=$((count+1))
        [[ ${fields[2]-} == "$device" ]] || return 1
        for index in rw nosuid nodev noexec; do
            [[ ,${fields[5]-}, == *,"$index",* ]] || return 1
        done
        for ((index=6; index<${#fields[@]}; index++)); do
            if [[ ${fields[index]} == - ]]; then
                [[ ${fields[index+1]-} == ext4 ]] || return 1
                break
            fi
        done
        ((index < ${#fields[@]})) || return 1
    done < "$info"
    [[ $count == 1 ]]
}

bootlog_private_dir() {
    local path=$1 owner=${2:-0}
    if [[ ! -e $path && ! -L $path ]]; then
        mkdir -m 0700 -- "$path" || return 1
    fi
    [[ -d $path && ! -L $path && $(stat -c '%u:%a' -- "$path") == "$owner:700" ]] ||
        { bootlog_fail 'directory is not private, owned, or is a symlink'; return 1; }
}

bootlog_prepare() {
    local mount=$1 boot=$2 invocation=$3 owner=${4:-0} values available blocksize total directory
    bootlog_uuid "$boot" && [[ $invocation =~ ^[0-9a-f]{32}$ ]] || return 1
    values=$(stat -f -c '%a %S' -- "$mount") || return 1
    read -r available blocksize <<< "$values"
    [[ $available =~ ^[0-9]+$ && $blocksize =~ ^[0-9]+$ ]] || return 1
    # A validated 1 GiB filesystem cannot legitimately overflow this arithmetic.
    ((available <= 2097152 && blocksize >= 512 && blocksize <= 65536)) || return 1
    ((available * blocksize >= 64*1024*1024)) || { bootlog_fail 'less than 64 MiB available'; return 1; }
    bootlog_private_dir "$mount/opd2413-bootlog" "$owner" || return 1
    values=$(du -sb -- "$mount/opd2413-bootlog") || return 1
    read -r total _ <<< "$values"
    [[ $total =~ ^[0-9]+$ ]] || return 1
    ((total <= 128*1024*1024 - 16*1024*1024 - 65536)) ||
        { bootlog_fail '128 MiB total log budget would be exceeded; no automatic deletion'; return 1; }
    directory=$mount/opd2413-bootlog/boot-$boot-$invocation
    [[ ! -e $directory && ! -L $directory ]] || { bootlog_fail 'existing boot evidence'; return 1; }
    mkdir -m 0700 -- "$directory" || return 1
    # Sync the entire new directory chain, not just the eventual file entry.
    sync -f -- "$mount" || return 1
    printf '%s\n' "$directory"
}

bootlog_finish() {
    local mount=$1 device=$2 info=$3 directory=$4 result=$5 code=$6 status=$7 failed=0
    bootlog_has_mount "$mount" "$info" || return 0
    bootlog_mount_matches "$mount" "$device" "$info" ||
        { bootlog_fail 'refusing cleanup of unexpected mount'; return 1; }
    if [[ -n $directory ]]; then
        if [[ $directory != "$mount"/opd2413-bootlog/boot-* || ! -d $directory || -L $directory ||
              ! $result =~ ^[a-z-]+$ || ! $code =~ ^[a-z-]+$ || ! $status =~ ^[A-Za-z0-9_-]+$ ]]; then
            bootlog_fail 'invalid stop metadata/directory' || :
            failed=1
        elif [[ -e $directory/service.result || -L $directory/service.result ]]; then
            bootlog_fail 'refusing overwrite of stop evidence' || :
            failed=1
        else
            (umask 077; set -o noclobber
             printf 'SERVICE_RESULT=%s\nEXIT_CODE=%s\nEXIT_STATUS=%s\n' "$result" "$code" "$status" > "$directory/service.result") || failed=1
            sync -f -- "$directory" || failed=1
        fi
    fi
    # Even a status-file error must not leave our verified mount pinning initrd.
    # Never use forced/lazy unmount. A busy/faulty filesystem is a real failure.
    bootlog_umount "$mount" || return 1
    return "$failed"
}
