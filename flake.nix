{
  description = "Breno's reproducible NixOS systems";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-26.05";
    
    home-manager = {
      url = "github:nix-community/home-manager/release-26.05";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    spicetify-nix = {
      url = "github:Gerg-L/spicetify-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = inputs@{ nixpkgs, home-manager, ... }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        inherit system;
        config.allowUnfree = true;
      };
      lib = nixpkgs.lib;
      hostsDirectory = ./hosts;
      hostNames = builtins.attrNames (
        lib.filterAttrs
          (name: type:
            type == "directory"
            && builtins.pathExists (hostsDirectory + "/${name}/default.nix")
            && builtins.pathExists (hostsDirectory + "/${name}/metadata.nix"))
          (builtins.readDir hostsDirectory)
      );
      hostPath = hostName: hostsDirectory + "/${hostName}";
      hostMetadata = hostName: import (hostPath hostName + "/metadata.nix");

      specialArgsFor = metadata: {
        inherit inputs;
        inherit (metadata) primaryUser primaryUserDescription primaryUserEmail;
      };

      mkHost = hostName:
        let
          metadata = hostMetadata hostName;
          specialArgs = specialArgsFor metadata;
        in
        nixpkgs.lib.nixosSystem {
          inherit system specialArgs;
          modules = [
            ./system/configuration.nix
            (hostPath hostName)
            home-manager.nixosModules.home-manager
            {
              home-manager = {
                useGlobalPkgs = true;
                useUserPackages = true;
                extraSpecialArgs = specialArgs;
                users.${metadata.primaryUser} = import ./modules;
              };
            }
          ];
        };

      userNames = lib.unique (map (hostName: (hostMetadata hostName).primaryUser) hostNames);
      metadataForUser = userName:
        hostMetadata (builtins.head (
          builtins.filter (hostName: (hostMetadata hostName).primaryUser == userName) hostNames
        ));

      mkHome = userName:
        let metadata = metadataForUser userName;
        in home-manager.lib.homeManagerConfiguration {
          inherit pkgs;
          modules = [ ./modules ];
          extraSpecialArgs = specialArgsFor metadata;
        };
    in {
      nixosConfigurations = lib.genAttrs hostNames mkHost;

      # Kept intentionally for the fast, user-only `home` Fish function.
      homeConfigurations = lib.genAttrs userNames mkHome;
    };
}
