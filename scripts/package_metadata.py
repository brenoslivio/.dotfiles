"""Optional metadata from the exact evaluated packages; never fetch metadata URLs."""
import json
import subprocess
import tempfile
import urllib.parse


def safe_url(value):
    if not isinstance(value, str) or len(value) > 2048 or any(c.isspace() or ord(c) < 32 for c in value) or '\\' in value:
        return None
    try:
        url = urllib.parse.urlsplit(value)
        if url.scheme not in {'https', 'http'} or not url.hostname or url.username or url.password:
            return None
        _ = url.port
    except ValueError:
        return None
    # Escape Markdown delimiters as well as quotes; preserve URL query semantics.
    try:
        return urllib.parse.quote(value, safe=':/?#=&%+@-._~')
    except UnicodeError:
        return None


def attach(packages, records):
    by_path = {}
    for record in records:
        if not isinstance(record.get('version'), str):
            continue
        links = {field: sorted({url for value in record.get(field, []) if (url := safe_url(value))})[:10]
                 for field in ('changelog', 'homepage')}
        if not any(links.values()):
            continue
        item = {'version': record['version'], **links}
        for path in record['paths']:
            by_path.setdefault(path, []).append(item)
    for package in packages.values():
        entries = {json.dumps(item, sort_keys=True) for path in package['paths'] for item in by_path.get(path, [])}
        if entries:
            package['metadata'] = [json.loads(item) for item in sorted(entries)]


def collect(packages, host, flake):
    with tempfile.NamedTemporaryFile('w', suffix='.json') as stream:
        json.dump({'names': list(packages), 'host': host, 'flake': flake}, stream)
        stream.flush()
        expression = '''let
          q = builtins.fromJSON (builtins.readFile QUERY);
          f = builtins.getFlake q.flake;
          h = f.nixosConfigurations.${q.host};
          p = h.pkgs;
          list = value: if builtins.isString value then [ value ]
            else if builtins.isList value then builtins.filter builtins.isString value else [];
          inspect = package: let result = builtins.tryEval (builtins.deepSeq data data);
            data = if !p.lib.isDerivation package then null else {
              version = package.version or (builtins.parseDrvName package.name).version;
              paths = map (output: package.${output}.outPath) (package.outputs or [ "out" ]);
              changelog = list (package.meta.changelog or []);
              homepage = list (package.meta.homepage or []);
            };
            in if result.success then result.value else null;
          direct = map (name: p.${name}) (builtins.filter (name: builtins.hasAttr name p) q.names);
          services = map (name: h.config.services.${name}.package or null)
            [ "jellyfin" "seerr" "radarr" "sonarr" "lidarr" "prowlarr" "bazarr" "qbittorrent" "caddy" ];
          home = if q.host == "ahimsa" then f.homeConfigurations.brenoslivio.config.home.packages else [];
          installed = h.config.environment.systemPackages ++ home ++ services
            ++ [ h.config.nix.package h.config.boot.kernelPackages.kernel ];
        in builtins.filter (item: item != null) (map inspect (installed ++ direct))
        '''.replace('QUERY', json.dumps(stream.name))
        result = subprocess.run(['nix', 'eval', '--json', '--impure', '--no-update-lock-file',
                                 '--no-write-lock-file', '--expr', expression],
                                text=True, capture_output=True, timeout=60, check=True)
    attach(packages, json.loads(result.stdout))
