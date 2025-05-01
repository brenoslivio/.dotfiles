{ dotfiles, outOfStore, config, pkgs, ... }:

{
  home.file = {
    ".config/rofi".source = outOfStore "${dotfiles}/modules/rofi";
  };
}
