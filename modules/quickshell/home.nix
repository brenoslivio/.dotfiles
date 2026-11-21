{ pkgs, ... }:

let
  panel = import ./package.nix { inherit pkgs; };
in {
  home.packages = [ panel panel.audio ];
  xdg.configFile."quickshell/power-menu".source = pkgs.writeShellScript "power-menu" ''
    ${pkgs.systemd}/bin/systemctl --user start quickshell-panel.service || exit 1
    # A freshly started panel can take a moment to register its IPC handler.
    for attempt in {1..30}; do
      if [[ $(${panel}/bin/quickshell-panel ipc call powerMenu toggle) == true ]]; then exit 0; fi
      ${pkgs.coreutils}/bin/sleep 0.1
    done
    exit 1
  '';
  xdg.configFile."quickshell/toggle-panel".source = pkgs.writeShellScript "toggle-panel" ''
    if ${pkgs.systemd}/bin/systemctl --user is-active --quiet quickshell-panel.service; then
      exec ${pkgs.systemd}/bin/systemctl --user stop quickshell-panel.service
    fi
    exec ${pkgs.systemd}/bin/systemctl --user start quickshell-panel.service
  '';
  systemd.user.services.quickshell-panel = {
    Unit = {
      Description = "Quickshell desktop panel";
      PartOf = [ "graphical-session.target" ];
      After = [ "wayland-session-waitenv.service" ];
      Conflicts = [ "waybar.service" ];
    };
    Service = {
      ExecStart = "${panel}/bin/quickshell-panel";
      Restart = "on-failure";
      RestartSec = 2;
    };
    Install.WantedBy = [ "wayland-session@hyprland.desktop.target" ];
  };
  systemd.user.services.dotfiles-update-check = {
    Unit.Description = "Refresh the desktop flake update indicator";
    Service = {
      Type = "oneshot";
      ExecStart = "${pkgs.lib.getExe panel.updates} check";
      ExecStopPost = "${pkgs.lib.getExe panel.updates} finish";
      TimeoutStartSec = "90s";
    };
  };
  systemd.user.timers.dotfiles-update-check = {
    Unit = {
      Description = "Check the desktop update every five minutes";
      PartOf = [ "graphical-session.target" ];
    };
    Timer = { OnCalendar = "*-*-* *:0/5:00"; OnActiveSec = "2s"; AccuracySec = "1s"; Persistent = true; };
    Install.WantedBy = [ "graphical-session.target" ];
  };
}
