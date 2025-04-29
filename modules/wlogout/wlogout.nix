{ dotfiles, outOfStore, config, pkgs, ... }:

{
  home.file = {
    ".config/wlogout".source = outOfStore "${dotfiles}/modules/wlogout";
  };
}
