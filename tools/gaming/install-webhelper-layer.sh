#!/usr/bin/env bash
# Compile and install the user-space Vulkan implicit layer that retries
# vkAcquireNextImage*KHR VK_TIMEOUT for steamwebhelper after s2idle resume.
# Installed into a Steam-scoped layer dir (~/.local/share/opd2413-steam-layer)
# so steam-arm64 loads it via VK_ADD_IMPLICIT_LAYER_PATH without affecting
# x86_64 FEX games or other Vulkan apps.
# Source adapted from Zaviya (GPL-2.0): external-and-mods/webhelper-acquire-layer.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SRC="${HERE}/webhelper_acquire_layer.c"
LIB_DIR="${HOME}/.local/lib/opd2413"
LAYER_DIR="${HOME}/.local/share/opd2413-steam-layer"
SO="${LIB_DIR}/libVkLayer_webhelper_acquire.so"
JSON="${LAYER_DIR}/VkLayer_webhelper_acquire.json"

[[ -f "${SRC}" ]] || { echo "missing ${SRC}" >&2; exit 1; }
command -v gcc >/dev/null || { echo "gcc not found" >&2; exit 1; }
[[ -f /usr/include/vulkan/vulkan.h ]] || { echo "vulkan-headers missing (/usr/include/vulkan/vulkan.h)" >&2; exit 1; }

# Remove legacy global user implicit layer if present
rm -f "${HOME}/.local/share/vulkan/implicit_layer.d/VkLayer_webhelper_acquire.json"

mkdir -p "${LIB_DIR}" "${LAYER_DIR}"
gcc -std=gnu11 -O2 -Wall -Wextra -shared -fPIC -fvisibility=hidden \
    "${SRC}" -o "${SO}"
chmod 0755 "${SO}"

cat >"${JSON}" <<EOF
{
  "file_format_version": "1.0.0",
  "layer": {
    "name": "VK_LAYER_webhelper_acquire",
    "type": "GLOBAL",
    "library_path": "${SO}",
    "api_version": "1.4.350",
    "implementation_version": "1",
    "description": "Retries vkAcquireNextImageKHR timeouts for Steam webhelper after s2idle resume",
    "functions": {
      "vkNegotiateLoaderLayerInterfaceVersion": "vkNegotiateLoaderLayerInterfaceVersion"
    },
    "disable_environment": {
      "DISABLE_WEBHELPER_ACQUIRE_RETRY": "1"
    }
  }
}
EOF
chmod 0644 "${JSON}"

echo "Installed ${SO} and ${JSON}"
