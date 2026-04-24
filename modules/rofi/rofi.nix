{ dotfiles, outOfStore, config, pkgs, ... }:

{
  home.file = {
    ".config/rofi".source = outOfStore "${dotfiles}/modules/rofi";
  };

  programs.rofi = {
    enable = true;
    package = pkgs.rofi;
    plugins = [
        pkgs.rofi-calc
    ];
    configPath = "";
  };
}