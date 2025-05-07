{ dotfiles, config, pkgs, ... }:

{
  programs.git = {
    enable = true;
    userName = "brenoslivio";
    userEmail = "brenoslivio@pm.me";
    extraConfig = {
      init.defaultBranch = "main";
      safe.directory = "/home/brenoslivio/.dotfiles";
      gpg.format = "ssh";
      user.signingKey = "/home/brenoslivio/.ssh/id_ed25519.pub";
      commit.gpgSign = true;
    };
  };
}
