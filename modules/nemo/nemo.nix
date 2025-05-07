{ dotfiles, outOfStore, config, pkgs, ... }:

{
  home.file = {
    ".local/share/nemo/actions".source = outOfStore "${dotfiles}/modules/nemo";
  };
}