{ pkgs, ... }:

let
  waybar = pkgs.waybar.overrideAttrs (old: {
    patches = (old.patches or [ ]) ++ [ ./context-menu.patch ./icon-tooltip.patch ];
  });
  sources = pkgs.lib.fileset.toSource {
    root = ../../scripts;
    fileset = pkgs.lib.fileset.unions [
      ../../scripts/update.py ../../scripts/waybar_updates.py
      ../../scripts/desktop_menu.py ../../scripts/waybar_audio.py ../../scripts/waybar_tasks.py
    ];
  };
  control = name: script: inputs: pkgs.writeShellApplication {
    inherit name;
    runtimeInputs = [ pkgs.python3 ] ++ inputs;
    text = "exec python3 ${sources}/${script} \"$@\"";
  };
  audio = control "dotfiles-audio" "waybar_audio.py" [ pkgs.pulseaudio pkgs.pavucontrol pkgs.zenity pkgs.libnotify ];
  updates = control "dotfiles-update-indicator" "waybar_updates.py" [ pkgs.gh pkgs.systemd pkgs.xdg-utils ];
  tasks = control "dotfiles-tasks" "waybar_tasks.py" [ pkgs.zenity pkgs.libnotify ];
in
{
  home.packages = [ audio waybar ];
  home.file = {
    ".config/waybar/config.jsonc".source = pkgs.replaceVars ./config.jsonc {
      # Keep the image available independently of home-file activation order.
      updateControl = pkgs.lib.getExe updates;
      updateIcon = "${../../assets/icons/flake-update.svg}";
      bellIcon = "${../../assets/icons/notification-bell.svg}";
      taskIcon = "${../../assets/icons/tasks.svg}";
      audioControl = pkgs.lib.getExe audio;
      taskControl = pkgs.lib.getExe tasks;
      resourceMonitor = "${pkgs.python3}/bin/python3 ${../../scripts/waybar_resources.py}";
      nixosIcon = "${../../assets/icons/nixos.svg}";
    };
    ".config/waybar/style.css".source = ./style.css;
    ".config/waybar/cava.conf".source = ./cava.conf;
    ".config/waybar/launch.sh" = {
      source = ./launch.sh;
      executable = true;
    };
    ".config/waybar/scripts/clock.sh" = {
      source = ./scripts/clock.sh;
      executable = true;
    };
    ".config/waybar/scripts/cava.sh" = {
      source = ./scripts/cava.sh;
      executable = true;
    };
    ".config/waybar/scripts/research.sh" = {
      source = ./scripts/research.sh;
      executable = true;
    };
    ".config/waybar/scripts/tasks.sh" = {
      source = pkgs.writeShellScript "tasks.sh" ''exec ${pkgs.lib.getExe tasks} "$@"'';
      executable = true;
    };
  };

  systemd.user.services.dotfiles-update-check = {
    Unit.Description = "Refresh the Waybar flake update indicator";
    Service = {
      Type = "oneshot";
      ExecStart = "${pkgs.lib.getExe updates} check";
      ExecStopPost = "${pkgs.lib.getExe updates} finish";
      TimeoutStartSec = "90s";
    };
  };
  systemd.user.timers.dotfiles-update-check = {
    Unit = {
      Description = "Check the desktop update every five minutes";
      PartOf = [ "graphical-session.target" ];
    };
    Timer = {
      OnCalendar = "*-*-* *:0/5:00";
      OnActiveSec = "2s";
      AccuracySec = "1s";
      Persistent = true;
    };
    Install.WantedBy = [ "graphical-session.target" ];
  };

  # Run the Hyprland bar and recover automatically from crashes.
  systemd.user.services.waybar = {
    Unit = {
      Description = "Highly customizable Wayland bar";
      Documentation = "https://github.com/Alexays/Waybar/wiki/";
      PartOf = [ "graphical-session.target" ];
      After = [ "graphical-session.target" ];
      Requisite = [ "graphical-session.target" ];
    };
    Service = {
      ExecStart = "${waybar}/bin/waybar";
      ExecReload = "${pkgs.coreutils}/bin/kill -SIGUSR2 $MAINPID";
      Restart = "always";
      RestartSec = 1;
    };
    Install.WantedBy = [ "graphical-session.target" ];
  };
}
