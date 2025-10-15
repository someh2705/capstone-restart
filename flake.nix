{
  description = "capstone project";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";
    nixpkgs-unstable.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, nixpkgs-unstable, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        unstable = import nixpkgs-unstable { inherit system; };

        dependencies = with pkgs; [
          ns-3
        ];

        buildTools = with pkgs; [
          gcc

          cmake
          ninja
          pkg-config
        ];

        devTools = with unstable; [
          clang-tools
          neocmakelsp
          yaml-language-server
          uv
          ty
          ruff
          tcpdump
          wireshark

          gemini-cli
        ];

        python = pkgs.python3.withPackages (ps: with ps; [
          numpy
          pandas
          matplotlib
          pyyaml
          networkx
          python-lsp-server
          python-lsp-ruff
        ]);

      in
      {
        devShells.default = pkgs.mkShell {
          nativeBuildInputs = buildTools ++ devTools;
          buildInputs = [ python ] ++ dependencies;
        };
      });
}
