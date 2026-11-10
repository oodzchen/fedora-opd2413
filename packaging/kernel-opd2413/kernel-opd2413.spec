# Binary repackaging of an already built kernel tree (vmlinuz, modules, DTBs
# under lib/modules/<kver>/) into the layout Fedora's kernel-install expects.
# Nothing is compiled or stripped here: modules carry BTF that must match the
# kernel they were built with.
#
# rpmbuild --define 'kver 7.2.6' --define 'pkgrel 1' --define 'kernel_tarball /path/to.tar.zst'

%global debug_package %{nil}
%global __os_install_post %{nil}
%global _build_id_links none
%global __strip /bin/true

Name:           kernel-opd2413
Version:        %{kver}
Release:        %{pkgrel}
Summary:        Linux kernel for the OnePlus Pad 2 Pro (OPD2413)
License:        GPL-2.0-only
URL:            https://kernel.org
ExclusiveArch:  aarch64
AutoReqProv:    no

# Several kernel versions stay installed side by side, like Fedora's kernel.
Provides:       installonlypkg(kernel)
Provides:       kernel = %{version}-%{release}
Provides:       kernel-core = %{version}-%{release}
Provides:       kernel-modules = %{version}-%{release}
Provides:       kernel-modules-core = %{version}-%{release}
Provides:       kernel-uname-r = %{kver}
Provides:       kernel-core-uname-r = %{kver}
Provides:       kernel-modules-uname-r = %{kver}
Provides:       kernel-modules-core-uname-r = %{kver}

Requires:       kmod
Requires:       dracut
Requires:       systemd-udev
Requires(posttrans): /usr/bin/kernel-install
Requires(preun): /usr/bin/kernel-install

%description
Kernel, modules and device trees for the OnePlus Pad 2 Pro. The files install
under /usr/lib/modules/%{kver}; kernel-install deploys them to the ESP.

%prep

%build

%install
mkdir -p %{buildroot}/usr
tar --zstd -xf %{kernel_tarball} -C %{buildroot}/usr
test -s %{buildroot}/usr/lib/modules/%{kver}/vmlinuz
test -s %{buildroot}/usr/lib/modules/%{kver}/dtb/qcom/sm8750-oneplus-pad2pro.dtb
test -s %{buildroot}/usr/lib/modules/%{kver}/modules.dep

%posttrans
/usr/bin/kernel-install add %{kver} /usr/lib/modules/%{kver}/vmlinuz || exit $?

%preun
/usr/bin/kernel-install remove %{kver} || exit $?

%files
/usr/lib/modules/%{kver}
