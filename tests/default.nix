{ pkgs, home, vmModules, vmSpecialArgs, vps, vpsModules, vpsSpecialArgs }:
let
  python = pkgs.python3.withPackages (p: [ p.json5 ]);
in {
  vps-config = vps.pkgs.runCommand "vps-config-checks" {
    nativeBuildInputs = [ vps.config.services.caddy.package vps.pkgs.python3 ];
  } ''
    export XDG_DATA_HOME="$TMPDIR/data"
    export XDG_CONFIG_HOME="$TMPDIR/config"
    caddy validate --adapter caddyfile --config ${vps.config.services.caddy.configFile}
    python - <<'PY'
    import json
    cfg = json.loads(${builtins.toJSON (builtins.toJSON {
      ports = vps.config.networking.firewall.allowedTCPPorts;
      ssh = vps.config.services.openssh.settings;
      interfaces = vps.config.services.media-stack.jellyfinLanInterfaces;
      requires = vps.config.systemd.services.caddy.requires;
    })})
    assert sorted(cfg['ports']) == [22, 80, 443]
    assert not cfg['interfaces']
    assert not cfg['ssh']['PasswordAuthentication']
    assert not cfg['ssh']['KbdInteractiveAuthentication']
    assert cfg['ssh']['PermitRootLogin'] == 'prohibit-password'
    assert 'media-stack-setup.service' in cfg['requires']
    PY
    touch "$out"
  '';
  vps-vm = import ./vps-vm.nix { inherit vps vpsModules vpsSpecialArgs; };
  generated-config = pkgs.runCommand "generated-config-checks" {
    nativeBuildInputs = [ python pkgs.bash pkgs.fish pkgs.lua pkgs.desktop-file-utils pkgs.hyprland ];
  } ''
    export HOME="$TMPDIR/home"
    mkdir -p "$HOME"
    cp -rs ${home.config.home-files}/. "$HOME/"
    export XDG_RUNTIME_DIR="$TMPDIR/runtime"
    mkdir -m700 "$XDG_RUNTIME_DIR"
    python ${./generated_config.py} ${home.config.home-files}
    fish --no-config --no-execute ${home.config.home-files}/.config/fish/config.fish
    luac -p ${home.config.home-files}/.config/hypr/hyprland.lua
    Hyprland --verify-config --config ${home.config.home-files}/.config/hypr/hyprland.lua
    touch "$out"
  '';

  updater = pkgs.runCommand "updater-checks" {
    nativeBuildInputs = [ pkgs.python3 pkgs.git pkgs.bash pkgs.shellcheck pkgs.actionlint ];
  } ''
    cp -R ${../scripts} scripts
    cp -R ${./.} tests
    cp -R ${../.github} .github
    chmod -R u+w scripts tests .github
    export HOME="$TMPDIR/home"
    mkdir -p "$HOME"
    python -m unittest discover -s tests -p 'test_*.py' -v
    shellcheck scripts/*.sh
    actionlint -shellcheck="" .github/workflows/*.yml
    touch "$out"
  '';

  ahimsa-vm = pkgs.testers.runNixOSTest {
    name = "ahimsa-smoke";
    globalTimeout = 900;
    node.pkgs = pkgs.lib.mkForce null;
    node.specialArgs = vmSpecialArgs;
    nodes.machine = { lib, ... }: {
      imports = vmModules;
      # No physical host module: the test framework supplies virtual disks/boot.
      networking.hostName = "ahimsa";
      boot.loader.systemd-boot.enable = lib.mkForce false;
      boot.loader.efi.canTouchEfiVariables = lib.mkForce false;
      virtualisation = { memorySize = 4096; cores = 2; };
      users.users.brenoslivio.password = "test-only";
      # Console test has no graphical session or personal network credentials.
      services.displayManager.sddm.enable = lib.mkForce false;
      services.xserver.enable = lib.mkForce false;
      systemd.services.NetworkManager-wait-online.enable = lib.mkForce false;
      networking.networkmanager.ensureProfiles.profiles = lib.mkForce {};
      nix.gc.automatic = lib.mkForce false;
      home-manager.users.brenoslivio.systemd.user.timers.flakeUpdate.Install.WantedBy = lib.mkForce [];
    };
    testScript = ''
      start_all()
      machine.wait_for_unit("multi-user.target")
      machine.wait_for_unit("home-manager-brenoslivio.service")
      machine.wait_for_unit("NetworkManager.service")
      machine.wait_for_unit("dbus.service")
      machine.wait_for_unit("cups.socket")
      machine.wait_for_unit("getty@tty1.service")
      machine.wait_until_tty_matches("1", "login: ")
      machine.send_chars("brenoslivio\n")
      machine.wait_until_tty_matches("1", "Password:")
      machine.send_chars("test-only\n")
      machine.wait_until_succeeds("pgrep -u brenoslivio fish")
      uid = machine.succeed("id -u brenoslivio").strip()
      machine.wait_for_unit(f"user@{uid}.service")
      machine.succeed("test -f /home/brenoslivio/.config/waybar/config.jsonc")
      machine.succeed("test -f /home/brenoslivio/.config/hypr/hyprland.lua")
      machine.succeed("test -f /home/brenoslivio/.config/containers/containers.conf")
      machine.succeed("su - brenoslivio -c 'git --version'")
      machine.succeed("su - brenoslivio -c 'podman info --format json'")
      machine.succeed("su - brenoslivio -c 'dotfiles-update status'")
      machine.succeed(f"su - brenoslivio -c 'env XDG_RUNTIME_DIR=/run/user/{uid} systemctl --user start pipewire.service wireplumber.service'")
      machine.succeed(f"su - brenoslivio -c 'env XDG_RUNTIME_DIR=/run/user/{uid} systemctl --user is-active pipewire.service wireplumber.service'")
    '';
  };
}
