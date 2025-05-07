{ dotfiles, outOfStore, config, pkgs, ... }:

{
  home.file = {
    ".config/fastfetch/config.jsonc".source = outOfStore "${dotfiles}/modules/fastfetch/config.jsonc";
  };
}
