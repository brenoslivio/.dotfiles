{ dotfiles, outOfStore, config, pkgs, ... }:

{
  home.file = {
    ".config/hypr".source = outOfStore "${dotfiles}/modules/hypr";
  };
}
