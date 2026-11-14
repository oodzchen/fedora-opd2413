%global debug_package %{nil}

Name:           opd2413-netshare
Version:        %{pkgver}
Release:        %{pkgrel}
Summary:        OPD2413 cross-device automatic mobile network sharing
License:        GPL-2.0-only
BuildArch:      noarch

Requires:       python3
Requires:       python3-gobject-base
Requires:       python3-pyside6
Requires:       bluez
Requires:       dnsmasq
Requires:       wpa_supplicant
Requires:       iw
Requires:       iproute
Requires:       procps-ng
Requires:       firewalld
Requires:       systemd
Requires:       NetworkManager

%description
Replicates ColorOS-style cross-device network sharing on the OnePlus Pad 2 Pro
(OPD2413) running Fedora KDE. Uses BlueZ LE advertisement and RFCOMM control to
wake a paired Android companion device and create a private Wi-Fi P2P IPv4 link
over p2p0 without enabling the phone's portable hotspot.

%prep

%build

%install
install -D -m 0755 %{srcdir}/opd-netshare-daemon %{buildroot}%{_libexecdir}/opd2413/opd-netshare-daemon
install -D -m 0755 %{srcdir}/opd-netshare %{buildroot}%{_bindir}/opd-netshare
install -D -m 0755 %{srcdir}/opd-netshare-tray %{buildroot}%{_bindir}/opd-netshare-tray

install -D -m 0600 %{srcdir}/config/netshare.conf %{buildroot}%{_sysconfdir}/opd2413/netshare.conf
install -D -m 0644 %{srcdir}/dbus/local.opd2413.NetShare.conf %{buildroot}%{_datadir}/dbus-1/system.d/local.opd2413.NetShare.conf
install -D -m 0644 %{srcdir}/nm/90-opd2413-netshare.conf %{buildroot}%{_prefix}/lib/NetworkManager/conf.d/90-opd2413-netshare.conf
install -D -m 0644 %{srcdir}/systemd/opd-netshare.service %{buildroot}%{_unitdir}/opd-netshare.service
install -D -m 0644 %{srcdir}/desktop/opd-netshare.desktop %{buildroot}%{_datadir}/applications/opd-netshare.desktop
install -D -m 0644 %{srcdir}/desktop/opd-netshare-tray.desktop %{buildroot}%{_sysconfdir}/xdg/autostart/opd-netshare-tray.desktop

%post
systemctl daemon-reload >/dev/null 2>&1 || :
systemctl reload dbus.service >/dev/null 2>&1 || :
systemctl reload NetworkManager.service >/dev/null 2>&1 || :
if [ "$1" -eq 1 ]; then
    systemctl enable opd-netshare.service >/dev/null 2>&1 || :
elif [ "$1" -ge 2 ]; then
    systemctl try-restart opd-netshare.service >/dev/null 2>&1 || :
fi

%preun
if [ "$1" -eq 0 ]; then
    systemctl --no-reload disable --now opd-netshare.service >/dev/null 2>&1 || :
fi

%postun
systemctl daemon-reload >/dev/null 2>&1 || :

%files
%dir %{_libexecdir}/opd2413
%{_libexecdir}/opd2413/opd-netshare-daemon
%{_bindir}/opd-netshare
%{_bindir}/opd-netshare-tray
%dir %{_sysconfdir}/opd2413
%config(noreplace) %attr(0600,root,root) %{_sysconfdir}/opd2413/netshare.conf
%{_datadir}/dbus-1/system.d/local.opd2413.NetShare.conf
%{_prefix}/lib/NetworkManager/conf.d/90-opd2413-netshare.conf
%{_unitdir}/opd-netshare.service
%{_datadir}/applications/opd-netshare.desktop
%{_sysconfdir}/xdg/autostart/opd-netshare-tray.desktop
