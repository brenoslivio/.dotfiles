{ lib, pkgs, ... }:
let
  displayMode = pkgs.writeShellScript "display-mode" ''
    export PATH="${lib.makeBinPath [ pkgs.hyprland pkgs.rofi ]}:$PATH"
    exec ${pkgs.python3}/bin/python3 ${./display_mode.py} "$@"
  '';
in
{
  home.file = {
    # The watchdog's safe-mode restart bypasses hyprland.lua, so this must
    # reach start-hyprland before it launches any compositor instance.
    ".config/uwsm/env-hyprland".text = ''
      export HYPRLAND_NO_RT=1
    '';
    ".config/hypr/hyprland.lua".source = ./hyprland.lua;
    ".config/hypr/hypridle.conf".source = ./hypridle.conf;
    ".config/hypr/hyprlock.conf".source = ./hyprlock.conf;
    ".config/hypr/hyprpaper.conf".source = ./hyprpaper.conf;
    ".config/hypr/hyprdocked.sh" = {
      source = displayMode;
      executable = true;
    };
  };

  # Listen for system lock requests and coordinate locking before suspend.
  services.hypridle = {
    enable = true;
    systemdTarget = "wayland-session@hyprland.desktop.target";
  };

  systemd.user.services.hypridle = {
    Unit.X-Restart-Triggers = [ "${./hypridle.conf}" ];
    Service.Environment = "PATH=${lib.makeBinPath [ pkgs.coreutils pkgs.procps pkgs.hyprlock pkgs.systemd pkgs.hyprland ]}";
  };

  services.hyprsunset = {
    enable = true;
    systemdTarget = "wayland-session@hyprland.desktop.target";
    settings.profile = [
      { time = "06:00"; temperature = 6500; }
      { time = "18:00"; temperature = 5625; }
      { time = "19:00"; temperature = 4750; }
      { time = "20:00"; temperature = 3875; }
      { time = "21:00"; temperature = 3000; }
    ];
  };

  systemd.user.services.hyprsunset.Unit = {
    # UWSM starts the compositor-specific target before graphical-session.target.
    After = lib.mkForce [ "wayland-session-waitenv.service" ];
    PartOf = lib.mkForce [ "wayland-session@hyprland.desktop.target" ];
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
      ExecStart = "${displayMode}";
      Restart = "on-failure";
      RestartSec = 2;
    };
  };
}
