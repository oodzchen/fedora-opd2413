Name:           opd2413-camera
Version:        %{?pkgver}%{!?pkgver:0.1}
Release:        %{?pkgrel}%{!?pkgrel:3}%{?dist}
Summary:        Native ZSL multi-frame RAW10 HDR+ camera application for OPD2413
License:        GPL-2.0-or-later

ExclusiveArch:  aarch64

BuildRequires:  python3-devel
BuildRequires:  python3-numpy
BuildRequires:  python3-opencv
BuildRequires:  python3-pillow
BuildRequires:  desktop-file-utils
BuildRequires:  /usr/bin/ffmpeg

Requires:       libcamera >= 0.7.2-5.fc45.opd2413.3
Requires:       libcamera-ipa >= 0.7.2-5.fc45.opd2413.3
Requires:       python3-libcamera
Requires:       python3-numpy
Requires:       python3-opencv
Requires:       python3-pillow
Requires:       python3-pyside6
Requires:       /usr/bin/ffmpeg

%description
Zero-shutter-lag dual-stream camera application and CLI for OnePlus Pad 2 Pro
(OPD2413 / sc820cs front 8MP & sc1300cs rear 13MP). Pairs live Adreno 830
GPU-ISP viewfinder preview with multi-frame RAW10 burst alignment, robust
temporal noise-variance merge, 5x5 Malvar-He-Cutler demosaic, neutral highlight
reconstruction, calibrated LSC/AWB/CCM, multi-scale Mertens exposure fusion,
YCrCb bilateral denoising, and CAS sharpening.

%prep
rm -rf %{name}-%{version}
mkdir -p %{name}-%{version}
cp -a %{srcdir}/* %{name}-%{version}/

%build
cd %{name}-%{version}
python3 -m py_compile src/hdrplus_isp.py src/video_recorder.py src/opd-camera-cli.py src/opd-camera-gui.py

%install
cd %{name}-%{version}

install -d %{buildroot}%{_libexecdir}/opd2413
install -m 0644 src/hdrplus_isp.py %{buildroot}%{_libexecdir}/opd2413/hdrplus_isp.py
install -m 0644 src/video_recorder.py %{buildroot}%{_libexecdir}/opd2413/video_recorder.py
install -m 0755 src/opd-camera-cli.py %{buildroot}%{_libexecdir}/opd2413/opd-camera-cli.py
install -m 0755 src/opd-camera-gui.py %{buildroot}%{_libexecdir}/opd2413/opd-camera-gui.py

install -d %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/opd-camera <<'EOF'
#!/bin/sh
exec python3 -B /usr/libexec/opd2413/opd-camera-gui.py "$@"
EOF
chmod 0755 %{buildroot}%{_bindir}/opd-camera

cat > %{buildroot}%{_bindir}/opd-camera-cli <<'EOF'
#!/bin/sh
exec python3 -B /usr/libexec/opd2413/opd-camera-cli.py "$@"
EOF
chmod 0755 %{buildroot}%{_bindir}/opd-camera-cli

install -d %{buildroot}%{_datadir}/applications
install -m 0644 data/opd-camera.desktop %{buildroot}%{_datadir}/applications/opd-camera.desktop

%check
cd %{name}-%{version}
desktop-file-validate %{buildroot}%{_datadir}/applications/opd-camera.desktop
python3 -B tests/test_hdrplus_isp.py
python3 -B tests/test_video_recorder.py

%files
%{_libexecdir}/opd2413/hdrplus_isp.py
%{_libexecdir}/opd2413/video_recorder.py
%{_libexecdir}/opd2413/opd-camera-cli.py
%{_libexecdir}/opd2413/opd-camera-gui.py
%{_bindir}/opd-camera
%{_bindir}/opd-camera-cli
%{_datadir}/applications/opd-camera.desktop

%changelog
* Sat Nov 21 2026 OPD2413 Contributors - 0.1-3
- Add native MP4 video recording with audio to opd-camera GUI
- Keep front-camera Selfie Mirror orientation consistent across preview, photos, and videos

* Mon Nov 16 2026 OPD2413 Contributors - 0.1-2
- Support rear sc1300cs Contrast AF convergence and manual lens diopter control
- Add EV compensation, GUI Refocus/EV controls, and AF-aware ZSL burst filtering
- Upgrade brightness/tone mapping and shadow/skin-protected vibrance calibration

* Sun Nov 15 2026 OPD2413 Contributors - 0.1-1
- Initial ZSL dual-stream multi-frame RAW10 HDR+ camera GUI and CLI package
