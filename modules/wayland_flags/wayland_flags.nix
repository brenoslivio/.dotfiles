{ ... }:

{
  home.file = {
    ".config/code-flags.conf".source = ./code-flags.conf;
    ".config/obsidian-flags.conf".source = ./obsidian-flags.conf;
    ".config/spotify-flags.conf".source = ./spotify-flags.conf;
  };
}
