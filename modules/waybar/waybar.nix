{ ... }:

{
  home.file = {
    ".config/waybar/config.jsonc".source = ./config.jsonc;
    ".config/waybar/style.css".source = ./style.css;
    ".config/waybar/assets/nixos.svg".source = ../../assets/icons/nixos.svg;
    ".config/waybar/launch.sh" = {
      source = ./launch.sh;
      executable = true;
    };
    ".config/waybar/scripts/clock.sh" = {
      source = ./scripts/clock.sh;
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
}
