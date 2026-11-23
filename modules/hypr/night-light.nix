{ pkgs }:
pkgs.writeShellApplication {
  name = "night-light";
  runtimeInputs = [ pkgs.hyprland ];
  text = ''exec ${pkgs.python3}/bin/python3 ${./night_light.py} ${./night-light.json} "$@"'';
}
