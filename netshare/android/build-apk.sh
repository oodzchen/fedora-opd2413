#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_DIR="${ROOT}/netshare/android/app/src/main"
OUT_DIR="${ROOT}/out/netshare"
BUILD_DIR="${OUT_DIR}/build"
KEYSTORE="${OUT_DIR}/opd-netshare.jks"
FINAL_APK="${OUT_DIR}/opd-netshare.apk"

SDK="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-${HOME}/Android/Sdk}}"
if [ ! -d "${SDK}" ]; then
    echo "Android SDK not found at ${SDK}" >&2
    exit 1
fi

BUILD_TOOLS_DIR="$(ls -1d "${SDK}/build-tools/"* | sort -V | tail -n1)"
PLATFORM_JAR="$(ls -1 "${SDK}/platforms/android-"*/android.jar | sort -V | tail -n1)"
AAPT2="${BUILD_TOOLS_DIR}/aapt2"
D8="${BUILD_TOOLS_DIR}/d8"
ZIPALIGN="${BUILD_TOOLS_DIR}/zipalign"
APKSIGNER="${BUILD_TOOLS_DIR}/apksigner"

if [ -n "${JAVA_HOME:-}" ] && [ -x "${JAVA_HOME}/bin/javac" ]; then
    JAVAC="${JAVA_HOME}/bin/javac"
    KEYTOOL="${JAVA_HOME}/bin/keytool"
elif command -v javac >/dev/null 2>&1; then
    JAVAC="$(command -v javac)"
    KEYTOOL="$(command -v keytool)"
    export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "${JAVAC}")")")"
elif [ -x "/usr/lib/jvm/temurin-21-jdk/bin/javac" ]; then
    JAVAC="/usr/lib/jvm/temurin-21-jdk/bin/javac"
    KEYTOOL="/usr/lib/jvm/temurin-21-jdk/bin/keytool"
    export JAVA_HOME="/usr/lib/jvm/temurin-21-jdk"
else
    echo "javac not found; install JDK 17+ or set JAVA_HOME" >&2
    exit 1
fi

rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"/{gen,classes,dex} "${OUT_DIR}"

"${AAPT2}" compile --dir "${APP_DIR}/res" -o "${BUILD_DIR}/res.zip"

"${AAPT2}" link \
    -o "${BUILD_DIR}/unaligned.apk" \
    -I "${PLATFORM_JAR}" \
    --manifest "${APP_DIR}/AndroidManifest.xml" \
    --java "${BUILD_DIR}/gen" \
    -A "${APP_DIR}/assets" \
    --auto-add-overlay \
    "${BUILD_DIR}/res.zip"

mapfile -t JAVA_SRCS < <(find "${APP_DIR}/java" "${BUILD_DIR}/gen" -name '*.java' | sort)
"${JAVAC}" --release 17 -encoding UTF-8 -classpath "${PLATFORM_JAR}" -d "${BUILD_DIR}/classes" "${JAVA_SRCS[@]}"

mapfile -t CLASS_FILES < <(find "${BUILD_DIR}/classes" -name '*.class' | sort)
"${D8}" --min-api 33 --lib "${PLATFORM_JAR}" --output "${BUILD_DIR}/dex" "${CLASS_FILES[@]}"

python3 - "${BUILD_DIR}/unaligned.apk" "${BUILD_DIR}/dex/classes.dex" <<'EOF'
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1], "a") as zf:
    zf.write(sys.argv[2], "classes.dex", compress_type=zipfile.ZIP_DEFLATED)
EOF

"${ZIPALIGN}" -p -f 4 "${BUILD_DIR}/unaligned.apk" "${BUILD_DIR}/aligned.apk"

if [ ! -f "${KEYSTORE}" ]; then
    "${KEYTOOL}" -genkeypair -noprompt \
        -keystore "${KEYSTORE}" \
        -alias opdnetshare \
        -keyalg RSA -keysize 2048 -validity 10000 \
        -storepass opdnetshare -keypass opdnetshare \
        -dname "CN=OPD NetShare,O=Local,C=CN"
fi

"${APKSIGNER}" sign \
    --ks "${KEYSTORE}" \
    --ks-key-alias opdnetshare \
    --ks-pass pass:opdnetshare \
    --key-pass pass:opdnetshare \
    --out "${FINAL_APK}" \
    "${BUILD_DIR}/aligned.apk"

rm -f "${FINAL_APK}.idsig"
"${APKSIGNER}" verify --verbose "${FINAL_APK}"
ls -lh "${FINAL_APK}"
