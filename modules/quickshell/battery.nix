{ pkgs, ... }:

let
  batteryAlert = pkgs.writeShellApplication {
    name = "battery-alert";
    runtimeInputs = [ pkgs.coreutils pkgs.libnotify ];
    text = builtins.readFile ./battery-alert.sh;
  };
in
{
  systemd.user.services.battery-alert = {
    Unit.Description = "Check the laptop battery and notify on low charge";
    Service = {
      Type = "oneshot";
      ExecStart = "${batteryAlert}/bin/battery-alert /sys/class/power_supply";
    };
  };

  systemd.user.timers.battery-alert = {
    Unit = {
      Description = "Monitor the laptop battery during the desktop session";
      PartOf = [ "graphical-session.target" ];
    };
    Timer = {
      OnActiveSec = "1s";
      OnUnitInactiveSec = "30s";
      AccuracySec = "1s";
    };
    Install.WantedBy = [ "graphical-session.target" ];
  };
}
