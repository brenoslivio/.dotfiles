{ pkgs }:
pkgs.stdenvNoCC.mkDerivation {
  pname = "jellyfin-manual-releases";
  version = "1.0.0";
  src = ./.;
  nativeBuildInputs = [ pkgs.dotnetCorePackages.sdk_10_0 ];
  buildPhase = ''
    export DOTNET_CLI_HOME="$TMPDIR/dotnet"
    export DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
    cat > MediaReleases.csproj <<EOF
    <Project Sdk="Microsoft.NET.Sdk">
      <PropertyGroup><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable><EnableDefaultEmbeddedResourceItems>false</EnableDefaultEmbeddedResourceItems></PropertyGroup>
      <ItemGroup>
        <FrameworkReference Include="Microsoft.AspNetCore.App" />
        <Reference Include="${pkgs.jellyfin}/lib/jellyfin/MediaBrowser.*.dll"><Private>false</Private></Reference>
        <EmbeddedResource Include="picker.js" LogicalName="MediaReleases.picker.js" />
        <EmbeddedResource Include="personal.js" LogicalName="MediaReleases.personal.js" />
        <EmbeddedResource Include="music.js" LogicalName="MediaReleases.music.js" />
      </ItemGroup>
    </Project>
    EOF
    dotnet build -c Release -p:NuGetAudit=false -p:RestoreSources= -o build
  '';
  installPhase = ''
    mkdir -p "$out"
    cp build/MediaReleases.dll "$out/"
  '';
}
