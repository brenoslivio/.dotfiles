{ dotfiles, config, pkgs, ... }:

{
  programs.fish = {
    enable = true;
    interactiveShellInit = ''
      set fish_greeting # Disable greeting
      figlet $hostname | cowsay -f tux -n | lolcat
    '';
    shellAliases = {
      up = "cd ${dotfiles} && nix flake update && sudo nixos-rebuild switch --flake ${dotfiles}#brenoslivio && cd";
      home = "home-manager switch --flake ${dotfiles}#brenoslivio -b backup --impure";
    };
  };

  programs.starship.enable = true;
}
