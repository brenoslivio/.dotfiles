{ pkgs, ... }:

{
  home.file = {
    ".config/waybar/config.jsonc".source = ./config.jsonc;
    ".config/waybar/style.css".source = pkgs.replaceVars ./style.css {
      # Copy the icon into the store and retain it as a CSS dependency.
      nixosIcon = "${../../assets/icons/nixos.svg}";
    };
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
      source = ./scripts/tasks.sh;
      executable = true;
    };
  };

  # Run one bar for either compositor and recover automatically from crashes.
  systemd.user.services.waybar = {
    Unit = {
      Description = "Highly customizable Wayland bar";
      Documentation = "https://github.com/Alexays/Waybar/wiki/";
      PartOf = [ "graphical-session.target" ];
      After = [ "graphical-session.target" ];
      Requisite = [ "graphical-session.target" ];
    };
    Service = {
      ExecStart = "${pkgs.waybar}/bin/waybar";
      ExecReload = "${pkgs.coreutils}/bin/kill -SIGUSR2 $MAINPID";
      Restart = "always";
      RestartSec = 1;
    };
    Install.WantedBy = [ "graphical-session.target" ];
  };
}
