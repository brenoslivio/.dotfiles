{ config, lib, pkgs, options, ... }:
let
  inherit (lib) mkOption mkEnableOption mkIf types;
  cfg = config.services.media-stack;
  names = [ "jellyfin" "seerr" "radarr" "sonarr" "prowlarr" "qbittorrent" "bazarr" "lidarr" ];
  enabled = builtins.filter (name: cfg.components.${name}) names;
  settings = pkgs.writeText "media-stack.json" (builtins.toJSON {
    inherit (cfg) root ports budgetGiB minFreeGiB downloadKiB uploadKiB viewers indexers automaticSearch libraryScanMinutes jellyfinEnhanced subtitleLanguages manualReleaseSelection releasePort jellyfinLanInterfaces jellyfinDomain personalHome recommendationCount recommendationSeedLimit recommendationRefreshHours;
    inherit enabled;
    inherit (cfg) viewerRenames;
    inherit (cfg) maxSizeMBPerMinute allowAllQualities playbackPolish;
    vpnInterface = if cfg.vpn.enable then "proton0" else "";
    stateDir = "/var/lib/media-stack";
  });
  releasePlugin = import ./media-releases/package.nix { inherit pkgs; };
  uiRevision = builtins.substring 0 16 (builtins.hashString "sha256"
    (builtins.readFile ./media-releases/picker.js + builtins.readFile ./media-releases/personal.js + builtins.readFile ./media-releases/music.js
      + builtins.readFile ./media-releases/Plugin.cs));
  mediaWeb = pkgs.runCommand "jellyfin-media-web-${uiRevision}" {} ''
    mkdir -p "$out/share"
    # Jellyfin's static handler reports symlink lengths, truncating responses.
    cp -rL ${pkgs.jellyfin-web}/share/jellyfin-web "$out/share/jellyfin-web"
    chmod u+w "$out/share/jellyfin-web"
    rm "$out/share/jellyfin-web/index.html"
    substitute ${pkgs.jellyfin-web}/share/jellyfin-web/index.html "$out/share/jellyfin-web/index.html" \
      --replace-fail '</body>' '<script plugin="Jellyfin Enhanced" src="../JellyfinEnhanced/script?media=${uiRevision}" defer></script></body>'
  '';
  mediaJellyfin = pkgs.symlinkJoin {
    name = "jellyfin-media-${pkgs.jellyfin.version}";
    paths = [ pkgs.jellyfin ];
    meta = pkgs.jellyfin.meta;
    postBuild = ''
      rm "$out/bin/jellyfin"
      substitute ${pkgs.jellyfin}/bin/jellyfin "$out/bin/jellyfin" \
        --replace-fail '${pkgs.jellyfin-web}/share/jellyfin-web' '${mediaWeb}/share/jellyfin-web'
      chmod +x "$out/bin/jellyfin"
    '';
  };
  releaseScripts = pkgs.runCommand "media-release-broker" {} ''
    mkdir -p "$out"
    cp ${../../scripts/media-stack.py} "$out/media-stack.py"
    cp ${../../scripts/media-releases.py} "$out/media-releases.py"
    cp ${../../scripts/media-personal.py} "$out/media-personal.py"
    cp ${../../scripts/media-next-up.py} "$out/media-next-up.py"
    cp ${../../scripts/media-removal.py} "$out/media-removal.py"
    cp ${../../scripts/media-activity.py} "$out/media-activity.py"
    cp ${../../scripts/media-music.py} "$out/media-music.py"
  '';
  enhanced = pkgs.runCommand "jellyfin-enhanced-12.15.0.0" {
    src = pkgs.fetchurl {
      url = "https://github.com/n00bcodr/Jellyfin-Enhanced/releases/download/12.15.0.0/Jellyfin.Plugin.JellyfinEnhanced_12.0.0.zip";
      hash = "sha256-Gci2kVV75LNCViBp5hB1bilL1GSO7+HyVQTDAU2Q4vs=";
    };
    nativeBuildInputs = [ pkgs.unzip ];
  } ''
    mkdir -p "$out"
    unzip "$src" -d "$out"
  '';
  introSkipper = pkgs.runCommand "jellyfin-intro-skipper-12.0.6.0" {
    src = pkgs.fetchurl {
      url = "https://github.com/intro-skipper/intro-skipper/releases/download/12.0/v12.0.6.0/intro-skipper-v12.0.6.0.zip";
      hash = "sha256-KMsrku1R8OYCnEYpXNIBvgL9UMupjRjxTe/m1SqjY1I=";
    };
    nativeBuildInputs = [ pkgs.unzip ];
  } ''
    mkdir -p "$out"
    unzip "$src" -d "$out"
  '';
  # Seed definitions so initial setup also works without Prowlarr's definition server.
  definitions = lib.mapAttrs (name: hash: pkgs.fetchurl {
    url = "https://raw.githubusercontent.com/Prowlarr/Indexers/d45f173d8b91c7965b70447c2eb5812483dfd730/definitions/v11/${name}.yml";
    inherit hash;
  }) {
    internetarchive = "sha256-BpNw3duEyxBN2DbBWXooWxFS8cfCEqTHKnnFruFWSms=";
    "1337x" = "sha256-hBmJmYPqIJ5+hzptan2kJuRaanhjCKQu0ylQ+ot2uYU=";
    nyaasi = "sha256-zqegbJOrvEbbsesNdNNN/sofJE8/f/4IodYzXWQAaHs=";
    yts = "sha256-PKqznEP1OQsvVYoOjuPVAKg1kwtj28LyF8KsIDAvZpM=";
    torrentdownloads = "sha256-PhoZcklB71ceO55Us0VEcIfohykUWiKSicRpG1ptA6Y=";
    torrentdownload = "sha256-xINxyAzCK/7u9Yt8Y4ByfuigSaqu+e1Z2dorL0OksLc=";
  };
  helper = pkgs.writeShellApplication {
    name = "media-stack";
    runtimeInputs = [ pkgs.python3 pkgs.systemd ];
    text = ''exec python3 ${../../scripts/media-stack.py} --config ${settings} "$@"'';
  };
  arrange = name: {
    enable = true;
    openFirewall = false;
    dataDir = "/var/lib/${name}";
    environmentFiles = [ "/run/media-stack/${name}.env" ];
    settings = {
      server = { port = cfg.ports.${name}; bindaddress = "127.0.0.1"; };
      auth = { method = "Forms"; required = "Enabled"; };
    };
  };
in {
  imports = [ ./media-vpn.nix ];
  options.services.media-stack = {
    enable = mkEnableOption "a local media stack";
    components = lib.genAttrs names (name: mkOption { type = types.bool; default = name != "lidarr"; });
    root = mkOption {
      type = types.str;
      default = "/srv/media-test";
      description = "Existing filesystem containing both downloads and library; never formatted.";
    };
    ports = lib.mapAttrs (_: port: mkOption { type = types.port; default = port; }) {
      jellyfin = 8096; seerr = 5055; radarr = 7878; sonarr = 8989; prowlarr = 9696; qbittorrent = 8080; bazarr = 6767; lidarr = 8686;
    };
    viewers = mkOption { type = types.listOf types.str; default = [ "viewer" "partner" ]; };
    viewerRenames = mkOption {
      type = types.attrsOf types.str;
      default = {};
      description = "Rename existing Jellyfin viewers in place, preserving IDs, passwords and history.";
    };
    indexers = mkOption {
      type = types.listOf (types.enum [ "internetarchive" "1337x" "nyaasi" "yts" "knaben" "torrentdownloads" "torrentdownload" ]);
      default = [];
      description = "Managed Prowlarr sources. Removed sources are disabled; other sources are untouched.";
    };
    automaticSearch = mkEnableOption "automatic searches and RSS monitoring for requested/monitored media";
    manualReleaseSelection = mkEnableOption "explicit release selection and approval before every download";
    releasePort = mkOption { type = types.port; default = 6768; description = "Loopback-only release broker."; };
    jellyfinEnhanced = mkEnableOption "Seerr discovery and requests in Jellyfin's web interface";
    personalHome = mkEnableOption "personal recommendations and favorites in Jellyfin web";
    playbackPolish = mkEnableOption "Intro Skipper and scheduled seek-preview generation";
    recommendationCount = mkOption { type = types.ints.between 1 30; default = 20; };
    recommendationSeedLimit = mkOption { type = types.ints.between 1 40; default = 30; };
    recommendationRefreshHours = mkOption { type = types.ints.positive; default = 24; };
    jellyfinLanInterfaces = mkOption {
      type = types.listOf types.str;
      default = [];
      description = "Interfaces allowing Jellyfin HTTP access from the LAN; empty keeps it on loopback.";
    };
    jellyfinDomain = mkOption {
      type = types.nullOr (types.strMatching "[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+");
      default = null;
      example = "media.example.org";
      description = "Public Jellyfin hostname served by Caddy with automatic HTTPS; enables remote access for managed accounts.";
    };
    subtitleLanguages = mkOption {
      type = types.listOf (types.enum [ "pb" "en" ]);
      default = [ "pb" "en" ];
      description = "Bazarr languages: pb is Brazilian Portuguese, en is English.";
    };
    libraryScanMinutes = mkOption {
      type = types.ints.positive;
      default = 2;
      description = "Jellyfin fallback scan interval when real-time file discovery misses an import.";
    };
    budgetGiB = mkOption { type = types.nullOr types.ints.positive; default = 10; description = "Soft budget, counting hardlinked files once; checked every 30 seconds. Null disables the budget, retaining the free-space reserve."; };
    maxSizeMBPerMinute = mkOption {
      type = types.nullOr types.ints.positive;
      default = 20;
      description = "Radarr/Sonarr maximum release size in MB per minute of runtime, for every quality. Null removes the size cap. Reconciled on every setup.";
    };
    allowAllQualities = mkEnableOption "all Radarr/Sonarr qualities, including existing request profiles";
    minFreeGiB = mkOption { type = types.ints.unsigned; default = 15; };
    downloadKiB = mkOption { type = types.ints.positive; default = 5120; };
    uploadKiB = mkOption { type = types.ints.positive; default = 512; };
    memoryHigh = mkOption { type = types.str; default = "3G"; };
    memoryMax = mkOption { type = types.str; default = "4G"; };
    cpuQuota = mkOption { type = types.str; default = "200%"; };
    cacheMiB = mkOption { type = types.ints.positive; default = 3072; description = "Private ephemeral Jellyfin cache; startup requires at least 2 GiB free."; };
    hardwareAcceleration = mkEnableOption "Jellyfin VA-API (requires a working render device)";
    renderDevice = mkOption { type = types.str; default = "/dev/dri/renderD128"; };
  };

  config = mkIf cfg.enable {
    assertions = [
      { assertion = cfg.jellyfinDomain == null || cfg.components.jellyfin;
        message = "A public Jellyfin domain requires Jellyfin to be enabled."; }
      { assertion = !cfg.components.lidarr || (cfg.manualReleaseSelection && cfg.components.prowlarr);
        message = "Music discovery requires manual release selection and Prowlarr."; }
      { assertion = !cfg.personalHome || cfg.manualReleaseSelection;
        message = "Personal discovery requires the manual release-selection integration."; }
      { assertion = !cfg.playbackPolish || cfg.components.jellyfin;
        message = "Playback polish requires Jellyfin."; }
      { assertion = lib.hasPrefix "/srv/" cfg.root && builtins.match "/srv/[A-Za-z0-9/_-]+" cfg.root != null && !(lib.hasInfix "/../" cfg.root);
        message = "media-stack.root must be a simple absolute path beneath /srv."; }
      { assertion = builtins.length (lib.unique (map (n: cfg.ports.${n}) enabled)) == builtins.length enabled;
        message = "Media stack web ports must be distinct."; }
      { assertion = builtins.all (n: builtins.match "[a-z][a-z0-9_-]*" n != null && n != "admin") cfg.viewers && builtins.length (lib.unique cfg.viewers) == builtins.length cfg.viewers;
        message = "Media viewer names must be unique lowercase names, excluding admin."; }
      { assertion = lib.all (old: old != "admin" && !(builtins.elem old cfg.viewers)) (builtins.attrNames cfg.viewerRenames)
          && lib.all (new: builtins.elem new cfg.viewers) (builtins.attrValues cfg.viewerRenames)
          && lib.unique (builtins.attrValues cfg.viewerRenames) == builtins.attrValues cfg.viewerRenames;
        message = "Viewer renames must map old non-admin names to distinct configured viewers."; }
      { assertion = cfg.cacheMiB >= 3072; message = "Jellyfin needs more than 2 GiB available in its cache at startup."; }
      { assertion = builtins.length (lib.unique cfg.indexers) == builtins.length cfg.indexers;
        message = "Media stack indexers must be unique."; }
      { assertion = !cfg.jellyfinEnhanced || (cfg.components.jellyfin && cfg.components.seerr);
        message = "Jellyfin Enhanced requires Jellyfin and Seerr."; }
      { assertion = !cfg.manualReleaseSelection || (cfg.jellyfinEnhanced && !cfg.automaticSearch && cfg.components.radarr && cfg.components.sonarr && cfg.components.qbittorrent && !(builtins.elem cfg.releasePort (map (n: cfg.ports.${n}) enabled)));
        message = "Manual selection needs Jellyfin Enhanced, Radarr, Sonarr and qBittorrent, automaticSearch disabled, and a distinct broker port."; }
      { assertion = cfg.subtitleLanguages != [] && lib.unique cfg.subtitleLanguages == cfg.subtitleLanguages;
        message = "Subtitle languages must be nonempty and unique."; }
    ];
    environment.systemPackages = [ helper ];
    environment.etc."media-stack.json".source = settings;
    users.groups.media = {};
    services.caddy = mkIf (cfg.jellyfinDomain != null) {
      enable = true;
      openFirewall = true;
      virtualHosts.${cfg.jellyfinDomain} = {
        # Jellyfin URLs can contain access tokens; omit request access logs.
        logFormat = null;
        extraConfig = ''
          reverse_proxy 127.0.0.1:${toString cfg.ports.jellyfin}
        '';
      };
    };
    networking.firewall.interfaces = mkIf cfg.components.jellyfin (lib.genAttrs cfg.jellyfinLanInterfaces (_: {
      allowedTCPPorts = [ cfg.ports.jellyfin ];
    }));
    users.users.jellyfin = mkIf cfg.components.jellyfin { extraGroups = [ "media" ]; };
    services.jellyfin = mkIf cfg.components.jellyfin {
      enable = true;
      package = mkIf cfg.manualReleaseSelection mediaJellyfin;
      openFirewall = false;
      hardwareAcceleration = mkIf cfg.hardwareAcceleration {
        enable = true;
        type = "vaapi";
        device = cfg.renderDevice;
      };
    };
    services.seerr = mkIf cfg.components.seerr ({ enable = true; openFirewall = false; port = cfg.ports.seerr;
      configDir = "/var/lib/seerr";
    } // lib.optionalAttrs (options.services.seerr ? stateRevision) { stateRevision = 1; });
    services.radarr = mkIf cfg.components.radarr ((arrange "radarr") // { group = "media"; });
    services.sonarr = mkIf cfg.components.sonarr ((arrange "sonarr") // { group = "media"; });
    services.lidarr = mkIf cfg.components.lidarr ((arrange "lidarr") // { group = "media"; });
    services.prowlarr = mkIf cfg.components.prowlarr (arrange "prowlarr");
    services.bazarr = mkIf cfg.components.bazarr {
      enable = true;
      group = "media";
      openFirewall = false;
      settings = {
        general = {
          ip = "127.0.0.1";
          port = cfg.ports.bazarr;
          use_radarr = cfg.components.radarr;
          use_sonarr = cfg.components.sonarr;
          use_embedded_subs = true;
          subfolder = "current";
          chmod_enabled = true;
          chmod = "0660";
          concurrent_jobs = 1;
        };
        auth = {
          type = "form";
          username = "admin";
          password._secret = "/var/lib/media-stack/bazarr-password";
          apikey._secret = "/var/lib/media-stack/bazarr-apikey";
        };
      } // lib.genAttrs (builtins.filter (n: cfg.components.${n}) [ "radarr" "sonarr" ]) (name: {
        ip = "127.0.0.1";
        port = cfg.ports.${name};
        apikey._secret = "/var/lib/media-stack/${name}-apikey";
      });
    };
    services.qbittorrent = mkIf cfg.components.qbittorrent {
      enable = true;
      group = "media";
      openFirewall = false;
      webuiPort = cfg.ports.qbittorrent;
      torrentingPort = 6881;
      # Seed runtime credentials without copying secrets into the Nix store.
      serverConfig = {};
      extraArgs = [ "--confirm-legal-notice" ];
    };
    systemd.tmpfiles.rules = [
      "d ${cfg.root} 0750 root media -"
      "d ${cfg.root}/downloads 2770 root media -"
      "d ${cfg.root}/downloads/movies 2770 root media -"
      "d ${cfg.root}/downloads/tv 2770 root media -"
      "d ${cfg.root}/library 2770 root media -"
      "d ${cfg.root}/library/movies 2770 root media -"
      "d ${cfg.root}/library/tv 2770 root media -"
    ] ++ lib.optional cfg.components.sonarr "d /var/lib/sonarr 0700 sonarr media -"
      ++ lib.optionals cfg.components.lidarr [
        "d ${cfg.root}/downloads/music 2770 root media -"
        "d ${cfg.root}/library/music 2770 root media -"
      ];
    systemd.slices.media-stack.sliceConfig = {
      MemoryHigh = cfg.memoryHigh;
      MemoryMax = cfg.memoryMax;
      CPUQuota = cfg.cpuQuota;
      IOWeight = 25;
    };
    systemd.services = lib.mkMerge [
      { caddy = mkIf (cfg.jellyfinDomain != null) {
          # Do not publish an unfinished Jellyfin setup wizard on first boot.
          requires = [ "media-stack-setup.service" ];
          after = [ "media-stack-setup.service" ];
        };
      }
      (lib.genAttrs enabled (name: {
        requires = [ "media-stack-prepare.service" ];
        after = [ "media-stack-prepare.service" ];
        unitConfig.RequiresMountsFor = [ cfg.root ];
        serviceConfig.Slice = "media-stack.slice";
      }))
      {
        media-stack-prepare = {
          description = "Prepare private media stack credentials";
          before = map (n: "${n}.service") enabled;
          after = [ "systemd-tmpfiles-setup.service" ];
          serviceConfig = {
            Type = "oneshot";
            RemainAfterExit = true;
            StateDirectory = "media-stack";
            StateDirectoryMode = "0700";
            RuntimeDirectory = "media-stack";
            RuntimeDirectoryMode = "0700";
            UMask = "0077";
            ExecStart = "${helper}/bin/media-stack prepare";
          };
          restartTriggers = [ settings ];
        };
        jellyfin = mkIf cfg.components.jellyfin {
          # Intro Skipper invokes ffmpeg/ffprobe directly, unlike Jellyfin's --ffmpeg option.
          path = lib.optionals cfg.playbackPolish [ pkgs.jellyfin-ffmpeg ];
          environment.MEDIA_RELEASE_PORT = toString cfg.releasePort;
          environment.MEDIA_PERSONAL_HOME = if cfg.personalHome then "1" else "0";
          environment.MEDIA_MUSIC = if cfg.components.lidarr then "1" else "0";
          environment.MEDIA_UI_REVISION = uiRevision;
          preStart = lib.mkBefore (''
            ${helper}/bin/media-stack seed jellyfin
          '' + (if cfg.jellyfinEnhanced then ''
            install -Dm644 ${enhanced}/Jellyfin.Plugin.JellyfinEnhanced.dll \
              /var/lib/jellyfin/plugins/JellyfinEnhanced/Jellyfin.Plugin.JellyfinEnhanced.dll
          '' else ''
            rm -f /var/lib/jellyfin/plugins/JellyfinEnhanced/Jellyfin.Plugin.JellyfinEnhanced.dll
          '') + (if cfg.playbackPolish then ''
            install -Dm644 ${introSkipper}/IntroSkipper.dll /var/lib/jellyfin/plugins/IntroSkipper/IntroSkipper.dll
          '' else ''
            rm -f /var/lib/jellyfin/plugins/IntroSkipper/IntroSkipper.dll
          '') + (if cfg.manualReleaseSelection then ''
            install -Dm644 ${releasePlugin}/MediaReleases.dll /var/lib/jellyfin/plugins/MediaReleases/MediaReleases.dll
          '' else ''
            rm -f /var/lib/jellyfin/plugins/MediaReleases/MediaReleases.dll
          ''));
          serviceConfig = {
            ReadOnlyPaths = [ "${cfg.root}/library" ];
            InaccessiblePaths = [ "${cfg.root}/downloads" ];
            # Only visible in this service's mount namespace. Cache loss is harmless.
            TemporaryFileSystem = [ "/var/cache/jellyfin:rw,size=${toString cfg.cacheMiB}M,mode=1777" ];
          };
        };
        seerr = mkIf cfg.components.seerr { environment.HOST = "127.0.0.1"; };
        radarr = mkIf cfg.components.radarr { serviceConfig.UMask = lib.mkForce "0007"; };
        sonarr = mkIf cfg.components.sonarr { serviceConfig.UMask = lib.mkForce "0007"; };
        lidarr = mkIf cfg.components.lidarr { serviceConfig.UMask = lib.mkForce "0007"; };
        bazarr = mkIf cfg.components.bazarr {
          serviceConfig = {
            UMask = "0007";
            InaccessiblePaths = [ "${cfg.root}/downloads" ];
          };
        };
        prowlarr = mkIf cfg.components.prowlarr {
          preStart = lib.concatStringsSep "\n" (lib.mapAttrsToList (name: file:
            "install -Dm644 ${file} /var/lib/prowlarr/Definitions/${name}.yml") definitions);
        };
        qbittorrent = mkIf cfg.components.qbittorrent {
          preStart = ''
            ${helper}/bin/media-stack seed qbittorrent
            ${helper}/bin/media-stack check-space
          '';
          serviceConfig = {
            UMask = "0007";
            LoadCredential = [ "qbittorrent:/var/lib/media-stack/qbittorrent.json" ];
            Restart = "on-failure";
            RestartSec = 60;
          };
        };
        media-stack-guard = mkIf cfg.components.qbittorrent {
          description = "Stop downloads when media budget or disk reserve is exhausted";
          after = [ "media-stack-prepare.service" ];
          serviceConfig = {
            Type = "oneshot";
            ExecStart = "${helper}/bin/media-stack guard";
          };
        };
        media-stack-setup = {
          description = "Connect local media services and create viewing accounts";
          wantedBy = [ "multi-user.target" ];
          requires = map (n: "${n}.service") enabled;
          after = map (n: "${n}.service") enabled;
          serviceConfig = {
            Type = "oneshot";
            RemainAfterExit = true;
            TimeoutStartSec = "15min";
            UMask = "0077";
            ExecStart = "${helper}/bin/media-stack setup";
          };
        };
        media-releases = mkIf cfg.manualReleaseSelection {
          description = "Explicit media release selection and approval broker";
          wantedBy = [ "multi-user.target" ];
          requires = [ "media-stack-setup.service" ];
          after = [ "media-stack-setup.service" ];
          serviceConfig = {
            ExecStart = "${pkgs.python3}/bin/python3 ${releaseScripts}/media-releases.py";
            Restart = "on-failure";
            UMask = "0077";
            Slice = "media-stack.slice";
            ProtectSystem = "strict";
            ProtectHome = true;
            PrivateTmp = true;
            NoNewPrivileges = true;
            ReadWritePaths = [ "/var/lib/media-stack" ];
            RestrictAddressFamilies = [ "AF_INET" "AF_UNIX" ];
          };
        };
      }
    ];
    systemd.timers.media-stack-guard = mkIf cfg.components.qbittorrent {
      wantedBy = [ "timers.target" ];
      timerConfig = { OnBootSec = "1m"; OnUnitActiveSec = "30s"; AccuracySec = "5s"; };
    };
  };
}
