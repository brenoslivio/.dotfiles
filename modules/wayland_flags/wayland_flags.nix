{ dotfiles, outOfStore, config, pkgs, ... }:

{
  home.file = {
    ".config/code-flags.conf".source = outOfStore "${dotfiles}/modules/wayland_flags/code-flags.conf";
    ".config/obsidian-flags.conf".source = outOfStore "${dotfiles}/modules/wayland_flags/obsidian-flags.conf";
    ".config/spotify-flags.conf".source = outOfStore "${dotfiles}/modules/wayland_flags/spotify-flags.conf";
  };
}
