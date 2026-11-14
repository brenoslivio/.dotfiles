{ pkgs }:
let
  # Disposable test-only keys. Production credentials are never evaluated by Nix.
  keys = pkgs.runCommand "media-vpn-test-keys" { nativeBuildInputs = [ pkgs.wireguard-tools ]; } ''
    mkdir "$out"
    wg genkey > "$out/client"
    wg genkey > "$out/peer"
    wg pubkey < "$out/client" > "$out/client.pub"
    wg pubkey < "$out/peer" > "$out/peer.pub"
  '';
in pkgs.testers.runNixOSTest {
  name = "media-vpn-isolation";
  globalTimeout = 300;
  nodes = {
    machine = { lib, ... }: {
      imports = [ ../system/services/media-stack.nix ];
      virtualisation = { memorySize = 1536; cores = 2; };
      networking.firewall.enable = false;
      environment.systemPackages = [ pkgs.curl pkgs.iproute2 pkgs.wireguard-tools pkgs.nftables pkgs.util-linux ];
      services.media-stack = {
        enable = true;
        components = lib.genAttrs [ "jellyfin" "seerr" "radarr" "sonarr" "prowlarr" "bazarr" "lidarr" ] (_: false);
        budgetGiB = 1;
        minFreeGiB = 0;
        vpn = { enable = true; configFile = "/run/test-vpn.conf"; portForwarding = true; };
      };
      # Credentials are loaded before ExecStartPre; prepare them at activation.
      system.activationScripts.test-vpn = ''
        umask 077
        cat > /run/test-vpn.conf <<EOF
        [Interface]
        PrivateKey = $(cat ${keys}/client)
        Address = 10.2.0.2/32
        DNS = 10.2.0.1
        [Peer]
        PublicKey = $(cat ${keys}/peer.pub)
        AllowedIPs = 0.0.0.0/0
        Endpoint = 192.168.1.2:51820
        EOF
      '';
    };
    peer = { ... }: {
      environment.systemPackages = [ pkgs.curl ];
      networking.firewall.enable = false;
      networking.wireguard.interfaces.wg0 = {
        ips = [ "10.2.0.1/24" ];
        listenPort = 51820;
        privateKeyFile = "${keys}/peer";
        peers = []; # Runtime test key supplied below.
      };
      systemd.services.wireguard-wg0.postStart = ''
        ${pkgs.wireguard-tools}/bin/wg set wg0 peer "$(cat ${keys}/client.pub)" allowed-ips 10.2.0.2/32
      '';
      services.dnsmasq = {
        enable = true;
        settings = { address = "/vpn.test/10.2.0.1"; bind-dynamic = true; interface = "wg0"; };
      };
      systemd.services.natpmp = {
        wantedBy = [ "multi-user.target" ];
        requires = [ "wireguard-wg0.service" ];
        after = [ "wireguard-wg0.service" ];
        serviceConfig.ExecStart = "${pkgs.python3}/bin/python3 ${pkgs.writeText "test-natpmp.py" ''
          import socket, struct
          sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
          sock.bind(('10.2.0.1', 5351))
          while True:
              data, address = sock.recvfrom(32)
              opcode = data[1]
              header = struct.pack('!BBHI', 0, opcode + 128, 0, 1)
              if opcode == 0:
                  payload = socket.inet_aton('1.1.1.1')  # Advertised only; never contacted.
              else:
                  payload = data[4:6] + struct.pack('!HI', 45678, 60)
              sock.sendto(header + payload, address)
        ''}";
      };
      systemd.services.web = {
        wantedBy = [ "multi-user.target" ];
        serviceConfig.ExecStart = "${pkgs.python3}/bin/python3 -m http.server 8081";
      };
    };
  };
  testScript = ''
    start_all()
    peer.wait_for_unit("wireguard-wg0.service")
    peer.wait_for_unit("web.service")
    machine.wait_for_unit("qbittorrent.service")
    machine.wait_for_unit("media-stack-setup.service")
    machine.succeed("curl --fail --max-time 5 http://127.0.0.1:8080/ >/dev/null")
    machine.succeed("ip netns exec media-vpn curl --fail --max-time 5 http://10.2.0.1:8081/ >/dev/null")
    machine.succeed("nsenter -t $(pidof qbittorrent-nox) -n -m cat /etc/resolv.conf | grep 10.2.0.1")
    machine.succeed("nsenter -t $(pidof qbittorrent-nox) -n -m getent ahostsv4 vpn.test | grep 10.2.0.1")
    peer.wait_for_unit("natpmp.service")
    machine.succeed("systemctl start media-vpn-forward.service")
    machine.succeed("grep 45678 /run/media-vpn/forwarding.json")
    machine.wait_until_succeeds("ip netns exec media-vpn ss -lnt | grep :45678")
    machine.succeed("systemctl start media-vpn-forward.service")
    peer.fail("curl --max-time 2 http://192.168.1.1:8080/")
    peer.fail("curl --max-time 2 http://10.2.0.2:8080/")
    machine.succeed("ip -n media-vpn -br link | grep proton0")
    machine.fail("ip -n media-vpn -br link | grep eth")
    machine.succeed("ip netns exec media-vpn nft list ruleset | grep 'policy drop'")
    # Tunnel down: no direct escape, while host traffic and private API remain usable.
    machine.succeed("ip -n media-vpn link set proton0 down")
    machine.fail("ip netns exec media-vpn curl --max-time 3 http://192.168.1.2:8081/")
    machine.fail("ip netns exec media-vpn curl -6 --max-time 3 'http://[2001:db8::1]/'")
    machine.succeed("curl --fail --max-time 5 http://192.168.1.2:8081/ >/dev/null")
    machine.succeed("curl --fail --max-time 5 http://127.0.0.1:8080/ >/dev/null")
    machine.succeed("systemctl stop media-vpn.service")
    machine.fail("systemctl is-active qbittorrent.service")
    machine.succeed("mv /run/test-vpn.conf /run/test-vpn.saved")
    machine.fail("systemctl start qbittorrent.service")
    machine.fail("systemctl is-active qbittorrent.service")
    machine.succeed("mv /run/test-vpn.saved /run/test-vpn.conf")
    machine.succeed("systemctl reset-failed")
    machine.succeed("systemctl restart media-vpn.service qbittorrent.service")
    machine.wait_for_unit("qbittorrent.service")
    machine.wait_until_succeeds("ip netns exec media-vpn curl --fail --max-time 5 http://10.2.0.1:8081/ >/dev/null")
    machine.wait_until_succeeds("curl --fail --max-time 5 http://127.0.0.1:8080/ >/dev/null")
  '';
}
