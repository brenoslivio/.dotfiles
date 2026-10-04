{ pkgs, ... }:

{
  home.file = {
    ".config/rofi/config.rasi".source = ./config.rasi;
    ".config/rofi/launch.sh" = {
      source = ./launch.sh;
      executable = true;
    };
  };

  programs.rofi = {
    enable = true;
    package = pkgs.rofi;
    plugins = [
        pkgs.rofi-calc
    ];
    # Keep Home Manager's generated file separate from the hand-written theme.
    configPath = "hm-generated.rasi";
  };
}
