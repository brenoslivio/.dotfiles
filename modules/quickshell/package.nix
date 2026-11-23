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
    export PATH=${lib.makeBinPath [ pkgs.systemd ]}:$PATH
    export PYTHONTZPATH=${pkgs.tzdata}/share/zoneinfo
    exec ${python}/bin/python3 ${lib.fileset.toSource {
      root = ./.;
      fileset = lib.fileset.unions [ ./clock.py ./weather.py ];
    }}/clock.py "$@"
  '';
  volumeFeedback = pkgs.writeShellScriptBin "dotfiles-volume-feedback" ''
    exec 9>"$XDG_RUNTIME_DIR/dotfiles-volume-feedback.lock"
    ${pkgs.util-linux}/bin/flock -n 9 || exit 0
    exec ${pkgs.pulseaudio}/bin/paplay --device=@DEFAULT_SINK@ --property=media.role=event \
      --stream-name="Volume feedback" --volume=65536 \
      ${pkgs.sound-theme-freedesktop}/share/sounds/freedesktop/stereo/audio-volume-change.oga
  '';
  audio = control "dotfiles-audio" "panel_audio.py" [ pkgs.pulseaudio pkgs.wireplumber pkgs.libnotify pkgs.zenity volumeFeedback ];
  updates = control "dotfiles-update-indicator" "panel_updates.py" [ pkgs.gh pkgs.git pkgs.systemd pkgs.xdg-utils ];
  tasks = control "dotfiles-tasks" "panel_tasks.py" [ pkgs.zenity pkgs.libnotify ];
  focus = pkgs.writeShellScript "panel-task-focus" ''
    export PYTHONTZPATH=${pkgs.tzdata}/share/zoneinfo
    export PATH=${lib.makeBinPath [ pkgs.libnotify ]}:$PATH
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
  powerAction = label: symbol: key: command: { inherit label symbol key command; };
  powerActions = [
    (powerAction "Lock" "system-lock-screen" "l" [ lock "--grace" "0" ])
    (powerAction "Suspend" "system-suspend" "u" [ (toString (sleepAndLock "suspend")) ])
    (powerAction "Hibernate" "system-hibernate" "h" [ (toString (sleepAndLock "hibernate")) ])
    (powerAction "Log Out" "system-log-out" "e" [ (toString logout) ])
    (powerAction "Reboot" "system-reboot" "r" [ systemctl "reboot" ])
    (powerAction "Shut Down" "system-shutdown" "s" [ systemctl "poweroff" ])
  ];
  commands = {
    airplane = [ (toString (pkgs.writeShellScript "panel-airplane" ''
      export PATH=${lib.makeBinPath [ pkgs.util-linux pkgs.systemd ]}:$PATH
      exec ${python}/bin/python3 ${./airplane.py} "$@"
    '')) ];
    displays = [ (toString (import ../hypr/display-mode.nix { inherit pkgs; })) ];
    clock = [ (toString clock) ];
    streetSearch = [ "${python}/bin/python3" "${./street_search.py}" ];
    audio = [ (lib.getExe audio) ];
    volumeFeedback = [ "${volumeFeedback}/bin/dotfiles-volume-feedback" ];
    nightLight = [ (lib.getExe (import ../hypr/night-light.nix { inherit pkgs; })) ];
    updates = [ (lib.getExe updates) ];
    tasks = [ (lib.getExe tasks) ];
    focus = [ (toString focus) ];
    resources = [ "${python}/bin/python3" "${../../scripts/panel_resources.py}" ];
    hardware = [ "${python}/bin/python3" "${lib.fileset.toSource {
      root = ./.;
      fileset = lib.fileset.unions [ ./hardware.py ./airplane.py ];
    }}/hardware.py" ];
    brightness = [ "${pkgs.brightnessctl}/bin/brightnessctl" "-c" "backlight" "set" ];
    spectrum = [ "${python}/bin/python3" "${./spectrum.py}" "${pkgs.cava}/bin/cava" "-p" "${./cava.conf}" ];
    capture = [ (toString capture) ];
    bluetoothDevice = [ "${pkgs.systemd}/bin/busctl" "--system" "--timeout=30s" "call" "org.bluez" ];
    bluetoothPair = [ "${pkgs.python3.withPackages (ps: [ ps.pygobject3 ])}/bin/python3" "${./bluetooth_pair.py}" ];
    obsidian = [ "${pkgs.obsidian}/bin/obsidian" ];
    logo = "file://${../../assets/icons/nixos.svg}";
    bellIcon = "file://${../../assets/icons/notification-bell.svg}";
    updateIcon = "file://${../../assets/icons/flake-update.svg}";
    taskIcon = "file://${../../assets/icons/tasks.svg}";
  };
  ui = pkgs.runCommandLocal "quickshell-panel-ui" { } ''
    mkdir -p "$out"
    cp ${./ui}/*.qml "$out/"
    cp -L ${papirus}/share/icons/Papirus-Dark/16x16/places/folder-magenta.svg "$out/nemo-folder.svg"
    icons=${papirus}/share/icons/Papirus-Dark/24x24/symbolic/status
    cp -L "$icons/../actions"/{go-previous,media-skip-{backward,forward},media-playback-{start,pause}}-symbolic.svg "$out/"
    cp -L "$icons/../actions"/system-{lock-screen,suspend,hibernate,log-out,reboot,shutdown}-symbolic.svg "$out/"
    cp -L "$icons"/battery-[0-9]*-symbolic.svg "$icons"/display-brightness-{off,low,medium,high}-symbolic.svg "$out/"
    cp -L "$icons"/weather-clear-night-symbolic.svg "$out/"
    cp -L "$icons"/airplane-mode-symbolic.svg "$out/"
    cp -L "$icons/../devices"/{ram,cpu,video-display}-symbolic.svg "$out/"
    cp -L "$icons"/{audio-volume-{high,muted},microphone-sensitivity-{high,muted},display-brightness,bluetooth-{disabled,active,disconnected},network-wireless-{disabled,offline,signal-{excellent,good,ok,weak}}}-symbolic.svg "$out/"
    cp -L ${papirus}/share/icons/Papirus-Dark/24x24/symbolic/status/{appointment-soon,battery-low,battery-caution}-symbolic.svg "$out/"
    echo 'var commands = ${builtins.toJSON commands}' > "$out/Config.js"
    echo 'var actions = ${builtins.toJSON powerActions}' > "$out/PowerActions.js"
    sed -nE 's/^@define-color desktop_([a-z]+) (#[a-fA-F0-9]+);$/var \1 = "\2";/p' \
      ${../desktop-theme/palette.css} > "$out/Palette.js"
  '';
  panel = pkgs.writeShellScriptBin "quickshell-panel" ''
    exec ${pkgs.quickshell}/bin/qs -n -p ${ui} "$@"
  '';
in panel.overrideAttrs { passthru = { inherit audio focus updates ui; }; }
