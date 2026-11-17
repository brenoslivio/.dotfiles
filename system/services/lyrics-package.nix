{ pkgs }:
pkgs.stdenvNoCC.mkDerivation {
  pname = "jellyfin-lrclib";
  version = "5.0.0.0";
  src = pkgs.fetchzip {
    url = "https://github.com/jellyfin/jellyfin-plugin-lrclib/archive/refs/tags/v5.tar.gz";
    hash = "sha256-HPlilULz96s/LeIyh9TE9oHqXIejBTNO2uxXWNkFJZk=";
  };
  nativeBuildInputs = [ pkgs.dotnetCorePackages.sdk_10_0 ];
  postPatch = ''
    # Keep bulk scans gentle; honor Retry-After with a minimum cooldown and jitter.
    substituteInPlace Jellyfin.Plugin.LrcLib/LrcLibRateLimiter.cs \
      --replace-fail 'FromMilliseconds(200)' 'FromMilliseconds(4000)' \
      --replace-fail 'var resolved = requested ?? _fallbackRetryAfter;' \
        'var resolved = TimeSpan.FromSeconds(Math.Max(30, (requested ?? _fallbackRetryAfter).TotalSeconds) + Random.Shared.NextDouble() * 5);'
    substituteInPlace Jellyfin.Plugin.LrcLib/PluginServiceRegistrator.cs \
      --replace-fail 'client.DefaultRequestHeaders.Accept.Add' \
        'client.DefaultRequestHeaders.UserAgent.Add(new ProductInfoHeaderValue("(+https://github.com/jellyfin/jellyfin-plugin-lrclib)")); client.DefaultRequestHeaders.Accept.Add'
  '';
  buildPhase = ''
    export DOTNET_CLI_HOME="$TMPDIR/dotnet"
    export DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
    cat > Jellyfin.Plugin.LrcLib/Jellyfin.Plugin.LrcLib.csproj <<EOF
    <Project Sdk="Microsoft.NET.Sdk">
      <PropertyGroup><TargetFramework>net10.0</TargetFramework><Nullable>enable</Nullable></PropertyGroup>
      <ItemGroup>
        <FrameworkReference Include="Microsoft.AspNetCore.App" />
        <Reference Include="${pkgs.jellyfin}/lib/jellyfin/MediaBrowser.*.dll"><Private>false</Private></Reference>
        <Reference Include="${pkgs.jellyfin}/lib/jellyfin/Jellyfin.*.dll"><Private>false</Private></Reference>
        <EmbeddedResource Include="Configuration/config.html" />
      </ItemGroup>
    </Project>
    EOF
    dotnet build Jellyfin.Plugin.LrcLib -c Release -p:NuGetAudit=false -p:RestoreSources= -o build
  '';
  installPhase = ''
    mkdir -p "$out"
    cp build/Jellyfin.Plugin.LrcLib.dll "$out/"
    cat > "$out/meta.json" <<EOF
    {"guid":"d106ebe6-9ca8-4fbc-9cd1-a92a213da9f9","name":"LrcLib Lyrics","version":"5.0.0.0","targetAbi":"12.0.0.0","autoUpdate":false}
    EOF
  '';
}
