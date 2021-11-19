# nix-build ./ -o ./env

let
  pkgs = import <nixpkgs> { };

  mach-nix = import (builtins.fetchGit {
    url = "https://github.com/DavHau/mach-nix/";
    ref = "refs/tags/3.3.0";
  }) {
    inherit pkgs;
    python = "python37";
  };

  requirements =  ''
    setuptools
    ewmh
    pynput
    psutil
  '';

in

mach-nix.mkPython {
  requirements = requirements;
}
