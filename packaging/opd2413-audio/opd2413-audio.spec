# rpmbuild --define 'pkgver X' --define 'pkgrel N' --define 'srcdir /repo/device/audio'

Name:           opd2413-audio
Version:        %{pkgver}
Release:        %{pkgrel}
Summary:        ALSA UCM profile and AudioReach topology for the OnePlus Pad 2 Pro
License:        BSD-3-Clause
BuildArch:      noarch

Requires:       alsa-ucm
Requires:       opd2413-firmware

%description
UCM configuration for the OnePlus-Pad-2-Pro sound card (six AW88261
amplifiers over TDM, WCD939x capture) and the AudioReach topology it loads.

%prep

%build

%install
mkdir -p %{buildroot}/usr/share/alsa/ucm2
cp -r %{srcdir}/ucm2/. %{buildroot}/usr/share/alsa/ucm2/
install -D -m 0644 %{srcdir}/topology/OnePlus-Pad-2-Pro-tplg.bin %{buildroot}/usr/lib/firmware/qcom/sm8750/OnePlus-Pad-2-Pro-tplg.bin

%files
/usr/share/alsa/ucm2/conf.d/sm8750/sm8750.conf
/usr/share/alsa/ucm2/conf.d/sm8750/OnePlus-Pad-2-Pro.conf
/usr/share/alsa/ucm2/Qualcomm/sm8750/OnePlus-Pad-2-Pro
/usr/lib/firmware/qcom/sm8750/OnePlus-Pad-2-Pro-tplg.bin
