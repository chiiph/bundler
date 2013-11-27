Bundler
+++++++

This application is intended to create bundles for the platform in which its being run. This should eventually become the main tool in order to create reproducible builds.

How to use
++++++++++

NOTE: Most of this will be done automatically in a while, but this is how it's done now.

- Install Xcode and command line tools (OSX only)
- Create a new virtualenv

::
  mkvirtualenv bundle

- Install bundler deps

::
  pip install -r pkg/requirements.pip

- Install the needed dependencies

::
  # Linux only dependencies
  aptitude install libsqlite3-dev

- psutils is a dependency for another dependency, it might get installed in a zip form, which we don't want, so we install it by hand for now

::
  pip install psutil

- We need a slightly different python-gnupg, so clone from a different repo

::
  git clone https://github.com/chiiph/python-gnupg
  cd python-gnupg/
  git checkout develop
  git pull origin develop
  python setup.py develop

- Same thing with protobuf.socketrpc

::
  git clone https://github.com/chiiph/protobuf-socket-rpc
  cd protobuf-socket-rpc
  python setup.py easy_install -Z .

- Install Qt 4.8 in whatever way you prefer.

- Build PySide:

::
  git clone git://gitorious.org/pyside/apiextractor.git
  git clone git://gitorious.org/pyside/generatorrunner.git
  git clone git://gitorious.org/pyside/shiboken.git
  git clone git://gitorious.org/pyside/pyside.git
  git clone git://gitorious.org/pyside/pyside-tools.git

  # OSX
  export PYSIDESANDBOXPATH=$HOME/Code/pyside/sandbox
  export DYLD_LIBRARY_PATH=$PYSIDESANDBOXPATH/lib:$DYLD_LIBRARY_PATH

  # Linux
  export PYSIDESANDBOXPATH=$HOME/sandbox
  export LD_LIBRARY_PATH=$PYSIDESANDBOXPATH/lib:$LD_LIBRARY_PATH

  export PATH=$PYSIDESANDBOXPATH/bin:$PATH
  export PYTHONPATH=$PYSIDESANDBOXPATH/lib/python2.6/site-packages:$PYTHONPATH
  export PKG_CONFIG_PATH=$PYSIDESANDBOXPATH/lib/pkgconfig:$PKG_CONFIG_PATH

  alias runcmake='cmake .. -DCMAKE_INSTALL_PREFIX=$PYSIDESANDBOXPATH'

  # In OSX, the paths may vary depending on the Qt installation
  runcmake -DCMAKE_OSX_DEPLOYMENT_TARGET=10.7 -DCMAKE_OSX_SYSROOT=/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX10.8.sdk .. -DQT_QMAKE_EXECUTABLE=/usr/local/bin/qmake -DQT_INCLUDE_DIR=/usr/local/include/ -DQT_INCLUDES=/usr/local/include/ -DALTERNATIVE_QT_INCLUDE_DIR=/usr/local/include/
  # In Linux
  runcmake ..

  make install

  # Make them available from the virtualenv
  ln -s $PYSIDESANDBOXPATH/lib/python2.7/site-packages/PySide $VIRTUAL_ENV/lib/python2.7/site-packages/PySide
  ln -s $PYSIDESANDBOXPATH/lib/python2.7/site-packages/pysideuic $VIRTUAL_ENV/lib/python2.7/site-packages/pysideuic

- Create a paths file: The problem is that inside a virtualenv we don't have access to the real distutils, so we'll need to look for it on the "original" (i.e. non-virtualenv) paths for python.

::
  python bundler/create_paths.py <paths file>

- Collect the binaries. We aren't building everything yet, so you'll need to collect the following files:

::
  # OSX
  Bitmask <-- this is the bitmask_launcher
  Python
  QtCore
  QtGui
  cocoasudo
  gpg
  libboost_filesystem.dylib
  libboost_python.dylib
  libboost_system.dylib
  libpng15.15.dylib
  libpyside-python2.7.1.2.dylib
  libshiboken-python2.7.1.2.dylib
  openvpn.files
  openvpn.leap
  qt_menu.nib
  tuntap-installer.app

- (Optional) Seed a configuration: You might want to create a bundle with a specific configuration pinned providers.

- Create the bundle:

::
  python bundler/main.py --workon <path/to/bundle/temp> --paths-file <paths file> --binaries <binaries dir> --seeded-config <seeded config> [--nightly] --do gitclone pythonsetup
  python bundler/main.py --workon <path/to/bundle/temp> --paths-file <paths file> --binaries <binaries dir> --seeded-config <seeded config> [--nightly] --skip gitclone pythonsetup
