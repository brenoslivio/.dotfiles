{
  description = "NixOS ahimsa flake";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-24.11";
    home-manager = {
      url = "github:nix-community/home-manager/release-24.11";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, home-manager, ... }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
    in {
      # NixOS system configuration
      nixosConfigurations."brenoslivio" = nixpkgs.lib.nixosSystem {
        inherit system;

        modules = [
          ./system/configuration.nix
        ];
      };

      # Home Manager as a standalone config
      homeConfigurations."brenoslivio" = home-manager.lib.homeManagerConfiguration {
        inherit pkgs;
        modules = [ 
          ./modules/home-manager
        ];
      };
    };
}
