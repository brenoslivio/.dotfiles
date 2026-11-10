{ pkgs, ... }:

{
  home.file = {
    ".config/waybar/config.jsonc".source = pkgs.replaceVars ./config.jsonc {
      # Keep the image available independently of home-file activation order.
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
      source = ./scripts/tasks.sh;
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
      ExecStart = "${pkgs.waybar}/bin/waybar";
      ExecReload = "${pkgs.coreutils}/bin/kill -SIGUSR2 $MAINPID";
      Restart = "always";
      RestartSec = 1;
    };
    Install.WantedBy = [ "graphical-session.target" ];
  };
}
