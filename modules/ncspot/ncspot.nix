{ dotfiles, outOfStore, config, pkgs, ... }:

{
  home.file = {
    ".config/ncspot/config.toml".source = outOfStore "${dotfiles}/modules/ncspot/config.toml";
  };
}
