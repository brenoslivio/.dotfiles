# Do not modify this file!  It was generated by ‘nixos-generate-config’
# and may be overwritten by future invocations.  Please make changes
# to /etc/nixos/configuration.nix instead.
{ config, lib, pkgs, modulesPath, ... }:

{
  imports =
    [ (modulesPath + "/installer/scan/not-detected.nix")
    ];

  boot.initrd.availableKernelModules = [ "nvme" "xhci_pci" "ahci" "usbhid" "usb_storage" "sd_mod" ];
  boot.initrd.kernelModules = [ ];
  boot.kernelModules = [ "kvm-amd" ];
  boot.extraModulePackages = [ ];

  fileSystems."/" =
    { device = "/dev/disk/by-uuid/b1751659-a790-4b7d-bcf9-e0c0f859e0e0";
      fsType = "ext4";
    };

  boot.initrd.luks.devices."luks-2049dc63-a811-426e-9365-757ea16aa5b2".device = "/dev/disk/by-uuid/2049dc63-a811-426e-9365-757ea16aa5b2";

  boot.initrd.luks.devices."luks-4de7db73-acb9-40bd-8c1c-4b09c7d7f3be".device = "/dev/disk/by-uuid/4de7db73-acb9-40bd-8c1c-4b09c7d7f3be";

  fileSystems."/boot" =
    { device = "/dev/disk/by-uuid/3AF3-C668";
      fsType = "vfat";
      options = [ "fmask=0077" "dmask=0077" ];
    };

  swapDevices =
    [ { device = "/dev/disk/by-uuid/ed2471ec-1154-43b0-9e28-b54ca66816a1"; }
    ];

  # Enables DHCP on each ethernet and wireless interface. In case of scripted networking
  # (the default) this is the recommended approach. When using systemd-networkd it's
  # still possible to use this option, but it's recommended to use it in conjunction
  # with explicit per-interface declarations with `networking.interfaces.<interface>.useDHCP`.
  networking.useDHCP = lib.mkDefault true;
  # networking.interfaces.wlp1s0.useDHCP = lib.mkDefault true;

  nixpkgs.hostPlatform = lib.mkDefault "x86_64-linux";
  hardware.cpu.amd.updateMicrocode = lib.mkDefault config.hardware.enableRedistributableFirmware;
}
