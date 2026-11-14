{ lib, pkgs, primaryUserEmail, ... }:
let
  deploymentKey = "restrict ${lib.trim (builtins.readFile ../../config/vps-deploy-key.pub)}";
  # Existing VPS administrator key; public, safe to keep in Git.
  administratorKeys = [
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM+eg7lGNdzVMiScG3nbI8qZQBebhJpGHFRjnXHBxx46"
    # Dedicated GitHub deployment key: no forwarding, agent, X11, or PTY.
    deploymentKey
  ];
in {
  imports = [
    ./hardware.nix
    ../../system/services/media-stack.nix
    ../../system/services/vps-updates.nix
  ];

  boot.loader.systemd-boot = {
    enable = true;
    configurationLimit = 10;
  };
  boot.loader.efi.canTouchEfiVariables = true;
  boot.kernelParams = [ "console=tty1" "console=ttyS0,115200n8" ];

  networking = {
    hostName = "ahimsa-vps";
    useDHCP = false;
    useNetworkd = true;
  };
  # Preserve the installed VPS's DHCPv4 and static IPv6 routing.
  systemd.network.networks."10-uplink" = {
    matchConfig.MACAddress = "92:00:0a:77:04:79";
    networkConfig = {
      DHCP = "ipv4";
      IPv6AcceptRA = false;
    };
    address = [ "2a01:4f9:c015:6265::1/64" ];
    routes = [ { Gateway = "fe80::1"; GatewayOnLink = true; } ];
    linkConfig.RequiredForOnline = "routable";
  };
  users.users.root.openssh.authorizedKeys.keys = administratorKeys;
  # The first deployment uses a temporary copy in root's personal key file.
  # Remove it only once both generations have the key, so first-deploy rollback
  # retains GitHub's SSH access too.
  system.activationScripts.vps-deployment-key = {
    deps = [ "etc" ];
    text = ''
      ${pkgs.python3}/bin/python3 - <<'PY'
      import os, tempfile
      from pathlib import Path
      key = ${builtins.toJSON deploymentKey}
      managed = Path('/etc/ssh/authorized_keys.d/root')
      previous = Path('/run/current-system/etc/ssh/authorized_keys.d/root')
      bootstrap = Path('/root/.ssh/authorized_keys')
      if all(p.exists() and key in p.read_text().splitlines() for p in (managed, previous)) and bootstrap.is_file() and not bootstrap.is_symlink():
          lines = bootstrap.read_text().splitlines()
          if key in lines:
              with tempfile.NamedTemporaryFile('w', dir=bootstrap.parent, delete=False) as stream:
                  stream.write("".join(line+'\n' for line in lines if line != key))
                  temporary = stream.name
              os.replace(temporary, bootstrap)
      PY
    '';
  };

  services.qemuGuest.enable = true;
  services.fstrim.enable = true;
  services.journald.settings.Journal.SystemMaxUse = "200M";
  zramSwap.enable = true;
  services.caddy.email = primaryUserEmail;

  services.media-stack = {
    enable = true;
    components.lidarr = true;
    # Install the private Finland P2P WireGuard profile before deployment.
    vpn = {
      enable = true;
      configFile = "/var/lib/private/proton-vpn/finland.conf";
      portForwarding = true;
    };
    # Retain the original paths to simplify the later database/data migration.
    root = "/srv/media-test";
    budgetGiB = 35;
    minFreeGiB = 10;
    memoryHigh = "2500M";
    memoryMax = "3G";
    cpuQuota = "180%";
    maxSizeMBPerMinute = null;
    allowAllQualities = true;
    viewers = [ "breno" "bianca" ];
    viewerRenames = { brenoslivio = "breno"; partner = "bianca"; };
    indexers = [ "yts" "knaben" "torrentdownloads" "torrentdownload" ];
    automaticSearch = false;
    manualReleaseSelection = true;
    jellyfinEnhanced = true;
    personalHome = true;
    playbackPolish = true;
    jellyfinDomain = "media.breno.science";
    # Caddy reaches Jellyfin on loopback; keep the application port private.
    jellyfinLanInterfaces = [];
    subtitleLanguages = [ "pb" "en" ];
  };

  # Preserve the installed system's compatibility baseline.
  system.stateVersion = "26.05";
}
