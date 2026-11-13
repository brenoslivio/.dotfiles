{ config, pkgs, ... }:

let
  updater = import ../../scripts/updater-package.nix { inherit pkgs; };
in
{
  home.packages = [ updater ];
  programs.fish = {
    enable = true;
    interactiveShellInit = ''
      set fish_greeting # Disable greeting
      ${pkgs.lolcat}/bin/lolcat ${./intro.txt} 2> /dev/null
    '';
    functions = {
      __dotfiles_repo = {
        description = "Resolve and validate the dotfiles repository";
        body = ''
          set -l repo "$HOME/.dotfiles"
          if set -q DOTFILES_REPO
            set repo "$DOTFILES_REPO"
          end

          if not test -f "$repo/flake.nix"
            echo "Dotfiles flake not found at $repo" >&2
            return 1
          end

          echo "$repo"
        '';
      };

      up = {
        description = "Review and activate the latest CI-tested system";
        body = ''
          ${updater}/bin/dotfiles-update up; or return 1
          ${pkgs.starship}/bin/starship init fish | source
        '';
      };
      home = {
        description = "Activate the CI-tested standalone Home Manager environment";
        body = "${updater}/bin/dotfiles-update home";
      };
      up-vps = {
        description = "Review and deploy the CI-tested VPS over SSH";
        body = "${updater}/bin/dotfiles-update up-vps";
      };
      up-vps-status = {
        description = "Inspect the VPS pending, active, and boot-default systems";
        body = "${updater}/bin/dotfiles-update status-vps";
      };
      up-vps-confirm = {
        description = "Verify and confirm a VPS update after reboot";
        body = "${updater}/bin/dotfiles-update confirm-vps";
      };
      rollback-vps = {
        description = "Recover the VPS using its previous protected system";
        body = "${updater}/bin/dotfiles-update rollback-vps";
      };
      flake-update = {
        description = "Update inputs on a clean proposal branch";
        body = ''
          set -l repo (__dotfiles_repo); or return 1
          ${pkgs.bash}/bin/bash "$repo/scripts/propose-update.sh"
        '';
      };
      rollback = {
        description = "Restore the previous NixOS generation offline";
        body = "${updater}/bin/dotfiles-update rollback";
      };
      rollback-good = {
        description = "Restore the protected known-good system offline";
        body = "${updater}/bin/dotfiles-update rollback-good";
      };
      dotfiles-status = {
        description = "Show pending, active, and next-boot systems";
        body = "${updater}/bin/dotfiles-update status";
      };
      dotfiles-mark-good = {
        description = "Protect the active system after hardware verification";
        body = "${updater}/bin/dotfiles-update mark-good";
      };
      dotfiles-check = {
        description = "Run shared local and CI checks (optional: quick)";
        body = ''
          set -l repo (__dotfiles_repo); or return 1
          ${pkgs.bash}/bin/bash "$repo/scripts/check.sh" $argv
        '';
      };
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
