{ lib, pkgs, ... }:
let
  displayMode = import ./display-mode.nix { inherit pkgs; };
  nightLight = lib.getExe (import ./night-light.nix { inherit pkgs; });
  mediaPython = pkgs.python3.withPackages (ps: [ ps.dbus-python ps.pillow ]);
  lockMedia = pkgs.writeShellScript "hyprlock-media" ''
    export PATH=${lib.makeBinPath [ pkgs.curl ]}:$PATH
    exec ${mediaPython}/bin/python3 ${./lock_media.py}
  '';
  blankCover = pkgs.runCommand "hyprlock-blank.png" {} ''
    ${mediaPython}/bin/python3 -c 'from PIL import Image; import sys; Image.new("RGBA", (1, 1)).save(sys.argv[1], "PNG")' "$out"
  '';
  lockCover = pkgs.writeShellScript "hyprlock-cover" ''
    cover="$XDG_RUNTIME_DIR/hyprlock-media/cover.png"
    if [[ -f "$cover" ]]; then
      echo "$cover"
    else
      echo ${blankCover}
    fi
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
    ".config/hypr/hyprlock.conf".text = lib.replaceStrings
      [ "@lockMedia@" "@lockCover@" "@blankCover@" ]
      [ (toString lockMedia) (toString lockCover) (toString blankCover) ]
      (builtins.readFile ./hyprlock.conf);
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
    extraArgs = [ "--temperature" "6500" ];
    settings.max-gamma = 100;
  };

  # One schedule writer also honors manual warmth across intermediate evening steps.
  systemd.user.services.hyprsunset.Service.ExecStartPost = "${nightLight} startup";
  systemd.user.services.night-light-schedule = {
    Unit = { Description = "Apply scheduled Night Light warmth"; Requisite = [ "hyprsunset.service" ]; After = [ "hyprsunset.service" ]; };
    Service = { Type = "oneshot"; ExecStart = "${nightLight} apply"; };
  };
  systemd.user.timers.night-light-schedule = {
    Unit = { Description = "Follow the Night Light schedule"; PartOf = [ "wayland-session@hyprland.desktop.target" ]; };
    Timer = {
      OnCalendar = "*-*-* *:*:00";
      AccuracySec = "1s";
      OnTimezoneChange = true;
      OnClockChange = true;
    };
    Install.WantedBy = [ "wayland-session@hyprland.desktop.target" ];
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
