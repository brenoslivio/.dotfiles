{ config, pkgs, ... }:

let
  mixer = "${config.services.pipewire.package}/share/alsa-card-profile/mixer";
in
{
  # The ALC257 can drive either output with the jack plugged in. If ACP marks
  # the speaker unavailable, WirePlumber unlinks playback even after selection.
  services.pipewire.wireplumber.extraConfig."80-ideapad-speaker"."monitor.alsa.rules" = [
    {
      matches = [ {
        "device.name" = "alsa_card.pci-0000_03_00.6";
        "device.vendor.id" = "0x1022";
        "device.product.id" = "0x15e3";
      } ];
      actions.update-props."device.profile-set" = "ideapad.conf";
    }
  ];

  environment.etc."alsa-card-profile/profile-sets/ideapad.conf".source =
    pkgs.runCommand "ideapad.conf" {} ''
      substitute ${mixer}/profile-sets/default.conf "$out" \
        --replace-fail analog-output-speaker analog-output-speaker-ideapad \
        --replace-fail '.include 9999-custom.conf' '.include ${mixer}/profile-sets/9999-custom.conf'
    '';

  environment.etc."alsa-card-profile/paths/analog-output-speaker-ideapad.conf".source =
    pkgs.runCommand "analog-output-speaker-ideapad.conf" {} ''
      substitute ${mixer}/paths/analog-output-speaker.conf "$out" \
        --replace-fail $'[Jack Headphone]\nstate.plugged = no\nstate.unplugged = unknown\n' "" \
        --replace-fail '.include analog-output.conf.common' '.include ${mixer}/paths/analog-output.conf.common'
    '';
}
