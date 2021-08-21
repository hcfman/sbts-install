# sbts-install

Installs the latest release of StalkedByTheState on one of NVIDIA Jetson Nano, NX or AGX.

Before installing this you need to first install sbts-base and the reboot into readwrite mode. To reboot the sbts-base into readwrite mode do the following:

cd sbts-bin

sudo ./make_readwrite.sh

sudo reboot

If you are in readwrite mode then findmnt -n / will not have anything about overlayfs in it.

At that stage you can clone this project and then run:

cd sbts-install

sudo -H ./sbts_install_stalkedbythestate.sh

The whole installation will happen and then the box will restart and will be running the software.

To view the user interface type in:

http:you-ip-address:8080/sbts/

with the account details you entered when installing.

This release is in preparation stage. Further documentation and instructional videos will be necessary in order to use this project. These are coming it will be a few more weeks yet.

