{ lib, pkgs, ... }:

{
  home.file = {
    ".config/hypr/hyprland.conf".source = ./hyprland.conf;
    ".config/hypr/hyprlock.conf".source = ./hyprlock.conf;
    ".config/hypr/hyprpaper.conf".source = ./hyprpaper.conf;
    ".config/hypr/hyprdocked.sh" = {
      source = ./hyprdocked.sh;
      executable = true;
    };
  };

  # Route manual locks and suspend/lid locks through one supervised listener.
  services.hypridle = {
    enable = true;
    systemdTarget = "wayland-session@hyprland.desktop.target";
    settings.general = {
      lock_cmd = "${pkgs.procps}/bin/pidof hyprlock || ${pkgs.hyprlock}/bin/hyprlock --grace 0";
      before_sleep_cmd = "${pkgs.systemd}/bin/loginctl lock-session";
      after_sleep_cmd = "${pkgs.hyprland}/bin/hyprctl dispatch dpms on";
    };
  };

  # Keep dock handling alive and reconcile DRM connector changes.
  systemd.user.services.hyprdocked = {
    Install.WantedBy = [ "wayland-session@hyprland.desktop.target" ];
    Unit = {
      Description = "Apply and monitor the Hyprland dock layout";
      After = [ "wayland-session-waitenv.service" ];
      PartOf = [ "wayland-session@hyprland.desktop.target" ];
    };
    Service = {
      ExecStart = "${pkgs.bash}/bin/bash ${./hyprdocked.sh}";
      Environment = "PATH=${lib.makeBinPath [ pkgs.coreutils pkgs.gnugrep pkgs.hyprland ]}";
      Restart = "on-failure";
      RestartSec = 2;
    };
  };
}
