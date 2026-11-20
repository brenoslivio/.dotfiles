{ pkgs, ... }:

let
  waybar = pkgs.waybar.overrideAttrs (old: {
    patches = (old.patches or [ ]) ++ [ ./context-menu.patch ];
  });
  sources = pkgs.lib.fileset.toSource {
    root = ../../scripts;
    fileset = pkgs.lib.fileset.unions [
      ../../scripts/desktop_menu.py ../../scripts/waybar_audio.py ../../scripts/waybar_tasks.py
    ];
  };
  control = name: script: inputs: pkgs.writeShellApplication {
    inherit name;
    runtimeInputs = [ pkgs.python3 pkgs.zenity pkgs.libnotify ] ++ inputs;
    text = "exec python3 ${sources}/${script} \"$@\"";
  };
  audio = control "dotfiles-audio" "waybar_audio.py" [ pkgs.pulseaudio pkgs.pavucontrol ];
  tasks = control "dotfiles-tasks" "waybar_tasks.py" [ ];
in
{
  home.packages = [ audio waybar ];
  home.file = {
    ".config/waybar/config.jsonc".source = pkgs.replaceVars ./config.jsonc {
      # Keep the image available independently of home-file activation order.
      audioControl = pkgs.lib.getExe audio;
      taskControl = pkgs.lib.getExe tasks;
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
