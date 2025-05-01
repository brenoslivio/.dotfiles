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
    (importModule "fish")
    (importModule "hypr")
    (importModule "rofi")
    (importModule "waybar")
    (importModule "wlogout")
  ];

  home.username = "brenoslivio";
  home.homeDirectory = "/home/brenoslivio";

  home.stateVersion = "24.11";

  home.packages = [
    pkgs.adwaita-qt
    pkgs.adwaita-qt6
    # # It is sometimes useful to fine-tune packages, for example, by applying
    # # overrides. You can do that directly here, just don't forget the
    # # parentheses. Maybe you want to install Nerd Fonts with a limited number of
    # # fonts?
    # (pkgs.nerdfonts.override { fonts = [ "FantasqueSansMono" ]; })

    # # You can also create simple shell scripts directly inside your
    # # configuration. For example, this adds a command 'my-hello' to your
    # # environment:
    # (pkgs.writeShellScriptBin "my-hello" ''
    #   echo "Hello, ${config.home.username}!"
    # '')
  ];

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
      gpg.format = "ssh";
      user.signingKey = "~/.ssh/id_ed25519.pub"; # example
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
    # name = "Bibata-Modern-Ice";
    # package = pkgs.bibata-cursors;
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

  qt = {
    enable = true;
    platformTheme.name = "qtct";
    style = {
      name = "adwaita-dark";
      package = pkgs.adwaita-qt;
    };
  };

  # Let Home Manager install and manage itself.
  programs.home-manager = {
    enable = true;
  };

  dconf.settings = {
    "org/gnome/desktop/interface" = {
      color-scheme = "prefer-dark";
    };
  };
}
