{ config, lib, pkgs, ... }:
let
  cfg = config.services.media-stack.vpn;
  port = toString config.services.media-stack.ports.qbittorrent;
  helper = pkgs.writeShellApplication {
    name = "media-vpn";
    runtimeInputs = [ pkgs.python3 pkgs.iproute2 pkgs.wireguard-tools pkgs.nftables pkgs.procps pkgs.libnatpmp ];
    text = ''exec python3 ${../../scripts/media_vpn.py} "$@"'';
  };
  # Avoid host nscd/systemd-resolved resolving torrent names outside the tunnel.
  nsswitch = pkgs.runCommand "media-vpn-nsswitch.conf" {} ''
    sed '/^hosts:/c\hosts: files dns' ${config.environment.etc."nsswitch.conf".source} > "$out"
  '';
  dependencies = [ "media-vpn.service" ];
  namespace = "/run/netns/media-vpn";
in {
  options.services.media-stack.vpn = {
    enable = lib.mkEnableOption "qBittorrent-only Proton WireGuard isolation";
    configFile = lib.mkOption {
      type = lib.types.str;
      default = "/var/lib/private/proton-vpn/finland.conf";
      description = "Runtime secret: Proton Finland P2P WireGuard profile, never a Nix path.";
    };
    portForwarding = lib.mkOption { type = lib.types.bool; default = true; };
    gateway = lib.mkOption { type = lib.types.str; default = "10.2.0.1"; };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      { assertion = config.services.media-stack.enable && config.services.media-stack.components.qbittorrent;
        message = "Media VPN requires the media stack's qBittorrent component."; }
      { assertion = lib.hasPrefix "/" cfg.configFile && !(lib.hasPrefix "/nix/store/" cfg.configFile);
        message = "Proton private configuration must be an absolute runtime path outside the Nix store."; }
    ];
    boot.kernelModules = [ "wireguard" ];
    systemd.services.media-vpn = {
      description = "Isolated Proton network for qBittorrent";
      wantedBy = [ "multi-user.target" ];
      wants = [ "network-online.target" ];
      after = [ "network-online.target" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        RuntimeDirectory = "media-vpn";
        RuntimeDirectoryMode = "0755";
        LoadCredential = [ "wireguard:${cfg.configFile}" ];
        ExecStart = "${helper}/bin/media-vpn start ${port}";
        ExecStop = "${helper}/bin/media-vpn stop";
      };
    };
    systemd.services.qbittorrent = {
      requires = dependencies;
      after = dependencies;
      bindsTo = dependencies;
      partOf = dependencies;
      serviceConfig = {
        NetworkNamespacePath = namespace;
        BindReadOnlyPaths = [
          "/run/media-vpn/resolv.conf:/etc/resolv.conf"
          "${nsswitch}:/etc/nsswitch.conf"
        ];
        InaccessiblePaths = [ "-/run/nscd" ];
      };
    };
    # The listening socket stays on host loopback. Only the proxy process enters
    # the namespace, so the API remains reachable without giving torrents a veth.
    systemd.sockets.media-vpn-api = {
      wantedBy = [ "sockets.target" ];
      listenStreams = [ "127.0.0.1:${port}" ];
      socketConfig.NoDelay = true;
    };
    systemd.services.media-vpn-api = {
      requires = dependencies ++ [ "qbittorrent.service" ];
      after = dependencies ++ [ "qbittorrent.service" ];
      bindsTo = dependencies;
      partOf = dependencies;
      serviceConfig = {
        ExecStart = "${pkgs.systemd}/lib/systemd/systemd-socket-proxyd 127.0.0.1:${port}";
        NetworkNamespacePath = namespace;
        DynamicUser = true;
        NoNewPrivileges = true;
        PrivateTmp = true;
        ProtectSystem = "strict";
        ProtectHome = true;
      };
    };
    systemd.services.media-vpn-forward = lib.mkIf cfg.portForwarding {
      description = "Renew Proton NAT-PMP port and update qBittorrent";
      requires = dependencies ++ [ "qbittorrent.service" ];
      after = dependencies ++ [ "qbittorrent.service" ];
      bindsTo = dependencies;
      partOf = dependencies;
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${helper}/bin/media-vpn forward ${port} ${lib.escapeShellArg cfg.gateway}";
        NetworkNamespacePath = namespace;
        LoadCredential = [ "qbittorrent:/var/lib/media-stack/qbittorrent.json" ];
        TimeoutStartSec = 45;
        NoNewPrivileges = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        ReadWritePaths = [ "/run/media-vpn" ];
      };
    };
    systemd.timers.media-vpn-forward = lib.mkIf cfg.portForwarding {
      wantedBy = [ "timers.target" ];
      timerConfig = { OnBootSec = "45s"; OnUnitInactiveSec = "25s"; AccuracySec = "1s"; };
    };
  };
}
