import os

from sh import otool, install_name_tool, find

def parse_otool_output(output):
    lines = output.splitlines()[1:]
    libs = []
    for line in lines:
        line = line.strip()
        if len(line) == 0:
            continue
        line = line.split("(")[0].strip()
        lib = os.path.split(line)[-1]
        libs.append((lib, line))

    return libs

def locate_lib(executable_path, lib):
    return find(executable_path, "-name", lib, "-type", "f").strip()

def install_name_tooler(executable_path, lib_path):
    out = otool("-L", lib_path)
    _, lib_name = os.path.split(lib_path)
    libs = parse_otool_output(out)
    updated_any = False
    for lib, original in libs:
        do_id = lib == lib_name

        if original.find("Carbon") > 0:
            continue
        location = locate_lib(executable_path, lib)
        if location is None or len(location) == 0:
            continue
        try:
            if do_id:
                install_name_tool("-id",
                                  os.path.join("@executable_path",
                                               os.path.relpath(location,
                                                               executable_path)),
                                  lib_path)
            else:
                install_name_tool("-change", original,
                                  os.path.join("@executable_path",
                                               os.path.relpath(location,
                                                               executable_path)),
                                  lib_path)
            updated_any = True
        except Exception as e:
            print "ERROR Fixing", lib
            print e
    if updated_any:
        print "Fixed", lib_path

def fix_all_dylibs(executable_path):
    print "Fixing all dylibs, this might take a while..."
    files = find(executable_path, "-type", "f").strip().splitlines()
    for f in files:
        install_name_tooler(executable_path, f)
    print "Done"
