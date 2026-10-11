{ config, lib, pkgs, ... }:

{
  home.file = {
    ".local/share/nemo/actions/compress.nemo_action".source = ./compress.nemo_action;
    ".local/share/nemo/actions/extracthere.nemo_action".source = ./extracthere.nemo_action;
  };

  home.activation.nemoFolderIcons = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
    set_folder_icon() {
      local directory="$1"
      local icon="$2"

      if [[ -d "$directory" ]]; then
        run ${lib.getExe' pkgs.glib "gio"} set "$directory" metadata::custom-icon-name "$icon"
      fi
    }

    set_folder_icon "${config.home.homeDirectory}/Documents" folder-documents
    set_folder_icon "${config.home.homeDirectory}/Downloads" folder-download
    set_folder_icon "${config.home.homeDirectory}/Pictures" folder-pictures
  '';
}
