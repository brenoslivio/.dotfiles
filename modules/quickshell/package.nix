{ pkgs }:

let
  inherit (pkgs) lib;
  papirus = pkgs.papirus-icon-theme.override { color = "magenta"; };
  python = pkgs.python3.withPackages (ps: [ ps.inotify-simple ps.pulsectl ]);
  sources = lib.fileset.toSource {
    root = ../../scripts;
    fileset = lib.fileset.unions [
      ../../scripts/panel_audio.py ../../scripts/desktop_menu.py
      ../../scripts/panel_updates.py ../../scripts/update.py ../../scripts/panel_tasks.py
    ];
  };
  control = name: script: inputs: pkgs.writeShellApplication {
    inherit name;
    runtimeInputs = inputs;
    text = ''exec ${python}/bin/python3 ${sources}/${script} "$@"'';
  };
  clock = pkgs.writeShellScript "panel-clock" ''
    export PYTHONTZPATH=${pkgs.tzdata}/share/zoneinfo
    exec ${python}/bin/python3 ${./clock.py} "$@"
  '';
  audio = control "dotfiles-audio" "panel_audio.py" [ pkgs.pulseaudio pkgs.libnotify pkgs.zenity ];
  updates = control "dotfiles-update-indicator" "panel_updates.py" [ pkgs.gh pkgs.systemd pkgs.xdg-utils ];
  tasks = control "dotfiles-tasks" "panel_tasks.py" [ pkgs.zenity pkgs.libnotify ];
  capture = pkgs.writeShellScript "panel-capture" ''
    set -o pipefail
    ${pkgs.pipewire}/bin/pw-dump -mN | ${python}/bin/python3 ${./capture.py}
  '';
  powerTheme = pkgs.runCommandLocal "panel-power-theme" { } ''
    mkdir -p "$out/wlogout" "$out/desktop-theme"
    cp -r ${../wlogout}/icons ${../wlogout}/style.css "$out/wlogout/"
    cp ${../desktop-theme/palette.css} "$out/desktop-theme/palette.css"
  '';
  commands = {
    displays = [ (toString (import ../hypr/display-mode.nix { inherit pkgs; })) ];
    clock = [ (toString clock) ];
    selectZone = [ (toString clock) "apply" ];
    audio = [ (lib.getExe audio) ];
    updates = [ (lib.getExe updates) ];
    tasks = [ (lib.getExe tasks) ];
    resources = [ "${python}/bin/python3" "${../../scripts/panel_resources.py}" ];
    hardware = [ "${python}/bin/python3" "${./hardware.py}" ];
    brightness = [ "${pkgs.brightnessctl}/bin/brightnessctl" "-c" "backlight" "set" ];
    notifications = [ "${pkgs.swaynotificationcenter}/bin/swaync-client" ];
    spectrum = [ "${python}/bin/python3" "${./spectrum.py}" "${pkgs.cava}/bin/cava" "-p" "${./cava.conf}" ];
    capture = [ (toString capture) ];
    mixer = [ "${pkgs.pavucontrol}/bin/pavucontrol" "-t" "3" ];
    obsidian = [ "${pkgs.obsidian}/bin/obsidian" ];
    power = [ "${pkgs.wlogout}/bin/wlogout" "-l" "${../wlogout}/layout" "-C" "${powerTheme}/wlogout/style.css" ];
    logo = "file://${../../assets/icons/nixos.svg}";
    bellIcon = "file://${../../assets/icons/notification-bell.svg}";
    updateIcon = "file://${../../assets/icons/flake-update.svg}";
    taskIcon = "file://${../../assets/icons/tasks.svg}";
  };
  ui = pkgs.runCommandLocal "quickshell-panel-ui" { } ''
    mkdir -p "$out"
    cp ${./ui}/*.qml "$out/"
    # Use the GTK panel variants for nm-applet and Blueman, including their state changes.
    mkdir "$out/tray"
    for icon in ${papirus}/share/icons/Papirus-Dark/16x16/panel/{nm-*,network-*,blueman*}.svg; do
      cp -L "$icon" "$out/tray/"
    done
    (
      cd "$out/tray"
      echo 'var names = ['
      printf '  "%s",\n' *.svg
      echo ']'
    ) > "$out/TrayIcons.js"
    echo 'var commands = ${builtins.toJSON commands}' > "$out/Config.js"
    sed -nE 's/^@define-color desktop_([a-z]+) (#[a-fA-F0-9]+);$/var \1 = "\2";/p' \
      ${../desktop-theme/palette.css} > "$out/Palette.js"
  '';
  panel = pkgs.writeShellScriptBin "quickshell-panel" ''
    exec ${pkgs.quickshell}/bin/qs -n -p ${ui} "$@"
  '';
in panel.overrideAttrs { passthru = { inherit audio updates ui; }; }
