#!/bin/bash


UPDATED=

APP_FILE="stalkedbythestate_app_jetson_v1.00.tar.gz"
APP_URL="https://github.com/hcfman/stalkedbythestate/releases/download/stalkedbythestate_app_jetson_v1.00/$APP_FILE"
APP_CHECKSUM="9191ba89947291033d297e2c962d81c2"

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
        abort "You need to run this script from a read-write mounted SSD drive"
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

install_packages() {
    echo ""
    echo "Installing packages"
    echo ""

    for package in  openjdk-8-jdk python3-numpy python3-pip libgeos-3.6.2 libgeos-c1v5 apache2 letsencrypt python3-certbot-apache python3-opencv maven; do
        if ! dpkg -l "$package" > /dev/null 2>&1 ; then
            echo "Installing package \"$package\""
            install_package "$package"
        fi
    done
}

install_module() {
    module=$1

    if ! python3 -c "import $module" ; then
        echo "Installing pip3 module \"$module\""
        if ! pip3 install "$module" ; then
            abort "Can't install pip3 module \"$module\""
        fi
    fi
}

install_python_modules() {
    echo ""
    echo "Installing python modules"
    echo ""

    module=$1

    for m in flask requests websockets shapely configparser ; do
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

migrate_letsencrypt() {
    echo ""
    echo "Migrating letsencrypt to the config partition"
    echo ""

    sudo -u "$SUDO_USER" "$SUDO_USER_HOME/sbts-bin/mount_readwrite" || abort "Can't re-mount $SUDO_USER_HOME/config"

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

    sudo -u "$SUDO_USER" "$SUDO_USER_HOME/sbts-bin/mount_readwrite" || abort "Can't re-mount $SUDO_USER_HOME/config"

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
            nvpmodel -m 2
	    jetson_clocks --fan
	    echo "Jetson Xavier NX detected"
            ;;
        "Jetson-AGX")
            PLATFORM_BRANCH=sbts-jetson-xavier-agx
            nvpmodel -m 0
	    jetson_clocks --fan
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

    if ! su "$SUDO_USER" -c "chmod +x python/sbts*.py start_sbts_yolov3_server.sh" ; then
        cd "$SUDO_USER_HOME" && rm -rf darknet
        abort "Can't set executable python and shell scripts in $SUDO_USER_HOME/darknet"
    fi

    YOLOV3_WEIGHTS_LOCATION="https://pjreddie.com/media/files/yolov3.weights"
    if ! wget "$YOLOV3_WEIGHTS_LOCATION" ; then
        cd "$SUDO_USER_HOME" && rm -rf darknet
        abort "Can't copy yolov3.weights from $YOLOV3_WEIGHTS_LOCATION"
    fi

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

    if ! su "$SUDO_USER" -c "chmod +x sbts*.py start_sbts_yolov3_server.sh start_sbts_yolov4_server.sh" ; then
        cd "$SUDO_USER_HOME" && rm -rf alexyab_darknet
        abort "Can't set executable python and shell scripts in $SUDO_USER_HOME/alexyab_darknet"
    fi

    if ! su "$SUDO_USER" -c "cp \"$SUDO_USER_HOME/darknet/yolov3.weights\" ." ; then
        cd "$SUDO_USER_HOME" && rm -rf alexyab_darknet
        abort "Can't copy yolov3.weights from $YOLOV3_WEIGHTS_LOCATION"
    fi

    YOLOV4_WEIGHTS_LOCATION="https://github.com/AlexeyAB/darknet/releases/download/darknet_yolo_v3_optimal/yolov4.weights"
    if ! su "$SUDO_USER" -c "wget \"$YOLOV4_WEIGHTS_LOCATION\"" ; then
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
	wget "$APP_URL" || abort "Can't download latest app release from $APP_URL"
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
	sudo -u "$SUDO_USER" ln -s "$SUDO_USER_HOME/sbts-bin/mount_readonly" "$SUDO_USER_HOME/app/bin" || abort "Can't link sbts-bin/mount_readonly to app/bin"
    fi

    if [ ! -L "$SUDO_USER_HOME/app/bin/mount_readwrite" ] ; then
	sudo -u "$SUDO_USER" ln -s "$SUDO_USER_HOME/sbts-bin/mount_readwrite" "$SUDO_USER_HOME/app/bin" || abort "Can't link sbts-bin/mount_readwrite to app/bin"
    fi
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
}

move_disk_to_disk_partition() {
    migrate_sbts_dir "$SUDO_USER_HOME/app/disk" "$SUDO_USER_HOME/disk/sbts"
    migrate_sbts_dir "$SUDO_USER_HOME/app/conf" "$SUDO_USER_HOME/config/sbts"
    migrate_sbts_dir "$SUDO_USER_HOME/app/certs" "$SUDO_USER_HOME/config/sbts"
    migrate_sbts_dir "$SUDO_USER_HOME/app/cacerts" "$SUDO_USER_HOME/config/sbts"
}

install_secure() {
    cd "$HERE" || abort "Can't change back to $HERE"

    if [ -f "$SUDO_USER_HOME/sbts-secure/config.json" -a -f "$SUDO_USER_HOME/sbts-secure/secure.py" -a -d "$SUDO_USER_HOME/sbts-secure/secureparse" -a -d "$SUDO_USER_HOME/config/secure/resources" ] ; then
	return
    fi

    echo ""
    echo "Installing secure"
    echo ""

    if [ ! -d "$SUDO_USER_HOME/sbts-secure" ] ; then
	sudo -u "$SUDO_USER" mkdir "$SUDO_USER_HOME/sbts-secure" || abort "Can't create $SUDO_USER_HOME/sbts-secure"
    fi

    if ! sudo -u "$SUDO_USER" cp -r resources/secure/secure.py resources/secure/secureparse "$SUDO_USER_HOME/sbts-secure" ; then
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

    if ! sudo -u "$SUDO_USER" cp -r resources/secure/config.json "$SUDO_USER_HOME/config/secure/resources" ; then
	abort "Can't install config.json to $SUDO_USER_HOME/config/secure/resources"
    fi

    if [ ! -L "$SUDO_USER_HOME/sbts-secure/resources" ] ; then
	if ! ln -s "$SUDO_USER_HOME/config/secure/resources" "$SUDO_USER_HOME/sbts-secure/resources" ; then
	    abort "Can't create symlink from $SUDO_USER_HOME/config/secure/resources to $SUDO_USER_HOME/sbts-secure/resources"
	fi
    fi

    if fgrep '${admin.user}' "$SUDO_USER_HOME/config/secure/resources/config.json" > /dev/null ; then
	if ! perl -pi -e "s%\\\$\\{admin\\.user\\}%${tomcat_username}%g" "$SUDO_USER_HOME/config/secure/resources/config.json" ; then
	    abort "Can't alter the config.json Username"
	fi
    fi

    if fgrep '${admin.password}' "$SUDO_USER_HOME/config/secure/resources/config.json" > /dev/null ; then
	if ! perl -pi -e "s%\\\$\\{admin\\.password\\}%${tomcat_password}%g" "$SUDO_USER_HOME/config/secure/resources/config.json" ; then
	    abort "Can't alter the tomcat Password"
	fi
    fi
}

update_etc_rc() {
    :
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

install_packages

install_python_modules

install_apache2_modules

migrate_letsencrypt

migrate_apache2_sites-available

install_darknet

install_alexeyab_darknet

download_latests_app_release

unpack_app

update_udev_rules

install_tomcat

move_disk_to_disk_partition

install_secure

update_etc_rc

echo ""
echo "Successfully installed stalkedbythestate"
