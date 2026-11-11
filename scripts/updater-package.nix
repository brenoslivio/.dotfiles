{ pkgs }:
pkgs.stdenvNoCC.mkDerivation {
  pname = "dotfiles-update";
  version = "1";
  src = ./update.py;
  dontUnpack = true;
  nativeBuildInputs = [ pkgs.makeWrapper ];
  installPhase = ''
    install -Dm755 "$src" "$out/bin/dotfiles-update"
    substituteInPlace "$out/bin/dotfiles-update" \
      --replace-fail '#!/usr/bin/env python3' '#!${pkgs.python3}/bin/python3'
    wrapProgram "$out/bin/dotfiles-update" \
      --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.git pkgs.gh pkgs.nix pkgs.libnotify pkgs.nixos-rebuild ]}
  '';
}
