#!/usr/bin/env bash
# Build Qualcomm msm_dpu / Adreno 830 patched MangoHud (v0.8.4 from ../Zaviya)
# inside a clean Fedora 45 aarch64 podman container and install into user-space
# (~/.local/lib/opd2413-mangohud + ~/.local/share/vulkan/implicit_layer.d/).
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC_DIR="${1:-${ROOT}/../Zaviya/external-and-mods/MangoHud}"
OUT_DIR="${ROOT}/out/mangohud-adreno"
IMG="localhost/opd2413-builder-mangohud:fc45-v2"
JOBS="$(nproc --ignore=1)"

if [[ ! -f "${SRC_DIR}/meson.build" ]]; then
    echo "build-mangohud-adreno: MangoHud source not found at ${SRC_DIR}" >&2
    exit 1
fi

mkdir -p "${OUT_DIR}"

if ! podman image exists "${IMG}"; then
    echo "==> Building cached Fedora 45 MangoHud builder image (${IMG})..."
    TMP_DF="$(mktemp -d)"
    trap 'rm -rf "$TMP_DF"' EXIT
    if podman image exists "localhost/opd2413-builder-mangohud:fc45"; then
        cat > "${TMP_DF}/Containerfile" <<'EOF'
FROM localhost/opd2413-builder-mangohud:fc45
RUN dnf --disablerepo='*' --enablerepo=fedora --enablerepo=updates install -y \
        libstdc++-static \
    && dnf clean all
EOF
    else
        cat > "${TMP_DF}/Containerfile" <<'EOF'
FROM registry.fedoraproject.org/fedora:45
RUN dnf --disablerepo='*' --enablerepo=fedora --enablerepo=updates install -y \
        gcc gcc-c++ libstdc++-static meson ninja-build pkgconf-pkg-config git cmake \
        python3 python3-mako glslang \
        wayland-devel wayland-protocols-devel libxkbcommon-devel \
        libX11-devel dbus-devel libdrm-devel \
        vulkan-headers vulkan-loader-devel \
        mesa-libGL-devel mesa-libEGL-devel \
        nlohmann-json-devel \
    && dnf clean all
EOF
    fi
    podman build -t "${IMG}" "${TMP_DF}"
    rm -rf "${TMP_DF}"
    trap - EXIT
fi

echo "==> Pre-caching meson wrap archives from GitHub (avoiding wrapdb.mesonbuild.com stalls)..."
PCACHE="${OUT_DIR}/packagecache"
mkdir -p "${PCACHE}"
fetch_wrap() {
    local fname="$1" url="$2" sha="$3"
    local dst="${PCACHE}/${fname}"
    if [[ -f "${dst}" ]] && echo "${sha}  ${dst}" | sha256sum -c - >/dev/null 2>&1; then
        return 0
    fi
    echo "  fetching ${fname}..."
    curl -fsSL --retry 3 --connect-timeout 15 --max-time 60 -o "${dst}.part" "${url}"
    echo "${sha}  ${dst}.part" | sha256sum -c - >/dev/null
    mv -f "${dst}.part" "${dst}"
}

fetch_wrap "vulkan-headers-1.4.346.tar.gz" \
    "https://github.com/KhronosGroup/Vulkan-Headers/archive/v1.4.346.tar.gz" \
    "5bb77f5d7b460e255a9e51affc00d64354986b55cf577d8eab28529cad01fc80"
fetch_wrap "vulkan-utility-libraries-1.4.346.tar.gz" \
    "https://github.com/KhronosGroup/Vulkan-Utility-Libraries/archive/v1.4.346.tar.gz" \
    "372eb525103ecb4e3a04d030b2a9778ebc67853bbdc82ce6747de3757d432ad9"
fetch_wrap "imgui-1.91.6.tar.gz" \
    "https://github.com/ocornut/imgui/archive/refs/tags/v1.91.6.tar.gz" \
    "c5fbc5dcab1d46064001c3b84d7a88812985cde7e0e9ced03f5677bec1ba502a"
fetch_wrap "implot-0.16.zip" \
    "https://github.com/epezent/implot/archive/refs/tags/v0.16.zip" \
    "24f772c688f6b8a6e19d7efc10e4923a04a915f13d487b08b83553aa62ae1708"
fetch_wrap "implot_0.16-1_patch.zip" \
    "https://github.com/mesonbuild/wrapdb/releases/download/implot_0.16-1/implot_0.16-1_patch.zip" \
    "1c6b1462066a5452fa50c1da1dd47fed841f28232972c82d778f2962936568c7"
fetch_wrap "spdlog-1.14.1.tar.gz" \
    "https://github.com/gabime/spdlog/archive/refs/tags/v1.14.1.tar.gz" \
    "1586508029a7d0670dfcb2d97575dcdc242d3868a259742b69f100801ab4e16b"
fetch_wrap "spdlog_1.14.1-1_patch.zip" \
    "https://github.com/mesonbuild/wrapdb/releases/download/spdlog_1.14.1-1/spdlog_1.14.1-1_patch.zip" \
    "ae878e732330ea1048f90d7e117c40c0cd2a6fb8ae5492c7955818ce3aaade6c"

echo "==> Compiling MangoHud v0.8.4 (Qualcomm msm_dpu / Adreno 830) with -j${JOBS}..."
# Copy source to writable build workspace inside out/ so ../Zaviya stays clean
rm -rf "${OUT_DIR}/src" "${OUT_DIR}/build" "${OUT_DIR}/stage"
cp -a "${SRC_DIR}" "${OUT_DIR}/src"
mkdir -p "${OUT_DIR}/src/subprojects/packagecache" "${OUT_DIR}/build" "${OUT_DIR}/stage"
cp -a "${PCACHE}/." "${OUT_DIR}/src/subprojects/packagecache/"

podman run --rm \
    --security-opt label=disable \
    -v "${OUT_DIR}:/work:rw" \
    -w /work/src \
    "${IMG}" \
    bash -c "set -euo pipefail
        meson setup /work/build \
            --wrap-mode=nodownload \
            --prefix=/usr \
            --libdir=lib64 \
            --buildtype=release \
            -Duse_system_spdlog=disabled \
            -Dappend_libdir_mangohud=false \
            -Dwith_nvml=disabled \
            -Dwith_xnvctrl=disabled \
            -Dwith_x11=enabled \
            -Dwith_wayland=enabled \
            -Dwith_dbus=enabled \
            -Dwith_server=false \
            -Dwith_mangohud_next=false \
            -Dmangoplot=disabled \
            -Dinclude_doc=false \
            -Dtests=disabled
        ninja -C /work/build -j${JOBS}
        DESTDIR=/work/stage ninja -C /work/build install"

echo "==> Installing user-space Adreno MangoHud into ~/.local..."
LIB_DST="${HOME}/.local/lib/opd2413-mangohud"
LAYER_DST="${HOME}/.local/share/vulkan/implicit_layer.d"
BIN_DST="${HOME}/.local/bin"
mkdir -p "${LIB_DST}" "${LAYER_DST}" "${BIN_DST}"

for f in libMangoHud.so libMangoHud_shim.so libMangoHud_opengl.so; do
    if [[ -f "${OUT_DIR}/stage/usr/lib64/${f}" ]]; then
        install -m 0755 "${OUT_DIR}/stage/usr/lib64/${f}" "${LIB_DST}/${f}"
    fi
done

cat > "${LAYER_DST}/MangoHud.aarch64.json" <<EOF
{
    "file_format_version" : "1.0.0",
    "layer" : {
      "name": "VK_LAYER_MANGOHUD_overlay_aarch64",
      "type": "GLOBAL",
      "api_version": "1.4.350",
      "library_path": "${LIB_DST}/libMangoHud.so",
      "implementation_version": "1",
      "description": "Vulkan Hud Overlay (OPD2413 Adreno msm_dpu)",
      "functions": {
         "vkGetInstanceProcAddr": "overlay_GetInstanceProcAddr",
         "vkGetDeviceProcAddr": "overlay_GetDeviceProcAddr"
      },
      "enable_environment": {
        "MANGOHUD": "1"
      },
      "disable_environment": {
        "DISABLE_MANGOHUD": "1"
      }
    }
}
EOF
chmod 0644 "${LAYER_DST}/MangoHud.aarch64.json"

# User-space mangohud wrapper pointing LD_PRELOAD to our shim too (for OpenGL)
cat > "${BIN_DST}/mangohud" <<EOF
#!/usr/bin/env bash
set -euo pipefail
if [[ "\${1:-}" == "--version" ]]; then
    echo "v0.8.4-opd2413-adreno"
    exit 0
fi
if [[ "\${1:-}" == "--dlsym" ]]; then
    shift
fi
SHIM="${LIB_DST}/libMangoHud_shim.so"
if [[ -f "\${SHIM}" ]]; then
    case ":\${LD_PRELOAD-}:" in
        *:"\${SHIM}":*) ;;
        *) LD_PRELOAD="\${LD_PRELOAD:+\${LD_PRELOAD}:}\${SHIM}" ;;
    esac
    export LD_PRELOAD
fi
exec env MANGOHUD=1 "\$@"
EOF
chmod 0755 "${BIN_DST}/mangohud"

echo "==> Verifying host ldd resolution:"
ldd "${LIB_DST}/libMangoHud.so" | grep "not found" && exit 1 || echo "  libMangoHud.so: all host deps OK"
echo "==> Done! Installed to ${LIB_DST}"
