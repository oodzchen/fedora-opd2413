# opd2413-sensors

Sensors of the ADSP's Qualcomm Sensor Core (accelerometer for auto-rotation, ambient
light, magnetometer/compass, gyroscope) for Fedora, following the `erhai-sensors`
package of [onepluspad-2pro-mainline](https://github.com/yzddmr6/onepluspad-2pro-mainline)
(commit `4cc3570`, v0.7.2), whose `docs/SENSORS.md` explains the stack.

| Here | From erhai | Changes |
|---|---|---|
| `sources.json` | `packaging/sensors/sources.json` | none: the pinned archives (hexagonrpc `598b591`, libssc 0.4.4, iio-sensor-proxy 3.9), SHA-256 and patch origins |
| `patches/` | `packaging/sensors/patches/` | none (23 patches; authors and origins in the patch headers and `sources.json`) |
| `rom-config.json` | `packaging/sensors/rom-config.json` | none: the 157 stock sensor configuration files and their SHA-256 |
| `files/` | `packaging/erhai-sensors/tree/` (units, udev rule, sysusers/tmpfiles, scripts; GPL-2.0-only) | names and paths only: `erhai` → `opd2413`, private prefix `/usr/libexec/opd2413-sensors`, state `/var/lib/opd2413/sensors` |
| `opd2413-sensors.spec` | `tools/build-sensors.py` (staging) | Fedora RPM instead of a .deb |

The stock configuration files are vendor files; they are read from an erhai checkout at
build time (verified against `rom-config.json`) and never copied into this repository.
The per-unit registry (Android `/mnt/vendor/persist/sensors`) is machine data: it is
imported on the tablet with `opd2413-sensors-import-registry` and kept under `private/`
on the host.

Build: `tools/build-sensors-rpm.sh VERSION RELEASE ~/github/onepluspad-2pro-mainline`
(aarch64 Fedora 45 container; the meson builds run their unit tests).
