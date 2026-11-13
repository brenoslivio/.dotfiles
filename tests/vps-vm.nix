{ vps, vpsModules, vpsSpecialArgs }:
vps.pkgs.testers.runNixOSTest {
  name = "vps-smoke";
  globalTimeout = 900;
  node.pkgs = vps.pkgs.lib.mkForce null;
  node.specialArgs = vpsSpecialArgs;
  nodes.machine = { lib, pkgs, ... }: {
    imports = vpsModules;
    boot.loader.systemd-boot.enable = lib.mkForce false;
    boot.loader.efi.canTouchEfiVariables = lib.mkForce false;
    # The test boots directly into its kernel; generate the GRUB menu without
    # installing a boot sector on its unpartitioned disposable filesystem.
    boot.loader.grub.device = lib.mkOverride 0 "nodev";
    boot.kernelParams = lib.mkForce [];
    system.switch.enable = true;
    systemd.network.networks."10-uplink" = lib.mkForce {};
    networking.useNetworkd = lib.mkForce false;
    networking.useDHCP = lib.mkForce false;
    fileSystems = lib.mkForce {};
    virtualisation = { memorySize = 6144; cores = 2; diskSize = 4096; };
    services.media-stack.minFreeGiB = lib.mkForce 1;
    nix.gc.automatic = lib.mkForce false;
    services.caddy.virtualHosts."media.breno.science".extraConfig = lib.mkBefore "tls internal";
    # Avoid external indexers/providers; exercise Jellyfin's real local API.
    systemd.services.media-stack-setup.serviceConfig.ExecStart = lib.mkForce (pkgs.writeShellScript "vm-media-setup" ''
      ${pkgs.python3}/bin/python3 - <<'PY'
      import importlib.util, json
      from pathlib import Path
      spec = importlib.util.spec_from_file_location('media', '${../scripts/media-stack.py}')
      module = importlib.util.module_from_spec(spec)
      spec.loader.exec_module(module)
      cfg = json.loads(Path('/etc/media-stack.json').read_text())
      credentials = json.loads(Path('/var/lib/media-stack/credentials.json').read_text())
      module.jellyfin(cfg, credentials)
      PY
    '');
  };
  testScript = ''
    import json, shlex
    start_all()
    machine.wait_for_unit("sshd.service")
    machine.wait_for_unit("media-stack-setup.service")
    for service in ["jellyfin", "seerr", "radarr", "sonarr", "lidarr", "prowlarr", "qbittorrent", "bazarr", "media-releases", "caddy"]:
        machine.wait_for_unit(service + ".service")
    machine.succeed("ss -lnt | grep '127.0.0.1:8096'")
    machine.wait_until_succeeds("curl --fail --cacert /var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt --resolve media.breno.science:443:127.0.0.1 https://media.breno.science/System/Info/Public | jq -e '.StartupWizardCompleted'")
    machine.succeed("dotfiles-vps-control status | jq -e '.host == \"ahimsa-vps\"'")
    machine.succeed("dotfiles-vps-control health | jq -e '.server_id'")
    machine.wait_for_unit("dotfiles-vps-recovery.timer")

    # Exercise a real account rename twice. IDs, passwords and preferences survive.
    machine.succeed("${vps.pkgs.python3}/bin/python3 - <<'PY'\n" + """
    import importlib.util, json
    from pathlib import Path
    spec = importlib.util.spec_from_file_location('media', '${../scripts/media-stack.py}')
    media = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(media)
    cfg = json.loads(Path('/etc/media-stack.json').read_text())
    creds = json.loads(Path('/var/lib/media-stack/credentials.json').read_text())
    api = media.jellyfin(cfg, creds)
    identities = {}
    for old, new in cfg['viewerRenames'].items():
        user = next(u for u in api.call('/Users') if u['Name'] == new)
        identities[new] = user['Id']
        preferences = dict(user['Configuration'], EnableNextEpisodeAutoPlay=False)
        api.call('/Users/'+user['Id']+'/Configuration', preferences, 'POST')
        api.call('/Users/'+user['Id'], dict(user, Name=old, Configuration=preferences), 'POST')
        creds['jellyfin']['viewers'][old] = creds['jellyfin']['viewers'].pop(new)
    media.write_json(Path(cfg['stateDir'])/'credentials.json', creds)
    media.prepare(cfg)
    creds = json.loads(Path('/var/lib/media-stack/credentials.json').read_text())
    for attempt in range(2):
        media.rename_viewers(api, cfg, creds)
        users = api.call('/Users')
        assert len(users) == 3
        for name, identity in identities.items():
            user = next(u for u in users if u['Name'] == name)
            assert user['Id'] == identity
            assert not user['Configuration']['EnableNextEpisodeAutoPlay']
            login = media.API(cfg['ports']['jellyfin'], headers={'Authorization': 'MediaBrowser Client="VM", Device="VM", DeviceId="vm-'+name+'", Version="1"'})
            result = login.call('/Users/AuthenticateByName', {'Username': name, 'Pw': creds['jellyfin']['viewers'][name]})
            assert result['User']['Id'] == identity
        assert not set(cfg['viewerRenames']) & set(creds['jellyfin']['viewers'])
    """ + "\nPY")

    def control(action, payload):
        command = "printf %s " + shlex.quote(json.dumps(payload)) + " | dotfiles-vps-control " + action
        return json.loads(machine.succeed(command))

    current = machine.succeed("readlink -f /run/current-system").strip()
    bootstrap_key = "restrict " + ${builtins.toJSON (vps.pkgs.lib.trim (builtins.readFile ../config/vps-deploy-key.pub))}
    machine.succeed("mkdir -p /root/.ssh; printf %s " + shlex.quote("# unrelated key entry\n" + bootstrap_key + "\n") + " > /root/.ssh/authorized_keys")
    machine.succeed("nix-env --profile /nix/var/nix/profiles/system --set " + shlex.quote(current))
    transaction = control("stage", {"path": current, "sha": "d" * 40})
    token = transaction["token"]
    backup = control("backup", {"token": token})
    assert backup["sha256"] == machine.succeed("sha256sum " + shlex.quote(backup["path"])).split()[0]
    assert machine.succeed("stat -c %a " + shlex.quote(backup["path"])).strip() == "600"
    machine.wait_for_unit("caddy.service")
    control("ack", {"token": token, "sha256": backup["sha256"]})
    control("begin", {"token": token, "choice": "switch"})
    machine.wait_until_succeeds("dotfiles-vps-control status | jq -e '.phase == \"awaiting_confirmation\"'")
    assert machine.succeed("cat /root/.ssh/authorized_keys").strip() == "# unrelated key entry"
    # Simulate a disconnected client: expire its lease and invoke the real watchdog.
    machine.succeed("${vps.pkgs.python3}/bin/python3 -c " + shlex.quote(
        "import json; from pathlib import Path; p=Path('/var/lib/dotfiles-vps/state.json'); s=json.loads(p.read_text()); s['deadline']=0; p.write_text(json.dumps(s))"))
    machine.succeed("systemctl start dotfiles-vps-recovery.service")
    machine.wait_until_succeeds("dotfiles-vps-control status | jq -e '.phase == \"rolled_back\"'")
    machine.succeed("test -f " + shlex.quote(backup["path"]))

    # Schedule the same test generation for boot, then exercise cold backup
    # and explicit confirmation after an actual VM reboot.
    transaction = control("stage", {"path": current, "sha": "e" * 40})
    token = transaction["token"]
    before_boot = control("backup", {"token": token})
    control("ack", {"token": token, "sha256": before_boot["sha256"]})
    control("begin", {"token": token, "choice": "boot"})
    machine.wait_until_succeeds("dotfiles-vps-control status | jq -e '.phase == \"boot_pending\"'")
    machine.shutdown()
    machine.start()
    machine.wait_for_unit("media-stack-setup.service")
    machine.wait_for_unit("caddy.service")
    status = json.loads(machine.succeed("dotfiles-vps-control status"))
    assert status["phase"] == "awaiting_confirmation"
    assert status["backup_ack"] is False
    assert status["backup"]["path"] != before_boot["path"]
    control("ack", {"token": token, "sha256": status["backup"]["sha256"]})
    control("confirm", {"token": token})
    machine.succeed("dotfiles-vps-control status | jq -e '.phase == \"confirmed\"'")
  '';
}
