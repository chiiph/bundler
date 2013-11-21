import os
import stat
import sys

from abc import ABCMeta, abstractmethod
from contextlib import contextmanager
from distutils import file_util, dir_util

from sh import git, cd, python, mkdir, make, cp, glob, pip, rm
from sh import find, SetFile, hdiutil, ln

from utils import IS_MAC
from depcollector import collect_deps
from darwin_dyliber import fix_all_dylibs

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

class GitCloneAll(Action):
    def __init__(self, basedir, skip, do):
        Action.__init__(self, "gitclone", basedir, skip, do)

    def _repo_url(self, repo_name):
        if repo_name == "leap_assets":
            return "git://leap.se/leap_assets"
        return "https://github.com/leapcode/{0}".format(repo_name)

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
    def run(self, sorted_repos):
        cd(self._basedir)
        for repo in sorted_repos:
            print "Setting up", repo
            if repo == "soledad":
                for subrepo in ["common", "client"]:
                    with push_pop(repo, subrepo):
                        pip("install", "-r", "pkg/requirements.pip")
                        python("setup.py", "develop")
                        sys.path.append(os.path.join(self._basedir, repo, subrepo, "src"))
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
                    python("setup.py", "develop")
                    sys.path.append(os.path.join(self._basedir, repo, "src"))

class CreateDirStructure(Action):
    def __init__(self, basedir, skip, do):
        Action.__init__(self, "createdirs", basedir, skip, do)

    @skippable
    def run(self):
        print "Creating directory structure..."
        if IS_MAC:
            self._darwin_create_dir_structure()
            self._create_dir_structure(os.path.join(self._basedir, "Bitmask.app", "Contents", "MacOS"))
        else:
            self._create_dir_structure(self._basedir)
        print "Done"

    def _create_dir_structure(self, basedir):
        mkdirp = mkdir.bake("-p")
        apps = os.path.join(basedir, "apps")
        mkdirp(apps)
        if not IS_MAC:
            mkdirp(os.path.join(apps, "eip", "files"))
        mkdirp(os.path.join(apps, "mail"))
        mkdirp(os.path.join(basedir, "lib"))

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
        for f in files:
            if f.find("PySide") > 0:
                if os.path.split(f)[1] not in ["QtCore.so",
                                               "QtGui.so",
                                               "__init__.py",
                                               "_utils.py",
                                               "PySide",
                                               ""]:  # empty means the whole pyside dir
                    rm("-rf", f)
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
        cp(glob(os.path.join(binaries_path, "Qt*")), dest_lib_dir)
        cp(glob(os.path.join(binaries_path, "*.dylib")), dest_lib_dir)
        cp(glob(os.path.join(binaries_path, "Python")), dest_lib_dir)

        if IS_MAC:
            resources_dir = os.path.join(self._basedir,
                                         "Bitmask",
                                         "Bitmask.app",
                                         "Contents",
                                         "Resources")
            cp(glob(os.path.join(binaries_path, "openvpn.leap*")), resources_dir)

            mkdir("-p", os.path.join(resources_dir, "openvpn"))
            cp("-r", glob(os.path.join(binaries_path, "openvpn.files", "*")), os.path.join(resources_dir, "openvpn"))

            cp(os.path.join(binaries_path, "cocoasudo"), resources_dir)

            cp("-r", os.path.join(binaries_path, "qt_menu.nib"), resources_dir)
            cp("-r", os.path.join(binaries_path, "tuntap-installer.app"), resources_dir)
        else:
            eip_dir = platform_dir(self._basedir, "apps", "eip")
            cp(glob(os.path.join(binaries_path, "openvpn.leap*")), eip_dir)

            mkdir(os.path.join(resources_dir, "openvpn"))
            cp("-r", glob(os.path.join(binaries_path, "openvpn.files", "*")), os.path.join(eip_dir, "files"))

        mail_dir = platform_dir(self._basedir, "apps", "mail")
        cp(os.path.join(binaries_path, "gpg"), mail_dir)
        cp(os.path.join(binaries_path, "Bitmask"), platform_dir(self._basedir))
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
        os.chmod(launcher_path, stat.S_IRGRP | stat.S_IROTH | stat.S_IRUSR \
                 | stat.S_IWGRP | stat.S_IWOTH | stat.S_IWUSR \
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
        cp(os.path.join(self._basedir, "leap_assets", "mac", "leap-client.tiff"),
           resources_dir)
        print "Done"

class CopyMisc(Action):
    def __init__(self, basedir, skip, do):
        Action.__init__(self, "copymisc", basedir, skip, do)

    @skippable
    def run(self):
        print "Copying misc files..."
        apps_dir = platform_dir(self._basedir, "apps")
        cp(os.path.join(self._basedir, "bitmask_launcher", "src", "launcher.py"),
           apps_dir)
        cp("-r", os.path.join(self._basedir, "thandy", "lib", "thandy"),
           apps_dir)
        cp("-r", os.path.join(self._basedir, "bitmask_client", "src", "leap"),
           apps_dir)
        lib_dir = platform_dir(self._basedir, "lib")
        cp(os.path.join(self._basedir,
                        "leap_pycommon",
                        "src", "leap", "common", "cacert.pem"),
           os.path.join(lib_dir, "leap", "common"))
        cp(os.path.join(self._basedir,
                        "bitmask_client", "build",
                        "lib", "leap", "bitmask", "_version.py"),
           os.path.join(apps_dir, "leap", "bitmask"))

        cp(os.path.join(self._basedir,
                        "bitmask_client", "relnotes.txt"),
           os.path.join(self._basedir, "Bitmask"))
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
    def run(self):
        cd(self._basedir)
        version = "unknown"
        with push_pop("bitmask_client"):
            version = git("describe").strip()
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
                "-format", "UDRW", "-ov",
                raw_dmg_path)
        rm("-rf", dmg_dir)
        mkdir(dmg_dir)
        hdiutil("attach", raw_dmg_path, "-mountpoint", dmg_dir)
        SetFile("-a", "C", dmg_dir)
        hdiutil("detach", dmg_dir)

        rm("-rf", dmg_dir)
        hdiutil("convert", raw_dmg_path, "-format", "UDZO", "-o",
                dmg_path)
        rm("-f", raw_dmg_path)

class PycRemover(Action):
    def __init__(self, basedir, skip, do):
        Action.__init__(self, "removepyc", basedir, skip, do)

    @skippable
    def run(self):
        print "Removing .pyc files..."
        find(self._basedir, "-name", "\"*.pyc\"", "-delete")
        print "Done"
