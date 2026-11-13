{
  description = "Breno's reproducible NixOS systems";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    # Temporary Brave exception: its restoration is on release-26.05 but
    # has not reached the nixos-unstable channel yet (NixOS/nixpkgs#584534).
    nixpkgs-stable.url = "github:nixos/nixpkgs/release-26.05";
    
    home-manager = {
      url = "github:nix-community/home-manager/master";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    spicetify-nix = {
      url = "github:Gerg-L/spicetify-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = inputs@{ self, nixpkgs, home-manager, ... }:
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
      isServer = hostName: ((hostMetadata hostName).profile or "desktop") == "server";

      specialArgsFor = metadata: {
        inherit inputs;
        inherit (metadata) primaryUser primaryUserDescription primaryUserEmail;
      };

      # Production and VM tests share these modules; only hardware differs.
      sharedModules = hostName:
        let metadata = hostMetadata hostName;
        in [ ./system/common.nix ./system/cache.nix ] ++ (if isServer hostName then [
          ./system/server.nix
          { system.configurationRevision = self.rev or null; }
        ] else [
          ./system/configuration.nix
          home-manager.nixosModules.home-manager
          {
            system.configurationRevision = self.rev or null;
            home-manager = {
              useGlobalPkgs = true;
              useUserPackages = true;
              extraSpecialArgs = specialArgsFor metadata;
              users.${metadata.primaryUser} = import ./modules;
            };
          }
        ]);

      mkHost = hostName: nixpkgs.lib.nixosSystem {
          inherit system;
          specialArgs = specialArgsFor (hostMetadata hostName);
          modules = sharedModules hostName ++ [ (hostPath hostName) ];
        };

      desktopHosts = builtins.filter (hostName: !(isServer hostName)) hostNames;
      userNames = lib.unique (map (hostName: (hostMetadata hostName).primaryUser) desktopHosts);
      metadataForUser = userName:
        hostMetadata (builtins.head (
          builtins.filter (hostName: (hostMetadata hostName).primaryUser == userName) desktopHosts
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

      packages.${system}.updater = import ./scripts/updater-package.nix { inherit pkgs; };

      checks.${system} = import ./tests {
        inherit pkgs;
        home = self.homeConfigurations.brenoslivio;
        vmModules = sharedModules "ahimsa";
        vmSpecialArgs = specialArgsFor (hostMetadata "ahimsa");
        vps = self.nixosConfigurations.ahimsa-vps;
        vpsModules = sharedModules "ahimsa-vps" ++ [ (hostPath "ahimsa-vps") ];
        vpsSpecialArgs = specialArgsFor (hostMetadata "ahimsa-vps");
      };
    };
}
