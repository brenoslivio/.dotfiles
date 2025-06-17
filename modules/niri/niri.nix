{ dotfiles, outOfStore, config, pkgs, ... }:

{
  home.file = {
    ".config/niri".source = outOfStore "${dotfiles}/modules/niri";
  };
}
