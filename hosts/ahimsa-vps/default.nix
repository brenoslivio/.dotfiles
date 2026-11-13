{ inputs, primaryUserEmail, ... }:
let
  # Existing VPS administrator key; public, safe to keep in Git.
  administratorKeys = [
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM+eg7lGNdzVMiScG3nbI8qZQBebhJpGHFRjnXHBxx46"
  ];
in {
  imports = [
    ./hardware.nix
    ../../system/services/media-stack.nix
    ../../system/services/vps-updates.nix
    # Backport declarative Bazarr credentials/settings, missing from 26.05.
    (inputs.nixpkgs + "/nixos/modules/services/misc/bazarr.nix")
  ];
  disabledModules = [ "services/misc/bazarr.nix" ];

  # Keep the working media versions and plugin APIs; the OS and other tools
  # use stable. Downgrading these applications would also risk migrated data.
  nixpkgs.overlays = [ (_final: _prev:
    let media = inputs.nixpkgs.legacyPackages.x86_64-linux;
    in {
      inherit (media) jellyfin jellyfin-web jellyfin-ffmpeg seerr radarr sonarr
        lidarr prowlarr qbittorrent-nox bazarr;
    }) ];

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

  services.qemuGuest.enable = true;
  services.fstrim.enable = true;
  services.journald.extraConfig = "SystemMaxUse=200M";
  zramSwap.enable = true;
  services.caddy.email = primaryUserEmail;

  services.media-stack = {
    enable = true;
    components.lidarr = true;
    # Retain the original paths to simplify the later database/data migration.
    root = "/srv/media-test";
    budgetGiB = 35;
    minFreeGiB = 10;
    memoryHigh = "2500M";
    memoryMax = "3G";
    cpuQuota = "180%";
    maxSizeMBPerMinute = null;
    allowAllQualities = true;
    viewers = [ "brenoslivio" "partner" ];
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
