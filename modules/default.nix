{ config, pkgs, ... }:

let
  dotfiles = "/home/brenoslivio/.dotfiles";
  outOfStore = config.lib.file.mkOutOfStoreSymlink;
  
  importModule = name: import "${dotfiles}/modules/${name}/${name}.nix" {
    inherit config pkgs dotfiles outOfStore;
  };
in
{
  imports = [
    (importModule "cava")
    (importModule "fish")
    (importModule "hypr")
    (importModule "rofi")
    (importModule "waybar")
    (importModule "wlogout")
  ];

  home.username = "brenoslivio";
  home.homeDirectory = "/home/brenoslivio";

  home.stateVersion = "24.11";

  # Allow unfree packages
  nixpkgs.config.allowUnfree = true;

  home.packages = with pkgs; [
    libsForQt5.qt5ct
    qt6Packages.qt6ct
    adwaita-qt
    adwaita-qt6

    pandoc
    texlive.combined.scheme-full
    
    hyprpaper
    hyprshot
    hyprlock
    hyprcursor

    git
    wget
    btop
    fortune
    cowsay
    lolcat
    figlet
    cava
    fastfetch
    nerdfetch
    distrobox

    nemo
    file-roller

    firefox
    thunderbird
    telegram-desktop
    stremio
    dropbox
    obs-studio
    gimp
    popsicle
    vscode
    ncspot
    okular
    vlc
    galaxy-buds-client
    libreoffice-qt6-fresh
    hunspell
    hunspellDicts.pt_BR
    
    kdePackages.gwenview
    kdePackages.kcalc
    kdePackages.kate

    pavucontrol
    networkmanagerapplet
    blueman
    playerctl

    waybar
    rofi-wayland
    swaynotificationcenter
    libnotify
    clipse
    wl-clipboard
    wlogout

    # # It is sometimes useful to fine-tune packages, for example, by applying
    # # overrides. You can do that directly here, just don't forget the
    # # parentheses. Maybe you want to install Nerd Fonts with a limited number of
    # # fonts?
    # (pkgs.nerdfonts.override { fonts = [ "FantasqueSansMono" ]; })

    inter
    (nerdfonts.override { fonts = [ "FiraCode" "DroidSansMono" ]; })

    # # You can also create simple shell scripts directly inside your
    # # configuration. For example, this adds a command 'my-hello' to your
    # # environment:
    # (pkgs.writeShellScriptBin "my-hello" ''
    #   echo "Hello, ${config.home.username}!"
    # '')
  ];

  fonts.fontconfig.enable = true;

  # Home Manager is pretty good at managing dotfiles. The primary way to manage
  # plain files is through 'home.file'.
  home.file = {
    # # Building this configuration will create a copy of 'dotfiles/screenrc' in
    # # the Nix store. Activating the configuration will then make '~/.screenrc' a
    # # symlink to the Nix store copy.
    # ".screenrc".source = dotfiles/screenrc;

    # Specific configs

    ## Nemo file-roller
    ".local/share/nemo/actions".source = outOfStore "${dotfiles}/config_files/nemo";

    # Wayland flags
    ".config/code-flags.conf".source = outOfStore "${dotfiles}/config_files/wayland_flags/code-flags.conf";

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

  programs.git = {
    enable = true;
    userName = "brenoslivio";
    userEmail = "brenoslivio@pm.me";
    extraConfig = {
      init.defaultBranch = "main";
      safe.directory = "/home/brenoslivio/.dotfiles";
      gpg.format = "ssh";
      user.signingKey = "/home/brenoslivio/.ssh/id_ed25519.pub";
      commit.gpgSign = true;
    };
  };

  services.kdeconnect = {
    enable = true;
    package = pkgs.kdePackages.kdeconnect-kde;
    indicator = true;
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
      Description = "Daily notification to warn about Flake updates";
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
      Description = "Daily notification to warn about Flake updates";
    };
    Timer = {
      OnCalendar = "21:00:00";
      Persistent = true;
    };
    Install = {
      WantedBy = [ "timers.target" ];
    };
  };

  # Let Home Manager install and manage itself.
  programs.home-manager = {
    enable = true;
  };
}
