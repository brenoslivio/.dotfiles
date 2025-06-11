{ dotfiles, outOfStore, config, pkgs, extras, ... }:

let
  spicetifyModule = extras.spicetify-nix.homeManagerModules.default;
  spicePkgs = extras.spicetify-nix.legacyPackages.${pkgs.system};
in
{
  imports = [
    spicetifyModule
  ];

  programs.spicetify = {
    enable = true;
    enabledExtensions = with spicePkgs.extensions; [
      betterGenres
      wikify
      songStats
    ];

    theme = spicePkgs.themes.orchis;
    colorScheme = "custom";
    customColorScheme = {
      text = "f5d9f6";             # Soft light pink for text contrast
      subtext = "d3a4d9";          # Muted lavender subtext
      sidebar-text = "e0b0f6";     # Light magenta-tinted tone
      main = "1a0a1f";             # Very dark purple, stylish base
      sidebar = "2a1a2f";          # Deep plum tone for sidebar
      player = "1a0a1f";           # Matches main for visual unity
      card = "2a1a2f";             # Slight contrast from player
      shadow = "100815";           # Subtle shadow, not too harsh
      selected-row = "de0be6";     # Use the main magenta for highlight
      button = "a64ac9";           # Complementary purple
      button-active = "de0be6";    # Your chosen magenta
      button-disabled = "59405c";  # Muted plum-gray
      tab-active = "de0be6";       # Keep magenta as active tab indicator
      notification = "29c46f";     # Contrasting green for alerts
      notification-error = "ff4fa1"; # Vibrant pink-red for errors
      misc = "7e6786";             # Dusty lavender tone
    };
  };
}
