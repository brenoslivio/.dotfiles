{ pkgs }:

let
  inherit (pkgs) lib;
  papirus = pkgs.papirus-icon-theme.override { color = "magenta"; };
  python = pkgs.python3.withPackages (ps: [ ps.inotify-simple ps.pulsectl ]);
  sources = lib.fileset.toSource {
    root = ../../scripts;
    fileset = lib.fileset.unions [
      ../../scripts/panel_audio.py ../../scripts/desktop_menu.py
      ../../scripts/panel_updates.py ../../scripts/update.py ../../scripts/panel_tasks.py ../../scripts/task_focus.py
      ../../scripts/task_board.py ../../scripts/task_plan.py
    ];
  };
  control = name: script: inputs: pkgs.writeShellApplication {
    inherit name;
    runtimeInputs = inputs;
    text = ''exec ${python}/bin/python3 ${sources}/${script} "$@"'';
  };
  clock = pkgs.writeShellScript "panel-clock" ''
    export PYTHONTZPATH=${pkgs.tzdata}/share/zoneinfo
    exec ${python}/bin/python3 ${lib.fileset.toSource {
      root = ./.;
      fileset = lib.fileset.unions [ ./clock.py ./weather.py ];
    }}/clock.py "$@"
  '';
  audio = control "dotfiles-audio" "panel_audio.py" [ pkgs.pulseaudio pkgs.libnotify pkgs.zenity ];
  updates = control "dotfiles-update-indicator" "panel_updates.py" [ pkgs.gh pkgs.systemd pkgs.xdg-utils ];
  tasks = control "dotfiles-tasks" "panel_tasks.py" [ pkgs.zenity pkgs.libnotify ];
  focus = pkgs.writeShellScript "panel-task-focus" ''
    export PYTHONTZPATH=${pkgs.tzdata}/share/zoneinfo
    export PATH=${lib.makeBinPath [ pkgs.libnotify pkgs.swaynotificationcenter ]}:$PATH
    exec ${python}/bin/python3 ${sources}/task_focus.py "$@"
  '';
  capture = pkgs.writeShellScript "panel-capture" ''
    set -o pipefail
    ${pkgs.pipewire}/bin/pw-dump -mN | ${python}/bin/python3 ${./capture.py}
  '';
  systemctl = "${pkgs.systemd}/bin/systemctl";
  lock = "${pkgs.hyprlock}/bin/hyprlock";
  sleepAndLock = mode: pkgs.writeShellScript "panel-${mode}" ''
    ${systemctl} ${mode}
    exec ${lock} --grace 0
  '';
  logout = pkgs.writeShellScript "panel-logout" ''
    ${pkgs.coreutils}/bin/sleep 1
    exec ${pkgs.hyprland}/bin/hyprctl dispatch 'hl.dsp.exit()'
  '';
  powerAction = label: glyph: key: command: { inherit label glyph key command; };
  powerActions = [
    (powerAction "Lock" "󰌾" "l" [ lock "--grace" "0" ])
    (powerAction "Suspend" "󰖔" "u" [ (toString (sleepAndLock "suspend")) ])
    (powerAction "Hibernate" "󰜗" "h" [ (toString (sleepAndLock "hibernate")) ])
    (powerAction "Log Out" "󰍃" "e" [ (toString logout) ])
    (powerAction "Reboot" "󰜉" "r" [ systemctl "reboot" ])
    (powerAction "Shut Down" "󰐥" "s" [ systemctl "poweroff" ])
  ];
  commands = {
    displays = [ (toString (import ../hypr/display-mode.nix { inherit pkgs; })) ];
    clock = [ (toString clock) ];
    streetSearch = [ "${python}/bin/python3" "${./street_search.py}" ];
    audio = [ (lib.getExe audio) ];
    updates = [ (lib.getExe updates) ];
    tasks = [ (lib.getExe tasks) ];
    focus = [ (toString focus) ];
    resources = [ "${python}/bin/python3" "${../../scripts/panel_resources.py}" ];
    hardware = [ "${python}/bin/python3" "${./hardware.py}" ];
    brightness = [ "${pkgs.brightnessctl}/bin/brightnessctl" "-c" "backlight" "set" ];
    notifications = [ "${pkgs.swaynotificationcenter}/bin/swaync-client" ];
    spectrum = [ "${python}/bin/python3" "${./spectrum.py}" "${pkgs.cava}/bin/cava" "-p" "${./cava.conf}" ];
    capture = [ (toString capture) ];
    mixer = [ "${pkgs.pavucontrol}/bin/pavucontrol" "-t" "3" ];
    obsidian = [ "${pkgs.obsidian}/bin/obsidian" ];
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
    echo 'var actions = ${builtins.toJSON powerActions}' > "$out/PowerActions.js"
    sed -nE 's/^@define-color desktop_([a-z]+) (#[a-fA-F0-9]+);$/var \1 = "\2";/p' \
      ${../desktop-theme/palette.css} > "$out/Palette.js"
  '';
  panel = pkgs.writeShellScriptBin "quickshell-panel" ''
    exec ${pkgs.quickshell}/bin/qs -n -p ${ui} "$@"
  '';
in panel.overrideAttrs { passthru = { inherit audio focus updates ui; }; }
