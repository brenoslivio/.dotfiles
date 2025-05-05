{ dotfiles, outOfStore, config, pkgs, ... }:

{
  home.file = {
    ".config/cava/config".source = outOfStore "${dotfiles}/modules/cava/config";
  };
}
