-- Hyprland 0.57+ uses Lua. Keep the existing layout, theme and shortcuts.
-- Avoid the 0.57 rtkit timeout crash during monitor modesets.
-- https://github.com/hyprwm/Hyprland/discussions/16801
hl.env("HYPRLAND_NO_RT", "1")

local terminal = "kitty"
local file_manager = "nemo"
local menu = "rofi -show drun -switchers drun -show-icons -modes drun,calc"
-- Lock this compositor directly, even if logind/Hypridle follows an older login.
local lock = "hyprlock --grace 0"

-- hyprdocked.sh switches to the external output when it is connected.
hl.monitor({ output = "HDMI-A-1", mode = "2560x1080@60", position = "1920x0", scale = 1 })
hl.monitor({ output = "eDP-1", mode = "1920x1080@60", position = "0x0", scale = 1 })
hl.monitor({ output = "", mode = "preferred", position = "auto", scale = 1 })
for workspace = 1, 6 do
    hl.workspace_rule({ workspace = tostring(workspace), persistent = true, default = workspace == 1 })
end

hl.on("hyprland.start", function()
    for _, command in ipairs({
        "hyprpaper", "lxqt-policykit-agent", "clipse -listen",
        "nm-applet --indicator", "dropbox", "protonvpn-app",
    }) do
        hl.exec_cmd(command)
    end
    hl.exec_cmd(terminal .. " --class dropdown", { workspace = "special:dropdown silent" })
end)

for name, value in pairs({
    XCURSOR_SIZE = "30", HYPRCURSOR_SIZE = "30",
    HYPRSHOT_DIR = "Pictures/Screenshots",
    QT_QPA_PLATFORM = "wayland", QT_QPA_PLATFORMTHEME = "qt6ct",
    XDG_CURRENT_DESKTOP = "Hyprland", XDG_SESSION_TYPE = "wayland",
    XDG_SESSION_DESKTOP = "Hyprland",
}) do
    hl.env(name, value)
end

hl.config({
    general = {
        gaps_in = 5, gaps_out = 15, border_size = 3,
        col = {
            active_border = { colors = { "rgba(de0be6ee)", "rgba(de0be6ee)" }, angle = 45 },
            inactive_border = "rgba(595959aa)",
        },
        resize_on_border = false, allow_tearing = false, layout = "dwindle",
    },
    decoration = {
        rounding = 10, active_opacity = 1.0, inactive_opacity = 1.0,
        shadow = { enabled = true, range = 5, render_power = 3, color = "rgba(ca25e8ee)" },
        blur = { enabled = true, size = 4, passes = 3, vibrancy = 0.1696 },
    },
    animations = { enabled = true },
    dwindle = { preserve_split = true },
    master = { new_status = "master" },
    misc = { force_default_wallpaper = -1, disable_hyprland_logo = true },
    input = {
        kb_layout = "us", kb_variant = "", kb_model = "", kb_options = "", kb_rules = "",
        numlock_by_default = true, follow_mouse = 1, sensitivity = 0,
        touchpad = { natural_scroll = false },
    },
})
hl.device({ name = "epic-mouse-v1", sensitivity = -0.5 })

for name, points in pairs({
    easeOutQuint = { { 0.23, 1 }, { 0.32, 1 } },
    easeInOutCubic = { { 0.65, 0.05 }, { 0.36, 1 } },
    linear = { { 0, 0 }, { 1, 1 } },
    almostLinear = { { 0.5, 0.5 }, { 0.75, 1 } },
    quick = { { 0.15, 0 }, { 0.1, 1 } },
}) do
    hl.curve(name, { type = "bezier", points = points })
end
for _, animation in ipairs({
    { "global", 10, "default" },
    { "border", 5.39, "easeOutQuint" },
    { "windows", 4.79, "easeOutQuint" },
    { "windowsIn", 4.1, "easeOutQuint", "popin 87%" },
    { "windowsOut", 1.49, "linear", "popin 87%" },
    { "fadeIn", 1.73, "almostLinear" }, { "fadeOut", 1.46, "almostLinear" },
    { "fade", 3.03, "quick" }, { "layers", 3.81, "easeOutQuint" },
    { "layersIn", 4, "easeOutQuint", "fade" }, { "layersOut", 1.5, "linear", "fade" },
    { "fadeLayersIn", 1.79, "almostLinear" }, { "fadeLayersOut", 1.39, "almostLinear" },
    { "workspaces", 1.94, "almostLinear", "fade" },
    { "workspacesIn", 1.94, "almostLinear", "slidevert" },
    { "workspacesOut", 1.94, "almostLinear", "slidevert" },
    { "specialWorkspace", 8, "default", "slidefadevert -50%" },
}) do
    hl.animation({ leaf = animation[1], enabled = true, speed = animation[2], bezier = animation[3], style = animation[4] })
end

-- Open Rofi on a standalone Super release, without consuming Super shortcuts.
hl.bind("Super_L", hl.dsp.exec_cmd("~/.config/rofi/launch.sh"), { release = true })
hl.bind("Print", hl.dsp.exec_cmd("hyprshot -m output"))
hl.bind("SHIFT + Print", hl.dsp.exec_cmd("hyprshot -m region"))
hl.bind("SUPER + L", hl.dsp.exec_cmd(lock))
hl.bind("switch:on:Lid Switch", hl.dsp.exec_cmd(lock), { locked = true })
hl.bind("SUPER + B", hl.dsp.exec_cmd(terminal .. " --class clipse -e 'clipse'"))
hl.bind("XF86PowerOff", hl.dsp.exec_cmd("wlogout"))
hl.bind("SUPER + W", hl.dsp.exec_cmd("~/.config/waybar/launch.sh"))
hl.bind("SUPER + Q", hl.dsp.exec_cmd(terminal))
hl.bind("SUPER + D", hl.dsp.exec_cmd(terminal .. " --class dropdown"))
hl.bind("SUPER + C", hl.dsp.window.close())
hl.bind("SUPER + M", hl.dsp.exit())
hl.bind("SUPER + E", hl.dsp.exec_cmd(file_manager))
hl.bind("SUPER + V", hl.dsp.window.float({ action = "toggle" }))
hl.bind("SUPER + R", hl.dsp.exec_cmd(menu))
hl.bind("SUPER + P", hl.dsp.window.pseudo())
hl.bind("SUPER + J", hl.dsp.layout("togglesplit"))
for _, direction in ipairs({ "left", "right", "up", "down" }) do
    hl.bind("SUPER + " .. direction, hl.dsp.focus({ direction = direction }))
end
for workspace = 1, 10 do
    local key = tostring(workspace % 10)
    hl.bind("SUPER + " .. key, hl.dsp.focus({ workspace = workspace }))
    hl.bind("SUPER + SHIFT + " .. key, hl.dsp.window.move({ workspace = workspace }))
end
for key, workspace in pairs({ Z = "dropdown", S = "deepseek", T = "deepl" }) do
    hl.bind("SUPER + " .. key, hl.dsp.workspace.toggle_special(workspace))
end
hl.bind("SUPER + SHIFT + S", hl.dsp.window.move({ workspace = "special:dropdown" }))
-- Switch workspaces while keeping a Super+left-dragged window under the pointer.
hl.bind("SUPER + mouse_down", hl.dsp.focus({ workspace = "e+1" }))
hl.bind("SUPER + mouse_up", hl.dsp.focus({ workspace = "e-1" }))
hl.bind("SUPER + mouse:272", hl.dsp.window.drag(), { mouse = true })
hl.bind("SUPER + mouse:273", hl.dsp.window.resize(), { mouse = true })
hl.bind("SUPER + F", hl.dsp.window.fullscreen())

for key, command in pairs({
    XF86AudioRaiseVolume = [[wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+ && wpctl get-volume @DEFAULT_AUDIO_SINK@ | awk '{print int($2 * 100)}' | xargs -I[] notify-send -e -u low -h string:x-canonical-private-synchronous:volume_notif -h int:value:[] "🔊 Volume : []%"]],
    XF86AudioLowerVolume = [[wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%- && wpctl get-volume @DEFAULT_AUDIO_SINK@ | awk '{print int($2 * 100)}' | xargs -I[] notify-send -e -u low -h string:x-canonical-private-synchronous:volume_notif -h int:value:[] "🔊 Volume : []%"]],
    XF86AudioMute = "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle",
    XF86AudioMicMute = "wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle",
    XF86MonBrightnessUp = "brightnessctl s 10%+",
    XF86MonBrightnessDown = "brightnessctl s 10%-",
}) do
    hl.bind(key, hl.dsp.exec_cmd(command), { locked = true, repeating = true })
end
for key, command in pairs({
    XF86AudioNext = "playerctl next", XF86AudioPause = "playerctl play-pause",
    XF86AudioPlay = "playerctl play-pause", XF86AudioPrev = "playerctl previous",
}) do
    hl.bind(key, hl.dsp.exec_cmd(command), { locked = true })
end

hl.window_rule({ name = "authentication-dialog", match = { title = "^(Authentication Required)$" }, float = true })
hl.window_rule({ name = "blueman-manager", match = { class = "^(.blueman-manager-wrapped)$" }, float = true })
hl.window_rule({ name = "pavucontrol", match = { class = "^(org.pulseaudio.pavucontrol)$" }, float = true })
hl.window_rule({ name = "kcalc", match = { class = "^(org.kde.kcalc)$" }, float = true })
for _, rule in ipairs({
    { name = "dropdown-terminal", match = { class = "^(dropdown)$" }, workspace = "special:dropdown" },
    { name = "deepseek", match = { initial_title = "^(DeepSeek)$" }, workspace = "special:deepseek" },
    { name = "deepl", match = { class = "^(brave-bllmiclhkidahfhjpfcipplbebkfhafn-Default)$" }, workspace = "special:deepl" },
}) do
    rule.float = true
    rule.size = "monitor_w*0.5 monitor_h*0.5"
    rule.move = "monitor_w*0.25 monitor_h*0.08"
    hl.window_rule(rule)
end
hl.window_rule({
    name = "cava-waybar", match = { class = "^(cava-waybar)$" }, pin = true, float = true,
    size = "monitor_w*0.985 monitor_h*0.04", move = "monitor_w*0.0075 monitor_h*0.014",
    no_initial_focus = true, no_focus = true,
})
hl.window_rule({ name = "clipse", match = { class = "^(clipse)$" }, float = true, size = "622 652" })
hl.window_rule({ name = "suppress-maximize", match = { class = ".*" }, suppress_event = "maximize" })
hl.window_rule({
    name = "xwayland-drag-focus",
    match = { class = "^$", title = "^$", xwayland = true, float = true, fullscreen = false, pin = false },
    no_focus = true,
})
hl.layer_rule({ name = "waybar-blur", match = { namespace = "^(waybar)$" }, blur = true })
hl.layer_rule({ name = "rofi-blur", match = { namespace = "^(rofi)$" }, blur = true })
hl.layer_rule({ name = "hyprpicker-no-animation", match = { namespace = "^(hyprpicker)$" }, no_anim = true })
hl.layer_rule({ name = "selection-no-animation", match = { namespace = "^(selection)$" }, no_anim = true })
