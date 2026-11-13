{ config, lib, pkgs, ... }:
let
  cfg = config.services.media-stack;
  settings = pkgs.writeText "vps-update.json" (builtins.toJSON {
    host = "ahimsa-vps";
    url = "https://${cfg.jellyfinDomain}";
    jellyfinPort = cfg.ports.jellyfin;
    services = [ "sshd.service" "media-stack-setup.service" "media-releases.service" "caddy.service" ]
      ++ map (name: "${name}.service") (builtins.attrNames (lib.filterAttrs (_: enabled: enabled) cfg.components));
  });
  helper = pkgs.writeShellApplication {
    name = "dotfiles-vps-control";
    runtimeInputs = [ pkgs.python3 pkgs.nix pkgs.systemd ];
    text = ''
      export DOTFILES_VPS_CONTROL="$0"
      exec python3 ${../../scripts/vps_control.py} --config ${settings} "$@"
    '';
  };
in {
  environment.systemPackages = [ helper ];
  systemd.tmpfiles.rules = [ "d /var/lib/dotfiles-vps 0700 root root -" ];
  systemd.services.dotfiles-vps-boot-prepare = {
    description = "Back up media state before a scheduled VPS activation";
    before = [ "media-stack-prepare.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      UMask = "0077";
      ExecStart = "${helper}/bin/dotfiles-vps-control boot-prepare";
      TimeoutStartSec = "30min";
    };
  };
  systemd.services.media-stack-prepare = {
    requires = [ "dotfiles-vps-boot-prepare.service" ];
    after = [ "dotfiles-vps-boot-prepare.service" ];
  };
  systemd.services.dotfiles-vps-recovery = {
    description = "Recover unconfirmed VPS activations";
    after = [ "dotfiles-vps-boot-prepare.service" ];
    serviceConfig = {
      Type = "oneshot";
      UMask = "0077";
      ExecStart = "${helper}/bin/dotfiles-vps-control recover";
      TimeoutStartSec = "10min";
    };
  };
  systemd.timers.dotfiles-vps-recovery = {
    wantedBy = [ "timers.target" ];
    timerConfig = { OnBootSec = "30s"; OnUnitActiveSec = "30s"; AccuracySec = "1s"; };
  };
}
