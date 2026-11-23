{ lib, pkgs, primaryUser, ... }:
{
  imports = [ ./hardware.nix ./audio.nix ];

  networking.hostName = "ahimsa";
  time.timeZone = lib.mkForce null;
  security.polkit.extraConfig = ''
    polkit.addRule(function(action, subject) {
      if (action.id !== "org.freedesktop.timedate1.set-timezone" ||
          subject.user !== ${builtins.toJSON primaryUser}) return;
      if (subject.local && subject.active) return polkit.Result.YES;
      // UWSM runs the panel under the user manager, outside the login session.
      var group = polkit.spawn(["${pkgs.coreutils}/bin/cat", "/proc/" + subject.pid + "/cgroup"]).trim();
      if (!group.endsWith("/app.slice/quickshell-panel.service")) return;
      var session = polkit.spawn(["${pkgs.systemd}/bin/loginctl", "show-seat", "seat0", "-p", "ActiveSession", "--value"]).trim();
      if (!session) return;
      var owner = polkit.spawn(["${pkgs.systemd}/bin/loginctl", "show-session", session, "-p", "Name", "--value"]).trim();
      if (owner === subject.user) return polkit.Result.YES;
    });
  '';

  # Trial for Bluetooth link timeouts on this RTL8822CE combo card: keep
  # Wi-Fi out of deep power saving. This is separate from btusb autosuspend.
  # Remove if it does not improve stability; it can increase power usage.
  boot.extraModprobeConfig = ''
    options rtw88_core disable_lps_deep=Y
  '';
}
