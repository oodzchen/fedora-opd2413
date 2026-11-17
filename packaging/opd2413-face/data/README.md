# opd2413-face

Native Linux face authentication service and PAM integration for OnePlus Pad 2 Pro (`opd2413`).

## Components

- `opd2413-faced`: Root systemd D-Bus service (`org.opd2413.Face1`) capturing from the front camera via `python3-libcamera` + `DebayerEGL` and running Apache-2.0 OpenCV Zoo YuNet (`face_detection_yunet_2023mar.onnx`) and SFace (`face_recognition_sface_2021dec.onnx`) with multi-frame liveness/sharpness/anti-static-replay checks and lid-closed rejection.
- `pam_opd2413_face.so`: Lightweight C `sd-bus` PAM module with zero camera/Python/ML dependencies in caller processes, automatically bypassed (`PAM_IGNORE`) on remote SSH sessions or unenrolled users.
- `opd-face`: CLI utility (`enroll`, `test`, `status`, `clear`, `list`, `enable`, `disable`).
- `authselect` vendor profile `opd2413-face`: Enables parallel non-blocking lockscreen unlock (`kde-fingerprint` -> `fingerprint-auth`), fast `sudo` face verification, and explicitly-armed `polkit-1` face verification (`system-auth`, gated via `SetPolkitArmed`), while keeping `password-auth` untouched so password entry is never delayed.
- SELinux policy module `opd2413_face`: Permits PAM client domains (`xdm_t`, `policykit_auth_t`, `chkpwd_t`, `local_login_t`, `unconfined_t`) to exchange system D-Bus messages with `unconfined_service_t`.
