{ config, inputs, lib, pkgs, primaryUser, primaryUserDescription, ... }:

let
  # Temporary stable exception until Brave's restoration reaches unstable.
  bravePackage = (import inputs.nixpkgs-stable {
    system = pkgs.stdenv.hostPlatform.system;
    config.allowUnfree = true;
  }).brave;
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
  flakeUpdateCheck = pkgs.writeShellApplication {
    name = "flake-update-check";
    runtimeInputs = with pkgs; [ coreutils git libnotify nix ];
    text = builtins.readFile ../notify-flake-updates.sh;
  };
in
{
  imports = [
    ./assets/assets.nix
    ./cava/cava.nix
    ./fastfetch/fastfetch.nix
    ./git/git.nix
    ./hypr/hypr.nix
    ./kdeconnect/kdeconnect.nix
    ./nemo/nemo.nix
    ./rofi/rofi.nix
    ./shell/shell.nix
    ./spicetify/spicetify.nix
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
    hyprsunset
    socat

    # Terminal apps
    git
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
    bravePackage
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
    waybar
    swaynotificationcenter
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
      cp ${bravePackage}/share/applications/com.brave.Browser.desktop "$out"
      chmod u+w "$out"
      substituteInPlace "$out" \
        --replace-fail 'Exec=${bravePackage}/bin/brave' 'Exec=${bravePackage}/bin/brave --ozone-platform=wayland' \
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
      Description = "Weekly notification to warn about Flake updates";
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
      Description = "Weekly notification to warn about Flake updates";
    };
    Timer = {
      OnCalendar = "Fri 21:00:00";
      Persistent = true;
    };
    Install = {
      WantedBy = [ "timers.target" ];
    };
  };

  systemd.user.services.hyprsunset = {
    Install = {
      WantedBy = [ "wayland-session@hyprland.desktop.target" ];
    };
    Service = {
      ExecStart = "${pkgs.bash}/bin/bash ${./hypr/hyprsunset.sh}";
      Restart = "always";
      RestartSec = 5;
      RuntimeMaxSec = 3600;
      Type = "simple";
    };
    Unit = {
      Description = "Run hyprsunset script 1h";
      After = [ "wayland-session-waitenv.service" ];
      PartOf = [ "wayland-session@hyprland.desktop.target" ];
    };
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
