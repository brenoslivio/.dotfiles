{ config, pkgs, ... }:

{
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
        description = "Build and activate NixOS and Home Manager";
        body = ''
          set -l repo (__dotfiles_repo); or return 1
          set -l host (hostname)
          set -l dirty_worktree (${pkgs.git}/bin/git -C "$repo" status --porcelain | string collect)

          if test -n "$dirty_worktree"
            echo "Warning: building from a dirty dotfiles worktree." >&2
          end

          sudo nixos-rebuild switch --flake "path:$repo#$host"; or return 1

          # Home Manager replaces the profile during the rebuild. Refresh the
          # prompt so this already-running shell does not retain Starship's old
          # profile path until the next terminal is opened.
          ${pkgs.starship}/bin/starship init fish | source
        '';
      };

      home = {
        description = "Build and activate only the Home Manager configuration";
        body = ''
          set -l repo (__dotfiles_repo); or return 1
          home-manager switch --flake "path:$repo#$USER"
        '';
      };

      flake-update = {
        description = "Update flake inputs and validate without activating";
        body = ''
          set -l repo (__dotfiles_repo); or return 1
          ${pkgs.nix}/bin/nix flake update --flake "$repo"; or return 1
          ${pkgs.nix}/bin/nix flake check --no-build "path:$repo"
        '';
      };

      rollback = {
        description = "Roll back the previous integrated NixOS generation";
        body = ''
          sudo nixos-rebuild switch --rollback
        '';
      };

      dotfiles-check = {
        description = "Check the current host configuration without activating";
        body = ''
          set -l repo (__dotfiles_repo); or return 1
          set -l host (hostname)
          ${pkgs.nix}/bin/nix flake check --no-build "path:$repo"; or return 1
          ${pkgs.nix}/bin/nix build --no-link "path:$repo#nixosConfigurations.$host.config.system.build.toplevel"
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
