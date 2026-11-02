{
  description = "Patches for Apple's iPod 3G (PP5002) firmware 2.3";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "aarch64-darwin" "x86_64-darwin" "x86_64-linux" "aarch64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in {
      devShells = forAllSystems (pkgs:
        let
          tools = with pkgs; [
            gcc-arm-embedded   # arm-none-eabi-{gcc,as,ld,objdump,objcopy} for the PP5002's ARM7TDMI cores
            gnumake            # loader/Makefile
            (python3.withPackages (ps: [ ps.unicorn ])) # patch/unpack scripts; unicorn runs osos functions in tools/emu
            unzip              # .ipsw files are zip archives
            unixtools.xxd      # hex dumps and diffs
            radare2            # disassembly / binary patching
          ];
        in {
          default = pkgs.mkShell { packages = tools; };

          # nix develop .#re: the same plus Ghidra for mapping Apple's osos image.
          re = pkgs.mkShell { packages = tools ++ [ pkgs.ghidra ]; };

          # nix develop .#emu: the same plus what the emupod tests need: Rust for emupod's core
          # (tools/emupod/setup.sh) and the tools that make test cards (tools/emupod/mkcards.py).
          emu = pkgs.mkShell { packages = tools ++ (with pkgs; [ cargo rustc mtools dosfstools sox lame ]); };
        });
    };
}
