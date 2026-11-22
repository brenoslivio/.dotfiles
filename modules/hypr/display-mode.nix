{ pkgs }:
pkgs.writeShellScript "display-mode" ''
  export PATH="${pkgs.lib.makeBinPath [ pkgs.hyprland pkgs.rofi ]}:$PATH"
  exec ${pkgs.python3}/bin/python3 ${./display_mode.py} "$@"
''
