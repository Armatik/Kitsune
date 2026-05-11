#!/usr/bin/env bash
# bundle-macos.sh - Creates a self-contained Kitsune.app for macOS distribution
set -euo pipefail
cd "$(dirname "$0")/.."

BREW="${HOMEBREW_PREFIX:-/opt/homebrew}"

# Auto-detect the highest installed Homebrew Python 3.x
PY_VER="${PYTHON_VERSION:-}"
if [ -z "$PY_VER" ]; then
    PY_VER="$(find "$BREW/Cellar" -maxdepth 1 -name 'python@3.*' -type d \
        | sed 's|.*/python@||' | sort -t. -k1,1n -k2,2n | tail -1)"
fi
if [ -z "$PY_VER" ]; then
    echo "ERROR: No Homebrew python@3.x found. Install with: brew install python@3.13" >&2
    exit 1
fi

APP_VERSION="$(grep "version:" meson.build | head -1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+")"
APP_NAME="Kitsune"
APP_ID="net.armatik.Kitsune"
DIST_DIR="dist"

# Find Python framework
PY_CELLAR="$(find "$BREW/Cellar/python@$PY_VER" -maxdepth 1 -mindepth 1 -type d | head -1)"
PY_FW_SRC="$PY_CELLAR/Frameworks/Python.framework"
PY_ROOT="$PY_FW_SRC/Versions/$PY_VER"

APP="$DIST_DIR/$APP_NAME.app"
CONTENTS="$APP/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
FRAMEWORKS="$CONTENTS/Frameworks"

echo "==> Kitsune $APP_VERSION macOS bundle"
echo "    Python: $PY_ROOT"

# ── 1. Clean & create structure ──────────────────────────────────────────────
chmod -R u+w "$DIST_DIR" 2>/dev/null || true
rm -rf "$DIST_DIR"
mkdir -p "$MACOS" "$RESOURCES" "$FRAMEWORKS"

# ── 2. Build the app ─────────────────────────────────────────────────────────
echo "==> Building app (release)..."
if [ -d "_build" ]; then
    PATH="$BREW/bin:$PATH" command meson configure _build \
        -Dprefix="$(pwd)/_build/testdir" \
        -Dbuildtype=release 2>/dev/null || true
else
    PATH="$BREW/bin:$PATH" command meson setup _build \
        --prefix="$(pwd)/_build/testdir" \
        --buildtype=release
fi
PATH="$BREW/bin:$PATH" ninja -C _build install

# ── 3. Copy app data ─────────────────────────────────────────────────────────
echo "==> Copying app data..."
cp -r _build/testdir/share/kitsune/. "$RESOURCES/app/"
mkdir -p "$RESOURCES/locale" "$RESOURCES/glib-2.0"
cp -r _build/testdir/share/locale/. "$RESOURCES/locale/" 2>/dev/null || true
cp -r _build/testdir/share/glib-2.0/schemas "$RESOURCES/glib-2.0/"
for schema in "$BREW/share/glib-2.0/schemas/org.gtk.gtk4.Settings"*.xml; do
    [ -f "$schema" ] && cp "$schema" "$RESOURCES/glib-2.0/schemas/"
done
"$BREW/bin/glib-compile-schemas" "$RESOURCES/glib-2.0/schemas/"

# ── 4. Copy icons ─────────────────────────────────────────────────────────────
echo "==> Copying icons..."
mkdir -p "$RESOURCES/icons/hicolor/scalable/apps"
cp "data/icons/hicolor/scalable/apps/$APP_ID.svg" \
   "$RESOURCES/icons/hicolor/scalable/apps/"

# Action icons
mkdir -p "$RESOURCES/icons/hicolor/scalable/actions"
cp _build/testdir/share/icons/hicolor/scalable/actions/*.svg \
   "$RESOURCES/icons/hicolor/scalable/actions/" 2>/dev/null || true

# Adwaita theme — symbolic only
ADWAITA_SRC="$BREW/share/icons/Adwaita"
mkdir -p "$RESOURCES/icons/Adwaita"
if [ -d "$ADWAITA_SRC/symbolic" ]; then
    cp -r "$ADWAITA_SRC/symbolic" "$RESOURCES/icons/Adwaita/"
elif [ -d "$ADWAITA_SRC/scalable" ]; then
    cp -r "$ADWAITA_SRC/scalable" "$RESOURCES/icons/Adwaita/"
fi
cp "$ADWAITA_SRC/index.theme" "$RESOURCES/icons/Adwaita/" 2>/dev/null || true

cp "$BREW/share/icons/hicolor/index.theme" "$RESOURCES/icons/hicolor/" 2>/dev/null || true
"$BREW/bin/gtk4-update-icon-cache" -q -t -f "$RESOURCES/icons/hicolor" 2>/dev/null || true

# ── 5. Bundle Python.framework ───────────────────────────────────────────────
echo "==> Bundling Python.framework..."
mkdir -p "$FRAMEWORKS/Python.framework"
(
    cd "$(dirname "$PY_FW_SRC")"
    tar cf - \
        --exclude='Python.framework/_CodeSignature' \
        --exclude='Python.framework/Versions/*/_CodeSignature' \
        "$(basename "$PY_FW_SRC")"
) | tar xf - -C "$FRAMEWORKS/"
BUNDLED_PY_FW="$FRAMEWORKS/Python.framework"
BUNDLED_PY="$BUNDLED_PY_FW/Versions/$PY_VER"
chmod -R u+w "$BUNDLED_PY_FW/"

rm -rf "$BUNDLED_PY/include"
rm -rf "$BUNDLED_PY/share"
find "$BUNDLED_PY/lib/python$PY_VER" -name "*.pyc" -delete 2>/dev/null || true
find "$BUNDLED_PY/lib/python$PY_VER" \( -name "test" -o -name "tests" \) \
    -type d -exec rm -rf {} + 2>/dev/null || true
find "$BUNDLED_PY/lib/python$PY_VER" -name "__pycache__" \
    -type d -exec rm -rf {} + 2>/dev/null || true

PY_SITEPACKAGES="$BUNDLED_PY/lib/python$PY_VER/site-packages"
SYS_SITEPACKAGES="$BREW/lib/python$PY_VER/site-packages"
if [ -L "$PY_SITEPACKAGES" ]; then
    rm "$PY_SITEPACKAGES"
    mkdir "$PY_SITEPACKAGES"
fi

# Copy Python packages and their installed dependency closure.
echo "==> Adding Python packages..."
SYS_SITEPACKAGES="$SYS_SITEPACKAGES" PY_SITEPACKAGES="$PY_SITEPACKAGES" \
"$PY_ROOT/bin/python$PY_VER" <<'PY_COPY_DEPS'
import importlib.metadata as metadata
import os
import re
import shutil
from pathlib import Path

site = Path(os.environ["SYS_SITEPACKAGES"]).resolve()
dest = Path(os.environ["PY_SITEPACKAGES"]).resolve()

seeds = [
    "PyGObject",
    "pycairo",
    "keyring",
    "pyobjc-core",
    "pyobjc-framework-Cocoa",
    "pyobjc-framework-MediaPlayer",
    "pyobjc-framework-AVFoundation",
    "pyobjc-framework-CoreMedia",
    "pyobjc-framework-CoreAudio",
    "pyobjc-framework-Quartz",
]

manual_modules = [
    "gi",
    "cairo",
    "objc",
    "Foundation",
    "CoreFoundation",
    "AppKit",
    "Cocoa",
    "MediaPlayer",
    "AVFoundation",
    "CoreMedia",
    "CoreAudio",
    "Quartz",
    "keyring",
    "jaraco",
    "more_itertools",
]


def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_name(req):
    match = re.match(r"\s*([A-Za-z0-9_.-]+)", req)
    return match.group(1) if match else None


def requirement_applies(req):
    marker = req.split(";", 1)[1] if ";" in req else ""
    marker = marker.lower()
    if "extra ==" in marker:
        return False
    if "sys_platform" in marker and "darwin" not in marker:
        return False
    if "platform_system" in marker and "darwin" not in marker and "macos" not in marker:
        return False
    if "python_version" in marker and "< \"3.12\"" in marker:
        return False
    return True


available = {}
for dist in metadata.distributions(path=[str(site)]):
    name = dist.metadata.get("Name")
    if name:
        available[norm(name)] = dist


def copy_path(src, rel):
    target = dest / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, target, dirs_exist_ok=True, symlinks=True)
    else:
        shutil.copy2(src, target, follow_symlinks=False)


def copy_distribution(dist):
    for file in dist.files or ():
        src = Path(dist.locate_file(file)).resolve()
        if not src.exists():
            continue
        try:
            rel = src.relative_to(site)
        except ValueError:
            continue
        copy_path(src, rel)


queue = list(seeds)
seen = set()
copied = []

while queue:
    name = queue.pop(0)
    key = norm(name)
    if key in seen:
        continue
    seen.add(key)

    dist = available.get(key)
    if not dist:
        print(f"   WARNING: Python distribution not found: {name}")
        continue

    copy_distribution(dist)
    copied.append(dist.metadata.get("Name", name))

    for req in dist.requires or ():
        dep = requirement_name(req)
        if dep and requirement_applies(req):
            queue.append(dep)

for module in manual_modules:
    src = site / module
    if src.exists():
        copy_path(src, Path(module))

print("   Copied distributions:", ", ".join(sorted(set(copied))))
PY_COPY_DEPS

# C-extension single-file packages
find "$SYS_SITEPACKAGES" -maxdepth 1 -name "*.so" \
    -exec cp {} "$PY_SITEPACKAGES/" \; 2>/dev/null || true
# .dist-info for importlib.metadata
find "$SYS_SITEPACKAGES" -maxdepth 1 -name "*.dist-info" -exec cp -r {} "$PY_SITEPACKAGES/" \; 2>/dev/null || true

# ── 6. Copy GObject typelibs ─────────────────────────────────────────────────
echo "==> Copying typelibs..."
mkdir -p "$RESOURCES/girepository-1.0"
for tl in Adw-1 Gdk-4.0 GdkMacos-4.0 GdkPixbuf-2.0 GdkPixdata-2.0 \
          Gio-2.0 GioUnix-2.0 GLib-2.0 GLibUnix-2.0 GObject-2.0 \
          Gsk-4.0 Gtk-4.0 Pango-1.0 PangoCairo-1.0 PangoFc-1.0 PangoFT2-1.0 \
          Gst-1.0 GstAudio-1.0 GstBase-1.0 GstGL-1.0 GstPbutils-1.0 \
          GstPlay-1.0 GstTag-1.0 GstVideo-1.0 GstApp-1.0 GstAllocators-1.0 \
          Soup-3.0; do
    src="$BREW/lib/girepository-1.0/$tl.typelib"
    [ -f "$src" ] && cp "$src" "$RESOURCES/girepository-1.0/"
done

# ── 7. Copy GTK4 + GStreamer + deps dylibs ───────────────────────────────────
echo "==> Copying GTK4 and GStreamer dylibs..."
copy_dylib() {
    local pkg="$1"
    local stem="$2"
    local found=""
    local dirs=("$BREW/lib")
    [ -d "$BREW/opt/$pkg/lib" ] && dirs=("$BREW/opt/$pkg/lib" "${dirs[@]}")
    found="$(find "${dirs[@]}" -maxdepth 1 -name "${stem}*.dylib" 2>/dev/null \
        | sort -V | tail -1)" || true
    if [ -n "$found" ]; then
        cp -n "$found" "$FRAMEWORKS/" 2>/dev/null || true
    else
        echo "  WARNING: not found: $pkg/$stem"
    fi
}

copy_dylib "gtk4"        "libgtk-4"
copy_dylib "libadwaita"  "libadwaita-1"
copy_dylib "glib"        "libglib-2.0"
copy_dylib "glib"        "libgobject-2.0"
copy_dylib "glib"        "libgio-2.0"
copy_dylib "glib"        "libgmodule-2.0"
copy_dylib "glib"        "libgirepository-2.0"
copy_dylib "pango"       "libpango-1.0"
copy_dylib "pango"       "libpangocairo-1.0"
copy_dylib "pango"       "libpangoft2-1.0"
copy_dylib "cairo"       "libcairo.2"
copy_dylib "cairo"       "libcairo-gobject.2"
copy_dylib "cairo"       "libcairo-script-interpreter"
copy_dylib "harfbuzz"    "libharfbuzz.0"
copy_dylib "harfbuzz"    "libharfbuzz-subset"
copy_dylib "fribidi"     "libfribidi"
copy_dylib "gdk-pixbuf"  "libgdk_pixbuf-2.0"
copy_dylib "libepoxy"    "libepoxy"
copy_dylib "graphene"    "libgraphene-1.0"
copy_dylib "fontconfig"  "libfontconfig"
copy_dylib "freetype"    "libfreetype"
copy_dylib "gettext"     "libintl"
copy_dylib "appstream"   "libappstream"
copy_dylib "libpng"      "libpng16"
copy_dylib "jpeg-turbo"  "libjpeg"
copy_dylib "libtiff"     "libtiff"
copy_dylib "webp"        "libwebp.7"
copy_dylib "webp"        "libwebpdemux"
copy_dylib "pcre2"       "libpcre2-8"
copy_dylib "lzo"         "liblzo2"
copy_dylib "pixman"      "libpixman-1"
copy_dylib "brotli"      "libbrotlidec"
copy_dylib "brotli"      "libbrotlicommon"

# GStreamer libraries — copy all libgst*.dylib from Homebrew
# (plugins link against secondary libs like libgstnet, libgstrtp, etc.)
find -L "$BREW/lib" -maxdepth 1 -type f -name "libgst*.dylib" \
    -exec cp -n {} "$FRAMEWORKS/" \; 2>/dev/null || true

# Soup
copy_dylib "libsoup"     "libsoup-3.0"

# Use dylibbundler to recursively collect transitive deps
echo "==> Running dylibbundler..."
SEARCH_FLAGS=(
    -s "$BREW/lib"
    -s "$BREW/opt/gtk4/lib"
    -s "$BREW/opt/libadwaita/lib"
    -s "$BREW/opt/glib/lib"
    -s "$BREW/opt/pango/lib"
    -s "$BREW/opt/cairo/lib"
    -s "$BREW/opt/harfbuzz/lib"
    -s "$BREW/opt/gdk-pixbuf/lib"
    -s "$BREW/opt/fontconfig/lib"
    -s "$BREW/opt/freetype/lib"
    -s "$BREW/opt/gettext/lib"
    -s "$BREW/opt/graphene/lib"
    -s "$BREW/opt/libepoxy/lib"
    -s "$BREW/opt/fribidi/lib"
    -s "$BREW/opt/libpng/lib"
    -s "$BREW/opt/jpeg-turbo/lib"
    -s "$BREW/opt/libtiff/lib"
    -s "$BREW/opt/appstream/lib"
    -s "$BREW/opt/pcre2/lib"
    -s "$BREW/opt/lzo/lib"
    -s "$BREW/opt/pixman/lib"
    -s "$BREW/opt/brotli/lib"
    -s "$BREW/opt/webp/lib"
    -s "$BREW/opt/gstreamer/lib"
    -s "$BREW/opt/libsoup/lib"
    -i /usr/lib
    -i /System
)

# ── 8. GStreamer plugins (copy BEFORE dylibbundler) ──────────────────────────
echo "==> Copying GStreamer plugins..."
GST_DEST="$RESOURCES/gstreamer-1.0"
mkdir -p "$GST_DEST"
find -L "$BREW/lib/gstreamer-1.0" -maxdepth 1 -type f -name "*.dylib" \
    -exec cp {} "$GST_DEST/" \;

# gtk4paintablesink lives in a separate dir on Homebrew
if [ -d "$BREW/lib/gstreamer-1.0-gtk4" ]; then
    cp -n "$BREW/lib/gstreamer-1.0-gtk4/"*.dylib "$GST_DEST/" 2>/dev/null || true
fi

# gst-plugin-scanner must be inside the bundle so Gst.init() can run it
GST_SCANNER_SRC="$(find "$BREW/Cellar/gstreamer" -path '*/libexec/gstreamer-1.0/gst-plugin-scanner' 2>/dev/null | head -1)"
if [ -n "$GST_SCANNER_SRC" ] && [ -f "$GST_SCANNER_SRC" ]; then
    mkdir -p "$RESOURCES/libexec/gstreamer-1.0"
    cp "$GST_SCANNER_SRC" "$RESOURCES/libexec/gstreamer-1.0/"
    chmod +x "$RESOURCES/libexec/gstreamer-1.0/gst-plugin-scanner"
    echo "   gst-plugin-scanner copied"
else
    echo "   WARNING: gst-plugin-scanner not found"
fi

# Copy CA certificates for Soup3 HTTPS
mkdir -p "$RESOURCES/ssl"
if [ -f "$BREW/etc/ca-certificates/cert.pem" ]; then
    cp "$BREW/etc/ca-certificates/cert.pem" "$RESOURCES/ssl/cert.pem"
fi

SO_FILES=()
for so in "$PY_SITEPACKAGES/gi/_gi.cpython"*".so" \
          "$PY_SITEPACKAGES/gi/_gi_cairo.cpython"*".so" \
          "$PY_SITEPACKAGES/cairo/_cairo.cpython"*".so"; do
    [ -f "$so" ] && SO_FILES+=(-x "$so")
done

# GStreamer plugins must also be processed so their deps are bundled
GST_PLUGIN_FILES=()
for plugin in "$GST_DEST"/*.dylib; do
    [ -f "$plugin" ] && GST_PLUGIN_FILES+=(-x "$plugin")
done

# Also include all pre-copied dylibs so dylibbundler fixes their install
# names and brings in their transitive dependencies (e.g. libxmlb for
# libappstream, libavif for gdk-pixbuf loaders, etc.)
FRAMEWORK_DYLIBS=()
for dylib in "$FRAMEWORKS"/*.dylib; do
    [ -f "$dylib" ] && FRAMEWORK_DYLIBS+=(-x "$dylib")
done

dylibbundler -b -of \
    -x "$BUNDLED_PY/bin/python$PY_VER" \
    ${SO_FILES[@]+"${SO_FILES[@]}"} \
    ${GST_PLUGIN_FILES[@]+"${GST_PLUGIN_FILES[@]}"} \
    ${FRAMEWORK_DYLIBS[@]+"${FRAMEWORK_DYLIBS[@]}"} \
    -d "$FRAMEWORKS/" \
    -p "@executable_path/../Frameworks/" \
    "${SEARCH_FLAGS[@]}" 2>/dev/null || true

# dylibbundler may add duplicate LC_RPATH entries (one per existing rpath),
# and macOS refuses to dlopen() binaries with duplicate rpaths.
# Remove duplicates, keeping the first occurrence.
echo "==> Deduplicating LC_RPATH entries..."
dedup_rpaths() {
    local f="$1"
    local all_rpaths dupes dup count to_remove
    all_rpaths=$(otool -l "$f" | awk '/cmd LC_RPATH/{getline; getline; print $2}')
    dupes=$(echo "$all_rpaths" | sort | uniq -d)
    for dup in $dupes; do
        count=$(echo "$all_rpaths" | grep -F -c "$dup")
        to_remove=$((count - 1))
        for i in $(seq 1 $to_remove); do
            install_name_tool -delete_rpath "$dup" "$f" 2>/dev/null || true
        done
    done
}

find "$FRAMEWORKS" "$RESOURCES/gstreamer-1.0" \
     "$PY_SITEPACKAGES" -type f \( -name "*.dylib" -o -name "*.so" \) \
     -print0 2>/dev/null | while IFS= read -r -d '' f; do
    dedup_rpaths "$f"
done

# ── 9. gdk-pixbuf loaders ────────────────────────────────────────────────────
echo "==> Copying pixbuf loaders..."
PIXBUF_SRC="$BREW/lib/gdk-pixbuf-2.0/2.10.0/loaders"
PIXBUF_DEST="$RESOURCES/gdk-pixbuf/2.10.0/loaders"
mkdir -p "$PIXBUF_DEST"
find -L "$PIXBUF_SRC" \( -name "*.so" -o -name "*.dylib" \) \
    -exec cp -L {} "$PIXBUF_DEST/" \; 2>/dev/null || true

LOADERS_CACHE="$RESOURCES/gdk-pixbuf/loaders.cache"
"$BREW/bin/gdk-pixbuf-query-loaders" "$PIXBUF_DEST/"*.so > "$LOADERS_CACHE" 2>/dev/null || true
# Replace absolute paths with @RESOURCES@ placeholder (replaced at runtime)
sed -i '' "s|$(pwd)/$RESOURCES|@RESOURCES@|g" "$LOADERS_CACHE" 2>/dev/null || true
sed -i '' "s|$BREW/lib/gdk-pixbuf-2.0|@RESOURCES@/gdk-pixbuf|g" "$LOADERS_CACHE" 2>/dev/null || true
sed -i '' "s|$RESOURCES|@RESOURCES@|g" "$LOADERS_CACHE" 2>/dev/null || true

# ── 9b. Fix remaining Homebrew references in ALL dylibs/so ─────────────────────
# dylibbundler only fixes binaries passed with -x and their directly-copied
# transitive deps. Pre-copied dylibs, .so extensions, and gdk-pixbuf loaders
# retain their Homebrew install names. Now that ALL files are in place,
# deduplicate rpaths and rewrite all Homebrew references.
echo "==> Fixing leftover Homebrew references..."
FIXED_COUNT=0
while IFS= read -r -d '' file; do
    dedup_rpaths "$file"
    base=$(basename "$file")

    # Fix LC_ID_DYLIB (own install name)
    current_id=$(otool -D "$file" 2>/dev/null | tail -1)
    if [ -n "$current_id" ] && [ "$current_id" != "@executable_path/../Frameworks/$base" ] \
       && echo "$current_id" | grep -q "$BREW"; then
        install_name_tool -id "@executable_path/../Frameworks/$base" "$file" 2>/dev/null || true
    fi

    # Fix LC_LOAD_DYLIB entries referencing Homebrew
    otool -L "$file" 2>/dev/null | awk '/^\t\/opt\/homebrew/ {print $1}' | while read -r dep; do
        dep_base=$(basename "$dep")
        install_name_tool -change "$dep" "@executable_path/../Frameworks/$dep_base" "$file" 2>/dev/null || true
    done
    FIXED_COUNT=$((FIXED_COUNT + 1))
done < <(find "$FRAMEWORKS" "$RESOURCES/gstreamer-1.0" "$RESOURCES/gdk-pixbuf" "$PY_SITEPACKAGES" \
    -type f \( -name "*.dylib" -o -name "*.so" \) -print0 2>/dev/null)
echo "   Processed $FIXED_COUNT files"

# ── 10. Create Python launch script ──────────────────────────────────────────
echo "==> Creating Python launcher..."
cat > "$RESOURCES/launch.py" << PYEOF
import os, sys, signal, gettext

_macos = os.path.dirname(os.path.abspath(__file__))
_bundle = os.path.dirname(_macos)
_resources = os.path.join(_bundle, "Resources")

pkgdatadir = os.path.join(_resources, "app")
localedir  = os.path.join(_resources, "locale")

sys.path.insert(1, pkgdatadir)
signal.signal(signal.SIGINT, signal.SIG_DFL)
gettext.bindtextdomain("kitsune", localedir)
gettext.textdomain("kitsune")
gettext.install("kitsune", localedir)

if "--debug" in sys.argv:
    import logging
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.DEBUG)
    sys.argv.remove("--debug")
    os.environ.setdefault("GST_DEBUG", "2")

import gi
from gi.repository import Gio
gresource = os.path.join(pkgdatadir, "net.armatik.Kitsune.gresource")
Gio.Resource.load(gresource)._register()

from kitsune.application import KitsuneApplication
sys.exit(KitsuneApplication(version="$APP_VERSION").run(sys.argv))
PYEOF

# ── 11. Create shell launcher ─────────────────────────────────────────────────
echo "==> Creating shell launcher..."
cat > "$MACOS/kitsune" << LAUNCHER_EOF
#!/usr/bin/env bash
DIR="\$(cd "\$(dirname "\$0")" && pwd)"
BUNDLE="\$(dirname "\$DIR")"
RESOURCES="\$BUNDLE/Resources"
FRAMEWORKS="\$BUNDLE/Frameworks"
PY_FW="\$FRAMEWORKS/Python.framework/Versions/$PY_VER"
PY_BIN="\$PY_FW/bin/python$PY_VER"

LOADERS_CACHE_TEMPLATE="\$RESOURCES/gdk-pixbuf/loaders.cache"
LOADERS_CACHE_DIR="\${TMPDIR:-/tmp}/$APP_ID"
LOADERS_CACHE="\$LOADERS_CACHE_DIR/gdk-pixbuf-loaders.cache"
mkdir -p "\$LOADERS_CACHE_DIR" 2>/dev/null || true
if grep -q "@RESOURCES@" "\$LOADERS_CACHE_TEMPLATE" 2>/dev/null; then
    sed "s|@RESOURCES@|\$RESOURCES|g" "\$LOADERS_CACHE_TEMPLATE" > "\$LOADERS_CACHE" 2>/dev/null \
        || LOADERS_CACHE="\$LOADERS_CACHE_TEMPLATE"
else
    LOADERS_CACHE="\$LOADERS_CACHE_TEMPLATE"
fi

export DYLD_FRAMEWORK_PATH="\$FRAMEWORKS"
export DYLD_LIBRARY_PATH="\$FRAMEWORKS:\${DYLD_LIBRARY_PATH:-}"
export PYTHONHOME="\$PY_FW"
export PYTHONPATH="\$PY_FW/lib/python$PY_VER/site-packages"
export GI_TYPELIB_PATH="\$RESOURCES/girepository-1.0"
export GSETTINGS_SCHEMA_DIR="\$RESOURCES/glib-2.0/schemas"
export XDG_DATA_DIRS="\$RESOURCES"
export GDK_PIXBUF_MODULE_FILE="\$LOADERS_CACHE"
export GST_PLUGIN_PATH="\$RESOURCES/gstreamer-1.0"
export GST_PLUGIN_SYSTEM_PATH=""
export GST_REGISTRY="\$RESOURCES/gstreamer-1.0/registry.bin"
export GST_PLUGIN_SCANNER="\$RESOURCES/libexec/gstreamer-1.0/gst-plugin-scanner"
export SSL_CERT_FILE="\$FRAMEWORKS/../Resources/ssl/cert.pem"
export DCONF_PROFILE=/dev/null

exec "\$PY_BIN" "\$RESOURCES/launch.py" "\$@"
LAUNCHER_EOF
chmod +x "$MACOS/kitsune"

# ── 12. Create Info.plist ─────────────────────────────────────────────────────
echo "==> Creating Info.plist..."
cat > "$CONTENTS/Info.plist" << PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>       <string>kitsune</string>
  <key>CFBundleIdentifier</key>       <string>$APP_ID</string>
  <key>CFBundleName</key>             <string>Kitsune</string>
  <key>CFBundleDisplayName</key>      <string>Kitsune</string>
  <key>CFBundleVersion</key>          <string>$APP_VERSION</string>
  <key>CFBundleShortVersionString</key><string>$APP_VERSION</string>
  <key>CFBundleIconFile</key>         <string>kitsune</string>
  <key>CFBundlePackageType</key>      <string>APPL</string>
  <key>LSMinimumSystemVersion</key>   <string>13.0</string>
  <key>NSHighResolutionCapable</key>  <true/>
  <key>NSRequiresAquaSystemAppearance</key><false/>
  <key>NSHumanReadableCopyright</key> <string>Copyright © 2024-2026 Anton Palgunov. GPL-3.0-or-later.</string>
</dict>
</plist>
PLIST_EOF

printf "APPL????" > "$CONTENTS/PkgInfo"

# ── 13. Create ICNS icon ──────────────────────────────────────────────────────
echo "==> Creating ICNS icon..."
SVG_SRC="data/icons/hicolor/scalable/apps/$APP_ID.svg"
ICONSET_DIR="$RESOURCES/kitsune.iconset"
mkdir -p "$ICONSET_DIR"

for size in 16 32 64 128 256 512; do
    rsvg-convert -w "$size" -h "$size" "$SVG_SRC" \
        > "$ICONSET_DIR/icon_${size}x${size}.png" 2>/dev/null || true
    dbl=$((size * 2))
    [ $size -le 256 ] && rsvg-convert -w "$dbl" -h "$dbl" "$SVG_SRC" \
        > "$ICONSET_DIR/icon_${size}x${size}@2x.png" 2>/dev/null || true
done

iconutil -c icns -o "$RESOURCES/kitsune.icns" "$ICONSET_DIR" 2>/dev/null \
    && echo "   ICNS created" || echo "   WARNING: iconutil failed"
rm -rf "$ICONSET_DIR"

# ── 13b. Dylib compatibility aliases ─────────────────────────────────────────
echo "==> Creating dylib compatibility aliases..."
ALIAS_COUNT=0
link_dylib_alias() {
    local alias="$1"
    local target="$2"
    if [ -f "$FRAMEWORKS/$target" ] && [ ! -e "$FRAMEWORKS/$alias" ]; then
        (cd "$FRAMEWORKS" && ln -s "$target" "$alias")
        ALIAS_COUNT=$((ALIAS_COUNT + 1))
        echo "   $alias -> $target"
    fi
}

while IFS= read -r dylib; do
    dylib_base="$(basename "$dylib")"
    if [[ "$dylib_base" =~ ^(.+)\.([0-9]+)\.[0-9].*\.dylib$ ]]; then
        link_dylib_alias "${BASH_REMATCH[1]}.${BASH_REMATCH[2]}.dylib" "$dylib_base"
    fi
done < <(find "$FRAMEWORKS" -maxdepth 1 -type f -name "*.dylib" -print 2>/dev/null)

while IFS= read -r -d '' binary; do
    otool -L "$binary" 2>/dev/null \
        | awk '/^\t@executable_path\/\.\.\/Frameworks\// {print $1}' \
        | while read -r dep; do
            dep_base="$(basename "$dep")"
            dep_stem="${dep_base%.dylib}"
            if [ -e "$FRAMEWORKS/$dep_base" ]; then
                continue
            fi

            target="$(find "$FRAMEWORKS" -maxdepth 1 -type f -name "$dep_stem.*.dylib" \
                | sort -V | tail -1)"
            if [ -n "$target" ]; then
                link_dylib_alias "$dep_base" "$(basename "$target")"
            fi
        done
done < <(find "$FRAMEWORKS" "$RESOURCES/gstreamer-1.0" "$RESOURCES/gdk-pixbuf" "$PY_SITEPACKAGES" \
    -type f \( -name "*.dylib" -o -name "*.so" \) -print0 2>/dev/null)

echo "   Created $ALIAS_COUNT aliases"

# ── 14. Ad-hoc code sign ─────────────────────────────────────────────────────
echo "==> Ad-hoc signing..."
find "$FRAMEWORKS" "$CONTENTS" \
    \( -name "*.dylib" -o -name "*.so" \) \
    -exec codesign --force --sign - {} \; 2>/dev/null || true
codesign --force --sign - "$BUNDLED_PY/bin/python$PY_VER" 2>/dev/null || true
codesign --force --deep --sign - "$APP" 2>/dev/null \
    && echo "   Signed (ad-hoc)" || echo "   WARNING: codesign failed"

# ── 15. Summary & DMG ─────────────────────────────────────────────────────────
echo ""
echo "==> Bundle summary:"
du -sh "$FRAMEWORKS" "$RESOURCES" "$MACOS"
echo "Total:"
du -sh "$APP"

echo ""
echo "==> Creating DMG..."
DMG_NAME="$APP_NAME-$APP_VERSION.dmg"
rm -f "$DIST_DIR/$DMG_NAME"

hdiutil create \
    -volname "Kitsune" \
    -srcfolder "$APP" \
    -ov -format UDZO \
    "$DIST_DIR/$DMG_NAME"

# ── 16. Release smoke test ───────────────────────────────────────────────────
echo ""
echo "==> Running isolated app smoke tests..."
scripts/test-isolated.sh

echo ""
echo "══════════════════════════════════════════"
echo "  Done!"
echo "  App:  $APP"
echo "  DMG:  $DIST_DIR/$DMG_NAME"
echo "══════════════════════════════════════════"
