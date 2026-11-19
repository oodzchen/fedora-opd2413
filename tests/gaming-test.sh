#!/usr/bin/env bash
# Offline tests for opd2413-gaming (opd-game + opd-power).
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
OPD_GAME="${ROOT}/packaging/opd2413-gaming/src/bin/opd-game"
OPD_POWER="${ROOT}/packaging/opd2413-gaming/src/bin/opd-power"
STEAM_BIN="${ROOT}/packaging/opd2413-gaming/src/bin/steam"

bash -n "${OPD_GAME}"
bash -n "${STEAM_BIN}"
python3 -m py_compile "${OPD_POWER}"

# 1. opd-game presets & flags (--dry-run)
out="$("${OPD_GAME}" --dry-run -- echo hi)"
grep -q '^PRESET=balanced$' <<<"$out"
grep -q '^PROTON_USE_NTSYNC=1$' <<<"$out"
grep -q '^WINE_D3D_CONFIG=renderer=vulkan$' <<<"$out"
grep -q '^FEX_X87REDUCEDPRECISION=1$' <<<"$out"
grep -q '^UCLAMP_MIN=256$' <<<"$out"

out="$("${OPD_GAME}" --dry-run --gamescope --res 1696x1200 --fps 60 --vk-icd /tmp/tu.json --log-perf /tmp/mh_test --wayland fastest -- echo hi)"
grep -q '^PRESET=fastest$' <<<"$out"
grep -q '^FEX_TSOENABLED=0$' <<<"$out"
grep -q '^FEX_PROFILESTATS=0$' <<<"$out"
grep -q '^PROTON_ENABLE_WAYLAND=1$' <<<"$out"
grep -q '^MANGOHUD_CONFIG=output_folder=/tmp/mh_test,' <<<"$out"
grep -q '^UCLAMP_MIN=320$' <<<"$out"
grep -q '^VK_DRIVER_FILES=/tmp/tu.json$' <<<"$out"
grep -q 'gamescope -W 3392 -H 2400 -w 1696 -h 1200 -f -F fsr -r 60 -- ' <<<"$out"

out="$("${OPD_GAME}" --dry-run compat -- echo hi)"
grep -q '^FEX_TSOENABLED=1$' <<<"$out"
grep -q '^FEX_STRICTINPROCESSSPLITLOCKS=1$' <<<"$out"
grep -q '^FEX_X87REDUCEDPRECISION=0$' <<<"$out"

# 2. opd-power against a mock sysfs root
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p \
    "${TMP}/sys/devices/system/cpu/cpufreq/policy0/schedutil" \
    "${TMP}/sys/devices/system/cpu/cpufreq/policy6/schedutil" \
    "${TMP}/sys/devices/system/cpu/cpuidle" \
    "${TMP}/sys/class/devfreq/3d00000.gpu" \
    "${TMP}/sys/class/thermal/thermal_zone0" \
    "${TMP}/sys/class/thermal/thermal_zone1" \
    "${TMP}/sys/class/power_supply/qcom-battmgr-bat" \
    "${TMP}/proc/sys/kernel" \
    "${TMP}/proc/sys/vm" \
    "${TMP}/proc/sys/net/core" \
    "${TMP}/dev"

echo "0 1 2 3 4 5" > "${TMP}/sys/devices/system/cpu/cpufreq/policy0/related_cpus"
echo "schedutil" > "${TMP}/sys/devices/system/cpu/cpufreq/policy0/scaling_governor"
echo "performance schedutil" > "${TMP}/sys/devices/system/cpu/cpufreq/policy0/scaling_available_governors"
echo "384000 1800000 3532800" > "${TMP}/sys/devices/system/cpu/cpufreq/policy0/scaling_available_frequencies"
echo "384000" > "${TMP}/sys/devices/system/cpu/cpufreq/policy0/scaling_min_freq"
echo "3532800" > "${TMP}/sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq"
echo "3532800" > "${TMP}/sys/devices/system/cpu/cpufreq/policy0/cpuinfo_max_freq"
echo "1800000" > "${TMP}/sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq"
echo "45" > "${TMP}/sys/devices/system/cpu/cpufreq/policy0/schedutil/rate_limit_us"

echo "6 7" > "${TMP}/sys/devices/system/cpu/cpufreq/policy6/related_cpus"
echo "performance" > "${TMP}/sys/devices/system/cpu/cpufreq/policy6/scaling_governor"
echo "performance schedutil" > "${TMP}/sys/devices/system/cpu/cpufreq/policy6/scaling_available_governors"
echo "1017600 2880000 3513600 4089600" > "${TMP}/sys/devices/system/cpu/cpufreq/policy6/scaling_available_frequencies"
echo "1017600" > "${TMP}/sys/devices/system/cpu/cpufreq/policy6/scaling_min_freq"
echo "4089600" > "${TMP}/sys/devices/system/cpu/cpufreq/policy6/scaling_max_freq"
echo "4089600" > "${TMP}/sys/devices/system/cpu/cpufreq/policy6/cpuinfo_max_freq"
echo "2880000" > "${TMP}/sys/devices/system/cpu/cpufreq/policy6/scaling_cur_freq"
echo "45" > "${TMP}/sys/devices/system/cpu/cpufreq/policy6/schedutil/rate_limit_us"

echo "teo" > "${TMP}/sys/devices/system/cpu/cpuidle/current_governor"
echo "menu teo" > "${TMP}/sys/devices/system/cpu/cpuidle/available_governors"

echo "simple_ondemand" > "${TMP}/sys/class/devfreq/3d00000.gpu/governor"
echo "50" > "${TMP}/sys/class/devfreq/3d00000.gpu/polling_interval"
echo "160000000 443000000 832000000 1100000000" > "${TMP}/sys/class/devfreq/3d00000.gpu/available_frequencies"
echo "160000000" > "${TMP}/sys/class/devfreq/3d00000.gpu/min_freq"
echo "1100000000" > "${TMP}/sys/class/devfreq/3d00000.gpu/max_freq"
echo "160000000" > "${TMP}/sys/class/devfreq/3d00000.gpu/cur_freq"

echo "cpu-1-0-0-thermal" > "${TMP}/sys/class/thermal/thermal_zone0/type"
echo "45000" > "${TMP}/sys/class/thermal/thermal_zone0/temp"
echo "gpuss0-thermal" > "${TMP}/sys/class/thermal/thermal_zone1/type"
echo "42000" > "${TMP}/sys/class/thermal/thermal_zone1/temp"

echo "Battery" > "${TMP}/sys/class/power_supply/qcom-battmgr-bat/type"
echo "Charging" > "${TMP}/sys/class/power_supply/qcom-battmgr-bat/status"
echo "82" > "${TMP}/sys/class/power_supply/qcom-battmgr-bat/capacity"
echo "4400000" > "${TMP}/sys/class/power_supply/qcom-battmgr-bat/voltage_now"
echo "1000000" > "${TMP}/sys/class/power_supply/qcom-battmgr-bat/current_now"
echo "0" > "${TMP}/sys/class/power_supply/qcom-battmgr-bat/charge_control_start_threshold"
echo "100" > "${TMP}/sys/class/power_supply/qcom-battmgr-bat/charge_control_end_threshold"

echo "64" > "${TMP}/proc/sys/kernel/sched_util_clamp_min_rt_default"
echo "150" > "${TMP}/proc/sys/vm/swappiness"
echo "536870912" > "${TMP}/proc/sys/vm/dirty_bytes"
echo "67108864" > "${TMP}/proc/sys/vm/dirty_background_bytes"
echo "33554432" > "${TMP}/proc/sys/net/core/rmem_max"
touch "${TMP}/dev/ntsync"

# Fanless safety: performance profile must keep policy6 on schedutil (NOT performance)
python3 "${OPD_POWER}" --sysfs-root "${TMP}" profile performance >/dev/null
test "$(cat "${TMP}/sys/devices/system/cpu/cpufreq/policy6/scaling_governor")" = "schedutil"
test "$(cat "${TMP}/sys/class/devfreq/3d00000.gpu/polling_interval")" = "16"
test "$(cat "${TMP}/sys/class/devfreq/3d00000.gpu/min_freq")" = "443000000"
test "$(cat "${TMP}/sys/class/devfreq/3d00000.gpu/max_freq")" = "1100000000"

python3 "${OPD_POWER}" --sysfs-root "${TMP}" profile silent >/dev/null
test "$(cat "${TMP}/sys/devices/system/cpu/cpufreq/policy6/scaling_max_freq")" = "2880000"
test "$(cat "${TMP}/sys/class/devfreq/3d00000.gpu/max_freq")" = "832000000"

python3 "${OPD_POWER}" --sysfs-root "${TMP}" profile sustained >/dev/null
test "$(cat "${TMP}/sys/devices/system/cpu/cpufreq/policy6/scaling_max_freq")" = "3513600"
test "$(cat "${TMP}/sys/class/devfreq/3d00000.gpu/min_freq")" = "443000000"

python3 "${OPD_POWER}" --sysfs-root "${TMP}" profile balanced >/dev/null
test "$(cat "${TMP}/sys/devices/system/cpu/cpufreq/policy6/scaling_max_freq")" = "4089600"
test "$(cat "${TMP}/sys/class/devfreq/3d00000.gpu/min_freq")" = "160000000"
test "$(cat "${TMP}/sys/class/devfreq/3d00000.gpu/max_freq")" = "1100000000"

python3 "${OPD_POWER}" --sysfs-root "${TMP}" gpu-clock 830 >/dev/null
test "$(cat "${TMP}/sys/class/devfreq/3d00000.gpu/min_freq")" = "832000000"
test "$(cat "${TMP}/sys/class/devfreq/3d00000.gpu/max_freq")" = "832000000"

python3 "${OPD_POWER}" --sysfs-root "${TMP}" gpu-clock auto >/dev/null
test "$(cat "${TMP}/sys/class/devfreq/3d00000.gpu/min_freq")" = "160000000"
test "$(cat "${TMP}/sys/class/devfreq/3d00000.gpu/max_freq")" = "1100000000"

python3 "${OPD_POWER}" --sysfs-root "${TMP}" bypass on >/dev/null
test "$(cat "${TMP}/sys/class/power_supply/qcom-battmgr-bat/charge_control_start_threshold")" = "81"
test "$(cat "${TMP}/sys/class/power_supply/qcom-battmgr-bat/charge_control_end_threshold")" = "82"

python3 "${OPD_POWER}" --sysfs-root "${TMP}" bypass on --level 40 >/dev/null
test "$(cat "${TMP}/sys/class/power_supply/qcom-battmgr-bat/charge_control_start_threshold")" = "54"
test "$(cat "${TMP}/sys/class/power_supply/qcom-battmgr-bat/charge_control_end_threshold")" = "55"

python3 "${OPD_POWER}" --sysfs-root "${TMP}" bypass off >/dev/null
test "$(cat "${TMP}/sys/class/power_supply/qcom-battmgr-bat/charge_control_start_threshold")" = "0"
test "$(cat "${TMP}/sys/class/power_supply/qcom-battmgr-bat/charge_control_end_threshold")" = "100"

python3 "${OPD_POWER}" --sysfs-root "${TMP}" status --json | grep -q '"ntsync_present": true'

# Live read-only smoke test on real /sys
python3 "${OPD_POWER}" status >/dev/null

echo "PASS: opd2413-gaming offline tests"
