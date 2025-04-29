# Edit this configuration file to define what should be installed on
# your system.  Help is available in the configuration.nix(5) man page
# and in the NixOS manual (accessible by running ‘nixos-help’).

{ config, pkgs, ... }:

{
  imports =
    [ # Include the results of the hardware scan.
      ./hardware-configuration.nix
    ];

  # Bootloader.
  boot.loader.systemd-boot.enable = true;
  boot.loader.efi.canTouchEfiVariables = true;

  security.polkit.enable = true;

  boot.initrd.luks.devices."luks-4de7db73-acb9-40bd-8c1c-4b09c7d7f3be".device = "/dev/disk/by-uuid/4de7db73-acb9-40bd-8c1c-4b09c7d7f3be";
  networking.hostName = "ahimsa"; # Define your hostname.
  # networking.wireless.enable = true;  # Enables wireless support via wpa_supplicant.

  # Configure network proxy if necessary
  # networking.proxy.default = "http://user:password@proxy:port/";
  # networking.proxy.noProxy = "127.0.0.1,localhost,internal.domain";

  # Enable networking
  networking.networkmanager.enable = true;

  # Set your time zone.
  time.timeZone = "America/Sao_Paulo";

  # Select internationalisation properties.
  i18n.defaultLocale = "en_US.UTF-8";

  i18n.extraLocaleSettings = {
    LC_ADDRESS = "pt_BR.UTF-8";
    LC_IDENTIFICATION = "pt_BR.UTF-8";
    LC_MEASUREMENT = "pt_BR.UTF-8";
    LC_MONETARY = "pt_BR.UTF-8";
    LC_NAME = "pt_BR.UTF-8";
    LC_NUMERIC = "pt_BR.UTF-8";
    LC_PAPER = "pt_BR.UTF-8";
    LC_TELEPHONE = "pt_BR.UTF-8";
    LC_TIME = "pt_BR.UTF-8";
  };

  # Enable the X11 windowing system.
  # You can disable this if you're only using the Wayland session.
  services.xserver.enable = true;

  programs.hyprland = {
    enable = true;
    xwayland.enable = true;
  };

  services.displayManager.sddm.enable = true;
  security.pam.services.sddm.enableGnomeKeyring = true;

  environment.sessionVariables = {
    NIXOS_OZONE_WL = "1";
  };

  # Configure keymap in X11
  services.xserver.xkb = {
    layout = "br";
    variant = "thinkpad";
  };

  # Configure console keymap
  console.keyMap = "br-abnt2";

  # Enable CUPS to print documents.
  services.printing.enable = true;

  # Enable sound with pipewire.
  hardware.pulseaudio.enable = false;
  security.rtkit.enable = true;
  services.pipewire = {
    enable = true;
    alsa.enable = true;
    alsa.support32Bit = true;
    pulse.enable = true;
    # If you want to use JACK applications, uncomment this
    #jack.enable = true;

    # use the example session manager (no others are packaged yet so this is enabled by default,
    # no need to redefine it in your config for now)
    #media-session.enable = true;
  };

  # Enable touchpad support (enabled default in most desktopManager).
  # services.xserver.libinput.enable = true;

  # Define a user account. Don't forget to set a password with ‘passwd’.
  users.users.brenoslivio = {
    isNormalUser = true;
    description = "Breno Livio";
    extraGroups = [ "networkmanager" "wheel" ];
    packages = with pkgs; [
      #kdePackages.kate
      #thunderbird      
    ];
  };

  # Allow unfree packages
  nixpkgs.config.allowUnfree = true;

  # List packages installed in system profile. To search, run:
  # $ nix search wget
  environment.systemPackages = with pkgs; [
    wget
    btop
    pavucontrol
    fortune
    cowsay
    lolcat
    git
    nemo
    file-roller
    firefox
    thunderbird
    okular
    libsForQt5.qt5ct
    qt6Packages.qt6ct
    kdePackages.gwenview
    kdePackages.kcalc
    kdePackages.kate
    spotify
    vlc
    vscode
    telegram-desktop
    stremio
    dropbox
    obs-studio
    gimp
    popsicle
    alacritty
    kitty
    galaxy-buds-client
    fastfetch
    nerdfetch
    figlet
    devenv
    pandoc
    texlive.combined.scheme-full
    libreoffice-qt6-fresh
    hunspell
    hunspellDicts.pt_BR
    distrobox
    mpvpaper
    waybar
    (pkgs.waybar.overrideAttrs (oldAttrs: {
        mesonFlags = oldAttrs.mesonFlags ++ [ "-Dexperimental=true" ];
      })
    )
    hyprshot
    swaynotificationcenter
    libnotify
    hyprlock
    hyprcursor
    clipse
    wl-clipboard
    wlogout
    rofi-wayland
    networkmanagerapplet
    blueman
    playerctl
    lxqt.lxqt-policykit
    home-manager
  ];

  services.gvfs.enable = true;

  services.flatpak.enable = true;

  programs.kdeconnect.enable = true;

  systemd.services.flatpak-repo = {
    wantedBy = [ "multi-user.target" ];
    path = [ pkgs.flatpak ];
    script = ''
      flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo

      flatpak install -y flathub md.obsidian.Obsidian
    '';
  };

  virtualisation.podman = {
    enable = true;
    dockerCompat = true;
  };

  virtualisation.docker.rootless = {
    enable = true;
    setSocketVariable = true;
  };

  xdg.portal = {
    enable = true;
    extraPortals = with pkgs; [
      xdg-desktop-portal-wlr
      xdg-desktop-portal-kde
      xdg-desktop-portal-gtk
    ];
  };

  hardware = {
    bluetooth = {
        enable = true;
        settings.General.Experimental = true;
    };
  };

  programs.fish = {
    enable = true;
    interactiveShellInit = ''
      set fish_greeting # Disable greeting
      figlet $hostname | cowsay -n | lolcat
    '';
  };

  programs.starship.enable = true;

  programs.bash = {
    interactiveShellInit = ''
      if [[ $(${pkgs.procps}/bin/ps --no-header --pid=$PPID --format=comm) != "fish" && -z ''${BASH_EXECUTION_STRING} ]]
      then
        shopt -q login_shell && LOGIN_OPTION='--login' || LOGIN_OPTION=""
        exec ${pkgs.fish}/bin/fish $LOGIN_OPTION
      fi
    '';
  };

  # Automatic Garbage Collection
  nix.gc = {
    automatic = true;
    dates = "daily";
    options = "--delete-older-than 10d";
  };

  nix.settings = {
    auto-optimise-store = true;
    experimental-features = [ "nix-command" "flakes" ];
  };

  # Auto system update
  system.autoUpgrade = {
    enable = true;
    dates = "weekly";
  };

  fonts.packages = with pkgs; [
    inter
    (nerdfonts.override { fonts = [ "FiraCode" "DroidSansMono" ]; })
  ];

  # Some programs need SUID wrappers, can be configured further or are
  # started in user sessions.
  # programs.mtr.enable = true;
  # programs.gnupg.agent = {
  #   enable = true;
  #   enableSSHSupport = true;
  # };

  # List services that you want to enable:

  # Enable the OpenSSH daemon.
  # services.openssh.enable = true;

  # Open ports in the firewall.
  networking.firewall = {
    enable = true;
    allowedTCPPortRanges = [ { from = 1714; to = 1764; } ]; # kde connect
    allowedUDPPortRanges = [ { from = 1714; to = 1764; } ]; # kde connect
  };  

  system.stateVersion = "24.11"; # Did you read the comment?
  
}
