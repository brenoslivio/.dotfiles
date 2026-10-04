{ pkgs, ... }:

{
  services.kdeconnect = {
    enable = true;
    package = pkgs.kdePackages.kdeconnect-kde;
    indicator = true;
  };

  # KDE Connect's Bluetooth backend keeps BlueZ in continuous discovery,
  # which destabilizes Bluetooth LE input devices. Keep KDE Connect on LAN.
  systemd.user.services.kdeconnect-disable-bluetooth = {
    Unit = {
      Description = "Disable KDE Connect Bluetooth discovery";
      After = [ "kdeconnect.service" ];
      PartOf = [ "graphical-session.target" ];
    };
    Service = {
      Type = "oneshot";
      ExecStart = "${pkgs.kdePackages.kdeconnect-kde}/bin/kdeconnect-cli --disable-backend AsyncLinkProvider";
      RemainAfterExit = true;
    };
    Install.WantedBy = [ "graphical-session.target" ];
  };

  xdg.desktopEntries = {
    "org.kde.kdeconnect.sms" = {
      exec = "";
      name = "KDE Connect SMS";
      settings.NoDisplay = "true";
    };
    "org.kde.kdeconnect.nonplasma" = {
      exec = "";
      name = "KDE Connect Indicator";
      settings.NoDisplay = "true";
    };
    "org.kde.kdeconnect.app" = {
      exec = "";
      name = "KDE Connect";
      settings.NoDisplay = "true";
    };
  };
}
