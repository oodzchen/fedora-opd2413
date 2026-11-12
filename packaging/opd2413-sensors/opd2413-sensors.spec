# Built by tools/build-sensors-rpm.sh inside an aarch64 Fedora container:
#   rpmbuild --define 'pkgver X' --define 'pkgrel N' --define 'stagedir /build/stage'
#            --define 'srcdir /repo/packaging/opd2413-sensors' --define 'romdir /erhai/packaging/sensors'
# stagedir holds the meson installs (prefix /usr/libexec/opd2413-sensors) of the
# pinned and patched hexagonrpc, libssc and iio-sensor-proxy (sources.json).
%global prefixdir /usr/libexec/opd2413-sensors
%global rpcdroot /usr/share/opd2413-sensors/hexagonrpcd
%global statedir /var/lib/opd2413/sensors
%global debug_package %{nil}
%global __provides_exclude_from ^%{prefixdir}/.*$
%global __requires_exclude ^lib(hexagonrpc|ssc)\\.so.*$

Name:           opd2413-sensors
Version:        %{pkgver}
Release:        %{pkgrel}
Summary:        OnePlus Pad 2 Pro rotation, light, compass and gyroscope sensors
License:        GPL-3.0-or-later AND GPL-2.0-only
ExclusiveArch:  aarch64
Requires:       iio-sensor-proxy
Requires:       systemd
Requires:       systemd-udev
Requires:       python3
Requires:       glib2
Requires:       libgudev
Requires:       polkit-libs
Requires:       protobuf-c
Requires:       libqmi

%description
Connects the Qualcomm Sensor Core on the ADSP to the desktop, following the
erhai-sensors package of the onepluspad-2pro-mainline project: a private
hexagonrpcd file server attaches the ADSP sensor domain and serves it the
stock sensor configuration, libssc reads the sensors over QRTR, and a private
iio-sensor-proxy build with SSC support replaces Fedora's binary through a
systemd drop-in. Fedora's iio-sensor-proxy files are left unchanged.

The per-unit sensor registry is not included. Import it once with
opd2413-sensors-import-registry from a copy of this tablet's Android persist
data (/mnt/vendor/persist/sensors), then reboot; until then the stack stays
inactive.

%prep

%build

%install
P=%{stagedir}/%{prefixdir}
install -D -m 0755 $P/bin/hexagonrpcd %{buildroot}%{prefixdir}/bin/hexagonrpcd
install -D -m 0755 $P/bin/ssccli %{buildroot}%{prefixdir}/bin/ssccli
install -D -m 0755 $P/libexec/iio-sensor-proxy %{buildroot}%{prefixdir}/libexec/iio-sensor-proxy
mkdir -p %{buildroot}%{prefixdir}/lib
for f in $P/lib/libhexagonrpc.so.* $P/lib/libssc.so.*; do
    cp -a "$f" %{buildroot}%{prefixdir}/lib/
done
install -D -m 0755 %{srcdir}/files/sleep-streams %{buildroot}%{prefixdir}/scripts/sleep-streams
install -D -m 0755 %{srcdir}/files/ssc-sample-gate %{buildroot}%{prefixdir}/scripts/ssc-sample-gate
install -D -m 0755 %{srcdir}/files/opd2413-sensors-import-registry %{buildroot}%{_sbindir}/opd2413-sensors-import-registry
install -D -m 0755 %{srcdir}/files/opd2413-sensors-ssc-delivery %{buildroot}%{_sbindir}/opd2413-sensors-ssc-delivery
for u in opd2413-sensors-rpcd opd2413-sensors-gate opd2413-sensors-sleep; do
    install -D -m 0644 %{srcdir}/files/$u.service %{buildroot}%{_unitdir}/$u.service
done
install -D -m 0644 %{srcdir}/files/80-opd2413-ssc.conf %{buildroot}%{_unitdir}/iio-sensor-proxy.service.d/80-opd2413-ssc.conf
install -D -m 0644 %{srcdir}/files/81-opd2413-sensors.rules %{buildroot}%{_udevrulesdir}/81-opd2413-sensors.rules
install -D -m 0644 %{srcdir}/files/sysusers-opd2413-sensors.conf %{buildroot}%{_sysusersdir}/opd2413-sensors.conf
install -D -m 0644 %{srcdir}/files/tmpfiles-opd2413-sensors.conf %{buildroot}%{_tmpfilesdir}/opd2413-sensors.conf
# Stock sensor configuration (rom-config.json, checked by the build script).
python3 - %{srcdir}/rom-config.json %{romdir} %{buildroot}%{rpcdroot} <<'EOF'
import json, os, shutil, sys
rom, src, dst = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
for e in rom['files']:
    t = os.path.join(dst, e['install'])
    os.makedirs(os.path.dirname(t), exist_ok=True)
    shutil.copyfile(os.path.join(src, e['file']), t)
    os.chmod(t, 0o644)
EOF
# Machine data stays in /var/lib; the served tree only points at it.
ln -s %{statedir}/persist/registry %{buildroot}%{rpcdroot}/sensors/registry
ln -s %{statedir}/persist/sns_reg_version %{buildroot}%{rpcdroot}/sensors/sns_reg_version
ln -s %{statedir}/socinfo %{buildroot}%{rpcdroot}/socinfo

%post
systemd-sysusers opd2413-sensors.conf >/dev/null 2>&1 || :
systemd-tmpfiles --create opd2413-sensors.conf >/dev/null 2>&1 || :
if [ $1 -eq 1 ]; then
    systemctl enable --quiet opd2413-sensors-sleep.service >/dev/null 2>&1 || :
fi
udevadm control --reload >/dev/null 2>&1 || :
if [ ! -d %{statedir}/persist/registry ]; then
    echo "opd2413-sensors: no sensor registry imported yet; run opd2413-sensors-import-registry, then reboot" >&2
fi

%preun
if [ $1 -eq 0 ]; then
    systemctl disable --quiet opd2413-sensors-sleep.service >/dev/null 2>&1 || :
fi

%files
%{prefixdir}
%{_sbindir}/opd2413-sensors-import-registry
%{_sbindir}/opd2413-sensors-ssc-delivery
%{_unitdir}/opd2413-sensors-rpcd.service
%{_unitdir}/opd2413-sensors-gate.service
%{_unitdir}/opd2413-sensors-sleep.service
%dir %{_unitdir}/iio-sensor-proxy.service.d
%{_unitdir}/iio-sensor-proxy.service.d/80-opd2413-ssc.conf
%{_udevrulesdir}/81-opd2413-sensors.rules
%{_sysusersdir}/opd2413-sensors.conf
%{_tmpfilesdir}/opd2413-sensors.conf
%{rpcdroot}
