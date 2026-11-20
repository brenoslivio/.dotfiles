{ ... }:

{
  xdg.configFile."swaync/style.css".source = ./style.css;
  xdg.configFile."swaync/config.json".text = builtins.toJSON {
    positionX = "right";
    positionY = "top";
    control-center-exclusive-zone = true;
    control-center-margin-top = 8;
    control-center-margin-right = 14;
    control-center-margin-bottom = 14;
    control-center-width = 416;
    control-center-height = 440;
    fit-to-screen = false;
    notification-window-width = 416;
    widgets = [ "inhibitors" "title" "dnd" "notifications" ];
    widget-config = {
      inhibitors = { text = "Inhibitors"; button-text = "Clear All"; clear-all-button = true; };
      title = { text = "Notifications"; button-text = "Clear All"; clear-all-button = true; };
      dnd.text = "Do Not Disturb";
      notifications.vexpand = true;
    };
  };
}
