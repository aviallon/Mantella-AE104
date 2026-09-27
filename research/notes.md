# Mantella → Skyrim AE 1.7.104 — notes de portage

Date : 2026-09-27. Objectif : rendre le mod Mantella (Nexus 98631) fonctionnel
sur le runtime **Skyrim AE 1.7.104.0** (confirmé par `strings SkyrimSE.exe`),
puis livrer un **override FOMOD** (MO2/Amethyst) qui remplace proprement les
DLL périmées du mod de base.

## 1. Cartographie des sources

Le dépôt `art-from-the-machine/Mantella` est **uniquement le backend Python**
(STT → LLM → TTS). Aucune DLL. Le mod côté jeu est `Mantella-Spell`
(Nexus 98631) : `Mantella.esp`, sources Papyrus, et 3 DLL précompilées que son
propre README déclare périmées. Les **sources C++ des DLL** vivent dans 4 dépôts
séparés (tous clonés dans `~/Programing/Opensource/`) :

| Dépôt | DLL | Dépendances |
|---|---|---|
| `Leidtier/SKSE_HTTP` | `SKSE_HTTP.dll` | CLNG + cpr (→ curl) + nlohmann-json |
| `mikastamm/mantella-vanilla-dialogue` | `MantellaDialogue.dll` | CLNG (hooks `ShowSubtitle` via `RELOCATION_ID(19119,19521)` / `(36543,37544)`) |
| `art-from-the-machine/Mantella-SKSE-Launcher` | `MantellaLauncher.dll` | CLNG |
| `swwu/Mantella-Subtitles-Plugin-NG` | `MantellaSubtitles.dll` | CLNG |

Les 4 sont des projets CMake + vcpkg + CommonLibSSE-NG (`find_package(CommonLibSSE)`,
`add_commonlibsse_plugin`), donc **rebuildables**. Aucun n'a de workflow CI.

## 2. Diagnostic : pourquoi ça casse sur 1.7.104

- Les DLL livrées sont des plugins **CommonLibSSE-NG** résolvant leurs adresses
  via **Address Library** (chaînes visibles : *"Failed to locate an appropriate
  address library"*, *"incompatible with the address library available for this
  version of the game"*). Pas d'offsets runtime codés en dur.
- Le runtime 1.7.104 est livré avec une Address Library **V5**
  (`Data/SKSE/Plugins/versionlib-1-7-104-0.bin`, vérifié) — format différent
  (header 96 octets + tableau dense `uint32` indexé par ID).
- Les DLL embarquées sont compilées contre un CLNG **antérieur au support V5**
  (le registre vcpkg `colorglass` épinglé par les 4 dépôts est figé depuis
  2022, CLNG 3.6/3.7) → erreur type *"Unsupported address library format"*.
- **Réparation attendue** : rebâtir contre CLNG ≥ 6.6 (commit `98c8df05f` a
  introduit `kVersionIndependentEx_AddressLibraryV5`). On utilise **CLNG
  v6.8.0** (`alandtse/CommonLibVR` @ `44dd911`).

Limite honnête : Mantella n'était pas installé au moment du diagnostic (rien
dans les logs SKSE du prefix Proton), donc le mode de défaillance est **inféré**
de l'analyse binaire + des versions, pas lu dans un log. La vérification finale
devra confirmer le chargement en jeu.

## 3. Toolchain de build (Linux → MSVC ABI, pas de Wine pour compiler)

Flux officiel CLNG `examples/linux-cross-compile` (README du dépôt) :

- **sysroot MSVC/SDK** : `nix run nixpkgs#xwin -- --accept-license --cache-dir
  /tmp/xwin-cache splat --output /tmp/xwin-winsysroot --include-debug-libs
  --use-winsysroot-style --preserve-ms-arch-notation` (les deux flags sont
  requis pour `/winsysroot`). Scratch re-générable : `/tmp` OK.
- **vcpkg** : clone `~/.local/share/vcpkg` (outil via `nix shell nixpkgs#vcpkg`).
- **llvm-mingw** : `~/.local/share/llvm-mingw` (20260826) — sert uniquement à
  compiler le stand-in `fxc2` (shader compiler HLSL) que le port overlay
  `directxtk` fait tourner sous Wine. `LLVM_MINGW_BIN` est lu par le port.
- **triplet** : `x64-windows-clangcl` (CRT dynamique, libs statiques,
  release-only) qui chainloade `toolchain-linux-clangcl.cmake` de CLNG.
- **ports overlay** : `ports/commonlibsse-ng` (ce repo) + `custom-ports/directxtk`
  de CLNG (contournement Wine/fxc2).

### Pourquoi un port overlay `commonlibsse-ng`

Le registre `colorglass` (`vcpkg-configuration.json` des 4 plugins) plafonne à
CLNG 3.7.0 (2022-11) : pas de V5. Le port overlay tire CLNG **6.8.0** directement
(`vcpkg_from_github`, SHA512 épinglé) et répare deux défauts d'export amont :

1. `cmake/CommonLibSSE.cmake` (fonction `add_commonlibsse_plugin`) n'est jamais
   installé par les règles `install()` de CLNG → copié manuellement dans
   `share/CommonLibSSE` ;
2. `CommonLibSSEConfig.cmake` référence `Microsoft::DirectXTK` sans
   `find_dependency(directxtk)` → ajouté.

### Options CLNG choisies

`ENABLE_SKYRIM_SE=ON`, `ENABLE_SKYRIM_AE=ON`, `ENABLE_SKYRIM_VR=OFF` (aucun
plugin n'appelle l'API VR ; évite le sous-module openvr absent des tarballs
GitHub), `SKSE_SUPPORT_XBYAK=ON`, `SKSE_SUPPORT_PATCH_SAFETY=ON`,
`REX_OPTION_{INI,JSON,TOML}=OFF` (voir piège 9 — syntaxe MSVC-only ; aucun
plugin Mantella ne les utilise),
`BUILD_TESTS=OFF`. Les plugins s'annoncent via
`RuntimeCompatibility = VersionIndependence::AddressLibrary` (défaut de
`add_commonlibsse_plugin`, identique aux DLL d'origine).

## 4. Build

```sh
cd ~/Programing/Opensource/Mantella-AE104
tools/build.sh ~/Programing/Opensource/<plugin>
```

Le script s'auto-relance dans un `nix shell` (vcpkg, cmake, ninja, wine64,
git, curl, patch, llvm, file, stdenv.cc, clang-unwrapped, lld, pkg-config).
Il : copie les sources dans `/tmp/mantella-build/`, **réécrit**
`vcpkg-configuration.json` (baseline `microsoft/vcpkg` @ `07f48122`, 2026-09),
applique les patches de `patches/`, configure CMake avec l'outillage vcpkg,
build, puis **vérifie le PE** (exports `SKSEPlugin_*`, chaînes address library,
sha256). Sortie : `/tmp/mantella-build/out/*.dll`.

### Pièges rencontrés (tous documentés pour ne pas les retrouver)

1. **Versions vcpkg incomparables** : les contraintes `version>=` reprises de
   `vcpkg.json` amont cassent la résolution (`rapidcsv@8.90` scheme *relaxed*
   vs `9.07` scheme *string*). Le port overlay les a supprimées.
2. **`~/.nix-profile/bin/c++` est cassé** (pas de `Scrt1.o`) : la détection
   compilateur *hôte* de vcpkg échoue. → `nixpkgs#stdenv.cc` dans le shell.
3. **`clang-cl` absent du shell** : le toolchain CLNG le cherche par nom.
   → `nixpkgs#llvmPackages.clang-unwrapped` + `nixpkgs#lld` (`lld-link`).
4. **`pkg-config` manquant** : `vcpkg_fixup_pkgconfig` (port `fmt`) l'exige.
5. **`nixpkgs#wine` est un build 32 bits** : il refuse le `fxc2.exe` 64 bits
   ("Bad EXE format") que le port overlay `directxtk` compile avec llvm-mingw.
   → `nixpkgs#wine64` (fournit `wine`, testé : fxc2 s'exécute). Préfixe wine
   re-créé à chaque run (un préfixe créé par un autre "bitness" est rejeté).
6. Les includes à antislash de SKSE_HTTP (`<cpr\cpr.h>`) passent tels quels
   sous clang-cl (testé) : aucun patch nécessaire.
7. **`FETCHCONTENT_FULLY_DISCONNECTED=ON` est forcé par vcpkg** pour tout
   build de port (un port ne doit pas fetcher ses deps). CLNG vendorise pourtant
   le décodeur hde64 de MinHook via FetchContent (feature `SKSE_SUPPORT_PATCH_SAFETY`).
   → le portfile pré-fetch MinHook (v1.3.4, SHA512 épinglé) et passe
   `-DFETCHCONTENT_SOURCE_DIR_HDE64=<chemin>` à FetchContent.
8. Les try_compile (ex. `check_ipo_supported`) perdent les linker flags
   `/winsysroot` dans le projet enfant (garde `if(NOT CMAKE_CXX_FLAGS MATCHES
   "winsysroot")` du toolchain) : le test IPO échoue, mais c'est bénin — le
   vrai lien du projet principal, lui, a bien ses flags.
9. **Syntaxe MSVC-only dans CLNG** : `src/REX/REX.cpp` définit ses templates
   avec `template <class T> void SettingLoad<T>(...)` (spécialisation partielle
   de fonction — extension MSVC, rejetée par clang-cl). Gardé par
   `#ifdef REX_OPTION_*` → on compile avec `REX_OPTION_{INI,JSON,TOML}=OFF`.
   Aucun plugin Mantella n'utilise `REX::INI/JSON/TOML` (vérifié par rg).
10. **Macros `min`/`max` de Windows** : `minwindef.h` remplace `std::max` par
    une macro (`MantellaDialogueIniConfig.h` : `std::max(1, atoi(value))`).
    → defines globaux du build : `/DUNICODE /D_UNICODE /DNOMINMAX
    /D_CRT_SECURE_NO_WARNINGS` (UNICODE indispensable aussi : le code appelle
    les API Win32 larges ; sur Windows c'est vcpkg `VCPKG_SET_CHARSET_FLAG`
    qui les fournit, absent de la passe consommateur).
11. Le projet principal doit recevoir explicitement
    `-DVCPKG_CHAINLOAD_TOOLCHAIN_FILE=...` : le triplet ne l'applique qu'aux
    ports vcpkg, pas au consumer (sinon c'est le g++ hôte qui compile).
12. **fmt 12 n'accepte plus les conversions implicites** : logger un
    `RE::BSString` directement (`SKSE::log::debug("...{}", subtitle)`) passait
    avec les vieux fmt (via conversion), plus maintenant
    (`type_is_unformattable_for`). → patch minimal `.c_str()` (diagnostic
    seul), voir `patches/Mantella-Subtitles-Plugin-NG-01-fmt12-bsstring.patch`.
13. **Casse des includes SDK** : `#include <Shlobj.h>` (le SDK s'appelle
    `shlobj.h`) — le classique "ça marche sur Windows, pas sur Linux".
    → patch d'une ligne. Alternative générale (suggérée par l'utilisateur) :
    builder dans un répertoire **casefold** bcachefs, qui rend la résolution
    d'includes insensible à la casse sans patch — utile si des libs tierces
    (curl/cpr) en encaissent aussi ; l'inverse est vrai pour les *données*
    livrées : le casefold masquerait des bugs de casse de fichiers de données.
14. **cpr se flagge lui-même** : `-Wall -Wextra -Wpedantic -Werror` pour tout
    compilateur non-MSVC, et `-Wpedantic` sous clang-cl casse le C++23
    ("incompatible with C++98"). → `target_compile_options(cpr PRIVATE
    -Wno-error ...)` après le FetchContent (patch sur le CMakeLists de
    SKSE_HTTP).

## 5. Packaging (attendu)

FOMOD (zip + `fomod/ModuleConfig.xml`) contenant `SKSE/Plugins/*.dll` aux mêmes
chemins que le mod de base, installé **après** Mantella → override propre dans
MO2/Amethyst. Fichiers à plat à la racine du zip pour les gestionnaires qui
ignorent le FOMOD.

## 6. Vérification (à ne pas confondre avec "ça compile")

- PE : exports `SKSEPlugin_Load/Query/Version`, `RuntimeCompatibility` = Address
  Library (byte 0 bit 0 du struct `SKSEPlugin_Version`).
- En jeu : logs SKSE dans le prefix Proton
  (`~/.local/share/Steam/steamapps/compatdata/489830/pfx/drive_c/users/steamuser/Documents/My Games/Skyrim Special Edition/SKSE/`),
  compter les erreurs *avant/après*, pas seulement le PASS.
