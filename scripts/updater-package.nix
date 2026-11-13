{ pkgs }:
pkgs.stdenvNoCC.mkDerivation {
  pname = "dotfiles-update";
  version = "1";
  src = pkgs.lib.fileset.toSource {
    root = ./.;
    fileset = pkgs.lib.fileset.unions [ ./update.py ./vps_update.py ];
  };
  dontUnpack = true;
  nativeBuildInputs = [ pkgs.makeWrapper ];
  installPhase = ''
    mkdir -p "$out/libexec" "$out/bin"
    cp "$src/update.py" "$out/libexec/update.py"
    cp "$src/vps_update.py" "$out/libexec/vps_update.py"
    chmod +x "$out/libexec/update.py"
    substituteInPlace "$out/libexec/update.py" \
      --replace-fail '#!/usr/bin/env python3' '#!${pkgs.python3}/bin/python3'
    makeWrapper "$out/libexec/update.py" "$out/bin/dotfiles-update" \
      --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.git pkgs.gh pkgs.nix pkgs.libnotify pkgs.nixos-rebuild pkgs.openssh ]}
  '';
}
