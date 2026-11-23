{ pkgs, ... }:

let
  panel = import ./package.nix { inherit pkgs; };
  panelControl = pkgs.writeShellScript "toggle-panel" ''
    set -eu
    exec 9>"$XDG_RUNTIME_DIR/quickshell-panel-toggle.lock"
    ${pkgs.util-linux}/bin/flock 9
    ctl=${pkgs.systemd}/bin/systemctl
    unit=quickshell-panel.service
    off="$XDG_RUNTIME_DIR/quickshell-panel.off"
    case "''${1:-toggle}" in
      toggle)
        if [[ $("$ctl" --user show -p MainPID --value "$unit") != 0 ]]; then
          # Block notification activation before releasing the D-Bus name.
          : > "$off"
          exec "$ctl" --user stop "$unit"
        fi
        action=start ;;
      --start) action=start ;;
      --restart) action=restart ;;
      *) exit 2 ;;
    esac
    if [[ -e "$off" ]]; then ${pkgs.coreutils}/bin/unlink "$off"; fi
    "$ctl" --user reset-failed "$unit"
    exec "$ctl" --user "$action" "$unit"
  '';
in {
  home.packages = [ panel panel.audio ];
  xdg.configFile."quickshell/audio".source = "${panel.audio}/bin/dotfiles-audio";
  xdg.dataFile."dbus-1/services/org.freedesktop.Notifications.service".text = ''
    [D-BUS Service]
    Name=org.freedesktop.Notifications
    Exec=${panel}/bin/quickshell-panel
    SystemdService=quickshell-panel.service
  '';
  xdg.configFile."quickshell/power-menu".source = pkgs.writeShellScript "power-menu" ''
    ${panelControl} --start || exit 1
    # A freshly started panel can take a moment to register its IPC handler.
    for attempt in {1..30}; do
      if [[ $(${panel}/bin/quickshell-panel ipc call powerMenu toggle) == true ]]; then exit 0; fi
      ${pkgs.coreutils}/bin/sleep 0.1
    done
    exit 1
  '';
  xdg.configFile."quickshell/toggle-panel".source = panelControl;
  systemd.user.services.quickshell-panel = {
    Unit = {
      Description = "Quickshell desktop panel";
      PartOf = [ "graphical-session.target" ];
      After = [ "wayland-session-waitenv.service" ];
      Conflicts = [ "waybar.service" ];
      ConditionPathExists = "!%t/quickshell-panel.off";
    };
    Service = {
      Type = "dbus";
      BusName = "org.freedesktop.Notifications";
      ExecStart = "${panel}/bin/quickshell-panel";
      Restart = "on-failure";
      RestartSec = 2;
      TimeoutStopSec = "4s";
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
