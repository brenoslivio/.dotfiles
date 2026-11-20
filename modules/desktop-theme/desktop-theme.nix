{ lib, ... }:

{
  xdg.configFile."desktop-theme/palette.css".source = ./palette.css;

  # Append to the selected GTK theme, including Home Manager's GTK 4 import.
  gtk.gtk3.extraCss = lib.mkAfter (builtins.readFile ./menus-gtk3.css);
  gtk.gtk4.extraCss = lib.mkAfter (builtins.readFile ./menus-gtk4.css);
}
