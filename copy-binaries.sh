#!/bin/bash

set -e  # Exit immediately if a command exits with a non-zero status.

BASE='/home/leap/bitmask.bundle'
BOOST="$BASE/boost_1_56_0"

# Note: we could use:
# ARCH=`uname -i`
# but it does not work on a VM (tested in i386 returns unknown)
if [[ `getconf LONG_BIT` == "64" ]]; then
    ARCH='x86_64-linux-gnu'
else
    ARCH='i386-linux-gnu'
fi

cd $BASE
mkdir binaries && cd binaries

cp /usr/bin/gpg .
cp $BASE/bitmask_launcher/build/src/launcher bitmask
cp $BOOST/stage/lib/libboost_filesystem.so.1.56.0 .
cp $BOOST/stage/lib/libboost_python.so.1.56.0 .
cp $BOOST/stage/lib/libboost_system.so.1.56.0 .

cp $BASE/pyside-setup.git/pyside_package/PySide/libpyside-python2.7.so.1.2 .
cp $BASE/pyside-setup.git/pyside_package/PySide/libshiboken-python2.7.so.1.2 .

cp /usr/lib/$ARCH/libQtGui.so libQtGui.non-ubuntu
cp /usr/lib/$ARCH/libQtCore.so libQtCore.non-ubuntu

cp /usr/lib/$ARCH/libaudio.so.2 .
cp /usr/lib/$ARCH/libffi.so.5 .
cp /usr/lib/$ARCH/libfontconfig.so.1 .
cp /lib/$ARCH/libpng12.so.0 .  # NOTE: it should be libpng15.so.15
cp /usr/lib/libpython2.7.so.1.0 .
cp /usr/lib/$ARCH/libssl.so.1.0.0 .
cp /usr/lib/$ARCH/libstdc++.so.6 .

touch root.json  # empty file for TUF

mkdir openvpn.files
cd openvpn.files
cp $BASE/openvpn/src/openvpn/openvpn leap-openvpn

# TODO: to avoid network requests this should be copied from the cloned repositories
# after `bundler gitclone` and before `bundler pythonsetup`
wget https://raw.githubusercontent.com/leapcode/bitmask_client/develop/pkg/linux/bitmask-root
wget https://raw.githubusercontent.com/leapcode/bitmask_client/develop/pkg/linux/leap-install-helper.sh
wget https://raw.githubusercontent.com/leapcode/bitmask_client/develop/pkg/linux/polkit/se.leap.bitmask.bundle.policy
chmod +x bitmask-root
chmod +x leap-install-helper.sh
