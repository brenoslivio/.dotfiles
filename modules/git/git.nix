{ dotfiles, config, pkgs, ... }:

let
  # Path to your SSH public key
  username = config.home.username;
  homeDir = config.home.homeDirectory;
  pubkeyPath = "${homeDir}/.ssh/id_ed25519.pub";

  # Read the full line from the public key
  pubkeyLine = builtins.readFile pubkeyPath;

  # Extract the key type, base64 key, and comment (email or label)
  parts = builtins.match "([a-z0-9-]+) ([A-Za-z0-9+/=]+) ?(.*)" (builtins.readFile pubkeyPath);

  keyType = builtins.elemAt parts 0;
  keyBase64 = builtins.elemAt parts 1;
  keyComment = builtins.elemAt parts 2;
  principal = builtins.replaceStrings ["\n"] [""] keyComment;
in
{
  home.file.".ssh/allowed_signers".text = ''
    ${principal} ${keyType} ${keyBase64}
  '';

  programs.git = {
    enable = true;
    userName = username;
    userEmail = principal; # use the extracted email if desired
    extraConfig = {
      init.defaultBranch = "main";
      safe.directory = dotfiles;
      gpg.format = "ssh";
      user.signingKey = pubkeyPath;
      gpg.ssh.allowedSignersFile = "${homeDir}/.ssh/allowed_signers";
      commit.gpgSign = true;
      tag.gpgSign = true;
    };
  };
}