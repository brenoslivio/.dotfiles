{ dotfiles, outOfStore, config, pkgs, ... }:

{
  home.file = {
    ".config/waybar".source = outOfStore "${dotfiles}/modules/waybar";
  };
}
