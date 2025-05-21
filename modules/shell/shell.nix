{ dotfiles, config, pkgs, ... }:

{
  programs.fish = {
    enable = true;
    interactiveShellInit = ''
      set fish_greeting # Disable greeting
      cat ${dotfiles}/modules/shell/intro.txt | lolcat
    '';
    shellAliases = {
      up = "cd ${dotfiles} && sudo nixos-rebuild switch --flake .#brenoslivio && home-manager switch --flake .#brenoslivio -b backup --impure && cd";
      home = "home-manager switch --flake ${dotfiles}#brenoslivio -b backup --impure";
    };
  };

  programs.starship.enable = true;

  programs.bash = {
    enable = true;
    initExtra = ''
      if [[ $(${pkgs.procps}/bin/ps --no-header --pid=$PPID --format=comm) != "fish" && -z ''${BASH_EXECUTION_STRING} ]]
      then
        shopt -q login_shell && LOGIN_OPTION='--login' || LOGIN_OPTION=""
        exec ${pkgs.fish}/bin/fish $LOGIN_OPTION
      fi
    '';
  };
}
