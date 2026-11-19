%global         base_name polkit-kde-agent-1

Name:    polkit-kde
Summary: PolicyKit integration for KDE Desktop
Version: 6.8.3
Release: 1%{?dist}.opd2413%{?opdrel:.%{opdrel}}

License: GPL-2.0-or-later AND CC0-1.0
URL:     https://invent.kde.org/plasma/%{base_name}

Source0: https://download.kde.org/stable/plasma/%{version}/%{base_name}-%{version}.tar.xz

## upstreamable / opd2413 patches
Patch01: 0001-add-explicit-face-recognition-confirmation-button.patch

BuildRequires:  extra-cmake-modules
BuildRequires:  kf6-rpm-macros
BuildRequires:  systemd-rpm-macros
BuildRequires:  qt6-qtbase-devel

BuildRequires:  cmake(KF6I18n)
BuildRequires:  cmake(KF6WindowSystem)
BuildRequires:  cmake(KF6DBusAddons)
BuildRequires:  cmake(KF6WidgetsAddons)
BuildRequires:  cmake(KF6CoreAddons)
BuildRequires:  cmake(KF6Crash)
BuildRequires:  cmake(KF6Config)
BuildRequires:  cmake(KF6IconThemes)
BuildRequires:  cmake(KF6Notifications)
BuildRequires:  cmake(KF6Declarative)

BuildRequires:  polkit-qt6-1-devel

Provides: PolicyKit-authentication-agent = %{version}-%{release}
Provides: polkit-kde-1 = %{version}-%{release}
Provides: polkit-kde-agent-1 = %{version}-%{release}

Obsoletes: PolicyKit-kde < 4.5

# Add explicit dependency on polkit, since polkit-libs were split out
Requires: polkit

%description
Provides Policy Kit Authentication Agent that nicely fits to KDE.


%prep
%autosetup -n %{base_name}-%{version} -p1


%build
%cmake_kf6 \
  -DKDE_INSTALL_LIBEXECDIR:PATH=%{_kf6_libexecdir}

%cmake_build

%install
%cmake_install

%find_lang polkit-kde-authentication-agent-1


%files -f polkit-kde-authentication-agent-1.lang
%license LICENSES/*
%{_kf6_libexecdir}/polkit-kde-authentication-agent-1
%{_sysconfdir}/xdg/autostart/polkit-kde-authentication-agent-1.desktop
%{_kf6_datadir}/knotifications6/polkit-kde-authentication-agent-1.notifyrc
%{_kf6_datadir}/applications/org.kde.polkit-kde-authentication-agent-1.desktop
%{_userunitdir}/plasma-polkit-agent.service


%changelog
* Thu Nov 19 2026 OPD2413 Maintainer <opd2413@local> - 6.8.3-1.opd2413.2
- Use monochrome symbolic smile icon (preferences-desktop-emoticons-symbolic) on face recognition button

* Tue Nov 17 2026 OPD2413 Maintainer <opd2413@local> - 6.8.3-1.opd2413.1
- Require explicit button click in authentication dialog before running OPD2413 face verification

* Thu Nov 12 2026 Steve Cossette <farchord@gmail.com> - 6.8.3-1
- 6.8.3
