import base64
import importlib.util
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import media_vpn as v

KEY = base64.b64encode(b'x'*32).decode()
CONFIG = f'''[Interface]
PrivateKey = {KEY}
Address = 10.2.0.2/32, fd00::2/128
DNS = 10.2.0.1
[Peer]
PublicKey = {KEY}
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = 192.0.2.1:51820
'''


class VPNTests(unittest.TestCase):
    def test_profile_produces_ipv4_only_tunnel(self):
        addresses, dns, mtu, wg = v.parse_config(CONFIG)
        self.assertEqual(addresses, ['10.2.0.2/32'])
        self.assertEqual(dns, ['10.2.0.1'])
        self.assertEqual(mtu, 1420)
        self.assertNotIn('::/0', wg)
        self.assertIn('AllowedIPs = 0.0.0.0/0', wg)
        self.assertNotIn('DNS', wg)

    def test_hooks_keys_and_unsafe_profiles_rejected(self):
        for invalid in [CONFIG.replace('[Peer]', 'PostUp = touch /tmp/unsafe\n[Peer]'),
                        CONFIG.replace(KEY, 'invalid'),
                        CONFIG.replace('0.0.0.0/0', '10.2.0.0/24'),
                        CONFIG.replace('192.0.2.1', 'untrusted.example'),
                        CONFIG.replace('51820', '99999'),
                        CONFIG.replace('DNS = 10.2.0.1', 'DNS = ::1'),
                        CONFIG+'SaveConfig = true\n']:
            with self.subTest(profile=invalid), self.assertRaises((ValueError, KeyError)):
                v.parse_config(invalid)

    def test_port_mapping_output_is_validated(self):
        self.assertEqual(v.mapped_port('Mapped public port 45678 protocol TCP to local port 1 lifetime 60'), 45678)
        for output in ['Mapped public port 0 protocol UDP', 'Mapped public port 999999 protocol UDP', 'timeout']:
            with self.assertRaises(ValueError):
                v.mapped_port(output)

    def test_mismatched_forwarding_never_updates_client(self):
        with patch.object(v, 'run', side_effect=['Mapped public port 1234 protocol UDP', 'Mapped public port 1235 protocol TCP']), patch.object(v.urllib.request, 'build_opener') as opener:
            with self.assertRaises(ValueError):
                v.forward(8080, '10.2.0.1')
            opener.assert_not_called()

    def test_setup_retries_proxy_reset_until_qbittorrent_is_ready(self):
        spec = importlib.util.spec_from_file_location('media_stack', Path(__file__).resolve().parents[1]/'scripts/media-stack.py')
        media = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(media)
        api = media.API(8080, '/api/v2')
        with patch.object(api, 'call', side_effect=[ConnectionResetError(), 'Ok.']) as request, patch.object(media.time, 'sleep'):
            self.assertEqual(api.wait('/auth/login'), 'Ok.')
            self.assertEqual(request.call_count, 2)
