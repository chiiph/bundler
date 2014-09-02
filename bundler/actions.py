import datetime
import hashlib
import os
import stat
import sys
import subprocess
import zipfile
import urllib

from abc import ABCMeta, abstractmethod
from contextlib import contextmanager
from distutils import file_util, dir_util

from utils import IS_MAC, IS_WIN

if IS_MAC:
    from sh import SetFile, hdiutil, codesign
    from darwin_dyliber import fix_all_dylibs
if IS_WIN:
    import pbs
    from pbs import cd, glob
    git = pbs.Command("C:\\Program Files\\Git\\bin\\git.exe")
    python = pbs.Command("C:\\Python27\\python.exe")
    pip = pbs.Command("C:\\Python27\\scripts\\pip.exe")
    mkdir = pbs.Command("C:\\Program Files\\Git\\bin\\mkdir.exe")
    make = pbs.Command("C:\\MinGW\\bin\\mingw32-make.exe")
    cp = pbs.Command("C:\\Program Files\\Git\\bin\\cp.exe")
    rm = pbs.Command("C:\\Program Files\\Git\\bin\\rm.exe")
    find = pbs.Command("C:\\Program Files\\Git\\bin\\find.exe")
    ln = pbs.Command("C:\\Program Files\\Git\\bin\\ln.exe")
    tar = pbs.Command("C:\\Program Files\\Git\\bin\\tar.exe")
    mv = pbs.Command("C:\\Program Files\\Git\\bin\\mv.exe")
else:
    from sh import git, cd, python, mkdir, make, cp, glob, pip, rm
    from sh import find, ln, tar, mv, strip

from depcollector import collect_deps


class Action(object):
    __metaclass__ = ABCMeta

    def __init__(self, name, basedir, skip=[], do=[]):
        self._name = name
        self._basedir = basedir
        self._skip = skip
        self._do = do

    @property
    def name(self):
        return self._name

    @property
    def skip(self):
        return self._name in self._skip

    @property
    def do(self):
        if len(self._do) > 0:
            return self._name in self._do
        return True

    @abstractmethod
    def run(self, *args, **kwargs):
        pass


def skippable(func):
    def skip_func(self, *args, **kwargs):
        if self.skip:
            print "Skipping...", self.name
            return
        if not self.do:
            print "Skipping...", self.name
            return
        return func(self, *args, **kwargs)
    return skip_func


def platform_dir(basedir, *args):
    dir = os.path.join(basedir,
                       "Bitmask",
                       *args)
    if IS_MAC:
        dir = os.path.join(basedir,
                           "Bitmask",
                           "Bitmask.app",
                           "Contents",
                           "MacOS",
                           *args)
    return dir


@contextmanager
def push_pop(*directories):
    cd(os.path.join(*directories))
    yield
    cd(os.path.join(*(("..",)*len(directories))))


def get_version(repos, nightly):
    if not nightly:
        version = "unknown"
        with push_pop("bitmask_client"):
            version = git("describe", "--tags").strip()
        return version

    m = hashlib.sha256()
    for repo in repos:
        version = "unknown"
        with push_pop(repo):
            try:
                version = git("describe").strip()
            except:
                pass
        m.update(version)

    return "{0}-{1}".format(str(datetime.date.today()),
                            m.hexdigest()[:8])


class GitCloneAll(Action):
    def __init__(self, basedir, skip, do):
        Action.__init__(self, "gitclone", basedir, skip, do)

    def _repo_url(self, repo_name):
        if repo_name == "leap_assets":
            return "git://leap.se/leap_assets"
        return "git://github.com/leapcode/{0}".format(repo_name)

    @skippable
    def run(self, sorted_repos, nightly):
        print "Cloning repositories..."
        cd(self._basedir)
        for repo in sorted_repos:
            print "Cloning", repo
            rm("-rf", repo)
            git.clone(self._repo_url(repo), repo)
            with push_pop(repo):
                # Thandy is a special case regarding branches, we'll just use
                # develop
                if repo in ["thandy", "leap_assets"]:
                    continue
                if not nightly:
                    git.checkout("master")
                    git.pull("--ff-only", "origin", "master")
                    git.fetch()
                    git.reset("--hard", "origin/master")
                    latest_tag = git.describe("--abbrev=0").strip()
                    git.checkout("--quiet", latest_tag)
                else:
                    git.checkout("develop")

        print "Done cloning repos..."


class PythonSetupAll(Action):
    def __init__(self, basedir, skip, do):
        Action.__init__(self, "pythonsetup", basedir, skip, do)

    @skippable
    def run(self, sorted_repos, binaries_path):
        cd(self._basedir)
        for repo in sorted_repos:
            print "Setting up", repo
            if repo == "soledad":
                for subrepo in ["common", "client"]:
                    with push_pop(repo, subrepo):
                        pip("install", "-r", "pkg/requirements.pip")
                        python("setup.py", "develop")
                        sys.path.append(os.path.join(self._basedir,
                                                     repo, subrepo, "src"))
            elif repo in ["bitmask_launcher", "leap_assets"]:
                print "Skipping launcher..."
                continue
            else:
                with push_pop(repo):
                    if repo != "thandy":
                        pip("install", "-r", "pkg/requirements.pip")
                    else:
                        # Thandy is a special kid at this point in
                        # terms of packaging. So we install
                        # dependencies ourselves for the time being
                        pip("install", "pycrypto")
                    if repo == "bitmask_client":
                        print "Running make on the client..."
                        make()
                        print "Running build to get correct version..."
                        python("setup.py", "build")
                        print "Updating hashes"
                        os.environ["OPENVPN_BIN"] = os.path.join(
                            binaries_path, "openvpn.files", "leap-openvpn")
                        os.environ["BITMASK_ROOT"] = os.path.join(
                            self._basedir, repo, "pkg", "linux", "bitmask-root")
                        python("setup.py", "hash_binaries")
                    python("setup.py", "develop")
                    sys.path.append(os.path.join(self._basedir, repo, "src"))


def _convert_path_for_win(path):
    npath = path
    if IS_WIN:
        npath = path.replace("\\", "/")
    return npath


class CreateDirStructure(Action):
    def __init__(self, basedir, skip, do):
        Action.__init__(self, "createdirs", basedir, skip, do)

    @skippable
    def run(self):
        print "Creating directory structure..."
        if IS_MAC:
            self._darwin_create_dir_structure()
            self._create_dir_structure(os.path.join(self._basedir,
                                                    "Bitmask.app",
                                                    "Contents", "MacOS"))
        else:
            self._create_dir_structure(self._basedir)
        print "Done"

    def _create_dir_structure(self, basedir):
        mkdirp = mkdir.bake("-p")
        apps = os.path.join(basedir, "apps")
        mkdirp(_convert_path_for_win(apps))
        if IS_WIN:
            mkdirp(_convert_path_for_win(os.path.join(apps, "eip")))
        else:
            mkdirp(_convert_path_for_win(os.path.join(apps, "eip", "files")))
        mkdirp(_convert_path_for_win(os.path.join(apps, "mail")))
        mkdirp(_convert_path_for_win(os.path.join(basedir, "lib")))

    def _darwin_create_dir_structure(self):
        mkdirp = mkdir.bake("-p")
        app_path = os.path.join(self._basedir, "Bitmask.app")
        mkdirp(app_path)
        mkdirp(os.path.join(app_path, "Contents", "MacOS"))
        mkdirp(os.path.join(app_path, "Contents", "Resources"))
        mkdirp(os.path.join(app_path, "Contents", "PlugIns"))
        mkdirp(os.path.join(app_path, "Contents", "StartupItems"))
        ln("-s", "/Applications", os.path.join(self._basedir, "Applications"))


class CollectAllDeps(Action):
    def __init__(self, basedir, skip, do):
        Action.__init__(self, "collectdeps", basedir, skip, do)

    def _remove_unneeded(self, lib_dir):
        print "Removing unneeded files..."
        files = find(lib_dir).strip().splitlines()
        keep = ["QtCore.so",
                "QtGui.so",
                "__init__.py",
                "_utils.py",
                "PySide",
                ""]  # empty means the whole pyside dir
        if IS_WIN:
            keep = ["QtCore4.dll",
                    "QtGui4.dll",
                    "__init__.py",
                    "_utils.py",
                    "PySide",
                    "QtGui.pyd",
                    "QtCore.pyd",
                    ""]  # empty means the whole pyside dir
        for f in files:
            if f.find("PySide") > 0:
                if os.path.split(f)[1] not in keep:
                    rm("-rf", f)
                    pass
        print "Done"

    @skippable
    def run(self, path_file):
        print "Collecting dependencies..."
        app_py = os.path.join(self._basedir,
                              "bitmask_client",
                              "src",
                              "leap",
                              "bitmask",
                              "app.py")
        dest_lib_dir = platform_dir(self._basedir, "lib")
        collect_deps(app_py, dest_lib_dir, path_file)

        self._remove_unneeded(dest_lib_dir)
        print "Done"


class CopyBinaries(Action):
    def __init__(self, basedir, skip, do):
        Action.__init__(self, "copybinaries", basedir, skip, do)

    @skippable
    def run(self, binaries_path):
        print "Copying binaries..."
        dest_lib_dir = platform_dir(self._basedir, "lib")

        if IS_MAC:
            cp(glob(os.path.join(binaries_path, "Qt*")), dest_lib_dir)
            cp(glob(os.path.join(binaries_path, "*.dylib")), dest_lib_dir)
            cp(glob(os.path.join(binaries_path, "Python")), dest_lib_dir)
            resources_dir = os.path.join(self._basedir,
                                         "Bitmask",
                                         "Bitmask.app",
                                         "Contents",
                                         "Resources")
            cp(glob(os.path.join(binaries_path, "openvpn.leap*")),
               resources_dir)

            mkdir("-p", os.path.join(resources_dir, "openvpn"))
            cp("-r", glob(os.path.join(binaries_path, "openvpn.files", "*")),
               os.path.join(resources_dir, "openvpn"))

            cp(os.path.join(binaries_path, "cocoasudo"), resources_dir)

            cp("-r", os.path.join(binaries_path, "qt_menu.nib"), resources_dir)
            cp("-r", os.path.join(binaries_path, "tuntap-installer.app"),
               resources_dir)
            cp(os.path.join(binaries_path, "Bitmask"),
               platform_dir(self._basedir))
        elif IS_WIN:
            root = _convert_path_for_win(
                os.path.join(self._basedir, "Bitmask"))
            for i in glob(os.path.join(binaries_path, "*.dll")):
                cp(_convert_path_for_win(i),
                   root)
            import win32com
            win32comext_path = os.path.split(win32com.__file__)[0] + "ext"
            shell_path = os.path.join(win32comext_path, "shell")
            cp("-r",
               _convert_path_for_win(shell_path),
               _convert_path_for_win(os.path.join(dest_lib_dir, "win32com")))
            cp(_convert_path_for_win(
                os.path.join(binaries_path, "bitmask.exe")),
               root)
            cp(_convert_path_for_win(
                os.path.join(binaries_path, "Microsoft.VC90.CRT.manifest")),
               root)
            cp(_convert_path_for_win(
                os.path.join(binaries_path, "openvpn_leap.exe")),
               _convert_path_for_win(
                   os.path.join(root, "apps", "eip")))
            cp(_convert_path_for_win(
                os.path.join(binaries_path, "openvpn_leap.exe.manifest")),
               _convert_path_for_win(
                   os.path.join(root, "apps", "eip")))
            cp("-r",
               _convert_path_for_win(
                   os.path.join(binaries_path, "tap_driver")),
               _convert_path_for_win(
                   os.path.join(root, "apps", "eip")))
        else:
            cp(glob(os.path.join(binaries_path, "*.so*")), dest_lib_dir)

            eip_dir = platform_dir(self._basedir, "apps", "eip")
            #cp(os.path.join(binaries_path, "openvpn"), eip_dir)

            cp("-r", glob(os.path.join(binaries_path, "openvpn.files", "*")),
               os.path.join(eip_dir, "files"))
            cp(os.path.join(binaries_path, "bitmask"),
               platform_dir(self._basedir))

        mail_dir = platform_dir(self._basedir, "apps", "mail")
        cp(_convert_path_for_win(os.path.join(binaries_path, "gpg")),
           _convert_path_for_win(mail_dir))
        print "Done"


class PLister(Action):
    plist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>CFBundleDisplayName</key>
        <string>Bitmask</string>
        <key>CFBundleExecutable</key>
        <string>MacOS/bitmask-launcher</string>
        <key>CFBundleIconFile</key>
        <string>bitmask.icns</string>
        <key>CFBundleInfoDictionaryVersion</key>
        <string>6.0</string>
        <key>CFBundleName</key>
        <string>Bitmask</string>
        <key>CFBundlePackageType</key>
        <string>APPL</string>
        <key>CFBundleShortVersionString</key>
        <string>1</string>
        <key>LSBackgroundOnly</key>
        <false/>
        <key>CFBundleIdentifier</key>
        <string>se.leap.bitmask</string>
</dict>
</plist>""".split("\n")

    qtconf = """[Paths]
Plugins = PlugIns"""

    def __init__(self, basedir, skip, do):
        Action.__init__(self, "plister", basedir, skip, do)

    @skippable
    def run(self):
        print "Generating Info.plist file..."
        file_util.write_file(os.path.join(self._basedir,
                                          "Bitmask",
                                          "Bitmask.app",
                                          "Contents",
                                          "Info.plist"),
                             self.plist)
        print "Generating qt.conf file..."
        file_util.write_file(os.path.join(self._basedir,
                                          "Bitmask",
                                          "Bitmask.app",
                                          "Contents",
                                          "Resources",
                                          "qt.conf"),
                             self.qtconf)
        print "Done"


class SeededConfig(Action):
    def __init__(self, basedir, skip, do):
        Action.__init__(self, "seededconfig", basedir, skip, do)

    @skippable
    def run(self, seeded_config):
        print "Copying seeded config..."
        dir_util.copy_tree(seeded_config,
                           platform_dir(self._basedir, "config"))
        print "Done"


class DarwinLauncher(Action):
    launcher = """#!/bin/bash
#
# Launcher for the LEAP Client under OSX
#
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd)"
export DYLD_LIBRARY_PATH=$DIR/lib
export PATH=$DIR/../Resources/:$PATH
# ---------------------------
# DEBUG Info -- enable this if you
# are having problems with dynamic libraries loading

cd "${DIR}" && ./Bitmask $1 $2 $3 $4 $5""".split("\n")

    def __init__(self, basedir, skip, do):
        Action.__init__(self, "darwinlauncher", basedir, skip, do)

    @skippable
    def run(self):
        print "Generating launcher script for OSX..."
        launcher_path = os.path.join(self._basedir,
                                     "Bitmask",
                                     "Bitmask.app",
                                     "Contents",
                                     "MacOS",
                                     "bitmask-launcher")
        file_util.write_file(launcher_path, self.launcher)
        os.chmod(launcher_path, stat.S_IRGRP | stat.S_IROTH | stat.S_IRUSR
                 | stat.S_IWGRP | stat.S_IWOTH | stat.S_IWUSR
                 | stat.S_IXGRP | stat.S_IXOTH | stat.S_IXUSR)
        print "Done"


class CopyAssets(Action):
    def __init__(self, basedir, skip, do):
        Action.__init__(self, "copyassets", basedir, skip, do)

    @skippable
    def run(self):
        print "Copying assets..."
        resources_dir = os.path.join(self._basedir,
                                     "Bitmask",
                                     "Bitmask.app",
                                     "Contents",
                                     "Resources")
        cp(os.path.join(self._basedir, "leap_assets", "mac", "bitmask.icns"),
           resources_dir)
        cp(os.path.join(self._basedir, "leap_assets", "mac", "bitmask.tiff"),
           resources_dir)
        print "Done"


class CopyMisc(Action):
    def __init__(self, basedir, skip, do):
        Action.__init__(self, "copymisc", basedir, skip, do)

    @skippable
    def run(self):
        print "Downloading thunderbird extension..."
        ext_path = platform_dir(self._basedir, "apps",
                                "bitmask-thunderbird-latest.xpi")
        urllib.urlretrieve(
            "https://downloads.leap.se/thunderbird_extension/"
            "bitmask-thunderbird-latest.xpi",
            ext_path)
        print "Done"
        print "Copying misc files..."
        apps_dir = _convert_path_for_win(platform_dir(self._basedir, "apps"))
        cp(_convert_path_for_win(
            os.path.join(self._basedir, "bitmask_launcher", "src",
                         "launcher.py")),
           apps_dir)
        cp("-r",
           _convert_path_for_win(os.path.join(self._basedir, "thandy", "lib",
                                              "thandy")),
           apps_dir)
        cp("-r",
           _convert_path_for_win(os.path.join(self._basedir, "bitmask_client",
                                              "src", "leap")),
           apps_dir)
        lib_dir = _convert_path_for_win(platform_dir(self._basedir, "lib"))
        cp(_convert_path_for_win(
            os.path.join(self._basedir,
                         "leap_pycommon",
                         "src", "leap", "common", "cacert.pem")),
           _convert_path_for_win(os.path.join(lib_dir, "leap", "common")))
        cp(_convert_path_for_win(glob(os.path.join(self._basedir,
                                                   "bitmask_client", "build",
                                                   "lib*", "leap", "bitmask",
                                                   "_version.py"))[0]),
           os.path.join(apps_dir, "leap", "bitmask"))

        cp(_convert_path_for_win(
            os.path.join(self._basedir,
                         "bitmask_client", "relnotes.txt")),
           _convert_path_for_win(os.path.join(self._basedir, "Bitmask")))
        print "Done"


class FixDylibs(Action):
    def __init__(self, basedir, skip, do):
        Action.__init__(self, "fixdylibs", basedir, skip, do)

    @skippable
    def run(self):
        fix_all_dylibs(platform_dir(self._basedir))


class DmgIt(Action):
    def __init__(self, basedir, skip, do):
        Action.__init__(self, "dmgit", basedir, skip, do)

    @skippable
    def run(self, repos, nightly):
        print "Dmg'ing it..."
        cd(self._basedir)
        version = get_version(repos, nightly)
        dmg_dir = os.path.join(self._basedir, "dmg")
        template_dir = os.path.join(self._basedir, "Bitmask")
        mkdir("-p", dmg_dir)
        cp("-R", os.path.join(template_dir, "Applications"), dmg_dir)
        cp("-R", os.path.join(template_dir, "relnotes.txt"), dmg_dir)
        cp("-R", os.path.join(template_dir, "Bitmask.app"), dmg_dir)
        cp(os.path.join(self._basedir,
                        "leap_assets",
                        "mac", "bitmask.icns"),
           os.path.join(dmg_dir, ".VolumeIcon.icns"))
        SetFile("-c", "icnC", os.path.join(dmg_dir, ".VolumeIcon.icns"))

        vol_name = "Bitmask"
        dmg_name = "Bitmask-OSX-{0}.dmg".format(version)
        raw_dmg_path = os.path.join(self._basedir, "raw-{0}".format(dmg_name))
        dmg_path = os.path.join(self._basedir, dmg_name)

        hdiutil("create", "-srcfolder", dmg_dir, "-volname", vol_name,
                "-fsargs", "-c c=64,a=16,e=16", "-fs", "HFS+",
                "-format", "UDRW", "-ov", "-size", "500000k",
                raw_dmg_path)
        rm("-rf", dmg_dir)
        mkdir(dmg_dir)
        hdiutil("attach", raw_dmg_path, "-mountpoint", dmg_dir)
        SetFile("-a", "C", dmg_dir)
        hdiutil("detach", dmg_dir)

        rm("-rf", dmg_dir)
        hdiutil("convert", raw_dmg_path, "-format", "UDZO",
                "-imagekey", "zlib-level=9", "-o",
                dmg_path)
        rm("-f", raw_dmg_path)
        print "Done"


class TarballIt(Action):
    def __init__(self, basedir, skip, do):
        Action.__init__(self, "tarballit", basedir, skip, do)

    @skippable
    def run(self, repos, nightly):
        print "Tarballing it..."
        cd(self._basedir)
        version = get_version(repos, nightly)
        import platform
        bits = platform.architecture()[0][:2]
        bundle_name = "Bitmask-linux%s-%s" % (bits, version)
        mv("Bitmask", bundle_name)
        tar("cjf", bundle_name+".tar.bz2", bundle_name)
        print "Done"


class PycRemover(Action):
    def __init__(self, basedir, skip, do):
        Action.__init__(self, "removepyc", basedir, skip, do)

    @skippable
    def run(self):
        print "Removing .pyc files..."
        files = find(self._basedir, "-name", "*.pyc").strip().splitlines()
        for f in files:
            rm(f)
        files = find(self._basedir, "-name", "*\\.so*").strip().splitlines()
        for f in files:
            print "Stripping", f
            try:
                strip(f)
            except:
                pass
        print "Done"


class MtEmAll(Action):
    def __init__(self, basedir, skip, do):
        Action.__init__(self, "mtemall", basedir, skip, do)

    @skippable
    def run(self):
        print "Mt'ing all the files..."
        cd(os.path.join(self._basedir, "Bitmask"))
        subprocess.check_call(
            ["C:\\Program Files\\Windows Kits\\8.0\\bin\\x86\\mt.exe",
             "-nologo", "-manifest", "Microsoft.VC90.CRT.manifest",
             "-outputresource:bitmask.exe;#1"])
        cd(os.path.join("apps", "eip"))
        subprocess.check_call(
            ["C:\\Program Files\\Windows Kits\\8.0\\bin\\x86\\mt.exe",
             "-nologo", "-manifest", "openvpn_leap.exe.manifest",
             "-outputresource:openvpn_leap.exe;#1"])
        print "Done"


class ZipIt(Action):
    def __init__(self, basedir, skip, do):
        Action.__init__(self, "zipit", basedir, skip, do)

    def _zipdir(self, path, zf):
        for root, dirs, files in os.walk(path):
            for f in files:
                zf.write(os.path.join(root, f))

    @skippable
    def run(self, repos, nightly):
        print "Ziping it..."
        cd(self._basedir)
        version = get_version(repos, nightly)
        name = "Bitmask-win32-{0}".format(version)
        mv(_convert_path_for_win(os.path.join(self._basedir, "Bitmask")),
           _convert_path_for_win(os.path.join(self._basedir, name)))
        zf = zipfile.ZipFile("{0}.zip".format(name), "w", zipfile.ZIP_DEFLATED)
        self._zipdir(name, zf)
        zf.close()
        print "Done"


class SignIt(Action):
    def __init__(self, basedir, skip, do):
        Action.__init__(self, "signit", basedir, skip, do)

    @skippable
    def run(self, identity):
        print "Signing tuntap kext..."
        kext = os.path.join(self._basedir,
                            "Bitmask",
                            "Bitmask.app",
                            "Contents",
                            "Resources",
                            "tuntap-installer.app",
                            "Contents",
                            "Extensions",
                            "tun.kext")
        codesign("-s", identity, "--deep", kext)
        print "Done"
        print "Signing tuntap installer..."
        tuntap_app = os.path.join(self._basedir,
                                  "Bitmask",
                                  "Bitmask.app",
                                  "Contents",
                                  "Resources",
                                  "tuntap-installer.app")
        codesign("-s", identity, "--deep", tuntap_app)
        print "Done"
        print "Signing main structure, this will take a while..."
        main_app = os.path.join(self._basedir,
                                "Bitmask",
                                "Bitmask.app")
        print codesign("-s", identity, "--force", "--deep", "--verbose", main_app)
        print "Done"



class RemoveUnused(Action):
    def __init__(self, basedir, skip, do):
        Action.__init__(self, "rmunused", basedir, skip, do)

    @skippable
    def run(self):
        print "Removing unused python code..."
        test_dirs = find(self._basedir, "-name", "*test*").strip().splitlines()
	for td in test_dirs:
            rm("-rf", os.path.join(self._basedir, td))

        twisted_used = ["aplication", "conch", "cred", "version", "internet", "mail"]
        # twisted_files = find(self._basedir, "-name", "t
        print "Done"

