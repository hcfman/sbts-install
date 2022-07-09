#!/bin/bash

# Copyright (c) 2021 Kim Hendrikse

UPDATED=

APP_FILE="stalkedbythestate_app_jetson_v1.00.tar.gz"
APP_URL="https://github.com/hcfman/stalkedbythestate/releases/download/stalkedbythestate_app_jetson_v1.00/$APP_FILE"
APP_CHECKSUM="539dd22daad7164a68aacf178cd7fb30"

# Needed after upgrading numpy due to a bug in the upgrade version on arm
export OPENBLAS_CORETYPE=ARMV8

disk_list=()

abort() {
    echo $* >&2
    echo "Aborting..."
    exit 1
}

HERE=$(dirname $0)
cd $HERE || abort "Can't change to script directory"
HERE=`/bin/pwd`

sanity_check() {
    mount_point=$(findmnt -n / | awk '{print $2}')
    if ! [[ "${mount_point}" =~ /dev/sd || "${mount_point}" =~ /dev/nvme ]] ; then
        abort "You need to run this script from a read-write mounted SSD drive. Please execute: cd ~/sbts-bin; sudo ./make_readwrite.sh; sudo reboot"
    fi
}

get_non_blank() {
    local prompt=$1
    local thevariable=$2
    local identifier=$3
    local thestring=
    echo "$prompt" >&2

    while [ 1 ] ; do
	echo -n "${thevariable}: " >&2
	read thestring
	if [[ $thestring =~ ^.*[[:blank:]].* || -z "$thestring" ]] ; then
	    echo ""
	    echo "You entered blanks" >&2
	    continue
	fi

	if [ "$identifier" == "username" ] ; then
	    if ! [[ $thestring =~ ^[[:alpha:]]([[:alnum:]]|_)*$ ]] ; then
		echo "" >&2
		echo "The $thevariable should being with an alpha and continue with aphanumerics or underscore" >&2
		continue
	    fi
	fi

	if [ "$identifier" == "password" ] ; then
	    if [[ $thestring =~ \& ]] ; then
		echo "" >&2
		echo "The $thevariable should not contain an ampersand character" >&2
		continue
	    fi

	    if [[ $thestring =~ \$ ]] ; then
		echo "" >&2
		echo "The $thevariable should not contain an dollar character" >&2
		continue
	    fi

	    if [[ $thestring =~ [{}] ]] ; then
		echo "" >&2
		echo "The $thevariable should not contain an braces" >&2
		continue
	    fi

	    if [[ $thestring =~ % ]] ; then
		echo "" >&2
		echo "The $thevariable should not contain a percent character" >&2
		continue
	    fi

	    if [[ $thestring =~ \" ]] ; then
		echo "" >&2
		echo "The $thevariable should not contain a quote character" >&2
		continue
	    fi
	fi

	break

    done

    echo "$thestring"
}

get_credentials() {
    # Get the tomcat admin username
    echo ""
    while [ 1 ] ; do
	tomcat_username=$(get_non_blank "Please enter the initial StalkedByTheState tomcat username" "Username" "username")
	if [ "$username" == "guest" ] ; then
	    echo "Sorry, choose another name than guest"
	    echo ""
	else
	    break
	fi
    done

    echo ""
    tomcat_password=$(get_non_blank "Please enter the initial StalkedByTheState tomcat password" "Password" "password")

    echo ""
    backup_password=$(get_non_blank "Please enter the StalkedByTheState backup/restore password" "Backup/restore password" "password")
}

update_pkg_registry() {
    if [ ! "$UPDATED" ] ; then
        echo Updating the package registry
        echo ""
        apt update
        apt upgrade -y
        UPDATED=1
    fi
}

install_package() {
    package=$1
    echo "Installing package \"$package\""
    echo ""
    if ! apt install -y "$package" ; then
        abort "Can't install package $package"
    fi
}

prep_pip_installation() {
  echo ""
  echo "Prepare pip installation"
  echo ""
  apt install -y python3-pip
  if ! dpkg -l "python3-pip" > /dev/null 2>&1 ; then
      echo "Installing \"python3-pip\""
      install_package "python3-pip"
  fi

  echo "Upgrade pip"
  python3 -m pip  install --upgrade pip

  echo ""
  echo "Remove cmake"
  if ! apt purge -y cmake ; then
      abort "Failed to purge cmake"
  fi

  echo ""
  echo "Remove python3-protobuf"
  if ! apt purge -y python3-protobuf ; then
      abort "Failed to purge python3-protobuf"
  fi

  echo ""
  echo "Upgrade setuptools"
  if ! python3 -m pip install setuptools==59.5.0 ; then
      abort "Failed to upgrade setuptools to version 59.5.0"
  fi

  echo ""
  echo "Upgrade cmake"

  if ! wget -O - https://apt.kitware.com/keys/kitware-archive-latest.asc 2>/dev/null |
          gpg --dearmor - | tee /etc/apt/trusted.gpg.d/kitware.gpg >/dev/null ; then
      abort "Failed to add kitware key"
  fi

  if ! apt-add-repository "deb https://apt.kitware.com/ubuntu/ $(lsb_release -cs) main" ; then
      abort "Failed to add kitware repository"
  fi

  apt update
  if ! apt install kitware-archive-keyring ; then
      abort "Failed to install kitware keyring"
  fi
}

install_packages() {
    echo ""
    echo "Installing packages"
    echo ""

    for package in cmake libomp-dev libpng-dev libjpeg-dev curl htop openjdk-8-jdk libgeos-3.6.2 libgeos-c1v5 apache2 letsencrypt python3-certbot-apache maven vlc vlc-bin pwgen; do
        if ! dpkg -l "$package" > /dev/null 2>&1 ; then
            echo "Installing package \"$package\""
            install_package "$package"
        fi
    done
}

remove_apache_default_pages() {
    cd "$HERE" || abort "Can't change back to $HERE"

    if [ -f "/var/www/html/index.html" ] ; then
	echo ""
	echo "Remove default apache2 packages"
	echo ""

	rm -f /var/www/html/index.html || abort "Can't remove /var/www/html/index.html"
    fi

    util/remove_apache2_default_permissions.pl || abort "Could not remove the default rights from apache"
}

install_module() {
    module=$1

    if ! python3 -c "import $module" ; then
        echo "Installing python module \"$module\""
        if ! python3 -m pip install "$module" ; then
            abort "Can't install pip3 module \"$module\""
        fi
    fi
}

download_file() {
    if ! wget "$1" ; then
        abort "Can't download $1"
    fi
}

gdown_file() {
    if ! gdown "https://drive.google.com/uc?id=$1" ; then
        abort "Can't gdown $1"
    fi
}

install_extra_wheels() {
    if ! cd /tmp ; then
        abort "Can't change directory to /tmp"
    fi

    # Pytorch
    download_file "https://github.com/hcfman/sbts-prereqs/releases/download/sbtq-prereqs_v1.0.0_jetpack_4.6.1/torch-1.10.0a0+git71f889c-cp36-cp36m-linux_aarch64.whl"

    if ! python3 -m pip install "./torch-1.10.0a0+git71f889c-cp36-cp36m-linux_aarch64.whl" ; then
        abort "Can't install torch module"
    fi

    if ! rm "./torch-1.10.0a0+git71f889c-cp36-cp36m-linux_aarch64.whl" ; then
        abort "Can't remove installed pytorch wheel"
    fi

    # Torchvision
    download_file "https://github.com/hcfman/sbts-prereqs/releases/download/sbtq-prereqs_v1.0.0_jetpack_4.6.1/torchvision-0.11.0a0+05eae32-cp36-cp36m-linux_aarch64.whl"

    if ! python3 -m pip install "./torchvision-0.11.0a0+05eae32-cp36-cp36m-linux_aarch64.whl" ; then
        abort "Can't install torchvision module"
    fi

    if ! rm "./torchvision-0.11.0a0+05eae32-cp36-cp36m-linux_aarch64.whl" ; then
        abort "Can't remove installed pytorch wheel"
    fi

    # Mish-cuda
    download_file "https://github.com/hcfman/sbts-prereqs/releases/download/sbtq-prereqs_v1.0.0_jetpack_4.6.1/mish_cuda-0.0.3-cp36-cp36m-linux_aarch64.whl"

    if ! python3 -m pip install "./mish_cuda-0.0.3-cp36-cp36m-linux_aarch64.whl" ; then
        abort "Can't install mish-cuda module"
    fi

    if ! rm "./mish_cuda-0.0.3-cp36-cp36m-linux_aarch64.whl" ; then
        abort "Can't remove installed mish-cuda wheel"
    fi
}

install_python_modules() {
    echo ""
    echo "Installing python modules"
    echo ""

    install_module "protobuf"
    if ! python3 -m pip install --upgrade numpy==1.19.5 ; then
        abort "Can't install numpy version 1.19.5"
    fi

    # Modules for pytorch and friends support
    for m in pillow tqdm; do
        install_module "$m"
    done

    if ! python3 -m pip install matplotlib==3.3.4 ; then
        abort "Can't install matplotlib version 3.3.4"
    fi

    install_module "pycocotools"

    if ! python3 -m pip install scipy==1.5.4 ; then
        abort "Can't install scipy version 1.5.4"
    fi

    if ! python3 -m pip install pandas==1.1.5 ; then
        abort "Can't install pandas version 1.1.5"
    fi

    for m in gdown seaborn; do
        install_module "$m"
    done

    # pytorch and friends
    install_extra_wheels

    # Pytorch should be installed first as above
    install_module "thop"

    # Modules for sbts
    for m in flask requests websockets shapely configparser asyncio aiohttp; do
        install_module "$m"
    done
}

install_apache2_modules() {
    echo ""
    echo "Installing apache modules"
    echo ""

    for m in rewrite headers proxy proxy_http proxy_balancer lbmethod_byrequests proxy_wstunnel ; do
        if ! a2enmod "$m" ; then
            abort "Can't enable apache2 module \"$m\""
        fi
    done
}

install_extra_apache2_ssl_config() {
    echo ""
    echo "Installing extra apache ssl config"
    echo ""

    cd "$HERE" || abort "Can't change back to $HERE"
    
    cp resources/sbts-ssl.conf /etc/apache2/conf-available
    a2enconf sbts-ssl.conf
}

migrate_letsencrypt() {
    echo ""
    echo "Migrating letsencrypt to the config partition"
    echo ""

    sudo -H -u "$SUDO_USER" "$SUDO_USER_HOME/sbts-bin/mount_readwrite" || abort "Can't re-mount $SUDO_USER_HOME/config"

    if [ ! -e "$SUDO_USER_HOME/config/letsencrypt" ] ; then
        mkdir "$SUDO_USER_HOME/config/letsencrypt" || abort "Can't create $SUDO_USER_HOME/config/letsencrypt"
    fi

    if [ ! -e "$SUDO_USER_HOME/config/letsencrypt/letsencrypt" -a -e "$SUDO_USER_HOME/config/letsencrypt" ] ; then
        mv /etc/letsencrypt $SUDO_USER_HOME/config/letsencrypt || abort "Can't move /etc/letsencrypt to $SUDO_USER_HOME/config/letsencrypt"
    fi

    if [ -e "$SUDO_USER_HOME/config/letsencrypt/letsencrypt" -a ! -e "/etc/letsencrypt" ] ; then
        ln -s "$SUDO_USER_HOME/config/letsencrypt/letsencrypt" "/etc/letsencrypt" || abort "Can't create symlink from $SUDO_USER_HOME/config/letsencrypt/letsencrypt to /etc/letsencrypt"
    fi
}

migrate_apache2_sites-available() {
    echo ""
    echo "Migrating /etc/apache2/sites-available"
    echo ""

    sudo -H -u "$SUDO_USER" "$SUDO_USER_HOME/sbts-bin/mount_readwrite" || abort "Can't re-mount $SUDO_USER_HOME/config"

    systemctl stop apache2 || abort "Can't stop apache2"

    if [ ! -e "$SUDO_USER_HOME/config/apache2" ] ; then
        mkdir "$SUDO_USER_HOME/config/apache2" || abort "Can't create $SUDO_USER_HOME/config/apache2"
    fi

    if [ -e "/etc/apache2/sites-available" -a ! -L "/etc/apache2/sites-available" -a ! -e "$SUDO_USER_HOME/config/apache2/sites-available" ] ; then
        mv "/etc/apache2/sites-available" "$SUDO_USER_HOME/config/apache2" || aborting "Can't move /etc/apache2/sites-available to $SUDO_USER_HOME/config/apache2"
    fi

    if [ ! -e "/etc/apache2/sites-available" -a -d "$SUDO_USER_HOME/config/apache2/sites-available" ] ; then
        ln -s "$SUDO_USER_HOME/config/apache2/sites-available" "/etc/apache2/sites-available" || abort "Can't link $SUDO_USER_HOME/config/apache2/sites-available to /etc/apache2/sites-available"
    fi

    systemctl start apache2 || abort "Can't restart apache2"
}

determine_platform_branch() {
    PLATFORM_LABEL=$(cat /proc/device-tree/model | tr '\0' '\n' ; echo '')
    case "$PLATFORM_LABEL" in
        "NVIDIA Jetson Nano Developer Kit")
            PLATFORM_BRANCH=sbts-jetson-nano
            nvpmodel -m 0
	    jetson_clocks --fan
	    echo "Jetson Nano detected"
            ;;
        "NVIDIA Jetson Xavier NX Developer Kit")
            PLATFORM_BRANCH=sbts-jetson-xavier-nx
            nvpmodel -m 8
	    jetson_clocks --fan

            if [ -d /var/lib/nvpmodel/status ] ; then
                echo -n 'pmode:0008 fmode:quiet' > /var/lib/nvpmodel/status
            fi

	    echo "Jetson Xavier NX detected"
            ;;
        "Jetson-AGX")
            PLATFORM_BRANCH=sbts-jetson-xavier-agx
            nvpmodel -m 3
	    jetson_clocks --fan

            if [ -d /var/lib/nvpmodel/status ] ; then
                echo -n 'pmode:0003 fmode:quiet' > /var/lib/nvpmodel/status
            fi

	    echo "Jetson Xavier AGX detected"
            ;;
        *)
            abort "Cannot determine the platform type to build darknet for"
            ;;
    esac
}

install_darknet() {
    PJREDDIE_DARKNET="https://github.com/hcfman/darknet.git"

    echo ""
    echo "Installing PJReddie darknet"
    echo ""

    if [ -e "$SUDO_USER_HOME/darknet" ] ; then
        echo "$PJREDDIE_DARKNET is already installed"
        return
    fi

    cd "$SUDO_USER_HOME" || abort "Can't change directory to $SUDO_USER_HOME"
    su "$SUDO_USER" -c "git clone --branch \"$PLATFORM_BRANCH\" $PJREDDIE_DARKNET" || abort "Can't clone darknet"
    cd "darknet" || abort "Can't change directory to darknet"

    if ! su "$SUDO_USER" -c "make -j4" ; then
        cd "$SUDO_USER_HOME" && rm -rf darknet
        abort "Unable to make darknet"
    fi

    chown -R "$SUDO_USER:$SUDO_USER" .

    if [ ! -e "$SUDO_USER_HOME/darknet/libdarknet.so" ] ; then
        cd "$SUDO_USER_HOME" && rm -rf darknet
        abort "Can't make darknet properly, $SUDO_USER_HOME/darknet/libdarknet.so does not exist"
    fi

    if ! su "$SUDO_USER" -c "chmod +x sbts*.py start_sbts_pj_yolov3_server.sh" ; then
        cd "$SUDO_USER_HOME" && rm -rf darknet
        abort "Can't set executable python and shell scripts in $SUDO_USER_HOME/darknet"
    fi

    YOLOV3_WEIGHTS_LOCATION="https://pjreddie.com/media/files/yolov3.weights"
    if ! sudo -H -u "$SUDO_USER" wget "$YOLOV3_WEIGHTS_LOCATION" ; then
        cd "$SUDO_USER_HOME" && rm -rf darknet
        abort "Can't copy yolov3.weights from $YOLOV3_WEIGHTS_LOCATION"
    fi

}

has_more_than_4GB() {
    if (( $(fgrep MemTotal /proc/meminfo |awk '{print $2}') > 5000000 )) ; then
        return 0
    else
        return 1
    fi
}

install_yolov7() {
    YOLOV7_SBTS_STABLE_COMMIT="9ee1835a7e38254182bdddd46d33484e05d009b7"
    YOLOV7_URL="https://github.com/WongKinYiu/yolov7.git"

    # This needs around 4GB of resident memory to run
    if ! has_more_than_4GB ; then
        return
    fi

    echo ""
    echo "Installing yolov7"
    echo ""

    if [ -e "$SUDO_USER_HOME/yolov7" ] ; then
        echo "YOLOV7_URL already installed"
        return
    fi

    cd "$SUDO_USER_HOME" || abort "Can't change directory to $SUDO_USER_HOME"

    if ! su "$SUDO_USER" -c "git clone \"$YOLOV7_URL\" yolov7" ; then
        abort "Can't clone YOLOV7_URL"
    fi

    cd "$SUDO_USER_HOME/yolov7" || abort "Can't change to $SUDO_USER_HOME/yolov7"

    # Stable with sbts code
    if ! su "$SUDO_USER" -c "git checkout \"$YOLOV7_SBTS_STABLE_COMMIT\"" ; then
        abort "Can't checkout SBTS stable commit for yolov7"
    fi

    if ! su "$SUDO_USER" -c "mkdir runs" ; then
        abort "Can't create runs directory"
    fi

    migrate_sbts_dir "$SUDO_USER_HOME/yolov7/runs" "$SUDO_USER_HOME/disk/yolov7"

    mkdir weights
    if ! cd "weights" ; then
        abort "Can't directory to weights"
    fi

    download_file "https://github.com/WongKinYiu/yolov7/releases/download/v0.1/yolov7-e6e.pt"
    download_file "https://github.com/WongKinYiu/yolov7/releases/download/v0.1/yolov7-d6.pt"
    download_file "https://github.com/WongKinYiu/yolov7/releases/download/v0.1/yolov7-e6.pt"
    download_file "https://github.com/WongKinYiu/yolov7/releases/download/v0.1/yolov7-w6.pt"
    download_file "https://github.com/WongKinYiu/yolov7/releases/download/v0.1/yolov7x.pt"
    download_file "https://github.com/WongKinYiu/yolov7/releases/download/v0.1/yolov7.pt"
}

install_yolor() {
    YOLOR_SBTS_STABLE_COMMIT="be7da6eba2f612a15bf462951d3cdde66755a180"
    YOLOR_URL="https://github.com/WongKinYiu/yolor.git"

    # This needs around 4GB of resident memory to run
    if ! has_more_than_4GB ; then
        return
    fi

    echo ""
    echo "Installing yolor"
    echo ""

    if [ -e "$SUDO_USER_HOME/yolor-paper" ] ; then
        echo "YOLOR_URL already installed"
        return
    fi

    cd "$SUDO_USER_HOME" || abort "Can't change directory to $SUDO_USER_HOME"

    if ! su "$SUDO_USER" -c "git clone \"$YOLOR_URL\" yolor-paper" ; then
        abort "Can't clone YOLOR_URL"
    fi

    cd "$SUDO_USER_HOME/yolor-paper" || abort "Can't change to $SUDO_USER_HOME/yolor-paper"

    if ! su "$SUDO_USER" -c "git checkout paper" ; then
        abort "Can't checkout yolor paper branch"
    fi

    # Stable with sbts code
    if ! su "$SUDO_USER" -c "git checkout \"$YOLOR_SBTS_STABLE_COMMIT\"" ; then
        abort "Can't checkout SBTS stable commit for yolor"
    fi

    if [ ! -d "inference" ] ; then
        if ! su "$SUDO_USER" -c "mkdir inference" ; then
            abort "Can't create inference directory"
        fi
    fi

    migrate_sbts_dir "$SUDO_USER_HOME/yolor/inference" "$SUDO_USER_HOME/disk/yolor"

    mkdir weights
    if ! cd "weights" ; then
        abort "Can't directory to weights"
    fi

    # yolor-d6.pt
    gdown_file "1WX33ymg_XJLUJdoSf5oUYGHAtpSG2gj8"
    # yolor-p6.pt
    gdown_file "1WyzcN1-I0n8BoeRhi_xVt8C5msqdx_7k"
    # yolor-w6.pt
    gdown_file "1KnkBzNxATKK8AiDXrW_qF-vRNOsICV0B"
    # yolor-e6.pt
    gdown_file "1jVrq8R1TA60XTUEqqljxAPlt0M_MAGC8"
}


install_scaled_yolov4() {
    SCALED_YOLOV4_SBTS_STABLE_COMMIT="676800364a3446900b9e8407bc880ea2127b3415"
    SCALED_YOLOV4_URL="https://github.com/WongKinYiu/ScaledYOLOv4.git"
    SCALED_YOLOV4_DIR="ScaledYOLOv4-large"

    # This needs around 4GB of resident memory to run
    if ! has_more_than_4GB ; then
        return
    fi

    echo ""
    echo "Installing scaled_yolov4"
    echo ""

    if [ -e "$SUDO_USER_HOME/$SCALED_YOLOV4_DIR" ] ; then
        echo "SCALED_YOLOV4_URL already installed"
        return
    fi

    cd "$SUDO_USER_HOME" || abort "Can't change directory to $SUDO_USER_HOME"

    if ! su "$SUDO_USER" -c "git clone \"$SCALED_YOLOV4_URL\" $SCALED_YOLOV4_DIR" ; then
        abort "Can't clone SCALED_YOLOV4_URL"
    fi

    cd "$SUDO_USER_HOME/$SCALED_YOLOV4_DIR" || abort "Can't change to $SUDO_USER_HOME/$SCALED_YOLOV4_DIR"

    if ! su "$SUDO_USER" -c "git checkout yolov4-large" ; then
        abort "Can't checkout scaled_yolov4 yolov4-large branch"
    fi

    # Stable with sbts code
    if ! su "$SUDO_USER" -c "git checkout \"$SCALED_YOLOV4_SBTS_STABLE_COMMIT\"" ; then
        abort "Can't checkout SBTS stable commit for scaled_yolov4"
    fi

    if [ ! -d "inference" ] ; then
        if ! su "$SUDO_USER" -c "mkdir inference" ; then
            abort "Can't create inference directory"
        fi
    fi

    migrate_sbts_dir "$SUDO_USER_HOME/$SCALED_YOLOV4_DIR/inference" "$SUDO_USER_HOME/disk/scaled_yolov4"

    mkdir weights
    if ! cd "weights" ; then
        abort "Can't directory to weights"
    fi

    # yolov4-p7.pt
    gdown_file "18fGlzgEJTkUEiBG4hW00pyedJKNnYLP3"
    # yolov4-p6.pt
    gdown_file "1aB7May8oPYzBqbgwYSZHuATPXyxh9xnf"
    # yolov4-p5.pt
    gdown_file "1aXZZE999sHMP1gev60XhNChtHPRMH3Fz"
}

install_alexeyab_darknet() {
    ALEXEYAB_DARKNET="https://github.com/AlexeyAB/darknet.git"
    ALEXEYAB_WORKING_COMMIT="64efa721ede91cd8ccc18257f98eeba43b73a6af"

    echo ""
    echo "Installing AlexeyAB darknet"
    echo ""

    if [ -e "$SUDO_USER_HOME/alexyab_darknet" ] ; then
        echo "$ALEXEYAB_DARKNET already installed"
        return
    fi

    echo ""
    echo "Installing $ALEXEYAB_DARKNET"
    echo ""

    cd "$SUDO_USER_HOME" || abort "Can't change directory to $SUDO_USER_HOME"

    if ! su "$SUDO_USER" -c "git clone \"$ALEXEYAB_DARKNET\" alexyab_darknet" ; then
        abort "Can't clone $ALEXEYAB_DARKNET"
    fi

    cd "$SUDO_USER_HOME/alexyab_darknet" || abort "Can't change to $SUDO_USER_HOME/alexyab_darknet"

    if ! su "$SUDO_USER" -c "git apply \"$HERE/resources/alexeyab/${PLATFORM_BRANCH}_Makefile.patch\"" ; then
        if ! su "$SUDO_USER" -c "git checkout --detach \"$ALEXEYAB_WORKING_COMMIT\"" ; then
            cd "$SUDO_USER_HOME" && rm -rf alexyab_darknet
            abort "Can't apply patch to AlexeyAB checkout, failed to checkout commit \"${ALEXEYAB_WORKING_COMMIT}\""
        fi

        if ! su "$SUDO_USER" -c "git apply \"$HERE/resources/alexeyab/${PLATFORM_BRANCH}_Makefile.patch\"" ; then
            cd "$SUDO_USER_HOME" && rm -rf alexyab_darknet
            abort "Can't apply patch to AlexeyAB checkout"
        fi
    fi

    if ! su "$SUDO_USER" -c "make -j4" ; then
        abort "Failed to compile AlexeyAB darknet"
    fi

    if ! su "$SUDO_USER" -c "cp $HERE/resources/alexeyab/*.cfg cfg" ; then
        cd "$SUDO_USER_HOME" && rm -rf alexyab_darknet
        abort "Can't copy sbts cfg files to AlexeyAB cfg directory"
    fi

    if ! su "$SUDO_USER" -c "cp $HERE/resources/alexeyab/*.sh ." ; then
        cd "$SUDO_USER_HOME" && rm -rf alexyab_darknet
        abort "Can't copy sbts yolo server shell script files to AlexeyAB directory"
    fi

    if ! su "$SUDO_USER" -c "cp $HERE/resources/alexeyab/*.py ." ; then
        cd "$SUDO_USER_HOME" && rm -rf alexyab_darknet
        abort "Can't copy sbts yolo server python files to AlexeyAB directory"
    fi

    if ! su "$SUDO_USER" -c "chmod +x sbts*.py start_sbts_ab_yolov3_server.sh start_sbts_ab_yolov4_server.sh" ; then
        cd "$SUDO_USER_HOME" && rm -rf alexyab_darknet
        abort "Can't set executable python and shell scripts in $SUDO_USER_HOME/alexyab_darknet"
    fi

    if ! su "$SUDO_USER" -c "cp \"$SUDO_USER_HOME/darknet/yolov3.weights\" ." ; then
        cd "$SUDO_USER_HOME" && rm -rf alexyab_darknet
        abort "Can't copy yolov3.weights from $YOLOV3_WEIGHTS_LOCATION"
    fi

    YOLOV4_WEIGHTS_LOCATION="https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v3_optimal/yolov4.weights"
    if ! sudo -H -u "$SUDO_USER" wget "$YOLOV4_WEIGHTS_LOCATION" ; then
        cd "$SUDO_USER_HOME" && rm -rf alexyab_darknet
        abort "Can't copy yolov4.weights from $YOLOV4_WEIGHTS_LOCATION"
    fi
}

migrate_sbts_dir() {
    local source=$1
    local target=$2

    local source_dir_part=${source##*/}

    if [ ! -d "$target" ] ; then
        if ! mkdir "$target" ; then
            abort "Could not create $target"
        fi
    fi

    if [ ! -L "$source" ] ; then
        echo "Need to make a symlink for $source"

        if [ -d "$target/$source_dir_part" ] ; then
            if ! rm -rf "$target/$source_dir_part" ; then
                abort "Could not remove $target/$source_dir_part"
            fi
        fi

        if ! mv "$source" "$target" ; then
            abort "Could not move $source to $target"
        fi

        if ! ln -s "$target/$source_dir_part" "$source" ; then
            abort "Could not make a symlink from $target/$source_dir_part to $source"
        fi
    fi
}

download_latests_app_release() {
    cd "$HERE" || abort "Can't change back to $HERE"

    if [ ! -f "$APP_FILE" ] ; then
	sudo -H -u "$SUDO_USER" wget "$APP_URL" || abort "Can't download latest app release from $APP_URL"
    fi

    [[ -f "$APP_FILE" ]] || abort "File $APP_FILE disappeared"

    [[ "$(md5sum $APP_FILE | awk '{print $1}')" == "$APP_CHECKSUM" ]] || abort "Checksum of latest release doens't match the release, not proceeding"
}

unpack_app() {
    cd "$SUDO_USER_HOME" || abort "Can't change directory to $SUDO_USER_HOME"

    if [ -d "app" ] ; then
	return
    fi

    tar xvzf "$HERE/$APP_FILE" || abort "Can't unpack application tree \"app\" into home directory"

    if fgrep '${admin.user}' "$SUDO_USER_HOME/app/tomcat/apache-tomcat-9.0.45/conf/tomcat-users.xml" > /dev/null ; then
	if ! perl -pi -e "s%\\\$\\{admin\\.user\\}%${tomcat_username}%g" "$SUDO_USER_HOME/app/tomcat/apache-tomcat-9.0.45/conf/tomcat-users.xml" ; then
	    abort "Can't alter the tomcat Username"
	fi
    fi

    if fgrep '${admin.password}' "$SUDO_USER_HOME/app/tomcat/apache-tomcat-9.0.45/conf/tomcat-users.xml" > /dev/null ; then
	if ! perl -pi -e "s%\\\$\\{admin\\.password\\}%${tomcat_password}%g" "$SUDO_USER_HOME/app/tomcat/apache-tomcat-9.0.45/conf/tomcat-users.xml" ; then
	    abort "Can't alter the tomcat Password"
	fi
    fi

    if fgrep '${tomcat.username}' "$SUDO_USER_HOME/app/conf/sbts.xml" > /dev/null ; then
	if ! perl -pi -e "s%\\\$\\{tomcat\\.username\\}%${tomcat_username}%g" "$SUDO_USER_HOME/app/conf/sbts.xml" ; then
	    abort "Can't alter the tomcat Username in sbts.xml"
	fi
    fi

    if fgrep '${tomcat.password}' "$SUDO_USER_HOME/app/conf/sbts.xml" > /dev/null ; then
	if ! perl -pi -e "s%\\\$\\{tomcat\\.password\\}%${tomcat_password}%g" "$SUDO_USER_HOME/app/conf/sbts.xml" ; then
	    abort "Can't alter the tomcat Password sbts.xml"
	fi
    fi

    if fgrep '${password}' "$SUDO_USER_HOME/app/bin/backup.sh" > /dev/null ; then
	if ! perl -pi -e "s%\\\$\\{password\\}%${backup_password}%g" "$SUDO_USER_HOME/app/bin/backup.sh" ; then
	    abort "Can't alter the backup/restore password"
	fi
    fi

    if fgrep '${password}' "$SUDO_USER_HOME/app/bin/restore.sh" > /dev/null ; then
	if ! perl -pi -e "s%\\\$\\{password\\}%${backup_password}%g" "$SUDO_USER_HOME/app/bin/restore.sh" ; then
	    abort "Can't alter the backup/restore password"
	fi
    fi

    if [ ! -L "$SUDO_USER_HOME/app/bin/mount_readonly" ] ; then
	sudo -H -u "$SUDO_USER" ln -s "$SUDO_USER_HOME/sbts-bin/mount_readonly" "$SUDO_USER_HOME/app/bin" || abort "Can't link sbts-bin/mount_readonly to app/bin"
    fi

    if [ ! -L "$SUDO_USER_HOME/app/bin/mount_readwrite" ] ; then
	sudo -H -u "$SUDO_USER" ln -s "$SUDO_USER_HOME/sbts-bin/mount_readwrite" "$SUDO_USER_HOME/app/bin" || abort "Can't link sbts-bin/mount_readwrite to app/bin"
    fi

    if fgrep '${domainPiece}' "$SUDO_USER_HOME/app/conf/sbts.xml" > /dev/null ; then
	if ! perl -pi -e "s%\\\$\\{domainPiece\\}%${DOMAIN_PIECE}%g" "$SUDO_USER_HOME/app/conf/sbts.xml" ; then
	    abort "Can't alter the sbts.xml domainPiece"
	fi
    fi

    if fgrep '${domainPrefix}' "$SUDO_USER_HOME/app/conf/sbts.xml" > /dev/null ; then
	if ! perl -pi -e "s%\\\$\\{domainPrefix\\}%${DOMAIN_PREFIX}%g" "$SUDO_USER_HOME/app/conf/sbts.xml" ; then
	    abort "Can't alter the sbts.xml domainPrefix"
	fi
    fi
}

create_reboot_and_shutdown() {
    cd "$SUDO_USER_HOME" || abort "Can't change directory to $SUDO_USER_HOME"

    echo ""
    echo "Create reboot and shutdown"
    echo ""

    cd "$SUDO_USER_HOME/app/bin" || abort "Can't change to $SUDO_USER_HOME/app/bin"
    gcc sbts_reboot.c -o sbts_reboot || abort "Can't compile sbts_reboot.c"
    gcc sbts_shutdown.c -o sbts_shutdown || abort "Can't compile sbts_shutdown.c"
    mv sbts_reboot sbts_shutdown /usr/local/sbts-sbin || abort "Can't move sbts_reboot and sbts_shutdown to /usr/local/sbts-sbin"
    chown root:root "/usr/local/sbts-sbin/sbts_reboot" "/usr/local/sbts-sbin/sbts_shutdown" || abort "Can't chown root:root /usr/local/sbts-sbin/sbts_reboot /usr/local/sbts-sbin/sbts_shutdown"
    chmod +s,g+s "/usr/local/sbts-sbin/sbts_reboot" "/usr/local/sbts-sbin/sbts_shutdown" || abort "Can't chmod setuid root /usr/local/sbts-sbin/sbts_reboot and /usr/local/sbts-sbin/sbts_shutdown"
    ln -s /usr/local/sbts-sbin/sbts_reboot . || abort "Can't create symlink from /usr/local/sbts-sbin/sbts_reboot to app/bin"
    ln -s /usr/local/sbts-sbin/sbts_shutdown . || abort "Can't create symlink from /usr/local/sbts-sbin/sbts_shutdown to app/bin"

}

update_udev_rules() {
    if ! cd $HERE ; then
        abort "Can't change to $HERE"
    fi

    cp resources/{98,99}* /etc/udev/rules.d
    udevadm control --reload-rules
}

install_tomcat() {
    echo ""
    echo "Installing apache tomcat"
    echo ""

    if ! cd $HERE ; then
        abort "Can't change to $HERE"
    fi

    TOMCAT_VERSION=$(echo "$SUDO_USER_HOME"/app/tomcat/apache-tomcat-* | sed -e 's/.*apache-tomcat-//')

    migrate_sbts_dir "$SUDO_USER_HOME/app/tomcat/apache-tomcat-${TOMCAT_VERSION}/conf" "$SUDO_USER_HOME/config/tomcat"
    migrate_sbts_dir "$SUDO_USER_HOME/app/tomcat/apache-tomcat-${TOMCAT_VERSION}/logs" "$SUDO_USER_HOME/disk/tomcat"
}

move_disk_to_disk_partition() {
    migrate_sbts_dir "$SUDO_USER_HOME/app/disk" "$SUDO_USER_HOME/disk/sbts"
    migrate_sbts_dir "$SUDO_USER_HOME/app/conf" "$SUDO_USER_HOME/config/sbts"
    migrate_sbts_dir "$SUDO_USER_HOME/app/certs" "$SUDO_USER_HOME/config/sbts"
    migrate_sbts_dir "$SUDO_USER_HOME/app/cacerts" "$SUDO_USER_HOME/config/sbts"

    if [ ! -d "$SUDO_USER_HOME/disk/log" ] ; then
        mkdir "$SUDO_USER_HOME/disk/log" || abort "Can't create $SUDO_USER_HOME/disk/log"
    fi

    chown -R "$SUDO_USER:$SUDO_USER" "$SUDO_USER_HOME/disk/log" || abort "Can't chown $SUDO_USER:$SUDO_USER $SUDO_USER_HOME/disk/log"
}

install_secure() {
    cd "$HERE" || abort "Can't change back to $HERE"

    if [ -f "$SUDO_USER_HOME/config/secure/resources/config.json" -a -f "$SUDO_USER_HOME/config/secure/resources/nano_config.json" -a -f "$SUDO_USER_HOME/sbts-secure/sbts-secure.py" -a -f "$SUDO_USER_HOME/sbts-secure/start_secure.sh" -a -f "" -a -d "$SUDO_USER_HOME/sbts-secure/multi_secureparse" -a -d "$SUDO_USER_HOME/config/secure/resources" ] ; then
	return
    fi

    echo ""
    echo "Installing secure"
    echo ""

    if [ ! -d "$SUDO_USER_HOME/sbts-secure" ] ; then
	sudo -H -u "$SUDO_USER" mkdir "$SUDO_USER_HOME/sbts-secure" || abort "Can't create $SUDO_USER_HOME/sbts-secure"
    fi

    if ! sudo -H -u "$SUDO_USER" cp -p -r resources/secure/sbts-secure.py resources/secure/sbts-test.py resources/secure/start_secure.sh resources/secure/multi_secureparse resources/secure/sbts-draw.py resources/secure/sbts-annotate.py resources/secure/vlc_front.sh resources/secure/vlc_back.sh "$SUDO_USER_HOME/sbts-secure" ; then
	abort "Can't install the \"secure\" program"
    fi

    if [ ! -d "$SUDO_USER_HOME/config/secure" ] ; then
	mkdir "$SUDO_USER_HOME/config/secure" || abort "Can't create directory $SUDO_USER_HOME/config/secure"
    fi

    if [ ! -d "$SUDO_USER_HOME/config/secure/resources" ] ; then
	mkdir "$SUDO_USER_HOME/config/secure/resources" || abort "Can't create $SUDO_USER_HOME/config/secure/resources"
    fi

    if ! chown "$SUDO_USER:$SUDO_USER" "$SUDO_USER_HOME/config/secure/resources" ; then
	abort "Can't chown $SUDO_USER:$SUDO_USER $SUDO_USER_HOME/config/secure/resources"
    fi

    if ! sudo -H -u "$SUDO_USER" cp -r resources/secure/config.json "$SUDO_USER_HOME/config/secure/resources" ; then
	abort "Can't install config.json to $SUDO_USER_HOME/config/secure/resources"
    fi

    if ! sudo -H -u "$SUDO_USER" cp -r resources/secure/nano_config.json "$SUDO_USER_HOME/config/secure/resources" ; then
	abort "Can't install nano_config.json to $SUDO_USER_HOME/config/secure/resources"
    fi

    if [ ! -L "$SUDO_USER_HOME/sbts-secure/resources" ] ; then
	if ! sudo -H -u "$SUDO_USER" ln -s "$SUDO_USER_HOME/config/secure/resources" "$SUDO_USER_HOME/sbts-secure/resources" ; then
	    abort "Can't create symlink from $SUDO_USER_HOME/config/secure/resources to $SUDO_USER_HOME/sbts-secure/resources"
	fi
    fi

    if fgrep '${admin.user}' "$SUDO_USER_HOME/config/secure/resources/config.json" > /dev/null ; then
	if ! perl -pi -e "s%\\\$\\{admin\\.user\\}%${tomcat_username}%g" "$SUDO_USER_HOME/config/secure/resources/config.json" ; then
	    abort "Can't alter the tomcat Username in config.json"
	fi
    fi

    if fgrep '${admin.password}' "$SUDO_USER_HOME/config/secure/resources/config.json" > /dev/null ; then
	if ! perl -pi -e "s%\\\$\\{admin\\.password\\}%${tomcat_password}%g" "$SUDO_USER_HOME/config/secure/resources/config.json" ; then
	    abort "Can't alter the tomcat Password config.json"
	fi
    fi

    if fgrep '${admin.user}' "$SUDO_USER_HOME/config/secure/resources/nano_config.json" > /dev/null ; then
	if ! perl -pi -e "s%\\\$\\{admin\\.user\\}%${tomcat_username}%g" "$SUDO_USER_HOME/config/secure/resources/nano_config.json" ; then
	    abort "Can't alter the tomcat Username in nano_config.json"
	fi
    fi

    if fgrep '${admin.password}' "$SUDO_USER_HOME/config/secure/resources/nano_config.json" > /dev/null ; then
	if ! perl -pi -e "s%\\\$\\{admin\\.password\\}%${tomcat_password}%g" "$SUDO_USER_HOME/config/secure/resources/nano_config.json" ; then
	    abort "Can't alter the tomcat Password nano_config.json"
	fi
    fi

    if [ "$PLATFORM_LABEL" == "NVIDIA Jetson Nano Developer Kit" ] ; then
        if grep /config.json "$SUDO_USER_HOME/sbts-secure/start_secure.sh" > /dev/null ; then
            if ! perl -pi -e "s%/config.json%/nano_config.json%g" "$SUDO_USER_HOME/sbts-secure/start_secure.sh" ; then
                abort "Can't set the correct config file for the nano"
            fi
        fi
    fi
}

determine_partition_base() {
    partition_base_path=$(findmnt -n / | awk '{print $2}' | sed -e 's/1$//')
}

update_etc_rc() {
    if [ -f "/etc/rc.local" ] ; then
	return
    fi

    cd "$HERE" || abort "Can't change back to $HERE"

    cat > /etc/rc.local <<EOF
#!/bin/bash

modprobe nvgpu
sleep 2

/usr/bin/jetson_clocks --fan
EOF

    chmod +x /etc/rc.local

    case "$PLATFORM_LABEL" in
        "NVIDIA Jetson Nano Developer Kit")
            PLATFORM_BRANCH=sbts-jetson-nano
            echo nvpmodel -m 0 >> /etc/rc.local
            ;;
        "NVIDIA Jetson Xavier NX Developer Kit")
            PLATFORM_BRANCH=sbts-jetson-xavier-nx
            echo nvpmodel -m 8 >> /etc/rc.local
            ;;
        "Jetson-AGX")
            PLATFORM_BRANCH=sbts-jetson-xavier-agx
            echo nvpmodel -m 3 >> /etc/rc.local
            ;;
        *)
            abort "Cannot determine the platform type"
            ;;
    esac

    echo "" >> /etc/rc.local

    cat >> /etc/rc.local <<EOF
fsck -y ${partition_base_path}2
fsck -y ${partition_base_path}3

mount ${partition_base_path}2 ${SUDO_USER_HOME}/config
mount ${partition_base_path}3 ${SUDO_USER_HOME}/disk

systemctl start apache2

# su - $SUDO_USER -c '$SUDO_USER_HOME/sbts-local/dynu_client.py > $SUDO_USER_HOME/disk/log/dynu_client.log'

# Choose just one of the below, comment out the ones that are not chosen
EOF

    case "$PLATFORM_LABEL" in
        "NVIDIA Jetson Nano Developer Kit")
            cat >> /etc/rc.local <<EOF
#su - "${SUDO_USER}" -c "${SUDO_USER_HOME}/darknet/start_sbts_pj_yolov3_server.sh > /dev/null 2>&1 &" &
#su - "${SUDO_USER}" -c "${SUDO_USER_HOME}/alexyab_darknet/start_sbts_ab_yolov3_server.sh > /dev/null 2>&1 &" &
su - "${SUDO_USER}" -c "${SUDO_USER_HOME}/alexyab_darknet/start_sbts_ab_yolov4_server.sh > /dev/null 2>&1 &" &
EOF
            ;;
        "NVIDIA Jetson Xavier NX Developer Kit")
            cat >> /etc/rc.local <<EOF
su - "${SUDO_USER}" -c "${SUDO_USER_HOME}/darknet/start_sbts_pj_yolov3_server.sh > /dev/null 2>&1 &" &
#su - "${SUDO_USER}" -c "${SUDO_USER_HOME}/alexyab_darknet/start_sbts_ab_yolov3_server.sh > /dev/null 2>&1 &" &
su - "${SUDO_USER}" -c "${SUDO_USER_HOME}/alexyab_darknet/start_sbts_ab_yolov4_server.sh > /dev/null 2>&1 &" &
EOF
            ;;
        "Jetson-AGX")
            cat >> /etc/rc.local <<EOF
su - "${SUDO_USER}" -c "${SUDO_USER_HOME}/darknet/start_sbts_pj_yolov3_server.sh > /dev/null 2>&1 &" &
#su - "${SUDO_USER}" -c "${SUDO_USER_HOME}/alexyab_darknet/start_sbts_ab_yolov3_server.sh > /dev/null 2>&1 &" &
su - "${SUDO_USER}" -c "${SUDO_USER_HOME}/alexyab_darknet/start_sbts_ab_yolov4_server.sh > /dev/null 2>&1 &" &
EOF
            ;;
        *)
            abort "Cannot determine the platform type"
            ;;
    esac

    cat >> /etc/rc.local <<EOF

sleep 20

su - "${SUDO_USER}" -c "${SUDO_USER_HOME}/sbts-local/vlc_front.sh > /dev/null 2>&1 &" &
su - "${SUDO_USER}" -c "${SUDO_USER_HOME}/sbts-local/vlc_back.sh > /dev/null 2>&1 &" &

su - "${SUDO_USER}" -c "${SUDO_USER_HOME}/app/bin/start.sh > /dev/null 2>&1 &" &

su - "${SUDO_USER}" -c "${SUDO_USER_HOME}/sbts-secure/start_secure.sh > /dev/null 2>&1 &" &

exit 0
EOF
    chmod +x /etc/rc.local

    systemctl stop apache2
    systemctl disable apache2

    if grep "^${partition_base_path}1" /etc/fstab > /dev/null || grep "^${partition_base_path}3" /etc/fstab > /dev/null ; then
	if ! perl -pi -e "s%^${partition_base_path}%#${partition_base_path}%" /etc/fstab ; then
	    abort "Can't modify /etc/fstab"
	fi
    fi
}

#
# As something else re-enabled docker (Probably the docker.socket service)
#
# The installed docker location is incompatible with this mode of operation as it would need to run on top of
# an overlayFS which doesn't work. If you need docker, then you will ensure that the docker that docker uses to write
# things to is on a normal read/write location. Such as somewhere under SUDO_USER_HOME/disk. Note also, you would likely also
# have to stop docker from starting and start it again in /etc/rc.local after the disks are mounted, much like is done with apache
#
disable_docker_again() {
    systemctl stop docker.service
    systemctl stop docker.socket
    systemctl disable docker.service
    systemctl disable docker.socket
}

disable_gui_for_nano() {
    if [ "$PLATFORM_LABEL" == "NVIDIA Jetson Nano Developer Kit" ] ; then
        echo ""
        echo "Turning off the GUI for the nano"
        echo ""

        systemctl set-default multi-user.target
    fi
}

make_readonly_and_reboot() {
    if ! "${SUDO_USER_HOME}/sbts-bin/make_readonly.sh" ; then
	abort "Can't set the system to boot into read-only mode"
    fi

    echo ""
    echo "Successfully installed stalkedbythestate"
    echo ""

    echo "A reboot is now required to finish installation. After the reboot, the system will be running in read-only mode"
    echo ""

    echo "Rebooting in 10 seconds..."
    sleep 10
    reboot
}

create_sbts_local() {
    echo "Create sbts-local"
    echo ""

    if [ ! -d "${SUDO_USER_HOME}/sbts-local" ] ; then
        sudo -H -u "$SUDO_USER" mkdir "$SUDO_USER_HOME/sbts-local" || abort "Can't create ${SUDO_USER_HOME}/sbts-local"
    fi

    if [ ! -f "${SUDO_USER_HOME}/sbts-local/vlc_front.sh" ] ; then
	sudo -H -u "$SUDO_USER" cp -p "${SUDO_USER_HOME}/sbts-secure/vlc_front.sh" "${SUDO_USER_HOME}/sbts-local" || abort "Can't cp ${SUDO_USER_HOME}/sbts-secure/vlc_front.sh to ${SUDO_USER_HOME}/sbts-local"
    fi

    if [ ! -f "${SUDO_USER_HOME}/sbts-local/vlc_back.sh" ] ; then
	sudo -H -u "$SUDO_USER" cp -p "${SUDO_USER_HOME}/sbts-secure/vlc_back.sh" "${SUDO_USER_HOME}/sbts-local" || abort "Can't cp ${SUDO_USER_HOME}/sbts-secure/vlc_back.sh to ${SUDO_USER_HOME}/sbts-local"
    fi

    if [ ! -f "${SUDO_USER_HOME}/sbts-local/000-default-le-ssl.conf" ] ; then
        if ! sudo -H -u "$SUDO_USER" cp -r resources/letsencrypt/000-default-le-ssl.conf "$SUDO_USER_HOME/sbts-local" ; then
            abort "Can't install 000-default-le-ssl.conf to $SUDO_USER_HOME/sbts-local"
        fi

    fi

    if fgrep '${domainPiece}' "$SUDO_USER_HOME/sbts-local/000-default-le-ssl.conf" > /dev/null ; then
	if ! perl -pi -e "s%\\\$\\{domainPiece\\}%${DOMAIN_PIECE}%g" "$SUDO_USER_HOME/sbts-local/000-default-le-ssl.conf" ; then
	    abort "Can't alter the 000-default-le-ssl.conf domainPiece"
	fi
    fi

    if fgrep '${domainPrefix}' "$SUDO_USER_HOME/sbts-local/000-default-le-ssl.conf" > /dev/null ; then
	if ! perl -pi -e "s%\\\$\\{domainPrefix\\}%${DOMAIN_PREFIX}%g" "$SUDO_USER_HOME/sbts-local/000-default-le-ssl.conf" ; then
	    abort "Can't alter the 000-default-le-ssl.conf domainPrefix"
	fi
    fi
}

install_dynu_client() {
    if [ ! -f "${SUDO_USER_HOME}/sbts-local/dynu_client.py" ] ; then
        sudo -H -u "$SUDO_USER" cp -p resources/dynu/dynu_client.py "${SUDO_USER_HOME}/sbts-local" || abort "Can't copy dynu_client.py to ${SUDO_USER_HOME}/sbts-local"
    fi

    if [ ! -f "${SUDO_USER_HOME}/sbts-local/dynuParams.config" ] ; then
        sudo -H -u "$SUDO_USER" cp resources/dynu/dynuParams.config "${SUDO_USER_HOME}/sbts-local" || abort "Can't copy dynuParams.config to ${SUDO_USER_HOME}/sbts-local"
    fi
}

add_crontabs() {
    echo "# $(perl -e 'print int(rand(59))') $(perl -e 'print int(rand(23))') * * * su $SUDO_USER - -c \"$SUDO_USER_HOME/sbts-bin/mount_readwrite\";(sleep 2; /usr/bin/certbot --apache --renew-hook \"systemctl restart apache2\" renew > $SUDO_USER_HOME/disk/log/certbot.log 2>&1);su $SUDO_USER - -c \"$SUDO_USER_HOME/sbts-bin/mount_readonly\"" > /tmp/root_crontab || abort "Can't create root crontab file"

    crontab /tmp/root_crontab || abort "Can't set root crontab to renew letsencrypt certificate"
    rm /tmp/root_crontab > /dev/null 2>&1

    echo "# $(perl -e 'print int(rand(59))') $(perl -e 'print int(rand(23))') * * *  $SUDO_USER_HOME/sbts-local/dynu_client.py > $SUDO_USER_HOME/disk/log/dynu_client.log 2>&1" > /tmp/user_crontab
    sudo -H -u "$SUDO_USER" crontab /tmp/user_crontab || abort "Can't install dynu client into user crontab"
    rm /tmp/user_crontab > /dev/null 2>&1
}

install_certbot_again() {
    # This was done before but in practise I found I had to install it again afterwards. Maybe something undid something.
    apt install -y python3-certbot-apache
}

set_prefixes() {
    DOMAIN_PIECE=$(pwgen 10 1)
    DOMAIN_PREFIX=$(pwgen 10 1)
}

#
# Main
#

if [ "$(id -n -u)" != "root" ] ; then
    abort "You need to execute this script as root"
fi

if [ ! "$SUDO_USER" -o "$SUDO_USER" == "root" ] ; then
    abort "Please execute this script simply as sudo $(basename $0)"
fi

SUDO_USER_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)

sanity_check

get_credentials

determine_platform_branch

update_pkg_registry

prep_pip_installation

install_packages

set_prefixes

remove_apache_default_pages

install_python_modules

install_apache2_modules

install_extra_apache2_ssl_config

migrate_letsencrypt

migrate_apache2_sites-available

install_darknet

install_alexeyab_darknet

install_yolov7

install_yolor

install_scaled_yolov4

download_latests_app_release

unpack_app

create_reboot_and_shutdown

update_udev_rules

install_tomcat

move_disk_to_disk_partition

install_secure

determine_partition_base

update_etc_rc

create_sbts_local

install_dynu_client

add_crontabs

install_certbot_again

disable_docker_again

disable_gui_for_nano

make_readonly_and_reboot
