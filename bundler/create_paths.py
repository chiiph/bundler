import sys
from distutils import file_util

def main():
    if len(sys.argv) != 2:
        print "ERROR: Wrong amount of parameters."
        print
        print "./create_paths.py <output file>"
        print
        quit()
    filename = sys.argv[1]

    print "Generating paths file in", filename
    file_util.write_file(filename, sys.path)
    print "Done"

if __name__ == "__main__":
    main()
