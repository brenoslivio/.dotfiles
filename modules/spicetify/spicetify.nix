{ inputs, pkgs, ... }:

let
  spicetifyModule = inputs.spicetify-nix.homeManagerModules.default;
  spicePkgs = inputs.spicetify-nix.legacyPackages.${pkgs.stdenv.hostPlatform.system};
in
{
  imports = [
    spicetifyModule
  ];

  programs.spicetify = {
    enable = true;
    enabledExtensions = with spicePkgs.extensions; [
      wikify
      songStats
    ];

    theme = spicePkgs.themes.ziro;
    colorScheme = "custom";
    customColorScheme = {
      # Match the magenta accents in Waybar, Rofi, Hyprland, and Niri.
      text = "eeeeee";
      subtext = "dba0d9";
      main = "221b24";
      sidebar = "221b24";
      player = "221b24";
      card = "19131c";
      shadow = "19131c"; # Ziro also uses this for text on selected rows/buttons.
      selected-row = "de0be6";
      button = "d891ed";
      button-active = "de0be6";
      button-disabled = "443248";
      tab-active = "de0be6";
      notification = "19131c";
      notification-error = "ff4fa1";
      misc = "221b24";
    };
  };
}
