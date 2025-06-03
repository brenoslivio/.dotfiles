{
  description = "NixOS ahimsa flake";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    spicetify-nix.url = "github:Gerg-L/spicetify-nix";
    home-manager = {
      url = "github:nix-community/home-manager";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, home-manager, spicetify-nix, ... }:
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
          ./modules
        ];
        extraSpecialArgs = { inherit spicetify-nix; };
      };
    };
}
