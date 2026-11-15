Name:    opd2413-face
Version: %{pkgver}
Release: %{pkgrel}%{?dist}
Summary: Native Linux face authentication service and PAM module for OPD2413
License: LGPL-2.1-or-later AND Apache-2.0
BuildRequires: gcc make cmake ninja-build pkgconf-pkg-config pam-devel systemd-devel qt6-qtbase-devel qt6-qtdeclarative-devel selinux-policy-devel checkpolicy policycoreutils python3 authselect
Requires: python3-libcamera python3-opencv python3-numpy python3-gobject-base python3-pyside6 libcamera libcamera-ipa authselect
Requires(post): systemd policycoreutils dbus-common
Requires(preun): systemd
Requires(postun): systemd policycoreutils

%description
Native Linux face recognition authentication daemon (org.opd2413.Face1),
lightweight C sd-bus PAM module, CLI management tool, Qt GUI enrollment wizard,
authselect vendor profile, and SELinux policy module for OnePlus Pad 2 Pro (OPD2413).

%prep
rm -rf opd2413-face-build && mkdir -p opd2413-face-build
cp -a %{srcdir}/* opd2413-face-build/

%build
cd opd2413-face-build
make -C src CFLAGS="%{optflags}" LDFLAGS="%{?build_ldflags}"
make -C data/selinux -f /usr/share/selinux/devel/Makefile opd2413_face.pp
cmake -S src/qml -B src/qml/build -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=%{_prefix} \
    -DQML_INSTALL_DIR=%{_lib}/qt6/qml
cmake --build src/qml/build

%install
cd opd2413-face-build
DESTDIR=%{buildroot} cmake --install src/qml/build

install -d %{buildroot}%{_libexecdir}/opd2413
install -m 0755 src/opd2413-faced.py %{buildroot}%{_libexecdir}/opd2413/opd2413-faced
install -m 0755 src/opd-face-enroll-gui.py %{buildroot}%{_libexecdir}/opd2413/opd-face-enroll

install -d %{buildroot}%{_bindir}
install -m 0755 src/opd-face.py %{buildroot}%{_bindir}/opd-face
cat > %{buildroot}%{_bindir}/opd-face-enroll <<'EOF'
#!/bin/sh
exec /usr/bin/python3 -B %{_libexecdir}/opd2413/opd-face-enroll "$@"
EOF
chmod 0755 %{buildroot}%{_bindir}/opd-face-enroll

install -d %{buildroot}%{_datadir}/applications
install -m 0644 data/opd-face-enroll.desktop %{buildroot}%{_datadir}/applications/opd-face-enroll.desktop

install -d %{buildroot}/%{_lib}/security
install -m 0755 src/pam_opd2413_face.so %{buildroot}/%{_lib}/security/pam_opd2413_face.so

install -d %{buildroot}%{_sysconfdir}
install -m 0644 data/opd2413-face.conf %{buildroot}%{_sysconfdir}/opd2413-face.conf

install -d %{buildroot}%{_datadir}/dbus-1/system.d
install -m 0644 data/org.opd2413.Face1.conf %{buildroot}%{_datadir}/dbus-1/system.d/org.opd2413.Face1.conf

install -d %{buildroot}%{_datadir}/dbus-1/system-services
install -m 0644 data/org.opd2413.Face1.service %{buildroot}%{_datadir}/dbus-1/system-services/org.opd2413.Face1.service

install -d %{buildroot}%{_unitdir}
install -m 0644 data/opd2413-face.service %{buildroot}%{_unitdir}/opd2413-face.service

install -d %{buildroot}%{_datadir}/opd2413-face/models
install -m 0644 %{modeldir}/face_detection_yunet_2023mar.onnx %{buildroot}%{_datadir}/opd2413-face/models/
install -m 0644 %{modeldir}/face_recognition_sface_2021dec.onnx %{buildroot}%{_datadir}/opd2413-face/models/
install -d %{buildroot}%{_datadir}/opd2413-face/lockscreen
install -m 0644 data/lockscreen/* %{buildroot}%{_datadir}/opd2413-face/lockscreen/

install -d %{buildroot}%{_datadir}/selinux/packages
install -m 0644 data/selinux/opd2413_face.pp %{buildroot}%{_datadir}/selinux/packages/opd2413_face.pp

install -d -m 0700 %{buildroot}%{_sharedstatedir}/opd2413-face
install -d %{buildroot}%{_docdir}/%{name}
install -m 0644 data/README.md %{buildroot}%{_docdir}/%{name}/README.md

# Derive authselect vendor profile cleanly from Fedora's local profile templates
prof=%{buildroot}%{_datadir}/authselect/vendor/opd2413-face
install -d "$prof"
cp -a /usr/share/authselect/default/local/* "$prof/"
python3 - "$prof" <<'EOF'
import pathlib, sys
p = pathlib.Path(sys.argv[1])

sa = (p / "system-auth").read_text(encoding="utf-8")
needle = "auth        sufficient                                   pam_fprintd.so"
ins = "auth        [success=done ignore=ignore default=ignore]  pam_opd2413_face.so timeout=3500\n"
assert needle in sa, "system-auth missing pam_fprintd anchor"
(p / "system-auth").write_text(sa.replace(needle, ins + needle, 1), encoding="utf-8")

fp = (p / "fingerprint-auth").read_text(encoding="utf-8")
fp_old = (
    'auth required pam_debug.so auth=authinfo_unavail {exclude if "with-fingerprint"}\n'
    '{continue if "with-fingerprint"}\n'
    "auth        required                                     pam_env.so"
)
fp_new = (
    "auth        required                                     pam_env.so\n"
    "auth        [success=done ignore=ignore default=die]     pam_opd2413_face.so timeout=4500 quiet\n"
    'auth        required                                     pam_debug.so auth=authinfo_unavail                      {exclude if "with-fingerprint"}\n'
    '{continue if "with-fingerprint"}'
)
assert fp_old in fp, "fingerprint-auth missing pam_debug anchor"
(p / "fingerprint-auth").write_text(fp.replace(fp_old, fp_new, 1), encoding="utf-8")

(p / "README").write_text(
"""OPD2413 Local users + Native Face Authentication
=================================================

Derived from 'local', adding pam_opd2413_face.so to system-auth
(for sudo/polkit) and fingerprint-auth (for Plasma kde-fingerprint
non-interactive lockscreen authentication, gated by lockscreen UI).
""", encoding="utf-8")
EOF

%post
%systemd_post opd2413-face.service
if selinuxenabled 2>/dev/null; then
    semodule -n -i %{_datadir}/selinux/packages/opd2413_face.pp >/dev/null 2>&1 || true
    /usr/sbin/load_policy >/dev/null 2>&1 || true
else
    semodule -n -i %{_datadir}/selinux/packages/opd2413_face.pp >/dev/null 2>&1 || true
fi
systemctl daemon-reload >/dev/null 2>&1 || true
systemctl enable opd2413-face.service >/dev/null 2>&1 || true

%posttrans
if command -v authselect >/dev/null 2>&1 && authselect current --raw 2>/dev/null | grep -q '^opd2413-face'; then
    %{_bindir}/opd-face enable >/dev/null 2>&1 || true
fi

%triggerin -- plasma-desktop
if command -v authselect >/dev/null 2>&1 && authselect current --raw 2>/dev/null | grep -q '^opd2413-face'; then
    %{_bindir}/opd-face enable >/dev/null 2>&1 || true
fi

%preun
if [ "$1" -eq 0 ]; then
    %{_bindir}/opd-face disable >/dev/null 2>&1 || true
fi
%systemd_preun opd2413-face.service

%postun
%systemd_postun_with_restart opd2413-face.service
if [ "$1" -eq 0 ]; then
    semodule -n -r opd2413_face >/dev/null 2>&1 || true
    selinuxenabled 2>/dev/null && /usr/sbin/load_policy >/dev/null 2>&1 || true
fi

%files
%{_libexecdir}/opd2413/opd2413-faced
%{_libexecdir}/opd2413/opd-face-enroll
%{_bindir}/opd-face
%{_bindir}/opd-face-enroll
%{_datadir}/applications/opd-face-enroll.desktop
/%{_lib}/security/pam_opd2413_face.so
%{_libdir}/qt6/qml/org/opd2413/
%config(noreplace) %{_sysconfdir}/opd2413-face.conf
%{_datadir}/dbus-1/system.d/org.opd2413.Face1.conf
%{_datadir}/dbus-1/system-services/org.opd2413.Face1.service
%{_unitdir}/opd2413-face.service
%{_datadir}/opd2413-face/
%{_datadir}/selinux/packages/opd2413_face.pp
%{_datadir}/authselect/vendor/opd2413-face/
%attr(0700,root,root) %dir %{_sharedstatedir}/opd2413-face
%doc %{_docdir}/%{name}/README.md
