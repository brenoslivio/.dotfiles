# Run inside a private D-Bus session with the packaged panel UI as the first argument.
set -euo pipefail
export HOME="$TMPDIR/home" XDG_RUNTIME_DIR="$TMPDIR/runtime" XDG_STATE_HOME="$TMPDIR/state"
mkdir -p "$HOME" "$TMPDIR/ui"
export XDG_DATA_HOME="$HOME/.local/share"
mkdir -p "$XDG_DATA_HOME/applications"
cat > "$XDG_DATA_HOME/applications/test-mail.desktop" <<DESKTOP
[Desktop Entry]
Name=Test Mail
Type=Application
Exec=$(command -v touch) $TMPDIR/mail-opened
DESKTOP
mkdir -m700 "$XDG_RUNTIME_DIR"
cp "$1"/{Notification*.qml,PanelSwitch.qml,BarButton.qml,TaskButton.qml,Palette.js} "$TMPDIR/ui/"
cp "$1"/*-symbolic.svg "$TMPDIR/ui/"
cp "$2" "$TMPDIR/ui/shell.qml"
export WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 QT_QUICK_BACKEND=software
echo 'output * mode 1024x768' > "$TMPDIR/sway.conf"
sway -c "$TMPDIR/sway.conf" > "$TMPDIR/sway.log" 2>&1 &
compositor=$!
panel=
cleanup() {
    if [[ -n "$panel" ]]; then kill "$panel" 2>/dev/null || true; fi
    kill "$compositor" 2>/dev/null || true
}
trap cleanup EXIT
trap 'cat "$TMPDIR"/{sway,panel}.log >&2' ERR
for _ in {1..100}; do
    for socket in "$XDG_RUNTIME_DIR"/wayland-*; do
        if [[ -S "$socket" ]]; then export WAYLAND_DISPLAY="${socket##*/}"; break 2; fi
    done
    sleep .1
done

call() { qs -p "$TMPDIR/ui" ipc call fixture "$@"; }
start_panel() {
    qs -n -p "$TMPDIR/ui" >> "$TMPDIR/panel.log" 2>&1 &
    panel=$!
    for _ in {1..100}; do
        if call counts >/dev/null 2>&1; then return; fi
        kill -0 "$panel" || return 1
        sleep .1
    done
    return 1
}
expect() {
    for _ in {1..40}; do
        if [[ "$(call counts)" == "$1" ]]; then return; fi
        sleep .05
    done
    echo "Expected history, unread, banners = $1; got $(call counts)" >&2
    return 1
}

start_panel
id=$(notify-send -p -a Brave -t 0 'Sample subject' $'mail.example.org\n\nFirst preview line\nSecond preview line')
expect 1,1,1
test "$(call latestText)" = '["mail.example.org","Sample subject","First preview line\nSecond preview line"]'
notify-send -r "$id" -a Brave -t 0 'Updated subject' $'First paragraph\n\nSecond paragraph'
test "$(call latestText)" = '["","Updated subject","First paragraph\n\nSecond paragraph"]'
call clear
notify-send -a 'Test Mail' -t 0 --action='archive=Archive' --action='default=Read message' 'New message' > "$TMPDIR/mail-action" &
sender=$!
expect 1,1,1
call toggleCenter
call openLatest
expect 0,0,0
wait "$sender"
test "$(cat "$TMPDIR/mail-action")" = default
notify-send -h string:desktop-entry:test-mail -t 180 'Mail digest'
expect 1,1,0
call openLatest
for _ in {1..40}; do [[ ! -f "$TMPDIR/mail-opened" ]] || break; sleep .05; done
test -f "$TMPDIR/mail-opened"
call clear
id=$(notify-send -p -t 0 Reminder)
expect 1,1,1
notify-send -r "$id" -t 0 Updated
expect 1,1,1
call toggleCenter
expect 1,0,0
call toggleCenter
call clear
call hideBar
call focus running 0
notify-send -t 0 Message
expect 1,1,0
notify-send -a Power -c device -u critical -t 0 Battery
expect 2,2,1
call clear
call toggleDnd
call focus paused 0
notify-send -t 0 Message
expect 1,1,0

# Session history is in memory. The independent manual switch survives a restart.
kill -TERM "$panel"
wait "$panel" || true
start_panel
notify-send -t 0 Message
expect 1,1,0
call clear
call toggleDnd
call focus running 1
notify-send -t 0 --action='extend=Extend 5 min' Timer > "$TMPDIR/action" &
sender=$!
expect 1,1,1
call invokeFirst
wait "$sender"
test "$(cat "$TMPDIR/action")" = extend
expect 0,0,0

notify-send -e -t 800 -h string:x-canonical-private-synchronous:volume Volume
notify-send -e -t 800 -h string:x-canonical-private-synchronous:volume Volume
expect 0,0,1
expect 0,0,0
notify-send -t 250 Mail
expect 1,1,0
call clear
expect 0,0,0
if grep -E 'TypeError|ReferenceError' "$TMPDIR/panel.log"; then exit 1; fi
