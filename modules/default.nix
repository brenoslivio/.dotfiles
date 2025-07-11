{ config, pkgs, ...}@extras:

let
  dotfiles = "/home/brenoslivio/.dotfiles";
  outOfStore = config.lib.file.mkOutOfStoreSymlink;

  importModule = name: import "${dotfiles}/modules/${name}/${name}.nix" {
    inherit config pkgs dotfiles outOfStore extras;
  };
in
{
  imports = [
    (importModule "cava")
    (importModule "fastfetch")
    (importModule "git")
    (importModule "hypr")
    (importModule "kdeconnect")
    (importModule "nemo")
    (importModule "niri")
    (importModule "rofi")
    (importModule "shell")
    (importModule "spicetify")
    (importModule "waybar")
    (importModule "wayland_flags")
    (importModule "wlogout")
  ];

  home.username = "brenoslivio";
  home.homeDirectory = "/home/brenoslivio";

  home.stateVersion = "24.11";

  # Allow unfree packages
  nixpkgs.config.allowUnfree = true;

  home.packages = with pkgs; [
    # Qt packages and themes
    libsForQt5.qt5ct
    qt6Packages.qt6ct
    adwaita-qt
    adwaita-qt6

    # Latex things
    pandoc
    texlive.combined.scheme-full
    
    # Hypr ecosystem
    hyprpaper
    hyprshot
    hyprlock
    hyprpicker
    hyprcursor
    hyprsunset

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
    hollywood
    distrobox

    # File manager
    nemo
    file-roller

    # GUI software
    brave
    firefox
    zoom-us
    xournalpp
    obsidian
    thunderbird
    telegram-desktop
    stremio
    dropbox
    obs-studio
    gimp
    popsicle
    vscode
    vlc
    galaxy-buds-client
    libreoffice-qt6-fresh
    hunspell
    hunspellDicts.pt_BR
    kdePackages.gwenview
    kdePackages.okular
    kdePackages.kcalc
    kdePackages.kate
    protonvpn-gui
    authenticator

    # Devices and audio
    pavucontrol
    networkmanagerapplet
    blueman
    playerctl

    # Desktop aux
    waybar
    xwayland-satellite
    swaynotificationcenter
    libnotify
    clipse
    wl-clipboard
    wlogout
    
    # Fonts
    inter
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
  home.sessionVariables = {
    # EDITOR = "emacs";
  };

  home.pointerCursor = {
    gtk.enable = true;
    x11.enable = true;
    name = "oreo_purple_cursors";
    package = pkgs.oreo-cursors-plus;
    size = 30;
  };

  gtk = {
    enable = true;
    theme = {
      package = pkgs.orchis-theme;
      name = "Orchis-Purple-Dark";
    };

    iconTheme = {
      package = pkgs.papirus-icon-theme;
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
      ExecStart = "${pkgs.bash}/bin/bash ${dotfiles}/notify-flake-updates.sh"; 
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
      WantedBy = [ "default.target" ];
    };
    Service = {
      ExecStart = "${pkgs.bash}/bin/bash ${dotfiles}/modules/hypr/hyprsunset.sh";
      Restart = "always";
      RuntimeMaxSec = 3600;
      Type = "simple";
    };
    Unit = {
      Description = "Run hyprsunset script 1h";
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
