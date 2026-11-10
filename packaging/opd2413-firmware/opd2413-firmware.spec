# Firmware the OnePlus Pad 2 Pro needs beyond Fedora's linux-firmware.
# Built locally from files the user extracted from their own OTA; the
# resulting package is not for redistribution.
#
# rpmbuild --define 'fwver YYYYMMDD' --define 'pkgrel N' --define 'fw_tree /staged/tree'
# fw_tree holds exactly the files of manifest.sha256, already verified.

%global debug_package %{nil}
%global __os_install_post %{nil}

Name:           opd2413-firmware
Version:        %{fwver}
Release:        %{pkgrel}
Summary:        Device firmware for the OnePlus Pad 2 Pro (OPD2413)
License:        LicenseRef-Proprietary
BuildArch:      noarch
AutoReqProv:    no
Source0:        manifest.sha256

# Adreno 830 SQE/GMU/AQE microcode comes from Fedora.
Requires:       qcom-firmware

%description
ADSP, SoCCP, GPU ZAP, touchscreen and amplifier firmware extracted from the
stock OnePlus firmware, plus WCN7860 Wi-Fi and Bluetooth firmware that
linux-firmware does not carry yet. See the manifest for every file's hash.

%prep

%build

%install
mkdir -p %{buildroot}/usr/lib/firmware %{buildroot}/usr/share/opd2413
cp -a %{fw_tree}/. %{buildroot}/usr/lib/firmware/
grep -v '^#' %{SOURCE0} > %{buildroot}/usr/share/opd2413/firmware.sha256
(cd %{buildroot}/usr/lib/firmware && sha256sum --quiet --check %{buildroot}/usr/share/opd2413/firmware.sha256)

%files
/usr/lib/firmware/qcom/sm8750/erhai
/usr/lib/firmware/awinic/erhai
/usr/lib/firmware/novatek/nt36536-xn242.bin
/usr/lib/firmware/ath12k/WCN7860
/usr/lib/firmware/qca/gngbtfw20.mbn
/usr/lib/firmware/qca/gngbtnv20.bin
/usr/share/opd2413/firmware.sha256
