{ pkgs, ... }:
{
  nix.gc = {
    automatic = true;
    dates = "weekly";
    options = "--delete-older-than 60d";
  };

  networking.firewall.enable = true;
  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "prohibit-password";
    };
  };
  environment.systemPackages = with pkgs; [
    git gh vim tmux fastfetch btop ncdu jq ripgrep fd
    curl wget rsync rclone unzip zip lsof dnsutils
    wireguard-tools openresolv
  ];
  programs.bash.completion.enable = true;
}
