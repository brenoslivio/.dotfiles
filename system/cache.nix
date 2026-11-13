{ lib, ... }:
let
  cache = builtins.fromJSON (builtins.readFile ../config/cache.json);
  enabled = cache.name != null;
in {
  assertions = [
    { assertion = enabled == (cache.publicKey != null);
      message = "Configure both the Cachix cache name and its public signing key."; }
    { assertion = !enabled || (builtins.match "[a-z0-9][a-z0-9-]*" cache.name != null
        && builtins.match "[A-Za-z0-9._-]+:[A-Za-z0-9+/]{43}=" cache.publicKey != null);
      message = "Invalid Cachix name or public signing key."; }
  ];
  nix.settings = lib.mkIf enabled {
    extra-substituters = [ "https://${cache.name}.cachix.org" ];
    extra-trusted-public-keys = [ cache.publicKey ];
  };
}
