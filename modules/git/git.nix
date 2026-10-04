{ config, primaryUserDescription, primaryUserEmail, ... }:

let
  homeDir = config.home.homeDirectory;
  pubkeyPath = "${homeDir}/.ssh/id_ed25519.pub";
in
{
  programs.git = {
    enable = true;
    settings = {
      user.name = primaryUserDescription;
      user.email = primaryUserEmail;
      init.defaultBranch = "main";
      gpg.format = "ssh";
      user.signingKey = pubkeyPath;
      gpg.ssh.allowedSignersFile = "${homeDir}/.ssh/allowed_signers";
      commit.gpgSign = true;
      tag.gpgSign = true;
    };
  };
}
