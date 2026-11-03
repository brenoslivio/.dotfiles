{
  imports = [ ./hardware.nix ];

  networking.hostName = "ahimsa";

  # Trial for Bluetooth link timeouts on this RTL8822CE combo card: keep
  # Wi-Fi out of deep power saving. This is separate from btusb autosuspend.
  # Remove if it does not improve stability; it can increase power usage.
  boot.extraModprobeConfig = ''
    options rtw88_core disable_lps_deep=Y
  '';
}
