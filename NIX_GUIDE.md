# Nix & Home Manager Installation Guide

This project supports installation via **Nix Flakes** and **Home Manager**. You can install `docviewer` either as a standalone package or configure it to run as a background service managed by `systemd`.

---

## 1. Prerequisites
Ensure you have Nix installed with flakes enabled. If flakes are not enabled yet, add the following to your `/etc/nix/nix.conf` or `~/.config/nix/nix.conf`:
```conf
experimental-features = nix-command flakes
```

---

## 2. Setting Up the Flake Input

In your Home Manager or system flake configuration (usually `flake.nix` in `~/.config/home-manager/` or `/etc/nixos/`), add this repository to your `inputs`:

### For Local Testing
If you want to test the local code directly from your disk:
```nix
inputs = {
  nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  home-manager.url = "github:nix-community/home-manager";
  home-manager.inputs.nixpkgs.follows = "nixpkgs";

  # Point to the local directory of docviewer
  docviewer.url = "git+file:///run/host/home/dkchw/Documents/Code/Ongoing/Repo/browser-docviewer";
  # Alternatively, use "path:" if you don't want git history checks:
  # docviewer.url = "path:/run/host/home/dkchw/Documents/Code/Ongoing/Repo/browser-docviewer";
};
```

### For Production / Remote Usage
Once committed/pushed to GitHub:
```nix
inputs = {
  nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  home-manager.url = "github:nix-community/home-manager";
  home-manager.inputs.nixpkgs.follows = "nixpkgs";

  docviewer.url = "github:dkchw/browser-docviewer";
};
```

Ensure your outputs expose `inputs` so that they can be used within your Home Manager configuration:
```nix
outputs = { self, nixpkgs, home-manager, docviewer, ... }@inputs: {
  # Your configuration setup passes inputs down to home-manager
};
```

---

## 3. Installation Options

### Option A: Install via the Home Manager Module (Recommended)
This option installs `docviewer` and configures it to run automatically in the background as a user-level `systemd` service when you log in.

1. **Import the module** in your Home Manager configuration file (e.g., `home.nix`):
   ```nix
   { config, pkgs, inputs, ... }:

   {
     imports = [
       inputs.docviewer.homeManagerModules.default
     ];

     # Configure and enable the service
     services.docviewer = {
       enable = true;
       port = 2005; # Optional (default: 2005)
     };
   }
   ```

2. **Rebuild your Home Manager configuration**:
   ```bash
   home-manager switch
   ```

3. **Check the service status**:
   ```bash
   systemctl --user status docviewer
   ```

---

### Option B: Package-Only Installation (CLI Only)
If you do not want `docviewer` running as a background service and only want the CLI tool (`docviewer` command) available in your shell:

1. **Add the package** directly to your `home.packages`:
   ```nix
   { config, pkgs, inputs, ... }:

   {
     home.packages = [
       inputs.docviewer.packages.${pkgs.system}.default
     ];
   }
   ```

2. **Rebuild your Home Manager configuration**:
   ```bash
   home-manager switch
   ```

3. **Run the tool manually**:
   * **Start server:** `docviewer serve --port 2005`
   * **Add a document:** `docviewer add /path/to/document.pdf`
   * **Open a document temporarily:** `docviewer open /path/to/document.pdf`

---

## 4. Run directly via Nix (Ad-hoc)
You can also run the tool directly without adding it to your Home Manager configuration:

```bash
# Start the web interface/server
nix run git+file:///run/host/home/dkchw/Documents/Code/Ongoing/Repo/browser-docviewer -- serve

# Open a specific file temporarily
nix run git+file:///run/host/home/dkchw/Documents/Code/Ongoing/Repo/browser-docviewer -- open /path/to/file.pdf
```
