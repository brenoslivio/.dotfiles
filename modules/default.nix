{ config, lib, pkgs, primaryUser, primaryUserDescription, ... }:

let
  # Hollywood only plays a soundtrack. Its MPlayer's old DVD navigation
  # library conflicts with FFmpeg's newer one in this Nixpkgs revision.
  hollywoodPackage = pkgs.hollywood.override {
    mplayer = pkgs.mplayer.override { dvdnavSupport = false; };
  };
  # Preserve existing desktop associations when Home Manager takes ownership.
  desktopDefaults = {
    "text/html" = [ "com.brave.Browser.desktop" ];
    "x-scheme-handler/http" = [ "com.brave.Browser.desktop" ];
    "x-scheme-handler/https" = [ "com.brave.Browser.desktop" ];
    "x-scheme-handler/about" = [ "com.brave.Browser.desktop" ];
    "x-scheme-handler/unknown" = [ "com.brave.Browser.desktop" ];
    "x-scheme-handler/tg" = [ "org.telegram.desktop.desktop" ];
    "x-scheme-handler/tonsite" = [ "org.telegram.desktop.desktop" ];
    "x-scheme-handler/codex" = [ "chatgpt.desktop" ];
    "video/mp4" = [ "vlc.desktop" ];
    "image/png" = [ "org.kde.gwenview.desktop" ];
    "application/pdf" = [ "okularApplication_pdf.desktop" ];
    "application/x-shellscript" = [ "org.kde.kate.desktop" ];
    "text/css" = [ "org.kde.kate.desktop" ];
    "text/x-csrc" = [ "org.kde.kate.desktop" ];
    "text/plain" = [ "org.kde.kate.desktop" ];
  };
  updater = import ../scripts/updater-package.nix { inherit pkgs; };
  flakeUpdateCheck = pkgs.writeShellApplication {
    name = "flake-update-check";
    runtimeInputs = [ updater ];
    text = builtins.readFile ../notify-flake-updates.sh;
  };
in
{
  imports = [
    ./assets/assets.nix
    ./cava/cava.nix
    ./desktop-theme/desktop-theme.nix
    ./fastfetch/fastfetch.nix
    ./git/git.nix
    ./hypr/hypr.nix
    ./kdeconnect/kdeconnect.nix
    ./nemo/nemo.nix
    ./rofi/rofi.nix
    ./shell/shell.nix
    ./swaync/swaync.nix
    ./waybar/waybar.nix
    ./wayland_flags/wayland_flags.nix
    ./wlogout/wlogout.nix
  ];

  home.username = primaryUser;
  home.homeDirectory = "/home/${primaryUser}";

  home.stateVersion = "24.11";

  xdg.mimeApps = {
    enable = true;
    defaultApplications = desktopDefaults;
    associations.added = desktopDefaults // {
      "application/x-zerosize" = [ "org.kde.kate.desktop" ];
    };
  };

  # Preserve host ownership for bind mounts used by rootless Podman and dockerCompat.
  xdg.configFile."containers/containers.conf".text = ''
    [containers]
    userns = "keep-id"
  '';

  home.packages = with pkgs; [
    # Qt packages and themes
    libsForQt5.qt5ct
    qt6Packages.qt6ct
    adwaita-qt
    adwaita-qt6

    # Documents and typesetting
    pandoc
    texliveFull
    typst
    tinymist
    
    # Hypr ecosystem
    hyprpaper
    hyprshot
    hyprlock
    hyprpicker
    hyprcursor
    socat

    # Terminal apps
    git
    gh
    codex
    openssl
    wget
    btop
    fortune
    cowsay
    lolcat
    figlet
    cava
    rclone
    fastfetch
    pipes
    hollywoodPackage
    distrobox

    # File manager
    nemo
    file-roller

    # GUI software
    brave
    qbittorrent
    firefox
    zoom-us
    xournalpp
    obsidian
    thunderbird
    telegram-desktop
    stremio-linux-shell
    dropbox
    obs-studio
    gimp
    popsicle
    vscode
    vlc
    jellyfin-desktop
    galaxy-buds-client
    libreoffice-qt-stable
    hunspell
    hunspellDicts.pt_BR
    kdePackages.gwenview
    kdePackages.okular
    kdePackages.kcalc
    kdePackages.kate
    gnome-clocks
    proton-vpn
    authenticator

    # Devices and audio
    android-tools # adb and fastboot for Android/Chromecast management
    pavucontrol
    networkmanagerapplet
    playerctl
    brightnessctl

    # Desktop aux
    libnotify
    clipse
    wl-clipboard
    wlogout
    
    # Fonts
    inter
    corefonts
    vista-fonts
    nerd-fonts.fira-code
    nerd-fonts.droid-sans-mono

    # # You can also create simple shell scripts directly inside your
    # # configuration. For example, this adds a command 'my-hello' to your
    # # environment:
    # (pkgs.writeShellScriptBin "my-hello" ''
    #   echo "Hello, ${config.home.username}!"
    # '')
  ];

  fonts.fontconfig.enable = true;

  home.file = { 
    # # You can also set the file content immediately.
    # ".gradle/gradle.properties".text = ''
    #   org.gradle.console=verbose
    #   org.gradle.daemon.idletimeout=3600000
    # '';
  };

  # Native Wayland avoids the sluggish accelerated rendering seen under XWayland.
  xdg.dataFile."applications/com.brave.Browser.desktop" = {
    force = true;
    source = pkgs.runCommand "brave-wayland.desktop" {
      nativeBuildInputs = [ pkgs.desktop-file-utils ];
    } ''
      cp ${pkgs.brave}/share/applications/com.brave.Browser.desktop "$out"
      chmod u+w "$out"
      substituteInPlace "$out" \
        --replace-fail 'Exec=${pkgs.brave}/bin/brave' 'Exec=${pkgs.brave}/bin/brave --ozone-platform=wayland' \
        --replace-fail 'NoDisplay=true' 'NoDisplay=false'
      desktop-file-validate "$out"
    '';
  };

  xdg.dataFile."applications/brave-browser.desktop" = {
    force = true;
    text = ''
      [Desktop Entry]
      Type=Application
      Name=Brave Web Browser
      Hidden=true
    '';
  };

  # Home Manager can also manage your environment variables through
  # 'home.sessionVariables'. These will be explicitly sourced when using a
  # shell provided by Home Manager. If you don't want to manage your shell
  # through Home Manager then you have to manually source 'hm-session-vars.sh'
  # located at either
  #
  #  ~/.nix-profile/etc/profile.d/hm-session-vars.sh
  #
  # or
  #
  #  ~/.local/state/nix/profiles/profile/etc/profile.d/hm-session-vars.sh
  #
  # or
  #
  #  /etc/profiles/per-user/brenoslivio/etc/profile.d/hm-session-vars.sh
  #
  home.sessionVariables.DOTFILES_REPO = "${config.home.homeDirectory}/.dotfiles";
  home.sessionVariables.BROWSER = "brave";

  home.pointerCursor = {
    enable = true;
    gtk.enable = true;
    x11.enable = true;
    name = "oreo_purple_cursors";
    package = pkgs.oreo-cursors-plus;
    size = 30;
  };

  gtk = {
    enable = true;
    gtk4.theme = config.gtk.theme;
    theme = {
      package = pkgs.orchis-theme;
      name = "Orchis-Purple-Dark";
    };

    iconTheme = {
      package = pkgs.papirus-icon-theme.override { color = "magenta"; };
      name = "Papirus-Dark";
    };

    font = {
      name = "Inter";
      size = 12;
    };
  };

  dconf.settings = {
    "org/gnome/desktop/interface" = {
      color-scheme = "prefer-dark";
    };
  };

  qt = {
    enable = true;
    platformTheme.name = "qtct";
    style = {
      name = "adwaita-dark";
      package = pkgs.adwaita-qt;
    };
  };

  systemd.user.services.flakeUpdate = {
    Unit = {
      Description = "Notify about CI-tested NixOS updates";
    };
    Service = {
      Type = "oneshot";
      ExecStart = lib.getExe flakeUpdateCheck;
      StandardOutput = "journal+console";
      StandardError = "journal+console";
    };
  };

  systemd.user.timers.flakeUpdate = {
    Unit = {
      Description = "Notify about CI-tested NixOS updates";
    };
    Timer = {
      OnCalendar = "*-*-* 09:15:00 America/Sao_Paulo";
      RandomizedDelaySec = "10m";
      Persistent = true;
    };
    Install = {
      WantedBy = [ "timers.target" ];
    };
  };

  systemd.user.services.weeklyUpdate = {
    Unit = {
      Description = "Check the Friday flake proposal and tested desktop update";
      PartOf = [ "graphical-session.target" ];
    };
    Service = {
      Type = "oneshot";
      ExecStart = "${updater}/bin/dotfiles-update weekly-notify";
      TimeoutStartSec = "4min";
      Restart = "on-failure";
      RestartSec = "5min";
    };
  };

  systemd.user.timers.weeklyUpdate = {
    Unit = {
      Description = "Follow the Friday update through Sunday evening";
      PartOf = [ "graphical-session.target" ];
    };
    Timer = {
      OnCalendar = [
        "Fri *-*-* 21..23:00/5:00 America/Sao_Paulo"
        "Sat *-*-* *:00/5:00 America/Sao_Paulo"
        "Sun *-*-* 00..20:00/5:00 America/Sao_Paulo"
        "Sun *-*-* 21:00:00 America/Sao_Paulo"
      ];
      AccuracySec = "1s";
      Persistent = true;
    };
    Install.WantedBy = [ "graphical-session.target" ];
  };

  # systemd.user.services.rclone = {
  #   Unit = {
  #     Description = "Sync local folder to remote storage";
  #   };
  #   Service = {
  #     Type = "oneshot";
  #     ExecStart = "${pkgs.rclone}/bin/rclone sync ${config.home.homeDirectory}/Documents/Ikiru remote:Ikiru"; 
  #     StandardOutput = "journal+console";
  #     StandardError = "journal+console";
  #   };
  # };

  # systemd.user.timers.rclone = {
  #   Unit = {
  #     Description = "Timer for syncing local folder to remote storage every 10 minutes";
  #   };
  #   Timer = {
  #     OnCalendar = "*:0/10:00";  # Every 10 minutes
  #     Persistent = true;
  #   };
  #   Install = {
  #     WantedBy = [ "timers.target" ];
  #   };
  # };

  # Let Home Manager install and manage itself.
  programs.home-manager = {
    enable = true;
  };
}
