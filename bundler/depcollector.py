import sys
import os
import errno

from distutils import dir_util, file_util
from modulegraph import modulegraph


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else: raise

def collect_deps(root, dest_lib_dir, path_file):
    mg = modulegraph.ModuleGraph([sys.path[0]] + [x.strip() for x in open(path_file, 'r').readlines()] + sys.path[1:])#, debug=3)

    mg.import_hook("distutils")
    mg.import_hook("site")
    mg.import_hook("jsonschema")
    mg.import_hook("scrypt")
    mg.import_hook("_scrypt")
    mg.import_hook("ConfigParser")
    mg.import_hook("Crypto")
    mg.import_hook("encodings.idna")
    mg.import_hook("leap.soledad.client")
    mg.import_hook("leap.mail")
    mg.import_hook("leap.keymanager")
    mg.import_hook("argparse")
    mg.import_hook("srp")
    mg.import_hook("pkgutil")
    mg.import_hook("pkg_resources")
    mg.import_hook("_sre")
    mg.import_hook("zope.proxy")
    mg.run_script(root)

    packages = [mg.findNode(i) for i in ["leap.common", "leap.keymanager", "leap.mail", "leap.soledad.client", "leap.soledad.common", "jsonschema"]]
    other = []

    sorted_pkg = [(os.path.basename(mod.identifier), mod) for mod in mg.flatten()]
    sorted_pkg.sort()
    for (name, pkg) in sorted_pkg:
        # skip namespace packages
        if name == "leap" or name == "leap.soledad" or name == "google" or name == "zope" or name.endswith("leap/bitmask/app.py"):
            continue
        # print pkg
        if isinstance(pkg, modulegraph.MissingModule):
            # print "ignoring", pkg.identifier
            continue
        elif isinstance(pkg, modulegraph.Package):
            foundpackage = False
            for i in packages:
                if pkg.identifier.startswith(i.identifier):
                    # print "skipping", pkg.identifier, "member of", i.identifier
                    # print "  found in", i.filename
                    foundpackage = True
                    break
            if foundpackage:
                continue
            if pkg.filename is None:
                continue
            if pkg not in packages:
                packages.append(pkg)
        else: #if isinstance(pkg, modulegraph.Extension):
            foundpackage = False
            for i in packages:
                if pkg.identifier.startswith(i.identifier):
                    # print "skipping", pkg.identifier, "member of", i.identifier
                    # print "  found in", i.filename
                    foundpackage = True
                    break
            if foundpackage:
                continue
            if pkg.filename is None:
                continue
            other.append(pkg)
            # print pkg.identifier
    #import pdb; pdb.set_trace()

    print "Packages", len(packages)
    for i in sorted(packages):
        # if i.identifier == "distutils":
        #     i.filename = distutils.__file__
        print i.identifier, i.filename
        if i.identifier == "leap.bitmask":
            continue
        parts = i.identifier.split(".")
        destdir = os.path.join(*([dest_lib_dir]+parts))
        mkdir_p(destdir)
        dir_util.copy_tree(os.path.dirname(i.filename), destdir)
        before = []
        for part in parts:
            before.append(part)
            current = before + ["__init__.py"]
            try:
                with open(os.path.join(dest_lib_dir, *current), 'a'):
                    pass
            except Exception:
                pass

    print "Other", len(other)
    for i in sorted(other):
        # if i.identifier == "site":
        #     i.filename = site.__file__
        print i.identifier, i.filename
        file_util.copy_file(i.filename, dest_lib_dir)
