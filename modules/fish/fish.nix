{ dotfiles, config, pkgs, ... }:

{
  programs.fish = {
    enable = true;
    interactiveShellInit = ''
      set fish_greeting # Disable greeting
      figlet $hostname | cowsay -f tux -n | lolcat
    '';
    shellAliases = {
      nixos = "sudo nixos-rebuild switch --flake ${dotfiles}#brenoslivio --upgrade";
      home = "home-manager switch --flake ${dotfiles}#brenoslivio -b backup --impure";
    };
  };

  programs.starship.enable = true;
}
