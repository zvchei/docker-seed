# dotnet

- `dotnet`: a .NET 10 SDK shell (interactive).
- `dotnet_app`: the same image (`extends`) running `dotnet run` from the project
  root. ASP.NET Core listens on `0.0.0.0:5000`, published on
  http://localhost:5000.

Containers run with a read-only root filesystem, so the recipe adds volumes for
every place the SDK writes: `~/.dotnet`, the NuGet package/config/HTTP caches,
`~/.templateengine` (`dotnet new`), `~/.aspnet/https` (dev certs), and a
`TMPDIR` that allows executables (MSBuild extracts and runs files there; `/tmp`
is `noexec`).

## Use

```bash
ds run dotnet                         # bash with the SDK
ds shell dotnet dotnet new webapi -o Api
ds up dotnet_app --project Api        # server: dotnet run --project Api → http://localhost:5000
```

`ds run` doesn't publish ports, so serve through `dotnet_app` with `ds up`.
Extra arguments are appended to `dotnet run`.

**Don't name the project directory `dotnet`.** The SDK lives in `~/dotnet`, and
the project volume is mounted at `~/$PROJECT`, so it would hide the SDK.
