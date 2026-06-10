{
  description = "A universal local web server for reading PDFs, EPUBs, and DOCX";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      supportedSystems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
      nixpkgsFor = forAllSystems (system: import nixpkgs { inherit system; });
    in
    {
      packages = forAllSystems (system:
        let
          pkgs = nixpkgsFor.${system};
        in
        {
          docviewer = pkgs.python3Packages.buildPythonApplication {
            pname = "docviewer";
            version = "1.7.0";
            pyproject = true;

            src = ./.;

            nativeBuildInputs = [
              pkgs.python3Packages.hatchling
            ];

            propagatedBuildInputs = with pkgs.python3Packages; [
              fastapi
              uvicorn
              mammoth
              python-multipart
              markdown
            ];

            meta = with pkgs.lib; {
              description = "A universal local web server for reading PDFs, EPUBs, and DOCX";
              license = licenses.asl20;
              mainProgram = "docviewer";
            };
          };
          default = self.packages.${system}.docviewer;
        }
      );

      homeManagerModules = {
        docviewer = { config, lib, pkgs, ... }:
          let
            cfg = config.services.docviewer;
          in
          {
            options.services.docviewer = {
              enable = lib.mkEnableOption "docviewer service";
              package = lib.mkOption {
                type = lib.types.package;
                default = self.packages.${pkgs.system}.default;
                defaultText = lib.literalExpression "inputs.self.packages.\${pkgs.system}.default";
                description = "The docviewer package to use.";
              };
              port = lib.mkOption {
                type = lib.types.port;
                default = 2005;
                description = "Port to run the docviewer server on.";
              };
            };

            config = lib.mkIf cfg.enable {
              home.packages = [ cfg.package ];

              systemd.user.services.docviewer = lib.mkIf pkgs.stdenv.isLinux {
                Unit = {
                  Description = "Docviewer universal local web server";
                  After = [ "graphical-session-pre.target" ];
                  PartOf = [ "graphical-session.target" ];
                };

                Service = {
                  ExecStart = "${cfg.package}/bin/docviewer serve --port ${builtins.toString cfg.port}";
                  Restart = "on-failure";
                };

                Install = {
                  WantedBy = [ "graphical-session.target" ];
                };
              };
            };
          };
        default = self.homeManagerModules.docviewer;
      };
    };
}
