using System.Reflection;
using System.Text;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Common.Plugins;
using MediaBrowser.Controller;
using MediaBrowser.Controller.Plugins;
using MediaBrowser.Model.Serialization;
using MediaBrowser.Model.Plugins;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.DependencyInjection;

namespace MediaReleases;

public sealed class Plugin(IApplicationPaths paths, IXmlSerializer serializer) : BasePlugin<BasePluginConfiguration>(paths, serializer)
{
    public override string Name => "Manual release selection";
    public override Guid Id => Guid.Parse("41cf617d-7a19-4875-a6da-01d174ba2485");
}

public sealed class Services : IPluginServiceRegistrator
{
    public void RegisterServices(IServiceCollection services, IServerApplicationHost host)
    {
        services.AddSingleton<IStartupFilter, Filter>();
    }
}

// Extend the pinned JE loader without modifying Jellyfin's immutable web directory.
public sealed class Filter : IStartupFilter
{
    public Action<IApplicationBuilder> Configure(Action<IApplicationBuilder> next) => app =>
    {
        app.Use(async (context, proceed) =>
        {
            var path = context.Request.Path.Value ?? "";
            if (HttpMethods.IsGet(context.Request.Method) &&
                (path.EndsWith("/web", StringComparison.OrdinalIgnoreCase) ||
                 path.EndsWith("/web/", StringComparison.OrdinalIgnoreCase) ||
                 path.EndsWith("/web/index.html", StringComparison.OrdinalIgnoreCase)))
            {
                context.Request.Headers.Remove("If-None-Match");
                context.Request.Headers.Remove("If-Modified-Since");
                context.Response.OnStarting(() => {
                    context.Response.Headers["Cache-Control"] = "no-store";
                    context.Response.Headers.Remove("ETag");
                    context.Response.Headers.Remove("Last-Modified");
                    return Task.CompletedTask;
                });
            }
            if (HttpMethods.IsPost(context.Request.Method) &&
                context.Request.Path.Equals("/JellyfinEnhanced/jellyseerr/request"))
            {
                context.Response.StatusCode = 409;
                await context.Response.WriteAsJsonAsync(new { error = "Choose a release before requesting." });
                return;
            }
            if (!HttpMethods.IsGet(context.Request.Method) ||
                !context.Request.Path.Equals("/JellyfinEnhanced/script"))
            {
                await proceed();
                return;
            }
            context.Request.Headers.Remove("Accept-Encoding");
            context.Request.Headers.Remove("If-None-Match");
            context.Request.Headers.Remove("If-Modified-Since");
            var original = context.Response.Body;
            using var buffer = new MemoryStream();
            context.Response.Body = buffer;
            try
            {
                await proceed();
                if (context.Response.StatusCode == 200)
                {
                    using var resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("MediaReleases.picker.js")!;
                    buffer.Position = buffer.Length;
                    await buffer.WriteAsync(Encoding.UTF8.GetBytes("\n;\n"));
                    await buffer.WriteAsync(Encoding.UTF8.GetBytes("window.mediaUIRevision=" +
                        System.Text.Json.JsonSerializer.Serialize(Environment.GetEnvironmentVariable("MEDIA_UI_REVISION")) + ";\n"));
                    await resource.CopyToAsync(buffer);
                    if (Environment.GetEnvironmentVariable("MEDIA_PERSONAL_HOME") == "1")
                    {
                        using var personal = Assembly.GetExecutingAssembly().GetManifestResourceStream("MediaReleases.personal.js")!;
                        await buffer.WriteAsync(Encoding.UTF8.GetBytes("\n;\n"));
                        await personal.CopyToAsync(buffer);
                    }
                    if (Environment.GetEnvironmentVariable("MEDIA_MUSIC") == "1")
                    {
                        using var music = Assembly.GetExecutingAssembly().GetManifestResourceStream("MediaReleases.music.js")!;
                        await buffer.WriteAsync(Encoding.UTF8.GetBytes("\n;\n"));
                        await music.CopyToAsync(buffer);
                    }
                    context.Response.Headers.Remove("ETag");
                    context.Response.Headers["Cache-Control"] = "no-store";
                }
                context.Response.ContentLength = buffer.Length;
                buffer.Position = 0;
                await buffer.CopyToAsync(original);
            }
            finally { context.Response.Body = original; }
        });
        next(app);
    };
}

[ApiController, Route("MediaReleases"), Authorize]
public sealed class ReleasesController : ControllerBase
{
    [HttpGet("client-version"), AllowAnonymous]
    public IActionResult ClientVersion()
    {
        Response.Headers["Cache-Control"] = "no-store";
        return Ok(new { revision = Environment.GetEnvironmentVariable("MEDIA_UI_REVISION") });
    }
    private static readonly HttpClient Client = new(new HttpClientHandler { UseProxy = false, AllowAutoRedirect = false })
    { Timeout = TimeSpan.FromMinutes(5) };

    [HttpGet("activity")]
    public Task<IActionResult> Activity() => Forward("activity", HttpMethod.Get);

    [HttpGet("disk-usage")]
    public Task<IActionResult> DiskUsage() => Forward("disk-usage", HttpMethod.Get);

    [HttpGet("music-status")]
    public Task<IActionResult> MusicStatus() => Forward("music-status", HttpMethod.Get);

    [HttpGet("removal-catalogue")]
    public Task<IActionResult> RemovalCatalogue() => Forward("removal-catalogue", HttpMethod.Get);

    [HttpGet("capabilities")]
    public Task<IActionResult> Capabilities() => Forward("capabilities", HttpMethod.Get);

    [HttpGet("personal-home")]
    public Task<IActionResult> Home() => Forward("personal-home", HttpMethod.Get);

    [HttpPost("{actionName}")]
    public Task<IActionResult> Post(string actionName) =>
        actionName is "search" or "episodes" or "select" or "cancel" or "acknowledge" or "removal-preview" or "item-removal-preview" or "remove" or "subtitle-search" or "subtitle-download" or "subtitle-status" or "personal-action" or "personal-movie" or "personal-next-up-action" or "music-search" or "music-artist" or "music-album" or "music-releases" or "music-select" or "music-removal-preview" or "music-remove" ? Forward(actionName, HttpMethod.Post) : Task.FromResult<IActionResult>(NotFound());

    private async Task<IActionResult> Forward(string action, HttpMethod method)
    {
        if (Request.ContentLength > 16384) return StatusCode(413);
        var port = int.Parse(Environment.GetEnvironmentVariable("MEDIA_RELEASE_PORT") ?? "6768");
        using var request = new HttpRequestMessage(method, $"http://127.0.0.1:{port}/{action}");
        foreach (var name in new[] { "Authorization", "X-Emby-Token" })
            if (Request.Headers.TryGetValue(name, out var value)) request.Headers.TryAddWithoutValidation(name, value.ToString());
        if (method == HttpMethod.Post)
        {
            // Bounded copy also covers chunked requests without a Content-Length header.
            using var body = new MemoryStream();
            byte[] chunk = new byte[4096];
            int count;
            while ((count = await Request.Body.ReadAsync(chunk)) > 0)
            {
                if (body.Length + count > 16384) return StatusCode(413);
                await body.WriteAsync(chunk.AsMemory(0, count));
            }
            request.Content = new ByteArrayContent(body.ToArray());
            request.Content.Headers.ContentType = new("application/json");
        }
        try
        {
            using var response = await Client.SendAsync(request);
            Response.Headers["Cache-Control"] = "no-store";
            return new ContentResult { StatusCode = (int)response.StatusCode, ContentType = "application/json", Content = await response.Content.ReadAsStringAsync() };
        }
        catch (HttpRequestException) { return StatusCode(502, new { error = "Release selection service is unavailable." }); }
        catch (TaskCanceledException) { return StatusCode(504, new { error = "Search timed out. Check Selected releases before trying a submission again." }); }
    }
}
